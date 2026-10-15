"""Step 2 — detect bank, document type and statement period (deterministic)."""

import re
from dataclasses import dataclass
from datetime import date

from app.domain.dates import month_key
from app.domain.normalize import strip_accents

BANK_PATTERNS: list[tuple[str, str]] = [
    # fictional banks used by the synthetic dataset
    (r"banco aurora", "Banco Aurora"),
    (r"cooperativa (de credito )?ipe", "Cooperativa Ipê"),
    (r"lume ?card", "Lume Card"),
    (r"banco mare\b", "Banco Maré"),
    # common real-world issuers (name detection only)
    (r"\bnubank\b|nu pagamentos", "Nubank"),
    (r"\bitau\b", "Itaú"),
    (r"\bbradesco\b", "Bradesco"),
    (r"banco do brasil", "Banco do Brasil"),
    (r"\bcaixa\b", "Caixa"),
    (r"\bsantander\b", "Santander"),
    (r"banco inter\b|\binter&co", "Inter"),
    (r"\bc6 ?bank\b", "C6 Bank"),
    (r"\bsicoob\b", "Sicoob"),
    (r"\bsicredi\b", "Sicredi"),
]

CARD_HINTS = ["fatura", "vencimento", "pagamento minimo", "limite", "cartao final", "fechamento"]
CHECKING_HINTS = [
    "extrato",
    "saldo anterior",
    "saldo do dia",
    "saldo inicial",
    "agencia",
    "conta corrente",
    "movimentacao",
]

_DATE = r"(\d{2})/(\d{2})/(\d{2,4})"


@dataclass
class DocumentInfo:
    bank: str | None
    document_type: str  # checking_statement | credit_card_invoice | unknown
    period_start: date | None = None
    period_end: date | None = None
    closing_date: date | None = None
    due_date: date | None = None

    @property
    def reference_year(self) -> int | None:
        d = self.period_end or self.closing_date or self.due_date
        return d.year if d else None

    @property
    def invoice_month(self) -> str | None:
        if self.document_type != "credit_card_invoice":
            return None
        if self.closing_date:
            return month_key(self.closing_date)
        if self.period_end:
            return month_key(self.period_end)
        return None


def _to_date(d: str, m: str, y: str) -> date | None:
    year = int(y) + 2000 if len(y) == 2 else int(y)
    try:
        return date(year, int(m), int(d))
    except ValueError:
        return None


def detect_document(lines: list[str]) -> DocumentInfo:
    head = [strip_accents(ln).lower() for ln in lines[:40]]
    blob = "\n".join(head)
    bank = next((name for pat, name in BANK_PATTERNS if re.search(pat, blob)), None)

    card_score = sum(blob.count(h) for h in CARD_HINTS)
    checking_score = sum(blob.count(h) for h in CHECKING_HINTS)
    if card_score == checking_score == 0:
        doc_type = "unknown"
    else:
        doc_type = "credit_card_invoice" if card_score > checking_score else "checking_statement"

    info = DocumentInfo(bank=bank, document_type=doc_type)
    m = re.search(rf"{_DATE}\s*(?:a|ate|-|–)\s*{_DATE}", blob)
    if m:
        info.period_start = _to_date(*m.groups()[:3])
        info.period_end = _to_date(*m.groups()[3:])
    else:
        # "de 01/09 a 30/09/2026"
        m = re.search(r"(\d{2})/(\d{2})\s*(?:a|ate|-)\s*(\d{2})/(\d{2})/(\d{4})", blob)
        if m:
            d1, m1, d2, m2, y = m.groups()
            info.period_end = _to_date(d2, m2, y)
            start_year = int(y) - (1 if int(m1) > int(m2) else 0)
            info.period_start = _to_date(d1, m1, str(start_year))
    m = re.search(rf"fechamento:?\s*{_DATE}", blob)
    if m:
        info.closing_date = _to_date(*m.groups())
    m = re.search(rf"vencimento:?\s*{_DATE}", blob)
    if m:
        info.due_date = _to_date(*m.groups())
    if info.period_end is None and info.closing_date:
        info.period_end = info.closing_date
    return info
