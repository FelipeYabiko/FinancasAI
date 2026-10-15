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
