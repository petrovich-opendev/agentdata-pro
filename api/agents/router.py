"""Agent management API endpoints."""

from __future__ import annotations

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException

from api.agents.models import (
    AgentConfigInput,
    AgentInfo,
    NotificationResponse,
    SearchRequest,
    SearchResult,
    WatchlistItem,
    WatchlistItemResponse,
)
from api.agents.registry import (
    AGENT_CATALOG,
    activate_agent,
    deactivate_agent,
    get_agent_config,
    get_available_agents,
    save_agent_config,
)
import uuid as _uuid

from api.db.pool import get_connection
from api.deps import get_pool
from api.agents.price_monitor.agent import search_prices
from api.middleware.auth import get_current_user

logger = structlog.get_logger()

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/", response_model=list[AgentInfo])
async def list_agents(
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[AgentInfo]:
    """Return catalog of available agents."""
    return await get_available_agents(pool, user["domain_id"])


@router.get("/{code}/config", response_model=AgentConfigInput)
async def get_config(
    code: str,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> AgentConfigInput:
    """Return current configuration for an agent."""
    try:
        return await get_agent_config(pool, user["domain_id"], code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/{code}/config")
async def update_config(
    code: str,
    body: AgentConfigInput,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """Update agent configuration."""
    try:
        await save_agent_config(pool, user["domain_id"], code, body.settings)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True}


@router.post("/{code}/activate")
async def activate(
    code: str,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """Activate an agent for the current domain."""
    try:
        await activate_agent(pool, user["domain_id"], code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True}


@router.post("/{code}/deactivate")
async def deactivate(
    code: str,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """Deactivate an agent for the current domain."""
    try:
        await deactivate_agent(pool, user["domain_id"], code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True}


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[NotificationResponse]:
    """Return unread and recent notifications for the current domain."""
    domain_id = _uuid.UUID(user["domain_id"])
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, content, is_read, created_at FROM agent_notification "
            "WHERE domain_id = $1 ORDER BY created_at DESC LIMIT 50",
            domain_id,
        )
    return [
        NotificationResponse(
            id=r["id"], content=r["content"], is_read=r["is_read"], created_at=r["created_at"]
        )
        for r in rows
    ]


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """Mark a notification as read."""
    domain_id = _uuid.UUID(user["domain_id"])
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE agent_notification SET is_read = true "
            "WHERE id = $1 AND domain_id = $2",
            notification_id,
            domain_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}



# --------------- Price Monitor: Watchlist ---------------


@router.get("/price-monitor/watchlist", response_model=list[WatchlistItemResponse])
async def list_watchlist(
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[WatchlistItemResponse]:
    domain_id = user["domain_id"]
    async with get_connection(pool, domain_id) as conn:
        rows = await conn.fetch(
            "SELECT id, product_name, product_category, target_price, "
            "best_price, best_source, best_url, last_checked_at "
            "FROM price_watchlist WHERE domain_id = $1 ORDER BY created_at DESC",
            _uuid.UUID(domain_id),
        )
    return [
        WatchlistItemResponse(
            id=r["id"],
            product_name=r["product_name"],
            product_category=r["product_category"],
            target_price=float(r["target_price"]) if r["target_price"] else None,
            best_price=float(r["best_price"]) if r["best_price"] else None,
            best_source=r["best_source"],
            best_url=r["best_url"],
            last_checked_at=r["last_checked_at"],
        )
        for r in rows
    ]


@router.post("/price-monitor/watchlist", response_model=WatchlistItemResponse, status_code=201)
async def add_watchlist_item(
    body: WatchlistItem,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> WatchlistItemResponse:
    domain_id = user["domain_id"]
    async with get_connection(pool, domain_id) as conn:
        row = await conn.fetchrow(
            "INSERT INTO price_watchlist (domain_id, product_name, product_category, target_price) "
            "VALUES ($1, $2, $3, $4) "
            "RETURNING id, product_name, product_category, target_price, "
            "best_price, best_source, best_url, last_checked_at",
            _uuid.UUID(domain_id),
            body.product_name,
            body.product_category,
            body.target_price,
        )
    return WatchlistItemResponse(
        id=row["id"],
        product_name=row["product_name"],
        product_category=row["product_category"],
        target_price=float(row["target_price"]) if row["target_price"] else None,
        best_price=float(row["best_price"]) if row["best_price"] else None,
        best_source=row["best_source"],
        best_url=row["best_url"],
        last_checked_at=row["last_checked_at"],
    )


@router.delete("/price-monitor/watchlist/{item_id}")
async def delete_watchlist_item(
    item_id: _uuid.UUID,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    domain_id = user["domain_id"]
    async with get_connection(pool, domain_id) as conn:
        result = await conn.execute(
            "DELETE FROM price_watchlist WHERE id = $1 AND domain_id = $2",
            item_id,
            _uuid.UUID(domain_id),
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    return {"ok": True}


# --------------- Price Monitor: Search ---------------


@router.post("/price-monitor/search", response_model=list[SearchResult])
async def price_search(
    body: SearchRequest,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[SearchResult]:
    results = await search_prices(
        pool=pool,
        query=body.query,
        city=body.city,
        category=body.category,
    )
    return [SearchResult(**r) for r in results]
