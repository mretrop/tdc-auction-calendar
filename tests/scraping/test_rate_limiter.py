"""Tests for per-domain rate limiter."""

import asyncio
from unittest.mock import AsyncMock, patch

from tdc_auction_calendar.collectors.scraping.rate_limiter import RateLimiter


async def test_first_request_no_delay():
    """First request to a domain should not wait."""
    limiter = RateLimiter(default_delay=2.0)
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await limiter.wait("example.com")
        mock_sleep.assert_not_called()


async def test_second_request_waits():
    """Second request to same domain should wait for the delay."""
    limiter = RateLimiter(default_delay=1.0)
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await limiter.wait("example.com")
        # Simulate time passing by setting last_request to now
        await limiter.wait("example.com")
        mock_sleep.assert_called_once()
        delay = mock_sleep.call_args[0][0]
        assert 0.0 < delay <= 1.0


async def test_different_domains_independent():
    """Requests to different domains should not block each other."""
    limiter = RateLimiter(default_delay=2.0)
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await limiter.wait("example.com")
        await limiter.wait("other.com")
        mock_sleep.assert_not_called()


async def test_per_domain_override():
    """Per-domain delay overrides the default."""
    limiter = RateLimiter(default_delay=1.0, per_domain={"slow.com": 5.0})
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await limiter.wait("slow.com")
        await limiter.wait("slow.com")
        delay = mock_sleep.call_args[0][0]
        assert delay > 1.0  # uses 5.0s override, not 1.0s default
