"""Tests for FetchResult model."""

from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult


def test_fetch_result_minimal():
    """FetchResult can be created with required fields only."""
    result = FetchResult(url="https://example.com", status_code=200, fetcher="cloudflare")
    assert result.url == "https://example.com"
    assert result.status_code == 200
    assert result.fetcher == "cloudflare"
    assert result.html is None
    assert result.markdown is None


def test_fetch_result_with_content():
    """FetchResult stores html and markdown content."""
    result = FetchResult(
        url="https://example.com",
        status_code=200,
        fetcher="crawl4ai",
        html="<h1>Auction</h1>",
        markdown="# Auction",
    )
    assert result.html == "<h1>Auction</h1>"
    assert result.markdown == "# Auction"


def test_fetch_result_serializes_to_dict():
    """FetchResult can be serialized for caching."""
    result = FetchResult(url="https://example.com", status_code=200, fetcher="cloudflare")
    data = result.model_dump()
    assert data["url"] == "https://example.com"
    restored = FetchResult.model_validate(data)
    assert restored == result
