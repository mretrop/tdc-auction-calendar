"""Minnesota public notice collector — mnpublicnotice.com."""

from __future__ import annotations

from tdc_auction_calendar.collectors.public_notices.base_notice import BaseNoticeCollector
from tdc_auction_calendar.collectors.public_notices.column_platform import ColumnPlatformMixin
from tdc_auction_calendar.models.enums import SaleType

_BASE_URL = "https://www.mnpublicnotice.com"


class MinnesotaCollector(ColumnPlatformMixin, BaseNoticeCollector):
    """Collects MN tax deed sale notices from mnpublicnotice.com."""

    state_code = "MN"
    default_sale_type = SaleType.DEED
    base_url = _BASE_URL
    search_keywords = ["tax deed sale", "delinquent tax"]

    @property
    def name(self) -> str:
        return "minnesota_public_notice"

    def _build_search_url(self, keyword: str) -> str:
        return f"{_BASE_URL}/Search.aspx"
