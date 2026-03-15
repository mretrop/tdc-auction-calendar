"""Tests for Purdue vendor collector."""

from tdc_auction_calendar.collectors.vendors.purdue import parse_listing_markdown

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


from datetime import date
from tdc_auction_calendar.collectors.vendors.purdue import extract_sale_date


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


from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from tdc_auction_calendar.collectors.vendors.purdue import download_and_parse_pdf


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
