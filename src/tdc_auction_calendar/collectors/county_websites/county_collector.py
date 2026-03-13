"""County website collector — scrapes individual county tax sale pages."""

from __future__ import annotations

import json

import structlog
from pydantic import BaseModel

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.db.seed_loader import SEED_DIR
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SourceType

logger = structlog.get_logger()


class CountyAuctionRecord(BaseModel):
    """Schema for extraction from a single county's tax sale page."""

    sale_date: str
    sale_type: str = ""
    end_date: str | None = None
    deposit_amount: str | None = None
    registration_deadline: str | None = None


class CountyWebsiteCollector(BaseCollector):
    """Scrapes individual county tax sale pages for auction dates."""

    confidence_score: float = 0.70

    def __init__(self) -> None:
        self._county_targets = self._load_county_targets()

    @property
    def name(self) -> str:
        return "county_website"

    @property
    def source_type(self) -> SourceType:
        return SourceType.COUNTY_WEBSITE

    @staticmethod
    def _load_county_targets() -> list[dict]:
        """Load counties with tax_sale_page_url from seed data, joined with state sale_type."""
        with open(SEED_DIR / "counties.json") as f:
            counties = json.load(f)
        with open(SEED_DIR / "states.json") as f:
            states = {s["state"]: s for s in json.load(f)}

        targets = []
        for county in counties:
            url = county.get("tax_sale_page_url")
            if not url:
                continue
            state_code = county["state"]
            state_info = states.get(state_code, {})
            targets.append({
                "state_code": state_code,
                "county_name": county["county_name"],
                "tax_sale_page_url": url,
                "default_sale_type": state_info.get("sale_type", "deed"),
            })
        return targets

    def normalize(self, raw: dict) -> Auction:
        raise NotImplementedError("Use _normalize_record() with county_target context")

    def _normalize_record(self, raw: dict, county_target: dict) -> Auction:
        raise NotImplementedError("Implement after normalization tests")

    async def _fetch(self) -> list[Auction]:
        raise NotImplementedError("Implement after fetch tests")
