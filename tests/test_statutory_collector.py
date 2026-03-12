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


class TestCollect:
    @pytest.mark.asyncio
    async def test_generates_500_plus_records(self):
        collector = StatutoryCollector()
        auctions = await collector.collect()
        assert len(auctions) >= 500

    @pytest.mark.asyncio
    async def test_all_records_have_valid_dates(self):
        collector = StatutoryCollector()
        auctions = await collector.collect()
        for a in auctions:
            assert a.start_date.day == 1
            assert a.end_date >= a.start_date

    @pytest.mark.asyncio
    async def test_correct_metadata(self):
        collector = StatutoryCollector()
        auctions = await collector.collect()
        for a in auctions:
            assert a.source_type == SourceType.STATUTORY
            assert a.confidence_score == 0.4

    @pytest.mark.asyncio
    async def test_two_year_span(self):
        collector = StatutoryCollector()
        auctions = await collector.collect()
        years = {a.start_date.year for a in auctions}
        import datetime
        current_year = datetime.date.today().year
        assert current_year in years
        assert current_year + 1 in years

    @pytest.mark.asyncio
    async def test_no_duplicate_dedup_keys(self):
        collector = StatutoryCollector()
        auctions = await collector.collect()
        keys = [a.dedup_key for a in auctions]
        assert len(keys) == len(set(keys))


class TestSkipLists:
    @pytest.mark.asyncio
    async def test_skip_states(self):
        collector = StatutoryCollector(skip_states={"FL"})
        auctions = await collector.collect()
        assert all(a.state != "FL" for a in auctions)
        assert len(auctions) > 0  # other states still present

    @pytest.mark.asyncio
    async def test_skip_counties(self):
        collector = StatutoryCollector(skip_counties={("AL", "Jefferson")})
        auctions = await collector.collect()
        assert all(
            not (a.state == "AL" and a.county == "Jefferson") for a in auctions
        )
        # other AL counties still present
        assert any(a.state == "AL" for a in auctions)


class TestVendorEnrichment:
    @pytest.mark.asyncio
    async def test_some_records_have_vendor(self):
        collector = StatutoryCollector()
        auctions = await collector.collect()
        with_vendor = [a for a in auctions if a.vendor is not None]
        assert len(with_vendor) > 0

    @pytest.mark.asyncio
    async def test_vendor_records_have_source_url(self):
        collector = StatutoryCollector()
        auctions = await collector.collect()
        with_vendor = [a for a in auctions if a.vendor is not None]
        for a in with_vendor:
            assert a.source_url is not None
