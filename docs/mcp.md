# MCP server

The MCP server (`mcp_server/server.py`, official MCP Python SDK v2, stdio transport) exposes the household
data to any MCP client (Claude Desktop, Claude Code, IDEs…).

| Tool | What it does |
|---|---|
| `get_summary(month?, category?, account?)` | Month totals, spending by category, budgets, change vs previous month |
| `query_transactions(text?, category?, account?, type?, month?, date_from?, date_to?, limit?)` | Search + totals for the filter |
| `create_transaction(description, amount_cents, type?, account?, category?, date?)` | Proposes a transaction and asks for confirmation |
| `confirm_action(action_id, confirm?)` | Second step for clients without elicitation |

**Confirmation.** `create_transaction` uses MCP *elicitation* when the client supports it (the user sees
"Confirmar? Despesa de R$ 10,00 …" and accepts/declines). Clients without elicitation get
`status: pending_confirmation` + `action_id`; the transaction is only written after `confirm_action`, which
MCP clients surface as a separate tool call for the user to approve.

## Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "financasia": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/FinancasAI", "python", "-m", "mcp_server"],
      "env": { "DATABASE_URL": "sqlite:////path/to/FinancasAI/data/financasia.db" }
    }
  }
}
```

With Docker (same volume as the web app):

```bash
docker compose run --rm -i app python -m mcp_server
```

Then ask: *"quanto gastei esse mês?"* → the client calls `get_summary` and answers from the returned totals.
`tests/test_mcp.py` does exactly this with the SDK's stdio client.
