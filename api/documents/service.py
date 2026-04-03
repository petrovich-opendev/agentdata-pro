"""Database operations for documents and biomarkers."""

import os
import uuid
from uuid import UUID

import asyncpg
import structlog

logger = structlog.get_logger()

UPLOADS_DIR = os.environ.get("UPLOADS_DIR", "/home/dev/biocoach/uploads")


def get_upload_path(domain_id: str, filename: str) -> tuple[str, str]:
    """Generate a unique stored filename and full path for upload."""
    ext = os.path.splitext(filename)[1].lower() or ".pdf"
    stored = f"{uuid.uuid4().hex}{ext}"
    domain_dir = os.path.join(UPLOADS_DIR, domain_id)
    os.makedirs(domain_dir, exist_ok=True)
    return stored, os.path.join(domain_dir, stored)


async def create_document(
    conn: asyncpg.Connection,
    domain_id: str,
    session_id: UUID | None,
    original_filename: str,
    stored_filename: str,
    file_type: str,
    mime_type: str,
    file_size: int,
    storage_path: str,
) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO uploaded_files
            (domain_id, session_id, original_filename, stored_filename,
             file_type, mime_type, file_size_bytes, storage_path)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id, original_filename, file_type, mime_type, file_size_bytes,
                  processing_status, created_at
        """,
        UUID(domain_id),
        session_id,
        original_filename,
        stored_filename,
        file_type,
        mime_type,
        file_size,
        storage_path,
    )
    return dict(row)


async def list_documents(conn: asyncpg.Connection, domain_id: str) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, original_filename, file_type, mime_type, file_size_bytes,
               processing_status, created_at
        FROM uploaded_files
        WHERE domain_id = $1
        ORDER BY created_at DESC
        """,
        UUID(domain_id),
    )
    return [dict(r) for r in rows]


async def get_document(conn: asyncpg.Connection, doc_id: UUID, domain_id: str) -> dict | None:
    row = await conn.fetchrow(
        """
        SELECT id, original_filename, file_type, mime_type, file_size_bytes,
               processing_status, extracted_text, storage_path, created_at
        FROM uploaded_files
        WHERE id = $1 AND domain_id = $2
        """,
        doc_id,
        UUID(domain_id),
    )
    return dict(row) if row else None


async def get_document_biomarkers(conn: asyncpg.Connection, doc_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, name, value, unit, ref_range_min, ref_range_max,
               ref_range_text, status, category
        FROM document_biomarkers
        WHERE document_id = $1
        ORDER BY category NULLS LAST, name
        """,
        doc_id,
    )
    return [dict(r) for r in rows]


async def update_document_status(
    conn: asyncpg.Connection, doc_id: UUID, status: str,
    extracted_text: str | None = None,
    extracted_data: dict | None = None,
    error_message: str | None = None,
) -> None:
    import json
    if extracted_text is not None:
        await conn.execute(
            """
            UPDATE uploaded_files
            SET processing_status = $1, extracted_text = $2,
                extracted_data = $3
            WHERE id = $4
            """,
            status,
            extracted_text,
            json.dumps(extracted_data) if extracted_data else None,
            doc_id,
        )
    elif error_message is not None:
        await conn.execute(
            """
            UPDATE uploaded_files
            SET processing_status = $1,
                extracted_data = $2
            WHERE id = $3
            """,
            status,
            json.dumps({"error": error_message}),
            doc_id,
        )
    else:
        await conn.execute(
            "UPDATE uploaded_files SET processing_status = $1 WHERE id = $2",
            status,
            doc_id,
        )


async def save_biomarkers(
    conn: asyncpg.Connection,
    doc_id: UUID,
    domain_id: str,
    biomarkers: list[dict],
) -> int:
    """Insert parsed biomarkers. Returns count inserted."""
    count = 0
    for bm in biomarkers:
        await conn.execute(
            """
            INSERT INTO document_biomarkers
                (document_id, domain_id, name, value, unit,
                 ref_range_min, ref_range_max, ref_range_text, status, category)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            doc_id,
            UUID(domain_id),
            bm.get("name", ""),
            bm.get("value", ""),
            bm.get("unit"),
            float(bm["ref_range_min"]) if bm.get("ref_range_min") is not None else None,
            float(bm["ref_range_max"]) if bm.get("ref_range_max") is not None else None,
            bm.get("ref_range_text"),
            bm.get("status", "unknown"),
            bm.get("category"),
        )
        count += 1
    return count


async def delete_document(conn: asyncpg.Connection, doc_id: UUID, domain_id: str) -> str | None:
    """Delete document and return storage_path for file cleanup. Returns None if not found."""
    row = await conn.fetchrow(
        "DELETE FROM uploaded_files WHERE id = $1 AND domain_id = $2 RETURNING storage_path",
        doc_id,
        UUID(domain_id),
    )
    return row["storage_path"] if row else None


async def get_user_biomarkers_summary(conn: asyncpg.Connection, domain_id: str) -> list[dict]:
    """Get latest biomarkers across all documents for a domain (for chat context injection)."""
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (b.name)
            b.name, b.value, b.unit, b.ref_range_text, b.status, b.category,
            f.original_filename, f.created_at AS doc_date
        FROM document_biomarkers b
        JOIN uploaded_files f ON f.id = b.document_id
        WHERE b.domain_id = $1 AND f.processing_status = 'done'
        ORDER BY b.name, f.created_at DESC
        """,
        UUID(domain_id),
    )
    return [dict(r) for r in rows]
