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

## D17 — Writes are proposals, enforced by architecture
The model never has a tool that writes. Write tools validate + build a preview and store a
`PendingAction`; only `POST /api/assistant/actions/{id}/confirm` (a human click) executes it, after
re-validating. "Asked for confirmation before writing" is therefore guaranteed, and the agent eval
measures whether the *proposed* action is the right one.

## D18 — Name resolution in Python, not in the prompt
Tools accept "Nubank" or "3". Resolution is deterministic (exact → unique substring), and ambiguity
returns an error telling the model to ask the user. This keeps ids out of the model's memory burden
and makes ambiguous cases testable.

## D19 — Extraction matching by |amount| + date ± 3 days
Matching on exact date+amount would make date/amount accuracy trivially 100%. Matching on the absolute
amount with a small date window lets the suite measure sign errors (in/out columns, card invoices) and
date errors (year inference) as field accuracy instead of as missing transactions.

## D20 — Memory eval uses one plain descriptor per merchant
"With memory" seeds `CategoryMemory` with what a single user correction would store, then scores all
statement variants. Gains therefore come from normalization quality, not from leaking labels.

## D21 — The report's conclusion is generated from the numbers
`evals/report.py` writes the "which model for which feature" paragraph from the latest results (best
quality vs. cheapest within 2 points). The offline provider is never recommended. No numbers are
written by hand.

## D22 — Insights: numbers first, LLM as copywriter
Every number is computed in Python and pre-formatted (`R$ 1.234,56`) before the LLM sees it; the
prompt forbids new numbers and the response must have one item per fact or it is discarded. Narration
is on demand, so page loads cost nothing.

## D23 — Prompt changes ship only with a side-by-side eval
`extraction.v2` targets the two weak spots the v1 run exposed (trailing-minus signs, skipped invoice rows):
explicit sign rules per document type, two worked examples, "extract every dated row", and a final
self-check. `--prompt-version v1,v2` runs both versions on the same statements in one report; the default
only changes when v2 wins on the full 40-statement set.

## D24 — Prompt injection: defense in layers, measured
No single filter stops injection, so each layer is cheap and independent: data delimited and labelled as
data in the prompt, regex markers surfaced as an import warning (not silently dropped: a false positive
must not lose a real transaction), grounding (an amount absent from its chunk is capped at confidence 0.3),
"only user messages request actions" in `assistant.v2`, and the architectural backstop that the model can
only propose writes. Adversarial PDFs and agent cases make the defense a number instead of a claim.

## D25 — A separate Java service, integrated by events
Alerts live in `alerts-service` (Spring Boot, MongoDB), not in the FastAPI app, to exercise a real service
boundary: own database, contract-tested message, failure isolation (the app works with the service down).
Events go through a transactional outbox (no dual write) and are delivered at-least-once; the consumer is
idempotent by `(eventId, rule)`. The event carries the facts the rules need, computed as of the transaction
(`id <= tx.id`), because the relay may publish after later transactions exist. RabbitMQ over Kafka: one
consumer, work-queue semantics and a DLQ are what this needs; the outbox/idempotency design carries over.

## D26 — LLM text in alerts must quote only known numbers
`LlmAlertWriter` asks for a one-sentence alert from the rule's facts and rejects the answer if it cites any
`R$` value that isn't among them, falling back to the deterministic template. Same principle as D22.
