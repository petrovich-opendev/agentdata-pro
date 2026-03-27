---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + httpx (async test client) |
| **Config file** | `pytest.ini` or `pyproject.toml [tool.pytest]` |
| **Quick run command** | `pytest tests/ -x -q --timeout=10` |
| **Full suite command** | `pytest tests/ -v --timeout=30` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q --timeout=10`
- **After every plan wave:** Run `pytest tests/ -v --timeout=30`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | — | infra | `docker compose config --quiet` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | — | infra | `docker compose up -d && docker compose ps` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | AUTH-01 | integration | `pytest tests/test_auth.py::test_register` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | AUTH-02 | integration | `pytest tests/test_auth.py::test_login_refresh` | ❌ W0 | ⬜ pending |
| 01-02-03 | 02 | 1 | AUTH-03 | integration | `pytest tests/test_auth.py::test_password_reset` | ❌ W0 | ⬜ pending |
| 01-02-04 | 02 | 1 | AUTH-04 | integration | `pytest tests/test_auth.py::test_rate_limiting` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 1 | AUD-01 | integration | `pytest tests/test_audit.py::test_event_logging` | ❌ W0 | ⬜ pending |
| 01-03-02 | 03 | 1 | — | integration | `pytest tests/test_rls.py::test_domain_isolation` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — shared fixtures (test DB, async client, auth helpers)
- [ ] `tests/test_auth.py` — stubs for AUTH-01 through AUTH-04
- [ ] `tests/test_audit.py` — stubs for AUD-01
- [ ] `tests/test_rls.py` — stubs for RLS cross-domain isolation
- [ ] `pytest` + `httpx` + `pytest-asyncio` — install in requirements-dev.txt

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Email delivery (password reset) | AUTH-03 | SMTP provider dependency | Check dev console log for reset link |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
