# Engineering decisions

Short ADR-style log. Newest at the bottom.

## D1 — Money as integer cents
All amounts are `int` cents everywhere (DB, API, LLM schemas). Floats never touch money.

## D2 — Signed amounts, type as classification
`amount_cents` is signed (in > 0, out < 0) so an account balance is `initial + SUM(amount)`.
`type` (income/expense/transfer) classifies. A refund is an `expense` with a positive amount, so it
reduces the month's expenses instead of inflating income. The API accepts positive magnitudes
plus `type` (+ `is_refund`) and derives the sign.

## D3 — Expenses count in the month of the purchase date
Monthly totals use the transaction date (accrual), including credit card purchases. The invoice
view (`invoice_month`) is a separate lens used by "Faturas em aberto".

## D4 — Credit card due date
If `due_day > closing_day` the invoice is due the same month it closes, otherwise the next month
(e.g. closes 25, due 5).

## D5 — Server-side sessions + double-submit CSRF
Sessions live in a `UserSession` table (revocable on logout) referenced by an HTTP-only cookie.
A second, JS-readable cookie carries a per-session CSRF token that must come back in the
`X-CSRF-Token` header on every non-GET request.

## D6 — Recurring rules materialize when the month arrives
`run_recurring` creates the transaction for every month from `start_month` to the current month
that doesn't have one yet (key: `recurring_rule_id + recurring_month`). It runs on dashboard
load, on rule create/update and via `POST /api/recurring/run`; it is idempotent.

## D7 — No migrations framework (yet)
`SQLModel.metadata.create_all` at startup. Fine for a single-household SQLite app; Alembic is a
listed next step if the schema starts changing under real data.

## D8 — Balances up to today
Account balances only include transactions dated up to today (future installments and recurring
entries already generated for later this month don't count yet).

## D9 — Frontend without a build step
ES modules + a tiny tagged-template `html` helper that escapes every interpolation (XSS-safe by
default). Chart.js is vendored instead of loaded from a CDN so the CSP can be `script-src 'self'`.

## D10 — One OpenAI-compatible transport for all providers
Groq, OpenRouter and Gemini (via its OpenAI compatibility endpoint) share the chat-completions wire
format, so a single implementation handles tools, JSON output and usage. Provider classes only set
base URL, auth headers and quirks (Groq gets `json_object` instead of `json_schema`). The raw
assistant message is echoed back verbatim in tool loops, which preserves provider-specific fields
such as Gemini thought signatures. No LangChain.

## D11 — Validation retry is exactly one, and both attempts are traced
If the output fails the Pydantic schema, the model gets its own answer plus the validation error and
one more chance. Each provider response is a separate `LLMCall` row (`validation_error`, then
`ok`/`validation_error`) so the cost of the retries is visible.

## D12 — Groq Llama models out of the defaults
Groq lists `llama-3.1-8b-instant`/`llama-3.3-70b-versatile` as "contact sales" pricing, so the
defaults use `openai/gpt-oss-20b` (extraction, categorization, insights) and `openai/gpt-oss-120b`
(assistant), which have public prices.

## D13 — Stateless review between preview and commit
The preview response carries the extracted rows; the client sends the (edited) rows back on commit.
Nothing extracted is persisted before confirmation except the `ImportBatch` metadata, and the PDF
bytes never touch the disk.

## D14 — Header/footer stripping by position, not by text alone
Lines are boilerplate only if they repeat at the same position (top/bottom zone) on several pages.
Lines with a money amount must repeat verbatim; otherwise digits are masked (page numbers). This keeps
a "SALDO DO DIA" or a recurring purchase from being mistaken for a header.

## D15 — Same-file duplicates stay selected
Two identical lines in one statement are usually two real purchases, so they are flagged ("repetida no
arquivo") but not unchecked. DB duplicates and near-duplicates are unchecked by default.

## D16 — Fake provider doubles as an offline demo
Without API keys the `fake` provider runs the regex baseline for extraction and keyword rules for
categorization. It is labelled as such and reported in evals as the deterministic floor, never as an LLM.
