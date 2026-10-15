"""Deterministic regex parser (baseline for the evals; also powers the offline `fake` provider).

Written for the "Banco Aurora" synthetic layout (dd/mm/yyyy, signed amount column, daily
balance rows). It generalizes a little (dd/mm and dd/mm/yy dates, trailing minus) but makes no
attempt at multi-line descriptions, separate in/out columns or card invoices — that gap is
exactly what the LLM vs. regex comparison measures.
"""

import re
from datetime import date

from app.domain.money import parse_brl

LINE_RE = re.compile(
    r"^\s*(?P<date>\d{2}/\d{2}(?:/\d{2,4})?)\s+(?P<desc>.+?)\s{2,}"
    r"(?P<amount>-?(?:R\$\s*)?\d{1,3}(?:\.\d{3})*,\d{2}-?)(?:\s|$)"
)
SKIP = re.compile(r"\bsaldo\b", re.IGNORECASE)


def parse_lines(lines: list[str], reference_year: int | None = None) -> list[dict]:
    out = []
    for line in lines:
        m = LINE_RE.match(line)
        if not m or SKIP.search(m.group("desc")):
            continue
        parts = m.group("date").split("/")
        day, month = int(parts[0]), int(parts[1])
        if len(parts) == 3:
            year = int(parts[2]) + (2000 if len(parts[2]) == 2 else 0)
        elif reference_year:
            year = reference_year
        else:
            continue
        try:
            d = date(year, month, day)
            amount = parse_brl(m.group("amount"))
        except ValueError:
            continue
        desc = " ".join(m.group("desc").split())
        if "PAGAMENTO FATURA" in desc.upper() or "PAGAMENTO RECEBIDO" in desc.upper():
            tx_type = "transfer"
        else:
            tx_type = "income" if amount > 0 else "expense"
        out.append({
            "date": d.isoformat(),
            "description": desc,
            "amount_cents": amount,
            "type": tx_type,
            "confidence": 0.9,
            "installment_number": None,
            "installment_total": None,
        })  # fmt: skip
    return out
