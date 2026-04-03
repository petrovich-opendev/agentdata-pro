"""Chat API endpoints — POST (SSE streaming) and GET (history)."""

import json
import re
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
from api.health.profile_builder import build_health_profile
from api.health.query_classifier import classify_health_query
from api.health.data_fetcher import fetch_abnormal_alerts, fetch_targeted_data
from api.health.fact_extractor import extract_and_store_facts, get_active_facts
from api.agents.price_monitor.context import get_price_context
from api.agents.price_monitor.agent import search_prices

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



# Price-related noise words to strip when extracting product name
_PRICE_NOISE_WORDS = {
    "где", "купить", "дешевле", "дешево", "цена", "стоимость", "сколько", "стоит",
    "аптека", "аптеке", "аптеки", "заказать", "найти", "поискать", "подешевле",
    "недорого", "сравнить", "цены", "ценах", "ценой", "можно",
    "price", "cheap", "buy", "pharmacy", "where", "find", "cost", "how", "much",
}


def _extract_product_name(message: str) -> str:
    """Extract product/medication name from a price-related user message."""
    cleaned = re.sub(r"[^\w\s\-]", " ", message)
    words = cleaned.lower().split()
    meaningful = [w for w in words if w not in _PRICE_NOISE_WORDS and len(w) > 1]
    return " ".join(meaningful).strip()


async def _get_agent_city(pool, domain_id: str) -> str:
    """Read city from agent_config for price_monitor, fallback to default."""
    from uuid import UUID as _UUID
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT settings FROM agent_config WHERE domain_id = $1 AND agent_code = $2",
                _UUID(domain_id), "price_monitor",
            )
        if row and row["settings"]:
            settings = json.loads(row["settings"]) if isinstance(row["settings"], str) else row["settings"]
            return settings.get("city", "Москва")
    except Exception:
        pass
    return "Москва"



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
            "SELECT id, title, folder_id, created_at FROM chat_sessions "
            "WHERE domain_id = $1 AND deleted_at IS NULL "
            "ORDER BY created_at DESC",
            _UUID(domain_id),
        )
    sessions = [
        {"id": str(r["id"]), "title": r["title"], "folder_id": str(r["folder_id"]) if r["folder_id"] else None, "created_at": r["created_at"].isoformat()}
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
    request: Request,
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
        user_msg_id = await save_message(conn, session_id, "user", body.content, domain_id=domain_id)
        all_messages = await load_history(conn, session_id)

    # Extract health facts from user message (fire-and-forget, non-blocking)
    try:
        await extract_and_store_facts(pool, domain_id, body.content, str(user_msg_id))
    except Exception:
        await logger.awarning("fact_extraction_failed", domain_id=domain_id)

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

    locale_for_response = request.headers.get("X-Locale", "en")

    # Classify query (pure function, no IO — safe outside try)
    classification = classify_health_query(body.content)

    # Smart health context injection
    health_context_parts: list[str] = []
    try:
        language = request.headers.get("X-Locale", "en")

        # 1. Cached profile summary
        result = await build_health_profile(pool, domain_id, language)
        profile = result.get("summary_text", "")
        if profile:
            health_context_parts.append(profile)

        # 2. Fetch targeted data based on classification
        if classification["categories"]:
            targeted = await fetch_targeted_data(
                pool, domain_id,
                classification["categories"],
                classification["depth"],
                classification["temporal"],
                language,
            )
            if targeted:
                health_context_parts.append(targeted)

        # 3. Critical alerts (always included)
        alerts = await fetch_abnormal_alerts(pool, domain_id)
        if alerts:
            health_context_parts.append(alerts)

        # 4. Known health facts from previous messages
        facts_context = await get_active_facts(pool, domain_id, language)
        if facts_context:
            health_context_parts.append(facts_context)
    except Exception:
        await logger.awarning("smart_health_context_failed")

    if health_context_parts:
        context.append({"role": "system", "content": "\n\n".join(health_context_parts)})

    # Price monitor: inject watchlist context
    try:
        price_ctx = await get_price_context(pool, domain_id, locale_for_response)
        if price_ctx:
            context.append({"role": "system", "content": price_ctx})
    except Exception:
        await logger.awarning("price_context_failed", domain_id=domain_id)

    # Price monitor: on-demand search if user asks about prices
    try:
        if classification.get("categories") and "prices" in classification["categories"]:
            product_name = _extract_product_name(body.content)
            user_city = await _get_agent_city(pool, domain_id)
            category = "medication"
            cat_list = classification.get("categories", [])
            if any("LAB" in c for c in cat_list):
                category = "lab_test"

            if product_name:
                price_results = await search_prices(pool, product_name, user_city, category)
                if price_results:
                    if locale_for_response == "ru":
                        header = f"Результаты поиска цен ({product_name}, {user_city}):"
                    else:
                        header = f"Price search results ({product_name}, {user_city}):"
                    lines = [header]
                    for i, pr in enumerate(price_results[:5], 1):
                        lines.append(
                            f"{i}. {pr['product_name']} — ₽{pr['price']:,.0f}, "
                            f"{pr['pharmacy_name']} ({pr['source']})"
                        )
                        if pr.get("url"):
                            lines.append(f"   {pr['url']}")
                    context.append({"role": "system", "content": "\n".join(lines)})
    except Exception:
        await logger.awarning("price_search_failed", domain_id=domain_id)

    # Inject search results as system message into context
    if search_context:
        context.append({"role": "system", "content": search_context})

    # Inject language instruction based on X-Locale header
    lang_names = {"ru": "Russian", "en": "English"}
    lang_name = lang_names.get(locale_for_response, "English")
    context.append({"role": "system", "content": f"IMPORTANT: Respond in {lang_name}. The user has selected {lang_name} as their preferred language."})

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


# --- Phase 2: Folders & Search ---

from api.chat.models import (
    CreateFolderInput,
    FolderResponse,
    MoveChatInput,
    ReorderFoldersInput,
    SearchResponse,
    SearchResultItem,
    UpdateFolderInput,
)
from api.chat.service import (
    create_folder,
    delete_folder,
    list_folders,
    move_session_to_folder,
    reorder_folders,
    search_messages_fulltext,
    search_sessions_by_title,
    update_folder,
)


@router.post("/folders", response_model=FolderResponse)
async def create_chat_folder(
    body: CreateFolderInput,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> FolderResponse:
    domain_id = user["domain_id"]
    async with get_connection(pool, domain_id) as conn:
        row = await create_folder(conn, domain_id, body.name, body.emoji, body.color)
    return FolderResponse(**row)


@router.get("/folders", response_model=list[FolderResponse])
async def get_chat_folders(
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[FolderResponse]:
    domain_id = user["domain_id"]
    async with get_connection(pool, domain_id) as conn:
        rows = await list_folders(conn, domain_id)
    return [FolderResponse(**r) for r in rows]


@router.patch("/folders/{folder_id}", response_model=FolderResponse)
async def update_chat_folder(
    folder_id: str,
    body: UpdateFolderInput,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> FolderResponse:
    domain_id = user["domain_id"]
    from uuid import UUID as _UUID
    fid = _UUID(folder_id)
    async with get_connection(pool, domain_id) as conn:
        row = await update_folder(conn, fid, domain_id, body.name, body.emoji, body.color)
    if not row:
        raise HTTPException(status_code=404, detail="Folder not found")
    return FolderResponse(**row)


@router.delete("/folders/{folder_id}")
async def delete_chat_folder(
    folder_id: str,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    domain_id = user["domain_id"]
    from uuid import UUID as _UUID
    fid = _UUID(folder_id)
    async with get_connection(pool, domain_id) as conn:
        deleted = await delete_folder(conn, fid, domain_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"ok": True}


@router.put("/folders/reorder")
async def reorder_chat_folders(
    body: ReorderFoldersInput,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    domain_id = user["domain_id"]
    async with get_connection(pool, domain_id) as conn:
        await reorder_folders(conn, body.folder_ids, domain_id)
    return {"ok": True}


@router.patch("/sessions/{session_id}/folder")
async def move_chat_to_folder(
    session_id: str,
    body: MoveChatInput,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> dict:
    domain_id = user["domain_id"]
    from uuid import UUID as _UUID
    sid = _UUID(session_id)
    async with get_connection(pool, domain_id) as conn:
        moved = await move_session_to_folder(conn, sid, body.folder_id, domain_id)
    if not moved:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@router.get("/search", response_model=SearchResponse)
async def search_chats(
    q: str,
    mode: str = "title",
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
) -> SearchResponse:
    domain_id = user["domain_id"]
    if not q or len(q.strip()) < 1:
        raise HTTPException(status_code=400, detail="Query is required")
    q = q.strip()[:200]

    async with get_connection(pool, domain_id) as conn:
        if mode == "content":
            rows = await search_messages_fulltext(conn, domain_id, q)
            results = [
                SearchResultItem(
                    session_id=r["session_id"],
                    session_title=r["session_title"],
                    snippet=r["snippet"],
                )
                for r in rows
            ]
        else:
            rows = await search_sessions_by_title(conn, domain_id, q)
            results = [
                SearchResultItem(
                    session_id=r["id"],
                    session_title=r["title"],
                )
                for r in rows
            ]
    return SearchResponse(results=results, query=q, mode=mode)
