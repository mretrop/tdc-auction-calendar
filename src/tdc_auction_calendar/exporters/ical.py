"""iCalendar exporter — converts Auction models to RFC 5545 .ics bytes."""

from __future__ import annotations

import datetime

from icalendar import Calendar, Event

from tdc_auction_calendar.models.auction import Auction


def _build_event(auction: Auction) -> Event:
    """Build a VEVENT from an Auction model."""
    event = Event()
    event.add("summary", f"{auction.county} {auction.state} Tax {auction.sale_type.title()} Sale")
    event.add("dtstart", auction.start_date)
    event.add("dtend", auction.end_date or auction.start_date + datetime.timedelta(days=1))
    event.add("uid", f"{auction.state}-{auction.county}-{auction.start_date}-{auction.sale_type}@tdc-auction-calendar")
    return event


def auctions_to_ical(auctions: list[Auction]) -> bytes:
    """Convert a list of Auction models to iCalendar bytes."""
    cal = Calendar()
    cal.add("prodid", "-//TDC Auction Calendar//EN")
    cal.add("version", "2.0")
    for auction in auctions:
        cal.add_component(_build_event(auction))
    return cal.to_ical()
