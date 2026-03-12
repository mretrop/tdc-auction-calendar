"""Tests for ColumnPlatformMixin."""

from tdc_auction_calendar.collectors.public_notices.column_platform import ColumnPlatformMixin


def test_build_search_js():
    """JS code should fill keyword field and trigger postback."""
    mixin = ColumnPlatformMixin()
    js = mixin._build_search_js("tax deed sale")
    assert "tax deed sale" in js
    assert "txtKeywords" in js
    assert "__doPostBack" in js


def test_build_search_js_escapes_quotes():
    """Single quotes in keywords should be escaped."""
    mixin = ColumnPlatformMixin()
    js = mixin._build_search_js("treasurer's sale")
    assert "treasurer\\'s sale" in js


def test_get_wait_for():
    """Should return the results container selector."""
    mixin = ColumnPlatformMixin()
    assert mixin._get_wait_for() == "#searchResults"
