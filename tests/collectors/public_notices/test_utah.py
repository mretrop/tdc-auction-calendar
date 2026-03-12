"""Tests for Utah public notice collector."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tdc_auction_calendar.collectors.public_notices.utah import UtahCollector
from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.models.enums import SaleType, SourceType

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "public_notices"


def _load_fixture():
    return json.loads((FIXTURES_DIR / "utah_notices.json").read_text())


def _mock_scrape_result(data):
    return ScrapeResult(
        fetch=FetchResult(
            url="https://www.utahlegals.com",
            status_code=200,
            fetcher="crawl4ai",
            html="<div>results</div>",
        ),
        data=data,
    )


@pytest.fixture()
def collector():
    return UtahCollector()


def test_name(collector):
    assert collector.name == "utah_public_notice"


def test_source_type(collector):
    assert collector.source_type == SourceType.PUBLIC_NOTICE


def test_normalize_valid_record(collector):
    raw = {"county": "Salt Lake", "sale_date": "2026-05-22", "sale_type": "deed"}
    auction = collector.normalize(raw)
    assert auction.state == "UT"
    assert auction.county == "Salt Lake"
    assert auction.sale_type == SaleType.DEED
    assert auction.confidence_score == 0.75


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

    assert len(auctions) >= 3
    assert all(a.state == "UT" for a in auctions)


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
