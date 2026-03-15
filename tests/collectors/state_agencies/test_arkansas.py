"""Tests for Arkansas COSL collector."""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from tdc_auction_calendar.collectors.state_agencies.arkansas import (
    ArkansasCollector,
    parse_catalog,
)
from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.models.enums import SaleType, SourceType

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "state_agencies"


def _load_fixture() -> str:
    return (FIXTURES_DIR / "arkansas_cosl.md").read_text()


@pytest.fixture()
def collector():
    return ArkansasCollector()


# ── collector identity tests ─────────────────────────────────────────


def test_name(collector):
    assert collector.name == "arkansas_state_agency"


def test_source_type(collector):
    assert collector.source_type == SourceType.STATE_AGENCY


# ── parse_catalog unit tests ──────────────────────────────────────────


def test_parse_catalog_basic():
    md = "7/28/2026 12:00 AM\n\n[ GARLAND](#)\n"
    result = parse_catalog(md)
    assert result == [{"sale_date": "2026-07-28", "county": "Garland"}]


def test_parse_catalog_multi_county_date():
    md = (
        "7/14/2026 12:00 AM\n\n"
        "[ PRAIRIE](#)\n\n"
        "[  View Catalog](https://example.com)\n\n"
        "[ LONOKE](#)\n\n"
        "[ ARKANSAS](#)\n"
    )
    result = parse_catalog(md)
    assert len(result) == 3
    assert all(r["sale_date"] == "2026-07-14" for r in result)
    assert [r["county"] for r in result] == ["Prairie", "Lonoke", "Arkansas"]


def test_parse_catalog_county_title_case():
    md = (
        "8/19/2026 12:00 AM\n\n"
        "[ ST FRANCIS](#)\n\n"
        "[ HOT SPRING](#)\n"
    )
    result = parse_catalog(md)
    assert [r["county"] for r in result] == ["St Francis", "Hot Spring"]


def test_parse_catalog_empty():
    assert parse_catalog("") == []
    assert parse_catalog("no dates or counties here") == []


def test_parse_catalog_date_format():
    """M/D/YYYY correctly converts to YYYY-MM-DD with zero-padded month/day."""
    md = "3/5/2026 11:00 AM\n\n[ SEVIER](#)\n"
    result = parse_catalog(md)
    assert result[0]["sale_date"] == "2026-03-05"


def test_parse_catalog_counties_before_date_skipped():
    md = "[ ORPHAN](#)\n\n7/14/2026 12:00 AM\n\n[ PRAIRIE](#)\n"
    result = parse_catalog(md)
    assert len(result) == 1
    assert result[0]["county"] == "Prairie"


def test_parse_catalog_duplicate_county_different_dates():
    md = (
        "3/5/2026 11:00 AM\n\n[ SEVIER](#)\n\n"
        "9/23/2026 12:00 AM\n\n[ SEVIER](#)\n"
    )
    result = parse_catalog(md)
    assert len(result) == 2
    assert result[0] == {"sale_date": "2026-03-05", "county": "Sevier"}
    assert result[1] == {"sale_date": "2026-09-23", "county": "Sevier"}


def test_parse_catalog_full_fixture():
    """Fixture has 5 dates, 9 total county entries."""
    md = _load_fixture()
    result = parse_catalog(md)
    assert len(result) == 9
    # Spot-check first and last
    assert result[0] == {"sale_date": "2026-03-05", "county": "Sevier"}
    assert result[-1] == {"sale_date": "2026-09-23", "county": "Sevier"}


# ── normalize tests ───────────────────────────────────────────────────


def test_normalize_valid_record(collector):
    raw = {"county": "Pulaski", "sale_date": "2026-06-10"}
    auction = collector.normalize(raw)
    assert auction.state == "AR"
    assert auction.county == "Pulaski"
    assert auction.start_date == date(2026, 6, 10)
    assert auction.sale_type == SaleType.DEED
    assert auction.source_type == SourceType.STATE_AGENCY
    assert auction.confidence_score == 0.85
    assert auction.source_url == "https://www.cosl.org/Home/Contents"


def test_normalize_missing_county_raises(collector):
    with pytest.raises((ValidationError, ValueError, KeyError)):
        collector.normalize({"sale_date": "2026-06-10"})


def test_normalize_invalid_date_raises(collector):
    raw = {"county": "Pulaski", "sale_date": "not-a-date"}
    with pytest.raises((ValidationError, ValueError)):
        collector.normalize(raw)


# ── _fetch integration tests ─────────────────────────────────────────


def _mock_scrape_result(markdown: str) -> ScrapeResult:
    return ScrapeResult(
        fetch=FetchResult(
            url="https://www.cosl.org/Home/Contents",
            status_code=200,
            fetcher="cloudflare",
            markdown=markdown,
        ),
    )


async def test_fetch_returns_auctions(collector):
    fixture_md = _load_fixture()
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(fixture_md)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.arkansas.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 9
    assert all(a.state == "AR" for a in auctions)
    assert all(a.source_type == SourceType.STATE_AGENCY for a in auctions)
    assert all(a.source_url == "https://www.cosl.org/Home/Contents" for a in auctions)


async def test_fetch_empty_markdown_returns_empty(collector):
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result("")
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.arkansas.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert auctions == []


async def test_collect_dedup(collector):
    """Duplicate county+date pairs are deduplicated."""
    md = "7/14/2026 12:00 AM\n\n[ PRAIRIE](#)\n\n[ PRAIRIE](#)\n"
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(md)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.arkansas.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 1
