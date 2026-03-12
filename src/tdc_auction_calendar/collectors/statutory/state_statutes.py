"""Tier 4 statutory baseline collector — generates auctions from seed data."""

from __future__ import annotations

import calendar
import json
from datetime import date

import structlog

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.db.seed_loader import SEED_DIR
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SourceType

logger = structlog.get_logger()

DEFAULT_SKIP_STATES: set[str] = set()
DEFAULT_SKIP_COUNTIES: set[tuple[str, str]] = set()


class StatutoryCollector(BaseCollector):

    def __init__(
        self,
        skip_states: set[str] | None = None,
        skip_counties: set[tuple[str, str]] | None = None,
    ) -> None:
        self._skip_states = skip_states if skip_states is not None else DEFAULT_SKIP_STATES
        self._skip_counties = skip_counties if skip_counties is not None else DEFAULT_SKIP_COUNTIES

    @property
    def name(self) -> str:
        return "statutory"

    @property
    def source_type(self) -> SourceType:
        return SourceType.STATUTORY

    async def _fetch(self) -> list[Auction]:
        raise NotImplementedError

    def normalize(self, raw: dict) -> Auction:
        month = raw["month"]
        year = raw["year"]
        _, last_day = calendar.monthrange(year, month)
        return Auction(
            state=raw["state"],
            county=raw["county"],
            start_date=date(year, month, 1),
            end_date=date(year, month, last_day),
            sale_type=raw["sale_type"],
            source_type=SourceType.STATUTORY,
            confidence_score=0.4,
            vendor=raw.get("vendor"),
            source_url=raw.get("portal_url"),
        )
