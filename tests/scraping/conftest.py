"""Shared fixtures for scraping tests."""

import pytest

from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult


@pytest.fixture()
def sample_fetch_result():
    """A valid FetchResult for test reuse."""
    return FetchResult(
        url="https://example.com/auctions",
        status_code=200,
        fetcher="cloudflare",
        html="<h1>Auctions</h1>",
        markdown="# Auctions",
    )
