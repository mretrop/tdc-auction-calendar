# src/tdc_auction_calendar/collectors/vendors/bid4assets.py
"""Bid4Assets vendor collector — tax sale auctions from bid4assets.com calendar."""

from __future__ import annotations

import re
from datetime import date

import structlog

from tdc_auction_calendar.models.enums import SaleType

logger = structlog.get_logger()

# Month name -> number
_MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

# Matches patterns like "May 8th - 12th", "April 22nd - 22nd"
_DATE_RANGE_RE = re.compile(
    r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)\s*-\s*(\d{1,2})(?:st|nd|rd|th)"
)


def parse_date_range(
    column_month: str, text: str, year: int
) -> tuple[date, date | None] | None:
    """Parse a date range string from the Bid4Assets calendar.

    Args:
        column_month: The month name from the column header (e.g., "May").
        text: The date range text (e.g., "May 8th - 12th").
        year: The calendar year.

    Returns:
        (start_date, end_date) tuple, or None if unparseable.
        end_date is None for single-day auctions (start == end).
    """
    m = _DATE_RANGE_RE.search(text)
    if m is None:
        return None

    month_name, start_day_str, end_day_str = m.group(1), m.group(2), m.group(3)
    month_num = _MONTHS.get(month_name)
    if month_num is None:
        return None

    start_day = int(start_day_str)
    end_day = int(end_day_str)

    try:
        start_date = date(year, month_num, start_day)
    except ValueError:
        return None

    if start_day == end_day:
        return start_date, None

    # Cross-month range: end day < start day means it spans into the next month
    if end_day < start_day:
        end_month = month_num + 1
        end_year = year
        if end_month > 12:
            end_month = 1
            end_year += 1
        try:
            end_date = date(end_year, end_month, end_day)
        except ValueError:
            return None
    else:
        try:
            end_date = date(year, month_num, end_day)
        except ValueError:
            return None

    return start_date, end_date
