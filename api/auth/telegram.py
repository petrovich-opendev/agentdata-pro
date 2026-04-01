"""Telegram Bot API integration for sending auth codes and resolving usernames."""

import asyncpg
import httpx
import structlog

logger = structlog.get_logger()


class TelegramSendError(Exception):
    """Raised when Telegram API fails to send a message."""


class UsernameNotFoundError(Exception):
    """Raised when username cannot be resolved to a chat_id."""


async def resolve_username_to_chat_id(
    pool: asyncpg.Pool, username: str, bot_token: str | None = None
) -> int:
    """Resolve a Telegram username to chat_id.

    First checks the users table (returning users).
    Then checks Telegram Bot API getUpdates (new users who sent /start).
    Users must send /start to the bot before they can register.
    """
    normalized = username.strip().lstrip("@").lower()

    # Check if user already exists in DB
    async with pool.acquire() as conn:
        await conn.execute("RESET ROLE")
        try:
            row = await conn.fetchrow(
                "SELECT telegram_chat_id FROM users "
                "WHERE lower(telegram_username) = $1",
                normalized,
            )
        finally:
            await conn.execute("SET ROLE biocoach_app")

    if row is not None:
        return row["telegram_chat_id"]

    # New user — look up via Telegram Bot API getUpdates
    if bot_token:
        chat_id = await _lookup_chat_id_from_updates(bot_token, normalized)
        if chat_id is not None:
            return chat_id

    await logger.awarn("username_not_resolved", username=normalized)
    raise UsernameNotFoundError(
        f"Username @{normalized} not found. "
        "Please send /start to @Agentdatapro_bot first."
    )


async def _lookup_chat_id_from_updates(bot_token: str, username: str) -> int | None:
    """Search recent bot updates for a chat_id matching the username."""
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params={"limit": 100})

    if resp.status_code != 200:
        return None

    data = resp.json()
    if not data.get("ok"):
        return None

    for update in data.get("result", []):
        msg = update.get("message", {})
        chat = msg.get("chat", {})
        from_user = msg.get("from", {})
        tg_username = (from_user.get("username") or chat.get("username") or "").lower()
        if tg_username == username:
            return chat.get("id")

    return None


async def send_code_message(bot_token: str, chat_id: int, code: str) -> None:
    """Send a 6-digit login code to the user via Telegram bot DM."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": f"Your BioCoach login code: {code}\nExpires in 5 minutes.",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json=payload)

    if resp.status_code != 200:
        await logger.aerror(
            "telegram_send_failed",
            chat_id=chat_id,
            status_code=resp.status_code,
        )
        raise TelegramSendError(f"Telegram API returned {resp.status_code}")
