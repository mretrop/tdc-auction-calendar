# RealAuction Collector Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a collector that scrapes ~59 RealAuction county portals for upcoming tax deed auction dates using CSS selectors on raw HTML.

**Architecture:** The collector follows the MVBA/Arkansas pattern — deterministic HTML parsing (BeautifulSoup + CSS selectors), no LLM extraction. It hardcodes a site registry in the module (matching how MVBA hardcodes its URL), fetches calendar pages via ScrapeClient, and parses `.CALSELT` cells for auction dates. The vendor_mapping.json is updated separately for seed data completeness.

**Tech Stack:** Python, BeautifulSoup4, asyncio (Semaphore + gather), ScrapeClient, BaseCollector

**Spec:** `docs/superpowers/specs/2026-03-15-realauction-collector-design.md`

---

## Chunk 1: Core Parser + Unit Tests

### Task 1: Add beautifulsoup4 as direct dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add beautifulsoup4 to dependencies**

In `pyproject.toml` under `[project] dependencies`, add `beautifulsoup4>=4.12` to the list.

- [ ] **Step 2: Sync dependencies**

Run: `uv sync`
Expected: Clean install, no errors.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add beautifulsoup4 as direct dependency (#50)"
```

---

### Task 2: Write the HTML parser module with tests (TDD)

**Files:**
- Create: `src/tdc_auction_calendar/collectors/vendors/realauction.py`
- Create: `tests/collectors/vendors/test_realauction.py`
- Create: `tests/collectors/vendors/fixtures/realauction_hillsborough_march.html`
- Create: `tests/collectors/vendors/fixtures/realauction_apache_empty.html`
- Create: `tests/collectors/vendors/fixtures/realauction_miamidade_mixed.html`

The parser is a standalone function `parse_calendar_html(html: str) -> list[dict]` that takes raw HTML and returns a list of dicts with keys: `date`, `sale_type`, `property_count`, `time`.

- [ ] **Step 1: Create test fixtures**

Save the raw HTML from browser research as fixture files. The Hillsborough fixture contains 4 auction cells (Tax Deed), the Apache fixture is empty (no `.CALSELT` cells), and the Miami-Dade fixture has both Foreclosure and Tax Deed cells.

**Hillsborough fixture** (`tests/collectors/vendors/fixtures/realauction_hillsborough_march.html`):

```html
<div class="CALBOX CALW5" aria-label="March-04-2026"><span class="CALNUM">4</span></div>
<div class="CALBOX CALW5 CALSELT" role="link" aria-label="March-05-2026" dayid="03/05/2026"><span class="CALNUM">5</span> <span class="CALTEXT">Tax Deed<br><span class="CALMSG"><span class="CALACT">0</span> / <span class="CALSCH">13</span> TD<br> </span><span class="CALTIME"> 10:00 AM ET</span></span></div>
<div class="CALBOX CALW5 CALSELT" role="link" aria-label="March-12-2026" dayid="03/12/2026"><span class="CALNUM">12</span> <span class="CALTEXT">Tax Deed<br><span class="CALMSG"><span class="CALACT">0</span> / <span class="CALSCH">16</span> TD<br> </span><span class="CALTIME"> 10:00 AM ET</span></span></div>
<div class="CALBOX CALW5 CALSELT" role="link" aria-label="March-19-2026" dayid="03/19/2026"><span class="CALNUM">19</span> <span class="CALTEXT">Tax Deed<br><span class="CALMSG"><span class="CALACT">5</span> / <span class="CALSCH">10</span> TD<br> </span><span class="CALTIME"> 10:00 AM ET</span></span></div>
<div class="CALBOX CALW5 CALSELT" role="link" aria-label="March-26-2026" dayid="03/26/2026"><span class="CALNUM">26</span> <span class="CALTEXT">Tax Deed<br><span class="CALMSG"><span class="CALACT">9</span> / <span class="CALSCH">14</span> TD<br> </span><span class="CALTIME"> 10:00 AM ET</span></span></div>
```

**Apache empty fixture** (`tests/collectors/vendors/fixtures/realauction_apache_empty.html`):

```html
<div class="CALBOX CALW5" aria-label="March-01-2026"><span class="CALNUM">1</span></div>
<div class="CALBOX CALW5" aria-label="March-02-2026"><span class="CALNUM">2</span></div>
<div class="CALBOX CALW5" aria-label="March-03-2026"><span class="CALNUM">3</span></div>
```

**Miami-Dade mixed fixture** (`tests/collectors/vendors/fixtures/realauction_miamidade_mixed.html`):

```html
<div class="CALBOX CALW5 CALSELT" role="link" aria-label="March-02-2026" dayid="03/02/2026"><span class="CALNUM">2</span> <span class="CALTEXT">Foreclosure<br><span class="CALMSG"><span class="CALACT">0</span> / <span class="CALSCH">37</span> FC<br> </span><span class="CALTIME"> 09:00 AM ET</span></span></div>
<div class="CALBOX CALW5 CALSELT" role="link" aria-label="March-19-2026" dayid="03/19/2026"><span class="CALNUM">19</span> <span class="CALTEXT">Tax Deed<br><span class="CALMSG"><span class="CALACT">16</span> / <span class="CALSCH">55</span> TD<br> </span><span class="CALTIME"> 02:00 PM ET</span></span></div>
<div class="CALBOX CALW5 CALSELT" role="link" aria-label="March-23-2026" dayid="03/23/2026"><span class="CALNUM">23</span> <span class="CALTEXT">Foreclosure<br><span class="CALMSG"><span class="CALACT">23</span> / <span class="CALSCH">26</span> FC<br> </span><span class="CALTIME"> 09:00 AM ET</span></span></div>
```

- [ ] **Step 2: Write failing tests for `parse_calendar_html()`**

`tests/collectors/vendors/test_realauction.py`:

```python
"""Tests for RealAuction vendor collector."""

from datetime import date
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


# ── parse_calendar_html tests ────────────────────────────────────────


from tdc_auction_calendar.collectors.vendors.realauction import parse_calendar_html


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
    """Combined portals should only return Tax Deed entries, not Foreclosure."""
    html = _load("realauction_miamidade_mixed.html")
    results = parse_calendar_html(html)
    assert len(results) == 1
    assert results[0]["sale_type"] == "Tax Deed"
    assert results[0]["date"] == date(2026, 3, 19)
    assert results[0]["property_count"] == 55


def test_parse_treasurer_deed():
    """Treasurer Deed (CO) should be accepted like Tax Deed."""
    html = '<div class="CALBOX CALW5 CALSELT" role="link" aria-label="April-15-2026" dayid="04/15/2026"><span class="CALNUM">15</span> <span class="CALTEXT">Treasurer Deed<br><span class="CALMSG"><span class="CALACT">0</span> / <span class="CALSCH">5</span> TD<br> </span><span class="CALTIME"> 10:00 AM MT</span></span></div>'
    results = parse_calendar_html(html)
    assert len(results) == 1
    assert results[0]["sale_type"] == "Treasurer Deed"
    assert results[0]["date"] == date(2026, 4, 15)


def test_parse_none_html():
    results = parse_calendar_html("")
    assert results == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_realauction.py -v`
Expected: FAIL with ImportError (module doesn't exist yet).

- [ ] **Step 4: Implement `parse_calendar_html()`**

Create `src/tdc_auction_calendar/collectors/vendors/realauction.py`:

```python
"""RealAuction vendor collector — tax deed auctions from county subdomains."""

from __future__ import annotations

from datetime import date, datetime

from bs4 import BeautifulSoup

_ACCEPTED_SALE_TYPES = frozenset({"Tax Deed", "Treasurer Deed"})


def parse_calendar_html(html: str) -> list[dict]:
    """Parse a RealAuction calendar page HTML into auction dicts.

    Returns list of dicts with keys: date, sale_type, property_count, time.
    Filters out Foreclosure entries; accepts Tax Deed and Treasurer Deed.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    cells = soup.select(".CALSELT")
    results: list[dict] = []

    for cell in cells:
        # Extract sale type from .CALTEXT first text node
        caltext = cell.select_one(".CALTEXT")
        if caltext is None:
            continue
        # First direct text node before <br> is the sale type
        sale_type = caltext.find(string=True, recursive=False)
        if sale_type is None:
            continue
        sale_type = sale_type.strip()
        if sale_type not in _ACCEPTED_SALE_TYPES:
            continue

        # Extract date from aria-label (format: "Month-DD-YYYY")
        label = cell.get("aria-label", "")
        try:
            auction_date = datetime.strptime(label, "%B-%d-%Y").date()
        except ValueError:
            continue

        # Extract scheduled property count
        calsch = cell.select_one(".CALSCH")
        property_count = int(calsch.get_text()) if calsch else 0

        # Extract time
        caltime = cell.select_one(".CALTIME")
        auction_time = caltime.get_text().strip() if caltime else ""

        results.append({
            "date": auction_date,
            "sale_type": sale_type,
            "property_count": property_count,
            "time": auction_time,
        })

    return results
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_realauction.py -v`
Expected: All 9 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/realauction.py \
        tests/collectors/vendors/test_realauction.py \
        tests/collectors/vendors/fixtures/
git commit -m "feat(realauction): add calendar HTML parser with tests (#50)"
```

---

## Chunk 2: Site Registry, URL Builder, Collector Class

### Task 3: Add site registry and URL builder with tests (TDD)

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/realauction.py`
- Modify: `tests/collectors/vendors/test_realauction.py`

The site registry is a module-level list of tuples: `(state, county, base_url)`. This follows the MVBA pattern of hardcoding source info in the module rather than querying the DB at runtime (existing collectors don't take a DB session).

- [ ] **Step 1: Write failing tests for URL builder and registry**

Append to `tests/collectors/vendors/test_realauction.py`:

```python
from tdc_auction_calendar.collectors.vendors.realauction import (
    calendar_url,
    SITES,
)


# ── URL builder tests ────────────────────────────────────────────────


def test_calendar_url_builds_correct_url():
    url = calendar_url("https://hillsborough.realtaxdeed.com", 2026, 4)
    assert url == "https://hillsborough.realtaxdeed.com/index.cfm?zaction=user&zmethod=calendar&selCalDate={ts '2026-04-01 00:00:00'}"


def test_calendar_url_pads_month():
    url = calendar_url("https://apache.realtaxdeed.com", 2026, 3)
    assert "2026-03-01" in url


def test_calendar_url_current_month():
    """When no year/month given, build URL without selCalDate (defaults to current month)."""
    url = calendar_url("https://hillsborough.realtaxdeed.com")
    assert url == "https://hillsborough.realtaxdeed.com/index.cfm?zaction=user&zmethod=calendar"


# ── Site registry tests ──────────────────────────────────────────────


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
    # All CO sites use treasurersdeedsale subdomain
    assert all("treasurersdeedsale" in u for _, _, u in co_sites)


def test_registry_contains_nj():
    nj_sites = [(s, c, u) for s, c, u in SITES if s == "NJ"]
    assert len(nj_sites) == 2


def test_registry_total_sites():
    assert len(SITES) >= 57
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_realauction.py -k "calendar_url or registry" -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement URL builder and site registry**

Add to `src/tdc_auction_calendar/collectors/vendors/realauction.py`, after the parse function:

```python
def calendar_url(base_url: str, year: int | None = None, month: int | None = None) -> str:
    """Build a RealAuction calendar page URL.

    If year/month are None, returns the default (current month) URL.
    """
    path = "/index.cfm?zaction=user&zmethod=calendar"
    if year is not None and month is not None:
        path += f"&selCalDate={{ts '{year:04d}-{month:02d}-01 00:00:00'}}"
    return f"{base_url}{path}"


# Site registry: (state, county, base_url)
# Sources: "Jump to" dropdown on RealAuction portals + SwitchSite AJAX resolution
SITES: list[tuple[str, str, str]] = [
    # Arizona
    ("AZ", "Apache", "https://apache.realtaxdeed.com"),
    ("AZ", "Coconino", "https://coconino.realtaxdeed.com"),
    ("AZ", "Mohave", "https://mohave.realtaxdeed.com"),
    # Colorado
    ("CO", "Adams", "https://adams.treasurersdeedsale.realtaxdeed.com"),
    ("CO", "Denver", "https://denver.treasurersdeedsale.realtaxdeed.com"),
    ("CO", "Eagle", "https://eagle.treasurersdeedsale.realtaxdeed.com"),
    ("CO", "El Paso", "https://elpasoco.treasurersdeedsale.realtaxdeed.com"),
    ("CO", "Larimer", "https://larimer.treasurersdeedsale.realtaxdeed.com"),
    ("CO", "Mesa", "https://mesa.treasurersdeedsale.realtaxdeed.com"),
    ("CO", "Pitkin", "https://pitkin.treasurersdeedsale.realtaxdeed.com"),
    ("CO", "Weld", "https://weld.treasurersdeedsale.realtaxdeed.com"),
    # Florida — dedicated .realtaxdeed.com
    ("FL", "Alachua", "https://alachua.realtaxdeed.com"),
    ("FL", "Baker", "https://baker.realtaxdeed.com"),
    ("FL", "Bay", "https://bay.realtaxdeed.com"),
    ("FL", "Brevard", "https://brevard.realtaxdeed.com"),
    ("FL", "Citrus", "https://citrus.realtaxdeed.com"),
    ("FL", "Clay", "https://clay.realtaxdeed.com"),
    ("FL", "Duval", "https://duval.realtaxdeed.com"),
    ("FL", "Escambia", "https://escambia.realtaxdeed.com"),
    ("FL", "Flagler", "https://flagler.realtaxdeed.com"),
    ("FL", "Gilchrist", "https://gilchrist.realtaxdeed.com"),
    ("FL", "Gulf", "https://gulf.realtaxdeed.com"),
    ("FL", "Hendry", "https://hendry.realtaxdeed.com"),
    ("FL", "Hernando", "https://hernando.realtaxdeed.com"),
    ("FL", "Highlands", "https://highlands.realtaxdeed.com"),
    ("FL", "Hillsborough", "https://hillsborough.realtaxdeed.com"),
    ("FL", "Indian River", "https://indianriver.realtaxdeed.com"),
    ("FL", "Jackson", "https://jackson.realtaxdeed.com"),
    ("FL", "Lake", "https://lake.realtaxdeed.com"),
    ("FL", "Lee", "https://lee.realtaxdeed.com"),
    ("FL", "Leon", "https://leon.realtaxdeed.com"),
    ("FL", "Marion", "https://marion.realtaxdeed.com"),
    ("FL", "Martin", "https://martin.realtaxdeed.com"),
    ("FL", "Monroe", "https://monroe.realtaxdeed.com"),
    ("FL", "Nassau", "https://nassau.realtaxdeed.com"),
    ("FL", "Orange", "https://orange.realtaxdeed.com"),
    ("FL", "Osceola", "https://osceola.realtaxdeed.com"),
    ("FL", "Palm Beach", "https://palmbeach.realtaxdeed.com"),
    ("FL", "Pasco", "https://pasco.realtaxdeed.com"),
    ("FL", "Pinellas", "https://pinellas.realtaxdeed.com"),
    ("FL", "Polk", "https://polk.realtaxdeed.com"),
    ("FL", "Putnam", "https://putnam.realtaxdeed.com"),
    ("FL", "Santa Rosa", "https://santarosa.realtaxdeed.com"),
    ("FL", "Sarasota", "https://sarasota.realtaxdeed.com"),
    ("FL", "Seminole", "https://seminole.realtaxdeed.com"),
    ("FL", "Suwannee", "https://suwannee.realtaxdeed.com"),
    ("FL", "Volusia", "https://volusia.realtaxdeed.com"),
    ("FL", "Washington", "https://washington.realtaxdeed.com"),
    # Florida — combined portals (.realforeclose.com, filter for TD only)
    ("FL", "Broward", "https://broward.realforeclose.com"),
    ("FL", "Calhoun", "https://calhoun.realforeclose.com"),
    ("FL", "Charlotte", "https://charlotte.realforeclose.com"),
    ("FL", "Collier", "https://collier.realforeclose.com"),
    ("FL", "Manatee", "https://manatee.realforeclose.com"),
    ("FL", "Miami-Dade", "https://miamidade.realforeclose.com"),
    ("FL", "Okeechobee", "https://okeechobee.realforeclose.com"),
    ("FL", "St. Lucie", "https://stlucie.realforeclose.com"),
    ("FL", "Walton", "https://walton.realforeclose.com"),
    # New Jersey
    ("NJ", "Hardyston", "https://hardystonnj.realforeclose.com"),
    ("NJ", "Newark", "https://newarknj.realforeclose.com"),
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_realauction.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/realauction.py \
        tests/collectors/vendors/test_realauction.py
git commit -m "feat(realauction): add site registry and URL builder (#50)"
```

---

### Task 4: Implement RealAuctionCollector class with tests (TDD)

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/realauction.py`
- Modify: `tests/collectors/vendors/test_realauction.py`

- [ ] **Step 1: Write failing tests for collector properties and normalize**

Append to `tests/collectors/vendors/test_realauction.py`:

```python
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.collectors.vendors.realauction import RealAuctionCollector
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor


# ── Collector property tests ─────────────────────────────────────────


@pytest.fixture()
def collector():
    return RealAuctionCollector()


def test_name(collector):
    assert collector.name == "realauction"


def test_source_type(collector):
    assert collector.source_type == SourceType.VENDOR


# ── normalize tests ──────────────────────────────────────────────────


def test_normalize_tax_deed(collector):
    raw = {
        "state": "FL",
        "county": "Hillsborough",
        "date": "2026-03-05",
        "sale_type": "Tax Deed",
        "property_count": 13,
        "time": "10:00 AM ET",
        "source_url": "https://hillsborough.realtaxdeed.com/index.cfm?zaction=user&zmethod=calendar",
    }
    auction = collector.normalize(raw)
    assert auction.state == "FL"
    assert auction.county == "Hillsborough"
    assert auction.start_date == date(2026, 3, 5)
    assert auction.sale_type == SaleType.DEED
    assert auction.source_type == SourceType.VENDOR
    assert auction.vendor == Vendor.REALAUCTION
    assert auction.confidence_score == 0.90
    assert auction.property_count == 13
    assert "10:00 AM ET" in auction.notes


def test_normalize_treasurer_deed(collector):
    raw = {
        "state": "CO",
        "county": "Denver",
        "date": "2026-04-15",
        "sale_type": "Treasurer Deed",
        "property_count": 5,
        "time": "10:00 AM MT",
        "source_url": "https://denver.treasurersdeedsale.realtaxdeed.com/index.cfm?zaction=user&zmethod=calendar",
    }
    auction = collector.normalize(raw)
    assert auction.sale_type == SaleType.DEED
    assert auction.state == "CO"


def test_normalize_missing_field_raises(collector):
    raw = {"state": "FL", "date": "2026-03-05"}
    with pytest.raises((KeyError, ValueError, ValidationError)):
        collector.normalize(raw)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_realauction.py -k "test_name or test_source or normalize" -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement RealAuctionCollector class**

Add to `src/tdc_auction_calendar/collectors/vendors/realauction.py`:

```python
import asyncio

import structlog
from pydantic import ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping import create_scrape_client
from tdc_auction_calendar.collectors.scraping import StealthLevel
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor

logger = structlog.get_logger()

_MONTHS_AHEAD = 2
_MAX_CONCURRENT = 5


class RealAuctionCollector(BaseCollector):
    """Collects tax deed auction dates from RealAuction county portals."""

    @property
    def name(self) -> str:
        return "realauction"

    @property
    def source_type(self) -> SourceType:
        return SourceType.VENDOR

    async def _fetch(self) -> list[Auction]:
        client = create_scrape_client(stealth=StealthLevel.STEALTH)
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

        async def _fetch_one(state: str, county: str, base_url: str, url: str) -> list[Auction]:
            async with semaphore:
                try:
                    result = await client.scrape(url)
                except Exception as exc:
                    logger.warning(
                        "realauction_fetch_failed",
                        state=state,
                        county=county,
                        url=url,
                        error=str(exc),
                    )
                    return []

                html = result.fetch.html or ""
                if not html:
                    return []

                entries = parse_calendar_html(html)
                auctions: list[Auction] = []
                for entry in entries:
                    raw = {
                        "state": state,
                        "county": county,
                        "date": entry["date"].isoformat(),
                        "sale_type": entry["sale_type"],
                        "property_count": entry["property_count"],
                        "time": entry["time"],
                        "source_url": url,
                    }
                    try:
                        auctions.append(self.normalize(raw))
                    except (KeyError, TypeError, ValueError, ValidationError) as exc:
                        logger.error(
                            "realauction_normalize_failed",
                            raw=raw,
                            error=str(exc),
                        )
                return auctions

        # Build all fetch tasks
        now = date.today()
        tasks: list = []
        for state, county, base_url in SITES:
            # Current month (default URL)
            tasks.append(_fetch_one(state, county, base_url, calendar_url(base_url)))
            # Next N months
            month = now.month
            year = now.year
            for _ in range(_MONTHS_AHEAD):
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                tasks.append(_fetch_one(state, county, base_url, calendar_url(base_url, year, month)))

        try:
            results = await asyncio.gather(*tasks)
        finally:
            await client.close()

        # Flatten
        all_auctions: list[Auction] = []
        for batch in results:
            all_auctions.extend(batch)

        logger.info(
            "realauction_fetch_complete",
            sites=len(SITES),
            months=_MONTHS_AHEAD + 1,
            auctions=len(all_auctions),
        )
        return all_auctions

    def normalize(self, raw: dict) -> Auction:
        return Auction(
            state=raw["state"],
            county=raw["county"],
            start_date=date.fromisoformat(raw["date"]),
            sale_type=SaleType.DEED,
            source_type=SourceType.VENDOR,
            source_url=raw["source_url"],
            confidence_score=0.90,
            vendor=Vendor.REALAUCTION,
            property_count=raw.get("property_count"),
            notes=raw.get("time", ""),
        )
```

Update imports at the top of the file to include all needed imports (asyncio, structlog, etc.).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_realauction.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/realauction.py \
        tests/collectors/vendors/test_realauction.py
git commit -m "feat(realauction): implement RealAuctionCollector class (#50)"
```

---

### Task 5: Write _fetch integration tests

**Files:**
- Modify: `tests/collectors/vendors/test_realauction.py`

- [ ] **Step 1: Write integration tests for _fetch with mocked ScrapeClient**

Append to `tests/collectors/vendors/test_realauction.py`:

```python
# ── _fetch integration tests ─────────────────────────────────────────


def _mock_scrape_result(html: str | None) -> ScrapeResult:
    return ScrapeResult(
        fetch=FetchResult(
            url="https://example.realtaxdeed.com/index.cfm",
            status_code=200,
            fetcher="cloudflare",
            html=html,
        ),
    )


@pytest.mark.asyncio
async def test_fetch_returns_auctions(collector):
    html = _load("realauction_hillsborough_march.html")
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(html)
    mock_client.close = AsyncMock()

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.create_scrape_client",
            return_value=mock_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.SITES",
            [("FL", "Hillsborough", "https://hillsborough.realtaxdeed.com")],
        ),
    ):
        auctions = await collector.collect()

    # 4 auctions per month * 3 months = 12 (same fixture reused)
    # After dedup: 4 unique (same dates across months dedup to one each)
    assert len(auctions) == 4
    assert all(a.state == "FL" for a in auctions)
    assert all(a.vendor == Vendor.REALAUCTION for a in auctions)


@pytest.mark.asyncio
async def test_fetch_empty_html_returns_empty(collector):
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result("")
    mock_client.close = AsyncMock()

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.create_scrape_client",
            return_value=mock_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.SITES",
            [("AZ", "Apache", "https://apache.realtaxdeed.com")],
        ),
    ):
        auctions = await collector.collect()

    assert auctions == []


@pytest.mark.asyncio
async def test_fetch_partial_failure_continues(collector):
    """If one county fails, others should still return results."""
    html = _load("realauction_hillsborough_march.html")

    call_count = 0

    async def mock_scrape(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if "apache" in url:
            raise ConnectionError("simulated failure")
        return _mock_scrape_result(html)

    mock_client = AsyncMock()
    mock_client.scrape = mock_scrape
    mock_client.close = AsyncMock()

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.create_scrape_client",
            return_value=mock_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.SITES",
            [
                ("AZ", "Apache", "https://apache.realtaxdeed.com"),
                ("FL", "Hillsborough", "https://hillsborough.realtaxdeed.com"),
            ],
        ),
    ):
        auctions = await collector.collect()

    # Apache fails, Hillsborough returns 4 per month * 3 months, deduped to 4
    assert len(auctions) == 4
    assert all(a.state == "FL" for a in auctions)


@pytest.mark.asyncio
async def test_fetch_mixed_portal_filters_foreclosure(collector):
    """Combined portals should only return Tax Deed auctions."""
    html = _load("realauction_miamidade_mixed.html")
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(html)
    mock_client.close = AsyncMock()

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.create_scrape_client",
            return_value=mock_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.SITES",
            [("FL", "Miami-Dade", "https://miamidade.realforeclose.com")],
        ),
    ):
        auctions = await collector.collect()

    # Only 1 Tax Deed entry per month, deduped across 3 months = 1
    assert len(auctions) == 1
    assert auctions[0].county == "Miami-Dade"
    assert auctions[0].sale_type == SaleType.DEED
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_realauction.py -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/collectors/vendors/test_realauction.py
git commit -m "test(realauction): add _fetch integration tests (#50)"
```

---

## Chunk 3: Registration, Seed Data, Final Wiring

### Task 6: Register collector in vendors module, collectors module, and orchestrator

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/__init__.py`
- Modify: `src/tdc_auction_calendar/collectors/__init__.py`
- Modify: `src/tdc_auction_calendar/collectors/orchestrator.py`

- [ ] **Step 1: Add to vendors/__init__.py**

Add import and `__all__` entry:
```python
from tdc_auction_calendar.collectors.vendors.realauction import RealAuctionCollector
```
Add `"RealAuctionCollector"` to `__all__`.

- [ ] **Step 2: Add to collectors/__init__.py**

Add import and `__all__` entry for `RealAuctionCollector`.

- [ ] **Step 3: Add to orchestrator.py**

Add import:
```python
from tdc_auction_calendar.collectors.vendors import MVBACollector, PurdueCollector, RealAuctionCollector
```

Add to `COLLECTORS` dict:
```python
"realauction": RealAuctionCollector,
```

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS, no import errors.

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/__init__.py \
        src/tdc_auction_calendar/collectors/__init__.py \
        src/tdc_auction_calendar/collectors/orchestrator.py
git commit -m "feat(realauction): register collector in orchestrator (#50)"
```

---

### Task 7: Update vendor_mapping.json seed data

**Files:**
- Modify: `src/tdc_auction_calendar/db/seed/vendor_mapping.json`

- [ ] **Step 1: Update existing FL entries and add new entries**

Update the 20 existing RealAuction entries:
- Change `portal_url` from `.realforeclose.com` to `.realtaxdeed.com` for counties that have dedicated taxdeed subdomains (Hillsborough, Orange, Duval, Pinellas, Lee, Polk, Brevard, Volusia, Seminole, Sarasota, Pasco, Escambia, Leon, Osceola, Marion, Palm Beach)
- Keep `.realforeclose.com` for combined portals (Miami-Dade, Broward, Manatee, Collier)

Add new entries for all counties in the `SITES` registry that don't already exist. Each entry uses the schema:
```json
{
  "vendor": "RealAuction",
  "vendor_url": "https://www.realauction.com",
  "state": "XX",
  "county": "County Name",
  "portal_url": "https://subdomain.realtaxdeed.com"
}
```

- [ ] **Step 2: Run seed data tests**

Run: `uv run pytest tests/ -k "seed" -v`
Expected: All seed tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/tdc_auction_calendar/db/seed/vendor_mapping.json
git commit -m "data: expand RealAuction vendor mapping to ~59 counties (#50)"
```

---

### Task 8: Final verification

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 2: Verify CLI integration**

Run: `uv run python -m tdc_auction_calendar --help`
Expected: CLI loads without import errors.

- [ ] **Step 3: Run linting if configured**

Run: `uv run ruff check src/tdc_auction_calendar/collectors/vendors/realauction.py tests/collectors/vendors/test_realauction.py`
Expected: No errors.
