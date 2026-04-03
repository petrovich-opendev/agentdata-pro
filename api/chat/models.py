"""Pydantic schemas for chat endpoints."""

from datetime import datetime
from uuid import UUID

from typing import Annotated

from pydantic import BaseModel, StringConstraints


class SendMessageInput(BaseModel):
    content: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)
    ]
    session_id: UUID | None = None


class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]


class SessionResponse(BaseModel):
    id: UUID
    title: str | None = None
    created_at: datetime


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]
    authenticated: bool = True


class RenameSessionInput(BaseModel):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


# --- Phase 2: Folders & Search ---

from typing import Literal


class CreateFolderInput(BaseModel):
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    emoji: str | None = None
    color: str | None = None


class FolderResponse(BaseModel):
    id: UUID
    name: str
    emoji: str | None = None
    color: str | None = None
    sort_order: int
    created_at: datetime


class UpdateFolderInput(BaseModel):
    name: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ] = None
    emoji: str | None = None
    color: str | None = None


class ReorderFoldersInput(BaseModel):
    folder_ids: list[UUID]


class MoveChatInput(BaseModel):
    folder_id: UUID | None = None


class SearchQuery(BaseModel):
    q: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    mode: Literal["title", "content"] = "title"


class SearchResultItem(BaseModel):
    session_id: UUID
    session_title: str | None = None
    snippet: str | None = None


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    query: str
    mode: str
