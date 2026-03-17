# PublicSurplus Collector Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a collector that scrapes PublicSurplus.com Tax Sale and Lien category pages, fetches auction detail pages for dates, and normalizes results into Auction models.

**Architecture:** Two-pass httpx + BeautifulSoup collector following the Bid4Assets pattern. Pass 1 scrapes paginated category listings to discover auctions (ID, state, title, end date from JS). Pass 2 fetches individual detail pages for start dates. Subclasses BaseCollector, bypasses ScrapeClient.

**Tech Stack:** httpx, BeautifulSoup, asyncio (Semaphore), Pydantic, pytest

**Spec:** `docs/superpowers/specs/2026-03-16-publicsurplus-collector-design.md`

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/tdc_auction_calendar/collectors/vendors/publicsurplus.py` | Collector: list page parsing, detail page parsing, county extraction, normalization, fetch orchestration |
| Modify | `src/tdc_auction_calendar/models/enums.py:33-40` | Add `PUBLIC_SURPLUS` to `Vendor` enum |
| Modify | `src/tdc_auction_calendar/collectors/vendors/__init__.py` | Export `PublicSurplusCollector` |
| Create | `tests/collectors/vendors/test_publicsurplus.py` | All unit tests |
| Create | `tests/collectors/vendors/fixtures/publicsurplus_listing.html` | Fixture: category listing page HTML |
| Create | `tests/collectors/vendors/fixtures/publicsurplus_detail.html` | Fixture: auction detail page HTML |

---

## Chunk 1: Enum + County Extraction + List Page Parsing

### Task 1: Add PUBLIC_SURPLUS to Vendor enum

**Files:**
- Modify: `src/tdc_auction_calendar/models/enums.py:33-40`

- [ ] **Step 1: Add the enum value**

In `src/tdc_auction_calendar/models/enums.py`, add to the `Vendor` class after the `MVBA` entry:

```python
    PUBLIC_SURPLUS = "PublicSurplus"
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `uv run pytest tests/models/ -v --timeout=10`
Expected: All pass (no existing tests depend on Vendor enum length)

- [ ] **Step 3: Commit**

```bash
git add src/tdc_auction_calendar/models/enums.py
git commit -m "feat: add PUBLIC_SURPLUS to Vendor enum (#57)"
```

---

### Task 2: County extraction helper

**Files:**
- Create: `src/tdc_auction_calendar/collectors/vendors/publicsurplus.py`
- Create: `tests/collectors/vendors/test_publicsurplus.py`

- [ ] **Step 1: Write failing tests for county extraction**

Create `tests/collectors/vendors/test_publicsurplus.py`:

```python
# tests/collectors/vendors/test_publicsurplus.py
"""Tests for PublicSurplus vendor collector."""

from tdc_auction_calendar.collectors.vendors.publicsurplus import extract_county


class TestExtractCounty:
    def test_county_in_title(self):
        assert extract_county("Tract 4: Norman County Tax-Forfeiture Parcels") == "Norman"

    def test_multi_word_county(self):
        assert extract_county("St Louis County Tax-Forfeiture Parcel") == "St Louis"

    def test_mohave_county_land_sale(self):
        assert extract_county("Mohave County Land Sale - Former Animal Shelter") == "Mohave"

    def test_no_county_returns_various(self):
        assert extract_county("Parcel 2 PIN#26-345-0510") == "Various"

    def test_forfeiture_minimum_bid(self):
        assert extract_county("2025 Forfeiture Minimum Bid Sale: 25-5311-25765") == "Various"

    def test_empty_string(self):
        assert extract_county("") == "Various"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_publicsurplus.py -v`
Expected: FAIL with ImportError (module doesn't exist yet)

- [ ] **Step 3: Write minimal implementation**

Create `src/tdc_auction_calendar/collectors/vendors/publicsurplus.py`:

```python
# src/tdc_auction_calendar/collectors/vendors/publicsurplus.py
"""PublicSurplus vendor collector — tax sale and lien auctions from publicsurplus.com."""

from __future__ import annotations

import re

_COUNTY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+County\b")


def extract_county(title: str) -> str:
    """Extract county name from an auction title, or 'Various' if not found."""
    m = _COUNTY_RE.search(title)
    return m.group(1) if m else "Various"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_publicsurplus.py::TestExtractCounty -v`
Expected: All 6 pass

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/publicsurplus.py tests/collectors/vendors/test_publicsurplus.py
git commit -m "feat(publicsurplus): add county extraction helper (#57)"
```

---

### Task 3: US state filter constant

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/publicsurplus.py`
- Modify: `tests/collectors/vendors/test_publicsurplus.py`

- [ ] **Step 1: Write failing test**

Add to `tests/collectors/vendors/test_publicsurplus.py`:

```python
from tdc_auction_calendar.collectors.vendors.publicsurplus import US_STATES


class TestUsStates:
    def test_contains_all_50_states_plus_dc(self):
        assert len(US_STATES) == 51  # 50 states + DC

    def test_mn_is_included(self):
        assert "MN" in US_STATES

    def test_canadian_province_excluded(self):
        assert "AB" not in US_STATES
        assert "ON" not in US_STATES
        assert "BC" not in US_STATES
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/collectors/vendors/test_publicsurplus.py::TestUsStates -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Add US_STATES constant**

Add to `src/tdc_auction_calendar/collectors/vendors/publicsurplus.py` after the imports:

```python
US_STATES: frozenset[str] = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL",
    "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
})
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/collectors/vendors/test_publicsurplus.py::TestUsStates -v`
Expected: All 3 pass

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/publicsurplus.py tests/collectors/vendors/test_publicsurplus.py
git commit -m "feat(publicsurplus): add US states constant (#57)"
```

---

### Task 4: List page HTML parsing

**Files:**
- Create: `tests/collectors/vendors/fixtures/publicsurplus_listing.html`
- Modify: `src/tdc_auction_calendar/collectors/vendors/publicsurplus.py`
- Modify: `tests/collectors/vendors/test_publicsurplus.py`

- [ ] **Step 1: Create listing HTML fixture**

Create `tests/collectors/vendors/fixtures/publicsurplus_listing.html`. Extract a minimal fixture from `data/research/sub/publicsurplus_recrawl.html` — include just the `<section id="auctionsListContainer">` with 3 auction items: one MN tax-forfeiture (Norman County), one AZ land sale, and one with no county in title. Include the `updateTimeLeftSpan` script blocks. Also include pagination markup to test page detection.

The fixture should include these 3 items from the research HTML:
- Auction 3860102: "Tract 4: Norman County Tax-Forfeiture Parcels 27-2506000 & 27-2507000" (MN, has county)
- Auction 3944053: "Mohave County Land Sale - Former Animal Shelter" (AZ, has county)
- Auction 3947401: "Parcel 2 PIN#26-345-0510" (MN, no county)

Wrap them in the container structure:

```html
<div class="mb-2 auction-items__container" id="auction_item">
  <section class="w-100 ps-card-feat" id="auctionsListContainer">

    <div class="auction-item" id="3860102catGrid">
      <div class="auction-item-img">
        <a href="/sms/auction/view?auc=3860102"></a>
        <span class="auction-item-state">
          MN
        </span>
      </div>
      <div class="auction-item-body px-0">
        <h6 class="w-100 card-title ps-card-feat__body--title ps-1 mb-2">
          <a href="/sms/auction/view?auc=3860102" title="#3860102 - Tract 4: Norman County Tax-Forfeiture Parcels 27-2506000 &amp; 27-2507000">
            #3860102 - Tract 4: Norman County Tax-Forfeiture...
          </a>
        </h6>
        <div class="w-100 ps-card__body--children px-1">
          <div class="fw-bold">
            <script>
              updateTimeLeftSpan(timeLeftInfoMap, 3860102, "3860102catGrid",
                1773711883006, 1773882000000, 0, "",
                "", "catList" , timeLeftCallback);
            </script>
          </div>
        </div>
      </div>
    </div>

    <div class="auction-item" id="3944053catGrid">
      <div class="auction-item-img">
        <a href="/sms/auction/view?auc=3944053"></a>
        <span class="auction-item-state">
          AZ
        </span>
      </div>
      <div class="auction-item-body px-0">
        <h6 class="w-100 card-title ps-card-feat__body--title ps-1 mb-2">
          <a href="/sms/auction/view?auc=3944053" title="#3944053 - Mohave County Land Sale - Former Animal Shelter">
            #3944053 - Mohave County Land Sale - Former Anim...
          </a>
        </h6>
        <div class="w-100 ps-card__body--children px-1">
          <div class="fw-bold">
            <script>
              updateTimeLeftSpan(timeLeftInfoMap, 3944053, "3944053catGrid",
                1773711883006, 1773970800000, 0, "",
                "", "catList" , timeLeftCallback);
            </script>
          </div>
        </div>
      </div>
    </div>

    <div class="auction-item" id="3947401catGrid">
      <div class="auction-item-img">
        <a href="/sms/auction/view?auc=3947401"></a>
        <span class="auction-item-state">
          MN
        </span>
      </div>
      <div class="auction-item-body px-0">
        <h6 class="w-100 card-title ps-card-feat__body--title ps-1 mb-2">
          <a href="/sms/auction/view?auc=3947401" title="#3947401 - Parcel 2 PIN#26-345-0510">
            #3947401 - Parcel 2 PIN#26-345-0510
          </a>
        </h6>
        <div class="w-100 ps-card__body--children px-1">
          <div class="fw-bold">
            <script>
              updateTimeLeftSpan(timeLeftInfoMap, 3947401, "3947401catGrid",
                1773711883006, 1774195200000, 0, "",
                "", "catList" , timeLeftCallback);
            </script>
          </div>
        </div>
      </div>
    </div>

  </section>
</div>
```

- [ ] **Step 2: Write failing tests for list page parser**

Add to `tests/collectors/vendors/test_publicsurplus.py`:

```python
from datetime import date, timezone, datetime
from pathlib import Path

from tdc_auction_calendar.collectors.vendors.publicsurplus import (
    extract_county,
    parse_listing_html,
    US_STATES,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


class TestParseListingHtml:
    def test_extracts_three_auctions(self):
        html = _load("publicsurplus_listing.html")
        results = parse_listing_html(html)
        assert len(results) == 3

    def test_auction_fields(self):
        html = _load("publicsurplus_listing.html")
        results = parse_listing_html(html)
        first = results[0]
        assert first["auction_id"] == "3860102"
        assert first["state"] == "MN"
        assert "Norman County" in first["title"]
        assert first["source_url"] == "https://www.publicsurplus.com/sms/auction/view?auc=3860102"

    def test_extracts_end_date_from_js(self):
        html = _load("publicsurplus_listing.html")
        results = parse_listing_html(html)
        first = results[0]
        # 1773882000000 ms = 2026-03-19 01:00:00 UTC = 2026-03-19
        assert first["end_date"] == date(2026, 3, 19)

    def test_state_is_stripped(self):
        html = _load("publicsurplus_listing.html")
        results = parse_listing_html(html)
        for r in results:
            assert r["state"] == r["state"].strip()
            assert len(r["state"]) == 2

    def test_empty_html(self):
        assert parse_listing_html("") == []
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/collectors/vendors/test_publicsurplus.py::TestParseListingHtml -v`
Expected: FAIL with ImportError

- [ ] **Step 4: Implement parse_listing_html**

Add to `src/tdc_auction_calendar/collectors/vendors/publicsurplus.py`:

```python
from datetime import date, datetime, timezone

import structlog
from bs4 import BeautifulSoup

logger = structlog.get_logger()

_BASE_URL = "https://www.publicsurplus.com"

# Extracts auction ID and end epoch ms from updateTimeLeftSpan JS call
_TIME_LEFT_RE = re.compile(
    r"updateTimeLeftSpan\([^,]+,\s*(\d+),\s*\"[^\"]+\",\s*\d+,\s*(\d+)"
)


def parse_listing_html(html: str) -> list[dict]:
    """Parse a PublicSurplus category listing page into auction dicts.

    Returns list of dicts with keys: auction_id, state, title, source_url, end_date.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []

    # Build a map of auction_id -> end_date from JS calls
    end_dates: dict[str, date] = {}
    for script in soup.find_all("script"):
        text = script.string or ""
        for m in _TIME_LEFT_RE.finditer(text):
            auc_id = m.group(1)
            end_epoch_ms = int(m.group(2))
            end_dt = datetime.fromtimestamp(end_epoch_ms / 1000, tz=timezone.utc)
            end_dates[auc_id] = end_dt.date()

    for item in soup.select("div.auction-item"):
        item_id = item.get("id", "")
        auction_id = item_id.replace("catGrid", "") if item_id.endswith("catGrid") else None
        if not auction_id:
            continue

        # State
        state_el = item.select_one("span.auction-item-state")
        if state_el is None:
            continue
        state = state_el.get_text().strip()

        # Title (full, from title attribute)
        title_link = item.select_one("h6.card-title a")
        if title_link is None:
            continue
        title = title_link.get("title", title_link.get_text()).strip()
        # Strip leading "#ID - " prefix
        if title.startswith("#"):
            dash_pos = title.find(" - ")
            if dash_pos != -1:
                title = title[dash_pos + 3:]

        source_url = f"{_BASE_URL}/sms/auction/view?auc={auction_id}"
        end_date = end_dates.get(auction_id)

        results.append({
            "auction_id": auction_id,
            "state": state,
            "title": title,
            "source_url": source_url,
            "end_date": end_date,
        })

    return results
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/collectors/vendors/test_publicsurplus.py::TestParseListingHtml -v`
Expected: All 5 pass

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/publicsurplus.py tests/collectors/vendors/test_publicsurplus.py tests/collectors/vendors/fixtures/publicsurplus_listing.html
git commit -m "feat(publicsurplus): add list page parser with JS end-date extraction (#57)"
```

---

### Task 4b: Direct JS timestamp regex tests

**Files:**
- Modify: `tests/collectors/vendors/test_publicsurplus.py`

- [ ] **Step 1: Write tests for _TIME_LEFT_RE regex edge cases**

Add to `tests/collectors/vendors/test_publicsurplus.py`:

```python
from tdc_auction_calendar.collectors.vendors.publicsurplus import _TIME_LEFT_RE


class TestTimeLeftRegex:
    def test_standard_js_call(self):
        js = 'updateTimeLeftSpan(timeLeftInfoMap, 3860102, "3860102catGrid", 1773711883006, 1773882000000, 0, "", "", "catList", timeLeftCallback);'
        m = _TIME_LEFT_RE.search(js)
        assert m is not None
        assert m.group(1) == "3860102"
        assert m.group(2) == "1773882000000"

    def test_extra_whitespace(self):
        js = 'updateTimeLeftSpan( timeLeftInfoMap ,  3860102 ,  "3860102catGrid" ,  1773711883006 ,  1773882000000 , 0, "", "", "catList", timeLeftCallback);'
        m = _TIME_LEFT_RE.search(js)
        assert m is not None
        assert m.group(1) == "3860102"

    def test_no_match_on_unrelated_js(self):
        js = 'console.log("hello world");'
        assert _TIME_LEFT_RE.search(js) is None

    def test_multiline_js_call(self):
        js = """updateTimeLeftSpan(timeLeftInfoMap, 3946030, "3946030catGrid",
            1773711883006, 1773846000000, 0, "",
            "", "catList" , timeLeftCallback);"""
        m = _TIME_LEFT_RE.search(js)
        assert m is not None
        assert m.group(1) == "3946030"
        assert m.group(2) == "1773846000000"
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/collectors/vendors/test_publicsurplus.py::TestTimeLeftRegex -v`
Expected: All 4 pass

- [ ] **Step 3: Commit**

```bash
git add tests/collectors/vendors/test_publicsurplus.py
git commit -m "test(publicsurplus): add direct JS timestamp regex tests (#57)"
```

---

## Chunk 2: Detail Page Discovery + Collector Class

### Task 5: Fetch and save a detail page fixture (discovery task)

**Files:**
- Create: `tests/collectors/vendors/fixtures/publicsurplus_detail.html`

This is a discovery step — we need to see what the detail page looks like before writing the parser.

- [ ] **Step 1: Fetch a sample detail page**

Run a quick script to fetch a detail page and save it as a fixture. Use an auction ID from our research data:

```bash
uv run python -c "
import httpx
resp = httpx.get(
    'https://www.publicsurplus.com/sms/auction/view?auc=3860102',
    headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'},
    follow_redirects=True,
    timeout=30.0,
)
print(f'Status: {resp.status_code}, Length: {len(resp.text)}')
with open('tests/collectors/vendors/fixtures/publicsurplus_detail.html', 'w') as f:
    f.write(resp.text)
print('Saved to fixture file')
"
```

If the auction has expired, try another active one — browse `https://www.publicsurplus.com/sms/browse/cataucs?catid=1506` to find a current auction ID.

- [ ] **Step 2: Examine the detail page for date fields**

Read the saved fixture HTML. Search for date-related content — look for patterns like:
- "Opens:", "Closes:", "Start Date:", "End Date:", "Auction Start:", "Auction End:"
- Date strings in formats like "Mar 19, 2026" or "03/19/2026"
- `updateTimeLeftSpan` JS calls (may contain both start and end timestamps here)

Document what you find. The exact CSS selectors and date format will inform the parser implementation in the next task.

- [ ] **Step 3: Trim the fixture to a minimal representative sample**

Remove unnecessary parts of the HTML (navigation, footer, scripts unrelated to auction data) to keep the fixture small and focused. Keep the auction details section with date fields intact.

- [ ] **Step 4: Commit the fixture**

```bash
git add tests/collectors/vendors/fixtures/publicsurplus_detail.html
git commit -m "test(publicsurplus): add detail page fixture for date extraction (#57)"
```

---

### Task 6: Detail page parser

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/publicsurplus.py`
- Modify: `tests/collectors/vendors/test_publicsurplus.py`

**IMPORTANT — Discovery-dependent task:** The exact CSS selectors, date format, and parsing logic for this task depend entirely on what Task 5 discovers from the actual detail page HTML. The tests and code below are **templates only**. After completing Task 5:

1. Examine the saved fixture from Task 5 Step 2 to identify how dates appear (labeled fields? table rows? JS timestamps?)
2. Write the actual CSS selectors and date parsing logic based on what you found
3. Update the test assertions to check for the specific dates present in your fixture
4. If the detail page has no usable date fields at all, this function should return `None` — the collector's `_fetch_detail` method will fall back to using the JS end date from the listing page

- [ ] **Step 1: Write failing tests for detail page parser**

Add to `tests/collectors/vendors/test_publicsurplus.py`. Update the date assertions after examining the fixture from Task 5:

```python
from tdc_auction_calendar.collectors.vendors.publicsurplus import parse_detail_html


class TestParseDetailHtml:
    def test_extracts_start_date(self):
        html = _load("publicsurplus_detail.html")
        result = parse_detail_html(html)
        assert result is not None
        assert "start_date" in result
        assert isinstance(result["start_date"], date)
        # TODO: assert result["start_date"] == date(YYYY, M, D) based on fixture

    def test_extracts_end_date(self):
        html = _load("publicsurplus_detail.html")
        result = parse_detail_html(html)
        assert result is not None
        assert "end_date" in result
        assert isinstance(result["end_date"], date)
        # TODO: assert result["end_date"] == date(YYYY, M, D) based on fixture

    def test_empty_html_returns_none(self):
        assert parse_detail_html("") is None

    def test_html_without_dates_returns_none(self):
        assert parse_detail_html("<html><body>No auction here</body></html>") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/collectors/vendors/test_publicsurplus.py::TestParseDetailHtml -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement parse_detail_html based on Task 5 findings**

Add to `src/tdc_auction_calendar/collectors/vendors/publicsurplus.py`. **You must write the real selectors here** — do not leave TODOs. Reference the fixture HTML saved in Task 5 to determine the correct approach. Common patterns to look for:

- Labeled text like "Opens: Mar 17, 2026" → parse with regex or find the label element and get sibling text
- Table rows with "Start Date" / "End Date" headers → select the `<td>` elements
- `updateTimeLeftSpan` JS call with different parameters than the listing page → extract epoch timestamps

```python
def parse_detail_html(html: str) -> dict | None:
    """Parse a PublicSurplus auction detail page for start/end dates.

    Returns dict with keys: start_date, end_date (both datetime.date), or None if dates not found.
    """
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # IMPLEMENT: Real selectors based on Task 5 discovery
    start_date = None
    end_date = None

    if start_date is None:
        return None

    return {"start_date": start_date, "end_date": end_date}
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/collectors/vendors/test_publicsurplus.py::TestParseDetailHtml -v`
Expected: All 4 pass

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/publicsurplus.py tests/collectors/vendors/test_publicsurplus.py
git commit -m "feat(publicsurplus): add detail page date parser (#57)"
```

---

### Task 7: Normalize + PublicSurplusCollector class

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/publicsurplus.py`
- Modify: `tests/collectors/vendors/test_publicsurplus.py`

- [ ] **Step 1: Write failing tests for normalize and collector properties**

Add to `tests/collectors/vendors/test_publicsurplus.py`:

```python
import pytest
from tdc_auction_calendar.collectors.vendors.publicsurplus import PublicSurplusCollector
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor


class TestPublicSurplusCollector:
    @pytest.fixture()
    def collector(self):
        return PublicSurplusCollector()

    def test_name(self, collector):
        assert collector.name == "publicsurplus"

    def test_source_type(self, collector):
        assert collector.source_type == SourceType.VENDOR

    def test_normalize_with_county(self, collector):
        raw = {
            "state": "MN",
            "title": "Tract 4: Norman County Tax-Forfeiture Parcels",
            "start_date": date(2026, 3, 17),
            "end_date": date(2026, 3, 19),
            "sale_type": SaleType.DEED,
            "source_url": "https://www.publicsurplus.com/sms/auction/view?auc=3860102",
        }
        auction = collector.normalize(raw)
        assert auction.state == "MN"
        assert auction.county == "Norman"
        assert auction.start_date == date(2026, 3, 17)
        assert auction.end_date == date(2026, 3, 19)
        assert auction.sale_type == SaleType.DEED
        assert auction.source_type == SourceType.VENDOR
        assert auction.vendor == Vendor.PUBLIC_SURPLUS
        assert auction.confidence_score == 0.80
        assert auction.notes == "Tract 4: Norman County Tax-Forfeiture Parcels"

    def test_normalize_without_county(self, collector):
        raw = {
            "state": "MN",
            "title": "Parcel 2 PIN#26-345-0510",
            "start_date": date(2026, 3, 21),
            "end_date": date(2026, 3, 23),
            "sale_type": SaleType.DEED,
            "source_url": "https://www.publicsurplus.com/sms/auction/view?auc=3947401",
        }
        auction = collector.normalize(raw)
        assert auction.county == "Various"

    def test_normalize_lien(self, collector):
        raw = {
            "state": "FL",
            "title": "Tax Lien Certificate Sale",
            "start_date": date(2026, 4, 1),
            "end_date": None,
            "sale_type": SaleType.LIEN,
            "source_url": "https://www.publicsurplus.com/sms/auction/view?auc=9999999",
        }
        auction = collector.normalize(raw)
        assert auction.sale_type == SaleType.LIEN
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/collectors/vendors/test_publicsurplus.py::TestPublicSurplusCollector -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement the collector class**

Add to `src/tdc_auction_calendar/collectors/vendors/publicsurplus.py`:

```python
import asyncio

import httpx
from pydantic import ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping.client import ScrapeError
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor

_LISTING_URL = "https://www.publicsurplus.com/sms/browse/cataucs"
_MAX_PAGES = 20
_PAGE_DELAY = 0.5  # seconds between list page fetches
_MAX_CONCURRENT_DETAIL = 3

# catid -> SaleType mapping
_CATEGORY_SALE_TYPES: dict[int, SaleType] = {
    1506: SaleType.DEED,   # Tax Sale
    1505: SaleType.LIEN,   # Lien
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class PublicSurplusCollector(BaseCollector):
    """Collects tax sale and lien auctions from PublicSurplus.com."""

    @property
    def name(self) -> str:
        return "publicsurplus"

    @property
    def source_type(self) -> SourceType:
        return SourceType.VENDOR

    def normalize(self, raw: dict) -> Auction:
        county = extract_county(raw["title"])
        return Auction(
            state=raw["state"],
            county=county,
            start_date=raw["start_date"],
            end_date=raw.get("end_date"),
            sale_type=raw["sale_type"],
            source_type=SourceType.VENDOR,
            source_url=raw.get("source_url"),
            confidence_score=0.80,
            vendor=Vendor.PUBLIC_SURPLUS,
            notes=raw["title"],
        )

    async def _fetch(self) -> list[Auction]:
        """Two-pass fetch: list pages for discovery, detail pages for dates."""
        async with httpx.AsyncClient(
            follow_redirects=True, headers=_HEADERS, timeout=30.0
        ) as client:
            # Pass 1: discover auctions from listing pages
            raw_listings = await self._fetch_all_listings(client)

            # Filter to US states only
            raw_listings = [r for r in raw_listings if r["state"] in US_STATES]

            # Pass 2: fetch detail pages for start dates
            semaphore = asyncio.Semaphore(_MAX_CONCURRENT_DETAIL)
            tasks = [
                self._fetch_detail(client, semaphore, listing)
                for listing in raw_listings
            ]
            enriched = await asyncio.gather(*tasks)

        # Normalize valid entries
        auctions: list[Auction] = []
        for entry in enriched:
            if entry is None or entry.get("start_date") is None:
                continue
            try:
                auctions.append(self.normalize(entry))
            except (ValidationError, KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "publicsurplus_normalize_failed",
                    entry=entry,
                    error=str(exc),
                )

        logger.info(
            "publicsurplus_fetch_complete",
            discovered=len(raw_listings),
            auctions=len(auctions),
        )
        return auctions

    async def _fetch_all_listings(
        self, client: httpx.AsyncClient
    ) -> list[dict]:
        """Fetch all paginated listing pages for Tax Sale and Lien categories."""
        all_listings: list[dict] = []

        for catid, sale_type in _CATEGORY_SALE_TYPES.items():
            page = 0
            while page < _MAX_PAGES:
                try:
                    resp = await client.get(
                        _LISTING_URL, params={"catid": catid, "page": page}
                    )
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.warning(
                        "publicsurplus_listing_page_failed",
                        catid=catid,
                        page=page,
                        error=str(exc),
                    )
                    break

                items = parse_listing_html(resp.text)
                if not items:
                    break

                for item in items:
                    item["sale_type"] = sale_type
                all_listings.extend(items)

                page += 1
                if page < _MAX_PAGES:
                    await asyncio.sleep(_PAGE_DELAY)

        return all_listings

    async def _fetch_detail(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        listing: dict,
    ) -> dict | None:
        """Fetch a detail page and merge dates into the listing dict."""
        async with semaphore:
            try:
                resp = await client.get(listing["source_url"])
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning(
                    "publicsurplus_detail_failed",
                    auction_id=listing["auction_id"],
                    error=str(exc),
                )
                # Fallback: use end_date from JS as start_date
                if listing.get("end_date"):
                    listing["start_date"] = listing["end_date"]
                    return listing
                return None

            detail = parse_detail_html(resp.text)
            if detail and detail.get("start_date"):
                listing["start_date"] = detail["start_date"]
                if detail.get("end_date"):
                    listing["end_date"] = detail["end_date"]
            elif listing.get("end_date"):
                # Fallback: use end_date from JS as start_date
                listing["start_date"] = listing["end_date"]
            else:
                return None

            return listing
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/collectors/vendors/test_publicsurplus.py::TestPublicSurplusCollector -v`
Expected: All 5 pass

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/publicsurplus.py tests/collectors/vendors/test_publicsurplus.py
git commit -m "feat(publicsurplus): add collector class with two-pass fetch (#57)"
```

---

### Task 8: Fetch integration tests (mocked httpx)

**Files:**
- Modify: `tests/collectors/vendors/test_publicsurplus.py`

- [ ] **Step 1: Write mocked fetch tests**

Add to `tests/collectors/vendors/test_publicsurplus.py`. Follow the Bid4Assets mock pattern:

```python
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_httpx_response(html: str, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = html
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


class TestFetch:
    @pytest.fixture()
    def listing_html(self):
        return _load("publicsurplus_listing.html")

    @pytest.fixture()
    def detail_html(self):
        return _load("publicsurplus_detail.html")

    def _make_mock_client(self, listing_html: str, detail_html: str):
        """Create a mock httpx client that returns listing for GET with catid params
        and detail for GET with auction view URLs.

        For listing pages: returns listing_html on the first page request per category,
        then empty HTML on subsequent pages to end pagination. This correctly handles
        both catid=1506 and catid=1505 iterations.
        """
        mock_client = AsyncMock()
        # Track which (catid, page) combos have been called
        listing_calls: dict[tuple, int] = {}

        async def mock_get(url, **kwargs):
            params = kwargs.get("params", {})
            if "cataucs" in str(url) or "catid" in str(params):
                catid = params.get("catid", "unknown")
                page = params.get("page", 0)
                key = (catid, page)
                listing_calls[key] = listing_calls.get(key, 0) + 1
                # Return listing HTML only for page 0 of each category
                if page == 0:
                    return _mock_httpx_response(listing_html)
                return _mock_httpx_response("<html></html>")
            else:
                return _mock_httpx_response(detail_html)

        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        return mock_client

    async def test_returns_auctions(self, listing_html, detail_html):
        collector = PublicSurplusCollector()
        mock_client = self._make_mock_client(listing_html, detail_html)
        with patch(
            "tdc_auction_calendar.collectors.vendors.publicsurplus.httpx.AsyncClient",
            return_value=mock_client,
        ):
            auctions = await collector.collect()

        assert len(auctions) > 0
        assert all(a.vendor == Vendor.PUBLIC_SURPLUS for a in auctions)
        assert all(a.source_type == SourceType.VENDOR for a in auctions)
        assert all(a.state in US_STATES for a in auctions)

    async def test_empty_listings_returns_empty(self):
        collector = PublicSurplusCollector()
        mock_client = self._make_mock_client("<html></html>", "<html></html>")
        with patch(
            "tdc_auction_calendar.collectors.vendors.publicsurplus.httpx.AsyncClient",
            return_value=mock_client,
        ):
            auctions = await collector.collect()

        assert auctions == []
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/collectors/vendors/test_publicsurplus.py::TestFetch -v`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add tests/collectors/vendors/test_publicsurplus.py
git commit -m "test(publicsurplus): add mocked fetch integration tests (#57)"
```

---

### Task 9: Export from vendors __init__ and also fetch a live listing page for catid=1506

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/__init__.py`

- [ ] **Step 1: Add export**

In `src/tdc_auction_calendar/collectors/vendors/__init__.py`, add:

```python
from tdc_auction_calendar.collectors.vendors.publicsurplus import PublicSurplusCollector
```

And add `"PublicSurplusCollector"` to the `__all__` list.

- [ ] **Step 2: Verify the listing page HTML structure matches catid=1506**

Run a quick fetch to confirm the Tax Sale sub-category uses the same HTML structure:

```bash
uv run python -c "
import httpx
resp = httpx.get(
    'https://www.publicsurplus.com/sms/browse/cataucs',
    params={'catid': 1506},
    headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'},
    follow_redirects=True,
    timeout=30.0,
)
print(f'Status: {resp.status_code}, Length: {len(resp.text)}')
# Check for expected structure
if 'auction-item' in resp.text:
    print('OK: auction-item class found')
else:
    print('WARNING: auction-item class NOT found - HTML structure may differ')
if 'updateTimeLeftSpan' in resp.text:
    print('OK: updateTimeLeftSpan JS found')
else:
    print('WARNING: updateTimeLeftSpan JS NOT found')
"
```

If the structure differs from our research data, update the parser and fixture accordingly before proceeding.

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/collectors/vendors/test_publicsurplus.py -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/__init__.py
git commit -m "feat(publicsurplus): export collector from vendors package (#57)"
```

---

### Task 10: Final verification

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -v --timeout=30`
Expected: All tests pass, no regressions

- [ ] **Step 2: Verify imports work end-to-end**

```bash
uv run python -c "from tdc_auction_calendar.collectors.vendors import PublicSurplusCollector; print('Import OK')"
```

- [ ] **Step 3: Commit any final fixes if needed**

---

### Task 11: Live integration test

**Files:**
- Modify: `tests/collectors/vendors/test_publicsurplus.py`

- [ ] **Step 1: Add integration test**

Add to `tests/collectors/vendors/test_publicsurplus.py`:

```python
@pytest.mark.integration
class TestLiveIntegration:
    async def test_collect_returns_auctions(self):
        """Smoke test against live PublicSurplus site.

        Run with: uv run pytest -m integration -v
        """
        collector = PublicSurplusCollector()
        auctions = await collector.collect()
        # Should find at least some auctions (site may have 0 in a category)
        # Just verify it runs without errors and returns valid Auction objects
        for a in auctions:
            assert a.state in US_STATES
            assert a.source_type == SourceType.VENDOR
            assert a.vendor == Vendor.PUBLIC_SURPLUS
            assert a.start_date is not None
            assert a.source_url is not None
```

- [ ] **Step 2: Register the integration marker if not already configured**

Check `pyproject.toml` for `[tool.pytest.ini_options]` markers. If `integration` is not registered, add it:

```toml
[tool.pytest.ini_options]
markers = [
    "integration: live site integration tests (deselect with '-m not integration')",
]
```

Then verify integration tests are excluded from normal runs:

```bash
uv run pytest tests/collectors/vendors/test_publicsurplus.py -v -m "not integration"
```

- [ ] **Step 3: Commit**

```bash
git add tests/collectors/vendors/test_publicsurplus.py
git commit -m "test(publicsurplus): add live integration smoke test (#57)"
```
