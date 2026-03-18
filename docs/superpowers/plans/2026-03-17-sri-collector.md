# SRI Services Collector Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `SRICollector` that fetches tax sale auction dates from SRI Services' Azure REST API using plain httpx.

**Architecture:** Plain httpx POST to `sriservicesusermgmtprod.azurewebsites.net/api/auction/listall`, filter to tax-sale types (A/C/D/J), normalize to `Auction` models. Same pattern as `LinebargerCollector`.

**Tech Stack:** httpx, Pydantic, structlog, pytest with unittest.mock

**Spec:** `docs/superpowers/specs/2026-03-17-sri-collector-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/tdc_auction_calendar/collectors/vendors/sri.py` | **Create** — SRICollector class + `parse_api_response()` helper |
| `tests/collectors/vendors/test_sri.py` | **Create** — Full test suite |
| `src/tdc_auction_calendar/collectors/vendors/__init__.py` | **Modify** — Add `SRICollector` export |
| `src/tdc_auction_calendar/collectors/__init__.py` | **Modify** — Add `SRICollector` re-export |
| `src/tdc_auction_calendar/collectors/orchestrator.py` | **Modify** — Register `"sri": SRICollector` |

**Note:** `Vendor.SRI` already exists in `enums.py` — no enum change needed.

---

### Task 1: Write `parse_api_response()` with tests (TDD)

**Files:**
- Create: `tests/collectors/vendors/test_sri.py`
- Create: `src/tdc_auction_calendar/collectors/vendors/sri.py`

- [ ] **Step 1: Write failing tests for `parse_api_response()`**

Create `tests/collectors/vendors/test_sri.py`:

```python
# tests/collectors/vendors/test_sri.py
"""Tests for SRI Services vendor collector."""

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tdc_auction_calendar.collectors.scraping.client import ScrapeError
from tdc_auction_calendar.collectors.vendors.sri import (
    SRICollector,
    parse_api_response,
)
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor


class TestParseApiResponse:
    def test_basic_parsing(self):
        data = [
            {
                "id": 100,
                "saleType": "Tax Sale",
                "saleTypeCode": "A",
                "county": "Marion",
                "state": "IN",
                "auctionDate": "2026-04-07T10:00:00",
                "auctionDetail": {
                    "date": "04/07/2026",
                    "time": "10:00 AM",
                    "location": "zeusauction.com",
                    "type": "Online",
                },
            },
            {
                "id": 101,
                "saleType": "Deed Sale",
                "saleTypeCode": "D",
                "county": "Davidson",
                "state": "TN",
                "auctionDate": "2026-04-10T09:00:00",
                "auctionDetail": {
                    "date": "04/10/2026",
                    "time": "09:00 AM",
                    "location": "Court House",
                    "type": "In-person",
                },
            },
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 2
        marion = next(a for a in auctions if a.county == "Marion")
        assert marion.state == "IN"
        assert marion.start_date == date(2026, 4, 7)
        assert marion.sale_type == SaleType.DEED
        assert marion.vendor == Vendor.SRI
        assert marion.confidence_score == 1.0
        assert marion.source_type == SourceType.VENDOR
        assert marion.source_url == "https://sriservices.com/properties"

    def test_filters_excluded_sale_types(self):
        """Only A, C, D, J are kept. F, R, B, O are excluded."""
        data = [
            {
                "id": 1,
                "saleTypeCode": "A",
                "county": "Marion",
                "state": "IN",
                "auctionDate": "2026-04-07T10:00:00",
            },
            {
                "id": 2,
                "saleTypeCode": "F",
                "county": "Fulton",
                "state": "IN",
                "auctionDate": "2026-04-07T10:00:00",
            },
            {
                "id": 3,
                "saleTypeCode": "R",
                "county": "Clark",
                "state": "IN",
                "auctionDate": "2026-04-08T10:00:00",
            },
            {
                "id": 4,
                "saleTypeCode": "B",
                "county": "Lake",
                "state": "IN",
                "auctionDate": "2026-04-09T10:00:00",
            },
            {
                "id": 5,
                "saleTypeCode": "O",
                "county": "Allen",
                "state": "LA",
                "auctionDate": "2026-04-10T10:00:00",
            },
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 1
        assert auctions[0].county == "Marion"

    def test_sale_type_mapping(self):
        """A/D/J -> DEED, C -> LIEN."""
        data = [
            {"id": 1, "saleTypeCode": "A", "county": "A", "state": "IN", "auctionDate": "2026-04-01T10:00:00"},
            {"id": 2, "saleTypeCode": "C", "county": "B", "state": "IN", "auctionDate": "2026-04-02T10:00:00"},
            {"id": 3, "saleTypeCode": "D", "county": "C", "state": "TN", "auctionDate": "2026-04-03T10:00:00"},
            {"id": 4, "saleTypeCode": "J", "county": "D", "state": "LA", "auctionDate": "2026-04-04T10:00:00"},
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 4
        by_county = {a.county: a for a in auctions}
        assert by_county["A"].sale_type == SaleType.DEED
        assert by_county["B"].sale_type == SaleType.LIEN
        assert by_county["C"].sale_type == SaleType.DEED
        assert by_county["D"].sale_type == SaleType.DEED

    def test_deduplicates_same_county_date_saletype(self):
        """Same (state, county, date, sale_type) = one Auction."""
        data = [
            {"id": 1, "saleTypeCode": "A", "county": "Marion", "state": "IN", "auctionDate": "2026-04-07T10:00:00"},
            {"id": 2, "saleTypeCode": "A", "county": "Marion", "state": "IN", "auctionDate": "2026-04-07T14:00:00"},
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 1

    def test_preserves_different_sale_types_same_date(self):
        """Same county+date but different sale types = separate records."""
        data = [
            {"id": 1, "saleTypeCode": "A", "county": "Marion", "state": "IN", "auctionDate": "2026-04-07T10:00:00"},
            {"id": 2, "saleTypeCode": "C", "county": "Marion", "state": "IN", "auctionDate": "2026-04-07T10:00:00"},
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 2

    def test_empty_response(self):
        assert parse_api_response([]) == []

    def test_skips_missing_auction_date(self):
        data = [
            {"id": 1, "saleTypeCode": "A", "county": "Marion", "state": "IN", "auctionDate": None},
            {"id": 2, "saleTypeCode": "A", "county": "Marion", "state": "IN"},
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 0

    def test_skips_invalid_date_format(self):
        data = [
            {"id": 1, "saleTypeCode": "A", "county": "Marion", "state": "IN", "auctionDate": "not-a-date"},
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 0

    def test_skips_unknown_sale_type_code(self):
        """Unknown sale type codes (e.g. 'M') are skipped."""
        data = [
            {"id": 1, "saleTypeCode": "M", "county": "Marion", "state": "IN", "auctionDate": "2026-04-07T10:00:00"},
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_sri.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Write `parse_api_response()` implementation**

Create `src/tdc_auction_calendar/collectors/vendors/sri.py`:

```python
# src/tdc_auction_calendar/collectors/vendors/sri.py
"""SRI Services vendor collector — tax sale auctions from sriservices.com API."""

from __future__ import annotations

import json
from datetime import date, datetime

import httpx
import structlog
from pydantic import ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping.client import ScrapeError
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor

logger = structlog.get_logger()

_API_URL = "https://sriservicesusermgmtprod.azurewebsites.net/api/auction/listall"
_API_KEY = "9f8fd9fe5160294175e1c737567030f495d838a7922a678bc06e0a093910"
_SOURCE_URL = "https://sriservices.com/properties"
_RECORD_COUNT = 500

# Sale type codes we collect, mapped to our SaleType enum
_SALE_TYPE_MAP: dict[str, SaleType] = {
    "A": SaleType.DEED,   # Tax Sale
    "C": SaleType.LIEN,   # Certificate Sale
    "D": SaleType.DEED,   # Deed Sale
    "J": SaleType.DEED,   # Adjudicated Sale
}


def parse_api_response(data: list[dict]) -> list[Auction]:
    """Parse the auction/listall API response into deduplicated Auction records.

    Filters to tax-sale types (A, C, D, J) and deduplicates by
    (state, county, date, sale_type).
    """
    seen: set[tuple[str, str, date, SaleType]] = set()
    auctions: list[Auction] = []
    skipped_type = 0
    skipped_no_date = 0
    skipped_bad_date = 0
    skipped_validation = 0

    for item in data:
        # Filter to relevant sale types
        code = item.get("saleTypeCode", "")
        sale_type = _SALE_TYPE_MAP.get(code)
        if sale_type is None:
            skipped_type += 1
            continue

        # Parse auction date
        raw_date = item.get("auctionDate")
        if not raw_date:
            skipped_no_date += 1
            continue

        try:
            auction_date = datetime.fromisoformat(raw_date).date()
        except (ValueError, TypeError):
            skipped_bad_date += 1
            logger.warning(
                "sri_date_parse_failed",
                county=item.get("county"),
                date=raw_date,
            )
            continue

        state = item.get("state", "")
        county = item.get("county", "")

        # Dedup by (state, county, date, sale_type)
        key = (state, county, auction_date, sale_type)
        if key in seen:
            continue
        seen.add(key)

        try:
            auctions.append(
                Auction(
                    state=state,
                    county=county,
                    start_date=auction_date,
                    sale_type=sale_type,
                    source_type=SourceType.VENDOR,
                    source_url=_SOURCE_URL,
                    confidence_score=1.0,
                    vendor=Vendor.SRI,
                )
            )
        except ValidationError as exc:
            skipped_validation += 1
            logger.warning(
                "sri_validation_failed",
                county=county,
                state=state,
                error=str(exc),
            )

    return auctions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_sri.py::TestParseApiResponse -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/sri.py tests/collectors/vendors/test_sri.py
git commit -m "feat(sri): add parse_api_response with tests (#59)"
```

---

### Task 2: Write `SRICollector` class with tests (TDD)

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/sri.py`
- Modify: `tests/collectors/vendors/test_sri.py`

- [ ] **Step 1: Write failing tests for `SRICollector`**

Append to `tests/collectors/vendors/test_sri.py`:

```python
class TestSRICollector:
    def test_properties(self):
        collector = SRICollector()
        assert collector.name == "sri"
        assert collector.source_type == SourceType.VENDOR

    def test_normalize(self):
        collector = SRICollector()
        raw = {
            "state": "IN",
            "county": "Marion",
            "start_date": date(2026, 4, 7),
            "sale_type": SaleType.DEED,
        }
        auction = collector.normalize(raw)
        assert auction.state == "IN"
        assert auction.county == "Marion"
        assert auction.start_date == date(2026, 4, 7)
        assert auction.vendor == Vendor.SRI
        assert auction.confidence_score == 1.0
        assert auction.source_url == "https://sriservices.com/properties"

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        mock_json = [
            {
                "id": 100,
                "saleTypeCode": "A",
                "county": "Marion",
                "state": "IN",
                "auctionDate": "2026-04-07T10:00:00",
            },
            {
                "id": 101,
                "saleTypeCode": "F",
                "county": "Fulton",
                "state": "IN",
                "auctionDate": "2026-04-07T10:00:00",
            },
            {
                "id": 102,
                "saleTypeCode": "C",
                "county": "LaPorte",
                "state": "IN",
                "auctionDate": "2026-04-08T10:00:00",
            },
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = mock_json
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200

        with patch("tdc_auction_calendar.collectors.vendors.sri.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = SRICollector()
            auctions = await collector._fetch()

        # Only A and C kept, F filtered
        assert len(auctions) == 2
        counties = {a.county for a in auctions}
        assert counties == {"Marion", "LaPorte"}

    @pytest.mark.asyncio
    async def test_fetch_sends_correct_request(self):
        """Verify POST body and headers are correct."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200

        with patch("tdc_auction_calendar.collectors.vendors.sri.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = SRICollector()
            await collector._fetch()

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://sriservicesusermgmtprod.azurewebsites.net/api/auction/listall"
        body = call_args[1]["json"]
        assert body["recordCount"] == 500
        assert body["auctionDateRange"]["compareOperator"] == ">"
        assert body["auctionDateRange"]["startDate"]  # non-empty date string
        headers = call_args[1]["headers"]
        assert headers["x-api-key"] == "9f8fd9fe5160294175e1c737567030f495d838a7922a678bc06e0a093910"

    @pytest.mark.asyncio
    async def test_fetch_http_error_raises_scrape_error(self):
        with patch("tdc_auction_calendar.collectors.vendors.sri.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.HTTPStatusError(
                "500", request=httpx.Request("POST", "http://test"), response=httpx.Response(500)
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = SRICollector()
            with pytest.raises(ScrapeError):
                await collector._fetch()

    @pytest.mark.asyncio
    async def test_fetch_timeout_raises_scrape_error(self):
        with patch("tdc_auction_calendar.collectors.vendors.sri.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("Connection timed out")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = SRICollector()
            with pytest.raises(ScrapeError):
                await collector._fetch()

    @pytest.mark.asyncio
    async def test_fetch_json_decode_error_raises_scrape_error(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)
        mock_response.text = "<html>Server Error</html>"

        with patch("tdc_auction_calendar.collectors.vendors.sri.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = SRICollector()
            with pytest.raises(ScrapeError):
                await collector._fetch()

    @pytest.mark.asyncio
    async def test_fetch_non_list_response_raises_scrape_error(self):
        """API returning non-list JSON (e.g. error object) is caught."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "something went wrong"}

        with patch("tdc_auction_calendar.collectors.vendors.sri.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = SRICollector()
            with pytest.raises(ScrapeError):
                await collector._fetch()

    @pytest.mark.asyncio
    async def test_fetch_api_key_error_raises_scrape_error(self):
        """401/403 from API key issues raises ScrapeError."""
        with patch("tdc_auction_calendar.collectors.vendors.sri.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.HTTPStatusError(
                "401", request=httpx.Request("POST", "http://test"), response=httpx.Response(401)
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            collector = SRICollector()
            with pytest.raises(ScrapeError):
                await collector._fetch()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_sri.py::TestSRICollector -v`
Expected: FAIL — `SRICollector` class not yet defined or incomplete

- [ ] **Step 3: Write `SRICollector` class**

Append to `src/tdc_auction_calendar/collectors/vendors/sri.py` (after `parse_api_response`):

```python
class SRICollector(BaseCollector):
    """Collects tax sale auction dates from the SRI Services API."""

    @property
    def name(self) -> str:
        return "sri"

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
            source_url=_SOURCE_URL,
            confidence_score=1.0,
            vendor=Vendor.SRI,
        )

    async def _fetch(self) -> list[Auction]:
        today = date.today().isoformat()
        body = {
            "searchText": "",
            "state": "",
            "county": "",
            "propertySaleType": "",
            "auctionStyle": "",
            "saleStatus": "",
            "auctionDateRange": {
                "startDate": today,
                "endDate": "",
                "compareOperator": ">",
            },
            "recordCount": _RECORD_COUNT,
            "startIndex": 0,
        }
        headers = {
            "x-api-key": _API_KEY,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=30.0
            ) as client:
                resp = await client.post(_API_URL, json=body, headers=headers)
                resp.raise_for_status()

                try:
                    data = resp.json()
                except json.JSONDecodeError as exc:
                    raise ScrapeError(
                        url=_API_URL,
                        attempts=[{
                            "fetcher": "httpx",
                            "error": f"Non-JSON response: {resp.text[:200]}",
                        }],
                    ) from exc

                if not isinstance(data, list):
                    raise ScrapeError(
                        url=_API_URL,
                        attempts=[{
                            "fetcher": "httpx",
                            "error": f"Expected list, got {type(data).__name__}: {str(data)[:200]}",
                        }],
                    )
        except httpx.HTTPError as exc:
            raise ScrapeError(
                url=_API_URL,
                attempts=[{"fetcher": "httpx", "error": str(exc)}],
            ) from exc

        auctions = parse_api_response(data)

        logger.info(
            "sri_fetch_complete",
            total_api_results=len(data),
            auctions=len(auctions),
        )
        return auctions
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_sri.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/sri.py tests/collectors/vendors/test_sri.py
git commit -m "feat(sri): add SRICollector class with fetch tests (#59)"
```

---

### Task 3: Register collector and add integration test

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/__init__.py`
- Modify: `src/tdc_auction_calendar/collectors/__init__.py`
- Modify: `src/tdc_auction_calendar/collectors/orchestrator.py`
- Modify: `tests/collectors/vendors/test_sri.py`

- [ ] **Step 1: Write failing integration test**

Append to `tests/collectors/vendors/test_sri.py`:

```python
def test_sri_in_orchestrator():
    from tdc_auction_calendar.collectors.orchestrator import COLLECTORS
    assert "sri" in COLLECTORS
    assert COLLECTORS["sri"] is SRICollector


def test_sri_vendor_exists():
    assert Vendor.SRI == "SRI"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/collectors/vendors/test_sri.py::test_sri_in_orchestrator -v`
Expected: FAIL — `SRICollector` not registered yet

- [ ] **Step 3: Register SRICollector in exports and orchestrator**

**`src/tdc_auction_calendar/collectors/vendors/__init__.py`** — add import and export:

```python
from tdc_auction_calendar.collectors.vendors.sri import SRICollector
```

Add `"SRICollector"` to `__all__`.

**`src/tdc_auction_calendar/collectors/__init__.py`** — add to vendors import and `__all__`:

```python
from tdc_auction_calendar.collectors.vendors import ..., SRICollector
```

Add `"SRICollector"` to `__all__`.

**`src/tdc_auction_calendar/collectors/orchestrator.py`** — add import and registry entry:

```python
from tdc_auction_calendar.collectors.vendors import ..., SRICollector
```

Add to `COLLECTORS` dict:
```python
"sri": SRICollector,
```

- [ ] **Step 4: Run all tests to verify everything passes**

Run: `uv run pytest tests/collectors/vendors/test_sri.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `uv run pytest -v`
Expected: All tests PASS, no regressions

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/__init__.py \
        src/tdc_auction_calendar/collectors/__init__.py \
        src/tdc_auction_calendar/collectors/orchestrator.py \
        tests/collectors/vendors/test_sri.py
git commit -m "feat(sri): register SRICollector in orchestrator (#59)"
```
