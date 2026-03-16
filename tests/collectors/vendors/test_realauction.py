"""Tests for RealAuction vendor collector."""

from datetime import date
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


from tdc_auction_calendar.collectors.vendors.realauction import (
    calendar_url,
    parse_calendar_html,
    SITES,
)


def test_parse_extracts_four_auctions():
    html = _load("realauction_hillsborough_march.html")
    results = parse_calendar_html(html)
    assert len(results) == 4


def test_parse_extracts_dates():
    html = _load("realauction_hillsborough_march.html")
    results = parse_calendar_html(html)
    dates = [r["date"] for r in results]
    assert dates == [
        date(2026, 3, 5),
        date(2026, 3, 12),
        date(2026, 3, 19),
        date(2026, 3, 26),
    ]


def test_parse_extracts_sale_type():
    html = _load("realauction_hillsborough_march.html")
    results = parse_calendar_html(html)
    assert all(r["sale_type"] == "Tax Deed" for r in results)


def test_parse_extracts_property_count():
    html = _load("realauction_hillsborough_march.html")
    results = parse_calendar_html(html)
    counts = [r["property_count"] for r in results]
    assert counts == [13, 16, 10, 14]


def test_parse_extracts_time():
    html = _load("realauction_hillsborough_march.html")
    results = parse_calendar_html(html)
    assert all(r["time"] == "10:00 AM ET" for r in results)


def test_parse_empty_calendar():
    html = _load("realauction_apache_empty.html")
    results = parse_calendar_html(html)
    assert results == []


def test_parse_filters_foreclosure():
    html = _load("realauction_miamidade_mixed.html")
    results = parse_calendar_html(html)
    assert len(results) == 1
    assert results[0]["sale_type"] == "Tax Deed"
    assert results[0]["date"] == date(2026, 3, 19)
    assert results[0]["property_count"] == 55


def test_parse_treasurer_deed():
    html = '<div class="CALBOX CALW5 CALSELT" role="link" aria-label="April-15-2026" dayid="04/15/2026"><span class="CALNUM">15</span> <span class="CALTEXT">Treasurer Deed<br><span class="CALMSG"><span class="CALACT">0</span> / <span class="CALSCH">5</span> TD<br> </span><span class="CALTIME"> 10:00 AM MT</span></span></div>'
    results = parse_calendar_html(html)
    assert len(results) == 1
    assert results[0]["sale_type"] == "Treasurer Deed"
    assert results[0]["date"] == date(2026, 4, 15)


def test_parse_none_html():
    results = parse_calendar_html("")
    assert results == []


def test_calendar_url_builds_correct_url():
    url = calendar_url("https://hillsborough.realtaxdeed.com", 2026, 4)
    assert url == "https://hillsborough.realtaxdeed.com/index.cfm?zaction=user&zmethod=calendar&selCalDate={ts '2026-04-01 00:00:00'}"


def test_calendar_url_pads_month():
    url = calendar_url("https://apache.realtaxdeed.com", 2026, 3)
    assert "2026-03-01" in url


def test_calendar_url_current_month():
    url = calendar_url("https://hillsborough.realtaxdeed.com")
    assert url == "https://hillsborough.realtaxdeed.com/index.cfm?zaction=user&zmethod=calendar"


def test_registry_contains_florida_counties():
    fl_sites = [(s, c, u) for s, c, u in SITES if s == "FL"]
    assert len(fl_sites) >= 37
    counties = {c for _, c, _ in fl_sites}
    assert "Hillsborough" in counties
    assert "Miami-Dade" in counties
    assert "Alachua" in counties


def test_registry_contains_arizona_counties():
    az_sites = [(s, c, u) for s, c, u in SITES if s == "AZ"]
    assert len(az_sites) == 3
    counties = {c for _, c, _ in az_sites}
    assert counties == {"Apache", "Coconino", "Mohave"}


def test_registry_contains_colorado_counties():
    co_sites = [(s, c, u) for s, c, u in SITES if s == "CO"]
    assert len(co_sites) == 8
    assert all("treasurersdeedsale" in u for _, _, u in co_sites)


def test_registry_contains_nj():
    nj_sites = [(s, c, u) for s, c, u in SITES if s == "NJ"]
    assert len(nj_sites) == 2


def test_registry_total_sites():
    assert len(SITES) >= 57
