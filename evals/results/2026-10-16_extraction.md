### Extraction

| model | f1 | precision | recall | acc_date | acc_amount | acc_description | acc_type | parse_failure_rate | cost_per_statement_usd | latency_p50_ms | latency_p95_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| groq:openai/gpt-oss-20b @extraction.v1 | 0.9697 | 1.00 | 0.9412 | 1.00 | 0.7344 | 1.00 | 1.00 | 0.0000 | 0.0007 | 2796 | 23326 |
| groq:openai/gpt-oss-20b @extraction.v2 | 0.9624 | 0.9846 | 0.9412 | 1.00 | 1.00 | 1.00 | 1.00 | 0.0000 | 0.0008 | 34120 | 54679 |

F1 by layout:

| model | aurora | ipe | lume | mare |
|---|---|---|---|---|
| groq:openai/gpt-oss-20b @extraction.v1 | 1.00 | 0.9512 | 0.9333 | 1.00 |
| groq:openai/gpt-oss-20b @extraction.v2 | 1.00 | 0.9512 | 0.9032 | 1.00 |
