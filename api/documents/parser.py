"""PDF parsing and biomarker extraction via LLM."""

import json
import re
import asyncio

import pdfplumber
import structlog

from api.llm.client import LLMClient

logger = structlog.get_logger()

EXTRACTION_PROMPT = """You are a medical lab results parser. Extract ALL biomarkers from the lab report.

Return a JSON array. Each element:
{"name":"...","value":"...","unit":"...","ref_range_min":null,"ref_range_max":null,"ref_range_text":"...","status":"normal|low|high|critical|unknown","category":"..."}

Rules:
- Return ONLY a valid JSON array, nothing else
- No markdown, no explanation, no thinking
- Keep original biomarker names (Russian/English as they appear)
- Compare value to reference range: normal/low/high/critical
- If no biomarkers found, return: []"""

RETRY_PROMPT = """Extract biomarkers from this lab report as a JSON array.
Each object: {"name":"...", "value":"...", "unit":"...", "ref_range_text":"...", "status":"normal|low|high|critical|unknown", "category":"..."}
Return ONLY the JSON array. No text before or after."""


def extract_text_from_pdf(file_path: str) -> tuple[str, int]:
    """Extract text from PDF using pdfplumber. Returns (text, page_count)."""
    text_parts = []
    page_count = 0
    with pdfplumber.open(file_path) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row:
                        cells = [str(c).strip() for c in row if c]
                        if cells:
                            text_parts.append(" | ".join(cells))

    return "\n\n".join(text_parts), page_count


def _repair_truncated_json(raw: str) -> str | None:
    """Try to repair a truncated JSON array by finding the last complete object."""
    raw = raw.strip()
    if not raw.startswith("["):
        return None

    last_brace = raw.rfind("}")
    if last_brace == -1:
        return None

    candidate = raw[:last_brace + 1].rstrip().rstrip(",") + "]"
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, list):
            return candidate
    except json.JSONDecodeError:
        pass

    return None


def _clean_llm_response(response: str) -> str:
    """Strip markdown, thinking tags, and find JSON array in LLM response."""
    response = response.strip()

    if response.startswith("```"):
        lines = response.split("\n")
        response = "\n".join(lines[1:-1]).strip()

    if "<think>" in response:
        response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()

    bracket_start = response.find("[")
    bracket_end = response.rfind("]")
    if bracket_start != -1 and bracket_end != -1:
        return response[bracket_start:bracket_end + 1]

    if bracket_start != -1:
        return response[bracket_start:]

    return response


async def extract_biomarkers_via_llm(
    text: str,
    llm_client: LLMClient,
    model: str,
) -> list[dict]:
    """Send extracted text to LLM for structured biomarker extraction."""
    if not text.strip():
        return []

    max_chars = 12000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... truncated ...]"

    messages = [
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": f"Lab report text:\n\n{text}"},
    ]

    for attempt in range(2):
        response = ""
        try:
            response = await llm_client.complete(messages, model)
            cleaned = _clean_llm_response(response)

            try:
                biomarkers = json.loads(cleaned)
                if isinstance(biomarkers, list):
                    await logger.ainfo("biomarkers_extracted", count=len(biomarkers), attempt=attempt)
                    return biomarkers
            except json.JSONDecodeError:
                pass

            repaired = _repair_truncated_json(cleaned)
            if repaired:
                biomarkers = json.loads(repaired)
                await logger.ainfo(
                    "biomarkers_extracted_after_repair",
                    count=len(biomarkers),
                    attempt=attempt,
                )
                return biomarkers

            await logger.awarning(
                "biomarker_extraction_failed",
                error="JSON parse failed",
                response_preview=response[:300] if response else "",
                attempt=attempt,
            )

        except Exception as exc:
            await logger.awarning(
                "biomarker_extraction_failed",
                error=str(exc),
                response_preview=response[:300] if response else "",
                attempt=attempt,
            )

        if attempt == 0:
            messages = [
                {"role": "system", "content": RETRY_PROMPT},
                {"role": "user", "content": text},
            ]
            await logger.ainfo("biomarker_extraction_retrying")

    return []


_RU_TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
    'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
    'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def _generate_type_code(name: str) -> str:
    """Generate a snake_case code from a biomarker name for auto-created observation_type."""
    result = []
    for ch in name.lower():
        if ch in _RU_TRANSLIT:
            result.append(_RU_TRANSLIT[ch])
        elif ch.isascii() and ch.isalnum():
            result.append(ch)
        else:
            result.append('_')
    code = re.sub(r'_+', '_', ''.join(result)).strip('_')
    return f"auto_{code[:50]}"


async def normalize_and_store_biomarkers(
    pool,
    domain_id: str,
    doc_uuid,
    biomarkers: list[dict],
    report_date,
) -> int:
    """Normalize LLM-extracted biomarkers into observation table.

    For each biomarker:
    1. Match against observation_type by code, name_ru, name_en, or aliases (case-insensitive).
    2. If no match found, auto-create observation_type with status='pending_review', category='LAB_UNKNOWN'.
    3. Parse numeric value and insert into observation.
    4. Trigger fn_observation_upsert_profile handles current_profile update via observation_type FK.

    Returns count of inserted observations.
    """
    from datetime import date
    from uuid import UUID
    from api.db.pool import get_connection

    domain_uuid = UUID(domain_id) if isinstance(domain_id, str) else domain_id
    effective_date = report_date.date() if hasattr(report_date, "date") else (report_date or date.today())

    inserted = 0

    try:
        async with get_connection(pool, domain_id) as conn:
            for bm in biomarkers:
                bm_name = bm.get("name", "").strip()
                if not bm_name:
                    continue

                # Parse numeric value
                raw_value = bm.get("value", "")
                numeric_value = None
                try:
                    cleaned = str(raw_value).replace(",", ".").replace("<", "").replace(">", "").strip()
                    numeric_value = float(cleaned)
                except (ValueError, TypeError):
                    pass

                if numeric_value is None:
                    await logger.awarning(
                        "biomarker_value_not_numeric",
                        name=bm_name,
                        value=raw_value,
                    )
                    continue

                # Match against observation_type: code, name_ru, name_en, aliases
                type_code = await conn.fetchval(
                    """
                    SELECT code FROM observation_type
                    WHERE lower(code) = lower($1)
                       OR lower(name_ru) = lower($1)
                       OR lower(name_en) = lower($1)
                       OR EXISTS (
                           SELECT 1 FROM unnest(aliases) AS a
                           WHERE lower(a) = lower($1)
                       )
                    LIMIT 1
                    """,
                    bm_name,
                )

                # Auto-create unknown observation_type
                if type_code is None:
                    auto_code = _generate_type_code(bm_name)
                    unit = bm.get("unit", "") or ""
                    try:
                        type_code = await conn.fetchval(
                            """
                            INSERT INTO observation_type (code, name_ru, name_en, aliases, unit, category, status)
                            VALUES ($1, $2, $2, ARRAY[$2], $3, 'LAB_UNKNOWN', 'pending_review')
                            ON CONFLICT (code) DO UPDATE SET code = observation_type.code
                            RETURNING code
                            """,
                            auto_code,
                            bm_name,
                            unit,
                        )
                        await logger.ainfo(
                            "observation_type_auto_created",
                            code=type_code,
                            name=bm_name,
                        )
                    except Exception as exc:
                        await logger.awarning(
                            "observation_type_auto_create_failed",
                            name=bm_name,
                            error=str(exc),
                        )
                        continue

                # Insert observation
                try:
                    await conn.execute(
                        """
                        INSERT INTO observation
                            (domain_id, type_code, value_numeric, effective_date,
                             source_type, source_document_id)
                        VALUES ($1, $2, $3, $4, 'lab_pdf', $5)
                        ON CONFLICT (domain_id, type_code, effective_date, source_document_id)
                        DO NOTHING
                        """,
                        domain_uuid,
                        type_code,
                        numeric_value,
                        effective_date,
                        doc_uuid,
                    )
                    inserted += 1
                except Exception as exc:
                    await logger.awarning(
                        "observation_insert_failed",
                        name=bm_name,
                        type_code=type_code,
                        error=str(exc),
                    )

        await logger.ainfo(
            "normalize_biomarkers_done",
            domain_id=domain_id,
            inserted=inserted,
            total=len(biomarkers),
        )

    except Exception as exc:
        await logger.aexception(
            "normalize_and_store_biomarkers_failed",
            domain_id=domain_id,
            error=str(exc),
        )

    return inserted


async def process_document(
    file_path: str,
    doc_id: str,
    domain_id: str,
    llm_client: LLMClient,
    model: str,
    pool,
) -> None:
    """Full pipeline: extract text -> extract biomarkers -> save to DB."""
    from api.db.pool import get_connection
    from api.documents.service import save_biomarkers, update_document_status
    from uuid import UUID

    doc_uuid = UUID(doc_id)

    try:
        async with get_connection(pool, domain_id) as conn:
            await update_document_status(conn, doc_uuid, "parsing")

        text, page_count = await asyncio.to_thread(extract_text_from_pdf, file_path)

        if not text.strip():
            async with get_connection(pool, domain_id) as conn:
                await update_document_status(
                    conn, doc_uuid, "error",
                    error_message="No text could be extracted from PDF",
                )
            return

        async with get_connection(pool, domain_id) as conn:
            await update_document_status(
                conn, doc_uuid, "extracting",
                extracted_text=text,
            )

        # Extract biomarkers — chunk if text is long
        chunk_size = 6000
        all_biomarkers = []

        if len(text) > chunk_size:
            pages = text.split("\n\n")
            chunks = []
            current_chunk = ""
            for page in pages:
                if len(current_chunk) + len(page) > chunk_size and current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = page
                else:
                    current_chunk = current_chunk + "\n\n" + page if current_chunk else page
            if current_chunk:
                chunks.append(current_chunk)

            await logger.ainfo("document_chunked", chunks=len(chunks), total_chars=len(text))

            for i, chunk in enumerate(chunks):
                biomarkers = await extract_biomarkers_via_llm(chunk, llm_client, model)
                if biomarkers:
                    all_biomarkers.extend(biomarkers)
                    await logger.ainfo("chunk_processed", chunk=i, found=len(biomarkers))
        else:
            all_biomarkers = await extract_biomarkers_via_llm(text, llm_client, model)

        # Deduplicate by name+value
        seen = set()
        unique_biomarkers = []
        for bm in all_biomarkers:
            key = (bm.get("name", ""), bm.get("value", ""))
            if key not in seen:
                seen.add(key)
                unique_biomarkers.append(bm)

        async with get_connection(pool, domain_id) as conn:
            count = 0
            if unique_biomarkers:
                count = await save_biomarkers(conn, doc_uuid, domain_id, unique_biomarkers)
            await update_document_status(
                conn, doc_uuid, "done",
                extracted_text=text,
                extracted_data={"page_count": page_count, "biomarker_count": count},
            )

        # Normalize biomarkers into new schema
        if unique_biomarkers:
            async with get_connection(pool, domain_id) as conn:
                file_created_at = await conn.fetchval(
                    "SELECT created_at FROM uploaded_files WHERE id = $1",
                    doc_uuid,
                )
            await normalize_and_store_biomarkers(
                pool, domain_id, doc_uuid, unique_biomarkers, file_created_at,
            )

        await logger.ainfo(
            "document_processed",
            doc_id=doc_id,
            pages=page_count,
            biomarkers=count,
        )

    except Exception as exc:
        await logger.aexception("document_processing_failed", doc_id=doc_id)
        try:
            async with get_connection(pool, domain_id) as conn:
                await update_document_status(
                    conn, doc_uuid, "error",
                    error_message=str(exc)[:500],
                )
        except Exception:
            await logger.aexception("status_update_failed_after_error", doc_id=doc_id)
