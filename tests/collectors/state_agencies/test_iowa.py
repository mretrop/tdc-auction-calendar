"""Tests for Iowa state agency collector."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from tdc_auction_calendar.collectors.state_agencies.iowa import IowaCollector
from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.models.enums import SaleType, SourceType

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "state_agencies"


def _load_fixture():
    return json.loads((FIXTURES_DIR / "iowa_treasurers.json").read_text())


def _mock_scrape_result(data):
    return ScrapeResult(
        fetch=FetchResult(
            url="https://iowatreasurers.org",
            status_code=200,
            fetcher="cloudflare",
            html="<table>...</table>",
        ),
        data=data,
    )


@pytest.fixture()
def collector():
    return IowaCollector()


def test_name(collector):
    assert collector.name == "iowa_state_agency"


def test_source_type(collector):
    assert collector.source_type == SourceType.STATE_AGENCY


def test_normalize_valid_record(collector):
    raw = {"county": "Polk", "sale_date": "2026-06-16", "sale_type": "lien"}
    auction = collector.normalize(raw)
    assert auction.state == "IA"
    assert auction.county == "Polk"
    assert auction.start_date == date(2026, 6, 16)
    assert auction.sale_type == SaleType.LIEN
    assert auction.source_type == SourceType.STATE_AGENCY
    assert auction.confidence_score == 0.85
    assert auction.source_url == "https://iowatreasurers.org"


def test_normalize_missing_county_raises(collector):
    raw = {"sale_date": "2026-06-16", "sale_type": "lien"}
    with pytest.raises((ValidationError, ValueError, KeyError)):
        collector.normalize(raw)


def test_normalize_invalid_date_raises(collector):
    raw = {"county": "Polk", "sale_date": "not-a-date", "sale_type": "lien"}
    with pytest.raises((ValidationError, ValueError)):
        collector.normalize(raw)


async def test_fetch_returns_auctions(collector):
    fixture_data = _load_fixture()
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(fixture_data)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.iowa.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) >= 10
    assert all(a.state == "IA" for a in auctions)
    assert all(a.source_type == SourceType.STATE_AGENCY for a in auctions)


async def test_fetch_empty_data_returns_empty(collector):
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(None)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.iowa.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert auctions == []


async def test_fetch_skips_invalid_records(collector):
    data = [
        {"county": "Polk", "sale_date": "2026-06-16", "sale_type": "lien"},
        {"county": "", "sale_date": "bad-date"},  # invalid
        {"county": "Linn", "sale_date": "2026-06-15", "sale_type": "lien"},
    ]
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(data)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.iowa.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 2
