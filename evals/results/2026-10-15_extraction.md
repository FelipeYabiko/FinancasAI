### Extraction

| model | f1 | precision | recall | acc_date | acc_amount | acc_description | acc_type | parse_failure_rate | cost_per_statement_usd | latency_p50_ms | latency_p95_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| groq:openai/gpt-oss-20b | 0.9249 | 1.00 | 0.8603 | 1.00 | 0.7094 | 1.00 | 1.00 | 0.0000 | 0.0007 | 4279 | 22839 |

F1 by layout:

| model | aurora | ipe | lume | mare |
|---|---|---|---|---|
| groq:openai/gpt-oss-20b | 1.00 | 0.9512 | 0.6938 | 1.00 |
