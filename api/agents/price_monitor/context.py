"""LLM context injection for price monitor agent."""

from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog

logger = structlog.get_logger()


def _format_time_ago(dt) -> str:
    """Format a datetime as a human-readable 'time ago' string in Russian."""
    from datetime import datetime, timezone

    if dt is None:
        return "нет данных"

    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        from datetime import timezone as tz

        dt = dt.replace(tzinfo=tz.utc)

    delta = now - dt
    total_seconds = int(delta.total_seconds())

    if total_seconds < 60:
        return "только что"
    if total_seconds < 3600:
        minutes = total_seconds // 60
        return f"{minutes}мин назад"
    if total_seconds < 86400:
        hours = total_seconds // 3600
        return f"{hours}ч назад"
    days = total_seconds // 86400
    return f"{days}д назад"


async def get_price_context(
    pool: asyncpg.Pool,
    domain_id: str,
    language: str,
) -> str | None:
    """Build LLM context text from user's price watchlist.

    Returns None if price_monitor is inactive or watchlist is empty.
    """
    uid = UUID(domain_id)

    async with pool.acquire() as conn:
        # Check if agent is active
        active = await conn.fetchval(
            "SELECT is_active FROM agent_config WHERE domain_id = $1 AND agent_code = $2",
            uid,
            "price_monitor",
        )
        if not active:
            return None

        # Fetch watchlist items
        rows = await conn.fetch(
            """
            SELECT product_name, best_price, best_source, last_checked_at, target_price
            FROM price_watchlist
            WHERE domain_id = $1
            ORDER BY product_name
            """,
            uid,
        )

    if not rows:
        return None

    if language == "ru":
        header = "Отслеживаемые цены:"
        no_price = "цена не найдена"
        target_label = "цель"
    else:
        header = "Tracked prices:"
        no_price = "no price found"
        target_label = "target"

    lines = [header]
    for row in rows:
        name = row["product_name"]
        best = row["best_price"]
        source = row["best_source"]
        checked = row["last_checked_at"]
        target = row["target_price"]

        if best is not None:
            time_ago = _format_time_ago(checked)
            line = f"— {name} — лучшая ₽{best:,.0f}"
            if source:
                line += f" ({source}"
                if checked:
                    line += f", обновлено {time_ago}"
                line += ")"
            if target is not None:
                line += f" [{target_label} ₽{target:,.0f}]"
        else:
            line = f"— {name} — {no_price}"

        lines.append(line)

    return "\n".join(lines)
