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
        states = json.loads((SEED_DIR / "states.json").read_text())
        counties = json.loads((SEED_DIR / "counties.json").read_text())
        vendors = json.loads((SEED_DIR / "vendor_mapping.json").read_text())

        vendor_index: dict[tuple[str, str], dict] = {}
        for v in vendors:
            vendor_index[(v["state"], v["county"])] = v

        today = date.today()
        years = [today.year, today.year + 1]

        state_rules = {s["state"]: s for s in states}
        auctions: list[Auction] = []

        for state_code, rules in state_rules.items():
            if state_code in self._skip_states:
                continue
            typical_months = rules.get("typical_months")
            if not typical_months:
                continue

            state_counties = [c for c in counties if c["state"] == state_code]

            for county in state_counties:
                county_name = county["county_name"]
                if (state_code, county_name) in self._skip_counties:
                    continue

                vendor_info = vendor_index.get((state_code, county_name))

                for month in typical_months:
                    for year in years:
                        raw: dict = {
                            "state": state_code,
                            "county": county_name,
                            "month": month,
                            "year": year,
                            "sale_type": rules["sale_type"],
                        }
                        if vendor_info:
                            raw["vendor"] = vendor_info["vendor"]
                            raw["portal_url"] = vendor_info.get("portal_url")
                        auctions.append(self.normalize(raw))

        logger.info(
            "statutory_fetch_complete",
            collector=self.name,
            records=len(auctions),
        )
        return auctions

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
