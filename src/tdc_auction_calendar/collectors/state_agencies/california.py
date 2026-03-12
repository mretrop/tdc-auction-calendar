"""California state agency collector — SCO tax deed sales."""

from __future__ import annotations

from datetime import date

import structlog
from pydantic import BaseModel, ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector

from tdc_auction_calendar.collectors.scraping import ExtractionError, create_scrape_client
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType

logger = structlog.get_logger()

_URL = "https://sco.ca.gov/ardtax_public_auction.html"
_PROMPT = (
    "Extract all county tax deed public auction dates from this page. "
    "Each row should have county name, sale date, and auction type."
)


class CaliforniaAuctionRecord(BaseModel):
    """Schema for a single California auction record from SCO."""

    county: str
    sale_date: str
    auction_type: str = "deed"


class CaliforniaCollector(BaseCollector):
    """Collects California tax deed sale dates from SCO."""

    @property
    def name(self) -> str:
        return "california_state_agency"

    @property
    def source_type(self) -> SourceType:
        return SourceType.STATE_AGENCY

    async def _fetch(self) -> list[Auction]:
        json_options = {
            "prompt": _PROMPT,
            "response_format": CaliforniaAuctionRecord.model_json_schema(),
        }
        client = create_scrape_client()
        try:
            result = await client.scrape(_URL, json_options=json_options)
        finally:
            await client.close()

        raw_records: list = (
            result.data
            if isinstance(result.data, list)
            else ([result.data] if result.data is not None else [])
        )

        auctions: list[Auction] = []
        failure_count = 0
        for raw in raw_records:
            try:
                auctions.append(self.normalize(raw))
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                failure_count += 1
                logger.error(
                    "normalize_failed",
                    collector=self.name,
                    raw=raw,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
        if failure_count:
            logger.error(
                "normalize_summary",
                collector=self.name,
                total=len(raw_records),
                succeeded=len(auctions),
                failed=failure_count,
            )
        if raw_records and not auctions:
            raise ExtractionError(
                f"{self.name}: all {len(raw_records)} records failed normalization"
            )
        return auctions

    def normalize(self, raw: dict) -> Auction:
        """Convert a raw SCO record into a validated Auction."""
        return Auction(
            state="CA",
            county=raw["county"],
            start_date=date.fromisoformat(raw["sale_date"]),
            sale_type=SaleType(raw.get("auction_type", "deed")),
            source_type=SourceType.STATE_AGENCY,
            source_url=_URL,
            confidence_score=0.85,
        )
