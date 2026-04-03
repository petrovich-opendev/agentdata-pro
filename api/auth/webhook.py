"""Telegram Bot webhook handler — stores chat_id on /start."""

import hashlib
import hmac
import structlog
from fastapi import APIRouter, Request, Response

from api.config import Settings
from api.deps import get_pool

logger = structlog.get_logger()

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(request: Request) -> Response:
    """Handle incoming Telegram bot updates.

    Stores chat_id + username when user sends /start.
    """
    try:
        data = await request.json()
    except Exception:
        return Response(status_code=400)

    message = data.get("message") or data.get("edited_message")
    if not message:
        return Response(status_code=200)

    chat = message.get("chat", {})
    from_user = message.get("from", {})
    text = message.get("text", "")

    chat_id = chat.get("id")
    username = (from_user.get("username") or "").lower().strip()
    first_name = from_user.get("first_name", "")

    if not chat_id:
        return Response(status_code=200)

    # Store on any message (not just /start) — user is contactable
    pool = request.app.state.pool
    try:
        await pool.execute(
            """
            INSERT INTO telegram_starts (chat_id, username, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (chat_id) DO UPDATE
            SET username = EXCLUDED.username,
                first_name = EXCLUDED.first_name
            """,
            chat_id,
            username if username else None,
            first_name if first_name else None,
        )
        await logger.ainfo(
            "telegram_start_saved",
            chat_id=chat_id,
            username=username,
        )
    except Exception:
        await logger.aexception("telegram_start_save_failed", chat_id=chat_id)

    # Send welcome if /start
    if text.strip() == "/start":
        settings = Settings()
        if settings.TELEGRAM_BOT_TOKEN:
            import httpx
            url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
            welcome = (
                "Welcome to BioCoach!\n\n"
                "You can now log in at https://agentdata.pro\n"
                "Use your Telegram username to request a login code."
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json={"chat_id": chat_id, "text": welcome})

    return Response(status_code=200)
