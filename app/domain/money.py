"""Money parsing/formatting. Amounts are always integer cents."""

import re

_AMOUNT_RE = re.compile(
    r"^(?P<lead>[-+−])?\s*(?:R\$\s*)?(?P<lead2>[-+−])?\s*(?P<num>\d{1,3}(?:\.\d{3})*|\d+)"
    r"(?:,(?P<dec>\d{1,2}))?\s*(?P<trail>[-+−DC])?$",
    re.IGNORECASE,
)


def parse_brl(text: str) -> int:
    """Parse a Brazilian-formatted amount into signed cents.

    Handles `1.234,56`, `R$ 10,00`, `-50,00`, trailing sign `150,00-`, and the
    `D`/`C` (débito/crédito) suffix used by some statements.
    """
    s = text.strip().replace(" ", " ")
    m = _AMOUNT_RE.match(s)
    if not m:
        raise ValueError(f"not a BRL amount: {text!r}")
    integer = int(m.group("num").replace(".", ""))
    dec = (m.group("dec") or "0").ljust(2, "0")
    cents = integer * 100 + int(dec)
    signs = {m.group("lead"), m.group("lead2"), (m.group("trail") or "").upper()}
    negative = bool(signs & {"-", "−", "D"})
    return -cents if negative else cents


def format_brl(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    integer, dec = divmod(cents, 100)
    int_str = f"{integer:,}".replace(",", ".")
    return f"{sign}R$ {int_str},{dec:02d}"


def cents_to_decimal(cents: int, sep: str = ",") -> str:
    """`-12345` -> `-123,45` (no thousands separator, integer math only)."""
    sign = "-" if cents < 0 else ""
    integer, dec = divmod(abs(cents), 100)
    return f"{sign}{integer}{sep}{dec:02d}"
