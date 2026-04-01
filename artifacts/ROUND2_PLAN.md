# BioCoach — Round 2: Usable Chat UX

> Created: 2026-04-01
> Depends on: Round 1 complete (chat responds)
> Goal: Session management works correctly, auto-titles, context trimming, follow-up suggestions.
> After this round: product is usable for early adopters.

---

## Current State Analysis

### What already exists (code is written but may be buggy)

| Feature | Backend | Frontend | Status |
|---------|---------|----------|--------|
| Create session | `POST /api/chat/sessions` ✅ | `createSession()` in chatStore ✅ | Works |
| List sessions | `GET /api/chat/sessions` ✅ | Sidebar with date grouping ✅ | Works |
| Switch session | `GET /api/chat/sessions/:id/messages` ✅ | `setActiveSession()` ✅ | **Buggy — loses state** |
| Delete session | `DELETE /api/chat/sessions/:id` ✅ | Sidebar delete UI ✅ | Works |
| Rename session | `PATCH /api/chat/sessions/:id` ✅ | Sidebar rename UI ✅ | **Buggy** |
| Auto-title | Not implemented ❌ | Not implemented ❌ | Missing |
| Context trimming | `api/chat/history.py` ✅ | N/A | **Untested — needs Qwen working first** |
| Follow-up suggestions | Not implemented ❌ | Not implemented ❌ | Missing |
| Send to specific session | Backend expects session in body ❌ | Sends `session_id` in body ✅ | **Mismatch** |

### Key bugs to investigate

1. **Session switching loses messages** — `setActiveSession()` sets `messages: []` then `loadMessages()` fetches from API. Race condition? Or API returns empty?
2. **Rename buggy** — `rename_session` in `service.py` has escaped dollar sign `\$1` (line ~last) that may be a copy-paste artifact
3. **`POST /api/chat/messages` ignores `session_id` from body** — the endpoint calls `get_or_create_session()` which always returns the latest session for the domain, ignoring which session the user is actually viewing

---

## Task 2.1 — Fix Session-Scoped Message Sending

### Problem
`POST /api/chat/messages` in `api/chat/router.py:72`:
```python
session_id = await get_or_create_session(conn, user_id, domain_id)
```
This always picks the **latest** session. But the frontend sends `session_id` in the body (`SendMessageInput`).

### Fix
In `api/chat/router.py`, use `body.session_id` when provided:
```python
# Instead of:
session_id = await get_or_create_session(conn, user_id, domain_id)

# Do:
if body.session_id:
    session_id = UUID(body.session_id)
else:
    session_id = await get_or_create_session(conn, user_id, domain_id)
```

**Check** `api/chat/models.py` — verify `SendMessageInput` has `session_id: str | None = None` field.

### Verification
1. Create two sessions
2. Switch to older session
3. Send message — it should appear in THAT session, not the latest one
4. Check DB: `SELECT session_id, content FROM chat_messages ORDER BY created_at DESC LIMIT 5;`

---

## Task 2.2 — Fix Session Switching

### Problem
In `web/src/stores/chatStore.ts`, `setActiveSession()`:
```typescript
setActiveSession: (id: string) => {
    if (id === activeSessionId) return;
    if (streaming) {
        abortController?.abort();
        set({ streaming: false });
    }
    set({ activeSessionId: id, messages: [], error: "" }); // ← clears messages
},
```
Messages are cleared immediately, then `loadMessages()` is called separately from `Chat.tsx` useEffect. This causes a flash of empty state.

### Fix option
Merge into a single action — load messages inside `setActiveSession`:
```typescript
setActiveSession: async (id: string) => {
    const { activeSessionId, streaming } = get();
    if (id === activeSessionId) return;
    if (streaming) {
        abortController?.abort();
        set({ streaming: false });
    }
    set({ activeSessionId: id, messages: [], error: "" });
    // Immediately load messages for new session
    try {
        const res = await apiFetch(`/api/chat/sessions/${id}/messages`);
        if (res.ok) {
            const data = await res.json();
            if (get().activeSessionId === id) {
                set({ messages: data.messages ?? data ?? [] });
            }
        }
    } catch { /* non-critical */ }
},
```

And in `Chat.tsx`, remove the separate `loadMessages` call from useEffect (or guard it to avoid double-fetching).

**Risk:** Changing async signature — check all callers. Currently called from:
- `Sidebar.tsx:handleSelectSession`
- `Chat.tsx:useEffect` (session sync)
- `chatStore.ts:deleteSession` (switch to remaining)

---

## Task 2.3 — Fix Rename (Escaped Dollar Sign)

### Problem
In `api/chat/service.py`, last function:
```python
async def rename_session(conn, session_id, title):
    await conn.execute(
        "UPDATE chat_sessions SET title = \$1 WHERE id = \$2::uuid AND deleted_at IS NULL",
        title, session_id,
    )
```
The `\$1` and `\$2` — if these are literal backslash-dollar in the source file, asyncpg will fail to bind parameters.

### Fix
```python
await conn.execute(
    "UPDATE chat_sessions SET title = $1 WHERE id = $2::uuid AND deleted_at IS NULL",
    title, session_id,
)
```

### Verification
1. Create a session, send a message
2. In sidebar, click rename (pencil icon)
3. Type new title, press Enter
4. Reload page — title persists

---

## Task 2.4 — Auto-Generate Session Titles

### Design
After the **first assistant response** in a session, generate a short title (5-7 words) summarizing the conversation topic.

### Backend
Add a function in `api/chat/service.py`:
```python
async def generate_session_title(
    llm_client: LLMClient,
    model: str,
    user_message: str,
    assistant_message: str,
) -> str:
    """Generate a short title for a chat session from the first exchange."""
    messages = [
        {"role": "system", "content": (
            "Generate a very short title (3-7 words) for this conversation. "
            "Reply with ONLY the title, no quotes, no punctuation at the end. "
            "Use the same language as the user."
        )},
        {"role": "user", "content": f"User: {user_message}\nAssistant: {assistant_message[:200]}"},
    ]
    title = await llm_client.complete(messages, model)
    return title.strip().strip('"').strip("'")[:100]
```

### Integration
In `api/chat/router.py`, inside `on_complete` callback:
```python
async def on_complete(full_text: str, usage: dict | None) -> str:
    # ... existing save logic ...

    # Auto-title: if this is the first message pair in session
    async with get_connection(pool, domain_id) as conn:
        msg_count = await conn.fetchval(
            "SELECT count(*) FROM chat_messages WHERE session_id = $1",
            session_id,
        )
        if msg_count <= 2:  # user + assistant = first exchange
            title = await generate_session_title(
                llm_client, _settings.LITELLM_SUMMARY_MODEL,
                body.content, full_text,
            )
            await rename_session(conn, str(session_id), title)

    return msg_id
```

### Frontend
Already handled — `chatStore.ts:sendMessage()` calls `get().loadSessions()` at the end, which refreshes the sidebar with new titles.

### Verification
1. Create new session
2. Send first message
3. After response completes, sidebar should show generated title instead of "New Chat"

---

## Task 2.5 — Verify Context Trimming

### Current implementation
`api/chat/history.py` already implements:
- `_RECENT_WINDOW = 10` — always include last 10 messages
- `_SUMMARY_THRESHOLD = 20` — if >20 messages, summarize older ones
- Uses `llm_client.complete()` for summarization (non-streaming)

### What to verify
1. Context trimming activates at >20 messages (send 11+ exchanges)
2. Summarization call succeeds against Qwen3
3. Summary is injected as system message
4. LLM still responds coherently after trimming

### Test
```bash
# Check logs for summarization:
docker compose logs api | grep "summarizing_history"
docker compose logs api | grep "history_summarized"
```

### Potential issue
`_SUMMARY_PROMPT` is in English but users chat in Russian. The instruction says "Write the summary in the same language the user used" — should work, but verify Qwen3 follows this instruction.

### Config consideration
`_RECENT_WINDOW = 10` and `_SUMMARY_THRESHOLD = 20` are hardcoded. For now acceptable, but in a future round these should come from `domain_types.agent_config` or `.env`.

---

## Task 2.6 — Follow-Up Suggestions

### Design
After each assistant response, show 3 clickable suggestion buttons below the message. Clicking a suggestion sends it as the next user message.

### Backend
Add suggestion generation to `on_complete` flow:

```python
async def generate_suggestions(
    llm_client: LLMClient,
    model: str,
    system_prompt: str,
    user_message: str,
    assistant_message: str,
) -> list[str]:
    """Generate 3 follow-up question suggestions."""
    messages = [
        {"role": "system", "content": (
            "Based on this conversation, suggest exactly 3 short follow-up questions "
            "the user might want to ask next. Each question should be 5-10 words. "
            "Reply as a JSON array of 3 strings, e.g.: [\"question 1\", \"question 2\", \"question 3\"]. "
            "Use the same language as the user. No numbering, no prefixes."
        )},
        {"role": "user", "content": f"User asked: {user_message}\nAssistant replied: {assistant_message[:300]}"},
    ]
    raw = await llm_client.complete(messages, model)
    import json
    try:
        suggestions = json.loads(raw)
        if isinstance(suggestions, list):
            return [str(s).strip() for s in suggestions[:3]]
    except json.JSONDecodeError:
        pass
    return []
```

### SSE integration
After the `done: true` event, send a `suggestions` event:
```python
# In on_complete or after it:
suggestions = await generate_suggestions(...)
suggestions_event = json.dumps({"suggestions": suggestions})
yield f"data: {suggestions_event}\n\n"
```

### Frontend

**types/index.ts** — extend SSEEvent:
```typescript
export interface SSEEvent {
  token: string;
  done: boolean;
  message_id?: string;
  error?: string;
  suggestions?: string[];  // NEW
}
```

**chatStore.ts** — add suggestions state:
```typescript
interface ChatState {
  // ... existing ...
  suggestions: string[];
}
```

Handle in SSE parsing:
```typescript
if (event.suggestions) {
    set({ suggestions: event.suggestions });
}
```

**New component: `Suggestions.tsx`**
```tsx
function Suggestions({ suggestions, onSelect }: { suggestions: string[]; onSelect: (s: string) => void }) {
    if (!suggestions.length) return null;
    return (
        <div className="flex flex-wrap gap-2 max-w-3xl mx-auto px-4 py-2">
            {suggestions.map((s, i) => (
                <button
                    key={i}
                    onClick={() => onSelect(s)}
                    className="px-3 py-1.5 text-sm rounded-full border border-[#3a3a5c] text-[#b0b0c8] hover:bg-[#2d2d5e] hover:text-[#e0e0e0] transition-colors"
                >
                    {s}
                </button>
            ))}
        </div>
    );
}
```

**Chat.tsx** — render below messages, above input:
```tsx
{!streaming && suggestions.length > 0 && (
    <Suggestions
        suggestions={suggestions}
        onSelect={(s) => {
            set({ suggestions: [] });
            sendMessage(s);
        }}
    />
)}
```

### Verification
1. Send a message
2. After response, 3 suggestion buttons appear
3. Click one — it sends as a new message
4. During streaming — suggestions hidden
5. New suggestions appear after new response

---

## File Change Map

| File | Task | Change |
|------|------|--------|
| `api/chat/router.py` | 2.1, 2.4, 2.6 | Use body.session_id; auto-title in on_complete; suggestions SSE |
| `api/chat/service.py` | 2.3, 2.4 | Fix \$ escaping; add generate_session_title |
| `api/chat/models.py` | 2.1 | Verify session_id field in SendMessageInput |
| `api/llm/streaming.py` | 2.6 | Add suggestions event after done |
| `web/src/stores/chatStore.ts` | 2.2, 2.6 | Fix setActiveSession; add suggestions state |
| `web/src/types/index.ts` | 2.6 | Add suggestions to SSEEvent |
| `web/src/components/Suggestions.tsx` | 2.6 | New file — suggestion buttons |
| `web/src/pages/Chat.tsx` | 2.2, 2.6 | Fix session switch effect; render Suggestions |

## Files NOT to Touch

- `api/auth/*` — auth works
- `api/middleware/*` — RLS works
- `api/agents/*` — agent framework works
- `api/llm/client.py` — LLM client works (after Round 1)
- `api/llm/gigachat.py` — fallback works
- `api/chat/history.py` — context trimming works (just verify)
- `docker-compose.yml`, `deploy/*`, `.env` — stable after Round 1
- `web/src/components/MessageItem.tsx` — markdown rendering works
- `web/src/components/ChatInput.tsx` — input works
- `web/src/stores/authStore.ts` — auth store works
- `web/src/pages/Landing.tsx` — login works

---

## Execution Order

```
2.1  Fix session-scoped sending     (backend — api/chat/router.py, models.py)
2.3  Fix rename escaping            (backend — api/chat/service.py)
2.2  Fix session switching          (frontend — chatStore.ts, Chat.tsx)
     ↑ These 3 are independent, can run in parallel

2.4  Auto-title generation          (backend — service.py + router.py)
2.5  Verify context trimming        (testing only — no code changes expected)
2.6  Follow-up suggestions          (backend + frontend — last, most complex)
```

---

## Success Criteria

- [ ] Create new session → appears in sidebar
- [ ] Switch session → messages load correctly, no flash
- [ ] Send message to specific session → appears in correct session
- [ ] Rename session → title persists after reload
- [ ] Delete session → removed from sidebar, switches to next
- [ ] First message → auto-generated title appears in sidebar
- [ ] 20+ messages → context trimming activates (check logs)
- [ ] After each response → 3 suggestion buttons appear
- [ ] Click suggestion → sends as new message
- [ ] Mobile sidebar → opens/closes correctly
