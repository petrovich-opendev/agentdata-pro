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
