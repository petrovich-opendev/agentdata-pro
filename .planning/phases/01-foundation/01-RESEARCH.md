# Phase 1: Foundation - Research

**Researched:** 2026-03-27
**Domain:** Docker Compose infrastructure, PostgreSQL RLS, JWT Auth (RS256 + Argon2id), FastAPI skeleton, audit event log
**Confidence:** HIGH

## Summary

Phase 1 establishes the entire runtime foundation: Docker Compose with PostgreSQL (pgvector image), Redis, Nginx, and FastAPI; a complete auth service with Argon2id password hashing, RS256 JWT tokens, refresh token rotation, rate limiting, and password reset via email; PostgreSQL schema with RLS policies for domain isolation; and an append-only partitioned audit event log.

The stack decisions from CONTEXT.md are well-validated. pwdlib v0.3.0 with argon2 extra is the FastAPI-recommended password hashing library (replaces deprecated passlib). PyJWT v2.12.1 with cryptography backend handles RS256 asymmetric signing. SQLAlchemy 2.0 async with asyncpg is the standard ORM path. The pgvector/pgvector:pg16 Docker image does NOT include pg_partman -- a custom Dockerfile extending it is required.

**Primary recommendation:** Build in three waves: (1) Docker Compose + DB schema + FastAPI skeleton, (2) Auth service with all endpoints, (3) RLS policies + domain context middleware + audit log. Each wave is independently testable.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Argon2id via `pwdlib[argon2]` (FastAPI recommended)
- JWT via `pyjwt` with RS256 (asymmetric -- public key can verify without secret)
- Access token: 15 min, contains user_id + email
- Refresh token: 7 days, stored hashed in DB, httpOnly SameSite=Strict cookie
- Token refresh: issues new access + rotates refresh token (old one invalidated)
- Rate limiting: `slowapi` on login endpoint (5/min per IP)
- Password reset: random token (secrets.token_urlsafe), hashed in DB, 1 hour expiry
- SQLAlchemy 2.0 async (asyncpg driver) -- declarative models
- Alembic for migrations
- SET LOCAL for RLS context injection (transaction-scoped)
- aiosmtplib for email (dev mode: log to console)
- Events table partitioned by month (pg_partman)
- pgvector/pgvector:pg16 Docker image (pgvector pre-installed for Phase 3)
- Docker Compose: nginx, api, postgres, redis -- internal network, only nginx exposes 80/443
- Two DB roles: `app_user` (RLS-enabled) and `app_admin` (migrations, bypasses RLS)
- Pydantic v2 for request/response schemas
- CORS middleware configured for frontend origin
- Health check endpoint: GET /health
- FastAPI project structure: `src/` with `api/`, `core/`, `models/`, `services/`, `middleware/`

### Claude's Discretion
- Exact project directory structure within src/
- Alembic migration naming conventions
- Pydantic model organization
- Error response format standardization
- Test framework choice (pytest assumed)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUTH-01 | User can register with email and password (Argon2id) | pwdlib[argon2] v0.3.0 handles hashing; SQLAlchemy users table with email unique constraint; Pydantic v2 with email-validator for input validation |
| AUTH-02 | User can login and stay logged in (JWT access 15min + refresh 7d httpOnly) | PyJWT v2.12.1 with RS256; cryptography lib for key generation; refresh token rotation pattern with DB storage |
| AUTH-03 | User can reset password via email | aiosmtplib v5.1.0 for async SMTP; secrets.token_urlsafe for token generation; hash token in DB with 1h expiry |
| AUTH-04 | Login endpoint protected by rate limiting (5 attempts/min per IP) | slowapi v0.1.9 wraps limits library; decorator-based, works with FastAPI |
| AUD-01 | Every user and agent action recorded in append-only events table (partitioned by month) | pg_partman extension for auto-partition management; custom Dockerfile needed; NO DELETE grant on app_user role |
</phase_requirements>

## Standard Stack

### Core (Phase 1 specific)

| Library | Version | Purpose | Why Standard | Confidence |
|---------|---------|---------|--------------|------------|
| FastAPI | ~0.128.0 | API framework | Async-native, Pydantic integration, production-proven | HIGH |
| Pydantic | ~2.12.5 | Validation/serialization | Native FastAPI integration, typed models | HIGH |
| Uvicorn | latest | ASGI server | Standard FastAPI deployment | HIGH |
| SQLAlchemy | ~2.0.48 | Async ORM | Mature async via asyncpg, Alembic compat | HIGH |
| asyncpg | ~3.2.1 | Async PG driver | Fastest Python PG driver, native async | HIGH |
| Alembic | ~1.18.4 | Schema migrations | SQLAlchemy native, autogenerate support | HIGH |
| pwdlib | ~0.3.0 | Password hashing | FastAPI-recommended replacement for passlib, Argon2id support | HIGH |
| PyJWT | ~2.12.1 | JWT tokens | Standard, well-maintained, RS256 via cryptography backend | HIGH |
| cryptography | latest | RSA key operations | Required by PyJWT for RS256 algorithm | HIGH |
| slowapi | ~0.1.9 | Rate limiting | Flask-limiter port for Starlette/FastAPI, decorator-based | HIGH |
| aiosmtplib | ~5.1.0 | Async SMTP client | Pure async, works with any SMTP provider | HIGH |
| redis[hiredis] | latest | Async Redis client | Session management, future TaskIQ broker | HIGH |
| email-validator | latest | Email validation | Required by Pydantic for EmailStr type | HIGH |
| python-dotenv | latest | Env vars | Local development .env loading | HIGH |
| structlog | latest | Structured logging | JSON logs for production, context-rich tracing | HIGH |
| orjson | latest | Fast JSON | 3-10x faster serialization, drop-in for FastAPI | HIGH |

### Infrastructure

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|------------|
| PostgreSQL | 16 | Primary database (via pgvector image) | HIGH |
| pgvector | 0.8.2 | Pre-installed in Docker image for Phase 3 | HIGH |
| pg_partman | latest | Events table auto-partitioning (installed via custom Dockerfile) | HIGH |
| Redis | 7-alpine | Session state, future broker/pub-sub | HIGH |
| Nginx | latest stable | Reverse proxy, SSL termination | HIGH |
| Docker Compose | v2 | Container orchestration | HIGH |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pwdlib[argon2] | argon2-cffi directly | pwdlib adds hash verification, upgrade detection; argon2-cffi is lower-level |
| PyJWT + RS256 | PyJWT + HS256 | HS256 simpler (shared secret), but RS256 allows public key verification without secret exposure |
| slowapi | fastapi-limiter | fastapi-limiter requires Redis; slowapi works in-memory too, simpler for Phase 1 |
| pg_partman | Manual partitioning | pg_partman auto-creates monthly partitions, handles maintenance; manual requires cron job |
| Custom Dockerfile | pgvector/pgvector:pg16 as-is | pgvector image lacks pg_partman; custom Dockerfile adds it with apt-get |

**Installation:**

```bash
# Core
pip install "fastapi[standard]" "uvicorn[standard]" "pydantic~=2.12"

# Database
pip install "sqlalchemy~=2.0.48" "asyncpg~=3.2" "alembic~=1.18"

# Auth
pip install "pwdlib[argon2]~=0.3" "pyjwt[crypto]~=2.12" "slowapi~=0.1"

# Email
pip install "aiosmtplib~=5.1"

# Redis
pip install "redis[hiredis]"

# Utilities
pip install structlog orjson python-dotenv email-validator python-multipart
```

## Architecture Patterns

### Recommended Project Structure

```
src/
  api/
    __init__.py
    deps.py              # FastAPI dependency injection (get_db, get_current_user)
    v1/
      __init__.py
      auth.py            # POST /auth/register, /auth/login, /auth/refresh, /auth/logout, /auth/password-reset
      health.py          # GET /health
  core/
    __init__.py
    config.py            # Pydantic BaseSettings — all env vars
    security.py          # JWT encode/decode, password hashing, token generation
    database.py          # SQLAlchemy engine, session factory, both roles
  models/
    __init__.py
    base.py              # SQLAlchemy declarative base, common mixins
    user.py              # User model
    domain.py            # Domain model (created in Phase 1, CRUD in Phase 2)
    event.py             # Event model (partitioned)
    refresh_token.py     # RefreshToken model
    password_reset.py    # PasswordResetToken model
  schemas/
    __init__.py
    auth.py              # Pydantic schemas for auth requests/responses
    common.py            # Common response schemas (ErrorResponse, etc.)
  services/
    __init__.py
    auth.py              # Auth business logic
    email.py             # Email sending (SMTP or console in dev)
    event.py             # Event logging service
  middleware/
    __init__.py
    domain_context.py    # SET LOCAL app.current_domain_id
    error_handler.py     # Global exception handlers
  main.py                # FastAPI app factory, middleware registration
alembic/
  env.py
  versions/
docker/
  postgres/
    Dockerfile           # FROM pgvector/pgvector:pg16, install pg_partman
    init.sql             # Create roles, extensions, initial schema
  nginx/
    nginx.conf
docker-compose.yml
.env.example
requirements.txt
pytest.ini
tests/
  conftest.py
  test_auth.py
  test_rls.py
  test_events.py
```

### Pattern 1: Two Database Roles (app_user vs app_admin)

**What:** Two PostgreSQL connection pools -- one with RLS-enabled role for application queries, one with admin role for migrations and schema operations.

**When:** Always. Every request uses `app_user`. Only Alembic migrations use `app_admin`.

**Example:**

```python
# core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# RLS-enabled connection pool (used by all application code)
app_engine = create_async_engine(
    settings.database_url_app_user,  # postgresql+asyncpg://app_user:pass@postgres/agentdata
    pool_size=20,
    max_overflow=10,
)
AppSession = async_sessionmaker(app_engine, expire_on_commit=False)

# Admin connection (used only by Alembic migrations)
admin_engine = create_async_engine(
    settings.database_url_admin,  # postgresql+asyncpg://app_admin:pass@postgres/agentdata
    pool_size=2,
    max_overflow=0,
)
```

```sql
-- init.sql (run on first PostgreSQL startup)
CREATE ROLE app_user LOGIN PASSWORD 'from_env';
CREATE ROLE app_admin LOGIN PASSWORD 'from_env' SUPERUSER;

-- app_user can SELECT, INSERT, UPDATE on all tables but NOT DELETE on events
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
REVOKE DELETE ON events FROM app_user;  -- append-only

-- Enable RLS (app_user sees only their domain's data)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE domains ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;

-- FORCE RLS even for table owner
ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE domains FORCE ROW LEVEL SECURITY;
ALTER TABLE events FORCE ROW LEVEL SECURITY;
```

### Pattern 2: RS256 JWT Key Pair Management

**What:** Generate RSA key pair at first startup, store in volume-mounted directory. Private key signs tokens, public key verifies them.

**When:** Application startup. Keys persisted across restarts.

**Example:**

```python
# core/security.py
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt
from pathlib import Path

def load_or_generate_rsa_keys(key_dir: Path) -> tuple[bytes, bytes]:
    """Load existing RSA keys or generate new pair."""
    private_key_path = key_dir / "jwt_private.pem"
    public_key_path = key_dir / "jwt_public.pem"

    if private_key_path.exists() and public_key_path.exists():
        private_key = private_key_path.read_bytes()
        public_key = public_key_path.read_bytes()
        return private_key, public_key

    # Generate new 2048-bit RSA key pair
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_key_path.write_bytes(private_key)
    public_key_path.write_bytes(public_key)
    return private_key, public_key

def create_access_token(user_id: str, email: str, private_key: bytes) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(minutes=15),
        "iat": datetime.utcnow(),
        "type": "access",
    }
    return jwt.encode(payload, private_key, algorithm="RS256")

def verify_access_token(token: str, public_key: bytes) -> dict:
    return jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],  # CRITICAL: pin algorithm, never accept alg:none
        options={"require": ["exp", "sub", "email", "type"]},
    )
```

**Source:** [PyJWT RS256 Documentation](https://pyjwt.readthedocs.io/en/stable/algorithms.html)

### Pattern 3: Refresh Token Rotation

**What:** Each refresh token use generates a new refresh token and invalidates the old one. Tokens stored hashed in DB.

**When:** POST /auth/refresh endpoint.

**Example:**

```python
# models/refresh_token.py
class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128))  # SHA-256 hash of token
    expires_at: Mapped[datetime] = mapped_column()
    revoked_at: Mapped[Optional[datetime]] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    replaced_by: Mapped[Optional[uuid.UUID]] = mapped_column(default=None)  # Token rotation chain

# services/auth.py
import hashlib
import secrets

async def create_refresh_token(session: AsyncSession, user_id: uuid.UUID) -> str:
    """Generate refresh token, store hash in DB, return raw token."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    db_token = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    session.add(db_token)
    await session.flush()
    return raw_token

async def rotate_refresh_token(session: AsyncSession, old_raw_token: str) -> tuple[str, str]:
    """Validate old token, revoke it, issue new pair."""
    old_hash = hashlib.sha256(old_raw_token.encode()).hexdigest()
    old_token = await session.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == old_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > func.now(),
        )
    )
    old_token = old_token.scalar_one_or_none()
    if not old_token:
        raise InvalidTokenError("Refresh token invalid or expired")

    # Revoke old token
    old_token.revoked_at = datetime.utcnow()

    # Issue new tokens
    new_raw = await create_refresh_token(session, old_token.user_id)
    old_token.replaced_by = new_raw  # chain tracking
    new_access = create_access_token(str(old_token.user_id), ...)

    return new_access, new_raw
```

### Pattern 4: Domain Context Middleware with SET LOCAL

**What:** Middleware injects domain_id into PostgreSQL session variable for RLS. Uses `SET LOCAL` which is transaction-scoped.

**When:** Every authenticated request that operates on domain-scoped data.

**Critical:** In Phase 1, this middleware is CREATED but domain_id extraction is minimal (no domains yet). Phase 2 activates it with actual domain resolution from request headers/path.

**Example:**

```python
# middleware/domain_context.py
from sqlalchemy import text

async def domain_context_middleware(request: Request, call_next):
    """Set RLS context for domain-scoped queries."""
    domain_id = request.headers.get("X-Domain-ID")

    if domain_id:
        # Validate UUID format to prevent injection
        try:
            uuid.UUID(domain_id)
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid domain ID"})

        async with request.state.db.begin():
            await request.state.db.execute(
                text("SET LOCAL app.current_domain_id = :did"),
                {"did": domain_id},
            )

    response = await call_next(request)
    return response
```

### Pattern 5: Events Table with Monthly Partitioning

**What:** Append-only events table partitioned by `created_at` month. pg_partman creates new partitions automatically.

**When:** Phase 1 schema setup.

**Example:**

```sql
-- Alembic migration: create partitioned events table
CREATE TABLE events (
    id BIGSERIAL,
    event_id UUID NOT NULL DEFAULT gen_random_uuid(),
    actor_id UUID NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('user', 'agent', 'system')),
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id UUID,
    domain_id UUID,
    payload JSONB DEFAULT '{}',
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)  -- partition key must be in PK
) PARTITION BY RANGE (created_at);

-- Enable RLS
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE events FORCE ROW LEVEL SECURITY;

CREATE POLICY events_domain_isolation ON events
    USING (domain_id = current_setting('app.current_domain_id', true)::uuid)
    WITH CHECK (domain_id = current_setting('app.current_domain_id', true)::uuid);

-- Index for domain-scoped time queries
CREATE INDEX idx_events_domain_created ON events (domain_id, created_at);

-- Unique constraint on event_id (across partitions)
CREATE UNIQUE INDEX idx_events_event_id ON events (event_id, created_at);

-- pg_partman: auto-create monthly partitions
SELECT partman.create_parent(
    p_parent_table := 'public.events',
    p_control := 'created_at',
    p_interval := '1 month',
    p_premake := 3  -- create 3 months ahead
);
```

**IMPORTANT:** The `current_setting()` call uses the `true` second parameter (missing_ok) so it returns NULL instead of erroring when no domain context is set. This allows system-level events (actor_type='system') to be logged without a domain context.

### Anti-Patterns to Avoid

- **Testing with superuser:** NEVER run application tests with the `app_admin` role. All tests must use `app_user` to verify RLS works.
- **Storing raw refresh tokens:** Always hash with SHA-256 before storing. Raw token exists only in the httpOnly cookie.
- **Accepting `alg:none` in JWT:** ALWAYS pin `algorithms=["RS256"]` in every `jwt.decode()` call.
- **Connection-scoped SET:** Use `SET LOCAL` (transaction-scoped), NEVER plain `SET` which persists across the connection pool.
- **Hardcoding SMTP credentials:** All SMTP config from env vars. Dev mode uses console logging, not a hardcoded test server.
- **Skip `FORCE ROW LEVEL SECURITY`:** Without this, the table owner bypasses RLS. Always add it.
- **DELETE on events table:** The `app_user` role must NOT have DELETE permission on events. This is enforced at the grant level.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Password hashing | Custom Argon2id wrapper | pwdlib[argon2] | Handles hash verification, cost upgrades, timing-safe comparison |
| JWT creation/verification | Manual JSON + HMAC | PyJWT with RS256 | Algorithm pinning, claim validation, key format handling |
| Rate limiting | Custom counter in Redis | slowapi | Handles sliding windows, IP extraction behind proxies, 429 responses |
| Table partitioning | Manual partition creation + cron | pg_partman | Auto-creates partitions, handles retention, maintains indexes |
| Email sending | raw socket SMTP | aiosmtplib | Handles TLS, authentication, connection pooling, error recovery |
| Input validation | Manual regex/if checks | Pydantic v2 | Type coercion, nested validation, error formatting, OpenAPI schema |
| DB migrations | Raw SQL scripts | Alembic | Version tracking, rollback, autogenerate from models |

**Key insight:** Auth is deceptively complex. Every "simple" JWT implementation has at least 3 security holes. Use the libraries exactly as documented -- they exist to prevent known attack vectors.

## Common Pitfalls

### Pitfall 1: pgvector Docker Image Lacks pg_partman

**What goes wrong:** Using `pgvector/pgvector:pg16` as-is -- the events table partitioning fails because pg_partman is not installed.

**Why it happens:** The pgvector image extends the official postgres:16 image and only adds the pgvector extension. pg_partman must be installed separately.

**How to avoid:** Create a custom Dockerfile:

```dockerfile
FROM pgvector/pgvector:pg16
RUN apt-get update && apt-get install -y postgresql-16-partman && rm -rf /var/lib/apt/lists/*
```

**Confidence:** HIGH

### Pitfall 2: RLS Policy with Non-LEAKPROOF Function

**What goes wrong:** `current_setting()` is not marked LEAKPROOF by default. The query planner cannot push RLS predicates through it, causing sequential scans on large tables.

**How to avoid:** Create a LEAKPROOF wrapper function:

```sql
CREATE OR REPLACE FUNCTION app_current_domain_id()
RETURNS uuid
LANGUAGE sql
STABLE
LEAKPROOF
AS $$ SELECT current_setting('app.current_domain_id', true)::uuid $$;

-- Use in RLS policies
CREATE POLICY domain_isolation ON events
    USING (domain_id = app_current_domain_id());
```

**Warning signs:** EXPLAIN ANALYZE shows sequential scans on domain_id-indexed tables.

**Confidence:** HIGH -- [documented optimization](https://scottpierce.dev/posts/optimizing-postgres-rls/)

### Pitfall 3: RS256 Key Not Persisted Across Container Restarts

**What goes wrong:** RSA key pair generated at startup is stored in container filesystem. Container restart generates new keys, invalidating all existing tokens. All users forced to re-login.

**How to avoid:** Mount key directory as Docker volume: `./keys:/app/keys`. Generate keys only if files don't exist.

**Confidence:** HIGH

### Pitfall 4: Refresh Token Reuse Detection Missing

**What goes wrong:** Attacker steals a refresh token, uses it. Legitimate user also uses it. Both get new tokens. Attacker maintains access indefinitely.

**How to avoid:** Track token chain via `replaced_by` field. If a revoked token is presented, revoke ALL tokens in the chain (entire token family) -- this is a token theft signal.

**Confidence:** HIGH -- [OWASP recommendation](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)

### Pitfall 5: slowapi Behind Nginx Counts Nginx IP, Not Client IP

**What goes wrong:** All requests appear to come from the Docker internal network IP (e.g., 172.18.0.1) because Nginx proxies them. Rate limiting treats all users as one.

**How to avoid:** Configure Nginx to pass `X-Real-IP` / `X-Forwarded-For`, and configure slowapi to read from these headers:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

# Use X-Forwarded-For behind trusted proxy
limiter = Limiter(key_func=get_remote_address)
```

Also configure FastAPI to trust the proxy: `app.add_middleware(TrustedHostMiddleware, ...)`

**Confidence:** HIGH

### Pitfall 6: Alembic Async Engine Configuration

**What goes wrong:** Default Alembic `env.py` uses synchronous engine. Async SQLAlchemy models fail to autogenerate migrations.

**How to avoid:** Configure Alembic with `run_async()` pattern:

```python
# alembic/env.py
from sqlalchemy.ext.asyncio import async_engine_from_config

async def run_async_migrations():
    connectable = async_engine_from_config(config.get_section("alembic"), ...)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

asyncio.run(run_async_migrations())
```

**Confidence:** HIGH -- standard pattern, documented in SQLAlchemy docs.

## Code Examples

### Docker Compose Configuration

```yaml
# docker-compose.yml
services:
  postgres:
    build:
      context: ./docker/postgres
    environment:
      POSTGRES_DB: agentdata
      POSTGRES_USER: app_admin
      POSTGRES_PASSWORD: ${POSTGRES_ADMIN_PASSWORD}
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./docker/postgres/init.sql:/docker-entrypoint-initdb.d/01-init.sql
    networks:
      - internal
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    networks:
      - internal
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"

  api:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      DATABASE_URL_APP: postgresql+asyncpg://app_user:${POSTGRES_APP_PASSWORD}@postgres:5432/agentdata
      DATABASE_URL_ADMIN: postgresql+asyncpg://app_admin:${POSTGRES_ADMIN_PASSWORD}@postgres:5432/agentdata
      REDIS_URL: redis://redis:6379/0
      JWT_KEY_DIR: /app/keys
      SMTP_HOST: ${SMTP_HOST}
      SMTP_PORT: ${SMTP_PORT:-587}
      SMTP_USER: ${SMTP_USER}
      SMTP_PASSWORD: ${SMTP_PASSWORD}
      SMTP_DEV: ${SMTP_DEV:-true}
      CORS_ORIGINS: ${CORS_ORIGINS:-http://localhost:3000}
    volumes:
      - jwt_keys:/app/keys
    depends_on:
      - postgres
      - redis
    networks:
      - internal
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"

  nginx:
    image: nginx:stable-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./docker/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - api
    networks:
      - internal
    restart: unless-stopped

volumes:
  pg_data:
  redis_data:
  jwt_keys:

networks:
  internal:
    driver: bridge
```

### PostgreSQL Init Script (Roles + Extensions)

```sql
-- docker/postgres/init.sql
-- Run as superuser (POSTGRES_USER=app_admin)

-- Create application role with RLS
CREATE ROLE app_user LOGIN PASSWORD 'PLACEHOLDER_FROM_ENV';

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;  -- pgvector, pre-installed
CREATE SCHEMA IF NOT EXISTS partman;
CREATE EXTENSION IF NOT EXISTS pg_partman SCHEMA partman;

-- Grant schema usage
GRANT USAGE ON SCHEMA public TO app_user;
GRANT USAGE ON SCHEMA partman TO app_user;
```

### Error Response Format (Claude's Discretion)

```python
# schemas/common.py
from pydantic import BaseModel

class ErrorResponse(BaseModel):
    """Standardized error response."""
    detail: str
    code: str  # machine-readable error code, e.g. "auth.invalid_credentials"

class ErrorDetail(BaseModel):
    """Validation error detail."""
    field: str
    message: str

class ValidationErrorResponse(BaseModel):
    """422 response with field-level errors."""
    detail: str
    code: str = "validation_error"
    errors: list[ErrorDetail]
```

### Pydantic Settings Configuration

```python
# core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url_app: str  # postgresql+asyncpg://app_user:...
    database_url_admin: str  # postgresql+asyncpg://app_admin:...

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # JWT
    jwt_key_dir: str = "/app/keys"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # SMTP
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_dev: bool = True  # True = log to console instead of sending

    # CORS
    cors_origins: str = "http://localhost:3000"

    # App
    app_name: str = "AgentData.pro"
    debug: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| passlib for password hashing | pwdlib (passlib successor) | 2024-2025 | passlib broken on Python 3.13+; pwdlib is drop-in replacement |
| python-jose for JWT | PyJWT | 2024 | python-jose unmaintained since 2022, security issues |
| bcrypt | Argon2id | PHC 2015, OWASP 2023 | Argon2id is memory-hard, GPU-resistant; bcrypt is not |
| SQLAlchemy 1.x sync | SQLAlchemy 2.0 async | 2023 | Native async, type annotations, modern API |
| Trigger-based partitioning | Declarative partitioning + pg_partman v5 | PostgreSQL 10+ | pg_partman 5.0+ only supports declarative; simpler, faster |
| HS256 JWT | RS256 JWT | Best practice | Asymmetric allows public key distribution without secret exposure |

## Open Questions

1. **pg_partman BGW (background worker) vs pg_cron for maintenance**
   - What we know: pg_partman includes a BGW that can auto-run maintenance. Alternatively, pg_cron can call `partman.run_maintenance_proc()`.
   - What's unclear: Whether BGW works reliably in Docker without special configuration.
   - Recommendation: Start with BGW configuration in postgresql.conf (`shared_preload_libraries = 'pg_partman_bgw'`). Fall back to calling maintenance manually in a FastAPI startup event if BGW is problematic.

2. **SMTP provider for production**
   - What we know: Dev mode logs to console. Production needs real SMTP.
   - What's unclear: Which provider will be used (Yandex Mail, Mailgun, etc.).
   - Recommendation: Keep SMTP_DEV=true for Phase 1. Provider choice is not blocking -- aiosmtplib works with any SMTP server.

3. **Nginx SSL in Phase 1**
   - What we know: Docker Compose exposes nginx on 80/443.
   - What's unclear: Whether Certbot/SSL is set up in Phase 1 or deferred.
   - Recommendation: Phase 1 HTTP only (localhost development). SSL setup is infrastructure, not application code.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio + httpx (for async FastAPI testing) |
| Config file | pytest.ini (Wave 0) |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v --tb=short` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | Register with email+password, Argon2id hash stored | integration | `pytest tests/test_auth.py::test_register -x` | Wave 0 |
| AUTH-01 | Reject duplicate email registration | integration | `pytest tests/test_auth.py::test_register_duplicate -x` | Wave 0 |
| AUTH-01 | Reject weak password / invalid email | unit | `pytest tests/test_auth.py::test_register_validation -x` | Wave 0 |
| AUTH-02 | Login returns access token + sets refresh cookie | integration | `pytest tests/test_auth.py::test_login -x` | Wave 0 |
| AUTH-02 | Refresh rotates tokens, old token invalidated | integration | `pytest tests/test_auth.py::test_token_refresh -x` | Wave 0 |
| AUTH-02 | Reject expired/invalid access token | unit | `pytest tests/test_auth.py::test_invalid_token -x` | Wave 0 |
| AUTH-02 | Pin RS256 algorithm, reject alg:none | unit | `pytest tests/test_auth.py::test_algorithm_pinning -x` | Wave 0 |
| AUTH-03 | Password reset sends email (or logs in dev mode) | integration | `pytest tests/test_auth.py::test_password_reset_request -x` | Wave 0 |
| AUTH-03 | Valid reset token allows password change | integration | `pytest tests/test_auth.py::test_password_reset_complete -x` | Wave 0 |
| AUTH-03 | Expired reset token rejected | unit | `pytest tests/test_auth.py::test_password_reset_expired -x` | Wave 0 |
| AUTH-04 | 6th login attempt within 1 min returns 429 | integration | `pytest tests/test_auth.py::test_rate_limiting -x` | Wave 0 |
| AUD-01 | Auth actions create events in events table | integration | `pytest tests/test_events.py::test_auth_events_logged -x` | Wave 0 |
| AUD-01 | Events table is append-only (DELETE rejected) | integration | `pytest tests/test_events.py::test_events_no_delete -x` | Wave 0 |
| RLS | Cross-domain query returns empty (not other domain's data) | integration | `pytest tests/test_rls.py::test_domain_isolation -x` | Wave 0 |
| RLS | SET LOCAL does not leak across connections | integration | `pytest tests/test_rls.py::test_set_local_isolation -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/ -x -q` (< 30 seconds)
- **Per wave merge:** `pytest tests/ -v --tb=short`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/conftest.py` -- shared fixtures: test DB, async session, test client, user factory
- [ ] `tests/test_auth.py` -- all AUTH-01 through AUTH-04 tests
- [ ] `tests/test_events.py` -- AUD-01 tests
- [ ] `tests/test_rls.py` -- RLS isolation tests
- [ ] `pytest.ini` -- asyncio mode=auto, test DB URL
- [ ] Framework install: `pip install pytest pytest-asyncio httpx`

## Sources

### Primary (HIGH confidence)
- [pwdlib PyPI](https://pypi.org/project/pwdlib/) -- v0.3.0, Oct 2025, Argon2id support confirmed
- [PyJWT Digital Signature Algorithms](https://pyjwt.readthedocs.io/en/stable/algorithms.html) -- RS256 with cryptography backend
- [PyJWT Usage Examples](https://pyjwt.readthedocs.io/en/latest/usage.html) -- v2.12.1 confirmed
- [aiosmtplib Docs](https://aiosmtplib.readthedocs.io/) -- v5.1.0, Jan 2026
- [pg_partman GitHub](https://github.com/pgpartman/pg_partman) -- v5.x, declarative partitioning only
- [PostgreSQL RLS Documentation](https://www.postgresql.org/docs/16/ddl-rowsecurity.html) -- official PG16 docs
- [SQLAlchemy Async Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) -- v2.0 async patterns
- [Alembic Async Cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic) -- async engine configuration

### Secondary (MEDIUM confidence)
- [slowapi PyPI](https://pypi.org/project/slowapi/) -- v0.1.9, Feb 2024 (last release somewhat old but stable)
- [Scott Pierce: Optimizing Postgres RLS](https://scottpierce.dev/posts/optimizing-postgres-rls/) -- LEAKPROOF optimization
- [Bytebase: RLS Footguns](https://www.bytebase.com/blog/postgres-row-level-security-footguns/) -- FORCE ROW LEVEL SECURITY

### Tertiary (LOW confidence)
- pgvector/pgvector:pg16 extension availability -- verified that pg_partman is NOT included by default (needs custom Dockerfile); LOW confidence on exact apt package name -- may need `postgresql-16-partman` or `postgresql-16-pg-partman`

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries verified on PyPI with current versions
- Architecture: HIGH -- patterns from official docs and project research phase
- Pitfalls: HIGH -- RLS and JWT pitfalls well-documented by multiple authoritative sources
- Validation: HIGH -- test structure follows standard pytest-asyncio + httpx patterns

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (stable libraries, no major releases expected)
