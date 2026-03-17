# src/tdc_auction_calendar/collectors/vendors/publicsurplus.py
"""PublicSurplus vendor collector — tax sale and lien auctions from publicsurplus.com."""

from __future__ import annotations

import asyncio
import re
from datetime import date, datetime, timezone

import httpx
import structlog
from bs4 import BeautifulSoup
from pydantic import ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor

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


_LISTING_URL = "https://www.publicsurplus.com/sms/browse/cataucs"
_MAX_PAGES = 20
_PAGE_DELAY = 0.5
_MAX_CONCURRENT_DETAIL = 3

_CATEGORY_SALE_TYPES: dict[int, SaleType] = {
    1506: SaleType.DEED,
    1505: SaleType.LIEN,
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class PublicSurplusCollector(BaseCollector):
    """Collects tax sale and lien auctions from PublicSurplus.com."""

    @property
    def name(self) -> str:
        return "publicsurplus"

    @property
    def source_type(self) -> SourceType:
        return SourceType.VENDOR

    def normalize(self, raw: dict) -> Auction:
        county = extract_county(raw["title"])
        return Auction(
            state=raw["state"],
            county=county,
            start_date=raw["start_date"],
            end_date=raw.get("end_date"),
            sale_type=raw["sale_type"],
            source_type=SourceType.VENDOR,
            source_url=raw.get("source_url"),
            confidence_score=0.80,
            vendor=Vendor.PUBLIC_SURPLUS,
            notes=raw["title"],
        )

    async def _fetch(self) -> list[Auction]:
        async with httpx.AsyncClient(
            follow_redirects=True, headers=_HEADERS, timeout=30.0
        ) as client:
            raw_listings = await self._fetch_all_listings(client)
            raw_listings = [r for r in raw_listings if r["state"] in US_STATES]

            semaphore = asyncio.Semaphore(_MAX_CONCURRENT_DETAIL)
            tasks = [
                self._fetch_detail(client, semaphore, listing)
                for listing in raw_listings
            ]
            enriched = await asyncio.gather(*tasks, return_exceptions=True)

        auctions: list[Auction] = []
        for entry in enriched:
            if isinstance(entry, Exception):
                logger.error(
                    "publicsurplus_detail_unexpected_error",
                    error=repr(entry),
                    error_type=type(entry).__name__,
                )
                continue
            if entry is None or entry.get("start_date") is None:
                continue
            try:
                auctions.append(self.normalize(entry))
            except (ValidationError, KeyError, TypeError, ValueError) as exc:
                logger.error(
                    "normalize_failed",
                    collector=self.name,
                    entry=entry,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

        logger.info(
            "publicsurplus_fetch_complete",
            discovered=len(raw_listings),
            auctions=len(auctions),
        )
        return auctions

    async def _fetch_all_listings(self, client: httpx.AsyncClient) -> list[dict]:
        all_listings: list[dict] = []

        for catid, sale_type in _CATEGORY_SALE_TYPES.items():
            page = 0
            while page < _MAX_PAGES:
                try:
                    resp = await client.get(
                        _LISTING_URL, params={"catid": catid, "page": page}
                    )
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.warning(
                        "publicsurplus_listing_page_failed",
                        catid=catid, page=page, error=str(exc),
                    )
                    break

                items = parse_listing_html(resp.text)
                if not items:
                    break

                for item in items:
                    item["sale_type"] = sale_type
                all_listings.extend(items)

                page += 1
                if page < _MAX_PAGES:
                    await asyncio.sleep(_PAGE_DELAY)

        return all_listings

    async def _fetch_detail(
        self, client: httpx.AsyncClient, semaphore: asyncio.Semaphore, listing: dict,
    ) -> dict | None:
        async with semaphore:
            try:
                resp = await client.get(listing["source_url"])
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning(
                    "publicsurplus_detail_failed",
                    auction_id=listing["auction_id"], error=str(exc),
                )
                if listing.get("end_date"):
                    logger.warning(
                        "publicsurplus_detail_fallback_to_end_date",
                        auction_id=listing["auction_id"],
                        reason="detail_fetch_failed",
                        end_date=str(listing["end_date"]),
                    )
                    listing["start_date"] = listing["end_date"]
                    return listing
                return None

            detail = parse_detail_html(resp.text)
            if detail and detail.get("start_date"):
                listing["start_date"] = detail["start_date"]
                if detail.get("end_date"):
                    listing["end_date"] = detail["end_date"]
            elif listing.get("end_date"):
                logger.warning(
                    "publicsurplus_detail_fallback_to_end_date",
                    auction_id=listing["auction_id"],
                    reason="start_date_not_in_detail_html",
                    end_date=str(listing["end_date"]),
                )
                listing["start_date"] = listing["end_date"]
            else:
                return None

            return listing
