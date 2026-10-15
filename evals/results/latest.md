# Eval results (latest)

- **extraction**: 2026-10-15T15:16:58+00:00 · commit `b55936d` · prompts extraction.v1, categorization.v1, assistant.v1, insights.v1 · subset ci
- **categorization**: 2026-10-15T14:00:50+00:00 · commit `9674aa6` · prompts extraction.v1, categorization.v1, assistant.v1, insights.v1
- **agent**: 2026-10-15T15:19:05+00:00 · commit `b55936d` · prompts extraction.v1, categorization.v1, assistant.v1, insights.v1 · subset ci
- **baseline**: 2026-10-15T16:40:01+00:00 · commit `b55936d` · prompts extraction.v1, categorization.v1, assistant.v1, insights.v1 · subset ci

## Comparison

| model | eval set | extraction F1 | cost / statement (USD) | extraction p95 (ms) | categ. acc | categ. acc + memory | agent pass rate | cost / agent case (USD) |
|---|---|---|---|---|---|---|---|---|
| groq:openai/gpt-oss-20b | 4 PDFs / 6 cases | 0.9249 | 0.0007 | 22839 | — | — | 1.00 | 0.0003 |
| fake:fake | 19 categories | — | — | — | 0.6138 | 0.6759 | — | — |
| regex-baseline (no LLM) | 4 PDFs | 0.8667 | 0.0000 | 90 | — | — | — | — |

## Conclusion

Only one LLM has been evaluated so far: `groq:openai/gpt-oss-20b` — extraction F1 0.9249 on 4 statements (US$ 0.000708/statement, p95 22839 ms); agent pass rate 1.0 on 6 cases. No model choice can be made from a single data point; the multi-model comparison is pending (run `uv run python -m evals.run --suite all` with keys for other providers).

> `fake:fake` is the offline stand-in provider (regex parser for extraction, keyword rules for categorization, a rule-based toy for the agent). It is **not an LLM**; it shows the deterministic floor and proves the harness runs end to end without API keys.

## Details

### Extraction

| model | f1 | precision | recall | acc_date | acc_amount | acc_description | acc_type | parse_failure_rate | cost_per_statement_usd | latency_p50_ms | latency_p95_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| groq:openai/gpt-oss-20b | 0.9249 | 1.00 | 0.8603 | 1.00 | 0.7094 | 1.00 | 1.00 | 0.0000 | 0.0007 | 4279 | 22839 |

F1 by layout:

| model | aurora | ipe | lume | mare |
|---|---|---|---|---|
| groq:openai/gpt-oss-20b | 1.00 | 0.9512 | 0.6938 | 1.00 |

### Baseline (regex parser, no LLM)

| model | f1 | precision | recall | acc_date | acc_amount | acc_description | acc_type | parse_failure_rate | cost_per_statement_usd | latency_p50_ms | latency_p95_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| regex-baseline | 0.8667 | 1.00 | 0.7647 | 1.00 | 0.7692 | 0.9712 | 0.7692 | 0.0000 | 0.0000 | 63 | 90 |

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
| groq:openai/gpt-oss-20b | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.83 | 0.0003 | 1094 |

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
