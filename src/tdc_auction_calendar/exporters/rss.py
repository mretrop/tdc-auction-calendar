"""RSS exporter — converts Auction models to RSS 2.0 XML string."""

from __future__ import annotations

import datetime
import html
import xml.etree.ElementTree as ET
from email.utils import format_datetime

from tdc_auction_calendar.models.auction import Auction


def _build_description(auction: Auction) -> str:
    """Build HTML description from auction fields."""
    parts: list[str] = []
    if auction.registration_deadline is not None:
        parts.append(f"<b>Registration deadline:</b> {auction.registration_deadline}")
    if auction.deposit_amount is not None:
        parts.append(f"<b>Deposit:</b> ${auction.deposit_amount:.2f}")
    if auction.vendor is not None:
        parts.append(f"<b>Vendor:</b> {html.escape(auction.vendor)}")
    if auction.property_count is not None:
        parts.append(f"<b>Properties:</b> {auction.property_count}")
    if auction.source_url is not None:
        url = html.escape(auction.source_url)
        parts.append(f'<a href="{url}">Source</a>')
    return "<br>".join(parts) if parts else "No additional details."


def _date_to_rfc822(d: datetime.date) -> str:
    """Convert a date to RFC 822 format string."""
    dt = datetime.datetime.combine(d, datetime.time.min, tzinfo=datetime.timezone.utc)
    return format_datetime(dt, usegmt=True)


def auctions_to_rss(auctions: list[Auction], title: str = "Tax Auction Calendar") -> str:
    """Convert a list of Auction models to an RSS 2.0 XML string."""
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "description").text = (
        "Tax deed auction dates aggregated from county and state sources"
    )
    ET.SubElement(channel, "link").text = "https://github.com/mretrop/tdc-auction-calendar"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(
        datetime.datetime.now(datetime.timezone.utc), usegmt=True
    )

    for auction in auctions:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = (
            f"{auction.county} {auction.state} Tax {auction.sale_type.title()} Sale"
            f" — {auction.start_date}"
        )
        ET.SubElement(item, "description").text = _build_description(auction)
        ET.SubElement(item, "pubDate").text = _date_to_rfc822(auction.start_date)
        guid = ET.SubElement(item, "guid", isPermaLink="false")
        guid.text = f"{auction.state}-{auction.county}-{auction.start_date}-{auction.sale_type}"
        if auction.source_url:
            ET.SubElement(item, "link").text = auction.source_url

    return ET.tostring(rss, encoding="unicode", xml_declaration=True)
