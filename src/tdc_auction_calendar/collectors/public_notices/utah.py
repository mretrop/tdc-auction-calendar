"""Utah public notice collector — utahlegals.com."""

from __future__ import annotations

from tdc_auction_calendar.collectors.public_notices.base_notice import BaseNoticeCollector
from tdc_auction_calendar.collectors.public_notices.column_platform import ColumnPlatformMixin
from tdc_auction_calendar.models.enums import SaleType

_BASE_URL = "https://www.utahlegals.com"


class UtahCollector(ColumnPlatformMixin, BaseNoticeCollector):
    """Collects UT tax deed sale notices from utahlegals.com."""

    state_code = "UT"
    default_sale_type = SaleType.DEED
    base_url = _BASE_URL
    search_keywords = ["tax sale", "delinquent tax"]

    @property
    def name(self) -> str:
        return "utah_public_notice"
