"""Pydantic models for the agent framework."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AgentInfo(BaseModel):
    """Agent catalog entry."""

    code: str
    name: str
    description: str
    is_active: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)
    last_run: datetime | None = None
    next_run: datetime | None = None


class AgentConfigInput(BaseModel):
    """Input for updating agent settings (JSONB)."""

    settings: dict[str, Any] = Field(default_factory=dict)


class WatchlistItem(BaseModel):
    """Input for adding an item to the price watchlist."""

    product_name: str
    product_category: str
    target_price: float | None = None


class WatchlistItemResponse(WatchlistItem):
    """Watchlist item with server-side fields."""

    id: UUID
    best_price: float | None = None
    best_source: str | None = None
    best_url: str | None = None
    last_checked_at: datetime | None = None


class SearchRequest(BaseModel):
    """Input for a price search."""

    query: str
    city: str = "Москва"
    category: str | None = None


class SearchResult(BaseModel):
    """Single search result row."""

    product_name: str
    source: str
    price: float
    pharmacy_name: str | None = None
    url: str | None = None
    city: str


class NotificationResponse(BaseModel):
    """Agent notification for the user."""

    id: int
    content: dict[str, Any]
    is_read: bool = False
    created_at: datetime
