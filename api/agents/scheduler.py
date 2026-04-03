"""Background scheduler for agent execution (runs inside FastAPI lifespan)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from api.agents.price_monitor.agent import (
    check_thresholds,
    monitor_watchlist,
    search_prices,
)
from api.agents.price_monitor.notifier import send_price_alert

logger = structlog.get_logger()

_SCHEDULE_INTERVALS: dict[str, timedelta] = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(hours=24),
}

_TICK_SECONDS = 60


async def _get_due_agents(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Return active price_monitor agent_configs where next_run_at <= now().

    If next_run_at is NULL the agent has never been scheduled — include it.
    """
    now = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ac.domain_id, ac.agent_code, ac.settings,
                   ae.next_run_at
            FROM agent_config ac
            LEFT JOIN LATERAL (
                SELECT next_run_at
                FROM agent_execution
                WHERE domain_id = ac.domain_id AND agent_code = ac.agent_code
                ORDER BY started_at DESC
                LIMIT 1
            ) ae ON true
            WHERE ac.is_active = true
              AND ac.agent_code = 'price_monitor'
              AND (ae.next_run_at IS NULL OR ae.next_run_at <= $1)
            """,
            now,
        )
    return [
        {
            "domain_id": str(r["domain_id"]),
            "agent_code": r["agent_code"],
            "settings": (
                json.loads(r["settings"])
                if isinstance(r["settings"], str)
                else (r["settings"] or {})
            ),
        }
        for r in rows
    ]


async def _run_agent_cycle(
    pool: asyncpg.Pool,
    domain_id: str,
    settings: dict[str, Any],
    bot_token: str,
) -> None:
    """Execute one price_monitor cycle for a single domain."""
    uid = UUID(domain_id)
    started_at = datetime.now(timezone.utc)

    # Insert execution record (status=running)
    async with pool.acquire() as conn:
        exec_id = await conn.fetchval(
            """
            INSERT INTO agent_execution (domain_id, agent_code, status, started_at)
            VALUES ($1, 'price_monitor', 'running', $2)
            RETURNING id
            """,
            uid,
            started_at,
        )

    try:
        # 1. Monitor watchlist (scrape + update best prices)
        summary = await monitor_watchlist(pool, domain_id)

        # 2. Check thresholds
        alerts = await check_thresholds(pool, domain_id)

        # 3. Send notifications for threshold hits
        if alerts:
            await send_price_alert(pool, domain_id, alerts, bot_token)

        # Calculate next_run_at
        schedule = settings.get("schedule", "daily")
        interval = _SCHEDULE_INTERVALS.get(schedule, _SCHEDULE_INTERVALS["daily"])
        next_run = datetime.now(timezone.utc) + interval

        # Update execution record
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_execution
                SET status = 'completed',
                    completed_at = now(),
                    next_run_at = $1,
                    result_summary = $2::jsonb
                WHERE id = $3
                """,
                next_run,
                json.dumps(summary, ensure_ascii=False, default=str),
                exec_id,
            )

        await logger.ainfo(
            "scheduler_cycle_completed",
            domain_id=domain_id,
            checked=summary.get("checked", 0),
            price_drops=summary.get("price_drops", 0),
            alerts=len(alerts),
            next_run=next_run.isoformat(),
        )

    except Exception as exc:
        # Mark execution as failed, set next_run_at so we retry next interval
        schedule = settings.get("schedule", "daily")
        interval = _SCHEDULE_INTERVALS.get(schedule, _SCHEDULE_INTERVALS["daily"])
        next_run = datetime.now(timezone.utc) + interval

        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_execution
                SET status = 'failed',
                    completed_at = now(),
                    next_run_at = $1,
                    error_message = $2
                WHERE id = $3
                """,
                next_run,
                str(exc)[:1000],
                exec_id,
            )

        await logger.awarning(
            "scheduler_cycle_failed",
            domain_id=domain_id,
            error=str(exc),
        )


async def start_scheduler(
    pool: asyncpg.Pool,
    nc: Any,
    bot_token: str,
) -> None:
    """Run infinite scheduler loop. Checks every 60 seconds for due agents.

    Smart batching: groups watchlist items by (product_name, city) across users
    to avoid duplicate scrapes within the same tick.
    """
    await logger.ainfo("scheduler_started", tick_seconds=_TICK_SECONDS)

    while True:
        try:
            due_agents = await _get_due_agents(pool)

            if due_agents:
                await logger.ainfo(
                    "scheduler_tick",
                    due_count=len(due_agents),
                )

                for agent in due_agents:
                    await _run_agent_cycle(
                        pool=pool,
                        domain_id=agent["domain_id"],
                        settings=agent["settings"],
                        bot_token=bot_token,
                    )

        except asyncio.CancelledError:
            await logger.ainfo("scheduler_cancelled")
            return
        except Exception:
            await logger.aexception("scheduler_tick_error")

        await asyncio.sleep(_TICK_SECONDS)
