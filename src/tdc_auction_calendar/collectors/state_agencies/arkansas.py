"""Arkansas state agency collector — COSL tax deed sales."""

from __future__ import annotations

import re
from datetime import date, datetime

import structlog
from pydantic import ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping import create_scrape_client
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType

logger = structlog.get_logger()

_URL = "https://www.cosl.org/Home/Contents"

_DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
_COUNTY_RE = re.compile(r"\[\s*([A-Z ]+?)\s*\]\(#\)")


def parse_catalog(markdown: str) -> list[dict]:
    """Extract (sale_date, county) pairs from COSL catalog markdown.

    Walks lines sequentially. A date line sets current_date; each subsequent
    county link line emits a record pairing that date with the county (title-cased).
    Counties appearing before any date line are skipped.
    """
    records: list[dict] = []
    current_date: str | None = None

    for line in markdown.splitlines():
        date_match = _DATE_RE.search(line)
        if date_match:
            parsed = datetime.strptime(date_match.group(1), "%m/%d/%Y")
            current_date = parsed.strftime("%Y-%m-%d")
            continue

        if current_date is None:
            continue

        county_match = _COUNTY_RE.search(line)
        if county_match:
            county = county_match.group(1).strip().title()
            records.append({"sale_date": current_date, "county": county})

    return records


class ArkansasCollector(BaseCollector):
    """Collects Arkansas tax deed sale dates from COSL."""

    @property
    def name(self) -> str:
        return "arkansas_state_agency"

    @property
    def source_type(self) -> SourceType:
        return SourceType.STATE_AGENCY

    async def _fetch(self) -> list[Auction]:
        client = create_scrape_client()
        try:
            result = await client.scrape(_URL)
        finally:
            await client.close()

        markdown = result.fetch.markdown or ""
        raw_records = parse_catalog(markdown)

        if markdown and not raw_records:
            logger.warning(
                "no_records_parsed",
                collector=self.name,
                url=_URL,
                markdown_length=len(markdown),
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
            sale_type=SaleType(raw.get("sale_type", "deed")),
            source_type=SourceType.STATE_AGENCY,
            source_url=_URL,
            confidence_score=0.85,
        )
