"""Pure date helpers. Months are represented as 'YYYY-MM' strings."""

import calendar
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")


def today() -> date:
    return datetime.now(TZ).date()


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def parse_month(month: str) -> tuple[int, int]:
    year, mon = month.split("-")
    y, m = int(year), int(mon)
    if not 1 <= m <= 12:
        raise ValueError(f"invalid month: {month}")
    return y, m


def add_months_to_month(month: str, n: int) -> str:
    y, m = parse_month(month)
    idx = y * 12 + (m - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def clamp_day(year: int, month: int, day: int) -> date:
    """Date with `day` clamped to the last day of the month (e.g. 31 -> 28 in Feb)."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(max(day, 1), last))


def add_months(d: date, n: int) -> date:
    y, m = parse_month(add_months_to_month(month_key(d), n))
    return clamp_day(y, m, d.day)


def month_bounds(month: str) -> tuple[date, date]:
    """First and last day of a 'YYYY-MM' month."""
    y, m = parse_month(month)
    return date(y, m, 1), clamp_day(y, m, 31)


def month_range(start: str, end: str) -> list[str]:
    """Inclusive list of months from start to end (empty if start > end)."""
    out: list[str] = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur = add_months_to_month(cur, 1)
    return out
