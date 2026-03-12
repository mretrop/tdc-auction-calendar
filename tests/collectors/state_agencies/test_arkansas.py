"""Tests for Arkansas state agency collector."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from tdc_auction_calendar.collectors.state_agencies.arkansas import ArkansasCollector
from tdc_auction_calendar.collectors.scraping.client import ExtractionError, ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.models.enums import SaleType, SourceType

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "state_agencies"


def _load_fixture():
    return json.loads((FIXTURES_DIR / "arkansas_cosl.json").read_text())


def _mock_scrape_result(data):
    return ScrapeResult(
        fetch=FetchResult(
            url="https://cosl.org",
            status_code=200,
            fetcher="cloudflare",
            html="<table>...</table>",
        ),
        data=data,
    )


@pytest.fixture()
def collector():
    return ArkansasCollector()


def test_name(collector):
    assert collector.name == "arkansas_state_agency"


def test_source_type(collector):
    assert collector.source_type == SourceType.STATE_AGENCY


def test_normalize_valid_record(collector):
    raw = {"county": "Pulaski", "sale_date": "2026-06-10", "sale_type": "deed"}
    auction = collector.normalize(raw)
    assert auction.state == "AR"
    assert auction.county == "Pulaski"
    assert auction.start_date == date(2026, 6, 10)
    assert auction.sale_type == SaleType.DEED
    assert auction.source_type == SourceType.STATE_AGENCY
    assert auction.confidence_score == 0.85
    assert auction.source_url == "https://cosl.org"


def test_normalize_missing_county_raises(collector):
    raw = {"sale_date": "2026-06-10", "sale_type": "deed"}
    with pytest.raises((ValidationError, ValueError, KeyError)):
        collector.normalize(raw)


def test_normalize_invalid_date_raises(collector):
    raw = {"county": "Pulaski", "sale_date": "not-a-date", "sale_type": "deed"}
    with pytest.raises((ValidationError, ValueError)):
        collector.normalize(raw)


async def test_fetch_returns_auctions(collector):
    fixture_data = _load_fixture()
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(fixture_data)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.arkansas.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) >= 10
    assert all(a.state == "AR" for a in auctions)
    assert all(a.source_type == SourceType.STATE_AGENCY for a in auctions)


async def test_fetch_empty_data_returns_empty(collector):
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(None)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.arkansas.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert auctions == []


async def test_fetch_skips_invalid_records(collector):
    data = [
        {"county": "Pulaski", "sale_date": "2026-06-10", "sale_type": "deed"},
        {"county": "", "sale_date": "bad-date"},  # invalid
        {"county": "Benton", "sale_date": "2026-06-10", "sale_type": "deed"},
    ]
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(data)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.arkansas.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 2


async def test_fetch_raises_when_all_records_fail(collector):
    data = [
        {"county": "", "sale_date": "bad-date"},
        {"sale_date": "also-bad"},
    ]
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(data)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.arkansas.create_scrape_client",
        return_value=mock_client,
    ):
        with pytest.raises(ExtractionError, match="all 2 records failed"):
            await collector.collect()
