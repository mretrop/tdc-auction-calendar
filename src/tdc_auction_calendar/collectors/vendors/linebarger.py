# src/tdc_auction_calendar/collectors/vendors/linebarger.py
"""Linebarger vendor collector — tax sale auctions from taxsales.lgbs.com API."""

from __future__ import annotations

import re
from datetime import date

import structlog
from pydantic import ValidationError

from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor

logger = structlog.get_logger()

_BASE_URL = "https://taxsales.lgbs.com"
_API_URL = f"{_BASE_URL}/api/filter_bar/"


def normalize_county_name(raw: str) -> str:
    """Strip ' COUNTY' suffix and title-case the name.

    Examples:
        "HARRIS COUNTY" -> "Harris"
        "FORT BEND COUNTY" -> "Fort Bend"
        "JIM HOGG COUNTY" -> "Jim Hogg"
    """
    cleaned = re.sub(r"\s+county$", "", raw.strip(), flags=re.IGNORECASE)
    return cleaned.title()


def parse_api_response(data: dict) -> list[Auction]:
    """Parse the filter_bar API response into deduplicated Auction records.

    Groups by (state, county, sale_date) so multiple precincts on the same
    date in the same county produce one Auction.
    """
    seen: set[tuple[str, str, date]] = set()
    auctions: list[Auction] = []

    for item in data.get("results", []):
        # Skip cancelled
        status = item.get("status", "")
        if "cancelled" in status.lower():
            continue

        # Skip empty/null dates
        raw_date = item.get("sale_date_only")
        if not raw_date:
            continue

        state = item.get("state", "")
        raw_county = item.get("county", "")
        county = normalize_county_name(raw_county)

        try:
            sale_date = date.fromisoformat(raw_date)
        except (ValueError, TypeError):
            logger.warning(
                "linebarger_date_parse_failed",
                county=raw_county,
                date=raw_date,
            )
            continue

        # Dedup by (state, county, date) — collapses precincts
        key = (state, county, sale_date)
        if key in seen:
            continue
        seen.add(key)

        # Both TX and PA are deed states per seed data
        sale_type = SaleType.DEED

        try:
            auctions.append(
                Auction(
                    state=state,
                    county=county,
                    start_date=sale_date,
                    sale_type=sale_type,
                    source_type=SourceType.VENDOR,
                    source_url=f"{_BASE_URL}/map?area={state}",
                    confidence_score=1.0,
                    vendor=Vendor.LINEBARGER,
                )
            )
        except ValidationError as exc:
            logger.warning(
                "linebarger_validation_failed",
                county=raw_county,
                state=state,
                error=str(exc),
            )

    return auctions
