# Eval results (latest)

- **extraction**: 2026-10-15T14:00:50+00:00 · commit `9674aa6` · prompts extraction.v1, categorization.v1, assistant.v1, insights.v1
- **categorization**: 2026-10-15T14:00:50+00:00 · commit `9674aa6` · prompts extraction.v1, categorization.v1, assistant.v1, insights.v1
- **agent**: 2026-10-15T14:00:51+00:00 · commit `9674aa6` · prompts extraction.v1, categorization.v1, assistant.v1, insights.v1
- **baseline**: 2026-10-15T14:00:55+00:00 · commit `9674aa6` · prompts extraction.v1, categorization.v1, assistant.v1, insights.v1

## Comparison

| model | extraction F1 | cost / statement (USD) | extraction p95 (ms) | categ. acc | categ. acc + memory | agent pass rate | cost / agent case (USD) |
|---|---|---|---|---|---|---|---|
| fake:fake | 0.8551 | 0.0000 | 5 | 0.6138 | 0.6759 | 0.0000 | 0.0000 |
| regex-baseline (no LLM) | 0.8551 | 0.0000 | 154 | — | — | — | — |

## Conclusion

_No real LLM has been evaluated yet in this results folder (only the offline baseline/fake provider). Configure API keys in `.env` and run `uv run python -m evals.run --suite all` to fill the comparison; this paragraph is generated from the measured numbers._

> `fake:fake` is the offline stand-in provider (regex parser for extraction, keyword rules for categorization, a rule-based toy for the agent). It is **not an LLM**; it shows the deterministic floor and proves the harness runs end to end without API keys.

## Details

### Extraction

| model | f1 | precision | recall | acc_date | acc_amount | acc_description | acc_type | parse_failure_rate | cost_per_statement_usd | latency_p50_ms | latency_p95_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fake:fake | 0.8551 | 1.00 | 0.7469 | 1.00 | 0.7315 | 0.9598 | 0.7443 | 0.0000 | 0.0000 | 3 | 5 |

F1 by layout:

| model | aurora | ipe | lume | mare |
|---|---|---|---|---|
| fake:fake | 1.00 | 1.00 | 0.0000 | 1.00 |

### Baseline (regex parser, no LLM)

| model | f1 | precision | recall | acc_date | acc_amount | acc_description | acc_type | parse_failure_rate | cost_per_statement_usd | latency_p50_ms | latency_p95_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| regex-baseline | 0.8551 | 1.00 | 0.7469 | 1.00 | 0.7315 | 0.9598 | 0.7443 | 0.0000 | 0.0000 | 62 | 154 |

F1 by layout:

| model | aurora | ipe | lume | mare |
|---|---|---|---|---|
| regex-baseline | 1.00 | 1.00 | 0.0000 | 1.00 |

### Categorization (145 labelled descriptions)

| model | accuracy (no memory) | accuracy (with memory) | memory hits | cost no-mem (USD) | cost with-mem (USD) |
|---|---|---|---|---|---|
| fake:fake | 0.6138 | 0.6759 | 33 | 0.0000 | 0.0000 |

Per-category accuracy (no memory):

| category | fake:fake |
|---|---|
| Assinaturas | 0.7000 |
| Compras | 0.0000 |
| Contas e serviços | 0.9000 |
| Delivery | 0.7273 |
| Educação | 0.0000 |
| Freelance | 0.0000 |
| Impostos e taxas | 0.0000 |
| Investimentos | 0.0000 |
| Lazer | 0.0000 |
| Mercado | 1.00 |
| Moradia | 0.0000 |
| Outras receitas | 1.00 |
| Outros | 1.00 |
| Pets | 0.0000 |
| Restaurantes | 0.7500 |
| Salário | 1.00 |
| Saúde | 0.8000 |
| Transporte | 0.8750 |
| Viagem | 0.0000 |

### Agent

| model | pass_rate | tool_accuracy | args_accuracy | state_accuracy | answer_accuracy | ask_when_ambiguous | confirmation_before_write | avg_steps | cost_per_case_usd | latency_p95_ms |
|---|---|---|---|---|---|---|---|---|---|---|
| fake:fake | 0.0000 | 0.3913 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.00 | 2.00 | 0.0000 | 2 |

## Methodology

- **Extraction** — 40 synthetic PDFs (4 fictional layouts, 1,466 transactions) with JSON ground truth
  (`evals/datasets/extraction`). A predicted transaction matches a gold one when |amount| is equal and the
  date is within ±3 days; precision/recall/F1 count matches. Field accuracy is measured on matched pairs:
  exact date, exact signed amount, normalized description similarity ≥ 0.8, exact type. Parse failure rate =
  chunks whose output failed validation twice (or the provider failed) / chunks. Cost comes from token usage ×
  `app/llm/pricing.yaml`; latency is wall-clock per statement (chunks run 4 in parallel).
- **Categorization** — labelled descriptions (`evals/datasets/categorization.json`), scored against the
  default categories. "With memory" pre-loads `CategoryMemory` with one plain descriptor per merchant (what a
  user correction would store) and evaluates every statement variant, so hits depend on normalization.
- **Agent** — cases in `evals/datasets/agent_cases.yaml`, each on a freshly seeded in-memory DB with a fixed
  "today". Checks: proposed write tools and arguments (resolved to ids), DB state after confirming every
  proposal, read tools used for questions, numbers in the answer, asking instead of acting on ambiguous
  requests, and that nothing was written before confirmation.
- **Baseline** — the regex parser (`app/services/importer/baseline.py`), written for the "aurora" layout,
  scored with the same matcher.
- Regressions: `evals/baseline.json` stores headline metrics per suite/model; the runner flags accuracy drops
  > 3 points and cost/latency increases > 50%.
