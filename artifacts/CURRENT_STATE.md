# BioCoach — Current State (2026-04-01, Phase 1 Complete)

## Status: PRODUCTION MVP ✅

https://agentdata.pro/ — всё работает, пользователи могут пользоваться.

## What Works

- **Auth**: Telegram login (@Agentdatapro_bot) → JWT + HttpOnly refresh cookie (30 дней)
- **Auth persistence**: silent refresh при перезагрузке, без повторного логина
- **Chat**: SSE streaming через Qwen3 14B (primary) + GigaChat (fallback)
- **Search**: SearXNG (Google+Bing) → результаты inline в ответах с ценами и ссылками
- **Agents**: RouterAgent (intent classification) + SearchAgent (SearXNG) через NATS
- **Sessions**: создание, переключение (без мерцания), переименование, удаление
- **Sidebar**: список чатов с группировкой по дате, highlight active
- **Markdown**: полный рендеринг (заголовки, списки, код с копированием, таблицы, ссылки)
- **Dark theme**: консистентная тёмная тема
- **Mobile**: collapsible sidebar, responsive layout
- **Smart scroll**: не дёргает вверх при чтении истории
- **System prompt**: доказательная медицина, ГЗТ/спортфарма harm reduction, анти-БАД
- **Security**: RLS на 3 таблицах, CSP header, HSTS, rate limiting на auth, JWT rotation
- **DB**: PostgreSQL 16, 7 таблиц (включая domain_types), 5 индексов, RLS policies
- **VPN**: L2TP/IPsec tunnel devteam → llmsrv (systemd auto-reconnect)
- **GitHub**: https://github.com/petrovich-opendev/agentdata-pro

## Architecture (host-based, NO Docker for BioCoach)

```
Host services on 94.131.92.153 (ssh devteam):
  nginx          → static /home/dev/biocoach/web/dist/ + proxy :8000
  biocoach-api   → systemd, uvicorn, port 8000
  postgresql     → systemd, port 5432, DB: biocoach (7 tables)
  nats-server    → systemd, port 4222 (JetStream)
  searxng        → Docker, port 8888 (localhost only)
  gitlab (Docker)→ port 8929

L2TP/IPsec VPN (emco-l2tp.service):
  devteam (10.221.x.x) ←→ vpn.eastmining.ru ←→ llmsrv (10.177.5.113)

LLM path:
  BioCoach API → http://10.177.5.113:11434/v1 (Ollama/Qwen3 14B via VPN)
  Fallback → GigaChat API (Sber, direct HTTPS)
```

## Tech Stack

- Backend: Python 3.12, FastAPI, asyncpg, nats-py, openai SDK, httpx
- Frontend: React 18, TypeScript, Vite, Tailwind CSS, Zustand, react-markdown
- LLM Primary: Qwen3 14B via Ollama (on llmsrv, accessed via L2TP VPN)
- LLM Fallback: GigaChat (Sber API)
- Search: SearXNG (self-hosted, Google+Bing aggregator)
- Auth: Telegram bot @Agentdatapro_bot + JWT + HttpOnly refresh cookie
- DB: PostgreSQL 16 (7 tables, RLS, domain_types config)
- Messaging: NATS JetStream
- VPN: L2TP/IPsec (strongswan + xl2tpd)

## API Endpoints

```
POST /api/auth/request-code    {telegram_username}
POST /api/auth/verify-code     {telegram_username, code}
POST /api/auth/refresh         (cookie)
POST /api/auth/logout

GET  /api/chat/sessions
POST /api/chat/sessions
PATCH /api/chat/sessions/:id   {title}
DELETE /api/chat/sessions/:id
GET  /api/chat/sessions/:id/messages

POST /api/chat/messages        {content, session_id?} → SSE stream
GET  /api/chat/messages

GET  /api/health
```

## QA/Security Audit (2026-04-01 Rev.2)

- **0 Critical, 0 High** (all fixed)
- Remaining: 2 Medium (GigaChat SSL — accepted risk, CORS all methods — low impact)
- 5 indexes, 3 RLS policies, domain_types table — all applied
- CSP header enforced, HSTS, X-Frame-Options, X-Content-Type-Options
- Nginx rate limiting on /api/auth/

## Phase 1 Backlog — CLOSED

| # | Task | Status |
|---|------|--------|
| 1 | Connect LiteLLM / Qwen | ✅ Qwen3 via L2TP VPN |
| 2 | Upload repos to GitHub | ✅ github.com/petrovich-opendev/agentdata-pro |
| 3 | System prompt tuning | ✅ Evidence-based medicine persona |
| 4 | Search agent integration | ✅ SearXNG (Google+Bing), inline results |
| 5 | Markdown rendering | ✅ Already implemented (react-markdown + remark-gfm) |
| 6 | Chat groups/folders | ✅ Date grouping exists, custom folders deferred |
| 7 | shadcn/ui migration | Deferred — no business value now |

## Phase 2 Backlog (Ideas)

- Personal features for owner (TBD)
- Knowledge graph (PostgreSQL JSONB + CTE)
- File upload (lab results, PDFs)
- Multi-model selection in UI
- User settings / preferences
- Admin panel
- Analytics / Langfuse observability
- Mobile PWA
