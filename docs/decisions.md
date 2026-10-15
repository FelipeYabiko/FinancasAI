# Engineering decisions

Short ADR-style log. Newest at the bottom.

## D1 — Money as integer cents
All amounts are `int` cents everywhere (DB, API, LLM schemas). Floats never touch money.
