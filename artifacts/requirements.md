# Knowledge Domains Platform — Requirements (MVP)

> Business requirements for MVP delivery.
> Platform: Knowledge Domains PaaS.
> First domain: BioCoach (personal health advisor).

---

## 1. Business Goal

**Построить платформу "Домены Знаний" (PaaS) для создания изолированных
AI-рабочих пространств с доменными агентами. Первый домен — BioCoach
(персональный AI-советник по здоровью) — валидирует платформу на реальных
пользователях.**

### Platform vs Domain

| Platform (universal code) | Domain "BioCoach" (configuration) |
|--------------------------|-----------------------------------|
| Auth (Telegram + JWT) | System prompt: health advisor |
| Knowledge domains CRUD | Agent config: RouterAgent + SearchAgent |
| Chat (streaming, history, trimming) | Search categories: pharmacy, labs, supplements |
| Agent framework (BaseAgent + NATS) | UI theme / disclaimer text |
| RLS data isolation | Language: Russian + English medical terms |
| Session management | Follow-up suggestion style |

**Rule: if the code contains "health", "pharmacy", "lab result" — it is domain
configuration, not platform code.**

### MVP Scope

We build the **platform**, but validate every decision through **one concrete
domain** (BioCoach). We do NOT build a domain-creation UI — the BioCoach domain
is seeded via a migration script. But the architecture must allow adding a new
domain type (e.g., "FinanceAdvisor") by inserting a row into the database, not
by changing platform code.

---

## 2. User Stories

### US-1: Registration via Telegram

**As a** new user
**I want to** register using my Telegram username
**So that** I get access to my personal cabinet without passwords

**Flow:**
1. User opens web portal
2. Clicks "Register" / "Login"
3. Enters their Telegram @username
4. System sends a 6-digit confirmation code to Telegram DM via bot
5. User enters the code on the web portal
6. System creates account + auto-creates personal domain (type from config)
7. User is redirected to personal cabinet

**Acceptance Criteria:**
- [ ] Confirmation code expires in 5 minutes
- [ ] Max 5 code requests per hour per IP (rate limiting)
- [ ] After successful auth, user does not need to re-confirm for 30 days (refresh token)
- [ ] JWT access token: 30 minutes, refresh token: 30 days (HttpOnly cookie)
- [ ] Only Telegram @username is stored (pseudonymous)
- [ ] Personal domain auto-created with type and config from platform settings

---

### US-2: Personal Cabinet (Knowledge Domain)

**As a** registered user
**I want to** see my personal cabinet after login
**So that** I can interact with the AI advisor configured for my domain

**Acceptance Criteria:**
- [ ] Each user has exactly one personal knowledge domain (auto-created at registration)
- [ ] Cabinet shows: chat interface (primary), session history (sidebar)
- [ ] Data isolation: user can only see their own data (PostgreSQL RLS)
- [ ] Mobile-responsive layout
- [ ] Domain name and disclaimer loaded from domain config (not hardcoded)

---

### US-3: AI Chat (Streaming)

**As a** user in my personal cabinet
**I want to** chat with an AI advisor in real-time
**So that** I get domain-specific advice and recommendations

**Acceptance Criteria:**
- [ ] Streaming responses (SSE) — tokens appear as they are generated
- [ ] Multi-turn conversation with context
- [ ] Chat history persisted in PostgreSQL
- [ ] Long conversation history is trimmed (sliding window or summarization) to fit LLM context
- [ ] System prompt loaded from domain config (not hardcoded in code)
- [ ] AI language and behavior defined by domain config
- [ ] Disclaimer text from domain config (not in every message, but visible in UI)
- [ ] Follow-up suggestions after each AI response (3 clickable options)

---

### US-4: Search Agent

**As a** user chatting with AI
**I want to** search for information relevant to my domain
**So that** I get real data (prices, sources, links) instead of hallucinations

**Flow:**
1. User asks a question in chat
2. AI detects search intent (via RouterAgent) or user clicks a search button
3. SearchAgent queries SearXNG with domain-configured search parameters
4. Results are displayed inline in chat (structured cards)

**Acceptance Criteria:**
- [ ] SearchAgent triggered by RouterAgent (intent detection) or explicit user action
- [ ] Searches via SearXNG (self-hosted, JSON API)
- [ ] Search query template, language, and categories come from domain config
- [ ] Results include: item name, snippet, source, URL
- [ ] No hallucinated data — only real search results
- [ ] Search results clearly marked as external data
- [ ] Agent communicates via NATS JetStream with the main chat service

**BioCoach domain config for SearchAgent:**
- Search language: `ru`
- Search categories: `general`
- Query enhancement: append price/buy keywords for pharmacy intent
- Result format: name, price (if found), pharmacy/lab name, URL

---

### US-5: Session Management

**As a** user
**I want to** start new chat sessions and see my history
**So that** I can organize my conversations

**Acceptance Criteria:**
- [ ] User can create a new chat session
- [ ] Session list displayed in sidebar (title, date)
- [ ] User can switch between sessions
- [ ] Session title auto-generated from first message (via LLM)
- [ ] Soft-delete sessions (mark as deleted, keep for analytics)

---

## 3. Non-Functional Requirements

### Security
- No plaintext credentials in code (env vars only)
- Input validation on all API endpoints (Pydantic)
- Parameterized SQL queries only (asyncpg with params)
- Rate limiting on auth endpoints
- HTTPS only (nginx + Let's Encrypt)
- CORS restricted to portal domain

### Performance
- Chat response start (first token): < 2 seconds
- Search results: < 10 seconds
- Page load (initial): < 3 seconds
- Support 10 concurrent users (MVP scale)

### Observability
- Langfuse integration for LLM tracing (prompt versions, costs, latency)
- Structured logging (JSON) to stdout
- Health check endpoint: GET /api/health

### Data
- PostgreSQL 16 as single data store
- JSONB for domain config and future graph-like relationships
- Conversation history with token counts
- All timestamps in UTC

### Platform Extensibility
- Adding a new domain type requires: one DB row (domain_types) + prompt file — zero code changes
- Agent framework: new agent = new Python class extending BaseAgent + DB registration
- All domain-specific behavior (prompts, search config, agent set) stored in DB, not in code

---

## 4. Out of Scope (MVP)

- [ ] Lab result upload (PDF/photo) — Phase 2 (separate agents: VisionAgent, LabAgent)
- [ ] PharmaAgent (drug interactions, dosages) — Phase 2
- [ ] NutritionAgent (diet, supplements protocol) — Phase 2
- [ ] Zero-knowledge client-side encryption — if project takes off
- [ ] Channels (shared knowledge domains) — Phase 3
- [ ] Domain creation UI (PaaS console) — Phase 3
- [ ] Template marketplace — Phase 3+
- [ ] Telegram bot (chat via bot) — Phase 2
- [ ] Inline charts (Chart.js) — Phase 2
- [ ] Drug marking system — Phase 2
- [ ] Export (JSON/PDF) — Phase 3
- [ ] Multiple domain types — Phase 3 (MVP has only "health")

---

## 5. Technical Constraints

| Constraint | Value |
|-----------|-------|
| Backend language | Python (FastAPI) |
| Frontend framework | React + TypeScript |
| Database | PostgreSQL 16 |
| Message broker | NATS JetStream |
| Search engine | SearXNG (self-hosted) |
| LLM access | LiteLLM proxy on llmsrv (IP whitelist) |
| LLM local | Qwen3 14B via Ollama (classification, routing) |
| LLM cloud | Claude / GPT via LiteLLM |
| Auth | Telegram bot (send code) + JWT sessions |
| Deploy target | agentdata.pro (94.131.92.153) |
| Deploy method | Docker Compose |
| Observability | Langfuse (SaaS) |

---

## 6. Users at Launch

- User 1: project owner — primary tester
- User 2-3: early adopters waiting for personal cabinet
- Total MVP capacity: ~10 concurrent users

---

## 7. Success Criteria

MVP is successful when:
1. A user can register via Telegram and enter personal cabinet
2. User can chat with AI advisor and get contextual responses
3. User can search for prices/information through chat (SearchAgent)
4. Two early adopters can use the system independently (data isolation works)
5. System runs stable on agentdata.pro for 7+ days without intervention
6. A new domain type can be added by inserting config into DB + writing a prompt file — no platform code changes required
