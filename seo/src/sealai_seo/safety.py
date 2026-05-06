from __future__ import annotations

from datetime import date

from .config import MAX_DAYS_BACKFILL, MAX_REQUESTS_PER_RUN


def inclusive_days(start: date, end: date) -> int:
    return (end - start).days + 1


def enforce_date_range(start: date, end: date) -> None:
    if end < start:
        raise ValueError("date-to must be on or after date-from")
    days = inclusive_days(start, end)
    if days > MAX_DAYS_BACKFILL:
        raise ValueError(f"date range has {days} days; limit is {MAX_DAYS_BACKFILL}")


def enforce_request_budget(next_request_number: int) -> None:
    if next_request_number > MAX_REQUESTS_PER_RUN:
        raise ValueError(f"request budget exceeded; limit is {MAX_REQUESTS_PER_RUN}")
