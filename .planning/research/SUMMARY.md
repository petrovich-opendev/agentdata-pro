# Project Research Summary

**Project:** AgentData.pro
**Domain:** Personal AI Operating System / Multi-Agent Knowledge Workspace
**Researched:** 2026-03-27
**Confidence:** HIGH

## Executive Summary

AgentData.pro is a multi-agent AI workspace where autonomous agents operate 24/7 within domain-isolated knowledge silos (health, finance, work), communicating with users via Telegram and a React Web UI. The product's architectural spine is PostgreSQL Row-Level Security for domain isolation, with agents that accumulate knowledge in git-versioned Markdown files and can debate each other using a thesis-antithesis-synthesis pattern. Research confirms this is a well-understood architecture class -- modular Python monolith (FastAPI + TaskIQ workers), PostgreSQL as the single data store (JSONB + pgvector + RLS + LTREE), Redis for task brokering and real-time events, and a hybrid LLM setup (local Ollama via WireGuard + OpenAI fallback). Every major technology choice has HIGH confidence with verified, current sources.

The recommended approach is monolith-first with strict internal service boundaries (Auth, Domain, Agent, Debate, Memory, Event, LLM Router) inside a single FastAPI process, with TaskIQ as the only separate worker process. The build order follows a clear dependency chain: foundation (RLS + Auth) before domains, domains before agents, agents before communication channels, channels before debates. The Health domain MVP validates all infrastructure by exercising isolation, agent memory, debates, and dual-channel delivery (Telegram + Web UI). This order avoids premature complexity while delivering a usable product at each phase boundary.

The primary risks are: (1) domain logic hardcoded in agent code instead of DB/config -- historically the #1 failure mode in similar projects, (2) RLS policies that appear secure but leak data through superuser testing or missing WITH CHECK clauses, (3) WireGuard tunnel drops silently killing LLM access overnight, and (4) context window overflow as agent memory accumulates. All four have well-documented prevention strategies outlined in the research. The LiteLLM supply chain compromise (March 2026) validates the decision to use a custom LLM router.

## Key Findings

### Recommended Stack

The stack is Python 3.12 + FastAPI for the backend, React 19 + TypeScript + Vite for the frontend, PostgreSQL 16 as the single database (with pgvector extension for vector search), Redis 7 for task brokering/pub-sub/streams, and TaskIQ as the async task queue. All choices have HIGH confidence with verified version numbers. Key corrections from research: TaskIQ has its own built-in scheduler (no APScheduler needed), dulwich replaces GitPython for programmatic git operations (pure Python, no system git dependency), and argon2-cffi is the correct password hashing choice (GPU-resistant, OWASP recommended).

**Core technologies:**
- **FastAPI 0.128 + Pydantic 2.12:** API server with native async, SSE, validation -- production-proven
- **PostgreSQL 16 + pgvector 0.8.2:** Single DB for relational data, vector search, RLS isolation, LTREE hierarchy -- eliminates need for separate vector DB at this scale
- **TaskIQ 0.12 + Redis 7:** Async-native task queue with built-in scheduling (cron + dynamic via Redis), replaces Celery/APScheduler entirely
- **React 19 + shadcn/ui + TanStack Router/Query:** Type-safe frontend with code-owned components, file-based routing, server state management
- **aiogram 3.26:** Fully async Telegram bot framework in webhook mode, integrated into FastAPI
- **Custom LLM Router:** ~50 lines using openai SDK with configurable base_url (Ollama-compatible), avoids compromised LiteLLM
- **dulwich 1.1:** Pure-Python git for agent memory versioning, no system git dependency

**Missing components identified:** websockets, redis[hiredis], structlog, tenacity, orjson, python-multipart (backend); lucide-react, sonner, recharts, cmdk (frontend). All are required or strongly recommended additions.

### Expected Features

**Must have (table stakes):**
- User registration and auth (JWT + Argon2id, httpOnly cookies)
- Knowledge domains with RLS isolation -- the core product promise
- Agent creation, configuration, and on-demand execution
- Telegram bot as primary mobile channel
- Web UI dashboard for deep work (not just chat)
- Agent memory persistence (MD + pgvector)
- Audit trail / event log from day one
- LLM routing with Ollama-first, OpenAI fallback
- Health MVP: medication reminders, weight tracking

**Should have (differentiators):**
- Agent debates (thesis-antithesis-synthesis) -- fixed cost (3 LLM calls), proven to reduce hallucinations
- Scheduled agent execution (cron) -- autonomous 24/7 work, the key differentiator vs ChatGPT
- Real-time updates (WebSocket + Redis Streams replay)
- Git-versioned agent knowledge -- unique vs all competitors

**Defer (v2+):**
- Reactive agents / proactive notifications -- needs event source infrastructure
- Semantic search across memory -- wait for data to accumulate
- Blood test analysis -- complex structured data entry UI
- Self-hosted Docker Compose packaging -- deploy manually first
- Domain templates, collaborative domains, git-versioned branching

### Architecture Approach

Modular monolith deployed in Docker Compose. Single FastAPI process with internal service boundaries (Auth, Domain, Agent, Debate, Memory, Event, LLM Router), TaskIQ workers as separate processes for background agent execution. PostgreSQL RLS is the architectural spine -- every data operation flows through domain context middleware that sets `SET LOCAL app.current_domain_id` before any query. Redis serves three roles in one instance: TaskIQ broker, WebSocket fan-out (Pub/Sub), event replay (Streams). Agent memory uses dual storage: git-versioned MD files as source of truth, pgvector as derived semantic search index.

**Major components:**
1. **FastAPI Application** -- REST API, WebSocket Hub, Telegram webhook handler, domain context middleware
2. **TaskIQ Workers** -- agent execution (on-demand, cron, reactive), debate orchestration, event fan-out
3. **PostgreSQL 16 + RLS** -- primary data store, domain isolation at database level, pgvector for semantic search
4. **Redis 7** -- task broker, pub/sub for real-time, Streams for event replay (24h TTL)
5. **LLM Router** -- Ollama via WireGuard (free, private), OpenAI fallback (reliability), health check + auto-switch
6. **Git Memory Store** -- MD files organized by domain, dulwich for programmatic commits/diffs

### Critical Pitfalls

1. **Domain data hardcoded in agent logic** -- The #1 risk. Agent prompts, health schemas, thresholds baked into Python code instead of DB/config. Prevention: agent config lives in JSONB, prompts are templates with domain-scoped variables, gate check "if I replace Health with Finance, does this code change?"
2. **RLS policies that leak data** -- Superuser testing bypasses RLS, missing WITH CHECK allows cross-domain writes, FORCE ROW LEVEL SECURITY not applied. Prevention: dedicated `app_user` role, both USING and WITH CHECK on every policy, integration tests that prove isolation
3. **RLS performance degradation** -- Non-LEAKPROOF functions prevent index usage, cascading policies multiply cost. Prevention: index every `domain_id`, SECURITY DEFINER functions, benchmark with EXPLAIN ANALYZE during development
4. **WireGuard tunnel drops kill LLM access** -- Silent failure overnight, agents stop working. Prevention: <5s timeout on Ollama, automatic OpenAI fallback, health check every 30s, DynDNS for home server
5. **Context window overflow** -- Agent memory grows without bounds, LLM silently drops early context, gives progressively worse advice. Prevention: token budget system per prompt section, memory summarization (daily -> weekly -> monthly), pgvector for retrieval not dump
6. **Custom JWT security holes** -- alg:none acceptance, missing claim validation, no token revocation. Prevention: pin HS256, validate all claims, refresh token rotation, revocation list in Redis

## Implications for Roadmap

Based on research, the architecture has clear dependency chains that dictate a 6-phase build order.

### Phase 1: Foundation (Infrastructure + Auth + Schema)
**Rationale:** Everything depends on PostgreSQL with RLS and authentication. Cannot build anything meaningful without domain-scoped data access and user identity.
**Delivers:** Working Docker Compose environment, PostgreSQL with RLS policies, Redis, Auth service (JWT + Argon2id), FastAPI skeleton with domain context middleware, WireGuard tunnel to home server with Ollama.
**Addresses features:** Registration/auth, domain isolation (schema), LLM routing (infrastructure).
**Avoids pitfalls:** JWT vulnerabilities (Pitfall 6) -- security test suite from day one; RLS gaps (Pitfall 2) -- never test with superuser; Docker resource limits (Pitfall 15).

### Phase 2: Domain Management + Basic Web UI
**Rationale:** Agents live inside domains. Domain CRUD and membership must work before agent infrastructure. Web UI needed to manage domains visually.
**Delivers:** Domain creation/listing, member invitation (owner/member/viewer), RLS isolation verification tests, React SPA with auth screens and domain management.
**Addresses features:** Domain creation with RLS, domain member invitation, basic Web UI.
**Avoids pitfalls:** RLS performance (Pitfall 3) -- index all RLS columns; JSONB drift (Pitfall 14) -- Pydantic validation from start.

### Phase 3: Agent Infrastructure + LLM Router
**Rationale:** The core product value -- agents that execute. Requires domains (Phase 2) and LLM access (Phase 1 WireGuard). TaskIQ workers must set the same domain context as HTTP middleware.
**Delivers:** Agent CRUD, LLM router with Ollama/OpenAI fallback and health checks, TaskIQ worker with domain context injection, on-demand agent execution, Memory Service (MD + git + basic pgvector), Event Service (audit log).
**Addresses features:** Agent creation/configuration, on-demand execution, agent memory persistence, LLM routing, event log.
**Avoids pitfalls:** Hardcoded domain logic (Pitfall 1) -- config-driven agents from first line; WireGuard drops (Pitfall 4) -- auto-fallback; Ollama cold start (Pitfall 7) -- KEEP_ALIVE=-1; Pool exhaustion (Pitfall 8) -- explicit pool limits.

### Phase 4: Communication Channels (Telegram + WebSocket)
**Rationale:** Agent execution engine must work (Phase 3) before connecting delivery mechanisms. Telegram is primary mobile channel; WebSocket provides real-time Web UI updates. Both are transport layers over the same service logic.
**Delivers:** Telegram webhook integration with aiogram, thin handlers routing to service layer, WebSocket Hub with Redis Pub/Sub, event replay from Redis Streams on reconnect, real-time agent activity in Web UI.
**Addresses features:** Telegram bot integration, real-time updates, multi-channel unified context.
**Avoids pitfalls:** Fat Telegram handler anti-pattern -- thin handlers only; Webhook security (Pitfall 12) -- secret_token + IP whitelist at nginx; WebSocket reconnection (Pitfall 11) -- Redis Streams replay.

### Phase 5: Debates + Autonomous Agents
**Rationale:** Debates need both agent execution (Phase 3) and notification delivery (Phase 4) to be useful. Cron scheduling builds on TaskIQ infrastructure from Phase 3.
**Delivers:** Debate orchestrator (thesis/antithesis/synthesis), debate transparency UI (summary + full log drill-down), cron-scheduled agent execution via TaskIQ Scheduler, debate view in Web UI and Telegram.
**Addresses features:** Agent debates, debate transparency, scheduled execution, autonomous 24/7 work.
**Avoids pitfalls:** Debate quality degradation (Pitfall 9) -- role enforcement, temperature differentiation, critic isolation; Duplicate cron fires (Pitfall 13) -- distributed lock; Context overflow (Pitfall 5) -- token budget system.

### Phase 6: Health Domain MVP
**Rationale:** Domain-specific features use ALL infrastructure built in Phases 1-5. Building the Health domain validates the entire system end-to-end.
**Delivers:** Health-specific agent templates (medication advisor, weight tracker, lab analyst), weight tracking with trend charts, medication reminders via Telegram cron, dashboard with health metrics and agent activity, memory summarization pipeline.
**Addresses features:** Medication reminders, weight tracking, blood test analysis (basic), domain templates (first one).
**Avoids pitfalls:** Hardcoded health logic (Pitfall 1) -- all health-specific data in DB/config, gate check before every commit; MD file growth (Pitfall 10) -- summarization lifecycle from start.

### Phase Ordering Rationale

- **Security first:** RLS and auth are non-negotiable prerequisites -- a data leak destroys trust permanently
- **Infrastructure before features:** Docker Compose, PostgreSQL, Redis, WireGuard must be solid before building on top
- **Domains before agents:** Agents are domain-scoped; the container must exist before contents
- **Engine before transport:** Agent execution logic is shared between Telegram and Web -- build once, deliver twice
- **Channels before debates:** Debates produce output that needs delivery; useless without notification
- **Domain-specific last:** Health MVP exercises all infrastructure; if something is broken, better to discover it in generic layers

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Agent Infrastructure):** TaskIQ worker patterns with domain context injection need prototype validation. Token budget system for context window management is not a standard pattern -- needs design.
- **Phase 5 (Debates):** Thesis-antithesis-synthesis orchestration is a novel pattern. Hegelion framework exists as reference but production implementation needs experimentation with prompt engineering, temperature tuning, and quality metrics.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** JWT auth, PostgreSQL RLS, Docker Compose, FastAPI skeleton -- extensively documented, established patterns.
- **Phase 2 (Domain Management):** CRUD operations, RLS verification, basic React SPA -- standard web development.
- **Phase 4 (Communication Channels):** aiogram webhook integration, WebSocket with Redis Pub/Sub -- well-documented with official examples.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified against PyPI/npm, LiteLLM compromise confirmed by Datadog, every library actively maintained |
| Features | HIGH | Multiple sources (CrewAI, AutoGPT, Agent Zero, health AI products), validated against existing platforms |
| Architecture | HIGH | RLS patterns from AWS/Permit.io/Nile docs, TaskIQ architecture from official docs, debate pattern from Microsoft Research + ICLR 2025 |
| Pitfalls | HIGH | RLS footguns from Bytebase/PortSwigger, JWT attacks extensively documented, WireGuard limitations confirmed, context overflow is universal LLM problem |

**Overall confidence:** HIGH

### Gaps to Address

- **TaskIQ scheduling at runtime:** ListRedisScheduleSource for dynamic user-configurable schedules is documented but not widely used in production. Validate during Phase 3 planning with a prototype.
- **Debate quality metrics:** No established framework for measuring thesis-antithesis-synthesis debate quality. Need to define metrics (critic disagreement rate, synthesis reference count) during Phase 5 planning.
- **Memory summarization pipeline:** The tiered memory approach (hot/warm/cold) is sound in theory but implementation details (when to summarize, how to preserve critical facts) need design during Phase 4.
- **react-shiki maturity:** MEDIUM confidence -- relatively new library for syntax highlighting in React. May need fallback to rehype-shiki or highlight.js if issues arise.
- **Ollama concurrent throughput:** At 70 users, peak concurrent LLM requests could reach 5-10. Single GPU handles 1-2 concurrent. Need to validate TaskIQ priority queue + OpenAI overflow strategy during Phase 3.

## Sources

### Primary (HIGH confidence)
- [FastAPI 0.128 Release Notes](https://fastapi.tiangolo.com/release-notes/) -- SSE, streaming, async
- [PostgreSQL RLS -- AWS](https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security/) -- isolation patterns
- [PostgreSQL RLS -- Permit.io](https://www.permit.io/blog/postgres-rls-implementation-guide) -- implementation guide
- [RLS Footguns -- Bytebase](https://www.bytebase.com/blog/postgres-row-level-security-footguns/) -- security pitfalls
- [RLS Performance -- Scott Pierce](https://scottpierce.dev/posts/optimizing-postgres-rls/) -- LEAKPROOF, indexing
- [TaskIQ Architecture](https://taskiq-python.github.io/guide/architecture-overview.html) -- scheduling, workers
- [JWT Attacks -- PortSwigger](https://portswigger.net/web-security/jwt) -- security testing
- [LiteLLM Compromise -- Datadog](https://securitylabs.datadoghq.com/articles/litellm-compromised-pypi-teampcp-supply-chain-campaign/) -- supply chain attack
- [Multi-Agent Debate -- ICLR 2025](https://d2jud02ci9yv69.cloudfront.net/2025-04-28-mad-159/blog/mad/) -- debate effectiveness
- [Hegelian Dialectic LLMs -- Microsoft Research](https://www.microsoft.com/en-us/research/wp-content/uploads/2025/02/2501.14917v3.pdf) -- debate framework
- [aiogram Webhook Docs](https://docs.aiogram.dev/en/latest/dispatcher/webhook.html) -- security, integration
- [pgvector 0.8.2 Release](https://www.postgresql.org/about/news/pgvector-082-released-3245/) -- vector search
- [Tailwind CSS v4](https://tailwindcss.com/blog/tailwindcss-v4) -- CSS-first config
- [shadcn/ui CLI v4](https://ui.shadcn.com/docs/changelog) -- Vite scaffold support

### Secondary (MEDIUM confidence)
- [DiffMem: Git-Based Agent Memory](https://github.com/Growth-Kinetics/DiffMem) -- memory architecture reference
- [Hegelion Framework](https://github.com/Hmbown/Hegelion) -- debate implementation reference
- [Multi-tenant isolation -- Nile](https://www.thenile.dev/blog/multi-tenant-rls) -- RLS patterns
- [Real-time with FastAPI + Redis Streams](https://dev.to/geetnsh2k1/building-a-real-time-notification-service-with-fastapi-redis-streams-and-websockets-52ib) -- WebSocket patterns
- [AI Agent Memory -- Markdown Files](https://dev.to/imaginex/ai-agent-memory-management-when-markdown-files-are-all-you-need-5ekk) -- MD memory validation
- [Multi-Agent Error Trap](https://towardsdatascience.com/why-your-multi-agent-system-is-failing-escaping-the-17x-error-trap-of-the-bag-of-agents/) -- debate quality risks
- [Context Window Overflow -- Redis](https://redis.io/blog/context-window-overflow/) -- memory management
- [WireGuard Keepalive Issues](https://github.com/pirate/wireguard-docs/issues/35) -- tunnel reliability
- [TaskIQ Connection Pool Issue #368](https://github.com/taskiq-python/taskiq/issues/368) -- worker pooling

### Tertiary (LOW confidence)
- [react-shiki](https://github.com/AVGVSTVS96/react-shiki) -- relatively new, limited production reports

---
*Research completed: 2026-03-27*
*Ready for roadmap: yes*
