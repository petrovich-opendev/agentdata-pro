# Phase 1: Foundation - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Docker Compose infrastructure, PostgreSQL with RLS schema and domain isolation, Auth service (JWT + Argon2id registration/login/refresh/password-reset with rate limiting), FastAPI skeleton with middleware, and append-only partitioned audit event log. No UI — backend only.

</domain>

<decisions>
## Implementation Decisions

### Email delivery (password reset)
- Use SMTP via `aiosmtplib` (async, works with any SMTP provider)
- SMTP credentials from environment variables (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD)
- Password reset: generate secure token, store hash in DB with expiry (1 hour), send link via email
- Dev mode: log email to console instead of sending (SMTP_DEV=true)

### RLS context injection
- FastAPI middleware sets `SET LOCAL app.current_domain_id = '{domain_id}'` at the start of each request transaction
- `SET LOCAL` is transaction-scoped — cannot leak between requests via connection pool
- Superuser connections (migrations, admin) bypass RLS — use separate connection pool with different role
- RLS policies use `current_setting('app.current_domain_id')::uuid` — mark functions as LEAKPROOF where possible
- Phase 1 creates the schema and RLS policies; Phase 2 activates them with actual domains

### Docker Compose structure
- Services: nginx, api (FastAPI), postgres (pgvector/pgvector:pg16), redis (redis:7-alpine)
- Internal Docker network for all services; only nginx exposes ports 80/443
- PostgreSQL: no exposed port, accessed only from api and worker containers
- Redis: no exposed port, accessed only from api and worker containers
- Volumes: pg_data, redis_data (persistent)
- All services: `restart: unless-stopped`
- Logging: json-file driver, max-size 50m, max-file 5

### Audit event schema
- Table `events` partitioned by month (pg_partman)
- Columns: id (bigserial), event_id (uuid, unique), actor_id (uuid), actor_type (text: 'user'|'agent'|'system'), action (text), resource_type (text), resource_id (uuid nullable), domain_id (uuid nullable), payload (jsonb), ip_address (inet nullable), created_at (timestamptz default now())
- RLS on events table scoped by domain_id (users see only their domain's events)
- Index on (domain_id, created_at) for efficient domain-scoped queries
- No DELETE allowed — append-only by design (no DELETE grant on role)

### Auth implementation
- Argon2id via `pwdlib[argon2]` (FastAPI recommended)
- JWT via `pyjwt` with RS256 (asymmetric — public key can verify without secret)
- Access token: 15 min, contains user_id + email
- Refresh token: 7 days, stored hashed in DB, httpOnly SameSite=Strict cookie
- Token refresh: issues new access + rotates refresh token (old one invalidated)
- Rate limiting: `slowapi` on login endpoint (5/min per IP)
- Password reset: random token (secrets.token_urlsafe), hashed in DB, 1 hour expiry

### FastAPI skeleton
- Project structure: `src/` with `api/`, `core/`, `models/`, `services/`, `middleware/`
- SQLAlchemy 2.0 async (asyncpg driver) — declarative models
- Alembic for migrations
- Pydantic v2 for request/response schemas
- Dependency injection via FastAPI Depends
- CORS middleware configured for frontend origin
- Health check endpoint: GET /health

### Claude's Discretion
- Exact project directory structure within src/
- Alembic migration naming conventions
- Pydantic model organization
- Error response format standardization
- Test framework choice (pytest assumed)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project context
- `.planning/PROJECT.md` — Full project vision, constraints, tech stack decisions
- `.planning/REQUIREMENTS.md` — AUTH-01 through AUTH-04, AUD-01 requirements with acceptance criteria
- `.planning/research/STACK.md` — Validated library versions, rationale for each choice
- `.planning/research/ARCHITECTURE.md` — Component boundaries, data flow, RLS patterns
- `.planning/research/PITFALLS.md` — RLS footguns, auth security risks, hardcode prevention

### Concept
- `CONCEPT.md` — Full 610-line product concept with architecture diagrams, security model, deployment topology

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project, no existing code

### Established Patterns
- None — this phase establishes the foundational patterns

### Integration Points
- Docker Compose defines the network topology for all subsequent phases
- PostgreSQL schema (users, domains, events) is the foundation for Phases 2-6
- FastAPI skeleton (middleware, auth deps) is extended by all subsequent phases
- RLS policies set in this phase protect all future tables

</code_context>

<specifics>
## Specific Ideas

- PostgreSQL image: use `pgvector/pgvector:pg16` from the start (pgvector extension pre-installed for Phase 3)
- Redis image: `redis:7-alpine` (lightweight, sufficient for TaskIQ broker + pub/sub)
- Use `asyncpg` connection pool with separate roles: `app_user` (RLS-enabled) and `app_admin` (migrations, bypasses RLS)
- Create `domains` table in Phase 1 schema even though CRUD is Phase 2 — RLS policies reference it
- Events table partitioning: create initial partition + pg_partman extension for automatic monthly partition creation

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-03-27*
