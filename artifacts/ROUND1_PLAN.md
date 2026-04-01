# BioCoach — Round 1: Chat Must Work

> Created: 2026-04-01
> Goal: User sends a message → gets a streamed LLM response with markdown formatting.
> Constraint: DO NOT modify files outside the scope listed below.

---

## Prerequisites (DONE)

- [x] VPN `emco-vpn.service` active — routes `10.0.0.0/8` via `ppp0`
- [x] Qwen at `10.177.5.113` reachable (ping ~298ms)
- [x] Ollama API at `10.177.5.113:11434` — responds
- [x] Markdown rendering — already implemented (`MessageItem.tsx` uses `react-markdown` + `remark-gfm`)

---

## Root Cause: Why Chat Doesn't Respond

`.env` has `LITELLM_BASE_URL=http://10.177.5.113:4000/v1` — but **there is no LiteLLM proxy on port 4000**. Only:
- Ollama at `:11434` (OpenAI-compatible API)
- OpenWebUI at `:8080` (web UI, not an API for programmatic use)

The `LLMClient` in `api/llm/client.py` uses `openai.AsyncOpenAI` SDK — fully compatible with Ollama's `/v1` endpoint. **No code changes needed** for basic connectivity.

---

## Task 1.1 — Verify Available Models on Ollama

```bash
curl -s http://10.177.5.113:11434/api/tags | python3 -m json.tool
```

Find the exact model name (e.g., `qwen3:14b`, `qwen3:14b-q4_K_M`, etc.) — this goes into `.env`.

---

## Task 1.2 — Update `.env`

**File:** `~/biocoach/.env`

```env
# CHANGE these 3 lines:
LITELLM_BASE_URL=http://10.177.5.113:11434/v1
LITELLM_MODEL=qwen3:14b
LITELLM_SUMMARY_MODEL=qwen3:14b
```

- `LITELLM_API_KEY` — keep any non-empty value (Ollama ignores it, but `openai.AsyncOpenAI` requires it)
- All other `.env` values — DO NOT CHANGE

---

## Task 1.3 — Handle `stream_options` Incompatibility

**File:** `api/llm/client.py:25`

Current code:
```python
stream = await self._client.chat.completions.create(
    model=model,
    messages=messages,
    stream=True,
    stream_options={"include_usage": True},  # ← Ollama may not support
)
```

**Test first** — Ollama 0.8+ may support `stream_options`. If it returns 400:

**Fix:** Remove `stream_options` parameter:
```python
stream = await self._client.chat.completions.create(
    model=model,
    messages=messages,
    stream=True,
)
```

**Impact:** `usage` dict in `on_complete` callback will be `None` — token counting won't work. Acceptable for MVP. The `sse_stream` function in `api/llm/streaming.py` already handles `usage=None` gracefully.

---

## Task 1.4 — Test Ollama API Directly from Server

```bash
# Non-streaming test
curl -s http://10.177.5.113:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy" \
  -d '{"model":"qwen3:14b","messages":[{"role":"user","content":"Привет! Ответь одним предложением."}],"stream":false}' \
  | python3 -m json.tool

# Streaming test
curl -s http://10.177.5.113:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy" \
  -d '{"model":"qwen3:14b","messages":[{"role":"user","content":"Привет!"}],"stream":true}'

# Streaming with stream_options test (check if supported)
curl -s http://10.177.5.113:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy" \
  -d '{"model":"qwen3:14b","messages":[{"role":"user","content":"Привет!"}],"stream":true,"stream_options":{"include_usage":true}}'
```

---

## Task 1.5 — Verify GigaChat Fallback

GigaChat is the safety net if VPN/Ollama goes down. The fallback logic in `api/chat/router.py:108-115`:
```python
try:
    llm_stream = await llm_client.stream_chat(context, _settings.LITELLM_MODEL)
except Exception as exc:
    if _settings.GIGACHAT_AUTH_KEY:
        use_gigachat = True
    else:
        raise HTTPException(status_code=502, detail="LLM service unavailable")
```

**Verify:**
```bash
# Check GigaChat key is set
grep GIGACHAT ~/biocoach/.env

# Test GigaChat OAuth from server (inside container)
docker compose exec api python3 -c "
import asyncio
from api.llm.gigachat import _get_token
from api.config import Settings
s = Settings()
if not s.GIGACHAT_AUTH_KEY:
    print('NO KEY SET')
else:
    token = asyncio.run(_get_token(s.GIGACHAT_AUTH_KEY))
    print('GigaChat token OK:', token[:20], '...')
"
```

---

## Task 1.6 — Rebuild and Test

```bash
cd ~/biocoach

# Rebuild only the API container (env changes + possible client.py fix)
docker compose up -d --build api

# Watch logs
docker compose logs -f api --tail=50

# In another terminal — test health
curl -s https://agentdata.pro/api/health
```

---

## Task 1.7 — End-to-End Browser Test

1. Open `https://agentdata.pro/`
2. Login via Telegram (`@petrovich_mobile`)
3. Send: `Привет, расскажи кратко что ты умеешь`
4. **Expect:** streamed markdown response from Qwen3
5. Send: `Где купить витамин D3?`
6. **Expect:** RouterAgent detects search intent (keyword `купить`) → SearchAgent runs DuckDuckGo → LLM responds with search results

### What to check in logs:
```
"event": "chat_message_received"
"event": "router_classified", "method": "keyword", "intent": "general_chat"
"event": "llm_call_started"
"event": "llm_call_completed"
```

For search query:
```
"event": "router_classified", "method": "keyword", "intent": "search"
"event": "search_completed", "result_count": N
```

---

## Files Modified in Round 1

| File | Change | Safe to edit |
|------|--------|-------------|
| `.env` | 3 vars: BASE_URL, MODEL, SUMMARY_MODEL | Yes — config only |
| `api/llm/client.py` | Maybe remove `stream_options` (1 line) | Yes — isolated |

**Total: 1–2 files, 3–4 lines changed.**

## Files NOT to Touch

Everything else. Specifically:
- `docker-compose.yml`
- `api/main.py`, `api/config.py`, `api/deps.py`
- `api/chat/*` (except maybe `client.py`)
- `api/auth/*`, `api/middleware/*`, `api/agents/*`
- `web/*` (markdown already works)
- `deploy/*`

---

## Success Criteria

- [ ] `curl` to Ollama from server returns valid LLM response
- [ ] Chat UI shows streamed markdown response
- [ ] Search intent ("купить") triggers SearchAgent
- [ ] GigaChat fallback verified (at least OAuth token works)
- [ ] No 502/500 errors in logs
