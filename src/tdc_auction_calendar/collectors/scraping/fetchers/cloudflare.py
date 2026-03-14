"""Cloudflare Browser Rendering fetcher backend."""

from __future__ import annotations

import asyncio
import os

import httpx
import structlog

from tdc_auction_calendar.collectors.scraping.client import PermanentFetchError
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult

logger = structlog.get_logger()

_BASE_URL = "https://api.cloudflare.com/client/v4/accounts"
_POLL_INTERVAL = 2.0
_POLL_TIMEOUT = 90.0


class CloudflareFetchError(RuntimeError):
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
        self._account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        self._api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN")
        if not self._account_id:
            raise ValueError("CLOUDFLARE_ACCOUNT_ID is required (pass account_id or set env var)")
        if not self._api_token:
            raise ValueError("CLOUDFLARE_API_TOKEN is required (pass api_token or set env var)")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=connect_timeout, read=read_timeout, write=30.0, pool=30.0),
            headers={"Authorization": f"Bearer {self._api_token}"},
        )

    @property
    def _crawl_url(self) -> str:
        return f"{_BASE_URL}/{self._account_id}/browser-rendering/crawl"

    @staticmethod
    def _build_post_body(url: str, render_js: bool, json_options: dict | None) -> dict:
        body: dict = {
            "url": url,
            "formats": ["markdown", "html"],
            "render": render_js,
            "limit": 1,
        }
        if json_options is not None:
            body["formats"].append("json")
            body["jsonOptions"] = json_options
        return body

    async def fetch(
        self,
        url: str,
        *,
        render_js: bool = True,
        json_options: dict | None = None,
        js_code: str | None = None,
        wait_for: str | None = None,
    ) -> FetchResult:
        """Submit a crawl job and poll until complete."""
        if js_code is not None or wait_for is not None:
            raise RuntimeError(
                f"Cloudflare fetcher does not support js_code/wait_for for {url}; "
                "requires Crawl4AI fallback"
            )
        logger.info("cloudflare_fetch_start", url=url, render_js=render_js)

        # POST to create job
        resp = await self._http.post(
            self._crawl_url,
            json=self._build_post_body(url, render_js, json_options),
        )
        if 400 <= resp.status_code < 500:
            raise PermanentFetchError(
                resp.status_code,
                f"Cloudflare API client error on job creation",
            )
        if resp.status_code >= 500:
            raise CloudflareFetchError(
                f"Cloudflare API server error {resp.status_code} on job creation"
            )
        try:
            body = resp.json()
        except ValueError as exc:
            raise CloudflareFetchError(
                f"Cloudflare returned non-JSON response for {url}: {exc}"
            ) from exc
        job_id = body.get("id") or body.get("result")
        if not job_id:
            raise CloudflareFetchError(f"Cloudflare API response missing 'id': {body}")

        # Poll for completion
        elapsed = 0.0
        while elapsed < _POLL_TIMEOUT:
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL

            poll_resp = await self._http.get(f"{self._crawl_url}/{job_id}")
            if 400 <= poll_resp.status_code < 500:
                raise PermanentFetchError(
                    poll_resp.status_code,
                    f"Cloudflare API client error polling job {job_id}",
                )
            if poll_resp.status_code >= 500:
                raise CloudflareFetchError(
                    f"Cloudflare API server error {poll_resp.status_code} polling job {job_id}"
                )
            try:
                data = poll_resp.json()
            except ValueError as exc:
                raise CloudflareFetchError(
                    f"Cloudflare returned non-JSON poll response for job {job_id}: {exc}"
                ) from exc
            status = data.get("status")
            if status is None:
                raise CloudflareFetchError(
                    f"Cloudflare API response missing 'status': {data}"
                )

            if status == "running":
                continue
            if status == "completed":
                results = data.get("result") or []
                if not results:
                    raise CloudflareFetchError(
                        f"Cloudflare job {job_id} completed but returned no results"
                    )
                page = results[0]
                metadata = page.get("metadata", {})
                status_code = metadata.get("statusCode")
                if status_code is None:
                    logger.warning(
                        "cloudflare_missing_status_code",
                        url=url,
                        job_id=job_id,
                        has_metadata=bool(metadata),
                    )
                    status_code = 200
                return FetchResult(
                    url=url,
                    html=page.get("html"),
                    markdown=page.get("markdown"),
                    json_data=page.get("json"),
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
