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

    lines = [
        "IMPORTANT: Below are real-time web search results. You MUST use them to answer the user.",
        "Include specific prices, links, and details from these results.",
        "Do NOT say you cannot search — the search has already been done for you.",
        f"",
        f"Web search results for '{query}':",
    ]
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


# --- Phase 2: Folders & Search ---


async def create_folder(
    conn: asyncpg.Connection,
    domain_id: str,
    name: str,
    emoji: str | None = None,
    color: str | None = None,
) -> dict:
    max_order = await conn.fetchval(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM chat_folders WHERE domain_id = $1",
        UUID(domain_id),
    )
    row = await conn.fetchrow(
        """
        INSERT INTO chat_folders (domain_id, name, emoji, color, sort_order)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, name, emoji, color, sort_order, created_at
        """,
        UUID(domain_id), name, emoji, color, max_order,
    )
    return dict(row)


async def list_folders(conn: asyncpg.Connection, domain_id: str) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, name, emoji, color, sort_order, created_at
        FROM chat_folders
        WHERE domain_id = $1
        ORDER BY sort_order ASC
        """,
        UUID(domain_id),
    )
    return [dict(r) for r in rows]


async def update_folder(
    conn: asyncpg.Connection,
    folder_id: UUID,
    domain_id: str,
    name: str | None = None,
    emoji: str | None = None,
    color: str | None = None,
) -> dict | None:
    current = await conn.fetchrow(
        "SELECT id, name, emoji, color, sort_order, created_at FROM chat_folders WHERE id = $1 AND domain_id = $2",
        folder_id, UUID(domain_id),
    )
    if not current:
        return None
    new_name = name if name is not None else current["name"]
    new_emoji = emoji if emoji is not None else current["emoji"]
    new_color = color if color is not None else current["color"]
    row = await conn.fetchrow(
        """
        UPDATE chat_folders SET name = $1, emoji = $2, color = $3
        WHERE id = $4 AND domain_id = $5
        RETURNING id, name, emoji, color, sort_order, created_at
        """,
        new_name, new_emoji, new_color, folder_id, UUID(domain_id),
    )
    return dict(row) if row else None


async def delete_folder(
    conn: asyncpg.Connection, folder_id: UUID, domain_id: str
) -> bool:
    result = await conn.execute(
        "DELETE FROM chat_folders WHERE id = $1 AND domain_id = $2",
        folder_id, UUID(domain_id),
    )
    return result == "DELETE 1"


async def reorder_folders(
    conn: asyncpg.Connection, folder_ids: list[UUID], domain_id: str
) -> None:
    for i, fid in enumerate(folder_ids):
        await conn.execute(
            "UPDATE chat_folders SET sort_order = $1 WHERE id = $2 AND domain_id = $3",
            i, fid, UUID(domain_id),
        )


async def move_session_to_folder(
    conn: asyncpg.Connection,
    session_id: UUID,
    folder_id: UUID | None,
    domain_id: str,
) -> bool:
    result = await conn.execute(
        """
        UPDATE chat_sessions SET folder_id = $1
        WHERE id = $2 AND domain_id = $3 AND deleted_at IS NULL
        """,
        folder_id, session_id, UUID(domain_id),
    )
    return result == "UPDATE 1"


async def search_sessions_by_title(
    conn: asyncpg.Connection, domain_id: str, query: str
) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id, title, created_at, folder_id
        FROM chat_sessions
        WHERE domain_id = $1
          AND deleted_at IS NULL
          AND title ILIKE $2
        ORDER BY created_at DESC
        LIMIT 50
        """,
        UUID(domain_id), f"%{query}%",
    )
    return [dict(r) for r in rows]


async def search_messages_fulltext(
    conn: asyncpg.Connection, domain_id: str, query: str
) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (s.id)
            s.id AS session_id,
            s.title AS session_title,
            ts_headline(
                'russian',
                m.content,
                plainto_tsquery('russian', $2) || plainto_tsquery('english', $2),
                'MaxWords=30, MinWords=10, StartSel=<mark>, StopSel=</mark>'
            ) AS snippet
        FROM chat_messages m
        JOIN chat_sessions s ON s.id = m.session_id
        WHERE m.domain_id = $1
          AND s.deleted_at IS NULL
          AND m.search_vector @@ (plainto_tsquery('russian', $2) || plainto_tsquery('english', $2))
        ORDER BY s.id, m.created_at DESC
        LIMIT 50
        """,
        UUID(domain_id), query,
    )
    return [dict(r) for r in rows]
