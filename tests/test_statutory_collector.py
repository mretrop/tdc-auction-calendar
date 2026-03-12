"""Tests for the statutory baseline collector."""

import datetime
import json
import time

import pytest

from tdc_auction_calendar.collectors.statutory import StatutoryCollector
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType

import tdc_auction_calendar.collectors.statutory.state_statutes as _stat_mod


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


class TestPerformance:
    @pytest.mark.asyncio
    async def test_collect_under_2_seconds(self):
        collector = StatutoryCollector()
        start = time.monotonic()
        await collector.collect()
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"collect() took {elapsed:.2f}s, expected < 2s"


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_null_typical_months_skipped(self, monkeypatch):
        """States with typical_months=None produce zero auctions for that state."""
        fake_states = [
            {"state": "XX", "sale_type": "deed", "typical_months": None},
            {"state": "YY", "sale_type": "lien", "typical_months": [6]},
        ]
        fake_counties = [
            {"state": "XX", "county_name": "FakeCounty"},
            {"state": "YY", "county_name": "TestCounty"},
        ]
        fake_vendors: list = []

        monkeypatch.setattr(_stat_mod, "_load_seed_files", lambda: (fake_states, fake_counties, fake_vendors))
        collector = StatutoryCollector()
        auctions = await collector.collect()
        assert all(a.state != "XX" for a in auctions)
        assert any(a.state == "YY" for a in auctions)

    @pytest.mark.asyncio
    async def test_empty_typical_months_skipped(self, monkeypatch):
        """States with typical_months=[] produce zero auctions for that state."""
        fake_states = [
            {"state": "XX", "sale_type": "deed", "typical_months": []},
            {"state": "YY", "sale_type": "lien", "typical_months": [3]},
        ]
        fake_counties = [
            {"state": "XX", "county_name": "FakeCounty"},
            {"state": "YY", "county_name": "TestCounty"},
        ]
        fake_vendors: list = []

        monkeypatch.setattr(_stat_mod, "_load_seed_files", lambda: (fake_states, fake_counties, fake_vendors))
        collector = StatutoryCollector()
        auctions = await collector.collect()
        assert all(a.state != "XX" for a in auctions)
        assert any(a.state == "YY" for a in auctions)


class TestIsolatedFetchLogic:
    """Unit tests for _fetch() logic using mocked seed data."""

    @pytest.mark.asyncio
    async def test_skip_states_with_mocked_data(self, monkeypatch):
        fake_states = [
            {"state": "AA", "sale_type": "deed", "typical_months": [1]},
            {"state": "BB", "sale_type": "lien", "typical_months": [6]},
        ]
        fake_counties = [
            {"state": "AA", "county_name": "Alpha"},
            {"state": "BB", "county_name": "Beta"},
        ]
        fake_vendors: list = []

        monkeypatch.setattr(_stat_mod, "_load_seed_files", lambda: (fake_states, fake_counties, fake_vendors))
        collector = StatutoryCollector(skip_states={"AA"})
        auctions = await collector.collect()
        assert all(a.state != "AA" for a in auctions)
        assert any(a.state == "BB" for a in auctions)

    @pytest.mark.asyncio
    async def test_skip_counties_with_mocked_data(self, monkeypatch):
        fake_states = [
            {"state": "AA", "sale_type": "deed", "typical_months": [1]},
        ]
        fake_counties = [
            {"state": "AA", "county_name": "Alpha"},
            {"state": "AA", "county_name": "Beta"},
        ]
        fake_vendors: list = []

        monkeypatch.setattr(_stat_mod, "_load_seed_files", lambda: (fake_states, fake_counties, fake_vendors))
        collector = StatutoryCollector(skip_counties={("AA", "Alpha")})
        auctions = await collector.collect()
        assert all(a.county != "Alpha" for a in auctions)
        assert any(a.county == "Beta" for a in auctions)

    @pytest.mark.asyncio
    async def test_vendor_enrichment_with_mocked_data(self, monkeypatch):
        fake_states = [
            {"state": "AA", "sale_type": "deed", "typical_months": [6]},
        ]
        fake_counties = [
            {"state": "AA", "county_name": "Alpha"},
        ]
        fake_vendors = [
            {"state": "AA", "county": "Alpha", "vendor": "TestVendor", "portal_url": "https://example.com"},
        ]

        monkeypatch.setattr(_stat_mod, "_load_seed_files", lambda: (fake_states, fake_counties, fake_vendors))
        collector = StatutoryCollector()
        auctions = await collector.collect()
        assert all(a.vendor == "TestVendor" for a in auctions)
        assert all(a.source_url == "https://example.com" for a in auctions)

    @pytest.mark.asyncio
    async def test_vendor_without_portal_url(self, monkeypatch):
        fake_states = [
            {"state": "AA", "sale_type": "deed", "typical_months": [6]},
        ]
        fake_counties = [
            {"state": "AA", "county_name": "Alpha"},
        ]
        fake_vendors = [
            {"state": "AA", "county": "Alpha", "vendor": "NoPortalVendor"},
        ]

        monkeypatch.setattr(_stat_mod, "_load_seed_files", lambda: (fake_states, fake_counties, fake_vendors))
        collector = StatutoryCollector()
        auctions = await collector.collect()
        assert all(a.vendor == "NoPortalVendor" for a in auctions)
        assert all(a.source_url is None for a in auctions)

    @pytest.mark.asyncio
    async def test_sale_type_lien_propagates(self, monkeypatch):
        fake_states = [
            {"state": "AA", "sale_type": "lien", "typical_months": [3]},
        ]
        fake_counties = [
            {"state": "AA", "county_name": "Alpha"},
        ]
        fake_vendors: list = []

        monkeypatch.setattr(_stat_mod, "_load_seed_files", lambda: (fake_states, fake_counties, fake_vendors))
        collector = StatutoryCollector()
        auctions = await collector.collect()
        assert all(a.sale_type == SaleType.LIEN for a in auctions)

    @pytest.mark.asyncio
    async def test_missing_county_name_skipped(self, monkeypatch):
        fake_states = [
            {"state": "AA", "sale_type": "deed", "typical_months": [6]},
        ]
        fake_counties = [
            {"state": "AA"},  # missing county_name
            {"state": "AA", "county_name": "Good"},
        ]
        fake_vendors: list = []

        monkeypatch.setattr(_stat_mod, "_load_seed_files", lambda: (fake_states, fake_counties, fake_vendors))
        collector = StatutoryCollector()
        auctions = await collector.collect()
        assert len(auctions) > 0
        assert all(a.county == "Good" for a in auctions)

    @pytest.mark.asyncio
    async def test_missing_sale_type_skipped(self, monkeypatch):
        """States with sale_type=None produce zero auctions for that state."""
        fake_states = [
            {"state": "XX", "sale_type": None, "typical_months": [6]},
            {"state": "YY", "sale_type": "lien", "typical_months": [6]},
        ]
        fake_counties = [
            {"state": "XX", "county_name": "FakeCounty"},
            {"state": "YY", "county_name": "TestCounty"},
        ]
        fake_vendors: list = []

        monkeypatch.setattr(_stat_mod, "_load_seed_files", lambda: (fake_states, fake_counties, fake_vendors))
        collector = StatutoryCollector()
        auctions = await collector.collect()
        assert all(a.state != "XX" for a in auctions)
        assert any(a.state == "YY" for a in auctions)


    @pytest.mark.asyncio
    async def test_vendor_missing_state_key_skipped(self, monkeypatch):
        """Vendor records missing state/county keys are skipped; auction has no vendor."""
        fake_states = [
            {"state": "AA", "sale_type": "deed", "typical_months": [6]},
        ]
        fake_counties = [
            {"state": "AA", "county_name": "Alpha"},
        ]
        fake_vendors = [
            {"vendor": "OrphanVendor", "portal_url": "https://example.com"},  # missing state & county
        ]

        monkeypatch.setattr(_stat_mod, "_load_seed_files", lambda: (fake_states, fake_counties, fake_vendors))
        collector = StatutoryCollector()
        auctions = await collector.collect()
        assert len(auctions) > 0
        assert all(a.vendor is None for a in auctions)
        assert all(a.source_url is None for a in auctions)

    @pytest.mark.asyncio
    async def test_vendor_missing_name_skips_enrichment(self, monkeypatch):
        """Vendor record with no 'vendor' key produces auction without vendor info."""
        fake_states = [
            {"state": "AA", "sale_type": "deed", "typical_months": [6]},
        ]
        fake_counties = [
            {"state": "AA", "county_name": "Alpha"},
        ]
        fake_vendors = [
            {"state": "AA", "county": "Alpha", "portal_url": "https://example.com"},  # no vendor key
        ]

        monkeypatch.setattr(_stat_mod, "_load_seed_files", lambda: (fake_states, fake_counties, fake_vendors))
        collector = StatutoryCollector()
        auctions = await collector.collect()
        assert len(auctions) > 0
        assert all(a.vendor is None for a in auctions)
        assert all(a.source_url is None for a in auctions)

    @pytest.mark.asyncio
    async def test_state_missing_state_key_skipped(self, monkeypatch):
        """State records missing the 'state' key are skipped."""
        fake_states = [
            {"sale_type": "deed", "typical_months": [6]},  # missing state key
            {"state": "YY", "sale_type": "lien", "typical_months": [6]},
        ]
        fake_counties = [
            {"state": "YY", "county_name": "TestCounty"},
        ]
        fake_vendors: list = []

        monkeypatch.setattr(_stat_mod, "_load_seed_files", lambda: (fake_states, fake_counties, fake_vendors))
        collector = StatutoryCollector()
        auctions = await collector.collect()
        assert any(a.state == "YY" for a in auctions)

    @pytest.mark.asyncio
    async def test_normalize_failure_skips_record(self, monkeypatch):
        """A record that fails Pydantic validation is skipped, not fatal."""
        fake_states = [
            {"state": "AA", "sale_type": "invalid_type", "typical_months": [6]},
            {"state": "BB", "sale_type": "deed", "typical_months": [6]},
        ]
        fake_counties = [
            {"state": "AA", "county_name": "Alpha"},
            {"state": "BB", "county_name": "Beta"},
        ]
        fake_vendors: list = []

        monkeypatch.setattr(_stat_mod, "_load_seed_files", lambda: (fake_states, fake_counties, fake_vendors))
        collector = StatutoryCollector()
        auctions = await collector.collect()
        # AA records fail validation but BB records still collected
        assert all(a.state != "AA" for a in auctions)
        assert any(a.state == "BB" for a in auctions)


class TestLoadSeedFiles:
    """Tests for _load_seed_files() error handling."""

    def test_missing_seed_file_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_stat_mod, "SEED_DIR", tmp_path)
        with pytest.raises(FileNotFoundError):
            _stat_mod._load_seed_files()

    def test_corrupt_seed_file_raises(self, monkeypatch, tmp_path):
        (tmp_path / "states.json").write_text("not json")
        monkeypatch.setattr(_stat_mod, "SEED_DIR", tmp_path)
        with pytest.raises(json.JSONDecodeError):
            _stat_mod._load_seed_files()
