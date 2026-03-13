"""Tests for CountyWebsiteCollector."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tdc_auction_calendar.collectors.county_websites.county_collector import (
    CountyWebsiteCollector,
)
from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.models.enums import SaleType, SourceType

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "county_websites"


def _mock_scrape_result(data, url="https://example.com"):
    return ScrapeResult(
        fetch=FetchResult(
            url=url,
            status_code=200,
            fetcher="crawl4ai",
            html="<div>results</div>",
        ),
        data=data,
    )


@pytest.fixture()
def collector():
    return CountyWebsiteCollector()


def test_name(collector):
    assert collector.name == "county_website"


def test_source_type(collector):
    assert collector.source_type == SourceType.COUNTY_WEBSITE


def test_normalize_raises_not_implemented(collector):
    """normalize() requires county context; callers must use _normalize_record()."""
    with pytest.raises(NotImplementedError):
        collector.normalize({"sale_date": "2026-06-15"})


def test_loads_counties_with_urls(collector):
    """Only counties with tax_sale_page_url should be loaded."""
    assert len(collector._county_targets) >= 50
    for target in collector._county_targets:
        assert target["tax_sale_page_url"] is not None
        assert target["state_code"]
        assert target["county_name"]
        assert target["default_sale_type"]


def test_normalize_uses_seed_county_info(collector):
    """State and county should come from seed data, not extraction."""
    target = collector._county_targets[0]
    raw = {"sale_date": "2026-06-15", "sale_type": "lien"}
    auction = collector._normalize_record(raw, target)
    assert auction.state == target["state_code"]
    assert auction.county == target["county_name"]
    assert auction.source_url == target["tax_sale_page_url"]
    assert auction.source_type == SourceType.COUNTY_WEBSITE
    assert auction.confidence_score == 0.70


def test_normalize_falls_back_sale_type(collector):
    """Empty/missing sale_type should use state's default."""
    target = collector._county_targets[0]
    raw = {"sale_date": "2026-06-15", "sale_type": ""}
    auction = collector._normalize_record(raw, target)
    assert auction.sale_type == SaleType(target["default_sale_type"])

    raw_missing = {"sale_date": "2026-06-15"}
    auction2 = collector._normalize_record(raw_missing, target)
    assert auction2.sale_type == SaleType(target["default_sale_type"])


def test_normalize_optional_fields(collector):
    """Optional fields should be parsed when present."""
    target = collector._county_targets[0]
    raw = {
        "sale_date": "2026-06-15",
        "sale_type": "lien",
        "end_date": "2026-06-17",
        "deposit_amount": "5000",
        "registration_deadline": "2026-05-01",
    }
    auction = collector._normalize_record(raw, target)
    assert auction.end_date == date(2026, 6, 17)
    assert auction.deposit_amount == Decimal("5000")
    assert auction.registration_deadline == date(2026, 5, 1)


def test_normalize_optional_fields_absent(collector):
    """Absent optional fields should be None."""
    target = collector._county_targets[0]
    raw = {"sale_date": "2026-06-15"}
    auction = collector._normalize_record(raw, target)
    assert auction.end_date is None
    assert auction.deposit_amount is None
    assert auction.registration_deadline is None


# --- Fetch behavior tests ---

def _make_collector_with_targets(targets):
    """Create a collector with specific county targets (bypasses seed loading)."""
    collector = CountyWebsiteCollector.__new__(CountyWebsiteCollector)
    collector._county_targets = targets
    return collector


_TEST_TARGETS = [
    {
        "state_code": "FL",
        "county_name": "Duval",
        "tax_sale_page_url": "https://duval.example.com/taxsale",
        "default_sale_type": "lien",
    },
    {
        "state_code": "CO",
        "county_name": "Denver",
        "tax_sale_page_url": "https://denver.example.com/taxlien",
        "default_sale_type": "lien",
    },
]


async def test_fetch_returns_auctions():
    collector = _make_collector_with_targets(_TEST_TARGETS)
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(
        [{"sale_date": "2026-06-15", "sale_type": "lien"}]
    )
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.county_websites.county_collector.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 2
    states = {a.state for a in auctions}
    assert states == {"FL", "CO"}


async def test_fetch_skips_failed_counties():
    collector = _make_collector_with_targets(_TEST_TARGETS)
    mock_client = AsyncMock()
    mock_client.scrape.side_effect = [
        RuntimeError("network error"),
        _mock_scrape_result(
            [{"sale_date": "2026-06-15", "sale_type": "lien"}]
        ),
    ]
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.county_websites.county_collector.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 1
    assert auctions[0].state == "CO"


async def test_fetch_skips_invalid_records():
    collector = _make_collector_with_targets(_TEST_TARGETS[:1])
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result([
        {"sale_date": "2026-06-15", "sale_type": "lien"},
        {"sale_date": "bad-date"},
    ])
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.county_websites.county_collector.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 1


async def test_fetch_filters_past_dates():
    collector = _make_collector_with_targets(_TEST_TARGETS[:1])
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result([
        {"sale_date": "2026-06-15", "sale_type": "lien"},
        {"sale_date": "2020-01-01", "sale_type": "lien"},
    ])
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.county_websites.county_collector.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 1
    assert auctions[0].start_date == date(2026, 6, 15)


async def test_fetch_empty_urls_returns_empty():
    collector = _make_collector_with_targets([])
    auctions = await collector.collect()
    assert auctions == []


async def test_fetch_single_dict_result():
    collector = _make_collector_with_targets(_TEST_TARGETS[:1])
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(
        {"sale_date": "2026-06-15", "sale_type": "lien"}
    )
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.county_websites.county_collector.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 1


async def test_closes_client_on_failure():
    collector = _make_collector_with_targets(_TEST_TARGETS[:1])
    mock_client = AsyncMock()
    mock_client.scrape.side_effect = RuntimeError("network error")
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.county_websites.county_collector.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert auctions == []
    mock_client.close.assert_called_once()


# --- Acceptance test ---

async def test_acceptance_50_counties(collector):
    """Integration: fixture data should produce >= 50 county auction records."""
    fixture_path = FIXTURES_DIR / "county_extraction_results.json"
    with open(fixture_path) as f:
        fixture_data = json.load(f)

    def _side_effect(url, **kwargs):
        data = fixture_data.get(url)
        return _mock_scrape_result(data, url=url)

    mock_client = AsyncMock()
    mock_client.scrape.side_effect = _side_effect
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.county_websites.county_collector.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) >= 50
    assert all(a.source_type == SourceType.COUNTY_WEBSITE for a in auctions)
    assert all(a.confidence_score == 0.70 for a in auctions)
