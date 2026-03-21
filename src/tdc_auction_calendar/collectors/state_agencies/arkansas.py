"""Arkansas state agency collector — COSL tax deed sales.

Uses plain httpx + BeautifulSoup to parse the Public Auction Catalog at
cosl.org/Home/Contents. The page is server-rendered HTML (ASP.NET MVC) with
sale dates and counties in a Bootstrap grid layout.
"""

from __future__ import annotations

import re
from datetime import date, datetime

import httpx
import structlog
from bs4 import BeautifulSoup
from pydantic import ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType

logger = structlog.get_logger()

_URL = "https://cosl.org/Home/Contents"
_DATE_RE = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})")


def parse_catalog(html: str) -> list[dict]:
    """Extract (sale_date, county) pairs from COSL catalog HTML.

    Each data row is a ``div.row`` whose first ``div.col-sm`` child contains a
    date like ``7/9/2026 12:00 AM``.  Counties appear as ``a.dropdown-toggle``
    links within the same row.
    """
    soup = BeautifulSoup(html, "html.parser")
    records: list[dict] = []

    for row in soup.find_all("div", class_="row"):
        cols = row.find_all("div", class_="col-sm", recursive=False)
        if not cols:
            continue
        date_match = _DATE_RE.match(cols[0].get_text(strip=True))
        if not date_match:
            continue

        sale_date = datetime.strptime(date_match.group(1), "%m/%d/%Y").strftime(
            "%Y-%m-%d"
        )
        county_links = row.find_all("a", class_="dropdown-toggle")
        for link in county_links:
            county = link.get_text(strip=True).title()
            if county:
                records.append({"sale_date": sale_date, "county": county})

    return records


class ArkansasCollector(BaseCollector):
    """Collects Arkansas tax deed sale dates from COSL."""

    @property
    def name(self) -> str:
        return "arkansas_cosl"

    @property
    def source_type(self) -> SourceType:
        return SourceType.STATE_AGENCY

    async def _fetch(self) -> list[Auction]:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(_URL)
            resp.raise_for_status()

        raw_records = parse_catalog(resp.text)

        if not raw_records:
            logger.warning(
                "no_records_parsed",
                collector=self.name,
                url=_URL,
                html_length=len(resp.text),
            )

        auctions: list[Auction] = []
        for raw in raw_records:
            try:
                auctions.append(self.normalize(raw))
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                logger.error(
                    "normalize_failed",
                    collector=self.name,
                    raw=raw,
                    error=str(exc),
                )

        return auctions

    def normalize(self, raw: dict) -> Auction:
        """Convert a raw COSL record into a validated Auction."""
        return Auction(
            state="AR",
            county=raw["county"],
            start_date=date.fromisoformat(raw["sale_date"]),
            sale_type=SaleType("deed"),
            source_type=SourceType.STATE_AGENCY,
            source_url=_URL,
            confidence_score=0.85,
        )
