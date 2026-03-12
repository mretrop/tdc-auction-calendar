"""Shared mixin for Column-platform ASP.NET public notice sites.

Sites: publicnoticepa.com, ncnotices.com, scpublicnotices.com,
       njpublicnotices.com, mnpublicnotice.com, utahlegals.com

All use the same ASP.NET PostBack search form with identical field names.
"""

from __future__ import annotations


class ColumnPlatformMixin:
    """Provides JS-based form interaction for Column-platform ASP.NET sites.

    Overrides _get_js_code(keyword) and _get_wait_for() from BaseNoticeCollector.
    Sets use_json_options = False to use LLM schema extraction (since Cloudflare
    can't execute js_code).
    """

    use_json_options: bool = False

    _KEYWORD_FIELD = "ctl00_ContentPlaceHolder1_as1_txtKeywords"
    _SEARCH_POSTBACK = "ctl00$ContentPlaceHolder1$as1$btnSearch"
    _RESULTS_SELECTOR = "#searchResults"

    def _build_search_js(self, keyword: str) -> str:
        """Generate JS to fill keyword field and submit ASP.NET PostBack form."""
        escaped = keyword.replace("'", "\\'")
        return (
            f"document.getElementById('{self._KEYWORD_FIELD}').value = '{escaped}';"
            f"__doPostBack('{self._SEARCH_POSTBACK}', '');"
        )

    def _get_js_code(self, keyword: str) -> str:
        """Return JS to submit keyword search on the Column platform."""
        return self._build_search_js(keyword)

    def _get_wait_for(self) -> str:
        return self._RESULTS_SELECTOR
