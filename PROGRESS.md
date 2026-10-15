# PROGRESS

Build log for FinançasIA v9. Each phase ends with lint + tests green and a commit.
To resume in a new session: read this file, then continue with the first phase not marked done.

| Phase | Status |
|---|---|
| 0 — Repo, tooling, CI | ✅ done |
| 1 — Domain + API | ⏳ next |
| 2 — Frontend + login | ⬜ |
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
