"""Shared query/filter utilities for all exporters."""

from __future__ import annotations

import datetime

import structlog
from sqlalchemy.orm import Session

from tdc_auction_calendar.models.auction import Auction, AuctionRow
from tdc_auction_calendar.models.enums import AuctionStatus, SaleType

logger = structlog.get_logger()


def query_auctions(
    session: Session,
    states: list[str] | None = None,
    sale_type: SaleType | None = None,
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
    upcoming_only: bool = False,
) -> list[Auction]:
    """Query auctions from the DB with optional filters, return Pydantic models."""
    logger.debug(
        "querying auctions",
        states=states,
        sale_type=str(sale_type) if sale_type else None,
        from_date=str(from_date) if from_date else None,
        to_date=str(to_date) if to_date else None,
        upcoming_only=upcoming_only,
    )
    query = session.query(AuctionRow)

    if states:
        query = query.filter(AuctionRow.state.in_([s.upper() for s in states]))
    if sale_type:
        query = query.filter(AuctionRow.sale_type == str(sale_type))
    if from_date:
        query = query.filter(AuctionRow.start_date >= from_date)
    else:
        query = query.filter(AuctionRow.start_date >= datetime.date.today())
    if to_date:
        query = query.filter(AuctionRow.start_date <= to_date)
    if upcoming_only:
        query = query.filter(AuctionRow.status == str(AuctionStatus.UPCOMING))

    rows = query.order_by(AuctionRow.start_date).all()
    auctions = [Auction.model_validate(r, from_attributes=True) for r in rows]
    logger.info("queried auctions", count=len(auctions))
    return auctions
