"""Collector orchestrator — runs collectors, deduplicates, reports."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.county_websites import CountyWebsiteCollector
from tdc_auction_calendar.collectors.public_notices import (
    FloridaCollector,
    MinnesotaCollector,
    NewJerseyCollector,
    NorthCarolinaCollector,
    PennsylvaniaCollector,
    SouthCarolinaCollector,
    UtahCollector,
)
from tdc_auction_calendar.collectors.state_agencies import (
    ArkansasCollector,
    CaliforniaCollector,
    ColoradoCollector,
    IowaCollector,
)
from tdc_auction_calendar.collectors.statutory import StatutoryCollector
from tdc_auction_calendar.models.auction import Auction, DeduplicationKey
from tdc_auction_calendar.models.health import CollectorError, RunReport

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = structlog.get_logger()

COLLECTORS: dict[str, type[BaseCollector]] = {
    "florida_public_notice": FloridaCollector,
    "minnesota_public_notice": MinnesotaCollector,
    "new_jersey_public_notice": NewJerseyCollector,
    "north_carolina_public_notice": NorthCarolinaCollector,
    "pennsylvania_public_notice": PennsylvaniaCollector,
    "south_carolina_public_notice": SouthCarolinaCollector,
    "utah_public_notice": UtahCollector,
    "arkansas_state_agency": ArkansasCollector,
    "california_state_agency": CaliforniaCollector,
    "colorado_state_agency": ColoradoCollector,
    "iowa_state_agency": IowaCollector,
    "county_website": CountyWebsiteCollector,
    "statutory": StatutoryCollector,
}


def cross_dedup(auctions: list[Auction]) -> list[Auction]:
    """Deduplicate across collectors. Keeps highest confidence_score per dedup key."""
    best: dict[DeduplicationKey, Auction] = {}
    for auction in auctions:
        key = auction.dedup_key
        existing = best.get(key)
        if existing is None or auction.confidence_score > existing.confidence_score:
            best[key] = auction

    before = len(auctions)
    after = len(best)
    logger.info("cross_dedup_complete", before=before, after=after)

    return list(best.values())


async def run_all() -> tuple[list[Auction], RunReport]:
    """Run all registered collectors, deduplicate, and return results with report.

    Placeholder — full implementation in Task 5.
    """
    raise NotImplementedError("run_all will be implemented in Task 5")
