"""
Expiration date utilities for the options data collection pipeline.

When the current date coincides with an expiration date, data collection
should skip today's expiration and begin from the next available one.
This module centralizes that logic so find_near_delta_puts.py,
upload_to_sheet.py, and atm_straddle.py all share the same behavior.
"""

from datetime import datetime, timedelta


def is_today_an_expiration(exp_date_str: str) -> bool:
    """Return True if *exp_date_str* (YYYY-MM-DD) matches today's date."""
    today = datetime.now().date()
    try:
        exp = datetime.strptime(exp_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return False
    return exp == today


def next_available_expiration(exp_date_str: str, available_dates: list[str] | None = None) -> str | None:
    """Given an expiration date string, return the next *non-today* expiration.

    If *exp_date_str* is today, skip it and return the next available date.
    When *available_dates* is provided (sorted YYYY-MM-DD strings), pick the
    next one after today.  Otherwise fall back to adding 7 days.

    Returns None when no next date could be determined.
    """
    if not is_today_an_expiration(exp_date_str):
        return exp_date_str

    if available_dates:
        today_str = datetime.now().date().isoformat()
        for d in available_dates:
            if d > today_str:
                return d
    else:
        today = datetime.now().date()
        fallback = (today + timedelta(days=7)).isoformat()
        return fallback

    return None


def next_friday_skip_today(skip: int = 0) -> datetime:
    """Return the Nth Friday from today, skipping today if it IS Friday.

    This is the drop-in replacement for the ad-hoc *next_friday* helpers in
    find_near_delta_puts.py and upload_to_sheet.py.
    """
    today = datetime.now()
    days_until_friday = (4 - today.weekday()) % 7

    # If today is Friday, always advance to next week
    if days_until_friday == 0:
        target = today + timedelta(days=7)
    else:
        target = today + timedelta(days=days_until_friday)

    return target + timedelta(weeks=skip)