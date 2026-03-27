# Roadmap: AgentData.pro

## Overview

AgentData.pro delivers a personal AI operating system with autonomous agents working 24/7 in domain-isolated knowledge silos. The build follows the dependency chain: security foundation (RLS + Auth) enables domains, domains enable agents, agents need LLM and communication channels, channels enable debates, and the Health domain MVP validates everything end-to-end. Each phase delivers a coherent, verifiable capability that builds on the previous.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - Docker Compose infra, PostgreSQL with RLS schema, Auth service (JWT + Argon2id), FastAPI skeleton, audit log
- [ ] **Phase 2: Domain Management** - Domain CRUD with RLS isolation, member invitation, domain switching, basic React SPA with auth and domain screens
- [ ] **Phase 3: Agent Engine** - Agent CRUD, LLM router (Ollama/OpenAI), on-demand execution via TaskIQ, MD memory with git versioning, pgvector semantic search, token budget
- [ ] **Phase 4: Communication Channels** - Telegram bot (aiogram webhook), WebSocket real-time updates, Redis Streams replay, PWA service worker
- [ ] **Phase 5: Debates + Autonomous Agents** - Thesis-antithesis-synthesis debates, cron-scheduled agent execution, debate transparency UI
- [ ] **Phase 6: Health Domain MVP** - Weight tracking (Telegram input + Web chart), medication reminders, Health Advisor agent, weekly health debates, deals search, food diary

## Phase Details

### Phase 1: Foundation
**Goal**: Users can register, authenticate, and the system enforces domain-level data isolation at the database layer from day one
**Depends on**: Nothing (first phase)
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUD-01
**Success Criteria** (what must be TRUE):
  1. User can register with email/password and receive JWT tokens (access + refresh)
  2. User can log in, stay logged in across browser sessions via refresh token, and log out
  3. User can reset forgotten password via email link
  4. Login endpoint rejects requests after 5 failed attempts per minute from same IP
  5. Every user action is recorded in an append-only event log partitioned by month
**Plans**: TBD

Plans:
- [ ] 01-01: Docker Compose + PostgreSQL + Redis + FastAPI skeleton
- [ ] 01-02: Auth service (registration, login, refresh, password reset, rate limiting)
- [ ] 01-03: RLS schema + domain context middleware + audit event log

### Phase 2: Domain Management
**Goal**: Users can create isolated knowledge domains, invite participants, and manage everything through a Web UI
**Depends on**: Phase 1
**Requirements**: DOM-01, DOM-02, DOM-03, DOM-04, UI-02
**Success Criteria** (what must be TRUE):
  1. User can create, rename, and delete a knowledge domain
  2. Data in one domain is completely invisible to queries from another domain (RLS enforced, verified by integration tests)
  3. Domain owner can invite members with owner/member/viewer roles
  4. User can switch between domains in the Web UI and see only active domain's data
  5. React SPA loads with auth screens (login/register) and domain management (list, create, switch, members)
**Plans**: TBD

Plans:
- [ ] 02-01: Domain CRUD API + RLS isolation verification tests
- [ ] 02-02: Domain membership (invitation, roles, switching)
- [ ] 02-03: React SPA scaffold + auth screens + domain management UI

### Phase 3: Agent Engine
**Goal**: Users can create config-driven agents that execute tasks on demand, route through LLM providers, and persist knowledge in git-versioned memory
**Depends on**: Phase 2
**Requirements**: AGT-01, AGT-02, LLM-01, LLM-02, LLM-03, LLM-04
**Success Criteria** (what must be TRUE):
  1. User can create an agent with role, system prompt, tools config, and domain binding -- all stored in DB/JSONB, not code
  2. User can give a task to an agent and receive a structured result (on-demand execution via TaskIQ worker)
  3. LLM requests route to Ollama first, auto-fallback to OpenAI if Ollama is unavailable within 5 seconds
  4. Agent knowledge, research, and results are persisted as git-versioned MD files with commit history
  5. User can search agent memory semantically via pgvector embeddings
**Plans**: TBD

Plans:
- [ ] 03-01: Agent CRUD API + config-driven agent model (JSONB)
- [ ] 03-02: LLM router (Ollama + OpenAI fallback + health check) + token budget
- [ ] 03-03: TaskIQ worker with domain context + on-demand agent execution
- [ ] 03-04: Memory service (MD files + dulwich git + pgvector semantic search)

### Phase 4: Communication Channels
**Goal**: Users receive agent results and notifications through Telegram and real-time Web UI, with consistent experience across both channels
**Depends on**: Phase 3
**Requirements**: UI-01, UI-03, UI-04
**Success Criteria** (what must be TRUE):
  1. Telegram bot receives webhook messages, routes commands to service layer, and delivers agent results back to user
  2. Web UI shows real-time agent activity (progress, results, notifications) via WebSocket without page refresh
  3. On WebSocket reconnect, missed events replay from Redis Streams (no lost updates)
  4. Web app installs as PWA with service worker and push notifications on mobile
**Plans**: TBD

Plans:
- [ ] 04-01: Telegram bot (aiogram webhook + thin handlers + domain binding)
- [ ] 04-02: WebSocket hub + Redis Pub/Sub fan-out + Streams replay
- [ ] 04-03: PWA (service worker, push notifications, app manifest)

### Phase 5: Debates + Autonomous Agents
**Goal**: Agents can debate each other (thesis-antithesis-synthesis) and work autonomously on schedules, delivering results through all channels
**Depends on**: Phase 4
**Requirements**: AGT-03, AGT-04
**Success Criteria** (what must be TRUE):
  1. Three agents conduct a structured debate (thesis, antithesis, synthesis) producing a summary and full log viewable in Web UI and Telegram
  2. User can configure an agent to run on a cron schedule (e.g., daily at 08:00) and receive results automatically
  3. Debate log shows each step with role attribution, and user can drill down from summary to full transcript
**Plans**: TBD

Plans:
- [ ] 05-01: Debate orchestrator (thesis/antithesis/synthesis pipeline + quality controls)
- [ ] 05-02: Cron-scheduled agent execution (TaskIQ scheduler + distributed lock)
- [ ] 05-03: Debate UI (summary cards, drill-down transcript, Telegram formatting)

### Phase 6: Health Domain MVP
**Goal**: Health domain validates the entire system end-to-end -- user tracks health data via Telegram, receives proactive reminders, gets AI analysis and debates, all within an isolated domain
**Depends on**: Phase 5
**Requirements**: HP-01, HP-02, HP-03, HP-04, HP-05, HP-06
**Success Criteria** (what must be TRUE):
  1. User sends weight via Telegram message, sees trend graph in Web UI dashboard
  2. Cron agent sends morning medication/vitamin schedule to user's Telegram at configured time
  3. Health Advisor agent analyzes weight trend and provides personalized recommendations
  4. Weekly health debate runs automatically (analyst vs critic vs synthesizer) with viewable results
  5. Deals agent searches and reports discounts on medications, food, and lab tests in user's city
**Plans**: TBD

Plans:
- [ ] 06-01: Health data models + weight tracking (Telegram input + trend chart)
- [ ] 06-02: Health agents (medication reminder, advisor, deals searcher) -- all config-driven
- [ ] 06-03: Weekly health debate + food diary with nutrient analysis

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/3 | Not started | - |
| 2. Domain Management | 0/3 | Not started | - |
| 3. Agent Engine | 0/4 | Not started | - |
| 4. Communication Channels | 0/3 | Not started | - |
| 5. Debates + Autonomous Agents | 0/3 | Not started | - |
| 6. Health Domain MVP | 0/3 | Not started | - |
