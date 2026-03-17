# src/tdc_auction_calendar/collectors/vendors/publicsurplus.py
"""PublicSurplus vendor collector — tax sale and lien auctions from publicsurplus.com."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger()

_BASE_URL = "https://www.publicsurplus.com"

# Extracts auction ID and end epoch ms from updateTimeLeftSpan JS call
_TIME_LEFT_RE = re.compile(
    r"updateTimeLeftSpan\([^,]+,\s*(\d+)\s*,\s*\"[^\"]+\"\s*,\s*\d+\s*,\s*(\d+)"
)

US_STATES: frozenset[str] = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL",
    "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
})

_COUNTY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+County\b")


def extract_county(title: str) -> str:
    """Extract county name from an auction title, or 'Various' if not found."""
    m = _COUNTY_RE.search(title)
    return m.group(1) if m else "Various"


def parse_listing_html(html: str) -> list[dict]:
    """Parse a PublicSurplus category listing page into auction dicts.

    Returns list of dicts with keys: auction_id, state, title, source_url, end_date.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []

    # Build a map of auction_id -> end_date from JS calls
    end_dates: dict[str, date] = {}
    for script in soup.find_all("script"):
        text = script.string or ""
        for m in _TIME_LEFT_RE.finditer(text):
            auc_id = m.group(1)
            end_epoch_ms = int(m.group(2))
            end_dt = datetime.fromtimestamp(end_epoch_ms / 1000, tz=timezone.utc)
            end_dates[auc_id] = end_dt.date()

    for item in soup.select("div.auction-item"):
        item_id = item.get("id", "")
        auction_id = item_id.replace("catGrid", "") if item_id.endswith("catGrid") else None
        if not auction_id:
            continue

        # State
        state_el = item.select_one("span.auction-item-state")
        if state_el is None:
            continue
        state = state_el.get_text().strip()

        # Title (full, from title attribute)
        title_link = item.select_one("h6.card-title a")
        if title_link is None:
            continue
        title = title_link.get("title", title_link.get_text()).strip()
        # Strip leading "#ID - " prefix
        if title.startswith("#"):
            dash_pos = title.find(" - ")
            if dash_pos != -1:
                title = title[dash_pos + 3:]

        source_url = f"{_BASE_URL}/sms/auction/view?auc={auction_id}"
        end_date = end_dates.get(auction_id)

        results.append({
            "auction_id": auction_id,
            "state": state,
            "title": title,
            "source_url": source_url,
            "end_date": end_date,
        })

    return results


# Matches date strings like "Mar 4, 2026 09:00 AM MST"
_DETAIL_DATE_RE = re.compile(
    r"([A-Z][a-z]{2}\s+\d{1,2},\s*\d{4})"
)


def parse_detail_html(html: str) -> dict | None:
    """Parse a PublicSurplus auction detail page for start/end dates.

    Returns dict with keys: start_date, end_date (both datetime.date), or None
    if dates not found.
    """
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    start_date: date | None = None
    end_date: date | None = None

    # Look for "Auction Started" / "Auction Ends" labels in div.auctitle elements
    for label_div in soup.select("div.auctitle"):
        label_text = label_div.get_text(strip=True)
        # The date is in the next sibling div
        next_div = label_div.find_next_sibling("div")
        if next_div is None:
            continue
        div_text = next_div.get_text(strip=True)
        m = _DETAIL_DATE_RE.search(div_text)
        if m is None:
            continue
        try:
            parsed = datetime.strptime(m.group(1), "%b %d, %Y").date()
        except ValueError:
            continue

        if "Started" in label_text or "Start" in label_text or "Opens" in label_text:
            start_date = parsed
        elif "Ends" in label_text or "End" in label_text or "Closes" in label_text:
            end_date = parsed

    if start_date is None and end_date is None:
        return None

    result: dict = {}
    if start_date is not None:
        result["start_date"] = start_date
    if end_date is not None:
        result["end_date"] = end_date

    return result if result else None
