# Knowledge Domains Platform — Architecture Review Report

> Reviewer: DevTeam Agent
> Date: 2026-03-31
> Documents reviewed: requirements.md, architecture.md
> Scope: Consistency, domain-agnosticism, DB schema, agent architecture, auth security, NATS design, gaps, risks

---

## Summary

The requirements and architecture documents are well-structured and demonstrate clear platform-first thinking. The separation of platform code from domain configuration (BioCoach) is correctly framed. However, the review identifies **3 critical issues**, **7 significant issues**, and **12 minor issues / recommendations** that should be resolved before implementation begins.

---

## 1. CRITICAL: Frontend Framework Conflict

**Finding:** Requirements (section 5) and architecture both specify **React + TypeScript**. The global development rules (CLAUDE.md) mandate **Vue 3 + TypeScript** as the approved frontend framework.

| Source | Framework |
|--------|-----------|
| CLAUDE.md (global rules) | Vue 3 + TypeScript |
| requirements.md section 5 | React + TypeScript |
| architecture.md section 4 | React 18+ TypeScript |

**Risk:** This is a blocking conflict. The global rules exist because Vue 3 is the audit-approved stack. Building with React means either (a) the global rules are wrong and need updating, or (b) the project documents need to switch to Vue 3.

**Action required:** Owner must decide. If React is chosen, update CLAUDE.md. If Vue 3, update requirements.md and architecture.md (component structure, state management: Pinia instead of Zustand, etc.).

---

## 2. CRITICAL: Nginx Configuration Error

**Finding:** The nginx config (architecture section 10) combines `proxy_pass` and `try_files` in the same location block:

```nginx
location / {
    proxy_pass http://web:80;
    try_files $uri $uri/ /index.html;
}
```

`try_files` does not work with `proxy_pass` — they are mutually exclusive directives. Nginx will either ignore `try_files` or produce unexpected behavior.

**Fix:** Two options:
- **Option A (proxy to web container):** Remove `try_files`. The `web` container's own nginx handles SPA fallback.
- **Option B (serve static directly):** Mount the React/Vue build as a volume in the main nginx container, remove `proxy_pass`, keep `try_files`. Eliminates the `web` service entirely (5 services instead of 6).

**Recommendation:** Option B is simpler for MVP. One fewer container, one fewer network hop.

---

## 3. CRITICAL: Telegram Username Mutability as Auth Identifier

**Finding:** The system uses `telegram_username` as the primary user identifier (`users.telegram_username UNIQUE NOT NULL`). Telegram usernames can be changed by the user at any time.

**Scenario:**
1. User registers as `@alice`
2. User changes Telegram username to `@alice_new`
3. User cannot log in (system looks up `@alice_new`, finds no match)
4. Worse: another person claims `@alice` and now has access to the original account

**Fix:** Use `telegram_chat_id` (BIGINT, immutable) as the primary identifier. The `chat_id` is obtained when the bot sends the verification code. Flow adjustment:
1. User enters `@username` on the portal
2. Bot sends code to that user (obtaining `chat_id` in the process)
3. On verify, store `chat_id` as the stable identifier
4. `telegram_username` becomes a display field, not a lookup key

**Schema change:** `UNIQUE` constraint should be on `telegram_chat_id`, not `telegram_username`.

---

## 4. Domain-Agnosticism Violations

Overall the domain-agnostic design is solid. The following leaks were found:

### 4a. DATABASE_URL uses "biocoach" (Significant)

```env
DATABASE_URL=postgresql://biocoach:${DB_PASSWORD}@postgres:5432/biocoach
```

The database name and user are `biocoach` — a domain-specific name. Should be platform-generic (e.g., `kdplatform`, `domains_platform`).

### 4b. SearXNG default_lang hardcoded to "ru" (Minor)

```yaml
search:
  default_lang: "ru"
```

The SearXNG server-level default is set to Russian. This is fine if overridden per-request by the SearchAgent (which it is — the code passes `language` from domain config). However, document this clearly: SearXNG default_lang is irrelevant because per-request params override it.

### 4c. knowledge_nodes.node_type comments (Minor)

```sql
node_type TEXT NOT NULL,  -- 'biomarker', 'medication', etc.
```

Comments reference health-specific types. The schema itself is generic, but comments should use domain-neutral examples (e.g., `'entity', 'concept', 'resource'`).

---

## 5. DB Schema Issues

### 5a. No uniqueness constraint on domains.owner_id (Significant)

Requirements state: "Each user has exactly one personal knowledge domain" (US-2). The schema has no constraint enforcing this:

```sql
-- Missing:
CREATE UNIQUE INDEX idx_domains_owner ON domains(owner_id) WHERE deleted_at IS NULL;
```

Without this, application bugs could create duplicate domains per user.

### 5b. No index on refresh_tokens.token_hash (Significant)

Token refresh validates the hash, but there's no index on `token_hash`. The existing index is on `user_id` only. Since the refresh endpoint receives the token (not the user_id), lookup must scan:

```sql
-- Missing:
CREATE UNIQUE INDEX idx_refresh_tokens_hash ON refresh_tokens(token_hash);
```

### 5c. RLS UUID-to-TEXT casting (Minor)

```sql
USING (id::text = current_setting('app.current_domain', true))
```

Casting UUID to TEXT on every row check bypasses index usage. Consider:
- Store the setting as UUID and compare directly, or
- Accept the performance cost for MVP (10 users, small dataset)

### 5d. No cleanup mechanism for auth_codes (Minor)

Expired codes accumulate. Add either:
- A scheduled cleanup (e.g., `DELETE FROM auth_codes WHERE expires_at < now() - interval '1 hour'`)
- A note in the architecture about periodic cleanup

### 5e. Missing updated_at columns (Minor)

`domains`, `chat_sessions`, `chat_messages` lack `updated_at`. While MVP may not need it, adding it now avoids a migration later. `knowledge_nodes` has it but no auto-update trigger.

### 5f. No soft-delete column on domains table (Minor)

`chat_sessions` has `deleted_at` for soft delete. `domains` does not, but may need it for Phase 3 (multiple domains, domain deletion).

---

## 6. Auth Flow Issues

### 6a. No CSRF protection on refresh endpoint (Significant)

The refresh token is sent via HttpOnly cookie. The `POST /api/auth/refresh` endpoint is vulnerable to CSRF — a malicious site can trigger a POST with the cookie attached.

**Fix:** Require a CSRF token header (e.g., `X-CSRF-Token`) that the SPA sends and the API validates. Alternatively, use the `SameSite=Strict` cookie attribute (already mentioned) — but verify browser support for your user base.

**Note:** `SameSite=Strict` mitigates CSRF in modern browsers, but document this as a deliberate security decision, not an oversight.

### 6b. JWT contains domain_id — limits multi-domain future (Minor)

JWT claims include `domain_id`. In Phase 3 (multiple domains per user), this breaks. Consider:
- Keeping only `sub` (user_id) in JWT
- Loading domain_id per-request from DB (or from a header/query param)
- Accept the tech debt for MVP and plan a migration

### 6c. No auth code lockout period (Minor)

After 5 failed attempts, what happens? The schema tracks `attempts` but the architecture doesn't specify a lockout duration. Recommend: after 5 failed attempts on a code, that code is invalidated. User must request a new code (subject to rate limiting).

### 6d. No access token revocation (Minor, acceptable for MVP)

If a user's account is compromised, there's no way to invalidate existing access tokens (30-min lifetime). Refresh token rotation helps limit damage. Document this as a known limitation.

---

## 7. Agent Architecture Issues

### 7a. No hot-reload for new domain types (Significant)

Agent lifecycle (architecture section 7) loads domain_types at startup and starts agents. If a new domain_type is added to the DB while the system is running, no new agents are started until restart.

**For MVP:** Acceptable (only one domain type). Document the limitation.
**For Phase 3:** Need a mechanism (DB polling, NATS control plane, or admin endpoint) to trigger agent reload.

### 7b. domain_config override not used by agents (Significant)

`domains.config_override` exists for per-domain customization, but agents receive `domain_config` from `domain_types` (type-level), not merged with the per-domain override. The architecture should specify how/when overrides are merged.

### 7c. No error handling in agent pipeline (Significant)

The chat flow (section 3) describes the happy path. Missing:
- What happens if RouterAgent fails or times out?
- What happens if SearchAgent returns no results or errors?
- What happens if NATS is unreachable?
- What is the timeout for agent responses?

**Recommendation:** Define fallback behavior:
- RouterAgent timeout (e.g., 5s) → default to `general_chat` intent
- SearchAgent timeout (e.g., 15s) → respond without search results, notify user
- NATS down → direct LLM call (bypass agent pipeline), log warning

### 7d. BaseAgent.start() subscribes to domain_id="*" but receives type-level config (Minor)

A single SearchAgent instance handles ALL domains, but its config comes from one `domain_type`. This works only if all domains of the same type share the same search config. With `config_override`, they might not. Clarify this in the architecture.

---

## 8. NATS Subject Design Issues

### 8a. No JetStream configuration specified (Significant)

The architecture mentions "NATS JetStream" but never defines:
- Stream names, subjects, retention policy
- Consumer configuration (durable? ack policy? max deliver?)
- Message TTL
- Max message size

**Recommendation:** Define at minimum:

```
Stream: AGENTS
  Subjects: chat.>, agents.>
  Retention: WorkQueue (messages consumed once)
  MaxAge: 5 minutes
  Storage: Memory (MVP)
```

### 8b. events.chat.message has no domain scoping (Minor)

```
events.chat.message  # Event: new message (analytics, logging)
```

This subject lacks `{domain_id}`, meaning analytics consumers see all domains. For MVP this is fine (only analytics/logging), but for Phase 3 multi-tenant isolation, scope it: `events.{domain_id}.chat.message`.

### 8c. No dead-letter / error subject (Minor)

Failed agent messages have no defined destination. Add:
```
agents.{domain_id}.*.error  # Failed agent processing
```

---

## 9. Missing Pieces

### 9a. Follow-up suggestions generation (Gap)

US-3 requires "Follow-up suggestions after each AI response (3 clickable options)" but the architecture doesn't describe how they are generated. Options:
- Include in the LLM system prompt: "Always end with 3 follow-up questions"
- Separate LLM call after main response
- Define in `ui_config.suggestions_style`

**Action:** Specify the approach in the architecture.

### 9b. Session title auto-generation (Gap)

US-5 requires "Session title auto-generated from first message (via LLM)" but no architecture detail exists. Specify:
- Which LLM (local Qwen3 to save cost?)
- Sync or async (after first message, background job?)
- Fallback if LLM fails (truncated first message?)

### 9c. API error response format (Gap)

No standardized error response format defined. Recommend:

```json
{
  "error": {
    "code": "AUTH_CODE_EXPIRED",
    "message": "Verification code has expired",
    "detail": null
  }
}
```

### 9d. No backup strategy (Gap)

PostgreSQL holds all user data. No backup strategy is mentioned. Minimum for MVP:
- Daily `pg_dump` to a separate location
- Document recovery procedure

### 9e. No graceful degradation specification (Gap)

What happens when external dependencies fail?
- LiteLLM unreachable → ?
- SearXNG unreachable → ?
- NATS unreachable → ?

### 9f. No rate limiting on chat endpoints (Gap)

Rate limiting is specified for auth endpoints only. A malicious or buggy client could flood `/api/chat/sessions/:id/messages`, causing excessive LLM costs. Add rate limiting (e.g., 20 messages per minute per user).

---

## 10. Risks and Trade-offs

| # | Risk | Severity | Likelihood | Mitigation |
|---|------|----------|-----------|------------|
| R1 | Framework conflict (React vs Vue) blocks implementation | Critical | Certain | Decide before writing any code |
| R2 | Telegram username change breaks auth | Critical | Medium | Switch to chat_id as primary identifier |
| R3 | 8GB RAM for 6 containers + LLM routing may be tight | High | Medium | Profile memory: PG (~1GB), NATS (~128MB), SearXNG (~512MB), API (~256MB), Nginx (~64MB). Monitor aggressively. |
| R4 | SSE over POST is non-standard | Medium | Low | Some CDNs/proxies may buffer or break SSE responses. The nginx config disables buffering, which helps. Test with real clients. |
| R5 | Single server, no redundancy | Medium | Low (MVP) | Acceptable for 10 users. Document disaster recovery (Docker Compose restart, PG backup restore). |
| R6 | In-memory rate limiting lost on restart | Low | Medium | Acceptable for MVP. Redis-backed rate limiting for Phase 2. |
| R7 | No monitoring/alerting beyond Langfuse | Medium | Medium | Add uptime monitoring (e.g., UptimeRobot on /api/health). Langfuse covers LLM costs only. |
| R8 | LLM cost runaway (no per-user budget) | Medium | Medium | Add token counting + daily budget per user in Phase 2. Log costs via Langfuse now. |

---

## 11. Checklist: Actions Before Implementation

### Must fix (blocking)

- [ ] **Resolve React vs Vue conflict** — update either CLAUDE.md or project documents
- [ ] **Fix nginx config** — remove conflicting `proxy_pass` + `try_files`
- [ ] **Switch auth identifier** — use `telegram_chat_id` (immutable) as primary key, not `telegram_username`

### Should fix (before or during Phase 1)

- [ ] **Add UNIQUE constraint** on `domains(owner_id)` for MVP invariant
- [ ] **Add index** on `refresh_tokens(token_hash)`
- [ ] **Rename database** from `biocoach` to platform-generic name
- [ ] **Document CSRF mitigation** — confirm SameSite=Strict is sufficient or add CSRF token
- [ ] **Define JetStream stream/consumer config** — retention, TTL, ack policy
- [ ] **Specify agent error handling and timeouts** — fallback behavior for each failure mode
- [ ] **Specify follow-up suggestions mechanism** — LLM prompt, separate call, or config
- [ ] **Specify session title generation** — model, sync/async, fallback
- [ ] **Document config_override merge strategy** — when/how domain overrides apply

### Nice to have (Phase 1 or early Phase 2)

- [ ] **Standardize API error format**
- [ ] **Add rate limiting to chat endpoints**
- [ ] **Add PostgreSQL backup cron**
- [ ] **Add uptime monitoring**
- [ ] **Scope analytics events** — `events.{domain_id}.chat.message`
- [ ] **Add dead-letter subject** for failed agent messages
- [ ] **Add auth_codes cleanup** — scheduled or on-demand
- [ ] **Add updated_at columns** to domains, chat_sessions, chat_messages

---

## 12. What's Done Well

To be clear, the architecture has strong foundations:

1. **Platform vs Domain separation** is correctly defined and consistently applied across DB schema, agent config, and API design
2. **RLS for data isolation** is properly designed with domain_id propagation
3. **NATS subject namespacing** with `{domain_id}` provides clean multi-tenant isolation
4. **Domain config in DB** (not code) correctly implements the "new domain = DB row + prompt" requirement
5. **Agent registry pattern** is extensible — new agents register without platform code changes
6. **Auth flow** is sound (code-based, no passwords, refresh rotation)
7. **Context trimming strategy** is practical and well-thought-out
8. **Denormalized domain_id in chat_messages** is a smart trade-off for RLS performance
9. **Knowledge graph tables created early** for schema stability — good forward planning
10. **LLM model selection from domain config** keeps the platform model-agnostic
