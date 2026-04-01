# BioCoach — Architecture (MVP)

> IMPORTANT: This document was partially simplified. Read PROJECT_BRIEF.md for the
> latest decisions. When this doc conflicts with PROJECT_BRIEF.md — trust the BRIEF.

## ⚠️ REMOVED FROM MVP (do NOT implement):
- **domain_types table** — DELETED. System prompt is loaded from file `prompts/health_advisor.md`
- **knowledge_nodes / knowledge_edges tables** — DELETED. Phase 2.
- **SearXNG Docker container** — REPLACED with `duckduckgo-search` pip package
- **Langfuse** — REMOVED. Use `structlog` for logging.
- **Session management UI** — REMOVED. One chat per user, no sidebar.
- **config_override in domains** — REMOVED.
- **domain_type_id in domains table** — REMOVED. Just owner_id + name.

## ⚠️ API CONTRACT (frontend ↔ backend):
- POST /api/auth/request-code accepts: `{"telegram_username": "@name"}` (NOT chat_id!)
- API resolves username → chat_id internally via Telegram Bot API
- JWT claims: `{"sub": "user-uuid", "domain_id": "domain-uuid"}`

---

## 1. System Overview

```
                    Internet
                       |
                   [nginx:443]
                    /       \
              /api/*        /*
                |             |
          [api:8000]     [web:80]
          FastAPI        React (nginx)
              |
         [nats:4222]
          JetStream
         /         \
   [Router]    [SearchAgent]
      |              |
   [LiteLLM]    [SearXNG:8888]
   (llmsrv)     (metasearch)
      |
  [postgres:5432]
```

---

## 2. Docker Compose Services

```yaml
services:
  nginx:        # Reverse proxy, SSL termination
  web:          # React build served by nginx
  api:          # Python FastAPI (platform core + agents)
  nats:         # NATS JetStream (agent messaging)
  postgres:     # PostgreSQL 16 (all data)
  searxng:      # SearXNG (web search)
```

**6 services total.** LiteLLM is external (llmsrv, IP-whitelisted).

### Port Map

| Service | Internal Port | External Port | Notes |
|---------|--------------|---------------|-------|
| nginx | 80, 443 | 80, 443 | Only public entry point |
| web | 80 | — | Internal only, nginx proxies |
| api | 8000 | — | Internal only, nginx proxies /api/* |
| nats | 4222, 8222 | — | 4222=client, 8222=monitoring |
| postgres | 5432 | — | Internal only |
| searxng | 8888 | — | Internal only, api calls directly |

---

## 3. Backend (api service)

### Tech Stack

| Component | Library | Why |
|-----------|---------|-----|
| Framework | FastAPI | Async, Pydantic validation, OpenAPI docs |
| DB driver | asyncpg | Fastest PostgreSQL driver for Python |
| ORM | None (raw SQL + asyncpg) | Full control, parameterized queries, no magic |
| Migrations | Alembic | Standard, works with asyncpg |
| Auth | PyJWT + python-telegram-bot | JWT tokens + Telegram bot for codes |
| NATS client | nats-py | Official async Python client |
| LLM client | openai (SDK) | OpenAI-compatible, works with LiteLLM |
| HTTP client | httpx | Async HTTP for SearXNG queries |
| Observability | langfuse | Python SDK, @observe decorator |
| Validation | Pydantic v2 | Request/response models |
| Logging | structlog | JSON structured logging |

### Project Structure

```
api/
├── main.py                  # FastAPI app, lifespan, middleware
├── config.py                # Settings from env vars (pydantic-settings)
├── deps.py                  # Dependency injection (db pool, nats, etc.)
│
├── auth/
│   ├── router.py            # POST /auth/request-code, POST /auth/verify-code
│   ├── service.py           # Code generation, Telegram send, JWT issue
│   ├── models.py            # Pydantic schemas
│   └── telegram.py          # Telegram bot wrapper (send code to DM)
│
├── domains/
│   ├── router.py            # GET /domains/me (current user domain + config)
│   ├── service.py           # Domain CRUD, config loading
│   └── models.py            # Pydantic schemas
│
├── chat/
│   ├── router.py            # POST /chat/sessions, GET /chat/sessions, POST /chat/messages
│   ├── service.py           # Chat logic, history management, context trimming
│   ├── models.py            # Pydantic schemas
│   └── history.py           # Sliding window / summarization for long chats
│
├── agents/
│   ├── base.py              # BaseAgent class (NATS subscribe/publish pattern)
│   ├── router_agent.py      # Intent classification (local LLM, domain-aware)
│   ├── search_agent.py      # Web search via SearXNG (config from domain)
│   └── registry.py          # Agent registration and lifecycle
│
├── llm/
│   ├── client.py            # LLM client wrapper (OpenAI SDK -> LiteLLM)
│   ├── prompts.py           # Prompt loader (from DB domain config)
│   └── streaming.py         # SSE streaming helpers
│
├── db/
│   ├── pool.py              # asyncpg connection pool setup
│   ├── queries/             # SQL query constants
│   │   ├── users.py
│   │   ├── sessions.py
│   │   ├── messages.py
│   │   └── domains.py
│   └── migrations/          # Alembic migrations
│       └── seed_biocoach.py # Seed: domain_type "health" + BioCoach config
│
└── middleware/
    ├── auth.py              # JWT verification middleware
    ├── domain.py            # Load domain config, set RLS context per request
    └── rate_limit.py        # Rate limiting (in-memory for MVP)
```

**Key difference from monolith:** no `prompts/` directory in code.
System prompts are stored in `domain_types.system_prompt` (DB) and loaded per request.

### API Endpoints

```
Auth:
  POST   /api/auth/request-code    {telegram_username}  → sends code via bot
  POST   /api/auth/verify-code     {telegram_username, code}  → {access_token}
  POST   /api/auth/refresh         (cookie: refresh_token) → {access_token}
  POST   /api/auth/logout          → clears refresh token

Domain:
  GET    /api/domains/me           → {id, name, type, config, disclaimer}

Chat:
  GET    /api/chat/sessions        → [{id, title, created_at}]
  POST   /api/chat/sessions        → {id, title}
  DELETE /api/chat/sessions/:id    → 204 (soft delete)
  GET    /api/chat/sessions/:id/messages  → [{role, content, created_at}]
  POST   /api/chat/sessions/:id/messages  {content} → SSE stream

Health:
  GET    /api/health               → {status: "ok", version: "..."}
```

### Chat Flow (detailed)

```
 1. Client: POST /api/chat/sessions/:id/messages {content: "..."}
 2. Middleware: extract domain_id from JWT, load domain config from DB
 3. Middleware: SET LOCAL app.current_domain = domain_id (RLS)
 4. API: save user message to PostgreSQL
 5. API: load conversation history (last N messages, trimmed)
 6. API: publish to NATS "chat.{domain_id}.classify"
        payload: {domain_id, session_id, message, history, domain_config}
 7. RouterAgent: classify intent via local LLM
        prompt: domain_config.router_prompt
        → {intent: "general_chat" | "search", entities: [...]}
 8. If intent=search:
        RouterAgent publishes to NATS "agents.{domain_id}.search.request"
        payload: {query, search_config: domain_config.search}
 9. SearchAgent: query SearXNG with domain-specific params
        (language, categories, query_template from domain_config.search)
        → publish results to "agents.{domain_id}.search.response"
10. API: receive search results (or skip if intent=general_chat)
11. API: call LLM via LiteLLM with:
        system_prompt = domain_config.system_prompt  (from DB)
        + history + search_results (if any)
12. API: stream response via SSE to client
13. API: save assistant message + metadata to PostgreSQL
14. Client: render streaming tokens + follow-up suggestions
```

### NATS Subjects (domain-scoped)

```
chat.{domain_id}.classify              # RouterAgent: classify intent
agents.{domain_id}.search.request      # SearchAgent: incoming search
agents.{domain_id}.search.response     # SearchAgent: results
agents.{domain_id}.*.request           # Future agents
agents.{domain_id}.*.response          # Future agent responses
events.chat.message                    # Event: new message (analytics, logging)
```

### Context Trimming Strategy

Long conversations must fit LLM context window. Strategy:

1. **System prompt** — always included, from domain config (~500-1000 tokens)
2. **Last 10 messages** — always included
3. **If > 20 messages total** — summarize older messages via local LLM (Qwen3)
4. **Summary** injected as a system message: "Previous conversation summary: ..."
5. **Max context budget** — configurable per domain (default: 8000 tokens)

---

## 4. Frontend (web service)

### Tech Stack

| Component | Library |
|-----------|---------|
| Framework | React 18+ |
| Language | TypeScript |
| Build | Vite |
| Routing | React Router v6 |
| State | Zustand (lightweight) |
| HTTP | fetch (native) + ReadableStream for SSE |
| UI | Tailwind CSS |
| Icons | Lucide React |

### Pages

```
/                    → Landing / Login page
/auth/verify         → Code verification form
/cabinet             → Personal cabinet (redirect if not authed)
/cabinet/chat/:id    → Chat session
```

### Components

```
web/src/
├── pages/
│   ├── Landing.tsx          # Login form (enter @telegram_username)
│   ├── VerifyCode.tsx       # 6-digit code input
│   └── Cabinet.tsx          # Main layout (sidebar + chat)
│
├── components/
│   ├── ChatWindow.tsx       # Message list + streaming display
│   ├── ChatInput.tsx        # Message input + send button
│   ├── MessageBubble.tsx    # Single message (user/assistant)
│   ├── SearchResults.tsx    # Inline search results card
│   ├── Suggestions.tsx      # Follow-up suggestion buttons
│   ├── SessionList.tsx      # Sidebar: session list
│   ├── Disclaimer.tsx       # Domain-specific disclaimer (from config)
│   └── Header.tsx           # Top bar (domain name, user info, logout)
│
├── hooks/
│   ├── useAuth.ts           # Auth state, login/logout, token refresh
│   ├── useChat.ts           # Chat state, send message, SSE stream
│   ├── useDomain.ts         # Load domain config (name, disclaimer, theme)
│   └── useSSE.ts            # ReadableStream SSE wrapper with reconnection
│
├── api/
│   └── client.ts            # API client (fetch + auth headers + refresh)
│
├── stores/
│   ├── authStore.ts         # Zustand: user, tokens
│   └── domainStore.ts       # Zustand: domain config (loaded once after auth)
│
└── types/
    └── index.ts             # Shared TypeScript types
```

### SSE Streaming (POST + ReadableStream)

```typescript
// useSSE.ts — POST with streaming response
const response = await fetch(`/api/chat/sessions/${id}/messages`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  },
  body: JSON.stringify({ content: message }),
});

const reader = response.body!.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  const chunk = decoder.decode(value);
  // Parse SSE events, update UI
}
```

---

## 5. Database Schema (PostgreSQL 16)

### Platform tables (domain-agnostic)

```sql
-- Domain types (platform-level configuration)
-- Adding a new domain type = INSERT here + write a prompt. No code changes.
CREATE TABLE domain_types (
    id TEXT PRIMARY KEY,                    -- 'health', 'finance', 'legal'
    name TEXT NOT NULL,                     -- 'Health Advisor'
    description TEXT,
    system_prompt TEXT NOT NULL,            -- main AI persona prompt
    router_prompt TEXT NOT NULL,            -- intent classification prompt
    search_config JSONB DEFAULT '{}',      -- {language, categories, query_template}
    agent_config JSONB DEFAULT '{}',       -- {enabled_agents: ["search"], models: {...}}
    ui_config JSONB DEFAULT '{}',          -- {disclaimer, theme, suggestions_style}
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Users (minimal, pseudonymous)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_chat_id BIGINT UNIQUE NOT NULL,  -- immutable, primary identifier
    telegram_username TEXT,                     -- display only, can change
    created_at TIMESTAMPTZ DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

-- Knowledge Domains (one per user for MVP)
CREATE TABLE domains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES users(id),
    domain_type_id TEXT NOT NULL REFERENCES domain_types(id),
    name TEXT NOT NULL DEFAULT 'personal',
    config_override JSONB DEFAULT '{}',    -- per-domain overrides (future)
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE domains ENABLE ROW LEVEL SECURITY;
ALTER TABLE domains FORCE ROW LEVEL SECURITY;
CREATE POLICY domain_isolation ON domains
    FOR ALL USING (id::text = current_setting('app.current_domain', true));

-- Auth codes (temporary, for Telegram verification)
CREATE TABLE auth_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_chat_id BIGINT NOT NULL,      -- immutable identifier
    code_hash TEXT NOT NULL,               -- SHA-256 of 6-digit code
    attempts INT DEFAULT 0,
    expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_auth_codes_chat_id ON auth_codes(telegram_chat_id, used, expires_at);

-- Refresh tokens
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,              -- SHA-256 of refresh token
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);

-- Chat sessions
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id UUID NOT NULL REFERENCES domains(id),
    title TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    deleted_at TIMESTAMPTZ               -- soft delete
);

ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY session_isolation ON chat_sessions
    FOR ALL USING (domain_id::text = current_setting('app.current_domain', true));

CREATE INDEX idx_sessions_domain ON chat_sessions(domain_id, created_at);

-- Chat messages
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id),
    domain_id UUID NOT NULL REFERENCES domains(id),   -- denormalized for RLS
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',          -- token_count, model, cost, search_results, suggestions
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages FORCE ROW LEVEL SECURITY;
CREATE POLICY message_isolation ON chat_messages
    FOR ALL USING (domain_id::text = current_setting('app.current_domain', true));

CREATE INDEX idx_messages_session ON chat_messages(session_id, created_at);
CREATE INDEX idx_messages_domain ON chat_messages(domain_id);
```

### Knowledge graph tables (for Phase 2, created now for schema stability)

```sql
CREATE TABLE knowledge_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id UUID NOT NULL REFERENCES domains(id),
    node_type TEXT NOT NULL,               -- 'biomarker', 'medication', etc.
    name TEXT NOT NULL,
    properties JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE knowledge_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_nodes FORCE ROW LEVEL SECURITY;
CREATE POLICY node_isolation ON knowledge_nodes
    FOR ALL USING (domain_id::text = current_setting('app.current_domain', true));

CREATE TABLE knowledge_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id UUID NOT NULL REFERENCES domains(id),
    source_id UUID NOT NULL REFERENCES knowledge_nodes(id),
    target_id UUID NOT NULL REFERENCES knowledge_nodes(id),
    edge_type TEXT NOT NULL,
    properties JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE knowledge_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_edges FORCE ROW LEVEL SECURITY;
CREATE POLICY edge_isolation ON knowledge_edges
    FOR ALL USING (domain_id::text = current_setting('app.current_domain', true));

CREATE INDEX idx_edges_source ON knowledge_edges(source_id);
CREATE INDEX idx_edges_target ON knowledge_edges(target_id);
CREATE INDEX idx_nodes_domain_type ON knowledge_nodes(domain_id, node_type);
```

### Seed data: BioCoach domain type

```sql
INSERT INTO domain_types (id, name, description, system_prompt, router_prompt, search_config, agent_config, ui_config)
VALUES (
    'health',
    'Health Advisor',
    'Personal AI health advisor: supplements, lab tests, medications, nutrition',
    -- system_prompt: loaded from file during migration
    E'You are a personal health and performance advisor...',
    -- router_prompt: intent classification
    E'Classify the user intent into one of: general_chat, search...',
    -- search_config
    '{"language": "ru", "categories": "general", "query_enhancement": {"search": "купить цена отзывы"}}',
    -- agent_config
    '{"enabled_agents": ["router", "search"], "models": {"router": "qwen3:14b", "chat": "claude-sonnet-4-20250514"}}',
    -- ui_config
    '{"disclaimer": "AI-советник не заменяет врача. Перед применением проконсультируйтесь со специалистом.", "theme": "health", "suggestions_count": 3}'
);
```

---

## 6. Auth Flow (Telegram + JWT)

### Registration / Login

```
1. Client: POST /api/auth/request-code {telegram_username: "@petrovich"}
2. API: resolve @username → chat_id via Telegram bot
   → Bot must be running and user must have /start'ed it at least once
3. API: generate 6-digit code, hash it, store in auth_codes with chat_id (expires: 5 min)
4. API: send code to user via Telegram bot DM (using chat_id)
5. Client: POST /api/auth/verify-code {telegram_username: "@petrovich", code: "482917"}
6. API: lookup auth_code by chat_id (resolved from username), verify hash, check expiration, check attempts (max 5)
7. API: create user if new (primary key: telegram_chat_id, username stored for display)
8. API: auto-create personal domain (domain_type_id = platform default, e.g., "health")
9. API: issue access_token (JWT, 30 min) + refresh_token (opaque, 30 days)
10. API: return {access_token} + Set-Cookie: refresh_token (HttpOnly, Secure, SameSite=Strict)
```

### Token Refresh

```
1. Client: access_token expired (401 from API)
2. Client: POST /api/auth/refresh (cookie: refresh_token)
3. API: validate refresh_token hash, check expiration
4. API: issue new access_token + new refresh_token (rotation)
5. API: return {access_token} + Set-Cookie: new refresh_token
```

### JWT Claims

```json
{
  "sub": "user-uuid",
  "domain_id": "domain-uuid",
  "domain_type": "health",
  "tg_id": 123456789,
  "exp": 1711900000,
  "iat": 1711898200
}
```

### Prerequisite

User must send `/start` to the Telegram bot at least once before registration.
The landing page should explain this clearly with a link to the bot.

---

## 7. Agent Architecture

### Base Pattern (platform-level)

All agents follow the same interface. The platform does not know what agents do —
it only knows how to start them, route messages, and collect results.

```python
class BaseAgent:
    def __init__(self, js: JetStreamContext, domain_config: dict):
        self.js = js
        self.config = domain_config  # agent behavior from domain_types table

    async def start(self, domain_id: str):
        """Subscribe to NATS subject scoped to domain_id"""

    async def handle(self, msg: AgentRequest) -> AgentResponse:
        """Process single request — override in subclass"""

    async def publish(self, subject: str, data: dict):
        """Publish result to NATS"""
```

### MVP Agents

**RouterAgent** (intent classification):
- Subscribes to: `chat.{domain_id}.classify`
- Uses: local LLM (Qwen3 via LiteLLM)
- Prompt: loaded from `domain_types.router_prompt`
- Output: `{intent: "general_chat" | "search", entities: [...]}`
- If intent=search → publishes to `agents.{domain_id}.search.request`

**SearchAgent** (web search):
- Subscribes to: `agents.{domain_id}.search.request`
- Uses: SearXNG JSON API
- Config: `domain_types.search_config` (language, categories, query_template)
- Publishes to: `agents.{domain_id}.search.response`
- Output: `{results: [{title, url, snippet, source}], query, timestamp}`

### Future Agents (Phase 2+)

Same pattern, different NATS subjects:
- `agents.{domain_id}.lab.request/response` — LabAgent
- `agents.{domain_id}.pharma.request/response` — PharmaAgent
- `agents.{domain_id}.nutrition.request/response` — NutritionAgent
- `agents.{domain_id}.vision.request/response` — VisionAgent

New agents are registered in `domain_types.agent_config.enabled_agents`.
Platform starts only the agents listed there for each domain.

### Agent Lifecycle

Agents start with FastAPI lifespan. Platform reads `domain_types.agent_config`
to determine which agents to activate.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    nc = await nats.connect(settings.nats_url)
    js = nc.jetstream()

    # Load all domain types and their agent configs
    domain_types = await load_domain_types(db_pool)

    # Start agents per domain type
    agent_instances = []
    for dt in domain_types:
        for agent_name in dt.agent_config["enabled_agents"]:
            agent_cls = AGENT_REGISTRY[agent_name]  # {"router": RouterAgent, "search": SearchAgent}
            agent = agent_cls(js, dt)
            await agent.start(domain_id="*")  # listen for all domains of this type
            agent_instances.append(agent)

    yield

    for agent in agent_instances:
        await agent.stop()
    await nc.close()
```

---

## 8. SearXNG Configuration

### Docker

```yaml
searxng:
  image: searxng/searxng:latest
  environment:
    - SEARXNG_BASE_URL=http://searxng:8888
  volumes:
    - ./config/searxng/settings.yml:/etc/searxng/settings.yml
```

### Settings (key parts)

```yaml
search:
  formats:
    - json
  default_lang: "ru"

engines:
  - name: google
    engine: google
    shortcut: g
  - name: bing
    engine: bing
    shortcut: b
  - name: duckduckgo
    engine: duckduckgo
    shortcut: ddg

server:
  secret_key: "${SEARXNG_SECRET}"
  limiter: false
  image_proxy: false
```

### Query Pattern from SearchAgent

```python
async def search(self, query: str, search_config: dict) -> list[SearchResult]:
    language = search_config.get("language", "ru")
    categories = search_config.get("categories", "general")

    params = {
        "q": query,
        "format": "json",
        "language": language,
        "categories": categories,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{self.searxng_url}/search",
            params=params,
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            SearchResult(
                title=r["title"],
                url=r["url"],
                snippet=r.get("content", ""),
            )
            for r in data.get("results", [])[:10]
        ]
```

---

## 9. LLM Integration

### Connection to LiteLLM

```python
from openai import AsyncOpenAI

llm_client = AsyncOpenAI(
    base_url=settings.litellm_base_url,
    api_key=settings.litellm_api_key,
)
```

### Model Selection (from domain config)

```python
# Router uses local model (from domain_types.agent_config.models.router)
model = domain_config["agent_config"]["models"]["router"]  # "qwen3:14b"
response = await llm_client.chat.completions.create(
    model=model,
    messages=[...],
    response_format={"type": "json_object"},
)

# Chat uses cloud model (from domain_types.agent_config.models.chat)
model = domain_config["agent_config"]["models"]["chat"]  # "claude-sonnet-4-20250514"
response = await llm_client.chat.completions.create(
    model=model,
    messages=[{"role": "system", "content": domain_config["system_prompt"]}, ...],
    stream=True,
)
```

### Prompt Management

- **System prompts** stored in `domain_types.system_prompt` (DB)
- **Router prompts** stored in `domain_types.router_prompt` (DB)
- Loaded once at startup, cached in memory
- Updated via DB migration or future admin API
- Versioned in Langfuse for A/B testing and quality monitoring

---

## 10. Deployment

### Target Server

- **Host:** agentdata.pro (94.131.92.153)
- **OS:** Ubuntu
- **Resources:** 4 vCPU, 8 GB RAM, 40 GB NVMe

### Environment Variables (api service)

```env
# Database
DATABASE_URL=postgresql://biocoach:${DB_PASSWORD}@postgres:5432/biocoach

# NATS
NATS_URL=nats://nats:4222

# LLM
LITELLM_BASE_URL=https://llmsrv-external-url/v1
LITELLM_API_KEY=sk-...

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...

# Auth
JWT_SECRET=...
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# SearXNG
SEARXNG_URL=http://searxng:8888

# Langfuse
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_HOST=https://cloud.langfuse.com

# Platform
DEFAULT_DOMAIN_TYPE=health
APP_ENV=production
LOG_LEVEL=info
CORS_ORIGINS=https://agentdata.pro
```

### Nginx Config (key parts)

```nginx
server {
    listen 443 ssl;
    server_name agentdata.pro;

    ssl_certificate /etc/letsencrypt/live/agentdata.pro/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/agentdata.pro/privkey.pem;

    # React SPA (web container's own nginx handles SPA fallback)
    location / {
        proxy_pass http://web:80;
    }

    # API
    location /api/ {
        proxy_pass http://api:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection '';
        proxy_buffering off;           # Required for SSE
        proxy_cache off;
        proxy_read_timeout 300s;       # Long timeout for LLM streaming
    }
}

server {
    listen 80;
    server_name agentdata.pro;
    return 301 https://$host$request_uri;
}
```

---

## 11. Development Phases

### Phase 1: Foundation (current MVP)
- Platform core: auth, domains, chat, agent framework
- BioCoach domain config (seed data)
- Telegram auth (bot + JWT)
- Personal cabinet (domain auto-creation)
- AI chat with streaming (SSE)
- RouterAgent + SearchAgent
- NATS JetStream for agent communication
- Docker Compose deployment on agentdata.pro

### Phase 2: Domain Agents
- LabAgent (interpret lab results)
- PharmaAgent (drug interactions, dosages)
- NutritionAgent (diet, supplements)
- VisionAgent (PDF/photo → data extraction)
- Knowledge graph population (knowledge_nodes/edges)
- Telegram bot (chat via bot)

### Phase 3: Platform Features
- Channels (shared knowledge domains)
- Invite system
- Role-based access within channels
- Multiple domain types (finance, legal)
- Domain creation UI (PaaS console)

### Phase 4: Scale
- Kubernetes migration (RKE2)
- Client-side encryption (zero-knowledge)
- Template marketplace
- Horizontal agent scaling
