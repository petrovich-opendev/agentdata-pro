"""Chat API endpoints — POST (SSE streaming) and GET (history)."""

import json
from typing import Any

import asyncpg
import nats.aio.client
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from api.chat.history import get_context_messages
from api.chat.models import MessageListResponse, MessageResponse, RenameSessionInput, SendMessageInput, SessionResponse
from api.chat.service import (
    create_session,
    format_search_results,
    get_messages,
    get_or_create_session,
    load_history,
    rename_session,
    save_message,
    soft_delete_session,
)
from api.config import Settings
from api.db.pool import get_connection
from api.deps import get_domain_config, get_llm_client, get_nats, get_pool, get_system_prompt
from api.llm.client import LLMClient
from api.llm.gigachat import gigachat_stream
from api.llm.streaming import create_sse_response, sse_stream, sse_stream_text
from api.middleware.auth import get_current_user
from api.middleware.rls import set_rls_context

logger = structlog.get_logger()

router = APIRouter(prefix="/api/chat", tags=["chat"])

_settings = Settings()

CLASSIFY_TIMEOUT_SEC = 15.0
SEARCH_TIMEOUT_SEC = 15.0


async def _classify_intent(
    nc: nats.aio.client.Client,
    domain_id: str,
    message: str,
) -> dict[str, Any]:
    """Send message to RouterAgent for intent classification via NATS request-reply."""
    subject = f"chat.{domain_id}.classify"
    payload = json.dumps({"message": message}).encode()
    try:
        response = await nc.request(subject, payload, timeout=CLASSIFY_TIMEOUT_SEC)
        return json.loads(response.data.decode())
    except Exception as exc:
        await logger.awarning("classify_timeout_or_error", error=str(exc))
        return {"intent": "general_chat", "entities": []}


async def _search(
    nc: nats.aio.client.Client,
    domain_id: str,
    query: str,
) -> dict[str, Any]:
    """Send search request to SearchAgent via NATS request-reply."""
    subject = f"agents.{domain_id}.search.request"
    payload = json.dumps({"query": query}).encode()
    try:
        response = await nc.request(subject, payload, timeout=SEARCH_TIMEOUT_SEC)
        return json.loads(response.data.decode())
    except Exception as exc:
        await logger.awarning("search_timeout_or_error", error=str(exc))
        return {"results": [], "query": query}




@router.get("/sessions")
async def list_sessions(
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """Return chat sessions for the current user (optional auth)."""
    from api.auth.service import decode_access_token
    from uuid import UUID as _UUID

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return {"sessions": [], "authenticated": False}

    token = auth_header.removeprefix("Bearer ").strip()
    try:
        claims = decode_access_token(token, Settings().JWT_SECRET)
    except Exception:
        return {"sessions": [], "authenticated": False}

    domain_id = claims["domain_id"]
    async with get_connection(pool, domain_id) as conn:
        rows = await conn.fetch(
            "SELECT id, title, created_at FROM chat_sessions "
            "WHERE domain_id = $1 AND deleted_at IS NULL "
            "ORDER BY created_at DESC",
            _UUID(domain_id),
        )
    sessions = [
        {"id": str(r["id"]), "title": r["title"], "created_at": r["created_at"].isoformat()}
        for r in rows
    ]
    return {"sessions": sessions, "authenticated": True}




@router.post("/sessions")
async def create_new_session(
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """Create a new chat session."""
    domain_id = user["domain_id"]
    async with get_connection(pool, domain_id) as conn:
        row = await create_session(conn, domain_id)
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "created_at": row["created_at"].isoformat(),
    }


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> MessageListResponse:
    """Return messages for a specific session."""
    domain_id = user["domain_id"]
    from uuid import UUID as _UUID
    sid = _UUID(session_id)
    async with get_connection(pool, domain_id) as conn:
        # Verify session belongs to this domain
        exists = await conn.fetchval(
            "SELECT 1 FROM chat_sessions WHERE id = $1 AND domain_id = $2 AND deleted_at IS NULL",
            sid, _UUID(domain_id),
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Session not found")
        rows = await get_messages(conn, sid)
    return MessageListResponse(
        messages=[
            MessageResponse(id=r["id"], role=r["role"], content=r["content"], created_at=r["created_at"])
            for r in rows
        ]
    )


@router.patch("/sessions/{session_id}")
async def rename_chat_session(
    session_id: str,
    body: RenameSessionInput,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """Rename a chat session."""
    domain_id = user["domain_id"]
    from uuid import UUID as _UUID
    sid = _UUID(session_id)
    async with get_connection(pool, domain_id) as conn:
        updated = await rename_session(conn, sid, body.title, domain_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@router.delete("/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    """Soft-delete a chat session."""
    domain_id = user["domain_id"]
    from uuid import UUID as _UUID
    sid = _UUID(session_id)
    async with get_connection(pool, domain_id) as conn:
        deleted = await soft_delete_session(conn, sid, domain_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@router.post("/messages")
async def send_message(
    body: SendMessageInput,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
    llm_client: LLMClient = Depends(get_llm_client),
    system_prompt: str = Depends(get_system_prompt),
    nc: nats.aio.client.Client | None = Depends(get_nats),
    domain_config: dict[str, Any] = Depends(get_domain_config),
):
    """Accept a user message, stream LLM response via SSE."""
    user_id = user["sub"]
    domain_id = user["domain_id"]

    await logger.ainfo("chat_message_received", user_id=user_id)

    # Acquire connection for DB ops, release before streaming
    async with get_connection(pool, domain_id) as conn:
        if body.session_id:
            from uuid import UUID as _UUID
            session_id = _UUID(str(body.session_id))
            # Verify session belongs to this domain
            exists = await conn.fetchval(
                "SELECT 1 FROM chat_sessions WHERE id = $1 AND domain_id = $2 AND deleted_at IS NULL",
                session_id, _UUID(domain_id),
            )
            if not exists:
                from fastapi import HTTPException as _HTTPException
                raise _HTTPException(status_code=404, detail="Session not found")
        else:
            session_id = await get_or_create_session(conn, user_id, domain_id)
        await save_message(conn, session_id, "user", body.content, domain_id=domain_id)
        all_messages = await load_history(conn, session_id)

    # Build context (may call LLM for summary)
    context = await get_context_messages(
        all_messages, system_prompt, llm_client, _settings.LITELLM_SUMMARY_MODEL
    )

    # Agent pipeline: classify intent, optionally search
    search_context: str | None = None
    if nc is not None and not nc.is_closed:
        classification = await _classify_intent(nc, domain_id, body.content)
        intent = classification.get("intent", "general_chat")
        entities = classification.get("entities", [])

        await logger.ainfo(
            "intent_classified",
            intent=intent,
            entities=entities,
            user_id=user_id,
        )

        if intent == "search" and entities:
            query = " ".join(entities)
            search_response = await _search(nc, domain_id, query)
            results = search_response.get("results", [])
            if results:
                search_context = format_search_results(results, query)

    # Inject search results as system message into context
    if search_context:
        context.append({"role": "system", "content": search_context})

    await logger.ainfo(
        "llm_call_started",
        user_id=user_id,
        session_id=str(session_id),
        context_length=len(context),
        has_search_context=search_context is not None,
    )

    use_gigachat = False
    llm_stream = None

    try:
        llm_stream = await llm_client.stream_chat(context, _settings.LITELLM_MODEL)
    except Exception as exc:
        await logger.awarning("litellm_failed_trying_gigachat", error=str(exc))
        if _settings.GIGACHAT_AUTH_KEY:
            use_gigachat = True
        else:
            await logger.aerror("llm_call_failed_no_fallback", error=str(exc))
            raise HTTPException(status_code=502, detail="LLM service unavailable") from exc

    model_used = _settings.GIGACHAT_MODEL if use_gigachat else _settings.LITELLM_MODEL

    async def on_complete(full_text: str, usage: dict | None) -> str:
        """Save assistant message after streaming finishes."""
        metadata: dict[str, Any] = {}
        if usage:
            metadata["usage"] = usage
        metadata["model"] = model_used
        if search_context:
            metadata["had_search"] = True

        async with get_connection(pool, domain_id) as conn:
            msg_id = await save_message(
                conn, session_id, "assistant", full_text, metadata, domain_id=domain_id
            )

        await logger.ainfo(
            "llm_call_completed",
            user_id=user_id,
            session_id=str(session_id),
            message_id=str(msg_id),
            usage=usage,
            model=model_used,
        )
        return msg_id

    if use_gigachat:
        await logger.ainfo("using_gigachat_fallback", user_id=user_id)
        gc_stream = gigachat_stream(context, _settings.GIGACHAT_AUTH_KEY, _settings.GIGACHAT_MODEL)
        return create_sse_response(sse_stream_text(gc_stream, on_complete))

    return create_sse_response(sse_stream(llm_stream, on_complete))


@router.get("/messages")
async def list_messages(
    conn: asyncpg.Connection = Depends(set_rls_context),
    user: dict = Depends(get_current_user),
) -> MessageListResponse:
    """Return message history for the current user's active session."""
    user_id = user["sub"]
    domain_id = user["domain_id"]

    session_id = await get_or_create_session(conn, user_id, domain_id)
    rows = await get_messages(conn, session_id)

    messages = [
        MessageResponse(
            id=row["id"],
            role=row["role"],
            content=row["content"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
    return MessageListResponse(messages=messages)
