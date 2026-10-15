"""Defenses for untrusted document text reaching the LLM (prompt injection, hallucination).

Statement text is external data: a description can carry instructions aimed at the model
("ignore as instruções…"). The pipeline never trusts the model's output blindly:

1. Grounding: every extracted amount must literally appear in the chunk the model read.
   A transaction whose value is not in the text was invented (by an injection or a
   hallucination) and is flagged with low confidence for the review screen.
2. Detection: text that looks like instructions to an AI raises a visible warning.
3. Architecture: imports are reviewed before saving and the assistant cannot write without a
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


def amounts_in_text(text: str) -> set[int]:
    """Absolute values (cents) of every BRL-formatted amount in the text."""
    out = set()
    for integer, dec in _MONEY.findall(text):
        out.add(int(integer.replace(".", "")) * 100 + int(dec))
    return out


def is_grounded(amount_cents: int, available: set[int]) -> bool:
    return abs(amount_cents) in available


def find_injection_markers(lines: list[str]) -> list[str]:
    """Lines that look like instructions to an AI (normalized, case/accent-insensitive)."""
    hits = []
    for line in lines:
        norm = strip_accents(line).lower()
        if any(p.search(norm) for p in _INJECTION_RE):
            hits.append(line.strip()[:120])
    return hits
