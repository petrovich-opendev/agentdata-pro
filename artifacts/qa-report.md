# QA Audit Report — BioCoach MVP

**Date:** 2026-03-31
**Scope:** Read-only code audit of `namespaces/dev/biocoach/`
**Auditor:** QA Agent (DevTeam)

---

## Summary

The BioCoach MVP codebase is largely functional and well-structured. Out of 10 QA checks, **8 PASS** and **2 FAIL**. One **CRITICAL** runtime bug was found: `save_message()` omits the required `domain_id` column, which will cause every message INSERT to fail with a NOT NULL constraint violation. Two MEDIUM issues relate to hardcoded domain-specific logic in application code.

| Result | Count |
|--------|-------|
| PASS   | 8     |
| FAIL   | 2     |
| Issues | 4     |

---

## Checklist Results

### 1. Auth Endpoints — PASS

All 4 endpoints exist in `api/auth/router.py`:
- `POST /api/auth/request-code` (line 29)
- `POST /api/auth/verify-code` (line 57)
- `POST /api/auth/refresh` (line 95)
- `POST /api/auth/logout` (line 119)

Pydantic models defined in `api/auth/models.py`: `RequestCodeInput`, `VerifyCodeInput`, `TokenResponse`.

**Note:** `RequestCodeInput` uses `telegram_chat_id: int` instead of `telegram_username` from the architecture spec. This is a simplification (no bot-based username-to-chat_id resolution).

### 2. Chat Endpoint — PASS (with deviation)

`POST /api/chat/messages` exists in `api/chat/router.py`.

**Deviation:** URL is `POST /api/chat/messages` (auto-session), not `POST /api/chat/sessions/:id/messages` as specified in architecture. The implementation auto-creates a single session per user via `get_or_create_session()`.

### 3. SSE Streaming — PASS

`create_sse_response()` in `api/llm/streaming.py:62-70` returns `StreamingResponse` with `media_type="text/event-stream"`. Confirmed SSE event format with `data:` prefix and `\n\n` delimiters.

### 4. Agent Framework — PASS

All 3 agent classes exist with correct inheritance:
- `BaseAgent` in `api/agents/base.py` — abstract class with NATS subscribe/handle/publish
- `RouterAgent` in `api/agents/router_agent.py` — intent classification via LLM
- `SearchAgent` in `api/agents/search_agent.py` — web search via DuckDuckGo

### 5. SearchAgent Uses duckduckgo_search — PASS

`api/agents/search_agent.py` imports `from duckduckgo_search import DDGS`. No SearXNG references in any `.py` file under `api/`. No httpx calls to SearXNG.

### 6. RLS Policies — PASS

Migration `api/db/migrations/versions/20260331_001_initial_schema.py`:
- `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` on `domains`, `chat_sessions`, `chat_messages`
- `FORCE ROW LEVEL SECURITY` applied to all three tables
- RLS policies filter by `current_setting('app.current_domain', true)`
- `biocoach_app` role created with `NOBYPASSRLS`
- `api/db/pool.py` sets `SET ROLE biocoach_app` on connection init
- `get_connection()` sets `app.current_domain` from JWT-derived domain_id

### 7. No Hardcoded Domain Logic in .py — FAIL

Domain-specific logic found in application code (not prompts/config):

| File | Line | Content |
|------|------|---------|
| `api/main.py` | 43 | Hardcoded path `"prompts" / "health_advisor.md"` |
| `api/chat/history.py` | 14 | String `"health-related details"` in summary prompt |

Acceptable locations (seed data / config):
- `api/db/migrations/versions/20260331_002_domain_types.py` — seed data INSERT (acceptable)
- `api/config.py:17` — `DEFAULT_DOMAIN_TYPE: str = "health"` (env-overridable, acceptable)

### 8. Docker Compose — 5 Services with Healthchecks — PASS

`docker-compose.yml` defines exactly 5 services: `nginx`, `web`, `api`, `nats`, `postgres`. All 5 have `healthcheck` blocks. No `searxng` service.

### 9. .env.example Completeness — PASS

All required variables present: `DATABASE_URL`, `NATS_URL`, `LITELLM_BASE_URL`, `LITELLM_API_KEY`, `TELEGRAM_BOT_TOKEN`, `JWT_SECRET`, `CORS_ORIGINS`.

Confirmed absent: No `SEARXNG_URL`, no `LANGFUSE_*` variables.

### 10. No Langfuse Imports — PASS

Grep for `langfuse` in all `.py` files: zero matches in application code. Only references are in `artifacts/` documentation (stale architecture docs).

---

## Issues Found

### ISSUE-1: CRITICAL — `save_message()` Missing `domain_id`

**File:** `api/chat/service.py:54-63`
**Impact:** Every message INSERT will fail at runtime.

The `chat_messages` table defines `domain_id UUID NOT NULL REFERENCES domains(id)` (migration line 103), but `save_message()` only inserts `(session_id, role, content, metadata)` — omitting `domain_id`. This will cause a PostgreSQL NOT NULL constraint violation on every call.

```sql
-- What save_message() does:
INSERT INTO chat_messages (session_id, role, content, metadata) VALUES ($1, $2, $3, $4)

-- What the schema requires:
domain_id UUID NOT NULL REFERENCES domains(id)
```

**Recommendation:** Add `domain_id` parameter to `save_message()` and include it in the INSERT statement. Pass `domain_id` from the JWT-derived user context at the call site.

### ISSUE-2: MEDIUM — Hardcoded Prompt Path

**File:** `api/main.py:43`
**Impact:** Adding a new domain type requires code changes.

```python
prompt_path = pathlib.Path(__file__).resolve().parent.parent / "prompts" / "health_advisor.md"
```

The prompt file path is hardcoded to `health_advisor.md`. For domain-agnostic architecture, this should be resolved from domain type configuration.

**Recommendation:** Load prompt path from domain configuration (DB or env var) based on active domain type.

### ISSUE-3: MEDIUM — Domain-Specific String in Application Logic

**File:** `api/chat/history.py:14`
**Impact:** Domain-specific language embedded in platform code.

```python
"user preferences, and health-related details mentioned. "
```

The `_SUMMARY_PROMPT` contains "health-related details" — this is domain-specific text in application logic rather than in prompts/config.

**Recommendation:** Move summary prompt to the prompts directory or make it configurable per domain.

### ISSUE-4: LOW — Chat Endpoint URL Deviates from Architecture

**File:** `api/chat/router.py`
**Impact:** Documentation mismatch.

Architecture spec defines `POST /api/chat/sessions/:id/messages` but implementation uses `POST /api/chat/messages` with auto-session creation. Functionally equivalent for single-session-per-user model, but creates confusion if architecture docs are referenced.

**Recommendation:** Update architecture documentation to reflect the actual API contract.

---

## Recommendations (Prioritized)

1. **P0 — Fix `save_message()` domain_id** — Add `domain_id` to the INSERT query. This is a blocking runtime bug.
2. **P1 — Extract hardcoded prompt path** — Make prompt file path configurable per domain type.
3. **P1 — Remove domain-specific string from history.py** — Move `_SUMMARY_PROMPT` to prompts directory.
4. **P2 — Update architecture docs** — Align API contract documentation with actual implementation.
