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
            try:
                with session.begin_nested():
                    session.add(row)
                    session.flush()
            except IntegrityError as exc:
                skipped += 1
                logger.warning(
                    "upsert_insert_integrity_error",
                    state=auction.state,
                    county=auction.county,
                    start_date=str(auction.start_date),
                    sale_type=auction.sale_type.value,
                    error=str(exc.orig),
                )
                continue
            new += 1
        elif auction.confidence_score > existing.confidence_score:
            try:
                with session.begin_nested():
                    for field in _UPSERT_FIELDS:
                        setattr(existing, field, _field_value(auction, field))
                    session.flush()
            except IntegrityError as exc:
                skipped += 1
                logger.warning(
                    "upsert_update_integrity_error",
                    state=auction.state,
                    county=auction.county,
                    start_date=str(auction.start_date),
                    sale_type=auction.sale_type.value,
                    error=str(exc.orig),
                )
                continue
            updated += 1
        else:
            skipped += 1
    logger.info("upsert_complete", new=new, updated=updated, skipped=skipped)
    return UpsertResult(new=new, updated=updated, skipped=skipped)


def save_collector_health(
    session: Session,
    name: str,
    success: bool,
    records: int,
    error: str | None,
) -> None:
    """Upsert collector health after a run.

    Does NOT commit — caller is responsible for committing the session.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    row = session.get(CollectorHealthRow, name)

    if row is None:
        row = CollectorHealthRow(
            collector_name=name,
            last_run=now,
            last_success=now if success else None,
            records_collected=records if success else 0,
            error_message=None if success else error,
        )
        session.add(row)
    else:
        row.last_run = now
        if success:
            row.last_success = now
            row.records_collected = records
            row.error_message = None
        else:
            row.error_message = error

    session.flush()


def get_collector_health(session: Session) -> list[CollectorHealth]:
    """Return all collector health records as Pydantic models."""
    rows = session.query(CollectorHealthRow).all()
    return [CollectorHealth.model_validate(row) for row in rows]
