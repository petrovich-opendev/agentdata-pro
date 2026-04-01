# BioCoach — Current State (2026-04-01)

## What Works
- https://agentdata.pro/ — React frontend, dark theme, deployed
- https://agentdata.pro/api/health — API responds `{"status":"ok"}`
- Telegram auth — sends code via @Agentdatapro_bot, JWT issued
- PostgreSQL — 6 tables with RLS
- NATS JetStream — running, 2 agents (router, search)
- GigaChat — connected as LLM fallback (LiteLLM not accessible from server yet)
- GitLab CE — running on server localhost:8929 (not exposed yet)

## What's Broken / Missing
- **Chat does not respond** — GigaChat fallback may have syntax issues, LiteLLM unreachable
- **Sidebar UX** — sessions exist but switching loses state, no groups, rename buggy
- **Dark theme inconsistent** — Landing page partially dark, Chat page better
- **No session management** — can't properly create/switch/rename/delete chats
- **No markdown rendering** — react-markdown added but may not render properly
- **Input history lost** on chat switch
- **No chat groups/folders**
- **Mobile sidebar** — may not collapse properly

## Architecture
```
Docker Compose on 94.131.92.153 (ssh devteam):
  nginx:443     → web:80 (React) + api:8000 (FastAPI)
  postgres:5432 → 6 tables (users, domains, auth_codes, refresh_tokens, chat_sessions, chat_messages)
  nats:4222     → RouterAgent + SearchAgent
```

## Tech Stack
- Backend: Python FastAPI + asyncpg + nats-py + openai SDK
- Frontend: React 18 + TypeScript + Vite + Tailwind CSS
- Search: duckduckgo-search (pip)
- LLM: GigaChat (fallback), LiteLLM on llmsrv (not connected yet)
- Auth: Telegram bot @Agentdatapro_bot + JWT

## API Endpoints
```
POST /api/auth/request-code   {telegram_username} → sends code
POST /api/auth/verify-code    {telegram_username, code} → {access_token}
POST /api/auth/refresh        (cookie) → {access_token}
POST /api/auth/logout

GET  /api/chat/sessions       → {sessions: [...]}
POST /api/chat/sessions       → {id, title, created_at}
DELETE /api/chat/sessions/:id
PATCH  /api/chat/sessions/:id {title}
GET  /api/chat/sessions/:id/messages → {messages: [...]}

POST /api/chat/messages       {content} → SSE stream
GET  /api/chat/messages       → history (current session)

GET  /api/health
```

## Key Files on Server (~/biocoach/)
```
api/main.py              — FastAPI app, lifespan, middleware
api/config.py            — pydantic-settings
api/auth/router.py       — auth endpoints
api/auth/service.py      — code gen, JWT, refresh
api/auth/telegram.py     — resolve username → chat_id, send code
api/chat/router.py       — chat endpoints + GigaChat fallback
api/chat/service.py      — DB operations for sessions/messages
api/llm/client.py        — OpenAI SDK → LiteLLM proxy
api/llm/gigachat.py      — GigaChat direct client
api/agents/base.py       — BaseAgent (NATS)
api/agents/router_agent.py — intent classification
api/agents/search_agent.py — DuckDuckGo search
web/src/pages/Chat.tsx   — main chat page
web/src/pages/Landing.tsx — login page
web/src/components/Sidebar.tsx
web/src/components/ChatInput.tsx
web/src/components/MessageItem.tsx
web/src/stores/authStore.ts
web/src/stores/chatStore.ts
web/src/api/client.ts
```

## Credentials
- Telegram bot: @Agentdatapro_bot (token in .env on server)
- Owner chat_id: 524605979 (@petrovich_mobile)
- GigaChat: GIGACHAT_AUTH_KEY in .env (scope GIGACHAT_API_PERS)
- GitLab: root / Gl@b2026Adm!n, API token: glpat-BgL2wX1IBXMLswkNrhNwO286MQp1OjEH.01.0w05nksai
- JWT_SECRET: generated, in .env

## DevTeam Status
- GoalController v3 running (PID on llmsrv)
- Pipeline: PREFLIGHT→BUILD→DEPLOY→VERIFY(curl+Playwright)→FIX loop
- Playwright MCP installed and configured
- Lessons learned: 8620 chars in controller/lessons_learned.md

## Priority Backlog for Next Session
1. **Fix chat to actually respond** — verify GigaChat works end-to-end
2. **Connect LiteLLM** — expose port 4000 on llmsrv or tunnel via WireGuard
3. **Fix sidebar UX** — proper session switching, rename, delete, groups
4. **ChatGPT-quality UI** — use shadcn/ui components, not custom CSS
5. **Configure GitLab external access** — nginx route for x.eosv.ae/gitlab
6. **Upload repos to GitLab** — biocoach + devteam
