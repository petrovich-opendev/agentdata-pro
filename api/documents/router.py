"""Document upload and management API endpoints."""

import asyncio
import os

import asyncpg
import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from api.config import Settings
from api.db.pool import get_connection
from api.deps import get_llm_client, get_pool
from api.documents.models import (
    BiomarkerResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
)
from api.documents.parser import process_document
from api.documents.service import (
    create_document,
    delete_document,
    get_document,
    get_document_biomarkers,
    get_upload_path,
    list_documents,
)
from api.llm.client import LLMClient
from api.middleware.auth import get_current_user

logger = structlog.get_logger()

router = APIRouter(prefix="/api/documents", tags=["documents"])

_settings = Settings()

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "image/jpeg": "image",
    "image/png": "image",
}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
    llm_client: LLMClient = Depends(get_llm_client),
) -> DocumentResponse:
    """Upload a document (PDF or image) for parsing."""
    domain_id = user["domain_id"]

    # Validate file type
    mime = file.content_type or ""
    if mime not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {mime}. Allowed: PDF, JPEG, PNG",
        )

    # Read file content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 20 MB)")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    file_type = ALLOWED_TYPES[mime]
    original_name = file.filename or "document"
    stored_name, file_path = get_upload_path(domain_id, original_name)

    # Write file to disk
    with open(file_path, "wb") as f:
        f.write(content)

    await logger.ainfo(
        "document_uploaded",
        filename=original_name,
        size=len(content),
        type=file_type,
        domain_id=domain_id,
    )

    # Save to DB
    async with get_connection(pool, domain_id) as conn:
        doc = await create_document(
            conn=conn,
            domain_id=domain_id,
            session_id=None,
            original_filename=original_name,
            stored_filename=stored_name,
            file_type=file_type,
            mime_type=mime,
            file_size=len(content),
            storage_path=file_path,
        )

    # Start async processing (parse PDF -> extract biomarkers)
    if file_type == "pdf":
        asyncio.create_task(
            process_document(
                file_path=file_path,
                doc_id=str(doc["id"]),
                domain_id=domain_id,
                llm_client=llm_client,
                model=_settings.LITELLM_MODEL,
                pool=pool,
            )
        )

    return DocumentResponse(**doc)


@router.get("", response_model=DocumentListResponse)
async def list_user_documents(
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> DocumentListResponse:
    """List all documents for the current user."""
    domain_id = user["domain_id"]
    async with get_connection(pool, domain_id) as conn:
        docs = await list_documents(conn, domain_id)
    return DocumentListResponse(
        documents=[DocumentResponse(**d) for d in docs]
    )


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document_detail(
    document_id: str,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> DocumentDetailResponse:
    """Get document details including parsed biomarkers."""
    domain_id = user["domain_id"]
    from uuid import UUID

    doc_uuid = UUID(document_id)
    async with get_connection(pool, domain_id) as conn:
        doc = await get_document(conn, doc_uuid, domain_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        biomarkers = await get_document_biomarkers(conn, doc_uuid)

    return DocumentDetailResponse(
        id=doc["id"],
        original_filename=doc["original_filename"],
        file_type=doc["file_type"],
        mime_type=doc["mime_type"],
        file_size_bytes=doc["file_size_bytes"],
        processing_status=doc["processing_status"],
        created_at=doc["created_at"],
        extracted_text=doc["extracted_text"],
        biomarkers=[BiomarkerResponse(**b) for b in biomarkers],
    )


@router.delete("/{document_id}")
async def delete_user_document(
    document_id: str,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """Delete a document and its file."""
    domain_id = user["domain_id"]
    from uuid import UUID

    doc_uuid = UUID(document_id)
    async with get_connection(pool, domain_id) as conn:
        storage_path = await delete_document(conn, doc_uuid, domain_id)

    if storage_path is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove file from disk
    try:
        if os.path.exists(storage_path):
            os.remove(storage_path)
    except OSError:
        await logger.awarning("file_delete_failed", path=storage_path)

    return {"ok": True}


@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Download the original uploaded file."""
    domain_id = user["domain_id"]
    from uuid import UUID

    doc_uuid = UUID(document_id)
    async with get_connection(pool, domain_id) as conn:
        doc = await get_document(conn, doc_uuid, domain_id)

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not os.path.exists(doc["storage_path"]):
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=doc["storage_path"],
        filename=doc["original_filename"],
        media_type=doc["mime_type"],
    )
