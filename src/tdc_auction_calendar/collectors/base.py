"""Abstract base collector interface for all auction data collectors."""

from __future__ import annotations

from abc import ABC, abstractmethod

import structlog

from tdc_auction_calendar.models.auction import Auction

logger = structlog.get_logger()


class BaseCollector(ABC):
    """Base class for auction data collectors.

    Subclasses must implement ``collect`` and ``normalize``.
    The ``deduplicate`` method is provided as a concrete utility.
    """

    @abstractmethod
    async def collect(self) -> list[Auction]:
        """Collect auction records from a data source."""
        ...

    @abstractmethod
    def normalize(self, raw: dict) -> Auction:
        """Convert a raw data dict into a validated Auction."""
        ...

    def deduplicate(self, auctions: list[Auction]) -> list[Auction]:
        """Remove duplicate auctions, keeping the highest confidence_score.

        Dedup key: (state, county, start_date, sale_type).
        On equal confidence, the first encountered auction wins.
        """
        best: dict[tuple, Auction] = {}
        for auction in auctions:
            key = auction.dedup_key
            existing = best.get(key)
            if existing is None or auction.confidence_score > existing.confidence_score:
                best[key] = auction

        dropped = len(auctions) - len(best)
        if dropped:
            logger.info("deduplicated_auctions", kept=len(best), dropped=dropped)

        return list(best.values())
