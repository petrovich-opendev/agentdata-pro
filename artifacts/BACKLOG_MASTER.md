# BioCoach — Master Backlog: Expansion Rounds

> Created: 2026-04-01
> Owner: Controller (GoalController v3)
> Status: Planning → Ready for execution

---

## Dependency Graph

```
                    ┌─────────────┐
                    │   ROUND 1   │
                    │ Chat Works  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
      ┌──────────┐  ┌───────────┐  ┌──────────┐
      │ ROUND N  │  │ ROUND PG  │  │ ROUND 2  │
      │ Host     │  │ Host      │  │ Sessions │
      │ Nginx    │  │ Postgres  │  │ & UX     │
      └──────────┘  └───────────┘  └──────────┘
              │            │
              ▼            │
      ┌──────────┐        │
      │ ROUND N  │◄───────┘
      │ (cont.)  │ PG needs compose
      │ Firewall │ changes too
      └──────────┘
```

### Execution Constraints

| Constraint | Reason |
|-----------|--------|
| Round 1 → first | Nothing works without LLM connection |
| Round 2 independent of N/PG | Feature work = code only, no infra deps |
| Round N before PG | Nginx migration changes compose; PG migration also changes compose. Do sequentially to avoid conflicts |
| Round N firewall last | UFW enable = point of no return, do after all services confirmed working |

### Recommended Order

```
1. ROUND 1  — Fix chat (5 min, config-only)
2. ROUND 2  — Session UX + features (2-3 hours, code changes)
3. ROUND N  — Host nginx + 2 domains (30 min, infra)
4. ROUND PG — Host PostgreSQL (20 min, infra + data migration)
5. FIREWALL — UFW enable (5 min, after everything stable)
```

Rationale: features (Round 2) first because they don't touch infra and deliver user value. Infra migrations (N, PG) are lower risk when product already works.

---

## Risk Analysis

| Round | Risk | Impact if fails | Mitigation |
|-------|------|----------------|------------|
| R1 | Ollama model name wrong | Chat stays broken | Verify `api/tags` first |
| R1 | `stream_options` not supported | 400 from Ollama | Remove param, test curl |
| R2 | Session switching race condition | Messages appear in wrong session | Test with 2+ sessions |
| R2 | Auto-title LLM call slow | Session title delayed | Acceptable — async after response |
| RN | Host nginx misconfigured | Site down | Keep Docker nginx config as rollback |
| RN | UFW kills SSH | **Server locked out** | Add SSH rule FIRST, test before enable |
| RPG | Data loss during migration | **All user data lost** | pg_dump before, keep Docker volume 24h |
| RPG | API can't reach host PG | Chat broken | Rollback .env to Docker connection |

### Critical Risks (red flags)

1. **UFW + SSH** — if `ufw enable` runs without `ufw allow 22/tcp` first, server is bricked. GoalController must enforce order.
2. **PG data migration** — if dump is incomplete or restore fails, data is lost. Must verify row counts match before switching.
3. **Docker compose conflicts** — Rounds N and PG both modify `docker-compose.yml`. Must not run in parallel.

---

## Scope Lock per Round

### Round 1: ONLY these changes
- `.env`: 3 variables (LITELLM_BASE_URL, LITELLM_MODEL, LITELLM_SUMMARY_MODEL)
- `api/llm/client.py`: maybe remove `stream_options` (1 line)
- Zero frontend changes
- Zero docker-compose changes

### Round 2: ONLY these files
- `api/chat/router.py` — session-scoped sending, auto-title, suggestions SSE
- `api/chat/service.py` — fix rename, add title generation
- `api/chat/models.py` — verify session_id field
- `api/llm/streaming.py` — suggestions event
- `web/src/stores/chatStore.ts` — fix session switch, add suggestions
- `web/src/types/index.ts` — extend SSEEvent
- `web/src/components/Suggestions.tsx` — new file
- `web/src/pages/Chat.tsx` — render suggestions, fix session effect
- **NOT TOUCH:** auth, middleware, agents, config, main.py, docker-compose, nginx

### Round N: ONLY infra
- Install `nginx-light` on host
- Create `/etc/nginx/sites-available/{agentdata.pro,x.oesv.ae}`
- Modify `docker-compose.yml` — remove nginx service, rebind ports
- SSL cert for x.oesv.ae
- GitLab `external_url` reconfigure
- UFW rules (last step)
- **NOT TOUCH:** any Python or TypeScript code

### Round PG: ONLY database
- Install `postgresql-16` on host
- Configure `postgresql.conf`, `pg_hba.conf`
- `pg_dump` from Docker → `pg_restore` to host
- Modify `.env` (DATABASE_URL)
- Modify `docker-compose.yml` — remove postgres service
- Setup backup cron
- **NOT TOUCH:** any Python or TypeScript code, nginx

---

## State After All Rounds

```
Host services (systemd):
  ├── nginx-light      (:443, :80) → agentdata.pro + x.oesv.ae
  ├── postgresql-16    (:5432 on localhost + docker bridge)
  ├── emco-vpn         (ppp0 → 10.0.0.0/8)
  └── ufw              (22, 80, 443 only)

Docker services (docker compose):
  ├── web              (127.0.0.1:3080 → React SPA)
  ├── api              (127.0.0.1:3000 → FastAPI)
  └── nats             (internal only → JetStream)

GitLab (separate compose):
  └── gitlab           (127.0.0.1:8929 → GitLab CE)

External:
  └── Ollama/Qwen3     (10.177.5.113:11434 via VPN)
```

Features:
- Chat responds via Qwen3 14B with streaming
- GigaChat fallback if VPN down
- Session create/switch/rename/delete
- Auto-generated session titles
- Context trimming (20+ messages → summarize)
- Follow-up suggestions (3 buttons)
- Markdown rendering with code blocks
- Search agent (DuckDuckGo) for pharmacy/lab queries
- Two domains: agentdata.pro (PaaS) + x.oesv.ae/gitlab/
- Daily PostgreSQL backups
- RLS actually enforced (non-superuser role)
