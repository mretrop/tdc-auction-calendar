"""Tests for ColumnPlatformMixin."""

from tdc_auction_calendar.collectors.public_notices.column_platform import ColumnPlatformMixin


class _FakeMixin(ColumnPlatformMixin):
    base_url = "https://www.example.com"


def test_get_js_code():
    """JS code should fill keyword field and trigger postback."""
    mixin = _FakeMixin()
    js = mixin._get_js_code("tax deed sale")
    assert "tax deed sale" in js
    assert "txtKeywords" in js
    assert "__doPostBack" in js


def test_get_js_code_escapes_quotes():
    """Single quotes in keywords should be escaped."""
    mixin = _FakeMixin()
    js = mixin._get_js_code("treasurer's sale")
    assert "treasurer\\'s sale" in js


def test_get_wait_for():
    """Should return the results container selector."""
    mixin = _FakeMixin()
    assert mixin._get_wait_for() == "#searchResults"


def test_build_search_url():
    """Should return base_url + /Search.aspx."""
    mixin = _FakeMixin()
    url = mixin._build_search_url("tax sale")
    assert url == "https://www.example.com/Search.aspx"
