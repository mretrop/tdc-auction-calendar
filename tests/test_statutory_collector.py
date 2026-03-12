"""Tests for the statutory baseline collector."""

import datetime

import pytest

from tdc_auction_calendar.collectors.statutory import StatutoryCollector
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType


class TestNormalize:
    def test_produces_valid_auction(self):
        collector = StatutoryCollector()
        raw = {
            "state": "FL",
            "county": "Miami-Dade",
            "month": 6,
            "year": 2026,
            "sale_type": "deed",
        }
        result = collector.normalize(raw)
        assert isinstance(result, Auction)
        assert result.state == "FL"
        assert result.county == "Miami-Dade"
        assert result.start_date == datetime.date(2026, 6, 1)
        assert result.end_date == datetime.date(2026, 6, 30)
        assert result.sale_type == SaleType.DEED
        assert result.source_type == SourceType.STATUTORY
        assert result.confidence_score == 0.4

    def test_with_vendor_enrichment(self):
        collector = StatutoryCollector()
        raw = {
            "state": "FL",
            "county": "Miami-Dade",
            "month": 6,
            "year": 2026,
            "sale_type": "deed",
            "vendor": "RealAuction",
            "portal_url": "https://miamidade.realforeclose.com",
        }
        result = collector.normalize(raw)
        assert result.vendor == "RealAuction"
        assert result.source_url == "https://miamidade.realforeclose.com"

    def test_without_vendor(self):
        collector = StatutoryCollector()
        raw = {
            "state": "TX",
            "county": "Harris",
            "month": 2,
            "year": 2027,
            "sale_type": "deed",
        }
        result = collector.normalize(raw)
        assert result.vendor is None
        assert result.source_url is None

    def test_february_end_date(self):
        collector = StatutoryCollector()
        raw = {
            "state": "TX",
            "county": "Harris",
            "month": 2,
            "year": 2026,
            "sale_type": "deed",
        }
        result = collector.normalize(raw)
        assert result.end_date == datetime.date(2026, 2, 28)

    def test_leap_year_february(self):
        collector = StatutoryCollector()
        raw = {
            "state": "TX",
            "county": "Harris",
            "month": 2,
            "year": 2028,
            "sale_type": "deed",
        }
        result = collector.normalize(raw)
        assert result.end_date == datetime.date(2028, 2, 29)
