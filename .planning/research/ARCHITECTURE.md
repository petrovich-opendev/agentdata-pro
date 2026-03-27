# Architecture Patterns

**Domain:** Multi-agent AI workspace with domain-scoped knowledge isolation
**Researched:** 2026-03-27

## Recommended Architecture

### High-Level System View

```
                         Internet
                            |
                    +--------------+
                    |   Cloudflare |  (DDoS, WAF)
                    +--------------+
                            |
                    +--------------+
                    |    Nginx     |  SSL termination, static files, rate limiting
                    +--------------+
                       /    |    \
                      /     |     \
               +-----+  +------+  +----------+
               | REST |  |  WS  |  | Telegram |
               | API  |  | Hub  |  | Webhook  |
               +-----+  +------+  +----------+
                  \        |        /
                   \       |       /
              +---------------------------+
              |     FastAPI Application    |
              |                           |
              |  +---------------------+  |
              |  | Domain Context      |  |  <-- RLS session variable
              |  | Middleware           |  |      set on every request
              |  +---------------------+  |
              |                           |
              |  +----------+ +--------+  |
              |  | Agent    | | Event  |  |
              |  | Service  | | Bus    |  |
              |  +----------+ +--------+  |
              +---------------------------+
                    |              |
              +----------+  +-----------+
              | TaskIQ   |  |  Redis 7  |
              | Workers  |  |           |
              | (agents, |  | - Broker  |
              |  debates,|  | - Pub/Sub |
              |  cron)   |  | - Streams |
              +----------+  +-----------+
                    |
              +-----------+          +------------------+
              | PostgreSQL|          |   Home Server     |
              | 16        |          |   (WireGuard)     |
              |           |          |                   |
              | - RLS     |          |   Ollama          |
              | - JSONB   |          |   - Qwen 2.5 14B  |
              | - pgvector|          |   - Llama 3.1 8B  |
              | - LTREE   |          +------------------+
              +-----------+
                    |
              +-----------+
              | Git Repo  |
              | (MD files)|
              | Agent     |
              | Memory    |
              +-----------+
```

### Design Philosophy

**Monolith-first with clear internal boundaries.** For 10-70 users, a modular monolith deployed in Docker Compose is the correct choice. The system is structured as distinct internal services (Auth, Domain, Agent, Debate, Event, LLM Router) within a single FastAPI process, with TaskIQ workers as the only separate process. This avoids microservice overhead while keeping the option to extract services later.

**Domain isolation is the architectural spine.** Every data operation flows through a domain context layer that sets PostgreSQL RLS session variables. This is not optional middleware -- it is the fundamental security guarantee. No query can execute without a domain context.

---

## Component Boundaries

### Layer 1: Edge (Nginx)

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| Nginx | SSL termination, static file serving (React SPA), reverse proxy, rate limiting | Cloudflare (upstream), FastAPI (downstream) |

**Build order:** Phase 1 (infrastructure). Straightforward, well-known patterns.

### Layer 2: API Gateway (FastAPI Application)

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| REST API Router | HTTP endpoints for CRUD operations, auth, domain management | All internal services |
| WebSocket Hub | Persistent connections for real-time updates, scoped by domain | Redis Pub/Sub + Streams, React client |
| Telegram Webhook Handler | Receives Telegram updates, routes to correct domain/agent | aiogram Dispatcher, Agent Service |
| Domain Context Middleware | Sets `app.current_domain_id` on every DB session | PostgreSQL (RLS enforcement) |
| Auth Middleware | JWT validation, token refresh, user context injection | PostgreSQL (users table) |

**Build order:** Phase 1 (auth + basic API), Phase 2 (domain CRUD), Phase 3 (WebSocket + Telegram).

### Layer 3: Core Services (Internal modules within FastAPI)

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| Auth Service | Registration, login, JWT issuance, Argon2id hashing, refresh tokens | PostgreSQL (users), Redis (token blacklist) |
| Domain Service | Create/manage domains, invite members, set roles (owner/member/viewer) | PostgreSQL (domains, domain_members) |
| Agent Service | Define agents, bind to domains, configure prompts/tools/schedule | PostgreSQL (agents), TaskIQ (task dispatch) |
| Debate Service | Orchestrate thesis-antithesis-synthesis rounds | Agent Service, LLM Router, PostgreSQL (debates) |
| Memory Service | Read/write agent MD files, git operations (commit, diff, log) | Git repo on filesystem, PostgreSQL (memory index + pgvector) |
| Event Service | Append-only audit log, event publishing | PostgreSQL (events), Redis Streams |
| LLM Router | Route LLM calls: Ollama-first, OpenAI fallback | Ollama (WireGuard), OpenAI API |
| Task Service | Tasks/work items with LTREE hierarchy | PostgreSQL (tasks) |

**Build order:** Auth (Phase 1) -> Domain (Phase 2) -> Agent + LLM Router (Phase 3) -> Debate + Memory (Phase 4) -> Event + Task (woven through phases).

### Layer 4: Background Workers (TaskIQ)

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| Agent Executor | Run agent tasks (on-demand, cron, reactive) | LLM Router, Memory Service, PostgreSQL |
| Debate Orchestrator | Execute multi-round debates asynchronously | LLM Router, PostgreSQL (debates) |
| Scheduled Tasks | APScheduler triggers for cron-mode agents | Redis (broker), Agent Executor |
| Event Processor | Fan-out events to WebSocket, Telegram notifications | Redis Streams, WebSocket Hub, Telegram API |

**Build order:** Phase 3 (basic task execution) -> Phase 4 (debates, cron scheduling).

### Layer 5: Data (PostgreSQL + Redis + Git)

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| PostgreSQL 16 | Primary data store with RLS, pgvector, JSONB, LTREE | All services via asyncpg/SQLAlchemy |
| Redis 7 | Task broker (TaskIQ), Pub/Sub (WebSocket fan-out), Streams (event replay) | TaskIQ Workers, WebSocket Hub, Event Service |
| Git Repository | Agent memory files (MD), version history, diffs | Memory Service (via GitPython or subprocess) |

**Build order:** Phase 1 (PostgreSQL schema + RLS + Redis).

### Layer 6: LLM Infrastructure (Home Server)

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| Ollama | Serve local LLM models via OpenAI-compatible API | LLM Router (via WireGuard tunnel) |
| WireGuard | Encrypted tunnel between VPS and Home Server | Nginx/FastAPI (VPS side), Ollama (Home side) |

**Build order:** Phase 1 (WireGuard + Ollama setup, independently of app code).

---

## Data Flow

### Flow 1: User sends message (Telegram)

```
User -> Telegram API -> Nginx -> FastAPI /webhook endpoint
  -> aiogram Dispatcher parses Update
  -> Auth: identify user by Telegram user_id mapping
  -> Domain Context: resolve active domain for this chat
  -> SET app.current_domain_id = '{domain_id}' (RLS)
  -> Agent Service: determine which agent handles this message
  -> TaskIQ: dispatch agent_execute task
  -> Worker: Agent Executor runs with domain-scoped DB session
    -> LLM Router: Ollama (or OpenAI fallback)
    -> Memory Service: read relevant context from MD + pgvector
    -> LLM generates response
    -> Memory Service: update MD files, git commit
    -> PostgreSQL: save message + response to messages table
    -> Event Service: log event to events table
    -> Redis Pub/Sub: publish 'message.new' event
  -> Telegram API: send response back to user
  -> WebSocket Hub: push update to connected web clients
```

### Flow 2: User interacts via Web UI

```
Browser -> Nginx -> FastAPI REST API
  -> Auth Middleware: validate JWT from httpOnly cookie
  -> Domain Context Middleware: extract domain_id from request path/header
  -> SET app.current_domain_id = '{domain_id}' (RLS)
  -> Service layer processes request (domain-scoped)
  -> Response returned
  -> If mutation: Redis Pub/Sub event -> WebSocket Hub -> all connected clients
```

### Flow 3: Agent debate (async)

```
User triggers debate (via Telegram command or Web UI button)
  -> Debate Service validates parameters
  -> TaskIQ: dispatch debate_execute task
  -> Worker: Debate Orchestrator
    -> Round 1 (Thesis):
      -> Load domain context (Memory Service + pgvector search)
      -> LLM Router -> generate thesis
      -> Save round to debates table
      -> Redis Pub/Sub: 'debate.round' event -> WebSocket + Telegram
    -> Round 2 (Antithesis):
      -> Load thesis as input context
      -> LLM Router -> generate antithesis
      -> Save round, publish event
    -> Round 3 (Synthesis):
      -> Load thesis + antithesis as input
      -> LLM Router -> generate synthesis
      -> Save round, publish event
    -> Memory Service: save debate summary to MD, git commit
    -> Event Service: log debate completion
    -> Redis Pub/Sub: 'debate.completed' event
  -> Telegram: send synthesis summary to user
  -> Web UI: update debate view in real-time
```

### Flow 4: Cron agent execution (autonomous)

```
APScheduler (via TaskIQ scheduled task)
  -> Fires at configured cron time
  -> Worker: Agent Executor
    -> Load agent config from PostgreSQL
    -> SET app.current_domain_id = agent's domain_id (RLS)
    -> Execute agent logic (same as on-demand flow)
    -> If result is notification-worthy:
      -> Telegram: push notification to domain owner/members
      -> WebSocket: push to connected clients
```

### Flow 5: WebSocket reconnection with event replay

```
Client connects to WebSocket endpoint
  -> Auth: validate JWT
  -> Client sends last_event_id (from localStorage)
  -> Server: read missed events from Redis Streams (XRANGE)
  -> Server: replay missed events to client
  -> Server: subscribe client to Redis Pub/Sub for live events
  -> Client receives continuous stream of domain-scoped events
  -> TanStack Query: invalidate relevant caches on each event type
```

---

## Patterns to Follow

### Pattern 1: Domain Context as Database Session Variable

**What:** Every database operation begins by setting a PostgreSQL session variable (`app.current_domain_id`) that RLS policies reference. This happens in middleware, before any service code runs.

**When:** Every authenticated request (REST, WebSocket, TaskIQ worker).

**Why:** Security is at the database level, not application level. Even a bug in service code cannot leak cross-domain data.

**Example:**

```python
# middleware.py
async def set_domain_context(request: Request, call_next):
    domain_id = extract_domain_id(request)
    async with db.session() as session:
        await session.execute(
            text("SET LOCAL app.current_domain_id = :did"),
            {"did": str(domain_id)}
        )
        request.state.db = session
        response = await call_next(request)
    return response
```

```sql
-- RLS policy (applied to all domain-scoped tables)
CREATE POLICY domain_isolation ON agents
  USING (domain_id = current_setting('app.current_domain_id')::uuid);
```

**Critical:** Use `SET LOCAL` (transaction-scoped), not `SET` (session-scoped). This prevents context leaking between requests on the same connection from a pool.

### Pattern 2: Event Sourcing Lite (Append-Only Event Log)

**What:** Every user and agent action creates an immutable entry in the `events` table. This is not full event sourcing (state is not derived from events) but provides complete audit trail.

**When:** Every mutation operation.

**Why:** Compliance, debugging, and replay. The event log answers "what happened, when, by whom, in which domain."

**Example:**

```python
# event_service.py
async def log_event(
    session: AsyncSession,
    actor_type: str,       # "user" | "agent" | "system"
    actor_id: UUID,
    action: str,           # "message.sent" | "debate.completed" | "agent.executed"
    resource_type: str,    # "message" | "debate" | "agent"
    resource_id: UUID,
    domain_id: UUID,
    metadata: dict = None  # JSONB for flexible extra data
):
    event = Event(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        domain_id=domain_id,
        metadata=metadata or {},
        created_at=utcnow()
    )
    session.add(event)
    # Also publish to Redis Stream for real-time delivery
    await redis.xadd(f"events:{domain_id}", event.to_stream_dict())
```

### Pattern 3: LLM Router with Graceful Degradation

**What:** A simple routing layer (~50 lines) that tries Ollama first, falls back to OpenAI on failure, and tracks which backend served each request.

**When:** Every LLM call from any agent or debate.

**Why:** Zero-cost operation when home server is available, seamless fallback when it is not (network issues, GPU overloaded).

**Example:**

```python
# llm_router.py
class LLMRouter:
    async def complete(self, messages: list, model_hint: str = "default") -> LLMResponse:
        model = self._resolve_model(model_hint)

        # Try Ollama first
        if self._ollama_available:
            try:
                response = await self._ollama_client.chat(model=model.ollama_name, messages=messages)
                return LLMResponse(content=response, backend="ollama", model=model.ollama_name)
            except (ConnectionError, TimeoutError):
                self._ollama_available = False
                self._schedule_ollama_health_check()

        # Fallback to OpenAI
        response = await self._openai_client.chat.completions.create(
            model=model.openai_name, messages=messages
        )
        return LLMResponse(content=response, backend="openai", model=model.openai_name)
```

### Pattern 4: TaskIQ Worker with Domain Context Injection

**What:** Background workers set the same domain context that HTTP middleware sets, ensuring RLS works identically for async tasks.

**When:** Every TaskIQ task that touches domain-scoped data.

**Why:** Agents running in background workers must have the same security guarantees as HTTP requests. No special "admin bypass" for workers.

**Example:**

```python
# tasks.py
@broker.task
async def execute_agent(agent_id: UUID, domain_id: UUID, trigger: str):
    async with db.session() as session:
        # Same RLS context as HTTP requests
        await session.execute(
            text("SET LOCAL app.current_domain_id = :did"),
            {"did": str(domain_id)}
        )
        agent = await agent_service.get(session, agent_id)
        # Agent can only see data from its own domain
        context = await memory_service.load_context(session, agent)
        result = await llm_router.complete(agent.build_messages(context))
        await memory_service.save_result(session, agent, result)
        await event_service.log_event(session, "agent", agent_id, "agent.executed", ...)
```

### Pattern 5: Git-Versioned Agent Memory (DiffMem Pattern)

**What:** Agent knowledge is stored as MD files in a git repository, organized by domain. The "current state" is always the HEAD of the file. History is in git log. A pgvector index provides semantic search over memory content.

**When:** Agent reads context before execution, writes results after execution.

**Why:** Human-readable, diffable, version-controlled knowledge. Agents naturally produce markdown. Git provides free undo/audit/branching.

**Structure:**

```
agent-memory/
  {domain_id}/
    memory/
      {topic}.md              # Agent's accumulated knowledge
    debates/
      {date}_{topic}.md       # Debate transcripts
    research/
      {date}_{query}.md       # Research outputs
```

**Dual storage:** MD files for full content (git-versioned), pgvector for semantic search (embeddings of chunks). The index is rebuilt from MD files -- git is the source of truth, pgvector is a derived index.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Application-Level Domain Filtering

**What:** Filtering data by `WHERE domain_id = ?` in application code instead of using RLS.

**Why bad:** One missed filter in one query = cross-domain data leak. Security depends on every developer remembering every time. Prompt injection could manipulate queries if they bypass the filter.

**Instead:** RLS policies on every domain-scoped table. Application code does not even include `domain_id` in WHERE clauses -- the database enforces it transparently.

### Anti-Pattern 2: Superuser Database Connection

**What:** Application connects to PostgreSQL as a superuser or role that bypasses RLS.

**Why bad:** RLS is completely ignored for superusers. All isolation guarantees evaporate.

**Instead:** Create a dedicated `app_user` role with RLS enabled. Only migrations and backups use superuser.

### Anti-Pattern 3: Synchronous LLM Calls in Request Handler

**What:** Calling LLM directly in the HTTP request/response cycle, making the user wait.

**Why bad:** LLM calls take 2-30 seconds. HTTP timeouts, blocked connections, poor UX.

**Instead:** Dispatch to TaskIQ immediately. Return task ID. Push results via WebSocket/Telegram when ready.

### Anti-Pattern 4: Global Agent Memory (No Domain Scoping)

**What:** Storing all agent memory in one flat directory or one pgvector collection without domain isolation.

**Why bad:** Semantic search could return chunks from other domains. Memory pollution between domains.

**Instead:** Domain-scoped directories in git. Domain-scoped pgvector queries (filter by `domain_id` column + RLS).

### Anti-Pattern 5: Fat Telegram Bot Handler

**What:** Business logic in aiogram handlers -- processing messages, calling LLM, formatting responses all in the handler function.

**Why bad:** Untestable, duplicates logic between Telegram and Web channels, blocking the webhook response.

**Instead:** Thin handler that maps Telegram input to domain service calls. Same service layer serves both Web API and Telegram. LLM calls always go through TaskIQ.

---

## Scalability Considerations

| Concern | At 10 users (MVP) | At 70 users | At 500+ users (future) |
|---------|-------------------|-------------|----------------------|
| Database | Single PostgreSQL, no replicas | Same, add connection pooling (PgBouncer) | Read replicas, partition events table |
| Task Queue | Single TaskIQ worker process | 2-3 worker processes | Dedicated worker nodes, priority queues |
| LLM Throughput | 1 concurrent request to Ollama | Queue with priority (Ollama handles 1-2 concurrent) | Multiple Ollama instances or dedicated inference server |
| WebSocket | All connections in one FastAPI process | Same (hundreds of connections are fine) | Separate WebSocket server, Redis-backed fan-out |
| Git Memory | Single git repo, all domains | Same (git handles thousands of files) | Sharded repos per domain group |
| Redis | Single instance | Same | Redis Cluster if Streams volume grows |
| Static Files | Nginx serves React build | CDN (Cloudflare) | Same |

**Key insight:** For 70 users, the only scaling concern is LLM throughput. Ollama on a single GPU can handle ~2 concurrent requests at useful speed. With 70 users, peak concurrent LLM requests could reach 5-10. Solution: prioritized queue in TaskIQ + OpenAI fallback for overflow. No infrastructure changes needed for everything else.

---

## Suggested Build Order (Dependencies)

The architecture has clear dependency chains that dictate build order:

```
Phase 1: Foundation
  ├── PostgreSQL schema + RLS policies (everything depends on this)
  ├── Redis setup (TaskIQ broker, Pub/Sub)
  ├── Auth Service (JWT + Argon2id)
  ├── FastAPI skeleton with domain context middleware
  ├── Docker Compose for all services
  └── WireGuard tunnel + Ollama (independent, parallel)

Phase 2: Domain Management
  ├── Domain CRUD (create, list, update domains)
  ├── Domain membership (invite, roles: owner/member/viewer)
  ├── RLS verification tests (prove isolation works)
  └── Basic Web UI (auth + domain management screens)

Phase 3: Agent Infrastructure
  ├── Agent CRUD (define agents, bind to domains)
  ├── LLM Router (Ollama + OpenAI fallback)
  ├── TaskIQ worker setup with domain context injection
  ├── Agent Executor (on-demand execution)
  ├── Memory Service (MD files + git + basic pgvector)
  └── Event Service (audit log)

Phase 4: Communication Channels
  ├── Telegram webhook integration (aiogram + FastAPI)
  ├── WebSocket Hub + Redis Pub/Sub
  ├── Event replay from Redis Streams
  └── Thin Telegram handlers -> service layer

Phase 5: Debates + Autonomy
  ├── Debate orchestrator (thesis/antithesis/synthesis)
  ├── Cron scheduling (APScheduler via TaskIQ)
  ├── Reactive triggers (event-driven agent activation)
  └── Debate UI in Web + Telegram

Phase 6: Health Domain MVP
  ├── Health-specific agent templates
  ├── Weight tracking, supplements, blood tests
  ├── Morning/evening Telegram routines
  └── Dashboard with charts and agent activity
```

**Why this order:**

1. **Foundation first** -- RLS and auth are non-negotiable prerequisites. Everything else builds on domain-scoped data access.
2. **Domains before agents** -- Agents live inside domains. Cannot build agents without domains.
3. **Agent infra before channels** -- Telegram and WebSocket are delivery mechanisms. The agent execution engine must work first.
4. **Channels before debates** -- Debates need notification delivery (Telegram, WebSocket) to be useful.
5. **Domain-specific features last** -- The Health domain MVP uses all infrastructure built in phases 1-5.

---

## Key Architectural Decisions

### Decision 1: Monolith, Not Microservices

For 10-70 users, a modular monolith in a single FastAPI process (+ TaskIQ workers) is correct. Microservices add network latency, deployment complexity, and operational overhead that is not justified at this scale. Internal module boundaries (services) allow extraction later if needed.

### Decision 2: PostgreSQL RLS as Primary Security Mechanism

RLS is the ONLY acceptable approach for domain isolation at the database level. Application-level filtering is insufficient -- it requires every query to be correct, which is fragile. RLS makes isolation a database guarantee, not an application concern.

### Decision 3: Async-All-The-Way

FastAPI (async) -> TaskIQ (async workers) -> asyncpg (async DB) -> aiohttp (async HTTP to Ollama/OpenAI). No sync bottlenecks anywhere. This is critical because LLM calls are I/O-bound and can take seconds.

### Decision 4: Redis for Three Roles (Broker + Pub/Sub + Streams)

Single Redis instance serves TaskIQ (broker), WebSocket fan-out (Pub/Sub), and event replay (Streams). This is appropriate for the scale. Separating would add operational complexity without benefit.

### Decision 5: Git for Agent Memory, pgvector for Search

Git is the source of truth for agent knowledge (human-readable, diffable, auditable). pgvector is a derived index for semantic search. If pgvector is lost, it can be rebuilt from git. If git is lost, the data is gone. Backup strategy focuses on git repo.

---

## Sources

- [Designing Effective Multi-Agent Architectures - O'Reilly](https://www.oreilly.com/radar/designing-effective-multi-agent-architectures/) - HIGH confidence
- [Multi-tenant data isolation with PostgreSQL RLS - AWS](https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security/) - HIGH confidence
- [Postgres RLS Implementation Guide - Permit.io](https://www.permit.io/blog/postgres-rls-implementation-guide) - HIGH confidence
- [Shipping multi-tenant SaaS using Postgres RLS - Nile](https://www.thenile.dev/blog/multi-tenant-rls) - MEDIUM confidence
- [TaskIQ Architecture Overview](https://taskiq-python.github.io/guide/architecture-overview.html) - HIGH confidence
- [Building Real-Time Notifications with FastAPI, Redis Streams, WebSockets](https://dev.to/geetnsh2k1/building-a-real-time-notification-service-with-fastapi-redis-streams-and-websockets-52ib) - MEDIUM confidence
- [DiffMem: Git-Based Memory for AI Agents](https://github.com/Growth-Kinetics/DiffMem) - MEDIUM confidence
- [Hegelion: Dialectical Reasoning for LLMs](https://github.com/Hmbown/Hegelion) - MEDIUM confidence
- [Self-reflecting LLMs: A Hegelian Dialectical Approach - Microsoft Research](https://www.microsoft.com/en-us/research/wp-content/uploads/2025/02/2501.14917v3.pdf) - HIGH confidence
- [Multi-LLM-Agents Debate Performance - ICLR 2025](https://d2jud02ci9yv69.cloudfront.net/2025-04-28-mad-159/blog/mad/) - HIGH confidence
- [aiogram Webhook Documentation](https://docs.aiogram.dev/en/latest/dispatcher/webhook.html) - HIGH confidence
- [AI Agent Memory Management - Markdown Files](https://dev.to/imaginex/ai-agent-memory-management-when-markdown-files-are-all-you-need-5ekk) - MEDIUM confidence
