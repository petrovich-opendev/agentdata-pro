# Domain Pitfalls

**Domain:** Multi-agent AI workspace (personal AI OS with domain isolation)
**Researched:** 2026-03-27

---

## Critical Pitfalls

Mistakes that cause rewrites, data breaches, or project failure.

### Pitfall 1: Domain Data Hardcoded in Agent Logic (THE #1 RISK)

**What goes wrong:** Agent prompts, tool configs, health domain schemas, medication names, analysis thresholds -- all get baked into Python code instead of stored in DB/config. When a second domain (Finance, Fitness) arrives, the codebase is riddled with Health-specific assumptions that require rewrites.

**Why it happens:** During MVP development with a single domain (Health), it feels faster to put domain-specific logic directly in code. "I'll refactor later" never happens. LLM-generated code defaults to hardcoding because training data is full of examples with literals.

**Consequences:**
- Every new domain requires code changes instead of configuration
- Agent prompts contain domain assumptions that break when reused
- Business rules (medication schedules, weight thresholds) buried in source code can't be changed by users
- Violates the core product promise: "create any domain with custom agents"

**Prevention:**
- Phase 1 architecture must define: Agent config lives in `agents` table (JSONB), domain rules live in DB, prompts are templates with domain-scoped variables
- Every agent tool must accept domain context from DB, never from imports
- Gate check: "If I replace Health with Finance, does this code change?" If yes -- it's hardcoded
- Automated lint: grep for domain-specific terms (medication, weight, supplement) in Python source files

**Detection:** Code review flag: any string literal that mentions a domain concept. Any `if domain == "health"` branch.

**Phase relevance:** Phase 1 (Architecture/Schema). Must be enforced from the first line of code.

**Confidence:** HIGH -- based on 3 real incidents in Petrovich's project history.

---

### Pitfall 2: RLS Policies That Look Secure But Leak Data

**What goes wrong:** PostgreSQL Row-Level Security is configured but has subtle gaps: testing with superuser accounts (which bypass RLS), missing `WITH CHECK` clauses allowing inserts into wrong domains, or `FORCE ROW LEVEL SECURITY` not applied to table owners. A domain member sees data from another domain.

**Why it happens:** RLS is counterintuitive. Superusers and table owners bypass RLS by default. Developers test with admin credentials, see correct behavior, ship to production where a regular user's session crosses domain boundaries. The `USING` clause filters reads but `WITH CHECK` (for writes) is often forgotten.

**Consequences:**
- Complete violation of the core product promise (domain isolation)
- Users' health data visible to other users
- Trust destruction -- if discovered, no one uses the platform again
- Potential legal liability (health data is sensitive)

**Prevention:**
- Never test RLS with superuser. Create a dedicated `app_user` role from day one
- Apply `ALTER TABLE ... FORCE ROW LEVEL SECURITY` to every RLS-protected table so even the table owner is subject to policies
- Every RLS policy must have BOTH `USING` and `WITH CHECK` clauses
- Set `current_setting('app.current_domain_id')` at the start of every DB session via connection middleware -- never rely on application-level filtering
- Integration tests that attempt cross-domain access and MUST fail

**Detection:** Test suite with two users in two domains. Every query is tested for isolation. CI blocks merge if cross-domain test is missing for new tables.

**Phase relevance:** Phase 1-2 (Database schema + Auth). RLS must be correct before any agent writes data.

**Confidence:** HIGH -- [well-documented PostgreSQL pitfall](https://www.bytebase.com/blog/postgres-row-level-security-footguns/).

---

### Pitfall 3: RLS Performance Degradation at Scale

**What goes wrong:** RLS policies use non-LEAKPROOF functions or subqueries that prevent index usage. Every row returned triggers a separate function call. With 70 users, multiple domains, and agents writing constantly, queries that were fast with 10 users become unacceptably slow.

**Why it happens:** RLS policies are invisible to developers writing application queries. The query planner cannot push RLS predicates through non-LEAKPROOF functions, forcing sequential scans. Cascading RLS policies (policy A references table B which also has RLS) multiply the cost.

**Consequences:**
- Agent tasks that should take 2 seconds take 30 seconds
- Dashboard loading times degrade as data grows
- Temptation to "just disable RLS for performance" -- destroying the security model

**Prevention:**
- Index every column used in RLS policies (`domain_id` on every table, always indexed)
- Use `SECURITY DEFINER` functions for RLS policies to avoid cascading policy evaluation
- Mark helper functions as `LEAKPROOF` where safe to do so
- Benchmark RLS queries with `EXPLAIN ANALYZE` during development, not after deployment
- Profile with realistic data volumes (simulate 70 users, 20 domains, 100K events)

**Detection:** Monitor slow query log. Alert on queries over 500ms. Periodic `EXPLAIN ANALYZE` on critical paths.

**Phase relevance:** Phase 2 (Schema implementation). Indexes and LEAKPROOF design must be baked in from the start.

**Confidence:** HIGH -- [documented by multiple sources](https://scottpierce.dev/posts/optimizing-postgres-rls/).

---

### Pitfall 4: WireGuard Tunnel Drops Kill LLM Access Silently

**What goes wrong:** The VPS-to-Home-Server WireGuard tunnel drops (ISP IP change, NAT timeout, router reboot). All LLM requests to Ollama silently fail or hang. Agents stop working. No one notices for hours because there's no health check -- the system just queues tasks that never complete.

**Why it happens:** WireGuard doesn't handle dynamic IP changes. PersistentKeepalive (25s) keeps NAT alive but cannot recover from IP changes. Home server ISPs typically provide dynamic IPs. A 3AM router reboot means agents are dead until manual intervention.

**Consequences:**
- All autonomous (cron) agent work stops overnight -- the core value proposition
- Tasks queue up in Redis, creating a burst of LLM requests when tunnel recovers
- User wakes up to zero agent output instead of morning briefing
- If fallback to OpenAI isn't automatic, health domain medication reminders don't fire

**Prevention:**
- LLM router MUST implement automatic OpenAI fallback with <5s timeout on Ollama connection
- Health check endpoint on Ollama: ping every 30 seconds, alert on 2 consecutive failures
- WireGuard auto-reconnect script with DNS re-resolution (reresolve-dns.sh pattern)
- DynDNS or Cloudflare tunnel as alternative to raw WireGuard for home server
- Never make Ollama the only path. OpenAI is the safety net, Ollama is the cost optimizer

**Detection:** Uptime Kuma monitoring Ollama endpoint through WireGuard. Telegram alert on failure. Dashboard showing LLM routing stats (local vs cloud ratio).

**Phase relevance:** Phase 3-4 (LLM integration + Agent runtime). Must be designed before agents go autonomous.

**Confidence:** HIGH -- [well-known WireGuard limitation](https://github.com/pirate/wireguard-docs/issues/35), and Petrovich already runs VPN infrastructure.

---

### Pitfall 5: Context Window Overflow in Agent Memory

**What goes wrong:** Agents accumulate memory (MD files, past debates, domain knowledge). When constructing LLM prompts, the system dumps everything into context. A Health agent with 6 months of weight data, medication history, and debate logs exceeds the context window. The LLM silently drops early context, loses medication interactions, and gives dangerous advice.

**Why it happens:** During MVP with one user and one domain, context fits easily. Growth is invisible -- each daily weight entry adds tokens, each debate adds thousands. No one tracks cumulative context size. Local models (Qwen 14B) have smaller context windows than GPT-4, making this hit earlier.

**Consequences:**
- Agent "forgets" critical health information (medication interactions, allergies)
- Debate quality degrades as agents can't reference full history
- Increased LLM costs (larger context = more tokens = higher OpenAI bills)
- Subtle: agent appears to work but gives progressively worse advice

**Prevention:**
- Token budget system: allocate fixed budgets per prompt section (system: 500, memory: 2000, conversation: 1500, tools: 1000)
- Implement memory summarization: weekly summaries replace daily entries older than 30 days
- Use pgvector for semantic retrieval: don't dump all memory, retrieve only relevant chunks
- Track token usage per agent invocation; alert when approaching 80% of model's context window
- Different memory tiers: hot (recent, full), warm (summarized), cold (archived, retrievable)

**Detection:** Log token count for every LLM call. Dashboard showing average/max context usage per agent. Alert when any call exceeds 80% of model limit.

**Phase relevance:** Phase 4 (Agent memory). Architecture decision needed before agents accumulate data.

**Confidence:** HIGH -- [universal LLM agent problem](https://redis.io/blog/context-window-overflow/).

---

### Pitfall 6: Custom JWT Auth Has Security Holes

**What goes wrong:** Custom JWT implementation (~260 lines per concept doc) has subtle vulnerabilities: accepting `alg: none`, weak secret keys, missing claim validation (iss, aud, exp), no token revocation mechanism, or refresh token reuse allowing session fixation.

**Why it happens:** JWT looks simple ("just sign a JSON blob"), but the specification has many attack vectors. Custom implementations miss edge cases that battle-tested libraries handle. The CONCEPT.md specifies httpOnly cookies and Argon2id (good), but doesn't mention algorithm pinning, token revocation, or refresh token rotation.

**Consequences:**
- Token forgery: attacker creates valid tokens for any user
- Session hijacking: stolen refresh token used indefinitely
- No logout: even after "logout", tokens remain valid until expiration
- AppSec audit failure (if this ever goes enterprise)

**Prevention:**
- Pin algorithm explicitly: `algorithms=["HS256"]` in every verify call, reject all others
- Use strong secret (256+ bits, generated with `secrets.token_hex(32)`)
- Validate ALL claims: `exp`, `iss`, `aud`, `sub`, `iat`
- Implement refresh token rotation: each use generates a new refresh token, old one is invalidated
- Store refresh tokens in DB with `revoked_at` column for forced logout
- Token revocation list in Redis (short-lived, only for active access tokens)
- Rate limit login endpoint: 5 attempts per minute per IP

**Detection:** Security test suite: attempt `alg: none`, expired tokens, tokens with wrong issuer. CI blocks merge if auth tests fail.

**Phase relevance:** Phase 1 (Auth). Must be correct before any data enters the system.

**Confidence:** HIGH -- [extensively documented attack surface](https://portswigger.net/web-security/jwt).

---

## Moderate Pitfalls

### Pitfall 7: Ollama Cold Start Kills User Experience

**What goes wrong:** Ollama unloads models from GPU after 5 minutes of inactivity (default). First request after idle period takes 10-30 seconds for model reload. User asks Telegram bot a question, waits 25 seconds for response. Feels broken.

**Prevention:**
- Set `OLLAMA_KEEP_ALIVE=-1` to pin primary model (Qwen 14B) permanently
- Pre-warm with empty request on startup/reconnect
- Show "thinking..." indicator in Telegram and WebSocket immediately
- Budget VRAM: pin Qwen 14B (~9GB), let Llama 8B load on-demand (~5GB), total fits 16GB

**Phase relevance:** Phase 3 (LLM routing).

**Confidence:** HIGH -- [documented Ollama behavior](https://markaicode.com/ollama-keep-alive-memory-management/).

---

### Pitfall 8: TaskIQ Connection Pool Exhaustion

**What goes wrong:** Multiple TaskIQ workers running concurrent agent tasks exhaust PostgreSQL connection pool. Error: "QueuePool limit exceeded". Agent tasks fail silently or retry indefinitely.

**Prevention:**
- Use connection pooling (PgBouncer or asyncpg pool) between TaskIQ workers and PostgreSQL
- Set explicit pool limits: max_size matching worker concurrency
- Each worker creates its own pool on startup (not shared from FastAPI process)
- Monitor active connections: `SELECT count(*) FROM pg_stat_activity`

**Phase relevance:** Phase 3 (Task queue setup).

**Confidence:** MEDIUM -- [reported in TaskIQ issues](https://github.com/taskiq-python/taskiq/issues/368), but manageable with proper pooling.

---

### Pitfall 9: Agent Debate Quality Degrades Without Guardrails

**What goes wrong:** The thesis-antithesis-synthesis pattern produces low-quality output: the critic agent agrees with the analyst instead of challenging, the synthesizer produces a generic summary, or all three agents hallucinate the same incorrect fact because they share the same flawed context.

**Prevention:**
- Explicit role enforcement in prompts: "You MUST find at least 2 weaknesses in the thesis"
- Temperature differentiation: analyst (0.3), critic (0.7), synthesizer (0.3)
- Critic receives thesis output but NOT the original prompt -- forces independent analysis
- Quality check: synthesizer must reference specific points from both thesis and antithesis
- Store debate quality metrics (did the critic actually disagree? did synthesis reference both sides?)
- Allow human override: "This debate was useless" -- feedback loop to improve prompts

**Phase relevance:** Phase 5 (Debate engine).

**Confidence:** MEDIUM -- pattern is novel, limited production data. Based on [multi-agent coordination research](https://towardsdatascience.com/why-your-multi-agent-system-is-failing-escaping-the-17x-error-trap-of-the-bag-of-agents/).

---

### Pitfall 10: MD Memory Files Become Unmanageable

**What goes wrong:** Git-versioned MD files grow without bounds. After 6 months, the `domains/health/memory/` directory has 500+ files. Git operations (clone, diff) become slow. Finding relevant context requires reading dozens of files. Agent memory retrieval becomes a performance bottleneck.

**Prevention:**
- Define file lifecycle: daily files auto-summarize into weekly, weekly into monthly
- Cap individual files at ~2000 tokens (easily fits in context window)
- Use pgvector index for semantic search over MD content -- don't scan files
- Git shallow clone for deployment (only recent history)
- Archive old files to cold storage (S3/MinIO) after 90 days
- Memory file naming convention: `YYYY-MM-DD_topic.md` for predictable sorting/cleanup

**Phase relevance:** Phase 4 (Agent memory architecture).

**Confidence:** MEDIUM -- projected from similar systems (Obsidian vaults, Claude memory).

---

### Pitfall 11: WebSocket Reconnection Loses Events

**What goes wrong:** User's browser loses WebSocket connection (mobile, network switch, laptop sleep). On reconnect, they miss events. Agent completed a task, debate finished -- UI shows stale state. User thinks system is broken.

**Prevention:**
- Store `last_event_id` on client (per the CONCEPT.md -- good)
- Redis Streams replay on reconnect (already planned -- implement correctly)
- Set reasonable TTL on Redis Streams (24h per concept, but test memory usage)
- Fallback: TanStack Query refetch on reconnect, not just cache invalidation
- Test: kill WebSocket mid-debate, verify reconnect shows complete state

**Phase relevance:** Phase 3 (Real-time architecture).

**Confidence:** HIGH -- standard WebSocket challenge, well-understood solutions.

---

### Pitfall 12: Telegram Bot Webhook Security

**What goes wrong:** Telegram webhook endpoint is publicly accessible. Attacker sends crafted payloads to `/webhook/telegram`, triggering agent actions or extracting data. `X-Forwarded-For` header is spoofed to bypass IP whitelist.

**Prevention:**
- Use Telegram's secret_token parameter (set on webhook registration, validate on every request)
- Whitelist Telegram's IP ranges (149.154.160.0/20, 91.108.4.0/22) at nginx level, NOT application level
- Never trust `X-Forwarded-For` unless behind trusted reverse proxy with header rewriting
- Rate limit webhook endpoint
- Validate message structure with Pydantic before processing

**Phase relevance:** Phase 2 (Telegram integration).

**Confidence:** HIGH -- [documented aiogram security practice](https://docs.aiogram.dev/en/latest/dispatcher/webhook.html).

---

## Minor Pitfalls

### Pitfall 13: APScheduler Cron Jobs Fire on All Workers

**What goes wrong:** When scaling to multiple TaskIQ workers, APScheduler cron triggers fire on every worker instance. Morning medication reminder sent 3 times.

**Prevention:**
- Use distributed lock (Redis-based) for scheduled tasks
- Or: run scheduler in a single dedicated process, not in workers
- Idempotency: every scheduled task checks "already executed today?" before running

**Phase relevance:** Phase 4 (Autonomous agents).

**Confidence:** MEDIUM -- standard distributed scheduling problem.

---

### Pitfall 14: JSONB Schema Drift

**What goes wrong:** Agent configs, task metadata, and domain settings stored in JSONB columns evolve without validation. Old records have `{"model": "qwen"}`, new ones have `{"llm": {"provider": "ollama", "model": "qwen2.5"}}`. Application code crashes on old format.

**Prevention:**
- Define JSONB schemas as Pydantic models with version field
- Migration function: `migrate_agent_config(data, from_version, to_version)`
- Validate JSONB on read (Pydantic), not just on write
- Never assume JSONB shape -- always use `.get()` with defaults

**Phase relevance:** Phase 2 (Schema design).

**Confidence:** HIGH -- universal JSONB problem.

---

### Pitfall 15: Docker Compose Resource Limits Not Set

**What goes wrong:** Ollama consumes all available RAM on home server. PostgreSQL OOM-killed during peak agent activity. Redis evicts task results because no memory limit. System becomes unstable under load.

**Prevention:**
- Set explicit `mem_limit` and `cpus` for every service in docker-compose.yml
- PostgreSQL: `shared_buffers`, `work_mem`, `max_connections` tuned for VPS (8GB RAM)
- Redis: `maxmemory` + `maxmemory-policy allkeys-lru`
- Ollama: `OLLAMA_MAX_LOADED_MODELS=1` on 16GB VRAM to prevent multi-model OOM

**Phase relevance:** Phase 1 (Infrastructure setup).

**Confidence:** HIGH -- operational standard.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Phase 1: Auth + Schema | JWT vulnerabilities (Pitfall 6), RLS gaps (Pitfall 2) | Security test suite from day one, never test with superuser |
| Phase 1: Infrastructure | Docker resource limits (Pitfall 15) | Set limits in initial docker-compose.yml |
| Phase 2: Domain isolation | RLS performance (Pitfall 3), JSONB drift (Pitfall 14) | Index all RLS columns, Pydantic for JSONB |
| Phase 2: Telegram | Webhook security (Pitfall 12) | Secret token + IP whitelist at nginx |
| Phase 3: LLM routing | WireGuard drops (Pitfall 4), cold start (Pitfall 7) | Auto-fallback to OpenAI, pin Ollama model |
| Phase 3: Task queue | Pool exhaustion (Pitfall 8), duplicate cron (Pitfall 13) | PgBouncer, distributed locks |
| Phase 4: Agent memory | Context overflow (Pitfall 5), MD file growth (Pitfall 10) | Token budgets, summarization pipeline |
| Phase 4: Agents runtime | Hardcoded domain logic (Pitfall 1) | Config-driven agents, gate check |
| Phase 5: Debates | Quality degradation (Pitfall 9) | Role enforcement, temperature tuning |
| Real-time | WebSocket gaps (Pitfall 11) | Redis Streams replay, TanStack Query refetch |

---

## Sources

- [Bytebase: Common PostgreSQL RLS Footguns](https://www.bytebase.com/blog/postgres-row-level-security-footguns/)
- [Bytebase: PostgreSQL RLS Limitations and Alternatives](https://www.bytebase.com/blog/postgres-row-level-security-limitations-and-alternatives/)
- [Scott Pierce: Optimizing Postgres RLS for Performance](https://scottpierce.dev/posts/optimizing-postgres-rls/)
- [Permit.io: Postgres RLS Implementation Guide](https://www.permit.io/blog/postgres-rls-implementation-guide)
- [PortSwigger: JWT Attacks](https://portswigger.net/web-security/jwt)
- [Authgear: JWT Security Best Practices](https://www.authgear.com/post/jwt-security-best-practices-common-vulnerabilities)
- [Redis: Context Window Overflow](https://redis.io/blog/context-window-overflow/)
- [Towards Data Science: Multi-Agent 17x Error Trap](https://towardsdatascience.com/why-your-multi-agent-system-is-failing-escaping-the-17x-error-trap-of-the-bag-of-agents/)
- [Composio: Why AI Agent Pilots Fail](https://composio.dev/blog/why-ai-agent-pilots-fail-2026-integration-roadmap)
- [Markaicode: Ollama Keep-Alive Memory Management](https://markaicode.com/ollama-keep-alive-memory-management/)
- [TaskIQ: DB Connection Pool Issue #368](https://github.com/taskiq-python/taskiq/issues/368)
- [aiogram: Webhook Documentation](https://docs.aiogram.dev/en/latest/dispatcher/webhook.html)
- [WireGuard: Keepalive Issues](https://github.com/pirate/wireguard-docs/issues/35)
- [Sendbird: 10 Agentic AI Challenges](https://sendbird.com/blog/agentic-ai-challenges)
