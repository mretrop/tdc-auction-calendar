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
