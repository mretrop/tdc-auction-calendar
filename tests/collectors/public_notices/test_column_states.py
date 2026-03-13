"""Parametrized tests for all Column-platform state collectors.

Covers the common behavior shared by all Column-platform collectors:
name, source_type, normalize, fetch with fixtures, empty data handling,
JS code generation, and search URL.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tdc_auction_calendar.collectors.public_notices.minnesota import MinnesotaCollector
from tdc_auction_calendar.collectors.public_notices.new_jersey import NewJerseyCollector
from tdc_auction_calendar.collectors.public_notices.north_carolina import NorthCarolinaCollector
from tdc_auction_calendar.collectors.public_notices.pennsylvania import PennsylvaniaCollector
from tdc_auction_calendar.collectors.public_notices.south_carolina import SouthCarolinaCollector
from tdc_auction_calendar.collectors.public_notices.utah import UtahCollector
from tdc_auction_calendar.models.enums import SaleType, SourceType

from tests.collectors.public_notices.conftest import load_fixture, mock_scrape_result

_P = "cls,expected_name,state_code,default_sale_type,fixture_file,sample_county,sample_date,min_records"

COLUMN_COLLECTORS = [
    pytest.param(
        MinnesotaCollector, "minnesota_public_notice", "MN", SaleType.DEED,
        "minnesota_notices.json", "Hennepin", "2026-05-15", 5,
        id="minnesota",
    ),
    pytest.param(
        NewJerseyCollector, "new_jersey_public_notice", "NJ", SaleType.LIEN,
        "new_jersey_notices.json", "Essex", "2026-10-20", 5,
        id="new_jersey",
    ),
    pytest.param(
        NorthCarolinaCollector, "north_carolina_public_notice", "NC", SaleType.DEED,
        "north_carolina_notices.json", "Wake", "2026-07-10", 5,
        id="north_carolina",
    ),
    pytest.param(
        PennsylvaniaCollector, "pennsylvania_public_notice", "PA", SaleType.DEED,
        "pennsylvania_notices.json", "Philadelphia", "2026-09-22", 5,
        id="pennsylvania",
    ),
    pytest.param(
        SouthCarolinaCollector, "south_carolina_public_notice", "SC", SaleType.DEED,
        "south_carolina_notices.json", "Charleston", "2026-10-05", 5,
        id="south_carolina",
    ),
    pytest.param(
        UtahCollector, "utah_public_notice", "UT", SaleType.DEED,
        "utah_notices.json", "Salt Lake", "2026-05-22", 3,
        id="utah",
    ),
]


@pytest.mark.parametrize(_P, COLUMN_COLLECTORS)
def test_name(cls, expected_name, state_code, default_sale_type, fixture_file, sample_county, sample_date, min_records):
    assert cls().name == expected_name


@pytest.mark.parametrize(_P, COLUMN_COLLECTORS)
def test_source_type(cls, expected_name, state_code, default_sale_type, fixture_file, sample_county, sample_date, min_records):
    assert cls().source_type == SourceType.PUBLIC_NOTICE


@pytest.mark.parametrize(_P, COLUMN_COLLECTORS)
def test_normalize_valid_record(cls, expected_name, state_code, default_sale_type, fixture_file, sample_county, sample_date, min_records):
    raw = {"county": sample_county, "sale_date": sample_date, "sale_type": default_sale_type.value}
    auction = cls().normalize(raw)
    assert auction.state == state_code
    assert auction.county == sample_county
    assert auction.sale_type == default_sale_type
    assert auction.confidence_score == 0.75


@pytest.mark.parametrize(_P, COLUMN_COLLECTORS)
def test_uses_column_platform_js(cls, expected_name, state_code, default_sale_type, fixture_file, sample_county, sample_date, min_records):
    js = cls()._get_js_code("tax sale")
    assert js is not None
    assert "txtKeywords" in js
    assert "tax sale" in js


@pytest.mark.parametrize(_P, COLUMN_COLLECTORS)
def test_build_search_url(cls, expected_name, state_code, default_sale_type, fixture_file, sample_county, sample_date, min_records):
    collector = cls()
    url = collector._build_search_url("tax sale")
    assert "Search.aspx" in url
    assert collector.base_url in url


@pytest.mark.parametrize(_P, COLUMN_COLLECTORS)
async def test_fetch_returns_auctions(cls, expected_name, state_code, default_sale_type, fixture_file, sample_county, sample_date, min_records):
    fixture_data = load_fixture(fixture_file)
    mock_client = AsyncMock()
    mock_client.scrape.return_value = mock_scrape_result(fixture_data)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await cls().collect()

    assert len(auctions) >= min_records
    assert all(a.state == state_code for a in auctions)
    assert all(a.source_type == SourceType.PUBLIC_NOTICE for a in auctions)


@pytest.mark.parametrize(_P, COLUMN_COLLECTORS)
async def test_fetch_empty_data_returns_empty(cls, expected_name, state_code, default_sale_type, fixture_file, sample_county, sample_date, min_records):
    mock_client = AsyncMock()
    mock_client.scrape.return_value = mock_scrape_result(None)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.public_notices.base_notice.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await cls().collect()

    assert auctions == []
