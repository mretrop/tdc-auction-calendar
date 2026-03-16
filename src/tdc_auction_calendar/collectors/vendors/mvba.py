"""MVBA Law vendor collector — Texas tax sales from mvbalaw.com."""

from __future__ import annotations

import re
from datetime import date, datetime

import structlog
from pydantic import ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping import create_scrape_client
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor

_SOURCE_URL = "https://mvbalaw.com/tax-sales/month-sales/"

logger = structlog.get_logger()

_MONTHS = (
    "January|February|March|April|May|June|"
    "July|August|September|October|November|December"
)

# Matches heading: "## April Tax Sales (Tuesday, April 7, 2026)"
_HEADING_RE = re.compile(
    rf"^##\s+\w+\s+Tax\s+Sales\s+\(\w+,\s+({_MONTHS})\s+(\d{{1,2}}),\s+(\d{{4}})\)",
    re.MULTILINE | re.IGNORECASE,
)

# Matches county links: "* [Eastland County](url)" or "* [Harrison County (MVBA Online Auction)](url)"
_COUNTY_RE = re.compile(
    r"^\*\s+\[([A-Za-z\s]+?)\s+County(?:\s*\([^)]*\))?\]",
    re.MULTILINE,
)


def parse_monthly_sales(markdown: str) -> list[tuple[date, str]]:
    """Parse MVBA monthly sales markdown into (sale_date, county_name) tuples."""
    results: list[tuple[date, str]] = []

    # Find all heading positions
    headings = list(_HEADING_RE.finditer(markdown))
    if not headings:
        return []

    for i, heading in enumerate(headings):
        month_str, day_str, year_str = heading.group(1), heading.group(2), heading.group(3)
        try:
            sale_date = datetime.strptime(f"{month_str} {day_str} {year_str}", "%B %d %Y").date()
        except ValueError:
            logger.error(
                "mvba_invalid_heading_date",
                raw_date=f"{month_str} {day_str} {year_str}",
            )
            continue

        # Extract counties between this heading and the next (or end of string)
        start = heading.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(markdown)
        section = markdown[start:end]

        for county_match in _COUNTY_RE.finditer(section):
            county_name = county_match.group(1).strip()
            results.append((sale_date, county_name))

    return results


class MVBACollector(BaseCollector):
    """Collects Texas tax sale dates from mvbalaw.com."""

    @property
    def name(self) -> str:
        return "mvba_vendor"

    @property
    def source_type(self) -> SourceType:
        return SourceType.VENDOR

    async def _fetch(self) -> list[Auction]:
        client = create_scrape_client()
        try:
            result = await client.scrape(_SOURCE_URL)
        finally:
            await client.close()

        markdown = result.fetch.markdown or ""
        entries = parse_monthly_sales(markdown)

        if markdown and not entries:
            logger.warning(
                "no_records_parsed",
                collector=self.name,
                url=_SOURCE_URL,
                markdown_length=len(markdown),
            )

        auctions: list[Auction] = []
        for sale_date, county in entries:
            raw = {"county": county, "date": sale_date.isoformat()}
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
        return Auction(
            state="TX",
            county=raw["county"],
            start_date=date.fromisoformat(raw["date"]),
            sale_type=SaleType.DEED,
            source_type=SourceType.VENDOR,
            source_url=_SOURCE_URL,
            confidence_score=0.90,
            vendor=Vendor.MVBA,
        )
