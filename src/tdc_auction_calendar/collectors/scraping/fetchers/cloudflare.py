"""Cloudflare Browser Rendering fetcher backend."""

from __future__ import annotations

import asyncio
import os

import httpx
import structlog

from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult

logger = structlog.get_logger()

_BASE_URL = "https://api.cloudflare.com/client/v4/accounts"
_POLL_INTERVAL = 2.0
_POLL_TIMEOUT = 90.0


class CloudflareFetchError(Exception):
    """Raised when a Cloudflare crawl job fails."""


class CloudflareFetcher:
    """Fetches pages via Cloudflare Browser Rendering /crawl API."""

    def __init__(
        self,
        account_id: str | None = None,
        api_token: str | None = None,
        connect_timeout: float = 30.0,
        read_timeout: float = 60.0,
    ) -> None:
        self._account_id = account_id or os.environ["CLOUDFLARE_ACCOUNT_ID"]
        self._api_token = api_token or os.environ["CLOUDFLARE_API_TOKEN"]
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=connect_timeout, read=read_timeout, write=30.0, pool=30.0),
            headers={"Authorization": f"Bearer {self._api_token}"},
        )

    @property
    def _crawl_url(self) -> str:
        return f"{_BASE_URL}/{self._account_id}/browser-rendering/crawl"

    async def fetch(self, url: str, *, render_js: bool = True) -> FetchResult:
        """Submit a crawl job and poll until complete."""
        logger.info("cloudflare_fetch_start", url=url, render_js=render_js)

        # POST to create job
        resp = await self._http.post(
            self._crawl_url,
            json={
                "url": url,
                "formats": ["markdown", "html"],
                "render": render_js,
                "limit": 1,
            },
        )
        if resp.status_code >= 400:
            raise CloudflareFetchError(
                f"Cloudflare API error {resp.status_code} on job creation"
            )
        job_id = resp.json()["id"]

        # Poll for completion
        elapsed = 0.0
        while elapsed < _POLL_TIMEOUT:
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL

            poll_resp = await self._http.get(f"{self._crawl_url}/{job_id}")
            if poll_resp.status_code >= 400:
                raise CloudflareFetchError(
                    f"Cloudflare API error {poll_resp.status_code} polling job {job_id}"
                )
            data = poll_resp.json()
            status = data["status"]

            if status == "running":
                continue
            if status == "completed":
                page = data["result"][0]
                status_code = page.get("metadata", {}).get("statusCode", 200)
                return FetchResult(
                    url=url,
                    html=page.get("html"),
                    markdown=page.get("markdown"),
                    status_code=status_code,
                    fetcher="cloudflare",
                )

            # errored, cancelled_*, etc.
            raise CloudflareFetchError(
                f"Cloudflare crawl job {job_id} failed with status: {status}"
            )

        raise CloudflareFetchError(
            f"Cloudflare crawl job {job_id} timed out after {_POLL_TIMEOUT}s"
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()
