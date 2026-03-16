# src/tdc_auction_calendar/collectors/vendors/bid4assets.py
"""Bid4Assets vendor collector — tax sale auctions from bid4assets.com calendar."""

from __future__ import annotations

import re
from datetime import date

import httpx
import structlog
from bs4 import BeautifulSoup

from pydantic import ValidationError
from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor

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


def parse_calendar_html(html: str) -> list[dict]:
    """Parse the Bid4Assets auction calendar HTML into auction dicts.

    Returns list of dicts with keys: county, state, start_date, end_date,
    sale_type, source_url.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []

    for month_div in soup.select("div.month"):
        # Get year from data-year attribute
        year_str = month_div.get("data-year")
        if year_str is None:
            continue
        try:
            year = int(year_str)
        except ValueError:
            continue

        # Get month name from header
        header = month_div.select_one("div.title h3")
        if header is None:
            continue
        month_name = header.get_text().strip()

        # Process each auction entry
        for li in month_div.select("ul.auction-list li"):
            # Get title from <a> or <strong>
            link_el = li.select_one("a[href]")
            strong_el = li.select_one("strong")

            if link_el is not None:
                title_text = link_el.get_text().strip()
            elif strong_el is not None:
                title_text = strong_el.get_text().strip()
            else:
                # No title element — likely "to be announced" text
                continue

            # Parse title
            parsed = parse_title(title_text)
            if parsed is None:
                logger.warning("bid4assets_unparseable_title", title=title_text)
                continue
            county, state, sale_type = parsed

            # Get date range from <span>
            span_el = li.select_one("span")
            if span_el is None:
                continue
            date_text = span_el.get_text().strip()

            # Parse date range
            date_result = parse_date_range(month_name, date_text, year)
            if date_result is None:
                logger.info(
                    "bid4assets_skipped_entry",
                    title=title_text,
                    date_text=date_text,
                )
                continue
            start_date, end_date = date_result

            # Get storefront link if present
            source_url = None
            if link_el is not None and link_el.get("href"):
                href = link_el["href"]
                if not href.startswith("http"):
                    href = f"https://www.bid4assets.com{href}"
                source_url = href

            results.append({
                "county": county,
                "state": state,
                "start_date": start_date,
                "end_date": end_date,
                "sale_type": sale_type,
                "source_url": source_url,
            })

    return results


_CALENDAR_URL = "https://www.bid4assets.com/county-tax-sales"


class Bid4AssetsCollector(BaseCollector):
    """Collects tax sale auction dates from the Bid4Assets calendar page."""

    @property
    def name(self) -> str:
        return "bid4assets"

    @property
    def source_type(self) -> SourceType:
        return SourceType.VENDOR

    def normalize(self, raw: dict) -> Auction:
        return Auction(
            state=raw["state"],
            county=raw["county"],
            start_date=raw["start_date"],
            end_date=raw.get("end_date"),
            sale_type=raw["sale_type"],
            source_type=SourceType.VENDOR,
            source_url=raw.get("source_url") or _CALENDAR_URL,
            confidence_score=0.85,
            vendor=Vendor.BID4ASSETS,
        )

    async def _fetch(self) -> list[Auction]:
        # Plain httpx bypasses Akamai (which only blocks headless browsers).
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, headers=headers, timeout=30.0
            ) as client:
                resp = await client.get(_CALENDAR_URL)
                resp.raise_for_status()
                html = resp.text
        except httpx.HTTPError as exc:
            logger.error("bid4assets_fetch_failed", url=_CALENDAR_URL, error=str(exc))
            return []

        if not html or "auction-calendar" not in html:
            logger.warning("bid4assets_empty_or_blocked", url=_CALENDAR_URL, html_length=len(html or ""))
            return []

        entries = parse_calendar_html(html)

        auctions: list[Auction] = []
        for entry in entries:
            if entry.get("state") is None:
                logger.info(
                    "bid4assets_skipped_no_state",
                    county=entry.get("county"),
                )
                continue
            try:
                auctions.append(self.normalize(entry))
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                logger.error(
                    "bid4assets_normalize_failed",
                    entry=entry,
                    error=str(exc),
                )

        logger.info(
            "bid4assets_fetch_complete",
            total_entries=len(entries),
            auctions=len(auctions),
            skipped=len(entries) - len(auctions),
        )
        return auctions
