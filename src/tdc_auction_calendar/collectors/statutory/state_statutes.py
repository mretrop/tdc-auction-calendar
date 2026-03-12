"""Tier 4 statutory baseline collector — generates auctions from seed data."""

from __future__ import annotations

import calendar
import json
from datetime import date

import structlog
from pydantic import ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.db.seed_loader import SEED_DIR
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SourceType

logger = structlog.get_logger()

DEFAULT_SKIP_STATES: set[str] = set()
DEFAULT_SKIP_COUNTIES: set[tuple[str, str]] = set()


def _load_seed_files() -> tuple[list[dict], list[dict], list[dict]]:
    """Load and parse the three seed JSON files. Returns (states, counties, vendors)."""
    try:
        states = json.loads((SEED_DIR / "states.json").read_text())
        counties = json.loads((SEED_DIR / "counties.json").read_text())
        vendors = json.loads((SEED_DIR / "vendor_mapping.json").read_text())
    except FileNotFoundError as exc:
        logger.error("statutory_seed_file_missing", seed_dir=str(SEED_DIR), error=str(exc))
        raise
    except json.JSONDecodeError as exc:
        logger.error("statutory_seed_file_corrupt", seed_dir=str(SEED_DIR), error=str(exc))
        raise
    return states, counties, vendors


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
        states, counties, vendors = _load_seed_files()

        vendor_index: dict[tuple[str, str], dict] = {}
        for v in vendors:
            v_state = v.get("state")
            v_county = v.get("county")
            if not v_state or not v_county:
                logger.warning("statutory_skip_vendor_missing_key", vendor_record=v)
                continue
            vendor_index[(v_state, v_county)] = v

        today = date.today()
        years = [today.year, today.year + 1]

        state_rules: dict[str, dict] = {}
        for s in states:
            s_state = s.get("state")
            if not s_state:
                logger.warning("statutory_skip_state_missing_code", state_record=s)
                continue
            state_rules[s_state] = s
        auctions: list[Auction] = []
        skipped = 0

        for state_code, rules in state_rules.items():
            if state_code in self._skip_states:
                continue
            typical_months = rules.get("typical_months")
            if not typical_months:
                logger.warning("statutory_skip_state_no_months", state=state_code)
                continue

            sale_type = rules.get("sale_type")
            if not sale_type:
                logger.warning("statutory_skip_state_no_sale_type", state=state_code)
                continue

            state_counties = [c for c in counties if c.get("state") == state_code]

            for county in state_counties:
                county_name = county.get("county_name")
                if not county_name:
                    logger.warning("statutory_skip_county_missing_name", state=state_code, county_record=county)
                    continue
                if (state_code, county_name) in self._skip_counties:
                    continue

                vendor_info = vendor_index.get((state_code, county_name))
                vendor_name = None
                portal_url = None
                if vendor_info:
                    vendor_name = vendor_info.get("vendor")
                    if not vendor_name:
                        logger.warning(
                            "statutory_vendor_missing_name",
                            state=state_code,
                            county=county_name,
                        )
                    else:
                        portal_url = vendor_info.get("portal_url")

                for month in typical_months:
                    for year in years:
                        raw: dict = {
                            "state": state_code,
                            "county": county_name,
                            "month": month,
                            "year": year,
                            "sale_type": sale_type,
                        }
                        if vendor_name:
                            raw["vendor"] = vendor_name
                            raw["portal_url"] = portal_url
                        try:
                            auctions.append(self.normalize(raw))
                        except (ValidationError, ValueError) as exc:
                            skipped += 1
                            logger.error(
                                "statutory_normalize_failed",
                                error_type=type(exc).__name__,
                                state=state_code,
                                county=county_name,
                                month=month,
                                year=year,
                                error=str(exc),
                            )

        log = logger.warning if skipped else logger.info
        log(
            "statutory_fetch_complete",
            collector=self.name,
            records=len(auctions),
            skipped=skipped,
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
