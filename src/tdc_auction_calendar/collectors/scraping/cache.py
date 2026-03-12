"""File-based response cache for scraping results."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import structlog

from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult

logger = structlog.get_logger()


class ResponseCache:
    """File-based cache for FetchResult objects."""

    def __init__(self, cache_dir: str = "data/cache", ttl: int = 21600) -> None:
        self._cache_dir = Path(cache_dir)
        self._ttl = ttl
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, url: str, render_js: bool) -> str:
        raw = f"{url}:{render_js}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    async def get(self, url: str, render_js: bool) -> FetchResult | None:
        """Return cached FetchResult if present and not expired, else None."""
        key = self._cache_key(url, render_js)
        path = self._cache_path(key)

        if not path.exists():
            logger.debug("cache_miss", url=url, reason="not_found")
            return None

        try:
            data = json.loads(path.read_text())
            if time.time() >= data["expires_at"]:
                logger.debug("cache_miss", url=url, reason="expired")
                path.unlink(missing_ok=True)
                return None

            logger.debug("cache_hit", url=url)
            return FetchResult.model_validate(data["result"])
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("cache_corrupted", url=url, path=str(path), error=str(exc))
            path.unlink(missing_ok=True)
            return None

    async def put(self, url: str, render_js: bool, result: FetchResult) -> None:
        """Write FetchResult to cache with expiry metadata."""
        key = self._cache_key(url, render_js)
        path = self._cache_path(key)

        try:
            data = {
                "expires_at": time.time() + self._ttl,
                "result": result.model_dump(),
            }
            path.write_text(json.dumps(data))
            logger.debug("cache_write", url=url, ttl=self._ttl)
        except OSError as exc:
            logger.warning("cache_write_failed", url=url, path=str(path), error=str(exc))
