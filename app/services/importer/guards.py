"""Defenses for untrusted document text reaching the LLM (prompt injection, hallucination).

Statement text is external data: a description can carry instructions aimed at the model
("ignore as instruções…"). The pipeline never trusts the model's output blindly:

1. Grounding: every extracted amount must literally appear in the chunk the model read.
   A transaction whose value is not in the text was invented (by an injection or a
   hallucination) and is flagged with low confidence for the review screen.
2. Detection: text that looks like instructions to an AI raises a visible warning.
3. Coverage: lines that look like transactions (a leading date and an amount) are counted
   without the model; an extraction that returns far fewer rows is flagged. This catches
   rows the model skipped, including an injection that suppresses rows instead of adding one.
4. Architecture: imports are reviewed before saving and the assistant cannot write without a
   human click, so a successful injection still cannot change data silently.
"""

import re

from app.domain.normalize import strip_accents

# 1.234,56 | 234,56 | 1234,56 — optional sign/currency handled by the caller
_MONEY = re.compile(r"(?<![\d,.])(\d{1,3}(?:\.\d{3})+|\d+),(\d{2})(?!\d)")

INJECTION_PATTERNS = [
    r"ignor\w*\s+(as\s+|todas\s+as\s+|the\s+|all\s+)?(instruc|previous|anterior|regras)",
    r"\b(system\s*prompt|prompt\s+do\s+sistema)\b",
    r"\bvoce\s+(agora\s+)?(e|eh)\s+um\b",
    r"\byou\s+are\s+now\b",
    r"\b(novas?\s+instruc\w*|new\s+instructions?)\b",
    r"\b(apague|delete|remova)\s+(todas|tudo|all)\b",
    r"\b(retorne|devolva|return)\s+(apenas|only|o\s+json|json)\b",
    r"\bamount_cents\b",
]
_INJECTION_RE = [re.compile(p) for p in INJECTION_PATTERNS]

# "12/05", "12/05/2026" or "12 MAR" at the start of the line
_ROW_DATE = re.compile(r"^\s*(\d{2}/\d{2}(?:/\d{2,4})?|\d{2}\s+[A-Za-z]{3})\b")
_NOT_A_ROW = re.compile(r"\b(saldo|total|subtotal|limite|pagamento minimo)\b")
COVERAGE_MIN = 0.85  # warn when the model returns fewer rows than this share of candidates


def amounts_in_text(text: str) -> set[int]:
    """Absolute values (cents) of every BRL-formatted amount in the text."""
    out = set()
    for integer, dec in _MONEY.findall(text):
        out.add(int(integer.replace(".", "")) * 100 + int(dec))
    return out


def is_grounded(amount_cents: int, available: set[int]) -> bool:
    return abs(amount_cents) in available


def count_candidate_rows(lines: list[str]) -> int:
    """Lines with a leading date and an amount that aren't balances or totals."""
    n = 0
    for line in lines:
        looks_like_row = _ROW_DATE.search(line) and _MONEY.search(line)
        if looks_like_row and not _NOT_A_ROW.search(strip_accents(line).lower()):
            n += 1
    return n


def low_coverage(extracted: int, candidates: int) -> bool:
    return candidates >= 5 and extracted < COVERAGE_MIN * candidates


def find_injection_markers(lines: list[str]) -> list[str]:
    """Lines that look like instructions to an AI (normalized, case/accent-insensitive)."""
    hits = []
    for line in lines:
        norm = strip_accents(line).lower()
        if any(p.search(norm) for p in _INJECTION_RE):
            hits.append(line.strip()[:120])
    return hits
