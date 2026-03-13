"""North Carolina public notice collector — ncnotices.com."""

from __future__ import annotations

from tdc_auction_calendar.collectors.public_notices.base_notice import BaseNoticeCollector
from tdc_auction_calendar.collectors.public_notices.column_platform import ColumnPlatformMixin
from tdc_auction_calendar.models.enums import SaleType

_BASE_URL = "https://www.ncnotices.com"


class NorthCarolinaCollector(ColumnPlatformMixin, BaseNoticeCollector):
    """Collects NC tax deed sale notices from ncnotices.com."""

    state_code = "NC"
    default_sale_type = SaleType.DEED
    base_url = _BASE_URL
    search_keywords = ["tax deed sale", "delinquent tax"]

    @property
    def name(self) -> str:
        return "north_carolina_public_notice"
