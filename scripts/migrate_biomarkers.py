"""
Migration script: document_biomarkers -> lab_report + biomarker_observation.

Reads from document_biomarkers + uploaded_files,
matches biomarker names to biomarker_definition via aliases,
creates lab_report and biomarker_observation records.

Idempotent: skips documents that already have a lab_report entry.

Run as: sudo -u postgres /home/dev/biocoach/.venv/bin/python scripts/migrate_biomarkers.py
Or with DATABASE_URL pointing to a superuser connection.
"""

import asyncio
import os
import re
from collections import defaultdict

import asyncpg


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql:///biocoach",
)

# Tables with forced RLS
RLS_TABLES = [
    "document_biomarkers",
    "uploaded_files",
    "lab_report",
    "biomarker_observation",
]


def parse_numeric(value: str) -> float | None:
    """Extract numeric value from string like '40%', '14.2', etc."""
    if value is None:
        return None
    cleaned = re.sub(r"[^\d.,\-]", "", value.strip())
    cleaned = cleaned.replace(",", ".")
    if not cleaned or cleaned == "-" or cleaned == ".":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize(name: str) -> str:
    """Normalize a name for comparison: lowercase, strip, collapse spaces."""
    return re.sub(r"\s+", " ", name.strip().lower())


def build_alias_index(definitions: list[dict]) -> dict[str, int]:
    """Build a lookup: normalized alias -> biomarker_definition id."""
    index: dict[str, int] = {}
    for defn in definitions:
        for name in [defn["name_ru"], defn["name_en"]]:
            key = normalize(name)
            if key not in index:
                index[key] = defn["id"]
        if defn["aliases"]:
            for alias in defn["aliases"]:
                key = normalize(alias)
                if key not in index:
                    index[key] = defn["id"]
    return index


def match_biomarker(name: str, alias_index: dict[str, int]) -> int | None:
    """Try to match a biomarker name to a definition id.

    Strategy:
    1. Exact normalized match
    2. Check if any alias is contained in the name (prefer longest match)
    3. Check if name is contained in any alias
    """
    norm = normalize(name)

    # 1. Exact match
    if norm in alias_index:
        return alias_index[norm]

    # 2. Substring matching (prefer longest alias match)
    best_match: tuple[int, int] | None = None
    for alias, def_id in alias_index.items():
        if alias in norm and len(alias) >= 3:
            if best_match is None or len(alias) > best_match[1]:
                best_match = (def_id, len(alias))
        elif norm in alias and len(norm) >= 3:
            if best_match is None or len(alias) < best_match[1]:
                best_match = (def_id, len(alias))

    if best_match:
        return best_match[0]

    return None


async def disable_rls(conn: asyncpg.Connection) -> None:
    """Disable RLS on migration tables. Requires superuser or table owner."""
    for table in RLS_TABLES:
        try:
            await conn.execute(
                f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"
            )
        except asyncpg.exceptions.InsufficientPrivilegeError:
            pass  # Non-owner; RLS may not apply to this role anyway


async def enable_rls(conn: asyncpg.Connection) -> None:
    """Re-enable forced RLS on migration tables."""
    for table in RLS_TABLES:
        try:
            await conn.execute(
                f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"
            )
            await conn.execute(
                f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"
            )
        except asyncpg.exceptions.InsufficientPrivilegeError:
            pass


async def main() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await disable_rls(conn)
        print("Configured RLS for migration")

        try:
            # Load biomarker definitions
            definitions = await conn.fetch(
                "SELECT id, name_ru, name_en, aliases FROM biomarker_definition"
            )
            defn_list = [dict(d) for d in definitions]
            alias_index = build_alias_index(defn_list)
            print(
                f"Loaded {len(defn_list)} biomarker definitions, "
                f"{len(alias_index)} aliases"
            )

            # Check which file_ids already have lab_reports (idempotency)
            existing = await conn.fetch(
                "SELECT file_id FROM lab_report WHERE file_id IS NOT NULL"
            )
            existing_file_ids = {str(r["file_id"]) for r in existing}
            print(f"Already migrated documents: {len(existing_file_ids)}")

            # Load document_biomarkers with file info
            # Use SET LOCAL to bypass RLS within this session
            await conn.execute(
                "SET LOCAL row_security = off"
            )
            rows = await conn.fetch("""
                SELECT
                    db.id,
                    db.document_id,
                    db.domain_id,
                    db.name,
                    db.value,
                    db.unit,
                    db.created_at AS biomarker_created_at,
                    uf.original_filename,
                    uf.created_at AS file_created_at
                FROM document_biomarkers db
                JOIN uploaded_files uf ON db.document_id = uf.id
                ORDER BY db.document_id, db.name
            """)

            if not rows:
                print("No records in document_biomarkers. Nothing to migrate.")
                return

            print(f"Found {len(rows)} records in document_biomarkers")

            # Group by document_id
            docs: dict[str, list[dict]] = defaultdict(list)
            for row in rows:
                docs[str(row["document_id"])].append(dict(row))

            print(f"Found {len(docs)} unique documents (uploaded_files)")

            # Stats
            total = 0
            matched = 0
            skipped_existing = 0
            unmatched_names: dict[str, int] = defaultdict(int)
            skipped_non_numeric = 0

            async with conn.transaction():
                await conn.execute("SET LOCAL row_security = off")

                for doc_id, biomarkers in docs.items():
                    if doc_id in existing_file_ids:
                        skipped_existing += len(biomarkers)
                        continue

                    first = biomarkers[0]
                    domain_id = first["domain_id"]
                    file_created = first["file_created_at"]
                    report_date = file_created.date()
                    source_name = first["original_filename"]

                    lab_report_id = await conn.fetchval("""
                        INSERT INTO lab_report
                            (domain_id, source_type, source_name,
                             report_date, uploaded_at, file_id)
                        VALUES ($1, 'pdf_upload', $2, $3, $4, $5)
                        RETURNING id
                    """, domain_id, source_name, report_date,
                        file_created, first["document_id"])

                    for bm in biomarkers:
                        total += 1
                        name = bm["name"]

                        numeric_val = parse_numeric(bm["value"])
                        if numeric_val is None:
                            skipped_non_numeric += 1
                            print(
                                f"  SKIP (non-numeric): {name} = "
                                f"{bm['value']!r}"
                            )
                            continue

                        def_id = match_biomarker(name, alias_index)
                        if def_id is None:
                            unmatched_names[name] += 1
                            continue

                        matched += 1
                        effective_date = bm["biomarker_created_at"].date()

                        await conn.execute("""
                            INSERT INTO biomarker_observation
                                (domain_id, biomarker_def_id, lab_report_id,
                                 value, effective_date)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT
                                (domain_id, biomarker_def_id,
                                 effective_date, lab_report_id)
                            DO UPDATE SET value = EXCLUDED.value
                        """, domain_id, def_id, lab_report_id,
                            numeric_val, effective_date)

            # Refresh materialized view
            await conn.execute(
                "REFRESH MATERIALIZED VIEW current_health_profile"
            )
            print("\nRefreshed materialized view: current_health_profile")

        finally:
            await enable_rls(conn)
            print("Re-enabled RLS on all tables")

        # Summary
        print("\n" + "=" * 60)
        print("MIGRATION SUMMARY")
        print("=" * 60)
        print(f"Total new biomarker records: {total}")
        print(f"Matched & migrated:          {matched}")
        print(f"Skipped (non-numeric):       {skipped_non_numeric}")
        print(f"Unmatched (no definition):   {sum(unmatched_names.values())}")
        print(f"Skipped (already migrated):  {skipped_existing}")
        print()

        if unmatched_names:
            print(
                "Unmatched biomarker names "
                "(add to biomarker_definition later):"
            )
            for name, count in sorted(unmatched_names.items()):
                print(f"  - {name} (x{count})")

        # Verify counts
        obs_count = await conn.fetchval(
            "SELECT count(*) FROM biomarker_observation"
        )
        report_count = await conn.fetchval("SELECT count(*) FROM lab_report")
        print(f"\nVerification:")
        print(f"  lab_report count:           {report_count}")
        print(f"  biomarker_observation count: {obs_count}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
