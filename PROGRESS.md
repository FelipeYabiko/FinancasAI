# PROGRESS

Build log for FinançasIA v9. Each phase ends with lint + tests green and a commit.
To resume in a new session: read this file, then continue with the first phase not marked done.

| Phase | Status |
|---|---|
| 0 — Repo, tooling, CI | ✅ done |
| 1 — Domain + API | ✅ done |
| 2 — Frontend + login | ✅ done |
| 3 — LLM providers, prompts, tracing, diagnostics | ✅ done |
| 4 — PDF import pipeline + review screen | ⏳ next |
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

## Phase 2
- Vanilla JS ES modules in `app/static/js` (no build step), served by FastAPI; Chart.js vendored
  (`app/static/vendor`, pinned 4.4.7) so the app works offline and under a strict CSP (`script-src 'self'`).
- Login / first-run setup screen; hash router; month picker; global search; theme (auto/light/dark).
- Views: dashboard (balances, open invoices, 6-month bars, category doughnut, MoM %, top merchants,
  weekday chart, budgets), transactions (filters, month/all scope with stats, inline edit of
  description/category, modal edit, installment-aware delete), budgets (80%/100% alerts, inline limit,
  copy from previous month), goals (inline add/withdraw/set — no `prompt()`), recurring rules, settings
  (accounts, categories, users, category memory, backup JSON/CSV, appearance/shortcuts).
- Shortcuts: Ctrl+N, Ctrl+I, Ctrl+/. Responsive layout with bottom nav on phones.
- Verified with a Playwright smoke run (desktop 1366px + mobile 390px): full flow without console errors.

## Phase 3
- Model names verified against provider docs on 2026-10-15 (Groq models page, Gemini models +
  pricing pages, OpenRouter `/api/v1/models`). They live only in `app/config.py` defaults, `.env`,
  the settings screen (DB `AppSetting`) and `app/llm/pricing.yaml`.
- `app/llm/providers/`: one OpenAI-compatible implementation shared by Groq, Gemini (OpenAI
  compatibility endpoint) and OpenRouter + a deterministic `FakeProvider` for tests/CI.
- `app/llm/client.py`: timeout, exponential backoff on 429/5xx/network, Pydantic validation with
  exactly one corrective retry (the validation error is fed back to the model), and an `LLMCall`
  row per provider response (tokens, cost via `pricing.yaml`, latency, status, attempts).
  Payloads are only stored with `LLM_LOG_PAYLOADS=true`.
- Versioned prompts (`app/llm/prompts/<feature>.<version>.md`); every call stores its version.
- Settings → IA (provider/model per feature + "Testar") and Settings → Diagnóstico de IA (cost by
  feature, calls per day, p50/p95, error rate, recent failures). Per-user rate limit on AI endpoints.
- Acceptance: `test_ai_test_endpoint_records_llmcall` shows a test call in `LLMCall` with tokens,
  cost and latency. No real API keys are configured in this environment, so real-provider calls
  record a clear "chave não configurada" error (visible in the diagnostics page).
