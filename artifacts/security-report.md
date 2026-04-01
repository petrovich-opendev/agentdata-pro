# Security Audit Report — BioCoach MVP (OWASP Top 10)

**Date:** 2026-03-31
**Scope:** Read-only security audit of `namespaces/dev/biocoach/`
**Auditor:** QA Agent (DevTeam)
**Standard:** OWASP Top 10 (2021)

---

## Summary

The BioCoach MVP has a **solid security foundation**: parameterized SQL queries, JWT authentication on all protected endpoints, RLS-based data isolation, and proper input validation via Pydantic. However, one **CRITICAL** issue was found: `save_message()` omits the required `domain_id` column, which breaks both data integrity and RLS isolation on chat messages. Two additional findings relate to missing rate limiting and overly permissive CORS configuration.

| Severity | Count |
|----------|-------|
| CRITICAL | 1     |
| HIGH     | 0     |
| MEDIUM   | 1     |
| LOW      | 1     |
| INFO     | 1     |

---

## OWASP Checklist Results

### A03:2021 — Injection (SQL Injection) — PASS

All database queries use asyncpg parameterized placeholders (`$1`, `$2`, etc.). No f-string SQL with user-controlled input found.

**Evidence (sample of verified queries):**
- `api/auth/service.py` — all queries use `$1`, `$2` placeholders
- `api/chat/service.py` — `INSERT INTO chat_messages ... VALUES ($1, $2, $3, $4)`
- `api/db/migrations/` — migration DDL uses f-strings with hardcoded table names from Python lists (not user input) — acceptable

### A01:2021 — Broken Access Control (JWT Auth) — PASS

- `OAuth2PasswordBearer` extracts Bearer token (`api/middleware/auth.py`)
- `get_current_user` dependency validates JWT signature and expiration
- All chat endpoints use `Depends(get_current_user)` for protection
- Auth endpoints (`request-code`, `verify-code`) are intentionally unprotected
- JWT claims include `domain_id` used for RLS context

### A02:2021 — Cryptographic Failures (Secrets in Code) — PASS

- No real secrets (API keys, passwords, tokens) found in `.py` or `.ts` source files
- `.env.example` uses placeholder values (`changeme`, `sk-change-me`) — acceptable for template
- `JWT_SECRET` loaded from environment variable, not hardcoded
- `TELEGRAM_BOT_TOKEN` loaded from environment variable

### A01:2021 — IDOR / Data Isolation — PASS (with caveat)

RLS enforcement is correctly implemented:
- `domain_id` extracted from verified JWT (cannot be manipulated by client)
- `app.current_domain` session variable set on every connection via `get_connection()`
- RLS policies on `chat_sessions` and `chat_messages` filter by `current_setting('app.current_domain')`
- `FORCE ROW LEVEL SECURITY` prevents superuser bypass
- `biocoach_app` role has `NOBYPASSRLS`

**Caveat:** `save_message()` doesn't supply `domain_id` — see VULN-1 below.

### A09:2021 — Security Logging and Monitoring (Error Handling) — PASS

- Error responses use generic messages: `"Invalid credentials"`, `"LLM service unavailable"`, `"Failed to send code"`
- Stack traces logged server-side via structlog only, not exposed to client
- `api/llm/streaming.py:56` logs `detail=str(exc)` to server log, sends generic error SSE event to client

### A05:2021 — Security Misconfiguration (CORS) — FAIL (LOW)

**File:** `api/main.py:97-101`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins_list,  # From CORS_ORIGINS env var — good
    allow_methods=["*"],              # Wildcarded — overly permissive
    allow_headers=["*"],              # Wildcarded — overly permissive
)
```

Origins are correctly restricted via `CORS_ORIGINS` env var (`.env.example` has `https://agentdata.pro`). However, `allow_methods` and `allow_headers` are wildcarded, allowing any HTTP method (PUT, DELETE, PATCH, etc.) and any header.

### A04:2021 — Insecure Design (Input Validation) — PASS

All request bodies validated via Pydantic models:
- `VerifyCodeInput.code` — `min_length=6, max_length=6, pattern=r"^\d{6}$"`
- `SendMessageInput.content` — `strip_whitespace=True, min_length=1, max_length=10000`
- `RequestCodeInput.telegram_chat_id` — validated as `int` by Pydantic type coercion

### A07:2021 — Identification and Authentication Failures (Rate Limiting) — FAIL (MEDIUM)

**Missing:** No rate limiting on `POST /api/auth/request-code`.

- The `auth_codes.attempts` column limits verification attempts to 5 per code — this protects against brute-force code guessing.
- However, there is **no throttling on code generation** — an attacker can flood code requests for any `telegram_chat_id`, causing Telegram API spam.
- Architecture specifies `middleware/rate_limit.py` but this file does not exist.

### A07:2021 — Refresh Token Rotation — PASS

- Old refresh token deleted: `DELETE FROM refresh_tokens WHERE id = $1` (`api/auth/service.py:228-230`)
- New refresh token issued: `INSERT INTO refresh_tokens ...` (`api/auth/service.py:269-275`)
- Both operations within the same database transaction — atomic rotation

---

## Vulnerabilities Found

### VULN-1: CRITICAL — Missing `domain_id` in `save_message()` Breaks RLS

**File:** `api/chat/service.py:54-63`
**OWASP Category:** A01:2021 — Broken Access Control
**Impact:** Runtime INSERT failure; potential RLS bypass if DEFAULT is added without proper value

The `chat_messages` table defines `domain_id UUID NOT NULL REFERENCES domains(id)` (migration `20260331_001_initial_schema.py:103`), and RLS policies filter by `domain_id`. However, `save_message()` does not include `domain_id` in the INSERT:

```python
INSERT INTO chat_messages (session_id, role, content, metadata)
VALUES ($1, $2, $3, $4)
```

**Current impact:** Every call to `save_message()` will fail with `NOT NULL constraint violation on column "domain_id"`. No messages can be saved.

**Potential secondary risk:** If a developer "fixes" this by adding `DEFAULT` on the column without using the correct domain_id from JWT context, it could silently break RLS isolation.

**Remediation:** Add `domain_id` parameter to `save_message()`. Pass the JWT-derived `domain_id` from the request context. Ensure the value is always sourced from the verified JWT, never from client input.

### VULN-2: MEDIUM — No Rate Limiting on Auth Code Request

**File:** `api/auth/router.py:29` (endpoint), no `middleware/rate_limit.py` exists
**OWASP Category:** A07:2021 — Identification and Authentication Failures
**Impact:** Telegram API spam, potential service abuse

An attacker can call `POST /api/auth/request-code` repeatedly with any `telegram_chat_id`, triggering unlimited Telegram bot messages. No IP-based throttling, no per-user cooldown, no CAPTCHA.

**Remediation:** Implement rate limiting middleware:
- Per-IP: max 5 requests/minute on `/api/auth/request-code`
- Per-chat_id: max 1 code request per 60 seconds
- Consider implementing the `middleware/rate_limit.py` specified in architecture

### VULN-3: LOW — CORS Methods and Headers Wildcarded

**File:** `api/main.py:100-101`
**OWASP Category:** A05:2021 — Security Misconfiguration
**Impact:** Minimal (origins are restricted), but violates principle of least privilege

```python
allow_methods=["*"],
allow_headers=["*"],
```

**Remediation:** Restrict to actual methods and headers used:
```python
allow_methods=["GET", "POST", "OPTIONS"],
allow_headers=["Authorization", "Content-Type"],
```

### VULN-4: INFO — Multiple `Settings()` Instantiations

**Files:** `api/auth/router.py` (per-call `get_settings()`), `api/chat/router.py` (module-level `_settings = Settings()`)
**OWASP Category:** N/A — Code quality
**Impact:** No security impact. Inconsistency pattern — if environment variables change at runtime, different parts of the app may see different config values.

**Remediation:** Use a single cached `Settings()` instance (e.g., `@lru_cache` on factory function).

---

## Recommendations (Prioritized)

1. **P0 — Fix `save_message()` domain_id** — Add `domain_id` to INSERT query, sourced from JWT context. This is both a functional bug and a security-relevant gap.
2. **P1 — Implement rate limiting on `/api/auth/request-code`** — Add IP-based and per-chat_id cooldowns. Consider using `slowapi` or custom middleware.
3. **P2 — Restrict CORS methods/headers** — Replace `["*"]` with explicit lists of allowed methods and headers.
4. **P3 — Unify Settings instantiation** — Use `@lru_cache` pattern for consistent config access.

---

## Positive Findings

The following security practices are well-implemented:

- Parameterized SQL queries throughout — no injection vectors found
- JWT-based authentication with proper validation
- RLS with `FORCE ROW LEVEL SECURITY` and `NOBYPASSRLS` role — defense in depth
- Pydantic input validation with strict constraints
- Refresh token rotation with atomic delete-and-recreate
- No secrets in source code
- Generic error messages — no internal information leakage
- structlog for server-side logging without client exposure
