"""Description normalization (used for category memory, dedup and grouping)."""

import re
import unicodedata

_NOISE_PATTERNS = [
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",  # dates and installment markers (03/10)
    r"\bparc(?:ela)?\s*\d+\b",
    r"\*+",
    r"\b\d+\b",  # bare numbers (card terminals, ids)
]
_PREFIXES = (
    "compra no debito",
    "compra no credito",
    "compra cartao",
    "pagamento cartao",
    "pag ",
    "deb aut ",
)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_description(text: str) -> str:
    s = strip_accents(text).lower()
    for pat in _NOISE_PATTERNS:
        s = re.sub(pat, " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for prefix in _PREFIXES:
        if s.startswith(prefix) and len(s) > len(prefix) + 2:
            s = s[len(prefix) :].strip()
    return s
