"""Abstract base collector interface for all auction data collectors."""

from __future__ import annotations

from abc import ABC, abstractmethod

import structlog

from tdc_auction_calendar.models.auction import Auction, DeduplicationKey
from tdc_auction_calendar.models.enums import SourceType

logger = structlog.get_logger()


class BaseCollector(ABC):
    """Base class for auction data collectors.

    Subclasses must implement ``name``, ``source_type``, ``_fetch``,
    and ``normalize``. The ``collect`` method calls ``_fetch`` and then
    deduplicates the results automatically.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable collector name."""
        ...

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """The source type for auctions produced by this collector."""
        ...

    async def collect(self) -> list[Auction]:
        """Collect and deduplicate auction records.

        Calls ``_fetch`` then applies deduplication automatically.
        """
        raw = await self._fetch()
        return self.deduplicate(raw)

    @abstractmethod
    async def _fetch(self) -> list[Auction]:
        """Fetch auction records from the data source (before dedup)."""
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
        best: dict[DeduplicationKey, Auction] = {}
        for auction in auctions:
            key = auction.dedup_key
            existing = best.get(key)
            if existing is None or auction.confidence_score > existing.confidence_score:
                best[key] = auction

        dropped = len(auctions) - len(best)
        if dropped:
            logger.info(
                "deduplicated_auctions",
                collector=self.name,
                kept=len(best),
                dropped=dropped,
            )

        return list(best.values())
