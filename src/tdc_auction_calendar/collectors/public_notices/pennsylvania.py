"""Pennsylvania public notice collector — publicnoticepa.com."""

from __future__ import annotations

from tdc_auction_calendar.collectors.public_notices.base_notice import BaseNoticeCollector
from tdc_auction_calendar.collectors.public_notices.column_platform import ColumnPlatformMixin
from tdc_auction_calendar.models.enums import SaleType

_BASE_URL = "https://www.publicnoticepa.com"


class PennsylvaniaCollector(ColumnPlatformMixin, BaseNoticeCollector):
    """Collects PA tax deed sale notices from publicnoticepa.com."""

    state_code = "PA"
    default_sale_type = SaleType.DEED
    base_url = _BASE_URL
    search_keywords = ["tax sale", "delinquent tax"]

    @property
    def name(self) -> str:
        return "pennsylvania_public_notice"

    def _build_search_url(self, keyword: str) -> str:
        return f"{_BASE_URL}/Search.aspx"
