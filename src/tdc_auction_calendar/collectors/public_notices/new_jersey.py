"""New Jersey public notice collector — njpublicnotices.com."""

from __future__ import annotations

from tdc_auction_calendar.collectors.public_notices.base_notice import BaseNoticeCollector
from tdc_auction_calendar.collectors.public_notices.column_platform import ColumnPlatformMixin
from tdc_auction_calendar.models.enums import SaleType

_BASE_URL = "https://www.njpublicnotices.com"


class NewJerseyCollector(ColumnPlatformMixin, BaseNoticeCollector):
    """Collects NJ tax lien sale notices from njpublicnotices.com."""

    state_code = "NJ"
    default_sale_type = SaleType.LIEN
    base_url = _BASE_URL
    search_keywords = ["tax lien sale", "tax sale"]

    @property
    def name(self) -> str:
        return "new_jersey_public_notice"
