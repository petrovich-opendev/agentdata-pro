"""FastAPI dependency for setting RLS context from JWT claims."""

from collections.abc import AsyncIterator

import asyncpg
from fastapi import Depends

from api.db.pool import get_connection
from api.deps import get_pool
from api.middleware.auth import get_current_user


async def set_rls_context(
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> AsyncIterator[asyncpg.Connection]:
    """Acquire a connection with RLS context set from JWT domain_id claim."""
    domain_id = user["domain_id"]
    async with get_connection(pool, domain_id) as conn:
        yield conn
