# PROGRESS

Build log for FinançasIA v9. Each phase ends with lint + tests green and a commit.
To resume in a new session: read this file, then continue with the first phase not marked done.

| Phase | Status |
|---|---|
| 0 — Repo, tooling, CI | ✅ done |
| 1 — Domain + API | ✅ done |
| 2 — Frontend + login | ✅ done |
| 3 — LLM providers, prompts, tracing, diagnostics | ✅ done |
| 4 — PDF import pipeline + review screen | ✅ done |
| 5 — Assistant with function calling | ✅ done |
| 6 — Synthetic generator, eval suites, report | 🟡 harness done — real 3-model run needs API keys |
| 7 — Insights | ✅ done |
| 8 — Docker | ✅ done |
| 9 — MCP server | ✅ done |
| 10 — README | ⏳ next |

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

## Phase 4
- Synthetic generator moved forward from phase 6 (needed for acceptance): `evals/generators/statements.py`
  creates 40 PDFs in 4 fictional layouts (Banco Aurora, Cooperativa Ipê, Lume Card invoice, Banco Maré)
  with JSON ground truth → `evals/datasets/extraction/`.
- Pipeline in `app/services/importer/`, each step testable on its own:
  1. `pdf_text` — pdfplumber words → lines by vertical position, columns re-anchored by x position;
     clear error for text-less (scanned) PDFs.
  2. `detect` — bank, document type, period, closing/due date (deterministic).
  3. `chunking` — line-boundary chunks sized in estimated tokens, prefers breaking before a dated line;
     repeated page headers/footers removed by position; every drop/limit is a warning.
  4. `extraction` — `extraction.v1` prompt + `ExtractionOutput` schema, chunks in parallel, out-of-period
     dates flagged as low confidence.
  5. `categorize` — `CategoryMemory` first (zero cost), LLM (`categorization.v1`) only for the rest;
     unknown/wrong-kind categories left blank.
  6. dedup — `dedup_hash` vs DB, within file, and near-duplicates (same date+amount, similar text).
- Review screen: edit date/description/category, uncheck rows, duplicate/low-confidence/installment
  badges, cost/latency of the run. Commit navigates to the latest month of the statement.
  Category corrections at review update `CategoryMemory`. History with undo.
- Card invoices: installments keep the printed (original) purchase date, so the statement's invoice
  month is used for `invoice_month`.
- Offline `fake` provider answers extraction with the regex baseline and categorization with keywords,
  so the app, tests and CI run without API keys.
- Acceptance (`tests/test_import.py::test_import_flow_dedup_and_undo` + Playwright run): imports a
  synthetic PDF, re-importing flags every row as duplicate, undo removes the batch.

## Phase 5
- `app/services/assistant/tools.py`: 9 tools (`query_transactions`, `get_summary`, `create_transaction`,
  `create_installment_purchase`, `create_transfer`, `set_budget`, `create_goal`, `update_goal`,
  `delete_transaction`) with JSON schemas; accounts/categories/goals resolved by id or name
  (accent/case-insensitive, ambiguous → error the model must turn into a question).
- `agent.py`: compact context per turn (today, accounts+balances, categories, budgets, goals — never
  transactions), tool loop capped at 6 iterations with a friendly message, read tools run immediately,
  write tools become `PendingAction` rows with a human preview. Confirm re-validates against the current
  state, executes with `origin=assistant` and appends a note to the conversation; cancel likewise.
- Conversations persisted (`AssistantConversation`), prompt `assistant.v1`.
- UI: side panel (Ctrl+/), tool activity hints, confirmation cards.
- Acceptance: `tests/test_assistant.py` covers the three examples end to end (scripted model) incl.
  "no write before confirmation". With a real key, the same flow runs against the configured model.

## Phase 6
- Datasets: 40 statement PDFs + ground truth (phase 4), 145 labelled descriptions
  (`evals/generators/categorization.py`), 31 agent cases (`evals/datasets/agent_cases.yaml`) incl. 6 where
  the right move is to ask. `tests/test_evals.py` checks that every expected number in the agent cases is
  what the tools actually return, and that the checkers pass/fail the right behaviours.
- Suites (`evals/suites/`): extraction (P/R/F1 by date±3d + |amount|, per-field accuracy, parse failure
  rate, cost/statement, p50/p95, per layout), categorization (with/without memory, per category),
  agent (tool, args, final state after confirming, answer numbers, ask-when-ambiguous, confirmation,
  steps, cost, latency), baseline (regex parser).
- Runner `uv run python -m evals.run --suite <s|all> --models provider:model,...` → dated JSON+MD in
  `evals/results/`, `latest.md` with comparison table + data-driven conclusion, regression check against
  `evals/baseline.json` (`--update-baseline`, `--fail-on-regression`).
- CI: offline eval smoke job always; LLM subset job when `GROQ_API_KEY` secret exists.
- **Blocked:** no provider API keys in this environment, so `latest.md` currently only has the offline
  provider + regex baseline (regex: F1 0.855 overall; 1.0 on its own layout, 0.0 on the card invoice, wrong
  signs on the in/out-column layout). To finish the acceptance criterion: put `GROQ_API_KEY`,
  `GEMINI_API_KEY`, `OPENROUTER_API_KEY` in `.env` and run
  `uv run python -m evals.run --suite all --skip-unavailable --update-baseline`.

## Phase 7
- `app/domain/insights.py` (pure, tested): subscription detection (same merchant, ±15% of median, 25–35
  day gaps, ≥3 charges, still active), category anomalies (current vs 3-month average, ≥30% and ≥ R$ 50),
  budget pace projection (linear, day the limit is crossed), end-of-month cash forecast (today's balance +
  future-dated recurring/scheduled entries − card invoices due this month net of payments).
- `app/services/insights.py`: facts with numbers + deterministic default text; `POST /api/insights/narrate`
  asks the LLM (`insights.v1`) to rewrite only title/body from the formatted numbers, falling back to the
  default text on any failure or item-count mismatch.
- Insights screen with "✨ Escrever com IA" (on demand, so no LLM cost on page load).

## Phase 8
- `Dockerfile`: python:3.12-slim + pinned `uv` binary, production deps only (`uv sync --locked --no-dev`),
  non-root user, SQLite in the `/app/data` volume, healthcheck on `/api/health`.
- `docker-compose.yml`: one service, port 8000, optional `.env`, named volume.
- Verified: `docker compose up` → container healthy, first-run setup, account + transaction created,
  data persisted across `docker compose restart`. (The sandbox needed its proxy CA injected through a
  scratch copy of the Dockerfile to download wheels; the committed Dockerfile is the clean one.)
- In `APP_ENV=production` the offline `fake` provider is hidden; AI features need real keys in `.env`.

## Phase 9
- `mcp_server/server.py` on the official MCP Python SDK **v2** (`MCPServer`; v1's FastMCP was renamed).
  Tools reuse the assistant's executors: `get_summary`, `query_transactions`, `create_transaction` (+
  `confirm_action`). Confirmation via elicitation when supported, otherwise two-step.
- `tests/test_mcp.py` spawns the server over stdio with the SDK client: lists tools, answers "quanto gastei
  esse mês?" via `get_summary`, creates with elicitation accept, declines, and the two-step path.
- Setup docs in `docs/mcp.md` (Claude Desktop/Code config, Docker).
