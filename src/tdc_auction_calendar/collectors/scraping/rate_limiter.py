"""Per-domain rate limiter for scraping requests."""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Enforces a minimum delay between requests to the same domain."""

    def __init__(
        self,
        default_delay: float = 2.0,
        per_domain: dict[str, float] | None = None,
    ) -> None:
        self._default_delay = default_delay
        self._per_domain = per_domain or {}
        self._last_request: dict[str, float] = {}

    async def wait(self, domain: str) -> None:
        """Wait until the per-domain delay has elapsed since the last request."""
        delay = self._per_domain.get(domain, self._default_delay)
        last = self._last_request.get(domain)

        if last is not None:
            elapsed = time.monotonic() - last
            remaining = delay - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)

        self._last_request[domain] = time.monotonic()
