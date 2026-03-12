"""Florida public notice collector — floridapublicnotices.com."""

from __future__ import annotations

from urllib.parse import quote_plus

from tdc_auction_calendar.collectors.public_notices.base_notice import BaseNoticeCollector
from tdc_auction_calendar.models.enums import SaleType

_BASE_URL = "https://www.floridapublicnotices.com"


class FloridaCollector(BaseNoticeCollector):
    """Collects Florida tax lien sale notices from floridapublicnotices.com."""

    state_code = "FL"
    default_sale_type = SaleType.LIEN
    base_url = _BASE_URL
    search_keywords = ["tax lien sale", "tax deed sale", "delinquent tax"]
    use_json_options = True

    @property
    def name(self) -> str:
        return "florida_public_notice"

    def _build_search_url(self, keyword: str) -> str:
        return f"{_BASE_URL}/?search={quote_plus(keyword)}"
