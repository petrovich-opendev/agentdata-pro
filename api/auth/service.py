"""Core authentication logic: code generation, JWT, refresh tokens."""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import jwt
import structlog
from fastapi import HTTPException

from api.auth.telegram import (
    TelegramSendError,
    UsernameNotFoundError,
    resolve_username_to_chat_id,
    send_code_message,
)

logger = structlog.get_logger()


def generate_code() -> str:
    """Generate a random 6-digit code."""
    return str(secrets.randbelow(900000) + 100000)


def hash_code(code: str) -> str:
    """SHA-256 hash of a code string."""
    return hashlib.sha256(code.encode()).hexdigest()


def verify_code_hash(code: str, code_hash: str) -> bool:
    """Constant-time comparison of code against stored hash."""
    return hmac.compare_digest(hash_code(code), code_hash)


def create_access_token(
    user_id: str,
    domain_id: str,
    tg_id: int,
    secret: str,
    expire_minutes: int,
) -> str:
    """Create a JWT access token with standard claims."""
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "domain_id": domain_id,
        "tg_id": tg_id,
        "iat": now,
        "exp": now + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str, secret: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid credentials")


def generate_refresh_token() -> str:
    """Generate a cryptographically secure opaque refresh token."""
    return secrets.token_urlsafe(32)


async def request_code(
    pool: asyncpg.Pool, bot_token: str, telegram_username: str
) -> None:
    """Resolve username to chat_id, generate auth code, store hash, send via Telegram."""
    try:
        telegram_chat_id = await resolve_username_to_chat_id(pool, telegram_username, bot_token)
    except UsernameNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=(
                "Username not found. "
                "Please send /start to @Agentdatapro_bot first."
            ),
        )

    code = generate_code()
    code_h = hash_code(code)

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Invalidate existing unused codes for this chat_id
            await conn.execute(
                "UPDATE auth_codes SET used = true "
                "WHERE telegram_chat_id = $1 AND used = false",
                telegram_chat_id,
            )
            # Store new code hash
            await conn.execute(
                "INSERT INTO auth_codes (telegram_chat_id, code_hash, expires_at) "
                "VALUES ($1, $2, now() + interval '5 minutes')",
                telegram_chat_id,
                code_h,
            )

    try:
        await send_code_message(bot_token, telegram_chat_id, code)
    except TelegramSendError:
        await logger.aerror("telegram_send_failed", chat_id=telegram_chat_id)
        raise HTTPException(status_code=502, detail="Failed to send code via Telegram")


async def verify_code(
    bot_token: str,
    pool: asyncpg.Pool,
    telegram_username: str,
    code: str,
    jwt_secret: str,
    access_expire_min: int,
    refresh_expire_days: int,
) -> tuple[str, str]:
    """Verify auth code and issue tokens. Auto-creates user on first login."""
    try:
        telegram_chat_id = await resolve_username_to_chat_id(pool, telegram_username, bot_token)
    except UsernameNotFoundError:
        raise HTTPException(status_code=404, detail="Username not found")

    normalized_username = telegram_username.strip().lstrip("@").lower()

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Find latest unused, non-expired code
            row = await conn.fetchrow(
                "SELECT id, code_hash, attempts FROM auth_codes "
                "WHERE telegram_chat_id = $1 AND used = false "
                "AND expires_at > now() "
                "ORDER BY created_at DESC LIMIT 1",
                telegram_chat_id,
            )
            if row is None:
                raise HTTPException(status_code=401, detail="Invalid or expired code")

            if row["attempts"] >= 5:
                raise HTTPException(status_code=429, detail="Too many attempts")

            # Increment attempts
            await conn.execute(
                "UPDATE auth_codes SET attempts = attempts + 1 WHERE id = $1",
                row["id"],
            )

            # Verify hash
            if not verify_code_hash(code, row["code_hash"]):
                raise HTTPException(status_code=401, detail="Invalid or expired code")

            # Mark code as used
            await conn.execute(
                "UPDATE auth_codes SET used = true WHERE id = $1",
                row["id"],
            )

            # Bypass RLS for user/domain operations
            await conn.execute("RESET ROLE")

            try:
                # Look up or create user
                user = await conn.fetchrow(
                    "SELECT id FROM users WHERE telegram_chat_id = $1",
                    telegram_chat_id,
                )

                if user is None:
                    # Create new user with username
                    user = await conn.fetchrow(
                        "INSERT INTO users (telegram_chat_id, telegram_username) "
                        "VALUES ($1, $2) RETURNING id",
                        telegram_chat_id,
                        normalized_username,
                    )
                    user_id = str(user["id"])

                    # Create personal domain
                    domain_id = str(uuid.uuid4())
                    await conn.execute(
                        "SELECT set_config('app.current_domain', $1, true)",
                        domain_id,
                    )
                    await conn.execute(
                        "INSERT INTO domains (id, owner_id, name) "
                        "VALUES ($1::uuid, $2::uuid, $3)",
                        domain_id,
                        user_id,
                        "personal",
                    )
                else:
                    user_id = str(user["id"])
                    # Update last login and username
                    await conn.execute(
                        "UPDATE users SET last_login_at = now(), "
                        "telegram_username = $2 WHERE id = $1::uuid",
                        user_id,
                        normalized_username,
                    )
                    # Get domain for existing user
                    domain_row = await conn.fetchrow(
                        "SELECT id FROM domains WHERE owner_id = $1::uuid LIMIT 1",
                        user_id,
                    )
                    domain_id = str(domain_row["id"]) if domain_row else str(uuid.uuid4())
            finally:
                # Restore RLS role
                await conn.execute("SET ROLE biocoach_app")

            # Generate tokens
            access_token = create_access_token(
                user_id, domain_id, telegram_chat_id, jwt_secret, access_expire_min
            )
            refresh_token = generate_refresh_token()
            refresh_hash = hash_code(refresh_token)

            await conn.execute(
                "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) "
                "VALUES ($1::uuid, $2, now() + make_interval(days => $3))",
                user_id,
                refresh_hash,
                refresh_expire_days,
            )

    return access_token, refresh_token


async def refresh_tokens(
    pool: asyncpg.Pool,
    refresh_token: str,
    jwt_secret: str,
    access_expire_min: int,
    refresh_expire_days: int,
) -> tuple[str, str]:
    """Validate refresh token, rotate it, and issue new access token."""
    token_hash = hash_code(refresh_token)

    async with pool.acquire() as conn:
        async with conn.transaction():
            # Find valid refresh token
            row = await conn.fetchrow(
                "SELECT id, user_id FROM refresh_tokens "
                "WHERE token_hash = $1 AND expires_at > now()",
                token_hash,
            )
            if row is None:
                raise HTTPException(status_code=401, detail="Invalid credentials")

            # Delete old refresh token (rotation)
            await conn.execute(
                "DELETE FROM refresh_tokens WHERE id = $1",
                row["id"],
            )

            user_id = str(row["user_id"])

            # Get user info (users table has no RLS)
            user = await conn.fetchrow(
                "SELECT telegram_chat_id FROM users WHERE id = $1::uuid",
                user_id,
            )
            if user is None:
                raise HTTPException(status_code=401, detail="Invalid credentials")

            # Bypass RLS to get domain
            await conn.execute("RESET ROLE")
            try:
                domain_row = await conn.fetchrow(
                    "SELECT id FROM domains WHERE owner_id = $1::uuid LIMIT 1",
                    user_id,
                )
            finally:
                await conn.execute("SET ROLE biocoach_app")

            if domain_row is None:
                raise HTTPException(status_code=401, detail="Invalid credentials")

            domain_id = str(domain_row["id"])

            # Generate new tokens
            new_access = create_access_token(
                user_id,
                domain_id,
                user["telegram_chat_id"],
                jwt_secret,
                access_expire_min,
            )
            new_refresh = generate_refresh_token()
            new_refresh_hash = hash_code(new_refresh)

            await conn.execute(
                "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) "
                "VALUES ($1::uuid, $2, now() + make_interval(days => $3))",
                user_id,
                new_refresh_hash,
                refresh_expire_days,
            )

    return new_access, new_refresh


async def invalidate_refresh_token(
    pool: asyncpg.Pool, refresh_token: str
) -> None:
    """Delete a refresh token from the database."""
    token_hash = hash_code(refresh_token)
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM refresh_tokens WHERE token_hash = $1",
            token_hash,
        )
