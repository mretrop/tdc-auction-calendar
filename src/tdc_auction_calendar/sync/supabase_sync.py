"""Sync auction data to Supabase."""

from __future__ import annotations

import datetime
from typing import NamedTuple

import structlog
from sqlalchemy.orm import Session
from supabase import create_client

from tdc_auction_calendar.exporters.filters import query_auctions
from tdc_auction_calendar.models.enums import SaleType

logger = structlog.get_logger()

BATCH_SIZE = 100


class SyncResult(NamedTuple):
    synced: int
    failed: int


def sync_to_supabase(
    session: Session,
    supabase_url: str,
    service_role_key: str,
    *,
    states: list[str] | None = None,
    sale_type: SaleType | None = None,
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
    upcoming_only: bool = False,
) -> SyncResult:
    """Query local auctions and upsert them to Supabase."""
    auctions = query_auctions(
        session,
        states=states,
        sale_type=sale_type,
        from_date=from_date,
        to_date=to_date,
        upcoming_only=upcoming_only,
    )

    if not auctions:
        logger.info("no auctions to sync")
        return SyncResult(synced=0, failed=0)

    client = create_client(supabase_url, service_role_key)
    table = client.table("auctions")

    rows = []
    for auction in auctions:
        row = auction.model_dump(mode="json")
        row.pop("id", None)
        rows.append(row)

    synced = 0
    failed = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        try:
            table.upsert(
                batch,
                on_conflict="state,county,start_date,sale_type",
            ).execute()
            synced += len(batch)
            logger.info("batch synced", batch_size=len(batch), total_synced=synced)
        except Exception as exc:
            failed += len(batch)
            logger.exception("batch upsert failed", batch_start=i, batch_size=len(batch))
            if synced == 0:
                raise RuntimeError(
                    f"First batch failed — aborting sync. Cause: {exc}"
                ) from exc

    return SyncResult(synced=synced, failed=failed)
