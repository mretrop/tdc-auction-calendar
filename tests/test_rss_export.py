"""Tests for RSS exporter."""

from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
from decimal import Decimal

from tdc_auction_calendar.exporters.rss import auctions_to_rss
from tdc_auction_calendar.models.auction import Auction


def _make_auction(**overrides) -> Auction:
    """Build an Auction with sensible defaults."""
    defaults = {
        "state": "FL",
        "county": "Miami-Dade",
        "start_date": datetime.date(2027, 4, 15),
        "end_date": datetime.date(2027, 4, 17),
        "sale_type": "deed",
        "status": "upcoming",
        "source_type": "statutory",
        "confidence_score": 1.0,
    }
    defaults.update(overrides)
    return Auction(**defaults)


class TestAuctionsToRss:
    def test_empty_list_returns_valid_rss(self):
        result = auctions_to_rss([])
        root = ET.fromstring(result)
        assert root.tag == "rss"
        assert root.attrib["version"] == "2.0"
        channel = root.find("channel")
        assert channel is not None
        assert channel.find("title").text == "Tax Auction Calendar"
        items = channel.findall("item")
        assert items == []

    def test_custom_title(self):
        result = auctions_to_rss([], title="Tax Auction Calendar — FL")
        root = ET.fromstring(result)
        assert root.find("channel/title").text == "Tax Auction Calendar — FL"

    def test_single_auction_produces_item(self):
        auction = _make_auction()
        result = auctions_to_rss([auction])
        root = ET.fromstring(result)
        items = root.findall("channel/item")
        assert len(items) == 1

    def test_item_title_format(self):
        auction = _make_auction(county="Miami-Dade", state="FL", sale_type="deed",
                                start_date=datetime.date(2027, 4, 15))
        result = auctions_to_rss([auction])
        root = ET.fromstring(result)
        item = root.find("channel/item")
        assert item.find("title").text == "Miami-Dade FL Tax Deed Sale — 2027-04-15"

    def test_guid_is_stable(self):
        auction = _make_auction(state="FL", county="Miami-Dade",
                                start_date=datetime.date(2027, 4, 15), sale_type="deed")
        result1 = auctions_to_rss([auction])
        result2 = auctions_to_rss([auction])
        root1 = ET.fromstring(result1)
        root2 = ET.fromstring(result2)
        guid1 = root1.find("channel/item/guid").text
        guid2 = root2.find("channel/item/guid").text
        assert guid1 == guid2
        assert guid1 == "FL-Miami-Dade-2027-04-15-deed"

    def test_guid_is_not_permalink(self):
        auction = _make_auction()
        result = auctions_to_rss([auction])
        root = ET.fromstring(result)
        guid = root.find("channel/item/guid")
        assert guid.attrib["isPermaLink"] == "false"

    def test_description_contains_key_fields(self):
        auction = _make_auction(
            registration_deadline=datetime.date(2027, 4, 1),
            deposit_amount=Decimal("5000.00"),
            vendor="RealAuction",
            source_url="https://example.com/auction",
        )
        result = auctions_to_rss([auction])
        root = ET.fromstring(result)
        desc = root.find("channel/item/description").text
        assert "2027-04-01" in desc
        assert "5000.00" in desc
        assert "RealAuction" in desc
        assert "https://example.com/auction" in desc

    def test_item_link_from_source_url(self):
        auction = _make_auction(source_url="https://example.com/auction")
        result = auctions_to_rss([auction])
        root = ET.fromstring(result)
        link = root.find("channel/item/link")
        assert link.text == "https://example.com/auction"

    def test_item_link_absent_when_no_source_url(self):
        auction = _make_auction(source_url=None)
        result = auctions_to_rss([auction])
        root = ET.fromstring(result)
        link = root.find("channel/item/link")
        assert link is None

    def test_pubdate_is_rfc822(self):
        auction = _make_auction(start_date=datetime.date(2027, 4, 15))
        result = auctions_to_rss([auction])
        root = ET.fromstring(result)
        pubdate = root.find("channel/item/pubDate").text
        assert "15 Apr 2027" in pubdate
        assert "GMT" in pubdate

    def test_multiple_auctions(self):
        a1 = _make_auction(state="FL")
        a2 = _make_auction(state="TX", county="Harris")
        result = auctions_to_rss([a1, a2])
        root = ET.fromstring(result)
        items = root.findall("channel/item")
        assert len(items) == 2

    def test_channel_has_last_build_date(self):
        result = auctions_to_rss([])
        root = ET.fromstring(result)
        lbd = root.find("channel/lastBuildDate")
        assert lbd is not None
        assert "GMT" in lbd.text

    def test_description_html_escapes_special_chars(self):
        auction = _make_auction(county="O'Brien & Sons")
        result = auctions_to_rss([auction])
        root = ET.fromstring(result)
        item = root.find("channel/item")
        assert item is not None
