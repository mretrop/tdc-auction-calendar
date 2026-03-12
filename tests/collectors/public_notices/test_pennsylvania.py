"""Tests for Pennsylvania public notice collector."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tdc_auction_calendar.collectors.public_notices.pennsylvania import PennsylvaniaCollector
from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.models.enums import SaleType, SourceType

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "public_notices"


def _load_fixture():
    return json.loads((FIXTURES_DIR / "pennsylvania_notices.json").read_text())


def _mock_scrape_result(data):
    return ScrapeResult(
        fetch=FetchResult(
            url="https://www.publicnoticepa.com",
            status_code=200,
            fetcher="crawl4ai",
            html="<div>results</div>",
        ),
        data=data,
    )


@pytest.fixture()
def collector():
    return PennsylvaniaCollector()


def test_name(collector):
    assert collector.name == "pennsylvania_public_notice"


def test_source_type(collector):
    assert collector.source_type == SourceType.PUBLIC_NOTICE


def test_normalize_valid_record(collector):
    raw = {"county": "Philadelphia", "sale_date": "2026-09-22", "sale_type": "deed"}
    auction = collector.normalize(raw)
    assert auction.state == "PA"
    assert auction.county == "Philadelphia"
    assert auction.sale_type == SaleType.DEED
    assert auction.confidence_score == 0.75


def test_build_search_url(collector):
    url = collector._build_search_url("tax sale")
    assert "publicnoticepa.com" in url
    assert "Search.aspx" in url


def test_uses_column_platform_js(collector):
    js = collector._get_js_code("tax sale")
    assert js is not None
    assert "txtKeywords" in js
    assert "tax sale" in js


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

    assert len(auctions) >= 5
    assert all(a.state == "PA" for a in auctions)
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
