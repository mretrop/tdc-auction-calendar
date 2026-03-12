"""Tests for Florida public notice collector."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tdc_auction_calendar.collectors.public_notices.florida import FloridaCollector
from tdc_auction_calendar.collectors.scraping.client import ExtractionError, ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.models.enums import SaleType, SourceType

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "public_notices"


def _load_fixture():
    return json.loads((FIXTURES_DIR / "florida_notices.json").read_text())


def _mock_scrape_result(data):
    return ScrapeResult(
        fetch=FetchResult(
            url="https://www.floridapublicnotices.com",
            status_code=200,
            fetcher="crawl4ai",
            html="<div>results</div>",
        ),
        data=data,
    )


@pytest.fixture()
def collector():
    return FloridaCollector()


def test_name(collector):
    assert collector.name == "florida_public_notice"


def test_source_type(collector):
    assert collector.source_type == SourceType.PUBLIC_NOTICE


def test_normalize_valid_record(collector):
    raw = {"county": "Duval", "sale_date": "2026-06-01", "sale_type": "lien"}
    auction = collector.normalize(raw)
    assert auction.state == "FL"
    assert auction.county == "Duval"
    assert auction.start_date == date(2026, 6, 1)
    assert auction.sale_type == SaleType.LIEN
    assert auction.source_type == SourceType.PUBLIC_NOTICE
    assert auction.confidence_score == 0.75


def test_normalize_defaults_to_lien(collector):
    raw = {"county": "Duval", "sale_date": "2026-06-01"}
    auction = collector.normalize(raw)
    assert auction.sale_type == SaleType.LIEN


def test_normalize_missing_county_raises(collector):
    raw = {"sale_date": "2026-06-01"}
    with pytest.raises((KeyError, ValueError)):
        collector.normalize(raw)


def test_build_search_url(collector):
    url = collector._build_search_url("tax lien sale")
    assert "floridapublicnotices.com" in url
    assert "tax+lien+sale" in url


def test_no_js_code(collector):
    """Florida uses URL-based search, no JS form interaction."""
    assert collector._get_js_code("tax lien sale") is None


async def test_fetch_returns_auctions(collector):
    fixture_data = _load_fixture()
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(fixture_data)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) >= 10
    assert all(a.state == "FL" for a in auctions)
    assert all(a.source_type == SourceType.PUBLIC_NOTICE for a in auctions)


async def test_fetch_empty_data_returns_empty(collector):
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(None)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert auctions == []


async def test_fetch_skips_invalid_records(collector):
    data = [
        {"county": "Duval", "sale_date": "2026-06-01", "sale_type": "lien"},
        {"county": "", "sale_date": "bad-date"},
        {"county": "Clay", "sale_date": "2026-06-15", "sale_type": "lien"},
    ]
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(data)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 2
