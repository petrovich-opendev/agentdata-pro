"""Pydantic schemas for document endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: UUID
    original_filename: str
    file_type: str
    mime_type: str
    file_size_bytes: int
    processing_status: str
    created_at: datetime


class DocumentDetailResponse(DocumentResponse):
    extracted_text: str | None = None
    biomarkers: list["BiomarkerResponse"] = []


class BiomarkerResponse(BaseModel):
    id: UUID
    name: str
    value: str
    unit: str | None = None
    ref_range_min: float | None = None
    ref_range_max: float | None = None
    ref_range_text: str | None = None
    status: str | None = None
    category: str | None = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
