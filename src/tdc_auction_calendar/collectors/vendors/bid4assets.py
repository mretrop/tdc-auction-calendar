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


# Matches: "County Name, ST ..."
_TITLE_COUNTY_STATE_RE = re.compile(
    r"^(.+?)\s+County,\s*([A-Z]{2})\s+"
)
# Matches: "City Name Tax ..." (no comma/state — independent cities)
_TITLE_CITY_RE = re.compile(
    r"^(.+?)\s+Tax\s+"
)

_SALE_TYPE_MAP: dict[str, SaleType] = {
    "tax defaulted": SaleType.DEED,
    "tax foreclosed": SaleType.DEED,
    "tax title/surplus": SaleType.DEED,
    "tax title": SaleType.DEED,
    "repository": SaleType.DEED,
    "tax lien": SaleType.LIEN,
}


def parse_title(title: str) -> tuple[str, str | None, SaleType] | None:
    """Parse county, state, and sale type from an auction title.

    Returns:
        (county, state, sale_type) tuple, or None if unparseable.
        state may be None for independent cities.
    """
    title = title.strip()

    # Try "County Name, ST ..." pattern first
    m = _TITLE_COUNTY_STATE_RE.match(title)
    if m:
        county = m.group(1).strip()
        state = m.group(2)
    else:
        # Try independent city pattern: "City Name Tax ..."
        m = _TITLE_CITY_RE.match(title)
        if m:
            county = m.group(1).strip()
            state = None
        else:
            return None

    # Determine sale type from keywords in the title
    title_lower = title.lower()
    sale_type = SaleType.DEED  # default
    matched = False
    for keyword, st in _SALE_TYPE_MAP.items():
        if keyword in title_lower:
            sale_type = st
            matched = True
            break
    if not matched:
        logger.warning("bid4assets_unknown_sale_type", title=title)

    return county, state, sale_type
