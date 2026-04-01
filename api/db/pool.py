"""asyncpg connection pool with RLS context management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import structlog

logger = structlog.get_logger()


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Set role on each new connection so all queries go through RLS."""
    await conn.execute("SET ROLE biocoach_app")


async def create_pool(database_url: str) -> asyncpg.Pool:
    """Create asyncpg connection pool."""
    pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=2,
        max_size=10,
        init=_init_connection,
    )
    await logger.ainfo("db_pool_created", min_size=2, max_size=10)
    return pool


async def close_pool(pool: asyncpg.Pool) -> None:
    """Gracefully close the connection pool."""
    await pool.close()
    await logger.ainfo("db_pool_closed")


@asynccontextmanager
async def get_connection(
    pool: asyncpg.Pool, domain_id: str
) -> AsyncIterator[asyncpg.Connection]:
    """Acquire a connection with RLS context set for the given domain.

    Uses SET LOCAL so the setting is transaction-scoped and resets automatically.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_domain', $1, true)",
                domain_id,
            )
            yield conn
