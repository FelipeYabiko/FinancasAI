"""Step 3 — split statement text into LLM-sized chunks on line boundaries.

Never cuts a line in half. Repeated page headers/footers are removed (deterministically) to
save tokens, and every removal or limit hit is reported as a warning — nothing is dropped
silently.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

from app.llm.providers.base import estimate_tokens

DATE_START = re.compile(r"^\s*(\d{1,2}[/.-]\d{1,2}|\d{1,2}\s+[A-Za-z]{3}\b)")
HEADER_ZONE = 6
FOOTER_ZONE = 3
MAX_CHUNKS = 60


@dataclass
class Chunks:
    chunks: list[list[str]]
    warnings: list[str] = field(default_factory=list)
    removed_lines: int = 0


MONEY = re.compile(r"\d,\d{2}\b")


def _shape(line: str) -> str:
    """Comparable form of a line. Digits are masked (page numbers) unless the line carries
    a money amount: then it must repeat verbatim, so a transaction or a daily balance with
    the same layout is never mistaken for a page header."""
    s = re.sub(r"\s+", " ", line.strip().lower())
    return s if MONEY.search(s) else re.sub(r"\d", "#", s)


def _zone_keys(page: list[str]) -> dict[int, tuple]:
    """Line index -> (side, position, shape) for lines in the header/footer zones."""
    keys = {}
    for i, ln in enumerate(page):
        if i < HEADER_ZONE:
            keys[i] = ("h", i, _shape(ln))
        elif i >= len(page) - FOOTER_ZONE:
            keys[i] = ("f", len(page) - i, _shape(ln))
    return keys


def strip_repeated_boilerplate(pages: list[list[str]]) -> tuple[list[list[str]], int]:
    """Remove header/footer lines that repeat at the same position on several pages.
    The header is kept once (first page) because it carries bank/period context."""
    if len(pages) < 2:
        return pages, 0
    page_keys = [_zone_keys(p) for p in pages]
    counts: Counter[tuple] = Counter(k for keys in page_keys for k in set(keys.values()))
    repeated = {k for k, c in counts.items() if c >= 2}
    out, removed = [], 0
    for n, (page, keys) in enumerate(zip(pages, page_keys, strict=True)):
        kept = []
        for i, ln in enumerate(page):
            key = keys.get(i)
            if key in repeated and (n > 0 or key[0] == "f"):
                removed += 1
                continue
            kept.append(ln)
        out.append(kept)
    return out, removed


def chunk_lines(lines: list[str], max_tokens: int) -> Chunks:
    result = Chunks(chunks=[])
    current: list[str] = []
    tokens = 0
    for line in lines:
        t = estimate_tokens(line) + 1
        if t > max_tokens:
            result.warnings.append(
                f"uma linha excede o tamanho do bloco ({t} tokens estimados) e foi enviada sozinha"
            )
        if current and tokens + t > max_tokens:
            # Prefer to break right before a line that starts a new transaction (date first),
            # so a description continued on the next line stays with its transaction.
            cut = len(current)
            for back in range(1, min(8, len(current))):
                if DATE_START.match(current[-back]):
                    cut = len(current) - back
                    break
            if cut == 0:
                cut = len(current)
            result.chunks.append(current[:cut])
            current = current[cut:]
            tokens = sum(estimate_tokens(x) + 1 for x in current)
        current.append(line)
        tokens += t
    if current:
        result.chunks.append(current)
    if len(result.chunks) > MAX_CHUNKS:
        dropped = sum(len(c) for c in result.chunks[MAX_CHUNKS:])
        result.warnings.append(
            f"documento muito grande: {len(result.chunks) - MAX_CHUNKS} bloco(s) "
            f"({dropped} linhas) NÃO foram processados; divida o PDF e importe em partes"
        )
        result.chunks = result.chunks[:MAX_CHUNKS]
    return result
