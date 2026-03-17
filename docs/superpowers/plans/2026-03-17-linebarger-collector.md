# Linebarger Collector Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a collector that fetches TX/PA tax sale auction dates from the Linebarger portal's REST API.

**Architecture:** Single httpx GET call to `/api/filter_bar/?limit=1000`, filter cancelled entries, group by (state, county, date) to produce unique Auction records. Follows the Bid4Assets collector pattern (plain httpx, no browser rendering).

**Tech Stack:** Python, httpx, Pydantic, pytest, structlog

---

### Task 1: Add LINEBARGER to Vendor enum

**Files:**
- Modify: `src/tdc_auction_calendar/models/enums.py:33-41`

- [ ] **Step 1: Write the failing test**

Create `tests/collectors/vendors/test_linebarger.py`:

```python
# tests/collectors/vendors/test_linebarger.py
"""Tests for Linebarger vendor collector."""

from tdc_auction_calendar.models.enums import Vendor


def test_linebarger_vendor_exists():
    assert Vendor.LINEBARGER == "Linebarger Goggan Blair & Sampson"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/collectors/vendors/test_linebarger.py::test_linebarger_vendor_exists -v`
Expected: FAIL with `AttributeError: LINEBARGER`

- [ ] **Step 3: Add the enum value**

In `src/tdc_auction_calendar/models/enums.py`, add to the `Vendor` class after `PUBLIC_SURPLUS`:

```python
    LINEBARGER = "Linebarger Goggan Blair & Sampson"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/collectors/vendors/test_linebarger.py::test_linebarger_vendor_exists -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/models/enums.py tests/collectors/vendors/test_linebarger.py
git commit -m "feat(linebarger): add LINEBARGER to Vendor enum (#58)"
```

---

### Task 2: Implement county name normalization

**Files:**
- Create: `src/tdc_auction_calendar/collectors/vendors/linebarger.py`
- Test: `tests/collectors/vendors/test_linebarger.py`

- [ ] **Step 1: Write failing tests for county name normalization**

Append to `tests/collectors/vendors/test_linebarger.py`:

```python
import pytest
from tdc_auction_calendar.collectors.vendors.linebarger import normalize_county_name


class TestNormalizeCountyName:
    def test_single_word(self):
        assert normalize_county_name("DALLAS COUNTY") == "Dallas"

    def test_multi_word(self):
        assert normalize_county_name("FORT BEND COUNTY") == "Fort Bend"

    def test_three_word(self):
        assert normalize_county_name("JIM HOGG COUNTY") == "Jim Hogg"

    def test_already_clean(self):
        assert normalize_county_name("PHILADELPHIA COUNTY") == "Philadelphia"

    def test_no_county_suffix(self):
        assert normalize_county_name("DALLAS") == "Dallas"

    def test_lowercase_input(self):
        assert normalize_county_name("harris county") == "Harris"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_linebarger.py::TestNormalizeCountyName -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement normalize_county_name**

Create `src/tdc_auction_calendar/collectors/vendors/linebarger.py`:

```python
# src/tdc_auction_calendar/collectors/vendors/linebarger.py
"""Linebarger vendor collector — tax sale auctions from taxsales.lgbs.com API."""

from __future__ import annotations

import re


def normalize_county_name(raw: str) -> str:
    """Strip ' COUNTY' suffix and title-case the name.

    Examples:
        "HARRIS COUNTY" -> "Harris"
        "FORT BEND COUNTY" -> "Fort Bend"
        "JIM HOGG COUNTY" -> "Jim Hogg"
    """
    cleaned = re.sub(r"\s+county$", "", raw.strip(), flags=re.IGNORECASE)
    return cleaned.title()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_linebarger.py::TestNormalizeCountyName -v`
Expected: PASS (all 6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/linebarger.py tests/collectors/vendors/test_linebarger.py
git commit -m "feat(linebarger): add county name normalization (#58)"
```

---

### Task 3: Implement API response parsing

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/linebarger.py`
- Test: `tests/collectors/vendors/test_linebarger.py`

- [ ] **Step 1: Write failing tests for parse_api_response**

Append to `tests/collectors/vendors/test_linebarger.py`:

```python
from datetime import date
from tdc_auction_calendar.collectors.vendors.linebarger import parse_api_response
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor


class TestParseApiResponse:
    def test_basic_parsing(self):
        data = {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
                {
                    "county": "DALLAS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
            ],
        }
        auctions = parse_api_response(data)
        assert len(auctions) == 2
        harris = next(a for a in auctions if a.county == "Harris")
        assert harris.state == "TX"
        assert harris.start_date == date(2026, 4, 7)
        assert harris.sale_type == SaleType.DEED
        assert harris.vendor == Vendor.LINEBARGER
        assert harris.confidence_score == 1.0
        assert harris.source_type == SourceType.VENDOR

    def test_filters_cancelled(self):
        data = {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
                {
                    "county": "DALLAS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Cancelled",
                    "precinct": "1",
                },
            ],
        }
        auctions = parse_api_response(data)
        assert len(auctions) == 1
        assert auctions[0].county == "Harris"

    def test_deduplicates_precincts(self):
        """Same county + date + different precincts = one Auction."""
        data = {
            "count": 3,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "2",
                },
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Online Auction",
                    "precinct": "3",
                },
            ],
        }
        auctions = parse_api_response(data)
        assert len(auctions) == 1
        assert auctions[0].county == "Harris"

    def test_pa_is_deed(self):
        data = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "PHILADELPHIA COUNTY",
                    "state": "PA",
                    "sale_date_only": "2026-03-24",
                    "status": "Scheduled for Auction",
                    "precinct": "",
                },
            ],
        }
        auctions = parse_api_response(data)
        assert len(auctions) == 1
        assert auctions[0].sale_type == SaleType.DEED

    def test_source_url_includes_state(self):
        data = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "PHILADELPHIA COUNTY",
                    "state": "PA",
                    "sale_date_only": "2026-03-24",
                    "status": "Scheduled for Auction",
                    "precinct": "",
                },
            ],
        }
        auctions = parse_api_response(data)
        assert auctions[0].source_url == "https://taxsales.lgbs.com/map?area=PA"

    def test_skips_empty_date(self):
        data = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
            ],
        }
        auctions = parse_api_response(data)
        assert len(auctions) == 0

    def test_skips_null_date(self):
        data = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": None,
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
            ],
        }
        auctions = parse_api_response(data)
        assert len(auctions) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_linebarger.py::TestParseApiResponse -v`
Expected: FAIL with `ImportError: cannot import name 'parse_api_response'`

- [ ] **Step 3: Implement parse_api_response**

Add to `src/tdc_auction_calendar/collectors/vendors/linebarger.py`:

```python
from datetime import date

import structlog
from pydantic import ValidationError

from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor

logger = structlog.get_logger()

_BASE_URL = "https://taxsales.lgbs.com"
_API_URL = f"{_BASE_URL}/api/filter_bar/"


def parse_api_response(data: dict) -> list[Auction]:
    """Parse the filter_bar API response into deduplicated Auction records.

    Groups by (state, county, sale_date) so multiple precincts on the same
    date in the same county produce one Auction.
    """
    seen: set[tuple[str, str, date]] = set()
    auctions: list[Auction] = []

    for item in data.get("results", []):
        # Skip cancelled
        status = item.get("status", "")
        if "cancelled" in status.lower():
            continue

        # Skip empty/null dates
        raw_date = item.get("sale_date_only")
        if not raw_date:
            continue

        state = item.get("state", "")
        raw_county = item.get("county", "")
        county = normalize_county_name(raw_county)

        try:
            sale_date = date.fromisoformat(raw_date)
        except (ValueError, TypeError):
            logger.warning(
                "linebarger_date_parse_failed",
                county=raw_county,
                date=raw_date,
            )
            continue

        # Dedup by (state, county, date) — collapses precincts
        key = (state, county, sale_date)
        if key in seen:
            continue
        seen.add(key)

        # Both TX and PA are deed states per seed data
        sale_type = SaleType.DEED

        try:
            auctions.append(
                Auction(
                    state=state,
                    county=county,
                    start_date=sale_date,
                    sale_type=sale_type,
                    source_type=SourceType.VENDOR,
                    source_url=f"{_BASE_URL}/map?area={state}",
                    confidence_score=1.0,
                    vendor=Vendor.LINEBARGER,
                )
            )
        except ValidationError as exc:
            logger.warning(
                "linebarger_validation_failed",
                county=raw_county,
                state=state,
                error=str(exc),
            )

    return auctions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_linebarger.py::TestParseApiResponse -v`
Expected: PASS (all 7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/linebarger.py tests/collectors/vendors/test_linebarger.py
git commit -m "feat(linebarger): add API response parsing with filtering and dedup (#58)"
```

---

### Task 4: Implement LinebargerCollector class

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/linebarger.py`
- Test: `tests/collectors/vendors/test_linebarger.py`

- [ ] **Step 1: Write failing tests for the collector**

Append to `tests/collectors/vendors/test_linebarger.py`:

```python
from unittest.mock import AsyncMock, patch
import httpx
from tdc_auction_calendar.collectors.scraping.client import ScrapeError
from tdc_auction_calendar.collectors.vendors.linebarger import LinebargerCollector


class TestLinebargerCollector:
    def test_properties(self):
        collector = LinebargerCollector()
        assert collector.name == "linebarger"
        assert collector.source_type == SourceType.VENDOR

    def test_normalize(self):
        collector = LinebargerCollector()
        raw = {
            "state": "TX",
            "county": "Harris",
            "start_date": date(2026, 4, 7),
            "sale_type": SaleType.DEED,
            "source_url": "https://taxsales.lgbs.com/map?area=TX",
        }
        auction = collector.normalize(raw)
        assert auction.state == "TX"
        assert auction.county == "Harris"
        assert auction.start_date == date(2026, 4, 7)
        assert auction.vendor == Vendor.LINEBARGER
        assert auction.confidence_score == 1.0

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        mock_json = {
            "count": 2,
            "next": None,
            "previous": None,
            "results": [
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
                {
                    "county": "PHILADELPHIA COUNTY",
                    "state": "PA",
                    "sale_date_only": "2026-03-24",
                    "status": "Scheduled for Auction",
                    "precinct": "",
                },
            ],
        }
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_json
        mock_response.raise_for_status = lambda: None

        with patch("tdc_auction_calendar.collectors.vendors.linebarger.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = LinebargerCollector()
            auctions = await collector._fetch()

        assert len(auctions) == 2
        counties = {a.county for a in auctions}
        assert counties == {"Harris", "Philadelphia"}

    @pytest.mark.asyncio
    async def test_fetch_http_error_raises_scrape_error(self):
        with patch("tdc_auction_calendar.collectors.vendors.linebarger.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.HTTPStatusError(
                "500", request=httpx.Request("GET", "http://test"), response=httpx.Response(500)
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = LinebargerCollector()
            with pytest.raises(ScrapeError):
                await collector._fetch()

    @pytest.mark.asyncio
    async def test_fetch_follows_pagination(self):
        page1 = {
            "count": 2,
            "next": "https://taxsales.lgbs.com/api/filter_bar/?limit=1000&offset=1000",
            "previous": None,
            "results": [
                {
                    "county": "HARRIS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
            ],
        }
        page2 = {
            "count": 2,
            "next": None,
            "previous": "https://taxsales.lgbs.com/api/filter_bar/?limit=1000",
            "results": [
                {
                    "county": "DALLAS COUNTY",
                    "state": "TX",
                    "sale_date_only": "2026-04-07",
                    "status": "Scheduled for Auction",
                    "precinct": "1",
                },
            ],
        }

        resp1 = AsyncMock()
        resp1.json.return_value = page1
        resp1.raise_for_status = lambda: None

        resp2 = AsyncMock()
        resp2.json.return_value = page2
        resp2.raise_for_status = lambda: None

        with patch("tdc_auction_calendar.collectors.vendors.linebarger.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = [resp1, resp2]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = LinebargerCollector()
            auctions = await collector._fetch()

        assert len(auctions) == 2
        assert mock_client.get.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_linebarger.py::TestLinebargerCollector -v`
Expected: FAIL with `ImportError: cannot import name 'LinebargerCollector'` (5 tests fail)

- [ ] **Step 3: Implement LinebargerCollector**

Add to `src/tdc_auction_calendar/collectors/vendors/linebarger.py`:

```python
import httpx

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping.client import ScrapeError


class LinebargerCollector(BaseCollector):
    """Collects tax sale auction dates from the Linebarger portal API."""

    @property
    def name(self) -> str:
        return "linebarger"

    @property
    def source_type(self) -> SourceType:
        return SourceType.VENDOR

    def normalize(self, raw: dict) -> Auction:
        return Auction(
            state=raw["state"],
            county=raw["county"],
            start_date=raw["start_date"],
            sale_type=raw["sale_type"],
            source_type=SourceType.VENDOR,
            source_url=raw.get("source_url", f"{_BASE_URL}/map"),
            confidence_score=1.0,
            vendor=Vendor.LINEBARGER,
        )

    async def _fetch(self) -> list[Auction]:
        headers = {
            "Accept": "application/json",
        }

        all_results: list[dict] = []
        url = f"{_API_URL}?limit=1000"

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, headers=headers, timeout=30.0
            ) as client:
                while url:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json()
                    all_results.extend(data.get("results", []))
                    url = data.get("next")
        except httpx.HTTPError as exc:
            raise ScrapeError(
                url=_API_URL,
                attempts=[{"fetcher": "httpx", "error": str(exc)}],
            ) from exc

        combined = {
            "count": len(all_results),
            "next": None,
            "previous": None,
            "results": all_results,
        }
        auctions = parse_api_response(combined)

        logger.info(
            "linebarger_fetch_complete",
            total_api_results=len(all_results),
            auctions=len(auctions),
        )
        return auctions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_linebarger.py::TestLinebargerCollector -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/linebarger.py tests/collectors/vendors/test_linebarger.py
git commit -m "feat(linebarger): implement LinebargerCollector with pagination (#58)"
```

---

### Task 5: Register collector in orchestrator and exports

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/__init__.py`
- Modify: `src/tdc_auction_calendar/collectors/__init__.py`
- Modify: `src/tdc_auction_calendar/collectors/orchestrator.py:19,26-38`

- [ ] **Step 1: Write failing test**

Append to `tests/collectors/vendors/test_linebarger.py`:

```python
from tdc_auction_calendar.collectors.orchestrator import COLLECTORS


def test_linebarger_in_orchestrator():
    assert "linebarger" in COLLECTORS
    assert COLLECTORS["linebarger"] is LinebargerCollector
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/collectors/vendors/test_linebarger.py::test_linebarger_in_orchestrator -v`
Expected: FAIL with `AssertionError`

- [ ] **Step 3: Update vendors/__init__.py**

Add to `src/tdc_auction_calendar/collectors/vendors/__init__.py`:

```python
from tdc_auction_calendar.collectors.vendors.linebarger import LinebargerCollector
```

And add `"LinebargerCollector"` to the `__all__` list.

- [ ] **Step 4: Update collectors/__init__.py**

In `src/tdc_auction_calendar/collectors/__init__.py`, add `LinebargerCollector` to the vendors import line and the `__all__` list.

- [ ] **Step 5: Update orchestrator.py**

In `src/tdc_auction_calendar/collectors/orchestrator.py`:
- Add `LinebargerCollector` to the vendors import on line 19
- Add `"linebarger": LinebargerCollector,` to the `COLLECTORS` dict after `"publicsurplus"`

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/collectors/vendors/test_linebarger.py::test_linebarger_in_orchestrator -v`
Expected: PASS

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest tests/collectors/vendors/test_linebarger.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/__init__.py src/tdc_auction_calendar/collectors/__init__.py src/tdc_auction_calendar/collectors/orchestrator.py tests/collectors/vendors/test_linebarger.py
git commit -m "feat(linebarger): register collector in orchestrator (#58)"
```

---

### Task 6: Final verification

**Files:** None (read-only verification)

- [ ] **Step 1: Run full project test suite**

Run: `uv run pytest -v`
Expected: All tests pass, no regressions

- [ ] **Step 2: Verify collector runs against live API (manual smoke test)**

Run: `uv run python -c "import asyncio; from tdc_auction_calendar.collectors.vendors.linebarger import LinebargerCollector; c = LinebargerCollector(); auctions = asyncio.run(c.collect()); print(f'{len(auctions)} auctions'); [print(f'  {a.state} {a.county} {a.start_date}') for a in auctions[:5]]"`

Expected: Output showing TX/PA counties with upcoming sale dates.

- [ ] **Step 3: Commit any final adjustments if needed**
