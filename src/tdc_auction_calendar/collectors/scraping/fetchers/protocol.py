"""PageFetcher protocol and FetchResult model."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class FetchResult(BaseModel):
    """Result of fetching a single URL."""

    model_config = {"frozen": True}

    url: str
    html: str | None = None
    markdown: str | None = None
    json_data: dict | list[dict] | None = None
    status_code: int = Field(ge=100, le=599)
    fetcher: str  # "cloudflare" or "crawl4ai"


class PageFetcher(Protocol):
    """Protocol for page-fetching backends."""

    async def fetch(
        self,
        url: str,
        *,
        render_js: bool = True,
        json_options: dict | None = None,
        js_code: str | None = None,
        wait_for: str | None = None,
    ) -> FetchResult: ...

    async def close(self) -> None: ...
