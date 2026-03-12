"""South Carolina public notice collector — scpublicnotices.com."""

from __future__ import annotations

from tdc_auction_calendar.collectors.public_notices.base_notice import BaseNoticeCollector
from tdc_auction_calendar.collectors.public_notices.column_platform import ColumnPlatformMixin
from tdc_auction_calendar.models.enums import SaleType

_BASE_URL = "https://www.scpublicnotices.com"


class SouthCarolinaCollector(ColumnPlatformMixin, BaseNoticeCollector):
    """Collects SC tax deed sale notices from scpublicnotices.com."""

    state_code = "SC"
    default_sale_type = SaleType.DEED
    base_url = _BASE_URL
    search_keywords = ["delinquent tax", "tax sale"]

    @property
    def name(self) -> str:
        return "south_carolina_public_notice"

    def _build_search_url(self, keyword: str) -> str:
        return f"{_BASE_URL}/Search.aspx"
