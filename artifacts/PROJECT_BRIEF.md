# Project Brief: BioCoach

**Платонический идеал**: Пишешь в чат про здоровье → получаешь ответ основанный на твоём контексте + реальные цены из интернета. Без паролей, без сложности.

**Суть**: AI-чат для управления здоровьем. Помнит контекст (протокол, препараты). Ищет реальные цены. Не галлюцинирует.

**Для кого**: 3 data-driven пользователя, которые ведут протоколы и мониторят биомаркеры.

**Метрика успеха**: Снижение жалоб пациента на 80%.

---

## Требования (прошедшие фильтр)

### 🔴 Физика (нельзя убрать)
- SSE streaming (без стриминга чат ждёт 10-30 сек)
- PostgreSQL (нужна БД)
- Docker Compose (деплой на удалённый сервер)
- HTTPS (Let's Encrypt)
- Parameterized queries (безопасность)

### 🟡 Обоснованные
- Telegram auth + JWT (2 пользователя ждут доступ, нужна регистрация)
- RLS (аудит-ready изоляция данных, невозможно забыть WHERE)
- NATS JetStream (второй агент появится через день после запуска)
- React (интерактивный чат с SSE streaming)

## Удалено / отложено

| Убрано | Почему | Когда вернуть |
|--------|--------|---------------|
| PaaS абстракции (domain_types) | 0 клиентов на другие домены | Когда появится клиент |
| Knowledge graph (nodes/edges) | Нет загрузки анализов в MVP | Phase 2 |
| SearXNG Docker | pip-пакет duckduckgo-search проще | Когда DDG начнёт throttle'ить |
| Langfuse | 3 пользователя, structlog достаточно | Когда >50 пользователей |
| Session management | Один чат на пользователя достаточно | Phase 2 |
| config_override в domains | Один тип домена | Phase 3 |
| 5 workflow stages | 3 достаточно (plan→implement→verify) | Никогда (оптимизация) |

## Архитектура (минимальная)

### Docker Compose (5 сервисов)
```
nginx      — reverse proxy, SSL, static
web        — React (nginx + build)
api        — Python FastAPI
nats       — NATS JetStream
postgres   — PostgreSQL 16
```

### БД (6 таблиц)
```
users           — telegram_chat_id (primary), username (display)
domains         — один на пользователя, auto-create
auth_codes      — временные коды подтверждения
refresh_tokens  — JWT refresh rotation
chat_sessions   — для будущего, пока одна сессия на юзера
chat_messages   — история чата + metadata
```

### Стек
- Backend: Python FastAPI + asyncpg + nats-py + openai SDK
- Frontend: React + TypeScript + Vite + Tailwind
- Search: duckduckgo-search (pip)
- LLM: LiteLLM proxy (llmsrv, внешний)
- Auth: Telegram bot (@Agentdatapro_bot) + JWT

### Промпт
- System prompt в файле `prompts/health_advisor.md` (не в БД)
- Загружается при старте API

## MVP-план (8 задач)

1. **Scaffold** — структура проекта, docker-compose, config
2. **DB Schema** — 6 таблиц, RLS, миграции
3. **Auth** — Telegram code → JWT
4. **Chat API** — messages + SSE streaming + LLM
5. **Agents** — BaseAgent + Router + Search (NATS)
6. **React** — login + chat UI (одна страница)
7. **Docker Deploy** — финализация compose + nginx
8. **QA + Security** — smoke test + OWASP audit

## Автоматизация
- DevTeam pipeline (автономное выполнение)
- Docker healthchecks
- structlog → stdout → docker logs

## Серверы
- **Dev**: llmsrv (10.177.5.113) — разработка
- **Prod**: agentdata.pro (94.131.92.153) — деплой
- **Telegram bot**: @Agentdatapro_bot (chat_id владельца: 524605979)
