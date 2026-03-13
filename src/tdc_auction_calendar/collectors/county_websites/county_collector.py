"""County website collector — scrapes individual county tax sale pages."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation

import structlog
from pydantic import BaseModel, ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping import create_scrape_client
from tdc_auction_calendar.db.seed_loader import SEED_DIR
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType

logger = structlog.get_logger()


class CountyAuctionRecord(BaseModel):
    """Raw extraction schema from a county tax sale page.

    All fields are strings because parsing/validation happens during
    normalization in _normalize_record().
    """

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
        """Load counties that have a tax_sale_page_url, enriched with the state's default sale_type."""
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
            state_info = states.get(state_code)
            if state_info is None:
                logger.warning(
                    "county_state_not_found",
                    state=state_code,
                    county=county["county_name"],
                )
                continue
            targets.append({
                "state_code": state_code,
                "county_name": county["county_name"],
                "tax_sale_page_url": url,
                "default_sale_type": state_info.get("sale_type", "deed"),
            })
        return targets

    def normalize(self, raw: dict) -> Auction:
        raise NotImplementedError(
            "CountyWebsiteCollector requires per-county context; "
            "normalization is handled internally by _fetch()"
        )

    def _normalize_record(self, raw: dict, county_target: dict) -> Auction:
        """Convert a raw extraction record into a validated Auction."""
        return Auction(
            state=county_target["state_code"],
            county=county_target["county_name"],
            start_date=date.fromisoformat(raw["sale_date"]),
            sale_type=SaleType(raw.get("sale_type") or county_target["default_sale_type"]),
            source_type=SourceType.COUNTY_WEBSITE,
            source_url=county_target["tax_sale_page_url"],
            confidence_score=self.confidence_score,
            end_date=date.fromisoformat(raw["end_date"]) if raw.get("end_date") else None,
            deposit_amount=Decimal(raw["deposit_amount"]) if raw.get("deposit_amount") else None,
            registration_deadline=(
                date.fromisoformat(raw["registration_deadline"])
                if raw.get("registration_deadline") else None
            ),
        )

    async def _fetch(self) -> list[Auction]:
        if not self._county_targets:
            return []

        client = create_scrape_client()
        try:
            all_auctions: list[Auction] = []
            today = date.today()
            scrape_failed = 0
            for target in self._county_targets:
                url = target["tax_sale_page_url"]
                try:
                    result = await client.scrape(
                        url, schema=CountyAuctionRecord,
                    )
                except Exception as exc:
                    scrape_failed += 1
                    logger.error(
                        "county_scrape_failed",
                        collector=self.name,
                        state=target["state_code"],
                        county=target["county_name"],
                        url=url,
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )
                    continue

                if isinstance(result.data, list):
                    raw_records = result.data
                elif result.data is None:
                    logger.warning(
                        "county_extraction_returned_none",
                        collector=self.name,
                        state=target["state_code"],
                        county=target["county_name"],
                        url=url,
                    )
                    raw_records = []
                elif isinstance(result.data, dict):
                    raw_records = [result.data]
                else:
                    logger.warning(
                        "unexpected_data_type",
                        collector=self.name,
                        county=target["county_name"],
                        data_type=type(result.data).__name__,
                    )
                    continue

                if not raw_records:
                    continue

                for raw in raw_records:
                    try:
                        auction = self._normalize_record(raw, target)
                        if auction.start_date < today:
                            continue
                        all_auctions.append(auction)
                    except (KeyError, ValueError, ValidationError, InvalidOperation) as exc:
                        logger.error(
                            "normalize_failed",
                            collector=self.name,
                            state=target["state_code"],
                            county=target["county_name"],
                            raw=raw,
                            error=str(exc),
                            error_type=type(exc).__name__,
                        )

            succeeded = len(self._county_targets) - scrape_failed
            if scrape_failed:
                logger.error(
                    "county_collection_summary",
                    collector=self.name,
                    total_targets=len(self._county_targets),
                    succeeded=succeeded,
                    failed=scrape_failed,
                    auctions_found=len(all_auctions),
                )

            return all_auctions
        finally:
            await client.close()
