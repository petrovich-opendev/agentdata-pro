# Technology Stack

**Project:** AgentData.pro
**Researched:** 2026-03-27
**Overall confidence:** HIGH

## Stack Validation Summary

The chosen stack is **well-validated** for this project scope (10-70 users, multi-agent AI workspace). All major decisions are sound. Below are specific versions, missing components identified during research, and corrections.

---

## Recommended Stack

### Core Backend

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | 3.12 | Runtime | Stable, all AI libs support it, async mature | HIGH |
| FastAPI | ~0.128.0 | API server | Async-native, Pydantic integration, SSE support, production-proven | HIGH |
| Pydantic | ~2.12.5 | Validation/serialization | Native FastAPI integration, typed models, JSON Schema generation | HIGH |
| Uvicorn | latest | ASGI server | Standard FastAPI deployment, production-grade with gunicorn wrapper | HIGH |

### Database

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| PostgreSQL | 16 | Primary database | JSONB + RLS + LTREE in one DB, proven at this scale | HIGH |
| pgvector | 0.8.2 | Vector similarity search | Native PG extension, no separate vector DB needed for 70 users | HIGH |
| SQLAlchemy | ~2.0.48 | ORM + async | Mature async support via asyncpg, type-safe queries, Alembic compat | HIGH |
| asyncpg | ~3.2.1 | Async PG driver | Fastest Python PG driver, native async, connection pooling | HIGH |
| Alembic | ~1.18.4 | Schema migrations | SQLAlchemy native, autogenerate support, production standard | HIGH |

### Task Queue & Scheduling

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| TaskIQ | ~0.12.1 | Async task queue | Async-native (unlike Celery), FastAPI integration, typed tasks | MEDIUM |
| taskiq-redis | latest | Redis broker for TaskIQ | Production-stable, dynamic scheduling support | MEDIUM |
| Redis | 7.x | Broker + pub/sub + Streams | Task broker, WebSocket event bus, event replay (Streams TTL 24h) | HIGH |

**Note on TaskIQ scheduling:** TaskIQ has its own `TaskiqScheduler` with `LabelScheduleSource` (static cron) and `ListRedisScheduleSource` (dynamic, runtime-configurable). APScheduler is NOT needed -- TaskIQ handles cron natively. Use `ListRedisScheduleSource` for agent schedules that users can modify at runtime.

### Telegram

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| aiogram | ~3.26.0 | Telegram Bot API | Fully async, webhook mode, active development, Python 3.10+ | HIGH |

### Auth & Security

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| PyJWT | ~2.12.1 | JWT tokens | Standard, well-maintained, no bloat | HIGH |
| argon2-cffi | ~25.1.0 | Password hashing | Argon2id (PHC winner), memory-hard, GPU-resistant, MIT license | HIGH |

### LLM Integration

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| openai (SDK) | ~2.30.0 | OpenAI API client | Also works with Ollama's OpenAI-compatible endpoint, typed responses | HIGH |
| httpx | ~0.28.1 | Async HTTP client | For custom LLM router, health checks, external API calls | HIGH |

**LLM Router approach:** Custom Python (~50 lines) using `openai` SDK with configurable `base_url`. Ollama exposes `/v1/chat/completions` -- same SDK, different URL. This is correct and simpler than any proxy library.

**LiteLLM status:** CONFIRMED COMPROMISED (March 24, 2026). Supply chain attack via TeamPCP -- credential-stealing malware in versions 1.82.7-1.82.8. Releases paused. Decision to avoid LiteLLM is correct and well-timed.

### Git-Versioned Memory

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| dulwich | ~1.1.0 | Pure-Python Git | No system git dependency, programmatic commits/diffs, Apache 2.0 | MEDIUM |

**Why dulwich over GitPython:** GitPython is in maintenance mode (no new features, slow bug fixes) and requires system git binary. Dulwich is pure Python, actively maintained, and works in Docker without git installation. For programmatic git operations (commit agent memory files, read diffs), dulwich is the right choice.

### Frontend

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| React | 19.x | UI framework | Latest stable, concurrent features, hooks mature | HIGH |
| TypeScript | ~5.7 | Type safety | Strict mode, satisfies operator, decorators | HIGH |
| Vite | ~6.x | Build tool | Fast HMR, ESM-native, shadcn/ui scaffolding support | HIGH |
| Tailwind CSS | 4.x | Utility CSS | CSS-first config, 5x faster builds, no JS config file needed | HIGH |
| shadcn/ui | CLI v4 (March 2026) | Component library | Code-owned components, Vite scaffold support, unified radix-ui package | HIGH |
| TanStack Router | ~1.168.x | Routing | Typesafe routes, file-based routing, search params as first-class | HIGH |
| TanStack Query | ~5.95.x | Server state | Cache invalidation via WebSocket events, optimistic updates, suspense | HIGH |
| Zustand | ~5.0.x | Client state | 1.5 kB, minimal API, middleware (persist, devtools) | HIGH |
| React Hook Form | ~7.x (stable) | Form management | Uncontrolled inputs (performance), Zod resolver | HIGH |
| Zod | ~4.x | Schema validation | Mirrors Pydantic schemas, TypeScript-first, Standard Schema support | HIGH |
| @hookform/resolvers | ~5.2.x | RHF + Zod bridge | Connects validation to forms | HIGH |

**Note on React Hook Form v8:** v8 is in beta (v8.0.0-beta.1, Jan 2026). Do NOT use it yet -- stick with v7 stable. Migrate when v8 reaches stable.

### Frontend: Markdown & Syntax Highlighting

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| react-markdown | latest | Render agent output | Standard React markdown renderer, rehype/remark plugins | HIGH |
| react-shiki | latest | Syntax highlighting | Shiki-powered, performs better than highlight.js, theme support | MEDIUM |
| Native WebSocket | N/A | Real-time | 0 kB bundle, bidirectional, TanStack Query invalidation on events | HIGH |

### Infrastructure

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Docker Compose | v2 | Container orchestration | Single-file deployment, auto-restart, sufficient for 70 users | HIGH |
| Nginx | latest stable | Reverse proxy + static | SSL termination, rate limiting, static React files | HIGH |
| Certbot | latest | SSL certificates | Auto-renewal with nginx plugin | HIGH |
| Cloudflare | Free tier | CDN + DDoS | Hides real IP, WAF, DNS | HIGH |
| WireGuard | latest | Admin VPN | SSH access only via VPN | HIGH |

### Monitoring

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Netdata | latest | System monitoring | Real-time metrics, low overhead, Telegram alerts | HIGH |
| Uptime Kuma | latest | Uptime monitoring | Self-hosted, Telegram notifications, status page | HIGH |

---

## Missing Components Identified

These are NOT in the current stack definition but are REQUIRED for the described functionality.

### Backend: Required Additions

| Library | Version | Purpose | Why Needed |
|---------|---------|---------|------------|
| websockets | latest | WebSocket server | FastAPI WebSocket support for real-time events to React UI |
| redis[hiredis] (aioredis) | latest | Async Redis client | Redis Streams for event replay, pub/sub for WebSocket fan-out |
| python-multipart | latest | Form data parsing | Required by FastAPI for file uploads (agent memory files) |
| structlog | latest | Structured logging | JSON logs for production, context-rich agent operation tracing |
| tenacity | latest | Retry logic | LLM API calls need retry with exponential backoff |

### Backend: Recommended Additions

| Library | Version | Purpose | Why Helpful |
|---------|---------|---------|-------------|
| orjson | latest | Fast JSON | 3-10x faster JSON serialization, drop-in for FastAPI response |
| python-dotenv | latest | Env vars | Local development .env loading |
| email-validator | latest | Email validation | Required by Pydantic for EmailStr type (user registration) |

### Frontend: Recommended Additions

| Library | Version | Purpose | Why Helpful |
|---------|---------|---------|-------------|
| date-fns | latest | Date formatting | Lightweight, tree-shakeable (vs dayjs/moment) |
| lucide-react | latest | Icons | Default shadcn/ui icon set, tree-shakeable |
| sonner | latest | Toast notifications | shadcn/ui default toast, agent completion alerts |
| recharts | latest | Charts | Weight trends, agent activity dashboards |
| cmdk | latest | Command palette | Quick domain/agent switching, ClickUp-like UX |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Task Queue | TaskIQ | Celery | Celery is sync-first, heavy, poor async support |
| Task Queue | TaskIQ | Dramatiq | No native async, smaller ecosystem than TaskIQ |
| Task Queue | TaskIQ | Temporal | Overkill for 70 users, complex ops, needed only at scale |
| Scheduling | TaskIQ Scheduler | APScheduler | Redundant -- TaskIQ has built-in scheduling with Redis source |
| LLM Proxy | Custom router | LiteLLM | Compromised (March 2026 supply chain attack), 800+ open issues |
| Password Hash | Argon2id | bcrypt | Not GPU-resistant, Argon2id is PHC winner and OWASP recommendation |
| Git Library | dulwich | GitPython | GitPython in maintenance mode, requires system git binary |
| ORM | SQLAlchemy 2 | Tortoise ORM | SQLAlchemy has larger ecosystem, Alembic migrations, better async |
| ORM | SQLAlchemy 2 | Raw asyncpg | SQLAlchemy provides migration tooling, model definitions, query builder |
| State Mgmt | Zustand | Redux Toolkit | Zustand is simpler, less boilerplate, sufficient for this scale |
| State Mgmt | Zustand | Jotai | Zustand better for global stores (auth, theme), Jotai better for atomic state |
| UI Kit | shadcn/ui | MUI | MUI bundles are large, theming is complex, code not owned |
| UI Kit | shadcn/ui | Ant Design | Enterprise-heavy, large bundle, Chinese documentation primary |
| Router | TanStack Router | React Router v7 | TanStack Router has superior type safety, search params handling |
| Vector DB | pgvector | Qdrant/Pinecone | Separate service unnecessary at 70 users, pgvector in same PG instance |
| Markdown | react-markdown | MDX | MDX is for content authoring, react-markdown for rendering agent output |

---

## Installation

### Backend

```bash
# Core
pip install fastapi[standard] uvicorn[standard] pydantic~=2.12

# Database
pip install sqlalchemy~=2.0.48 asyncpg~=3.2 alembic~=1.18 pgvector

# Task Queue
pip install taskiq~=0.12 taskiq-redis

# Auth
pip install pyjwt~=2.12 argon2-cffi~=25.1

# Telegram
pip install aiogram~=3.26

# LLM
pip install openai~=2.30 httpx~=0.28

# Git Memory
pip install dulwich~=1.1

# Utilities
pip install structlog tenacity orjson python-dotenv email-validator python-multipart

# Redis
pip install redis[hiredis]
```

### Frontend

```bash
# Init project
npx shadcn@latest init --template=vite

# Core (already included by shadcn init)
# react, react-dom, typescript, vite, tailwindcss v4

# State & Data
npm install @tanstack/react-router @tanstack/react-query zustand

# Forms
npm install react-hook-form @hookform/resolvers zod

# Markdown
npm install react-markdown react-shiki

# UI extras
npm install lucide-react sonner recharts cmdk date-fns

# Dev
npm install -D @tanstack/router-devtools @tanstack/react-query-devtools
```

---

## Version Pinning Strategy

Pin MINOR versions in requirements.txt/package.json for reproducible builds:

```
# Python: pin minor, allow patch
fastapi~=0.128
sqlalchemy~=2.0.48
pydantic~=2.12

# Node: pin minor
"@tanstack/react-query": "~5.95.0"
"@tanstack/react-router": "~1.168.0"
"zustand": "~5.0.0"
```

Update dependencies monthly. Run `pip-audit` and `npm audit` in CI.

---

## Key Architecture Notes

### TaskIQ replaces APScheduler

The CONCEPT.md mentions "APScheduler (via TaskIQ)" but this is misleading. TaskIQ has its own scheduler:

```python
# TaskIQ native scheduling -- no APScheduler needed
from taskiq import TaskiqScheduler
from taskiq_redis import ListRedisScheduleSource

scheduler = TaskiqScheduler(
    broker=redis_broker,
    sources=[ListRedisScheduleSource(redis_url)],  # Dynamic, user-configurable
)

@broker.task(schedule=[{"cron": "0 7 * * *"}])
async def morning_health_reminder(domain_id: str):
    ...
```

`ListRedisScheduleSource` supports adding/removing schedules at runtime via Redis -- perfect for user-configurable agent schedules.

### SQLAlchemy 2 async pattern

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/agentdata",
    pool_size=20,
    max_overflow=10,
)
async_session = async_sessionmaker(engine, expire_on_commit=False)
```

### Custom LLM Router pattern

```python
from openai import AsyncOpenAI

class LLMRouter:
    def __init__(self, ollama_url: str, openai_key: str):
        self.local = AsyncOpenAI(base_url=ollama_url, api_key="unused")
        self.cloud = AsyncOpenAI(api_key=openai_key)

    async def chat(self, messages: list, model: str = "qwen2.5:14b", force_cloud: bool = False):
        client = self.cloud if force_cloud else self.local
        try:
            return await client.chat.completions.create(model=model, messages=messages)
        except Exception:
            # Fallback to cloud
            return await self.cloud.chat.completions.create(model="gpt-4o-mini", messages=messages)
```

---

## Sources

- [FastAPI PyPI](https://pypi.org/project/fastapi/) -- v0.128.0 confirmed
- [FastAPI Release Notes](https://fastapi.tiangolo.com/release-notes/) -- SSE support, streaming
- [TaskIQ GitHub](https://github.com/taskiq-python/taskiq) -- v0.12.1, updated March 2026
- [TaskIQ Scheduling Docs](https://taskiq-python.github.io/guide/scheduling-tasks.html) -- native scheduler
- [aiogram Docs](https://docs.aiogram.dev/) -- v3.26.0
- [shadcn/ui Changelog](https://ui.shadcn.com/docs/changelog) -- CLI v4, Vite scaffold, unified radix-ui
- [TanStack Router](https://tanstack.com/router/latest) -- v1.168.x
- [TanStack Query](https://tanstack.com/query/latest) -- v5.95.x
- [Zustand GitHub](https://github.com/pmndrs/zustand) -- v5.0.12
- [Tailwind CSS v4](https://tailwindcss.com/blog/tailwindcss-v4) -- stable Jan 2025
- [pgvector Release](https://www.postgresql.org/about/news/pgvector-082-released-3245/) -- v0.8.2
- [SQLAlchemy PyPI](https://pypi.org/project/SQLAlchemy/) -- v2.0.48
- [Alembic Docs](https://alembic.sqlalchemy.org/) -- v1.18.4
- [LiteLLM Security Incident](https://docs.litellm.ai/blog/security-update-march-2026) -- supply chain attack confirmed
- [Datadog LiteLLM Analysis](https://securitylabs.datadoghq.com/articles/litellm-compromised-pypi-teampcp-supply-chain-campaign/)
- [argon2-cffi Docs](https://argon2-cffi.readthedocs.io/) -- v25.1.0
- [PyJWT Docs](https://pyjwt.readthedocs.io/) -- v2.12.1
- [OpenAI Python SDK](https://pypi.org/project/openai/) -- v2.30.0
- [Pydantic Changelog](https://docs.pydantic.dev/latest/changelog/) -- v2.12.5
- [dulwich PyPI](https://pypi.org/project/dulwich/) -- v1.1.0, pure Python
- [react-shiki GitHub](https://github.com/AVGVSTVS96/react-shiki) -- Shiki-powered React highlighting
