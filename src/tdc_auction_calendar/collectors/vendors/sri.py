# src/tdc_auction_calendar/collectors/vendors/sri.py
"""SRI Services vendor collector — tax sale auctions from sriservices.com API."""

from __future__ import annotations

import json
from datetime import date, datetime

import httpx
import structlog
from pydantic import ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping.client import ScrapeError
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor

logger = structlog.get_logger()

_API_URL = "https://sriservicesusermgmtprod.azurewebsites.net/api/auction/listall"
_API_KEY = "9f8fd9fe5160294175e1c737567030f495d838a7922a678bc06e0a093910"
_SOURCE_URL = "https://sriservices.com/properties"
_RECORD_COUNT = 500

# Sale type codes we collect, mapped to our SaleType enum
_SALE_TYPE_MAP: dict[str, SaleType] = {
    "A": SaleType.DEED,   # Tax Sale
    "C": SaleType.LIEN,   # Certificate Sale
    "D": SaleType.DEED,   # Deed Sale
    "J": SaleType.DEED,   # Adjudicated Sale
}


def parse_api_response(data: list[dict]) -> list[Auction]:
    """Parse the auction/listall API response into deduplicated Auction records.

    Filters to tax-sale types (A, C, D, J) and deduplicates by
    (state, county, date, sale_type).
    """
    seen: set[tuple[str, str, date, SaleType]] = set()
    auctions: list[Auction] = []
    skipped_type = 0
    skipped_no_date = 0
    skipped_bad_date = 0
    skipped_validation = 0

    for item in data:
        # Filter to relevant sale types
        code = item.get("saleTypeCode", "")
        sale_type = _SALE_TYPE_MAP.get(code)
        if sale_type is None:
            skipped_type += 1
            continue

        # Parse auction date
        raw_date = item.get("auctionDate")
        if not raw_date:
            skipped_no_date += 1
            continue

        try:
            auction_date = datetime.fromisoformat(raw_date).date()
        except (ValueError, TypeError):
            skipped_bad_date += 1
            logger.warning(
                "sri_date_parse_failed",
                county=item.get("county"),
                date=raw_date,
            )
            continue

        state = item.get("state", "")
        county = item.get("county", "")

        # Dedup by (state, county, date, sale_type)
        key = (state, county, auction_date, sale_type)
        if key in seen:
            continue
        seen.add(key)

        try:
            auctions.append(
                Auction(
                    state=state,
                    county=county,
                    start_date=auction_date,
                    sale_type=sale_type,
                    source_type=SourceType.VENDOR,
                    source_url=_SOURCE_URL,
                    confidence_score=1.0,
                    vendor=Vendor.SRI,
                )
            )
        except ValidationError as exc:
            skipped_validation += 1
            logger.warning(
                "sri_validation_failed",
                county=county,
                state=state,
                error=str(exc),
            )

    return auctions


class SRICollector(BaseCollector):
    """Collects tax sale auction dates from the SRI Services API."""

    @property
    def name(self) -> str:
        return "sri"

    @property
    def source_type(self) -> SourceType:
        return SourceType.VENDOR

    def normalize(self, raw: dict) -> Auction:
        return Auction(
            state=raw["state"],
            county=raw["county"],
            start_date=raw["start_date"],
            sale_type=raw["sale_type"],
            source_type=SourceType.VENDOR,
            source_url=_SOURCE_URL,
            confidence_score=1.0,
            vendor=Vendor.SRI,
        )

    async def _fetch(self) -> list[Auction]:
        today = date.today().isoformat()
        body = {
            "searchText": "",
            "state": "",
            "county": "",
            "propertySaleType": "",
            "auctionStyle": "",
            "saleStatus": "",
            "auctionDateRange": {
                "startDate": today,
                "endDate": "",
                "compareOperator": ">",
            },
            "recordCount": _RECORD_COUNT,
            "startIndex": 0,
        }
        headers = {
            "x-api-key": _API_KEY,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=30.0
            ) as client:
                resp = await client.post(_API_URL, json=body, headers=headers)
                resp.raise_for_status()

                try:
                    data = resp.json()
                except json.JSONDecodeError as exc:
                    raise ScrapeError(
                        url=_API_URL,
                        attempts=[{
                            "fetcher": "httpx",
                            "error": f"Non-JSON response: {resp.text[:200]}",
                        }],
                    ) from exc

                if not isinstance(data, list):
                    raise ScrapeError(
                        url=_API_URL,
                        attempts=[{
                            "fetcher": "httpx",
                            "error": f"Expected list, got {type(data).__name__}: {str(data)[:200]}",
                        }],
                    )
        except httpx.HTTPError as exc:
            raise ScrapeError(
                url=_API_URL,
                attempts=[{"fetcher": "httpx", "error": str(exc)}],
            ) from exc

        auctions = parse_api_response(data)

        logger.info(
            "sri_fetch_complete",
            total_api_results=len(data),
            auctions=len(auctions),
        )
        return auctions
