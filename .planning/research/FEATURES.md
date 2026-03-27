# Feature Landscape

**Domain:** Personal AI Operating System / Multi-Agent Knowledge Workspace
**Researched:** 2026-03-27
**Confidence:** HIGH (multiple sources, validated against existing products and frameworks)

## Table Stakes

Features users expect from a personal AI agent platform. Missing = product feels incomplete or untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| User registration & authentication | Users need accounts to own data; JWT+Argon2id is the minimum bar | Low | httpOnly cookies, refresh token rotation. No OAuth needed for 10-15 users |
| Knowledge domains with isolation | Core promise of the product; without isolation, users cannot trust agents with sensitive data (health, finance) | High | PostgreSQL RLS from day one. Every table gets `domain_id`. This is non-negotiable |
| Agent creation & configuration | Users must define what agents do — role, prompt, tools, schedule | Medium | Template agents (analyst, critic, researcher) + custom creation |
| On-demand agent execution | "Ask agent a question, get an answer" — the most basic interaction | Medium | Synchronous request-response via Telegram or Web UI |
| Telegram bot integration | Telegram is the primary mobile channel; 10-15 early users all use Telegram | Medium | aiogram 3 webhook mode, domain-scoped conversations, rich formatting |
| Web UI dashboard | Users need a place for deep work — configure agents, view history, manage domains | High | React SPA with real-time updates. Not a glorified chat — structured data views |
| Agent memory persistence | Without memory, agents are stateless chatbots. Memory = accumulated knowledge over time | Medium | MD files for human-readable debug + pgvector for semantic search. Git-versioned |
| Audit trail / event log | Users must see what agents did and when — trust requires transparency | Medium | Append-only `events` table, actor/action/resource/domain/decision. Never delete |
| Medication reminders (Health MVP) | Table stakes for any health domain — users expect daily medication schedules | Low | Cron-triggered agent sends morning reminder via Telegram, tracks acknowledgment |
| Weight tracking (Health MVP) | Simple numeric input with trend visualization — every health app has this | Low | Telegram: user sends number, agent stores. Web UI: chart with trend line |
| Real-time updates (WebSocket) | Users expect to see agent activity live, not poll-and-refresh | Medium | Native WebSocket, Redis Streams for event replay on reconnect |
| LLM routing (local + cloud) | Users expect AI to work reliably; fallback from Ollama to OpenAI ensures availability | Medium | Custom router (~50 lines). Ollama-first, OpenAI fallback. Health check on home server |
| Domain member invitation | Collaborative domains (work) require inviting others with role-based access | Low | owner/member/viewer roles. Simple invite link or email |
| Error handling & user feedback | When agent fails, user must know why — no silent failures, no fake success | Low | Error states in UI, failure notifications in Telegram, retry options |

## Differentiators

Features that set AgentData.pro apart from ChatGPT, Notion AI, Obsidian, and CrewAI. Not expected, but create real value.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Agent debates (thesis-antithesis-synthesis) | Multi-perspective reasoning produces higher quality outputs than single-agent responses. Research confirms debate frameworks significantly reduce hallucinations and improve complex reasoning | High | Fixed cost: 3 LLM calls per round. Orchestrator decides if additional rounds needed. Summary for user, full log available on click. See Hegelion framework as reference |
| Autonomous 24/7 agent work | Agents work overnight — research, analysis, market monitoring — ready by morning. Competitors (ChatGPT, Claude) only work on-demand | High | TaskIQ workers + APScheduler cron. Requires robust error handling and resource limits |
| Reactive agents (event-driven) | Agents trigger on external events (price drop, weight anomaly, deadline approaching) — not just cron, not just on-demand | Medium | Redis pub/sub for internal events. External event sources per domain (API polling, webhooks) |
| Proactive notifications | Agents push important information to user without being asked — "BTC dropped 10%", "Weight trend suggests plateau" | Medium | Depends on: reactive agents + Telegram integration. User controls notification frequency and priority thresholds |
| Git-versioned agent knowledge | Full diff history of what agents know and when they learned it. Rollback bad knowledge. Branch agent memory for experiments | Medium | MD files on filesystem, git operations via Python (gitpython or subprocess). Unique differentiator vs all competitors |
| Cross-agent debate within domain | Multiple agents with different roles (analyst vs critic) debate a topic within the same domain, producing stress-tested conclusions | High | Extension of basic debate. Agents share domain context but argue from different perspectives. No cross-domain data leakage |
| Domain templates | Pre-built domain configurations (Health, Finance, Fitness, Work) with recommended agents, tools, and schedules | Low | JSON/YAML templates. Dramatically reduces time-to-value for new users. Can be community-contributed |
| Debate transparency & drill-down | User sees summary, can expand to full thesis/antithesis/synthesis log. Full audit trail of agent reasoning | Low | UI component. Low complexity once debates are implemented |
| Semantic search across agent memory | "What did my health agent conclude about magnesium last month?" — pgvector similarity search within domain boundaries | Medium | pgvector embeddings on memory entries. RLS ensures search stays within domain |
| Hybrid deploy (VPS + home GPU) | Users run AI locally on their hardware for free (80% of tasks) with cloud fallback. Privacy + cost savings | Medium | WireGuard tunnel between VPS and home server. Health monitoring. Graceful fallback |
| Self-hostable (Docker Compose) | One-command deployment. Users own their data completely. Apache 2.0 license | Medium | `docker compose up -d` with `.env` configuration. Strong differentiator for privacy-conscious users |
| Blood test analysis (Health MVP) | Agent interprets lab results, compares to history, flags anomalies — most health apps cannot do this | Medium | Structured data entry for lab markers. Agent uses medical knowledge to contextualize. Requires strong disclaimer (not medical advice) |
| Multi-channel unified context | Same conversation context across Telegram and Web UI. Message in Telegram appears in Web, and vice versa | Medium | Single message store with channel indicator. WebSocket sync |

## Anti-Features

Features to explicitly NOT build. Each would waste time, increase complexity, or harm the product.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Mobile native app (iOS/Android) | Enormous development overhead for 10-15 users. PWA via Web UI + Telegram covers mobile use cases completely | PWA with `manifest.json`, add-to-homescreen. Telegram is the real mobile client |
| Voice input / speech-to-text | Requires audio pipeline, STT model, latency handling. Telegram already has voice messages (handle later) | Accept text input only for MVP. Voice messages can be added as a Telegram handler post-MVP |
| Video analysis / computer vision | Entirely different ML pipeline. Not related to core agent workspace value | Separate project if ever needed |
| Smartwatch / wearable integration | API-dependent, device-specific, maintenance nightmare for small user base | Manual data entry (weight, steps) is sufficient. API integration when user base justifies it |
| OAuth / social login | Over-engineering for 10-15 trusted users. Adds OIDC complexity, consent flows, provider maintenance | Email + password with Argon2id. Add Keycloak at 50+ users |
| CRDT / real-time co-editing | Agents do not edit simultaneously. File-level locking is sufficient for agent memory | Simple file locking. Agents operate sequentially within a domain |
| Visual workflow builder (no-code) | Premature complexity. Users are technical. YAML/JSON agent config is cleaner and version-controllable | Agent configuration via structured forms in Web UI + raw YAML/JSON for power users |
| Plugin marketplace | Requires review process, security scanning, versioning infrastructure. Way too early | Built-in tools per domain type. Community contributions via GitHub PRs |
| Natural language agent creation | "Create an agent that monitors BTC" sounds nice but produces unreliable agent configs. Structured forms are more predictable | Structured agent creation form with templates. Natural language can help fill fields later |
| Multi-language UI (i18n) | 10-15 Russian-speaking users. i18n infrastructure adds complexity to every UI component | Russian-first UI. Internationalize when user base demands it |
| Calendar / route planning integrations | Requires Google/Apple calendar APIs, map services. Tangential to core value | Out of scope until "Personal Assistant" domain is built post-MVP |
| Fine-tuning local LLM | Requires training data pipeline, GPU time, evaluation. Ollama + good prompts is sufficient | Use Ollama with well-crafted prompts and system instructions. Fine-tuning is a separate research project |
| Agent-to-agent cross-domain communication | Defeats the purpose of domain isolation. Security risk. Confuses trust boundaries | Domains are isolated. Period. If user needs cross-domain insight, they ask in a new domain that has access to relevant data |

## Feature Dependencies

```
Registration/Auth ─────────────────────────────────────────────────────┐
       │                                                                │
       v                                                                │
Domain Creation (with RLS) ────────────────────────────────────────────│
       │                                                                │
       ├──► Agent Creation & Configuration                              │
       │         │                                                      │
       │         ├──► On-Demand Execution ──► Telegram Bot Integration  │
       │         │                            Web UI Dashboard          │
       │         │                                                      │
       │         ├──► Scheduled Execution (cron) ──► Medication Reminders
       │         │         │                                            │
       │         │         └──► Autonomous 24/7 Work                    │
       │         │                                                      │
       │         ├──► Reactive Execution ──► Proactive Notifications    │
       │         │                                                      │
       │         └──► Agent Memory (MD + pgvector) ──► Semantic Search  │
       │                   │                                            │
       │                   └──► Git-versioned Knowledge                 │
       │                                                                │
       ├──► Agent Debates (thesis/antithesis/synthesis)                 │
       │         │                                                      │
       │         └──► Debate Transparency & Drill-down                  │
       │                                                                │
       ├──► Domain Member Invitation ──► Collaborative Domains          │
       │                                                                │
       └──► Event Log / Audit Trail                                     │
                                                                        │
LLM Router (Ollama + OpenAI) ── independent, required by all agents ───┘

WebSocket / Real-time ── independent, enhances all UI interactions
Weight Tracking ── requires: Health domain + Telegram bot
Blood Test Analysis ── requires: Health domain + agent memory + on-demand execution
```

## MVP Recommendation

### Must Ship (Phase 1-2)

1. **Registration & Auth** (JWT + Argon2id) — gate to everything
2. **Domain creation with RLS** — core isolation promise
3. **Agent creation & configuration** — with Health Advisor template
4. **LLM router** (Ollama-first, OpenAI fallback) — agents need a brain
5. **On-demand agent execution** — basic "ask and get answer"
6. **Telegram bot** — primary interaction channel, medication reminders, weight input
7. **Web UI dashboard** — domain management, agent config, weight chart, agent logs
8. **Agent memory** (MD + DB) — agents must remember between sessions
9. **Event log** — audit trail from day one

### Should Ship (Phase 3)

10. **Scheduled agent execution** (cron) — autonomous morning reminders, nightly analysis
11. **Agent debates** (thesis-antithesis-synthesis) — key differentiator, prove it works with weekly health review
12. **Real-time updates** (WebSocket) — live agent activity in Web UI

### Defer

- **Reactive agents / proactive notifications** — requires event source infrastructure, build after cron works
- **Semantic search** — pgvector embeddings, build after memory accumulates
- **Git-versioned knowledge** — valuable but not blocking; basic file persistence first, git versioning later
- **Blood test analysis** — structured data entry UI is complex; add after basic health flow works
- **Domain templates** — create manually first, templatize when patterns emerge
- **Collaborative domains** — invitation flow is simple, but shared agent context adds complexity
- **Self-hosted Docker Compose** — deploy manually first, package for others later

## Sources

- [Best Autonomous AI Agents Platforms 2026](https://www.getsnippets.ai/articles/best-autonomous-ai-agents) — market landscape
- [AutoGPT vs CrewAI vs Agent Zero Comparison](https://blog.canadianwebhosting.com/autogpt-crewai-agent-zero-comparison-2026/) — multi-agent framework features
- [LLM OS Guide (DataCamp)](https://www.datacamp.com/blog/llm-os) — AI operating system concepts
- [AI Agent Memory: When Markdown Files Are All You Need](https://dev.to/imaginex/ai-agent-memory-management-when-markdown-files-are-all-you-need-5ekk) — MD memory architecture
- [DiffMem: Git-Based Memory for AI Agents](https://github.com/Growth-Kinetics/DiffMem) — git-versioned agent memory
- [Hegelion: Dialectical Reasoning for LLMs](https://github.com/Hmbown/Hegelion) — thesis-antithesis-synthesis framework
- [Multi-Agent Debate Frameworks (Medium)](https://sikkha.medium.com/exploring-multi-agent-debate-frameworks-for-ai-reasoning-and-persona-driven-architectures-0ffb5db05ee3) — debate architecture patterns
- [AI Models Internal Debate Improves Accuracy (VentureBeat)](https://venturebeat.com/orchestration/ai-models-that-simulate-internal-debate-dramatically-improve-accuracy-on) — debate effectiveness research
- [Access Control for Multi-Tenant AI Agents](https://www.scalekit.com/blog/access-control-multi-tenant-ai-agents) — domain isolation patterns
- [Tenant Isolation in AI Systems (Blaxel)](https://blaxel.ai/blog/tenant-isolation) — multi-tenant security
- [AI Health Companions: Medication Reminders (Medium)](https://medium.com/@jrottum/ai-health-companions-your-personal-medication-reminder-and-symptom-tracker-0a7b6b3dc6a8) — health domain features
- [ChatGPT Health (OpenAI)](https://openai.com/index/introducing-chatgpt-health/) — health AI baseline features
- [Telegram AI Agent: Scheduled Tasks (RunTheAgent)](https://runtheagent.com/platforms/telegram-ai-agent) — Telegram agent capabilities
- [MoltBot: Open-Source AI Agent](https://moltbotai.chat/) — Telegram autonomous agent reference
- [CrewAI: Leading Multi-Agent Platform](https://crewai.com/) — multi-agent feature comparison
- [Best AI Agent Memory Frameworks 2026](https://machinelearningmastery.com/the-6-best-ai-agent-memory-frameworks-you-should-try-in-2026/) — memory architecture options
