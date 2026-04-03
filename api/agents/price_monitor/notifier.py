"""Price alert notifications — in-app and Telegram."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg
import httpx
import structlog

logger = structlog.get_logger()

_TELEGRAM_API = "https://api.telegram.org"


async def _get_telegram_chat_id(pool: asyncpg.Pool, domain_id: UUID) -> int | None:
    """Look up the Telegram chat_id for a domain owner.

    Query: users.telegram_chat_id via domains.owner_id.
    """
    async with pool.acquire() as conn:
        chat_id = await conn.fetchval(
            "SELECT telegram_chat_id FROM users WHERE id = (SELECT owner_id FROM domains WHERE id = $1)",
            domain_id,
        )
        if chat_id is not None:
            return int(chat_id)
    return None


def _format_alert_message(item: dict[str, Any]) -> str:
    """Format a single price alert item into a Telegram message."""
    product_name = item.get("product_name", "")
    best_price = item.get("best_price", 0)
    target_price = item.get("target_price", 0)
    best_source = item.get("best_source", "")
    best_url = item.get("best_url", "")

    msg = (
        f"\U0001f50d Мониторинг цен\n\n"
        f"{product_name} — \u20bd{best_price:,.0f} (цель: \u20bd{target_price:,.0f})\n"
        f"Аптека: {best_source}\n\n"
        f"[Открыть \u2192]({best_url})"
    )
    return msg


async def send_price_alert(
    pool: asyncpg.Pool,
    domain_id: str,
    items: list[dict[str, Any]],
    bot_token: str,
) -> None:
    """Create agent_notification records and send Telegram message for threshold alerts.

    Creates both in_app and telegram notification records.
    Sends Telegram message if chat_id is available.
    """
    if not items:
        return

    uid = UUID(domain_id)

    # Look up chat_id once
    chat_id = await _get_telegram_chat_id(pool, uid)

    for item in items:
        message_text = _format_alert_message(item)
        content = {
            "type": "price_alert",
            "item": item,
            "message": message_text,
        }
        content_json = json.dumps(content, ensure_ascii=False)

        async with pool.acquire() as conn:
            # Create in_app notification
            await conn.execute(
                """
                INSERT INTO agent_notification (domain_id, agent_code, channel, content)
                VALUES ($1, $2, $3, $4::jsonb)
                """,
                uid,
                "price_monitor",
                "in_app",
                content_json,
            )

            # Create telegram notification record
            await conn.execute(
                """
                INSERT INTO agent_notification (domain_id, agent_code, channel, content)
                VALUES ($1, $2, $3, $4::jsonb)
                """,
                uid,
                "price_monitor",
                "telegram",
                content_json,
            )

        # Send Telegram message
        if chat_id is None:
            await logger.awarning(
                "telegram_chat_id_not_found",
                domain_id=domain_id,
            )
            continue

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{_TELEGRAM_API}/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": message_text,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                    },
                )
                if resp.status_code != 200:
                    await logger.awarning(
                        "telegram_send_failed",
                        domain_id=domain_id,
                        status=resp.status_code,
                        body=resp.text,
                    )
                else:
                    await logger.ainfo(
                        "telegram_alert_sent",
                        domain_id=domain_id,
                        product=item.get("product_name"),
                    )
        except Exception as exc:
            await logger.awarning(
                "telegram_send_error",
                domain_id=domain_id,
                error=str(exc),
            )
