"""Tests for Arkansas COSL collector."""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import ValidationError

from tdc_auction_calendar.collectors.state_agencies.arkansas import (
    ArkansasCollector,
    parse_catalog,
)
from tdc_auction_calendar.models.enums import SaleType, SourceType

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "state_agencies"


def _load_fixture() -> str:
    return (FIXTURES_DIR / "arkansas_cosl.html").read_text()


def _row_html(date_str: str, counties: list[str]) -> str:
    """Build a minimal COSL-style HTML row for testing."""
    county_divs = "\n".join(
        f'<div class="dropdown m-1">'
        f'<a class="btn btn-light dropdown-toggle" href="#">{c}</a></div>'
        for c in counties
    )
    return (
        f'<div class="row bg-white border p-2">'
        f'<div class="col-sm font-weight-bold">{date_str}</div>'
        f'<div class="col-sm"></div><div class="col-sm"></div>'
        f'<div class="col-sm">{county_divs}</div></div>'
    )


@pytest.fixture()
def collector():
    return ArkansasCollector()


# ── collector identity tests ─────────────────────────────────────────


def test_name(collector):
    assert collector.name == "arkansas_cosl"


def test_source_type(collector):
    assert collector.source_type == SourceType.STATE_AGENCY


# ── parse_catalog unit tests ──────────────────────────────────────────


def test_parse_catalog_basic():
    html = _row_html("7/28/2026 12:00 AM", ["GARLAND"])
    result = parse_catalog(html)
    assert result == [{"sale_date": "2026-07-28", "county": "Garland"}]


def test_parse_catalog_multi_county_date():
    html = _row_html("7/14/2026 12:00 AM", ["PRAIRIE", "LONOKE", "ARKANSAS"])
    result = parse_catalog(html)
    assert len(result) == 3
    assert all(r["sale_date"] == "2026-07-14" for r in result)
    assert [r["county"] for r in result] == ["Prairie", "Lonoke", "Arkansas"]


def test_parse_catalog_county_title_case():
    html = _row_html("8/19/2026 12:00 AM", ["ST FRANCIS", "HOT SPRING"])
    result = parse_catalog(html)
    assert [r["county"] for r in result] == ["St Francis", "Hot Spring"]


def test_parse_catalog_empty():
    assert parse_catalog("") == []
    assert parse_catalog("<div>no dates or counties here</div>") == []


def test_parse_catalog_date_format():
    """M/D/YYYY correctly converts to YYYY-MM-DD with zero-padded month/day."""
    html = _row_html("3/5/2026 11:00 AM", ["SEVIER"])
    result = parse_catalog(html)
    assert result[0]["sale_date"] == "2026-03-05"


def test_parse_catalog_counties_before_date_skipped():
    """Rows without a parseable date in col 0 are skipped."""
    html = (
        '<div class="row"><div class="col-sm">No date here</div>'
        '<div class="col-sm"><a class="dropdown-toggle" href="#">ORPHAN</a></div></div>'
        + _row_html("7/14/2026 12:00 AM", ["PRAIRIE"])
    )
    result = parse_catalog(html)
    assert len(result) == 1
    assert result[0]["county"] == "Prairie"


def test_parse_catalog_duplicate_county_different_dates():
    html = _row_html("3/5/2026 11:00 AM", ["SEVIER"]) + _row_html(
        "9/23/2026 12:00 AM", ["SEVIER"]
    )
    result = parse_catalog(html)
    assert len(result) == 2
    assert result[0] == {"sale_date": "2026-03-05", "county": "Sevier"}
    assert result[1] == {"sale_date": "2026-09-23", "county": "Sevier"}


def test_parse_catalog_full_fixture():
    """Fixture has 5 dates, 9 total county entries."""
    html = _load_fixture()
    result = parse_catalog(html)
    assert len(result) == 9
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
    assert auction.source_url == "https://cosl.org/Home/Contents"


def test_normalize_missing_county_raises(collector):
    with pytest.raises((ValidationError, ValueError, KeyError)):
        collector.normalize({"sale_date": "2026-06-10"})


def test_normalize_invalid_date_raises(collector):
    raw = {"county": "Pulaski", "sale_date": "not-a-date"}
    with pytest.raises((ValidationError, ValueError)):
        collector.normalize(raw)


# ── _fetch integration tests ─────────────────────────────────────────


def _mock_response(html: str) -> httpx.Response:
    return httpx.Response(200, text=html, request=httpx.Request("GET", _URL))


_URL = "https://cosl.org/Home/Contents"


async def test_fetch_returns_auctions(collector):
    fixture_html = _load_fixture()
    mock_resp = _mock_response(fixture_html)

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.arkansas.httpx.AsyncClient"
    ) as MockClient:
        instance = AsyncMock()
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        auctions = await collector.collect()

    assert len(auctions) == 9
    assert all(a.state == "AR" for a in auctions)
    assert all(a.source_type == SourceType.STATE_AGENCY for a in auctions)
    assert all(a.source_url == "https://cosl.org/Home/Contents" for a in auctions)


async def test_fetch_empty_html_returns_empty(collector):
    mock_resp = _mock_response("")

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.arkansas.httpx.AsyncClient"
    ) as MockClient:
        instance = AsyncMock()
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        auctions = await collector.collect()

    assert auctions == []


async def test_collect_dedup(collector):
    """Duplicate county+date pairs are deduplicated by BaseCollector."""
    html = _row_html("7/14/2026 12:00 AM", ["PRAIRIE", "PRAIRIE"])
    mock_resp = _mock_response(html)

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.arkansas.httpx.AsyncClient"
    ) as MockClient:
        instance = AsyncMock()
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        auctions = await collector.collect()

    assert len(auctions) == 1
