# Bid4Assets Collector Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a collector that scrapes the Bid4Assets auction calendar page to extract tax sale dates across multiple states.

**Architecture:** Single collector `Bid4AssetsCollector` fetches the calendar page at `bid4assets.com/auctionCalendar` using Crawl4AI with UNDETECTED stealth (Akamai protection). BeautifulSoup parses the carousel HTML. Pagination via JS click on the "next" arrow to capture two 3-month windows (~6 months total).

**Tech Stack:** Python, BeautifulSoup, Crawl4AI (UNDETECTED stealth), Pydantic, pytest

**Spec:** `docs/superpowers/specs/2026-03-16-bid4assets-collector-design.md`

---

## Chunk 1: Parsing and Normalization

### Task 1: Date parsing helper

**Files:**
- Create: `src/tdc_auction_calendar/collectors/vendors/bid4assets.py`
- Test: `tests/collectors/vendors/test_bid4assets.py`

- [ ] **Step 1: Write failing tests for date parsing**

Create the test file with tests for the `parse_date_range` helper function. This function takes a month name (from the calendar column header) and a date range string like `"May 8th - 12th"`, and returns `(start_date, end_date)`.

```python
# tests/collectors/vendors/test_bid4assets.py
"""Tests for Bid4Assets vendor collector."""

from datetime import date

import pytest

from pydantic import ValidationError

from tdc_auction_calendar.collectors.vendors.bid4assets import parse_date_range
from tdc_auction_calendar.models.enums import SaleType


class TestParseDateRange:
    def test_multi_day_range(self):
        start, end = parse_date_range("May", "May 8th - 12th", 2026)
        assert start == date(2026, 5, 8)
        assert end == date(2026, 5, 12)

    def test_single_day_range(self):
        start, end = parse_date_range("April", "April 8th - 8th", 2026)
        assert start == date(2026, 4, 8)
        assert end is None

    def test_ordinal_suffixes(self):
        start, end = parse_date_range("May", "May 1st - 4th", 2026)
        assert start == date(2026, 5, 1)
        assert end == date(2026, 5, 4)

    def test_ordinal_nd(self):
        start, end = parse_date_range("April", "April 22nd - 22nd", 2026)
        assert start == date(2026, 4, 22)
        assert end is None

    def test_ordinal_rd(self):
        start, end = parse_date_range("May", "May 23rd - 27th", 2026)
        assert start == date(2026, 5, 23)
        assert end == date(2026, 5, 27)

    def test_date_range_without_month_prefix(self):
        """Some entries show just the date range without repeating the month."""
        start, end = parse_date_range("June", "June 5th - 8th", 2026)
        assert start == date(2026, 6, 5)
        assert end == date(2026, 6, 8)

    def test_cross_month_range(self):
        """Handle ranges where end day < start day (spans into next month)."""
        start, end = parse_date_range("March", "March 30th - 2nd", 2026)
        assert start == date(2026, 3, 30)
        assert end == date(2026, 4, 2)

    def test_invalid_date_range_returns_none(self):
        result = parse_date_range("August", "Tax Sale Dates to be announced soon for August", 2026)
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_bid4assets.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_date_range'`

- [ ] **Step 3: Implement `parse_date_range`**

```python
# src/tdc_auction_calendar/collectors/vendors/bid4assets.py
"""Bid4Assets vendor collector — tax sale auctions from bid4assets.com calendar."""

from __future__ import annotations

import re
from datetime import date

import structlog

from tdc_auction_calendar.models.enums import SaleType

logger = structlog.get_logger()

# Month name -> number
_MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

# Matches patterns like "May 8th - 12th", "April 22nd - 22nd"
_DATE_RANGE_RE = re.compile(
    r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)\s*-\s*(\d{1,2})(?:st|nd|rd|th)"
)


def parse_date_range(
    column_month: str, text: str, year: int
) -> tuple[date, date | None] | None:
    """Parse a date range string from the Bid4Assets calendar.

    Args:
        column_month: The month name from the column header (e.g., "May").
        text: The date range text (e.g., "May 8th - 12th").
        year: The calendar year.

    Returns:
        (start_date, end_date) tuple, or None if unparseable.
        end_date is None for single-day auctions (start == end).
    """
    m = _DATE_RANGE_RE.search(text)
    if m is None:
        return None

    month_name, start_day_str, end_day_str = m.group(1), m.group(2), m.group(3)
    month_num = _MONTHS.get(month_name)
    if month_num is None:
        return None

    start_day = int(start_day_str)
    end_day = int(end_day_str)

    try:
        start_date = date(year, month_num, start_day)
    except ValueError:
        return None

    if start_day == end_day:
        return start_date, None

    # Cross-month range: end day < start day means it spans into the next month
    if end_day < start_day:
        end_month = month_num + 1
        end_year = year
        if end_month > 12:
            end_month = 1
            end_year += 1
        try:
            end_date = date(end_year, end_month, end_day)
        except ValueError:
            return None
    else:
        try:
            end_date = date(year, month_num, end_day)
        except ValueError:
            return None

    return start_date, end_date
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_bid4assets.py::TestParseDateRange -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/bid4assets.py tests/collectors/vendors/test_bid4assets.py
git commit -m "feat(bid4assets): add date range parser for calendar entries"
```

---

### Task 2: Title parsing helper

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/bid4assets.py`
- Modify: `tests/collectors/vendors/test_bid4assets.py`

- [ ] **Step 1: Write failing tests for title parsing**

The `parse_title` function extracts county, state, and sale type from auction titles like `"Riverside County, CA Tax Defaulted Properties Auction"`.

Add to test file:

```python
from tdc_auction_calendar.collectors.vendors.bid4assets import parse_date_range, parse_title
from tdc_auction_calendar.models.enums import SaleType


class TestParseTitle:
    def test_standard_county(self):
        county, state, sale_type = parse_title(
            "Riverside County, CA Tax Defaulted Properties Auction"
        )
        assert county == "Riverside"
        assert state == "CA"
        assert sale_type == SaleType.DEED

    def test_tax_foreclosed(self):
        county, state, sale_type = parse_title(
            "Klickitat County, WA Tax Foreclosed Properties Auction"
        )
        assert county == "Klickitat"
        assert state == "WA"
        assert sale_type == SaleType.DEED

    def test_tax_title_surplus(self):
        county, state, sale_type = parse_title(
            "Klickitat County, WA Tax Title/Surplus Properties Auction"
        )
        assert county == "Klickitat"
        assert state == "WA"
        assert sale_type == SaleType.DEED

    def test_repository(self):
        county, state, sale_type = parse_title(
            "Monroe County, PA Repository May26"
        )
        assert county == "Monroe"
        assert state == "PA"
        assert sale_type == SaleType.DEED

    def test_tax_lien(self):
        county, state, sale_type = parse_title(
            "Essex County, NJ Tax Lien Certificate Sale"
        )
        assert county == "Essex"
        assert state == "NJ"
        assert sale_type == SaleType.LIEN

    def test_independent_city(self):
        county, state, sale_type = parse_title(
            "Carson City Tax Defaulted Properties Auctions"
        )
        assert county == "Carson City"
        assert state is None
        assert sale_type == SaleType.DEED

    def test_no_county_with_state(self):
        county, state, sale_type = parse_title(
            "Nye County, NV Tax Defaulted Properties Auction"
        )
        assert county == "Nye"
        assert state == "NV"

    def test_unknown_sale_type_defaults_to_deed(self):
        county, state, sale_type = parse_title(
            "Wayne County, MI Special Properties Auction"
        )
        assert county == "Wayne"
        assert state == "MI"
        assert sale_type == SaleType.DEED

    def test_unparseable_returns_none(self):
        result = parse_title("MonroePATaxApr26")
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_bid4assets.py::TestParseTitle -v`
Expected: FAIL — `ImportError: cannot import name 'parse_title'`

- [ ] **Step 3: Implement `parse_title`**

Add to `bid4assets.py`:

```python
# Matches: "County Name, ST ..." or "City Name ..." (no comma/state)
_TITLE_COUNTY_STATE_RE = re.compile(
    r"^(.+?)\s+County,\s*([A-Z]{2})\s+"
)
_TITLE_CITY_RE = re.compile(
    r"^(.+?)\s+Tax\s+"
)

_SALE_TYPE_MAP: dict[str, SaleType] = {
    "tax defaulted": SaleType.DEED,
    "tax foreclosed": SaleType.DEED,
    "tax title": SaleType.DEED,
    "tax title/surplus": SaleType.DEED,
    "repository": SaleType.DEED,
    "tax lien": SaleType.LIEN,
}


def parse_title(title: str) -> tuple[str, str | None, SaleType] | None:
    """Parse county, state, and sale type from an auction title.

    Returns:
        (county, state, sale_type) tuple, or None if unparseable.
        state may be None for independent cities.
    """
    title = title.strip()

    # Try "County Name, ST ..." pattern first
    m = _TITLE_COUNTY_STATE_RE.match(title)
    if m:
        county = m.group(1).strip()
        state = m.group(2)
    else:
        # Try independent city pattern: "City Name Tax ..."
        m = _TITLE_CITY_RE.match(title)
        if m:
            county = m.group(1).strip()
            state = None
        else:
            return None

    # Determine sale type from keywords in the title
    title_lower = title.lower()
    sale_type = SaleType.DEED  # default
    matched = False
    for keyword, st in _SALE_TYPE_MAP.items():
        if keyword in title_lower:
            sale_type = st
            matched = True
            break
    if not matched:
        logger.warning("bid4assets_unknown_sale_type", title=title)

    return county, state, sale_type
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_bid4assets.py::TestParseTitle -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/bid4assets.py tests/collectors/vendors/test_bid4assets.py
git commit -m "feat(bid4assets): add title parser for county/state/sale_type extraction"
```

---

### Task 3: HTML calendar parsing

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/bid4assets.py`
- Create: `tests/collectors/vendors/fixtures/bid4assets_calendar.html`
- Modify: `tests/collectors/vendors/test_bid4assets.py`

- [ ] **Step 1: Capture a sample HTML fixture**

Run the collector manually against the live Bid4Assets calendar to capture sample HTML. Save to `tests/collectors/vendors/fixtures/bid4assets_calendar.html`. This is a one-time manual step during development.

If live capture isn't possible, create a minimal fixture based on the observed calendar structure. The HTML structure needs to be discovered during implementation — inspect the actual page DOM to identify the CSS selectors for:
- Column headers (month names: "April", "May", "June")
- Auction entries (title text, date text, optional link)
- The carousel "next" button

Example minimal fixture (structure will be refined after inspecting real HTML):

```html
<div class="calendar-container">
  <div class="month-column">
    <h3>May</h3>
    <div class="auction-entry">
      <a href="/storefront/VenturaCountyMay26">
        <strong>Ventura County, CA Tax Defaulted Properties Auction</strong>
      </a>
      <div>May 8th - 12th</div>
    </div>
    <div class="auction-entry">
      <strong>Nye County, NV Tax Defaulted Properties Auction</strong>
      <div>May 1st - 4th</div>
    </div>
  </div>
</div>
```

**Note:** The actual CSS classes/structure MUST be discovered by inspecting the real page HTML. The fixture above is a placeholder. During implementation, use the browser dev tools or a Crawl4AI fetch to capture the real DOM structure, then update the fixture and selectors accordingly.

- [ ] **Step 2: Write failing tests for `parse_calendar_html`**

Add to test file:

```python
from pathlib import Path

from tdc_auction_calendar.collectors.vendors.bid4assets import (
    parse_calendar_html,
    parse_date_range,
    parse_title,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


class TestParseCalendarHtml:
    def test_extracts_auctions_from_fixture(self):
        html = _load("bid4assets_calendar.html")
        results = parse_calendar_html(html, year=2026)
        assert len(results) > 0

    def test_auction_entry_has_required_fields(self):
        html = _load("bid4assets_calendar.html")
        results = parse_calendar_html(html, year=2026)
        entry = results[0]
        assert "county" in entry
        assert "state" in entry
        assert "start_date" in entry
        assert "sale_type" in entry

    def test_skips_announced_entries(self):
        """Entries like 'Tax Sale Dates to be announced soon' should be skipped."""
        html = _load("bid4assets_calendar.html")
        results = parse_calendar_html(html, year=2026)
        for r in results:
            assert r["start_date"] is not None

    def test_empty_html(self):
        results = parse_calendar_html("", year=2026)
        assert results == []

    def test_captures_source_url(self):
        html = _load("bid4assets_calendar.html")
        results = parse_calendar_html(html, year=2026)
        linked = [r for r in results if r.get("source_url")]
        # Fixture should include at least one linked entry
        assert len(linked) >= 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_bid4assets.py::TestParseCalendarHtml -v`
Expected: FAIL — `ImportError: cannot import name 'parse_calendar_html'`

- [ ] **Step 4: Implement `parse_calendar_html`**

Add to `bid4assets.py`. **Important:** The CSS selectors below are placeholders. During implementation, inspect the real Bid4Assets calendar HTML to determine the actual DOM structure, and update the selectors accordingly.

```python
from bs4 import BeautifulSoup


def parse_calendar_html(html: str, *, year: int) -> list[dict]:
    """Parse the Bid4Assets auction calendar HTML into auction dicts.

    Returns list of dicts with keys: county, state, start_date, end_date,
    sale_type, source_url.

    NOTE: CSS selectors must be updated after inspecting real page HTML.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []

    # TODO: Replace these selectors after inspecting real HTML structure.
    # The calendar has month columns, each containing auction entries.
    # Discover the actual selectors by fetching the page and inspecting DOM.
    month_columns = soup.select(".month-column")  # PLACEHOLDER SELECTOR

    for column in month_columns:
        # Get month name from column header
        header = column.select_one("h3")  # PLACEHOLDER SELECTOR
        if header is None:
            continue
        month_name = header.get_text().strip()

        # Find auction entries within this month column
        entries = column.select(".auction-entry")  # PLACEHOLDER SELECTOR
        for entry in entries:
            # Get title text
            title_el = entry.select_one("strong")  # PLACEHOLDER SELECTOR
            if title_el is None:
                continue
            title_text = title_el.get_text().strip()

            # Parse title for county/state/sale_type
            parsed = parse_title(title_text)
            if parsed is None:
                logger.warning("bid4assets_unparseable_title", title=title_text)
                continue
            county, state, sale_type = parsed

            # Get date range text
            date_el = entry.select_one("div")  # PLACEHOLDER SELECTOR
            if date_el is None:
                continue
            date_text = date_el.get_text().strip()

            # Parse date range
            date_result = parse_date_range(month_name, date_text, year)
            if date_result is None:
                logger.info("bid4assets_skipped_entry", title=title_text, date_text=date_text)
                continue
            start_date, end_date = date_result

            # Get storefront link if present
            link = entry.select_one("a[href]")  # PLACEHOLDER SELECTOR
            source_url = None
            if link and link.get("href"):
                href = link["href"]
                if not href.startswith("http"):
                    href = f"https://www.bid4assets.com{href}"
                source_url = href

            # Skip entries without a state code (unless independent city is handled)
            if state is None:
                logger.info("bid4assets_no_state", county=county, title=title_text)

            results.append({
                "county": county,
                "state": state,
                "start_date": start_date,
                "end_date": end_date,
                "sale_type": sale_type,
                "source_url": source_url,
            })

    return results
```

- [ ] **Step 5: Update fixture to match real HTML, then run tests**

After inspecting the real page HTML (via browser dev tools or a test fetch), update:
1. The fixture file to contain real HTML structure
2. The CSS selectors in `parse_calendar_html` to match
3. Test assertions to match the actual data in the fixture

Run: `uv run pytest tests/collectors/vendors/test_bid4assets.py::TestParseCalendarHtml -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/bid4assets.py tests/collectors/vendors/test_bid4assets.py tests/collectors/vendors/fixtures/bid4assets_calendar.html
git commit -m "feat(bid4assets): add calendar HTML parser with BeautifulSoup"
```

---

## Chunk 2: Collector Class and Integration

### Task 4: Collector class with normalize

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/bid4assets.py`
- Modify: `tests/collectors/vendors/test_bid4assets.py`

- [ ] **Step 1: Write failing tests for normalize and collector properties**

Add to test file:

```python
from tdc_auction_calendar.collectors.vendors.bid4assets import Bid4AssetsCollector
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor


class TestBid4AssetsCollector:
    @pytest.fixture()
    def collector(self):
        return Bid4AssetsCollector()

    def test_name(self, collector):
        assert collector.name == "bid4assets"

    def test_source_type(self, collector):
        assert collector.source_type == SourceType.VENDOR

    def test_normalize_standard(self, collector):
        raw = {
            "state": "CA",
            "county": "Riverside",
            "start_date": date(2026, 4, 23),
            "end_date": date(2026, 4, 28),
            "sale_type": SaleType.DEED,
            "source_url": "https://www.bid4assets.com/storefront/RiversideCountyApr26",
        }
        auction = collector.normalize(raw)
        assert auction.state == "CA"
        assert auction.county == "Riverside"
        assert auction.start_date == date(2026, 4, 23)
        assert auction.end_date == date(2026, 4, 28)
        assert auction.sale_type == SaleType.DEED
        assert auction.source_type == SourceType.VENDOR
        assert auction.vendor == Vendor.BID4ASSETS
        assert auction.confidence_score == 0.85

    def test_normalize_single_day(self, collector):
        raw = {
            "state": "PA",
            "county": "Monroe",
            "start_date": date(2026, 4, 8),
            "end_date": None,
            "sale_type": SaleType.DEED,
            "source_url": None,
        }
        auction = collector.normalize(raw)
        assert auction.end_date is None
        assert auction.source_url == "https://www.bid4assets.com/auctionCalendar"

    def test_normalize_lien(self, collector):
        raw = {
            "state": "NJ",
            "county": "Essex",
            "start_date": date(2026, 5, 10),
            "end_date": date(2026, 5, 12),
            "sale_type": SaleType.LIEN,
            "source_url": None,
        }
        auction = collector.normalize(raw)
        assert auction.sale_type == SaleType.LIEN

    def test_normalize_missing_state_skipped(self, collector):
        """Entries with state=None should raise or be filtered."""
        raw = {
            "state": None,
            "county": "Carson City",
            "start_date": date(2026, 4, 22),
            "end_date": None,
            "sale_type": SaleType.DEED,
            "source_url": None,
        }
        with pytest.raises((ValueError, ValidationError)):
            collector.normalize(raw)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_bid4assets.py::TestBid4AssetsCollector -v`
Expected: FAIL — `ImportError: cannot import name 'Bid4AssetsCollector'`

- [ ] **Step 3: Implement `Bid4AssetsCollector`**

Add to `bid4assets.py`:

```python
from pydantic import ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping import create_scrape_client, StealthLevel
from tdc_auction_calendar.collectors.scraping.client import ScrapeError
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor

_CALENDAR_URL = "https://www.bid4assets.com/auctionCalendar"


class Bid4AssetsCollector(BaseCollector):
    """Collects tax sale auction dates from the Bid4Assets calendar page."""

    @property
    def name(self) -> str:
        return "bid4assets"

    @property
    def source_type(self) -> SourceType:
        return SourceType.VENDOR

    def normalize(self, raw: dict) -> Auction:
        return Auction(
            state=raw["state"],
            county=raw["county"],
            start_date=raw["start_date"],
            end_date=raw.get("end_date"),
            sale_type=raw["sale_type"],
            source_type=SourceType.VENDOR,
            source_url=raw.get("source_url") or _CALENDAR_URL,
            confidence_score=0.85,
            vendor=Vendor.BID4ASSETS,
        )

    async def _fetch(self) -> list[Auction]:
        # Placeholder — implemented in Task 5
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_bid4assets.py::TestBid4AssetsCollector -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/bid4assets.py tests/collectors/vendors/test_bid4assets.py
git commit -m "feat(bid4assets): add Bid4AssetsCollector class with normalize"
```

---

### Task 5: Implement `_fetch` method

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/bid4assets.py`
- Modify: `tests/collectors/vendors/test_bid4assets.py`

- [ ] **Step 1: Write failing tests for `_fetch`**

Add to test file:

```python
from unittest.mock import AsyncMock, patch

from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult


def _mock_scrape_result(html: str) -> ScrapeResult:
    return ScrapeResult(
        fetch=FetchResult(
            url=_CALENDAR_URL,
            status_code=200,
            fetcher="crawl4ai",
            html=html,
        ),
    )


_CALENDAR_URL = "https://www.bid4assets.com/auctionCalendar"


async def test_fetch_returns_auctions():
    html = _load("bid4assets_calendar.html")
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(html)
    mock_client.close = AsyncMock()

    collector = Bid4AssetsCollector()
    with patch(
        "tdc_auction_calendar.collectors.vendors.bid4assets.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) > 0
    assert all(a.vendor == Vendor.BID4ASSETS for a in auctions)
    assert all(a.source_type == SourceType.VENDOR for a in auctions)


async def test_fetch_empty_html_returns_empty():
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result("")
    mock_client.close = AsyncMock()

    collector = Bid4AssetsCollector()
    with patch(
        "tdc_auction_calendar.collectors.vendors.bid4assets.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert auctions == []


async def test_fetch_scrape_error_returns_empty():
    mock_client = AsyncMock()
    mock_client.scrape.side_effect = ScrapeError(
        url=_CALENDAR_URL, attempts=[{"error": "blocked"}]
    )
    mock_client.close = AsyncMock()

    collector = Bid4AssetsCollector()
    with patch(
        "tdc_auction_calendar.collectors.vendors.bid4assets.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert auctions == []


async def test_fetch_filters_none_state_entries():
    """Entries with no state (independent cities) should be skipped."""
    html = _load("bid4assets_calendar.html")
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(html)
    mock_client.close = AsyncMock()

    collector = Bid4AssetsCollector()
    with patch(
        "tdc_auction_calendar.collectors.vendors.bid4assets.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert all(a.state is not None for a in auctions)
    assert all(len(a.state) == 2 for a in auctions)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_bid4assets.py::test_fetch_returns_auctions -v`
Expected: FAIL — `_fetch` returns empty list (placeholder)

- [ ] **Step 3: Implement `_fetch`**

Replace the placeholder `_fetch` method in `Bid4AssetsCollector`:

```python
    async def _fetch(self) -> list[Auction]:
        client = create_scrape_client(stealth=StealthLevel.UNDETECTED)
        year = date.today().year

        try:
            # Fetch the initial calendar page (shows 3 months)
            try:
                result = await client.scrape(_CALENDAR_URL)
            except ScrapeError as exc:
                logger.error("bid4assets_fetch_failed", url=_CALENDAR_URL, error=str(exc))
                return []

            html = result.fetch.html or ""
            if not html:
                logger.warning("bid4assets_empty_html", url=_CALENDAR_URL)
                return []

            # Parse the calendar HTML
            entries = parse_calendar_html(html, year=year)

            # Try clicking "next" to get the next 3 months
            # TODO: Implement pagination via js_code after discovering the
            # next-button selector from real HTML. For now, single page fetch.

            # Normalize each entry, skip entries without a state code
            auctions: list[Auction] = []
            for entry in entries:
                if entry.get("state") is None:
                    logger.info(
                        "bid4assets_skipped_no_state",
                        county=entry.get("county"),
                    )
                    continue
                try:
                    auctions.append(self.normalize(entry))
                except (KeyError, TypeError, ValueError, ValidationError) as exc:
                    logger.error(
                        "bid4assets_normalize_failed",
                        entry=entry,
                        error=str(exc),
                    )

            logger.info(
                "bid4assets_fetch_complete",
                total_entries=len(entries),
                auctions=len(auctions),
                skipped=len(entries) - len(auctions),
            )
            return auctions
        finally:
            await client.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_bid4assets.py -k "test_fetch" -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/bid4assets.py tests/collectors/vendors/test_bid4assets.py
git commit -m "feat(bid4assets): implement _fetch with UNDETECTED stealth"
```

---

### Task 6: Register collector and update exports

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/__init__.py`
- Modify: `src/tdc_auction_calendar/collectors/orchestrator.py`

- [ ] **Step 1: Update `vendors/__init__.py`**

Add `Bid4AssetsCollector` to the exports:

```python
from tdc_auction_calendar.collectors.vendors.bid4assets import Bid4AssetsCollector
from tdc_auction_calendar.collectors.vendors.mvba import MVBACollector
from tdc_auction_calendar.collectors.vendors.purdue import PurdueCollector
from tdc_auction_calendar.collectors.vendors.realauction import RealAuctionCollector

__all__ = ["Bid4AssetsCollector", "MVBACollector", "PurdueCollector", "RealAuctionCollector"]
```

- [ ] **Step 2: Register in orchestrator**

Add import and dict entry in `orchestrator.py`:

In the import block, update:
```python
from tdc_auction_calendar.collectors.vendors import Bid4AssetsCollector, MVBACollector, PurdueCollector, RealAuctionCollector
```

In the `COLLECTORS` dict, add after `"realauction"`:
```python
    "bid4assets": Bid4AssetsCollector,
```

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 4: Verify CLI integration**

Run: `uv run tdc-auction-calendar collect --collectors bid4assets --help`
Expected: CLI accepts `bid4assets` as a valid collector name

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/__init__.py src/tdc_auction_calendar/collectors/orchestrator.py
git commit -m "feat(bid4assets): register collector in orchestrator and exports"
```

---

### Task 7: Live test and HTML fixture capture

**Files:**
- Modify: `tests/collectors/vendors/fixtures/bid4assets_calendar.html`
- Modify: `src/tdc_auction_calendar/collectors/vendors/bid4assets.py` (CSS selectors)
- Modify: `tests/collectors/vendors/test_bid4assets.py` (assertions)

This task is the integration step where you run the collector against the live site, discover the real HTML structure, and update everything accordingly.

- [ ] **Step 1: Test fetch against live site**

Run the collector against the live site to see if UNDETECTED stealth bypasses Akamai:

```bash
uv run python -c "
import asyncio
from tdc_auction_calendar.collectors.scraping import create_scrape_client, StealthLevel

async def test():
    client = create_scrape_client(stealth=StealthLevel.UNDETECTED)
    try:
        result = await client.scrape('https://www.bid4assets.com/auctionCalendar')
        print(f'Status: {result.fetch.status_code}')
        print(f'HTML length: {len(result.fetch.html or \"\")}')
        # Save HTML for fixture and inspection
        if result.fetch.html:
            with open('tests/collectors/vendors/fixtures/bid4assets_calendar.html', 'w') as f:
                f.write(result.fetch.html)
            print('Saved HTML fixture')
        else:
            print('No HTML returned')
    finally:
        await client.close()

asyncio.run(test())
"
```

- [ ] **Step 2: Inspect HTML and update CSS selectors**

Open the saved HTML file and identify the real CSS selectors for:
- Month column containers
- Month name headers
- Auction entry containers
- Title text elements
- Date text elements
- Storefront links

Update `parse_calendar_html()` with the real selectors.

- [ ] **Step 3: Update test assertions to match real data**

Update `TestParseCalendarHtml` assertions to match the actual number and content of auctions in the fixture.

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/collectors/vendors/test_bid4assets.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run collector via CLI**

```bash
uv run tdc-auction-calendar collect --collectors bid4assets -v
```

Expected: Auctions collected and displayed, or a clear "Akamai blocked" error if stealth doesn't work.

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/bid4assets.py tests/collectors/vendors/test_bid4assets.py tests/collectors/vendors/fixtures/bid4assets_calendar.html
git commit -m "feat(bid4assets): finalize CSS selectors and fixture from live HTML"
```
