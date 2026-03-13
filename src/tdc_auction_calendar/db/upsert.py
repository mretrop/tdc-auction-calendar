"""Auction upsert and collector health persistence."""

from __future__ import annotations

import datetime

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tdc_auction_calendar.models.auction import Auction, AuctionRow
from tdc_auction_calendar.models.health import (
    CollectorHealth,
    CollectorHealthRow,
    UpsertResult,
)

logger = structlog.get_logger()

# Fields to copy from Auction to AuctionRow on insert/update.
# Excludes: id, created_at, updated_at (managed by DB/ORM).
_UPSERT_FIELDS = [
    "state",
    "county",
    "start_date",
    "end_date",
    "sale_type",
    "status",
    "source_type",
    "source_url",
    "registration_deadline",
    "deposit_deadline",
    "deposit_amount",
    "min_bid",
    "interest_rate",
    "confidence_score",
    "property_count",
    "vendor",
    "notes",
]


_ENUM_FIELDS = frozenset(("sale_type", "status", "source_type"))


def _field_value(auction: Auction, field: str):
    """Get field value, converting enums to their string value."""
    value = getattr(auction, field)
    if field in _ENUM_FIELDS and value is not None:
        return value.value if hasattr(value, "value") else value
    return value


def upsert_auctions(session: Session, auctions: list[Auction]) -> UpsertResult:
    """Upsert auctions by dedup key. Higher confidence wins.

    Does NOT commit — caller is responsible for committing the session.
    """
    new = 0
    updated = 0
    skipped = 0

    for auction in auctions:
        existing = (
            session.query(AuctionRow)
            .filter_by(
                state=auction.state,
                county=auction.county,
                start_date=auction.start_date,
                sale_type=auction.sale_type.value,
            )
            .first()
        )

        if existing is None:
            row = AuctionRow(
                **{field: _field_value(auction, field) for field in _UPSERT_FIELDS}
            )
            session.add(row)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                skipped += 1
                logger.warning(
                    "upsert_integrity_error",
                    state=auction.state,
                    county=auction.county,
                )
                continue
            new += 1
        elif auction.confidence_score > existing.confidence_score:
            for field in _UPSERT_FIELDS:
                setattr(existing, field, _field_value(auction, field))
            updated += 1
        else:
            skipped += 1

    session.flush()
    logger.info("upsert_complete", new=new, updated=updated, skipped=skipped)
    return UpsertResult(new=new, updated=updated, skipped=skipped)


def save_collector_health(
    session: Session, health: CollectorHealth
) -> CollectorHealthRow:
    """Save or update collector health record."""
    existing = (
        session.query(CollectorHealthRow)
        .filter_by(collector_name=health.collector_name)
        .first()
    )

    if existing is None:
        row = CollectorHealthRow(
            collector_name=health.collector_name,
            last_run=health.last_run,
            last_success=health.last_success,
            records_collected=health.records_collected,
            error_message=health.error_message,
        )
        session.add(row)
    else:
        existing.last_run = health.last_run
        existing.last_success = health.last_success
        existing.records_collected = health.records_collected
        existing.error_message = health.error_message
        row = existing

    session.flush()
    return row


def get_collector_health(
    session: Session, collector_name: str
) -> CollectorHealthRow | None:
    """Retrieve health record for a collector."""
    return (
        session.query(CollectorHealthRow)
        .filter_by(collector_name=collector_name)
        .first()
    )
