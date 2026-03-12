"""Base collector for public notice sites."""

from __future__ import annotations

from abc import abstractmethod
from datetime import date

import structlog
from pydantic import BaseModel, ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping import ExtractionError, create_scrape_client
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType

logger = structlog.get_logger()


class NoticeRecord(BaseModel):
    """Schema for a single public notice auction record."""

    county: str
    sale_date: str
    sale_type: str = ""


class BaseNoticeCollector(BaseCollector):
    """Base class for public notice site collectors.

    Subclasses must set these class attributes:
        state_code:        Two-letter state abbreviation
        default_sale_type: Default SaleType for this state
        base_url:          The public notice site URL
        search_keywords:   Keywords to search for
        use_json_options:  True for Cloudflare json extraction, False for LLM schema extraction

    Subclasses must implement:
        name:                Property returning collector name
        _build_search_url(): Returns the URL to scrape for a given keyword
    """

    state_code: str
    default_sale_type: SaleType
    base_url: str
    search_keywords: list[str]
    use_json_options: bool = True
    confidence_score: float = 0.75

    _EXTRACTION_PROMPT = (
        "Extract all tax sale / tax lien sale / tax deed sale notices from this page. "
        "For each notice, extract: county name, sale date (ISO format YYYY-MM-DD), "
        "and sale type (lien, deed, or hybrid). "
        "Only include upcoming sales with concrete dates."
    )

    @property
    def source_type(self) -> SourceType:
        return SourceType.PUBLIC_NOTICE

    @abstractmethod
    def _build_search_url(self, keyword: str) -> str:
        """Build the search URL for a given keyword."""
        ...

    def _get_js_code(self, keyword: str) -> str | None:
        """Return JS code to execute on page. None by default (no form interaction)."""
        return None

    def _get_wait_for(self) -> str | None:
        """Return CSS selector to wait for after JS execution. None by default."""
        return None

    def normalize(self, raw: dict) -> Auction:
        """Convert a raw notice record dict into a validated Auction."""
        return Auction(
            state=self.state_code,
            county=raw["county"],
            start_date=date.fromisoformat(raw["sale_date"]),
            sale_type=SaleType(raw.get("sale_type", self.default_sale_type)),
            source_type=SourceType.PUBLIC_NOTICE,
            source_url=self.base_url,
            confidence_score=self.confidence_score,
        )

    async def _fetch(self) -> list[Auction]:
        client = create_scrape_client()
        try:
            all_auctions: list[Auction] = []
            for keyword in self.search_keywords:
                url = self._build_search_url(keyword)
                js_code = self._get_js_code(keyword)
                wait_for = self._get_wait_for()

                scrape_kwargs: dict = {}
                if self.use_json_options and js_code is None:
                    scrape_kwargs["json_options"] = {
                        "prompt": self._EXTRACTION_PROMPT,
                        "response_format": NoticeRecord.model_json_schema(),
                    }
                else:
                    scrape_kwargs["schema"] = NoticeRecord
                    if js_code is not None:
                        scrape_kwargs["js_code"] = js_code
                    if wait_for is not None:
                        scrape_kwargs["wait_for"] = wait_for

                result = await client.scrape(url, **scrape_kwargs)

                raw_records: list = (
                    result.data
                    if isinstance(result.data, list)
                    else ([result.data] if result.data is not None else [])
                )

                failure_count = 0
                today = date.today()
                for raw in raw_records:
                    try:
                        auction = self.normalize(raw)
                        if auction.start_date < today:
                            continue
                        all_auctions.append(auction)
                    except (KeyError, TypeError, ValueError, ValidationError) as exc:
                        failure_count += 1
                        logger.error(
                            "normalize_failed",
                            collector=self.name,
                            raw=raw,
                            error=str(exc),
                            error_type=type(exc).__name__,
                        )

                if failure_count:
                    logger.error(
                        "normalize_summary",
                        collector=self.name,
                        keyword=keyword,
                        total=len(raw_records),
                        succeeded=len(raw_records) - failure_count,
                        failed=failure_count,
                    )

                if raw_records and failure_count == len(raw_records):
                    raise ExtractionError(
                        f"{self.name}: all {len(raw_records)} records failed normalization"
                    )

            return all_auctions
        finally:
            await client.close()
