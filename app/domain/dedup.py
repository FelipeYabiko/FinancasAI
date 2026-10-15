"""Duplicate detection for imported transactions."""

import hashlib
from datetime import date
from difflib import SequenceMatcher

NEAR_DUPLICATE_THRESHOLD = 0.85


def dedup_hash(d: date, amount_cents: int, normalized_description: str, account_id: int) -> str:
    raw = f"{d.isoformat()}|{amount_cents}|{normalized_description}|{account_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def description_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def is_near_duplicate(
    a_date: date, a_amount: int, a_desc: str, b_date: date, b_amount: int, b_desc: str
) -> bool:
    """Same date and amount, and descriptions similar enough (normalized)."""
    if a_date != b_date or a_amount != b_amount:
        return False
    return description_similarity(a_desc, b_desc) >= NEAR_DUPLICATE_THRESHOLD
