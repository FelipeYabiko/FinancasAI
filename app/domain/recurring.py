"""Recurring rule scheduling."""

from datetime import date

from app.domain.dates import add_months_to_month, clamp_day, month_range, parse_month


def months_to_generate(
    start_month: str,
    current_month: str,
    already_generated: set[str],
) -> list[str]:
    """Months (from the rule start up to the current month) that still need a
    transaction. Months already generated are skipped, so running this any
    number of times never duplicates."""
    return [m for m in month_range(start_month, current_month) if m not in already_generated]


def occurrence_date(month: str, day_of_month: int) -> date:
    y, m = parse_month(month)
    return clamp_day(y, m, day_of_month)


def next_occurrence(start_month: str, day_of_month: int, after: date) -> date:
    """First occurrence strictly after `after` (used by forecasts)."""
    month = max(start_month, f"{after.year:04d}-{after.month:02d}")
    while True:
        d = occurrence_date(month, day_of_month)
        if d > after:
            return d
        month = add_months_to_month(month, 1)
