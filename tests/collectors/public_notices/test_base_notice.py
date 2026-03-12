"""Tests for BaseNoticeCollector."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from tdc_auction_calendar.collectors.public_notices.base_notice import BaseNoticeCollector
from tdc_auction_calendar.collectors.scraping.client import ExtractionError, ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType


class ConcreteNoticeCollector(BaseNoticeCollector):
    """Minimal concrete implementation for testing."""

    state_code = "FL"
    default_sale_type = SaleType.LIEN
    base_url = "https://example.com"
    search_keywords = ["tax lien sale"]
    use_json_options = True

    @property
    def name(self) -> str:
        return "test_notice"

    def _build_search_url(self, keyword: str) -> str:
        return f"{self.base_url}?search={keyword.replace(' ', '+')}"


def _mock_scrape_result(data):
    return ScrapeResult(
        fetch=FetchResult(
            url="https://example.com",
            status_code=200,
            fetcher="crawl4ai",
            html="<div>results</div>",
        ),
        data=data,
    )


@pytest.fixture()
def collector():
    return ConcreteNoticeCollector()


def test_source_type(collector):
    assert collector.source_type == SourceType.PUBLIC_NOTICE


def test_confidence_score(collector):
    assert collector.confidence_score == 0.75


def test_normalize_valid_record(collector):
    raw = {"county": "Duval", "sale_date": "2026-06-01", "sale_type": "lien"}
    auction = collector.normalize(raw)
    assert auction.state == "FL"
    assert auction.county == "Duval"
    assert auction.start_date == date(2026, 6, 1)
    assert auction.sale_type == SaleType.LIEN
    assert auction.source_type == SourceType.PUBLIC_NOTICE
    assert auction.confidence_score == 0.75
    assert auction.source_url == "https://example.com"


def test_normalize_uses_default_sale_type(collector):
    raw = {"county": "Duval", "sale_date": "2026-06-01"}
    auction = collector.normalize(raw)
    assert auction.sale_type == SaleType.LIEN


def test_normalize_missing_county_raises(collector):
    raw = {"sale_date": "2026-06-01"}
    with pytest.raises((KeyError, ValueError)):
        collector.normalize(raw)


def test_normalize_invalid_date_raises(collector):
    raw = {"county": "Duval", "sale_date": "not-a-date"}
    with pytest.raises(ValueError):
        collector.normalize(raw)


async def test_fetch_searches_keywords(collector):
    """_fetch should try each keyword and aggregate results."""
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(
        [{"county": "Duval", "sale_date": "2026-06-01", "sale_type": "lien"}]
    )
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) >= 1
    assert all(a.source_type == SourceType.PUBLIC_NOTICE for a in auctions)


async def test_fetch_filters_past_dates(collector):
    """Records with start_date in the past should be dropped."""
    data = [
        {"county": "Duval", "sale_date": "2026-06-01", "sale_type": "lien"},
        {"county": "Clay", "sale_date": "2020-01-01", "sale_type": "lien"},
    ]
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(data)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 1
    assert auctions[0].county == "Duval"


async def test_fetch_empty_results_returns_empty(collector):
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


async def test_fetch_raises_when_all_records_fail(collector):
    data = [{"county": "", "sale_date": "bad"}, {"sale_date": "nope"}]
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(data)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        with pytest.raises(ExtractionError, match="all 2 records failed"):
            await collector.collect()
