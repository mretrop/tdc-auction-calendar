"""Collector orchestrator — runs collectors, deduplicates, reports."""

from __future__ import annotations

import time

import structlog
from sqlalchemy.orm import Session

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
from tdc_auction_calendar.db.upsert import save_collector_health, upsert_auctions
from tdc_auction_calendar.models.auction import Auction, DeduplicationKey
from tdc_auction_calendar.models.health import CollectorError, RunReport

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


async def run_all(
    collectors: list[str] | None = None,
) -> tuple[list[Auction], RunReport]:
    """Run collectors sequentially, deduplicate, and return results with report."""
    # 1. Resolve collector list
    if collectors is not None:
        unknown = set(collectors) - set(COLLECTORS)
        if unknown:
            raise ValueError(f"Unknown collector names: {sorted(unknown)}")
        to_run = {name: COLLECTORS[name] for name in collectors}
    else:
        to_run = COLLECTORS

    # 2. Execute sequentially
    start = time.monotonic()
    all_auctions: list[Auction] = []
    succeeded: list[str] = []
    failed: list[CollectorError] = []
    per_collector_counts: dict[str, int] = {}

    for name, cls in to_run.items():
        logger.info("collector_start", collector=name)
        try:
            collector = cls()
            results = await collector.collect()
            all_auctions.extend(results)
            succeeded.append(name)
            per_collector_counts[name] = len(results)
            logger.info("collector_complete", collector=name, records=len(results))
        except Exception as exc:
            failed.append(
                CollectorError(
                    collector_name=name,
                    error=repr(exc),
                    error_type=type(exc).__name__,
                )
            )
            logger.error(
                "collector_failed",
                collector=name,
                error=repr(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )

    # 3. Cross-collector dedup
    deduped = cross_dedup(all_auctions)

    # 4. Build report
    elapsed = time.monotonic() - start
    report = RunReport(
        total_records=len(deduped),
        collectors_succeeded=succeeded,
        collectors_failed=failed,
        per_collector_counts=per_collector_counts,
        duration_seconds=round(elapsed, 3),
    )

    return deduped, report


async def run_and_persist(
    session: Session,
    collectors: list[str] | None = None,
) -> RunReport:
    """Run all collectors and persist results to the database."""
    auctions, report = await run_all(collectors)

    try:
        # Upsert auctions
        upsert_result = upsert_auctions(session, auctions)
        report.new_records = upsert_result.new
        report.updated_records = upsert_result.updated
        report.skipped_records = upsert_result.skipped

        # Save health for each collector (using per-collector counts)
        for name in report.collectors_succeeded:
            save_collector_health(
                session,
                name=name,
                success=True,
                records=report.per_collector_counts.get(name, 0),
                error=None,
            )
        for err in report.collectors_failed:
            save_collector_health(
                session,
                name=err.collector_name,
                success=False,
                records=0,
                error=err.error,
            )

        # Single commit for all DB writes
        session.commit()
    except Exception:
        session.rollback()
        logger.error(
            "run_and_persist_failed",
            collectors_run=len(report.collectors_succeeded) + len(report.collectors_failed),
            auctions_collected=report.total_records,
            exc_info=True,
        )
        raise

    return report
