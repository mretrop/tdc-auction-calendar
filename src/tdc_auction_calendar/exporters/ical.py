"""iCalendar exporter — converts Auction models to RFC 5545 .ics bytes."""

from __future__ import annotations

import datetime

import structlog
from icalendar import Alarm, Calendar, Event
from sqlalchemy.orm import Session

from tdc_auction_calendar.models.auction import Auction, AuctionRow
from tdc_auction_calendar.models.enums import SaleType

logger = structlog.get_logger()


def _build_description(auction: Auction) -> str:
    """Build human-readable DESCRIPTION from non-null fields."""
    lines: list[str] = []
    if auction.registration_deadline is not None:
        lines.append(f"Registration deadline: {auction.registration_deadline}")
    if auction.deposit_amount is not None:
        lines.append(f"Deposit amount: ${auction.deposit_amount:,.2f}")
    if auction.deposit_deadline is not None:
        lines.append(f"Deposit deadline: {auction.deposit_deadline}")
    if auction.property_count is not None:
        lines.append(f"Properties: {auction.property_count}")
    if auction.source_url is not None:
        lines.append(f"Source: {auction.source_url}")
    return "\n".join(lines)


def _make_alarm(trigger_dt: datetime.datetime, description: str) -> Alarm:
    """Create a DISPLAY VALARM with an absolute trigger time."""
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", description)
    alarm.add("trigger", trigger_dt)
    return alarm


def _add_alarms(event: Event, auction: Auction) -> None:
    """Add VALARMs for registration and deposit deadlines."""
    if auction.registration_deadline is not None:
        reg_dt = datetime.datetime.combine(
            auction.registration_deadline, datetime.time.min, tzinfo=datetime.timezone.utc
        )
        event.add_component(_make_alarm(
            reg_dt - datetime.timedelta(days=7),
            f"Registration in 7 days: {auction.county} {auction.state}",
        ))
        event.add_component(_make_alarm(
            reg_dt - datetime.timedelta(days=1),
            f"Registration tomorrow: {auction.county} {auction.state}",
        ))
    if auction.deposit_deadline is not None:
        dep_dt = datetime.datetime.combine(
            auction.deposit_deadline, datetime.time.min, tzinfo=datetime.timezone.utc
        )
        event.add_component(_make_alarm(
            dep_dt - datetime.timedelta(days=1),
            f"Deposit due tomorrow: {auction.county} {auction.state}",
        ))


def _build_event(auction: Auction) -> Event:
    """Build a VEVENT from an Auction model."""
    event = Event()
    event.add("summary", f"{auction.county} {auction.state} Tax {auction.sale_type.title()} Sale")
    event.add("dtstart", auction.start_date)
    event.add("dtend", auction.end_date or auction.start_date + datetime.timedelta(days=1))
    event.add("uid", f"{auction.state}-{auction.county}-{auction.start_date}-{auction.sale_type}@tdc-auction-calendar")
    description = _build_description(auction)
    if description:
        event.add("description", description)
    if auction.source_url:
        event.add("url", auction.source_url)
    _add_alarms(event, auction)
    return event


def auctions_to_ical(auctions: list[Auction]) -> bytes:
    """Convert a list of Auction models to iCalendar bytes."""
    cal = Calendar()
    cal.add("prodid", "-//TDC Auction Calendar//EN")
    cal.add("version", "2.0")
    for auction in auctions:
        cal.add_component(_build_event(auction))
    return cal.to_ical()


def query_auctions(
    session: Session,
    states: list[str] | None = None,
    sale_type: SaleType | None = None,
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
) -> list[Auction]:
    """Query auctions from the DB with optional filters, return Pydantic models."""
    logger.debug(
        "querying auctions",
        states=states,
        sale_type=str(sale_type) if sale_type else None,
        from_date=str(from_date) if from_date else None,
        to_date=str(to_date) if to_date else None,
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

    rows = query.order_by(AuctionRow.start_date).all()
    auctions = [Auction.model_validate(r, from_attributes=True) for r in rows]
    logger.info("queried auctions", count=len(auctions))
    return auctions
