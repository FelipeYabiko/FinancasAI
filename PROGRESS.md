# PROGRESS

Build log for FinançasIA v9. Each phase ends with lint + tests green and a commit.
To resume in a new session: read this file, then continue with the first phase not marked done.

| Phase | Status |
|---|---|
| 0 — Repo, tooling, CI | ✅ done |
| 1 — Domain + API | ✅ done |
| 2 — Frontend + login | ⏳ next |
| 3 — LLM providers, prompts, tracing, diagnostics | ⬜ |
| 4 — PDF import pipeline + review screen | ⬜ |
| 5 — Assistant with function calling | ⬜ |
| 6 — Synthetic generator, eval suites, report | ⬜ |
| 7 — Insights | ⬜ |
| 8 — Docker | ⬜ |
| 9 — MCP server | ⬜ |
| 10 — README | ⬜ |

## Phase 0
- `uv` project (Python 3.12), FastAPI skeleton with `/api/health`.
- `ruff` (lint + format) and `pytest` configured in `pyproject.toml`.
- GitHub Actions CI: `uv sync --locked`, ruff check/format, pytest.
- `.env.example` with every variable (no values); `.gitignore` covers `.env`, SQLite, `evals/private/`, uploads.

## Phase 1
- Pure domain in `app/domain/`: dates/months, BRL parsing (`150,00-`, `D/C`), invoice rule
  (purchase on/before closing day → that month; clamps day 31 to month length; year rollover),
  installment split (difference on last installment, exact sum), description normalization,
  dedup hash + near-duplicate similarity, recurring scheduling, aggregations.
- SQLModel tables for every entity in the spec (+ `UserSession`, `AppSetting`, `LLMCall`).
- Services: ledger (create/update/delete, installments, transfers, filters, balances),
  recurring (idempotent via `recurring_rule_id + recurring_month`), dashboard, backup (JSON/CSV).
- Auth: bcrypt, server-side session table, HTTP-only cookie + double-submit CSRF header.
- API routers for auth/users, accounts, categories, category memory, transactions,
  budgets, goals, recurring, dashboard and backup. 102 tests passing.
