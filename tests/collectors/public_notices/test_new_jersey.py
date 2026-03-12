"""Tests for New Jersey public notice collector."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tdc_auction_calendar.collectors.public_notices.new_jersey import NewJerseyCollector
from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.models.enums import SaleType, SourceType

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "public_notices"


def _load_fixture():
    return json.loads((FIXTURES_DIR / "new_jersey_notices.json").read_text())


def _mock_scrape_result(data):
    return ScrapeResult(
        fetch=FetchResult(
            url="https://www.njpublicnotices.com",
            status_code=200,
            fetcher="crawl4ai",
            html="<div>results</div>",
        ),
        data=data,
    )


@pytest.fixture()
def collector():
    return NewJerseyCollector()


def test_name(collector):
    assert collector.name == "new_jersey_public_notice"


def test_source_type(collector):
    assert collector.source_type == SourceType.PUBLIC_NOTICE


def test_normalize_valid_record(collector):
    raw = {"county": "Essex", "sale_date": "2026-10-20", "sale_type": "lien"}
    auction = collector.normalize(raw)
    assert auction.state == "NJ"
    assert auction.county == "Essex"
    assert auction.sale_type == SaleType.LIEN
    assert auction.confidence_score == 0.75


def test_normalize_defaults_to_lien(collector):
    raw = {"county": "Essex", "sale_date": "2026-10-20"}
    auction = collector.normalize(raw)
    assert auction.sale_type == SaleType.LIEN


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
    assert all(a.state == "NJ" for a in auctions)


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
