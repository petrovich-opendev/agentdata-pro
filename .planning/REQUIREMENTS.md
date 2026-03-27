# Requirements: AgentData.pro

**Defined:** 2026-03-27
**Core Value:** Агенты автономно работают в изолированных доменах знаний 24/7, проактивно уведомляя пользователя о важном и накапливая экспертизу со временем.

## v1 Requirements

### Authentication

- [ ] **AUTH-01**: Пользователь может зарегистрироваться с email и паролем (Argon2id)
- [ ] **AUTH-02**: Пользователь может войти и оставаться залогиненным (JWT access 15min + refresh 7d httpOnly)
- [ ] **AUTH-03**: Пользователь может сбросить пароль через email
- [ ] **AUTH-04**: Login endpoint защищён rate limiting (5 попыток/мин на IP)

### Domains

- [ ] **DOM-01**: Пользователь может создать, редактировать и удалить домен знаний
- [ ] **DOM-02**: Данные доменов физически изолированы через PostgreSQL RLS (SET LOCAL app.current_domain_id)
- [ ] **DOM-03**: Владелец домена может пригласить участников с ролями owner/member/viewer
- [ ] **DOM-04**: Пользователь может переключаться между доменами, контекст привязан к активному домену

### Agents

- [ ] **AGT-01**: Пользователь может создать агента с ролью, промптом, набором tools и привязкой к домену
- [ ] **AGT-02**: Пользователь может дать задачу агенту и получить результат (on-demand execution)
- [ ] **AGT-03**: Агент может работать автономно по cron-расписанию (ночной ресерч, утренние напоминания)
- [ ] **AGT-04**: Три агента могут вести дебаты (thesis → antithesis → synthesis) с итогом + полным логом

### LLM Integration

- [ ] **LLM-01**: Система маршрутизирует запросы: локальная модель (Ollama) → OpenAI API fallback с auto-переключением
- [ ] **LLM-02**: Агенты хранят знания, ресерчи, дебаты в git-versioned MD-файлах (dulwich)
- [ ] **LLM-03**: Система контролирует бюджет токенов на домен/пользователя с лимитами
- [ ] **LLM-04**: Память агентов доступна через semantic search (pgvector)

### Interfaces

- [ ] **UI-01**: Telegram-бот (aiogram webhook) для уведомлений, ввода данных, быстрых действий
- [ ] **UI-02**: Web UI (React SPA) с дашбордом, управлением доменами, агентами, просмотром результатов
- [ ] **UI-03**: Real-time обновления через WebSocket (прогресс агентов, дебаты, уведомления) + Redis Streams replay
- [ ] **UI-04**: PWA: service worker, push notifications, app-like mobile experience

### Health Domain (MVP)

- [ ] **HP-01**: Пользователь может вводить вес через Telegram, видеть график тренда в Web UI
- [ ] **HP-02**: Cron-агент отправляет утреннее расписание препаратов и витаминов в Telegram
- [ ] **HP-03**: Health Advisor агент анализирует тренд веса и даёт персональные рекомендации
- [ ] **HP-04**: Еженедельные дебаты по здоровью (аналитик vs критик vs синтезатор)
- [ ] **HP-05**: Агент ищет скидки и промокоды на препараты, еду и анализы в городе пользователя
- [ ] **HP-06**: Пользователь может вести дневник питания с анализом нутриентов

### Audit

- [ ] **AUD-01**: Каждое действие пользователя и агента записывается в append-only events таблицу (партиционирована по месяцам)

## v2 Requirements

### Reactive Agents

- **AGT-05**: Агент реагирует на внешние события (новые данные, изменение цены, погода)

### Advanced UI

- **AUD-02**: Просмотр логов событий по домену/агенту в Web UI
- **UI-05**: Command palette (Cmd+K) для быстрых действий

### Advanced Health

- **HP-07**: Интеграция с Apple Health / Google Fit (телеметрия часов)
- **HP-08**: Анализ тренировок с рекомендациями по нагрузке

### Collaboration

- **COLLAB-01**: Чат внутри домена для участников
- **COLLAB-02**: Агент может упоминать участников в результатах

### Finance Domain

- **FIN-01**: Мониторинг крипто-портфеля с алертами
- **FIN-02**: Агент-аналитик рынка с дебатами по сделкам

## Out of Scope

| Feature | Reason |
|---------|--------|
| Мобильное приложение (native) | PWA достаточно для v1 |
| Голосовой ввод (STT) | Добавить позже как Telegram voice handler |
| Видео-анализ (CV) | Отдельный проект, требует pipeline |
| OAuth/Social login | email+password для 15 юзеров |
| Keycloak/OIDC | Overkill для стартового масштаба |
| Visual workflow builder | Высокая сложность, мало ценности для 15 юзеров |
| Plugin marketplace | Преждевременная абстракция |
| Cross-domain agent communication | Нарушает изоляцию доменов |
| Fine-tuning локальных моделей | Сложно, дорого, мало ценности |
| NL agent creation ("создай агента для...") | Сложный UX, проще CRUD-форма |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 | — | Pending |
| AUTH-02 | — | Pending |
| AUTH-03 | — | Pending |
| AUTH-04 | — | Pending |
| DOM-01 | — | Pending |
| DOM-02 | — | Pending |
| DOM-03 | — | Pending |
| DOM-04 | — | Pending |
| AGT-01 | — | Pending |
| AGT-02 | — | Pending |
| AGT-03 | — | Pending |
| AGT-04 | — | Pending |
| LLM-01 | — | Pending |
| LLM-02 | — | Pending |
| LLM-03 | — | Pending |
| LLM-04 | — | Pending |
| UI-01 | — | Pending |
| UI-02 | — | Pending |
| UI-03 | — | Pending |
| UI-04 | — | Pending |
| HP-01 | — | Pending |
| HP-02 | — | Pending |
| HP-03 | — | Pending |
| HP-04 | — | Pending |
| HP-05 | — | Pending |
| HP-06 | — | Pending |
| AUD-01 | — | Pending |

**Coverage:**
- v1 requirements: 27 total
- Mapped to phases: 0
- Unmapped: 27 ⚠️

---
*Requirements defined: 2026-03-27*
*Last updated: 2026-03-27 after initial definition*
