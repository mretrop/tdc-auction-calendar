"""Tests for file-based response cache."""

import json
import time

import pytest

from tdc_auction_calendar.collectors.scraping.cache import ResponseCache
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult


@pytest.fixture()
def cache(tmp_path):
    """ResponseCache using a temporary directory."""
    return ResponseCache(cache_dir=str(tmp_path), ttl=3600)


@pytest.fixture()
def sample_result():
    return FetchResult(
        url="https://example.com/auctions",
        status_code=200,
        fetcher="cloudflare",
        html="<h1>Auctions</h1>",
        markdown="# Auctions",
    )


async def test_cache_miss_returns_none(cache):
    """get() returns None for uncached URLs."""
    result = await cache.get("https://example.com", render_js=True)
    assert result is None


async def test_cache_put_then_get(cache, sample_result):
    """Cached result is returned on subsequent get()."""
    await cache.put("https://example.com", render_js=True, result=sample_result)
    cached = await cache.get("https://example.com", render_js=True)
    assert cached is not None
    assert cached.url == sample_result.url
    assert cached.html == sample_result.html


async def test_cache_different_render_js(cache, sample_result):
    """Different render_js values produce different cache keys."""
    await cache.put("https://example.com", render_js=True, result=sample_result)
    cached = await cache.get("https://example.com", render_js=False)
    assert cached is None


async def test_cache_expired_returns_none(tmp_path, sample_result):
    """Expired entries return None."""
    cache = ResponseCache(cache_dir=str(tmp_path), ttl=0)  # immediate expiry
    await cache.put("https://example.com", render_js=True, result=sample_result)
    # TTL=0 means already expired
    cached = await cache.get("https://example.com", render_js=True)
    assert cached is None
