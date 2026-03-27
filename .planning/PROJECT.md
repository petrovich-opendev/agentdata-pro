# AgentData.pro

## What This Is

Персональная AI-операционная система с мультиагентами и коллаборацией. Агенты работают автономно 24/7 в изолированных доменах знаний (здоровье, финансы, работа, фитнес), взаимодействуя с пользователем через Telegram и Web UI. Агенты ведут дебаты между собой (thesis → antithesis → synthesis) для получения качественных результатов. Память агентов хранится в git-versioned MD-файлах.

## Core Value

Агенты автономно работают в изолированных доменах знаний 24/7, проактивно уведомляя пользователя о важном и накапливая экспертизу со временем — при абсолютной изоляции данных между доменами.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Регистрация и аутентификация пользователей (JWT + Argon2id)
- [ ] Создание и управление доменами знаний с полной изоляцией (PostgreSQL RLS)
- [ ] Приглашение участников в домен (owner/member/viewer)
- [ ] Telegram-бот с webhook mode (aiogram + FastAPI)
- [ ] Web UI: дашборд, управление доменами, просмотр результатов агентов
- [ ] Создание и настройка агентов (роль, промпт, tools, домен)
- [ ] Три режима работы агентов: по запросу, по расписанию (cron), реактивный
- [ ] Дебаты агентов: thesis → antithesis → synthesis (3 LLM-вызова на раунд)
- [ ] Просмотр дебатов: итог + раскрытие полного лога
- [ ] MD-память агентов (git-versioned research, debates, knowledge)
- [ ] LLM routing: локальная модель (Ollama) → OpenAI API fallback
- [ ] Real-time обновления через WebSocket + Redis Streams
- [ ] Event log: audit trail каждого действия
- [ ] MVP домен "Здоровье": препараты, вес, анализы, рекомендации

### Out of Scope

- Мобильное приложение — PWA через Web UI достаточно для MVP
- Видео-анализ (фитнес, камера) — требует Computer Vision pipeline, отдельный проект
- Голосовой ввод (speech-to-text) — можно добавить позже как Telegram voice message handler
- Интеграция с умными часами — API-зависимость, после MVP
- Маршруты/навигация — требует интеграцию с картами, не MVP
- OAuth/Social login — email+password достаточно для 10-15 пользователей
- Keycloak — overkill для стартового масштаба, добавить при росте до 50+
- CRDT/real-time co-editing — агенты не редактируют одновременно, file-level locking достаточно

## Context

### Предыстория
Проект вырос из потребности автора (Petrovich) в инструменте, который объединяет управление разными сферами жизни через AI-агентов. Существующие инструменты (ClickUp, Notion, ChatGPT) не дают: автономных агентов 24/7, изоляцию доменов, дебаты между агентами, Telegram как равноправный канал.

### Исследования (2026-03-27)
Проведено 7 параллельных исследований:
1. MD-first архитектуры (Claude Code, Obsidian, Logseq, AnyType, Notion, Linear)
2. Мультиагентные платформы (CrewAI, LangGraph, Temporal, MCP)
3. Доменная изоляция (Zanzibar/OpenFGA, ABAC, RLS, zero-trust)
4. ClickUp и альтернативы (Linear, Plane, Huly, Height)
5. Валидация Python-стека (FastAPI, TaskIQ, PG-only, aiogram)
6. React UI архитектура (Vite SPA, shadcn/ui, TanStack)
7. Инфраструктура home server (Docker Compose, SSL, security, GPU)

### Концепт-документ
Полный концепт: `/home/ubuntu/projects/agentdata-pro/CONCEPT.md` (610 строк)

### Пользователи
- 10-15 на старте (друзья, коллеги, семья)
- Рост до 70+ человек
- Каждый имеет личные домены + может участвовать в совместных

### MVP домен
"Здоровье" — один пользователь (автор), препараты, вес, анализы. Проверяет: изоляцию, агентов, дебаты, Telegram+Web UI, MD-память.

## Constraints

- **Stack (backend)**: Python 3.12 + FastAPI — единый язык, AI-экосистема нативна
- **Stack (frontend)**: React + TypeScript + Vite SPA — shadcn/ui + Tailwind v4
- **Stack (DB)**: PostgreSQL 16 only — JSONB, pgvector, RLS, LTREE в одной БД
- **Stack (queue)**: TaskIQ + Redis — async-native, FastAPI интеграция
- **Stack (Telegram)**: aiogram 3 — webhook mode, встроен в FastAPI
- **Infra**: Docker Compose — VPS (Yandex Cloud KZ) + Home Server (GPU)
- **LLM**: Ollama (Qwen 2.5 14B + Llama 3.1 8B) + OpenAI API fallback
- **LLM router**: Custom Python (~50 строк) — NOT LiteLLM (compromised March 2026)
- **Auth**: JWT + Argon2id — NOT bcrypt, NOT Keycloak for MVP
- **Security**: RLS from day one, WireGuard для admin, Cloudflare для DDoS
- **License**: Apache 2.0
- **Open Source**: GitHub, public repo

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python-only backend (no Go) | AI экосистема нативна, один язык проще | — Pending |
| TaskIQ вместо Dramatiq/Celery | Async-native, интеграция с FastAPI | — Pending |
| PostgreSQL-only (no FalkorDB/Mongo) | JSONB+pgvector+RLS+LTREE покрывают всё для 70 юзеров | — Pending |
| Custom LLM router (no LiteLLM) | LiteLLM compromised March 2026, 800+ issues | — Pending |
| Argon2id вместо bcrypt | GPU-resistant, рекомендация FastAPI | — Pending |
| Vite SPA вместо Next.js | Нет SSR, статика через nginx, проще ops | — Pending |
| shadcn/ui вместо MUI/Ant | Код принадлежит проекту, ClickUp-like эстетика | — Pending |
| Thesis-Antithesis-Synthesis дебаты | Фиксированная стоимость (3 LLM), аудитируемо | — Pending |
| Hybrid deploy (VPS + Home GPU) | VPS для app, GPU дома для Ollama, WireGuard tunnel | — Pending |
| MD для памяти агентов, не для UI | Пользователь в Telegram/Web, MD для debug и git history | — Pending |

---
*Last updated: 2026-03-27 after initialization*
