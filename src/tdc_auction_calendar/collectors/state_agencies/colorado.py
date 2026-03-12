"""Colorado state agency collector — CCTPTA tax lien sales."""

from __future__ import annotations

from datetime import date

import structlog
from pydantic import BaseModel

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping import create_scrape_client
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType

logger = structlog.get_logger()

_URL = "https://cctpta.org/tax-lien-sales"
_PROMPT = (
    "Extract all county tax lien sale dates from this page. "
    "Each row should have county name, sale date, and sale type."
)


class ColoradoAuctionRecord(BaseModel):
    """Schema for a single Colorado auction record from CCTPTA."""

    county: str
    sale_date: str
    sale_type: str = "lien"


class ColoradoCollector(BaseCollector):
    """Collects Colorado tax lien sale dates from CCTPTA."""

    @property
    def name(self) -> str:
        return "colorado_state_agency"

    @property
    def source_type(self) -> SourceType:
        return SourceType.STATE_AGENCY

    async def _fetch(self) -> list[Auction]:
        json_options = {
            "prompt": _PROMPT,
            "response_format": ColoradoAuctionRecord.model_json_schema(),
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
        for raw in raw_records:
            try:
                auctions.append(self.normalize(raw))
            except Exception as exc:
                logger.warning(
                    "normalize_failed",
                    collector=self.name,
                    raw=raw,
                    error=str(exc),
                )
        return auctions

    def normalize(self, raw: dict) -> Auction:
        """Convert a raw CCTPTA record into a validated Auction."""
        return Auction(
            state="CO",
            county=raw["county"],
            start_date=date.fromisoformat(raw["sale_date"]),
            sale_type=SaleType(raw.get("sale_type", "lien")),
            source_type=SourceType.STATE_AGENCY,
            source_url=_URL,
            confidence_score=0.85,
        )
