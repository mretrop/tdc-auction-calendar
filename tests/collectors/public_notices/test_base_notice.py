"""Tests for BaseNoticeCollector."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from tdc_auction_calendar.collectors.public_notices.base_notice import (
    BaseNoticeCollector,
    NoticeRecord,
    NoticeResults,
)
from tdc_auction_calendar.collectors.scraping.client import ExtractionError
from tdc_auction_calendar.models.enums import SaleType, SourceType

from tests.collectors.public_notices.conftest import mock_scrape_result


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


class MultiKeywordCollector(ConcreteNoticeCollector):
    """Collector with multiple keywords for aggregation testing."""

    search_keywords = ["tax lien sale", "delinquent tax"]


class SchemaCollector(ConcreteNoticeCollector):
    """Collector that uses schema extraction (not json_options)."""

    use_json_options = False


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


def test_normalize_empty_sale_type_uses_default(collector):
    """Empty string sale_type should fall back to default, not raise."""
    raw = {"county": "Duval", "sale_date": "2026-06-01", "sale_type": ""}
    auction = collector.normalize(raw)
    assert auction.sale_type == SaleType.LIEN


def test_normalize_missing_county_raises(collector):
    raw = {"sale_date": "2026-06-01"}
    with pytest.raises((KeyError, ValueError)):
        collector.normalize(raw)


def test_normalize_empty_county_raises(collector):
    raw = {"county": "", "sale_date": "2026-06-01"}
    with pytest.raises(ValueError, match="Empty county"):
        collector.normalize(raw)


def test_normalize_whitespace_county_raises(collector):
    raw = {"county": "   ", "sale_date": "2026-06-01"}
    with pytest.raises(ValueError, match="Empty county"):
        collector.normalize(raw)


def test_normalize_invalid_date_raises(collector):
    raw = {"county": "Duval", "sale_date": "not-a-date"}
    with pytest.raises(ValueError):
        collector.normalize(raw)


async def test_fetch_searches_keywords(collector):
    """_fetch should try each keyword and aggregate results."""
    mock_client = AsyncMock()
    mock_client.scrape.return_value = mock_scrape_result(
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


async def test_fetch_multiple_keywords_aggregates():
    """Results from multiple keywords should be combined."""
    collector = MultiKeywordCollector()
    mock_client = AsyncMock()
    mock_client.scrape.side_effect = [
        mock_scrape_result(
            [{"county": "Duval", "sale_date": "2026-06-01", "sale_type": "lien"}]
        ),
        mock_scrape_result(
            [{"county": "Clay", "sale_date": "2026-07-15", "sale_type": "lien"}]
        ),
    ]
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 2
    counties = {a.county for a in auctions}
    assert counties == {"Duval", "Clay"}
    assert mock_client.scrape.call_count == 2


async def test_fetch_json_options_path(collector):
    """When use_json_options=True and no js_code, should pass json_options to scrape."""
    mock_client = AsyncMock()
    mock_client.scrape.return_value = mock_scrape_result(
        [{"county": "Duval", "sale_date": "2026-06-01", "sale_type": "lien"}]
    )
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        await collector.collect()

    call_kwargs = mock_client.scrape.call_args[1]
    assert "json_options" in call_kwargs
    assert "schema" not in call_kwargs


async def test_fetch_schema_path():
    """When use_json_options=False, should pass schema to scrape."""
    collector = SchemaCollector()
    mock_client = AsyncMock()
    mock_client.scrape.return_value = mock_scrape_result(
        [{"county": "Duval", "sale_date": "2026-06-01", "sale_type": "lien"}]
    )
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        await collector.collect()

    call_kwargs = mock_client.scrape.call_args[1]
    assert "schema" in call_kwargs
    assert call_kwargs["schema"] is NoticeResults
    assert "json_options" not in call_kwargs


async def test_fetch_filters_past_dates(collector):
    """Records with start_date in the past should be dropped."""
    data = [
        {"county": "Duval", "sale_date": "2026-06-01", "sale_type": "lien"},
        {"county": "Clay", "sale_date": "2020-01-01", "sale_type": "lien"},
    ]
    mock_client = AsyncMock()
    mock_client.scrape.return_value = mock_scrape_result(data)
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
    mock_client.scrape.return_value = mock_scrape_result(None)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert auctions == []


async def test_fetch_single_dict_result(collector):
    """A single dict result.data (not in a list) should be wrapped and processed."""
    mock_client = AsyncMock()
    mock_client.scrape.return_value = mock_scrape_result(
        {"county": "Duval", "sale_date": "2026-06-01", "sale_type": "lien"}
    )
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 1
    assert auctions[0].county == "Duval"


async def test_fetch_skips_invalid_records(collector):
    data = [
        {"county": "Duval", "sale_date": "2026-06-01", "sale_type": "lien"},
        {"sale_date": "bad-date"},
        {"county": "Clay", "sale_date": "2026-06-15", "sale_type": "lien"},
    ]
    mock_client = AsyncMock()
    mock_client.scrape.return_value = mock_scrape_result(data)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 2


async def test_fetch_raises_when_all_keywords_fail():
    """Should raise ExtractionError only when ALL keywords fail normalization."""
    collector = MultiKeywordCollector()
    bad_data = [{"county": "", "sale_date": "bad"}, {"sale_date": "nope"}]
    mock_client = AsyncMock()
    mock_client.scrape.return_value = mock_scrape_result(bad_data)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        with pytest.raises(ExtractionError, match="all keywords failed"):
            await collector.collect()


async def test_fetch_continues_when_one_keyword_fails():
    """If one keyword's records all fail but another succeeds, should return results."""
    collector = MultiKeywordCollector()
    mock_client = AsyncMock()
    mock_client.scrape.side_effect = [
        mock_scrape_result([{"county": "", "sale_date": "bad"}]),
        mock_scrape_result(
            [{"county": "Clay", "sale_date": "2026-07-15", "sale_type": "lien"}]
        ),
    ]
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 1
    assert auctions[0].county == "Clay"


async def test_fetch_closes_client_on_failure(collector):
    """client.close() must be called even when scraping raises."""
    mock_client = AsyncMock()
    mock_client.scrape.side_effect = RuntimeError("network error")
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        with pytest.raises(RuntimeError, match="network error"):
            await collector.collect()

    mock_client.close.assert_called_once()
