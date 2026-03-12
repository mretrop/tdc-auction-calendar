"""PageFetcher protocol and FetchResult model."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class FetchResult(BaseModel):
    """Result of fetching a single URL."""

    url: str
    html: str | None = None
    markdown: str | None = None
    status_code: int
    fetcher: str  # "cloudflare" or "crawl4ai"


class PageFetcher(Protocol):
    """Protocol for page-fetching backends."""

    async def fetch(self, url: str, *, render_js: bool = True) -> FetchResult: ...
