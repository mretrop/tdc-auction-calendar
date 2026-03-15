"""Tests for Purdue vendor collector."""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.collectors.vendors.purdue import (
    PurdueCollector,
    download_and_parse_pdf,
    extract_sale_date,
    parse_listing_markdown,
)
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor

# Sample markdown matching the structure from data/research/purdue.md
SAMPLE_MARKDOWN = """\
* BRAZORIA COUNTY
   * [Brazoria County](docs/taxdocs/sales/04-2026brazoriataxsale.pdf)
* FORT BEND COUNTY
   * [Ft Bend County Pct 2](docs/taxdocs/sales/04-2026ftbendpct2taxsale.pdf)
   * [Ft Bend County Pct 3](docs/taxdocs/sales/04-2026ftbendpct3taxsale.pdf)
* CALDWELL COUNTY
   * [Manufactured Home Sale - March 17, 2026 at 10:00 am](docs/taxdocs/sales/03-17-2025lulingmanufacturedhomesale.pdf)
"""


def test_parse_listing_extracts_counties_and_urls():
    results = parse_listing_markdown(SAMPLE_MARKDOWN)
    counties = [r[0] for r in results]
    assert "Brazoria" in counties
    assert "Fort Bend" in counties
    assert "Caldwell" in counties


def test_parse_listing_builds_full_urls():
    results = parse_listing_markdown(SAMPLE_MARKDOWN)
    urls = [r[1] for r in results]
    assert all(url.startswith("https://www.pbfcm.com/") for url in urls)


def test_parse_listing_multi_precinct_produces_multiple_entries():
    results = parse_listing_markdown(SAMPLE_MARKDOWN)
    fort_bend_entries = [r for r in results if r[0] == "Fort Bend"]
    assert len(fort_bend_entries) == 2


def test_parse_listing_empty_markdown():
    results = parse_listing_markdown("")
    assert results == []


def test_extract_date_with_sale_date_label():
    text = "NOTICE OF SALE\nSale Date: April 7, 2026\nLocation: County Courthouse"
    assert extract_sale_date(text) == date(2026, 4, 7)


def test_extract_date_with_date_of_sale_label():
    text = "Date of Sale: March 17, 2026 at 10:00 AM"
    assert extract_sale_date(text) == date(2026, 3, 17)


def test_extract_date_month_name_no_label():
    text = "Tax Foreclosure\nThe sale will be held on June 3, 2026"
    assert extract_sale_date(text) == date(2026, 6, 3)


def test_extract_date_numeric_format():
    text = "Sale scheduled for 04/07/2026 at the courthouse"
    assert extract_sale_date(text) == date(2026, 4, 7)


def test_extract_date_with_ordinal():
    text = "Sale Date: April 7th, 2026"
    assert extract_sale_date(text) == date(2026, 4, 7)


def test_extract_date_returns_none_when_no_date():
    text = "This PDF has no date information whatsoever."
    assert extract_sale_date(text) is None


async def test_download_and_parse_pdf_extracts_date(tmp_path):
    """Test PDF download + date extraction with a mocked httpx response and pypdf."""
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"%PDF-fake-content"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch(
        "tdc_auction_calendar.collectors.vendors.purdue.PdfReader"
    ) as mock_reader_cls:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Sale Date: April 7, 2026\nProperties:"
        mock_reader_cls.return_value.pages = [mock_page]

        result = await download_and_parse_pdf(
            mock_client, "https://www.pbfcm.com/docs/test.pdf", pdf_dir
        )

    assert result == date(2026, 4, 7)


async def test_download_and_parse_pdf_returns_none_on_http_error(tmp_path):
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()

    mock_response = MagicMock()
    mock_response.status_code = 404

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    result = await download_and_parse_pdf(
        mock_client, "https://www.pbfcm.com/docs/missing.pdf", pdf_dir
    )
    assert result is None


async def test_download_and_parse_pdf_uses_cache(tmp_path):
    """If PDF already exists and is fresh, don't re-download."""
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()

    cached = pdf_dir / "test.pdf"
    cached.write_bytes(b"%PDF-cached")

    mock_client = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.vendors.purdue.PdfReader"
    ) as mock_reader_cls:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Sale Date: June 1, 2026"
        mock_reader_cls.return_value.pages = [mock_page]

        result = await download_and_parse_pdf(
            mock_client, "https://www.pbfcm.com/docs/test.pdf", pdf_dir
        )

    mock_client.get.assert_not_called()
    assert result == date(2026, 6, 1)


@pytest.fixture()
def collector():
    return PurdueCollector()


def test_name(collector):
    assert collector.name == "purdue_vendor"


def test_source_type(collector):
    assert collector.source_type == SourceType.VENDOR


def test_normalize(collector):
    raw = {
        "county": "Brazoria",
        "date": "2026-04-07",
        "pdf_url": "https://www.pbfcm.com/docs/taxdocs/sales/04-2026brazoriataxsale.pdf",
    }
    auction = collector.normalize(raw)
    assert auction.state == "TX"
    assert auction.county == "Brazoria"
    assert auction.start_date == date(2026, 4, 7)
    assert auction.sale_type == SaleType.DEED
    assert auction.source_type == SourceType.VENDOR
    assert auction.confidence_score == 0.80
    assert auction.vendor == Vendor.PURDUE
    assert auction.source_url == raw["pdf_url"]


def test_normalize_missing_county_raises(collector):
    raw = {"date": "2026-04-07", "pdf_url": "https://example.com/test.pdf"}
    with pytest.raises((KeyError, ValueError, ValidationError)):
        collector.normalize(raw)


async def test_fetch_end_to_end(collector):
    """Full _fetch with mocked ScrapeClient and mocked PDF downloads."""
    markdown = """\
* BRAZORIA COUNTY
   * [Brazoria County](docs/taxdocs/sales/04-2026brazoriataxsale.pdf)
* DALLAS COUNTY
   * [Dallas County](docs/taxdocs/sales/04-2026dallastaxsale.pdf)
"""
    mock_scrape_client = AsyncMock()
    mock_scrape_client.scrape.return_value = ScrapeResult(
        fetch=FetchResult(
            url="https://www.pbfcm.com/taxsale.html",
            status_code=200,
            fetcher="cloudflare",
            markdown=markdown,
        ),
    )
    mock_scrape_client.close = AsyncMock()

    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_response.content = b"%PDF-fake"

    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(return_value=mock_http_response)
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.create_scrape_client",
            return_value=mock_scrape_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.httpx.AsyncClient",
            return_value=mock_http_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.PdfReader"
        ) as mock_reader_cls,
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.asyncio.sleep",
            new_callable=AsyncMock,
        ),
    ):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Sale Date: April 7, 2026"
        mock_reader_cls.return_value.pages = [mock_page]

        auctions = await collector._fetch()

    assert len(auctions) == 2
    assert all(a.state == "TX" for a in auctions)
    assert all(a.sale_type == SaleType.DEED for a in auctions)
    counties = {a.county for a in auctions}
    assert counties == {"Brazoria", "Dallas"}


async def test_fetch_skips_pdf_failures(collector):
    """If one PDF fails, other counties still produce records."""
    markdown = """\
* BRAZORIA COUNTY
   * [Brazoria County](docs/taxdocs/sales/04-2026brazoriataxsale.pdf)
* DALLAS COUNTY
   * [Dallas County](docs/taxdocs/sales/04-2026dallastaxsale.pdf)
"""
    mock_scrape_client = AsyncMock()
    mock_scrape_client.scrape.return_value = ScrapeResult(
        fetch=FetchResult(
            url="https://www.pbfcm.com/taxsale.html",
            status_code=200,
            fetcher="cloudflare",
            markdown=markdown,
        ),
    )
    mock_scrape_client.close = AsyncMock()

    success_response = MagicMock()
    success_response.status_code = 200
    success_response.content = b"%PDF-fake"

    fail_response = MagicMock()
    fail_response.status_code = 404

    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(side_effect=[success_response, fail_response])
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.create_scrape_client",
            return_value=mock_scrape_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.httpx.AsyncClient",
            return_value=mock_http_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.PdfReader"
        ) as mock_reader_cls,
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.asyncio.sleep",
            new_callable=AsyncMock,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue._is_cache_fresh",
            return_value=False,
        ),
    ):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Sale Date: April 7, 2026"
        mock_reader_cls.return_value.pages = [mock_page]

        auctions = await collector._fetch()

    assert len(auctions) == 1
    assert auctions[0].county == "Brazoria"


async def test_collect_deduplicates_same_date_precincts(collector):
    """Multi-precinct counties with same sale date collapse to one record via dedup."""
    markdown = """\
* FORT BEND COUNTY
   * [Ft Bend County Pct 2](docs/taxdocs/sales/04-2026ftbendpct2taxsale.pdf)
   * [Ft Bend County Pct 3](docs/taxdocs/sales/04-2026ftbendpct3taxsale.pdf)
"""
    mock_scrape_client = AsyncMock()
    mock_scrape_client.scrape.return_value = ScrapeResult(
        fetch=FetchResult(
            url="https://www.pbfcm.com/taxsale.html",
            status_code=200,
            fetcher="cloudflare",
            markdown=markdown,
        ),
    )
    mock_scrape_client.close = AsyncMock()

    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_response.content = b"%PDF-fake"

    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(return_value=mock_http_response)
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.create_scrape_client",
            return_value=mock_scrape_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.httpx.AsyncClient",
            return_value=mock_http_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.PdfReader"
        ) as mock_reader_cls,
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.asyncio.sleep",
            new_callable=AsyncMock,
        ),
    ):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Sale Date: April 7, 2026"
        mock_reader_cls.return_value.pages = [mock_page]

        # Use collect() (not _fetch()) to trigger dedup
        auctions = await collector.collect()

    # Two precincts, same county + date -> deduped to 1
    assert len(auctions) == 1
    assert auctions[0].county == "Fort Bend"


async def test_fetch_returns_empty_when_all_pdfs_fail(collector):
    """If every PDF fails, return empty list and log error."""
    markdown = """\
* BRAZORIA COUNTY
   * [Brazoria County](docs/taxdocs/sales/04-2026brazoriataxsale.pdf)
"""
    mock_scrape_client = AsyncMock()
    mock_scrape_client.scrape.return_value = ScrapeResult(
        fetch=FetchResult(
            url="https://www.pbfcm.com/taxsale.html",
            status_code=200,
            fetcher="cloudflare",
            markdown=markdown,
        ),
    )
    mock_scrape_client.close = AsyncMock()

    fail_response = MagicMock()
    fail_response.status_code = 404

    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(return_value=fail_response)
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.create_scrape_client",
            return_value=mock_scrape_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.httpx.AsyncClient",
            return_value=mock_http_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.asyncio.sleep",
            new_callable=AsyncMock,
        ),
    ):
        auctions = await collector._fetch()

    assert auctions == []
