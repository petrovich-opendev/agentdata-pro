"""Database operations for chat sessions and messages."""

import json
from uuid import UUID

import asyncpg
import structlog

logger = structlog.get_logger()


async def get_or_create_session(
    conn: asyncpg.Connection, user_id: str, domain_id: str
) -> UUID:
    """Find active session for user's domain, or create one.

    RLS filters by domain_id automatically. Each domain has one owner,
    so domain_id is sufficient for "one chat per user" semantics.
    """
    row = await conn.fetchrow(
        """
        SELECT id FROM chat_sessions
        WHERE domain_id = $1 AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT 1
        """,
        UUID(domain_id),
    )
    if row:
        return row["id"]

    new_row = await conn.fetchrow(
        """
        INSERT INTO chat_sessions (domain_id)
        VALUES ($1)
        RETURNING id
        """,
        UUID(domain_id),
    )
    await logger.ainfo(
        "chat_session_created",
        session_id=str(new_row["id"]),
        user_id=user_id,
    )
    return new_row["id"]


async def save_message(
    conn: asyncpg.Connection,
    session_id: UUID,
    role: str,
    content: str,
    metadata: dict | None = None,
    domain_id: str | None = None,
) -> UUID:
    """Insert a chat message and return its id."""
    row = await conn.fetchrow(
        """
        INSERT INTO chat_messages (session_id, domain_id, role, content, metadata)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        session_id,
        UUID(domain_id) if domain_id else None,
        role,
        content,
        json.dumps(metadata) if metadata else None,
    )
    return row["id"]


async def load_history(conn: asyncpg.Connection, session_id: UUID) -> list[dict]:
    """Load all messages for a session, ordered by created_at ASC."""
    rows = await conn.fetch(
        """
        SELECT id, role, content, created_at
        FROM chat_messages
        WHERE session_id = $1
        ORDER BY created_at ASC
        """,
        session_id,
    )
    return [dict(r) for r in rows]


async def get_messages(conn: asyncpg.Connection, session_id: UUID) -> list[dict]:
    """Load all messages for display (GET endpoint)."""
    return await load_history(conn, session_id)


def format_search_results(results: list[dict], query: str) -> str:
    """Format search results into a system message for LLM context injection."""
    if not results:
        return ""

    lines = [f"Search results for '{query}':"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        url = r.get("url", "")
        snippet = r.get("snippet", "")
        lines.append(f"{i}. {title} — {url}")
        if snippet:
            lines.append(f"   {snippet}")

    return "\n".join(lines)


async def create_session(
    conn: asyncpg.Connection, domain_id: str
) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO chat_sessions (domain_id)
        VALUES ($1)
        RETURNING id, title, created_at
        """,
        UUID(domain_id),
    )
    return dict(row)


async def rename_session(
    conn: asyncpg.Connection, session_id: UUID, title: str, domain_id: str
) -> bool:
    result = await conn.execute(
        """
        UPDATE chat_sessions
        SET title = $1
        WHERE id = $2 AND domain_id = $3 AND deleted_at IS NULL
        """,
        title,
        session_id,
        UUID(domain_id),
    )
    return result == "UPDATE 1"


async def soft_delete_session(
    conn: asyncpg.Connection, session_id: UUID, domain_id: str
) -> bool:
    result = await conn.execute(
        """
        UPDATE chat_sessions
        SET deleted_at = now()
        WHERE id = $1 AND domain_id = $2 AND deleted_at IS NULL
        """,
        session_id,
        UUID(domain_id),
    )
    return result == "UPDATE 1"
