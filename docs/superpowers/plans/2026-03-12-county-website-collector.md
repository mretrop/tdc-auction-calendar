# County Website Collector Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a collector that scrapes individual county tax sale pages and extracts auction dates, plus populate ~50+ real county URLs in seed data.

**Architecture:** Single `CountyWebsiteCollector` extends `BaseCollector`, loads counties with `tax_sale_page_url` from seed JSON, iterates serially with LLM schema extraction via `ScrapeClient`. Logs and skips failures per county.

**Tech Stack:** Python, Pydantic, structlog, ScrapeClient (Crawl4AI/Cloudflare), pytest

**Spec:** `docs/superpowers/specs/2026-03-12-county-website-collector-design.md`

---

## Chunk 1: Seed Data & Collector Implementation

### Task 1: Populate county URLs in seed data

**Files:**
- Modify: `src/tdc_auction_calendar/db/seed/counties.json`

Research and populate `tax_sale_page_url` for ~50+ counties across states with existing collectors. Target states: FL, CO, CA, NJ, PA, NC, SC, MN, UT, AR, IA. Each URL should point to the county's treasurer/tax collector page that lists upcoming tax sale dates.

**Important seed data notes:**
- The `state` field is two-letter abbreviation (e.g., `"FL"`, not `"state_code"`)
- The `county_name` field is the county name
- Set `tax_sale_page_url` to the real URL string (was previously `null`)
- Do NOT change any other fields

- [ ] **Step 1: Research and populate URLs for FL counties (~10-15)**

Use web search to find real county treasurer/tax collector URLs for Florida counties in the seed data (e.g., Duval, Miami-Dade, Broward, Hillsborough, Orange, etc.). These are lien states — look for "tax certificate sale" or "tax lien sale" pages.

- [ ] **Step 2: Research and populate URLs for CO counties (~10-15)**

Colorado counties from seed data. Look for treasurer pages with tax lien sale information.

- [ ] **Step 3: Research and populate URLs for CA counties (~10-15)**

California counties from seed data. Look for tax collector pages with tax-defaulted property auction information.

- [ ] **Step 4: Research and populate URLs for NJ, PA, NC, SC, MN, UT (~10-15 total)**

Remaining target states. Spread across available counties in seed data.

- [ ] **Step 5: Verify count >= 50 populated URLs**

```bash
python3 -c "
import json
with open('src/tdc_auction_calendar/db/seed/counties.json') as f:
    counties = json.load(f)
populated = [c for c in counties if c.get('tax_sale_page_url')]
print(f'Counties with URLs: {len(populated)}')
for c in populated[:5]:
    print(f\"  {c['state']} - {c['county_name']}: {c['tax_sale_page_url']}\")
"
```

Expected: >= 50 counties with URLs populated.

- [ ] **Step 6: Commit seed data**

```bash
git add src/tdc_auction_calendar/db/seed/counties.json
git commit -m "feat(seed): populate tax_sale_page_url for 50+ counties (issue #13)"
```

---

### Task 2: Create CountyWebsiteCollector with tests (TDD)

**Files:**
- Create: `src/tdc_auction_calendar/collectors/county_websites/__init__.py`
- Create: `src/tdc_auction_calendar/collectors/county_websites/county_collector.py`
- Create: `tests/collectors/county_websites/__init__.py`
- Create: `tests/collectors/county_websites/test_county_collector.py`
- Create: `tests/fixtures/county_websites/county_extraction_results.json`

**Reference files:**
- `src/tdc_auction_calendar/collectors/base.py` — BaseCollector ABC
- `src/tdc_auction_calendar/collectors/public_notices/base_notice.py` — similar pattern for _fetch loop
- `src/tdc_auction_calendar/db/seed_loader.py` — `SEED_DIR` constant
- `src/tdc_auction_calendar/models/enums.py` — SourceType.COUNTY_WEBSITE, SaleType enum
- `src/tdc_auction_calendar/models/auction.py` — Auction model

#### Step group A: Test infrastructure

- [ ] **Step 1: Create test file with basic property tests**

Create `tests/collectors/county_websites/__init__.py` (empty) and `tests/collectors/county_websites/test_county_collector.py`:

```python
"""Tests for CountyWebsiteCollector."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tdc_auction_calendar.collectors.county_websites.county_collector import (
    CountyWebsiteCollector,
)
from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.models.enums import SaleType, SourceType

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "county_websites"


def _mock_scrape_result(data, url="https://example.com"):
    return ScrapeResult(
        fetch=FetchResult(
            url=url,
            status_code=200,
            fetcher="crawl4ai",
            html="<div>results</div>",
        ),
        data=data,
    )


@pytest.fixture()
def collector():
    return CountyWebsiteCollector()


def test_name(collector):
    assert collector.name == "county_website"


def test_source_type(collector):
    assert collector.source_type == SourceType.COUNTY_WEBSITE
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/collectors/county_websites/test_county_collector.py -v
```

Expected: FAIL — `CountyWebsiteCollector` doesn't exist yet.

- [ ] **Step 3: Create minimal collector skeleton (stubs only)**

Create `src/tdc_auction_calendar/collectors/county_websites/__init__.py`:
```python
from tdc_auction_calendar.collectors.county_websites.county_collector import (
    CountyWebsiteCollector,
)

__all__ = ["CountyWebsiteCollector"]
```

Create `src/tdc_auction_calendar/collectors/county_websites/county_collector.py` with stubs:
```python
"""County website collector — scrapes individual county tax sale pages."""

from __future__ import annotations

import json

import structlog
from pydantic import BaseModel

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.db.seed_loader import SEED_DIR
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SourceType

logger = structlog.get_logger()


class CountyAuctionRecord(BaseModel):
    """Schema for extraction from a single county's tax sale page."""

    sale_date: str
    sale_type: str = ""
    end_date: str | None = None
    deposit_amount: str | None = None
    registration_deadline: str | None = None


class CountyWebsiteCollector(BaseCollector):
    """Scrapes individual county tax sale pages for auction dates."""

    confidence_score: float = 0.70

    def __init__(self) -> None:
        self._county_targets = self._load_county_targets()

    @property
    def name(self) -> str:
        return "county_website"

    @property
    def source_type(self) -> SourceType:
        return SourceType.COUNTY_WEBSITE

    @staticmethod
    def _load_county_targets() -> list[dict]:
        """Load counties with tax_sale_page_url from seed data, joined with state sale_type."""
        with open(SEED_DIR / "counties.json") as f:
            counties = json.load(f)
        with open(SEED_DIR / "states.json") as f:
            states = {s["state"]: s for s in json.load(f)}

        targets = []
        for county in counties:
            url = county.get("tax_sale_page_url")
            if not url:
                continue
            state_code = county["state"]
            state_info = states.get(state_code, {})
            targets.append({
                "state_code": state_code,
                "county_name": county["county_name"],
                "tax_sale_page_url": url,
                "default_sale_type": state_info.get("sale_type", "deed"),
            })
        return targets

    def normalize(self, raw: dict) -> Auction:
        raise NotImplementedError("Use _normalize_record() with county_target context")

    def _normalize_record(self, raw: dict, county_target: dict) -> Auction:
        raise NotImplementedError("Implement in Step 9")

    async def _fetch(self) -> list[Auction]:
        raise NotImplementedError("Implement in Step 12")
```

- [ ] **Step 4: Run property tests to verify they pass**

```bash
uv run pytest tests/collectors/county_websites/test_county_collector.py::test_name tests/collectors/county_websites/test_county_collector.py::test_source_type -v
```

Expected: 2 PASSED

- [ ] **Step 5: Commit skeleton**

```bash
git add src/tdc_auction_calendar/collectors/county_websites/ tests/collectors/county_websites/
git commit -m "feat(collectors): add CountyWebsiteCollector skeleton (issue #13)"
```

#### Step group B: County target loading tests

- [ ] **Step 6: Add test for loading counties with URLs**

Append to `test_county_collector.py`:

```python
def test_loads_counties_with_urls(collector):
    """Only counties with tax_sale_page_url should be loaded."""
    assert len(collector._county_targets) >= 50
    for target in collector._county_targets:
        assert target["tax_sale_page_url"] is not None
        assert target["state_code"]
        assert target["county_name"]
        assert target["default_sale_type"]
```

- [ ] **Step 7: Run to verify it passes**

```bash
uv run pytest tests/collectors/county_websites/test_county_collector.py::test_loads_counties_with_urls -v
```

Expected: PASS (depends on Task 1 seed data being committed first)

#### Step group C: Normalization (TDD — test first, then implement)

- [ ] **Step 8: Add normalization tests (they will fail)**

Append to `test_county_collector.py`:

```python
def test_normalize_uses_seed_county_info(collector):
    """State and county should come from seed data, not extraction."""
    target = collector._county_targets[0]
    raw = {"sale_date": "2026-06-15", "sale_type": "lien"}
    auction = collector._normalize_record(raw, target)
    assert auction.state == target["state_code"]
    assert auction.county == target["county_name"]
    assert auction.source_url == target["tax_sale_page_url"]
    assert auction.source_type == SourceType.COUNTY_WEBSITE
    assert auction.confidence_score == 0.70


def test_normalize_falls_back_sale_type(collector):
    """Empty/missing sale_type should use state's default."""
    target = collector._county_targets[0]
    raw = {"sale_date": "2026-06-15", "sale_type": ""}
    auction = collector._normalize_record(raw, target)
    assert auction.sale_type == SaleType(target["default_sale_type"])

    raw_missing = {"sale_date": "2026-06-15"}
    auction2 = collector._normalize_record(raw_missing, target)
    assert auction2.sale_type == SaleType(target["default_sale_type"])


def test_normalize_optional_fields(collector):
    """Optional fields should be parsed when present."""
    target = collector._county_targets[0]
    raw = {
        "sale_date": "2026-06-15",
        "sale_type": "lien",
        "end_date": "2026-06-17",
        "deposit_amount": "5000",
        "registration_deadline": "2026-05-01",
    }
    auction = collector._normalize_record(raw, target)
    assert auction.end_date == date(2026, 6, 17)
    assert auction.deposit_amount == Decimal("5000")
    assert auction.registration_deadline == date(2026, 5, 1)


def test_normalize_optional_fields_absent(collector):
    """Absent optional fields should be None."""
    target = collector._county_targets[0]
    raw = {"sale_date": "2026-06-15"}
    auction = collector._normalize_record(raw, target)
    assert auction.end_date is None
    assert auction.deposit_amount is None
    assert auction.registration_deadline is None
```

- [ ] **Step 9: Run normalization tests to verify they fail**

```bash
uv run pytest tests/collectors/county_websites/test_county_collector.py -k "normalize" -v
```

Expected: FAIL — `_normalize_record` raises `NotImplementedError`

- [ ] **Step 10: Implement `_normalize_record()`**

Replace the `_normalize_record` stub in `county_collector.py` with the real implementation. Also add the necessary imports (`date`, `Decimal`, `SaleType`):

```python
from datetime import date
from decimal import Decimal

from tdc_auction_calendar.models.enums import SaleType, SourceType
```

```python
def _normalize_record(self, raw: dict, county_target: dict) -> Auction:
    """Convert a raw extraction record into a validated Auction."""
    return Auction(
        state=county_target["state_code"],
        county=county_target["county_name"],
        start_date=date.fromisoformat(raw["sale_date"]),
        sale_type=SaleType(raw.get("sale_type") or county_target["default_sale_type"]),
        source_type=SourceType.COUNTY_WEBSITE,
        source_url=county_target["tax_sale_page_url"],
        confidence_score=self.confidence_score,
        end_date=date.fromisoformat(raw["end_date"]) if raw.get("end_date") else None,
        deposit_amount=Decimal(raw["deposit_amount"]) if raw.get("deposit_amount") else None,
        registration_deadline=(
            date.fromisoformat(raw["registration_deadline"])
            if raw.get("registration_deadline") else None
        ),
    )
```

- [ ] **Step 11: Run normalization tests to verify they pass**

```bash
uv run pytest tests/collectors/county_websites/test_county_collector.py -k "normalize" -v
```

Expected: 4 PASSED

- [ ] **Step 12: Commit normalization**

```bash
git add src/tdc_auction_calendar/collectors/county_websites/county_collector.py tests/collectors/county_websites/test_county_collector.py
git commit -m "feat(collectors): implement county website normalization with TDD (issue #13)"
```

#### Step group D: Fetch behavior (TDD — tests first, then implement)

- [ ] **Step 13: Add fetch tests (they will fail)**

Append to `test_county_collector.py`. These tests mock `create_scrape_client` and patch `_county_targets` to control the test data:

```python
def _make_collector_with_targets(targets):
    """Create a collector with specific county targets (bypasses seed loading)."""
    collector = CountyWebsiteCollector.__new__(CountyWebsiteCollector)
    collector._county_targets = targets
    return collector


_TEST_TARGETS = [
    {
        "state_code": "FL",
        "county_name": "Duval",
        "tax_sale_page_url": "https://duval.example.com/taxsale",
        "default_sale_type": "lien",
    },
    {
        "state_code": "CO",
        "county_name": "Denver",
        "tax_sale_page_url": "https://denver.example.com/taxlien",
        "default_sale_type": "lien",
    },
]


async def test_fetch_returns_auctions():
    collector = _make_collector_with_targets(_TEST_TARGETS)
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(
        [{"sale_date": "2026-06-15", "sale_type": "lien"}]
    )
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.county_websites.county_collector.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 2
    states = {a.state for a in auctions}
    assert states == {"FL", "CO"}


async def test_fetch_skips_failed_counties():
    collector = _make_collector_with_targets(_TEST_TARGETS)
    mock_client = AsyncMock()
    mock_client.scrape.side_effect = [
        RuntimeError("network error"),
        _mock_scrape_result(
            [{"sale_date": "2026-06-15", "sale_type": "lien"}]
        ),
    ]
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.county_websites.county_collector.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 1
    assert auctions[0].state == "CO"


async def test_fetch_skips_invalid_records():
    collector = _make_collector_with_targets(_TEST_TARGETS[:1])
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result([
        {"sale_date": "2026-06-15", "sale_type": "lien"},
        {"sale_date": "bad-date"},
    ])
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.county_websites.county_collector.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 1


async def test_fetch_filters_past_dates():
    collector = _make_collector_with_targets(_TEST_TARGETS[:1])
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result([
        {"sale_date": "2026-06-15", "sale_type": "lien"},
        {"sale_date": "2020-01-01", "sale_type": "lien"},
    ])
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.county_websites.county_collector.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 1
    assert auctions[0].start_date == date(2026, 6, 15)


async def test_fetch_empty_urls_returns_empty():
    collector = _make_collector_with_targets([])
    auctions = await collector.collect()
    assert auctions == []


async def test_fetch_single_dict_result():
    collector = _make_collector_with_targets(_TEST_TARGETS[:1])
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(
        {"sale_date": "2026-06-15", "sale_type": "lien"}
    )
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.county_websites.county_collector.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 1


async def test_closes_client_on_failure():
    collector = _make_collector_with_targets(_TEST_TARGETS[:1])
    mock_client = AsyncMock()
    mock_client.scrape.side_effect = RuntimeError("network error")
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.county_websites.county_collector.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert auctions == []
    mock_client.close.assert_called_once()
```

- [ ] **Step 14: Run fetch tests to verify they fail**

```bash
uv run pytest tests/collectors/county_websites/test_county_collector.py -k "fetch or closes" -v
```

Expected: FAIL — `_fetch` raises `NotImplementedError`

- [ ] **Step 15: Implement `_fetch()`**

Replace the `_fetch` stub in `county_collector.py` with the real implementation. Add necessary imports:

```python
from decimal import InvalidOperation

from pydantic import ValidationError

from tdc_auction_calendar.collectors.scraping import create_scrape_client
```

```python
async def _fetch(self) -> list[Auction]:
    if not self._county_targets:
        return []

    client = create_scrape_client()
    try:
        all_auctions: list[Auction] = []
        for target in self._county_targets:
            url = target["tax_sale_page_url"]
            try:
                result = await client.scrape(
                    url, schema=CountyAuctionRecord,
                )
            except Exception:
                logger.warning(
                    "county_scrape_failed",
                    collector=self.name,
                    state=target["state_code"],
                    county=target["county_name"],
                    url=url,
                )
                continue

            if isinstance(result.data, list):
                raw_records = result.data
            elif result.data is None:
                raw_records = []
            elif isinstance(result.data, dict):
                raw_records = [result.data]
            else:
                logger.warning(
                    "unexpected_data_type",
                    collector=self.name,
                    county=target["county_name"],
                    data_type=type(result.data).__name__,
                )
                continue

            if not raw_records:
                logger.info(
                    "county_no_results",
                    collector=self.name,
                    state=target["state_code"],
                    county=target["county_name"],
                    url=url,
                )
                continue

            today = date.today()
            for raw in raw_records:
                try:
                    auction = self._normalize_record(raw, target)
                    if auction.start_date < today:
                        continue
                    all_auctions.append(auction)
                except (KeyError, ValueError, ValidationError, InvalidOperation) as exc:
                    logger.error(
                        "normalize_failed",
                        collector=self.name,
                        state=target["state_code"],
                        county=target["county_name"],
                        raw=raw,
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )

        return all_auctions
    finally:
        await client.close()
```

- [ ] **Step 16: Run fetch tests to verify they pass**

```bash
uv run pytest tests/collectors/county_websites/test_county_collector.py -k "fetch or closes" -v
```

Expected: 7 PASSED

- [ ] **Step 17: Commit fetch implementation**

```bash
git add src/tdc_auction_calendar/collectors/county_websites/county_collector.py tests/collectors/county_websites/test_county_collector.py
git commit -m "feat(collectors): implement county website fetch with TDD (issue #13)"
```

#### Step group E: Acceptance test and wiring

- [ ] **Step 18: Create fixture file with URLs matching seed data**

Create `tests/fixtures/county_websites/county_extraction_results.json` — a dict keyed by `tax_sale_page_url` values from `counties.json` (populated in Task 1). Each URL maps to 1-3 extraction result dicts with future dates (2026+).

**Important:** The fixture keys MUST match the real URLs populated in Task 1. To verify, extract the URLs from seed data first:

```bash
python3 -c "
import json
with open('src/tdc_auction_calendar/db/seed/counties.json') as f:
    counties = json.load(f)
urls = [c['tax_sale_page_url'] for c in counties if c.get('tax_sale_page_url')]
print(f'Total URLs: {len(urls)}')
for u in urls[:5]:
    print(f'  {u}')
"
```

Use these URLs as keys in the fixture file. Include a mix of: records with all fields, records with only `sale_date`, and records with empty `sale_type` (to test fallback). Total records across all URLs should be >= 55.

- [ ] **Step 19: Add acceptance test**

Append to `test_county_collector.py`:

```python
async def test_acceptance_50_counties(collector):
    """Integration: fixture data should produce >= 50 county auction records."""
    fixture_path = FIXTURES_DIR / "county_extraction_results.json"
    with open(fixture_path) as f:
        fixture_data = json.load(f)

    def _side_effect(url, **kwargs):
        data = fixture_data.get(url)
        return _mock_scrape_result(data, url=url)

    mock_client = AsyncMock()
    mock_client.scrape.side_effect = _side_effect
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.county_websites.county_collector.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) >= 50
    assert all(a.source_type == SourceType.COUNTY_WEBSITE for a in auctions)
    assert all(a.confidence_score == 0.70 for a in auctions)
```

- [ ] **Step 20: Run acceptance test**

```bash
uv run pytest tests/collectors/county_websites/test_county_collector.py::test_acceptance_50_counties -v
```

Expected: PASS with >= 50 auctions

- [ ] **Step 21: Wire up exports**

Modify `src/tdc_auction_calendar/collectors/__init__.py` — add import and __all__ entry for `CountyWebsiteCollector`:

```python
from tdc_auction_calendar.collectors.county_websites import CountyWebsiteCollector
```

Add `"CountyWebsiteCollector"` to the `__all__` list.

- [ ] **Step 22: Run full test suite**

```bash
uv run pytest
```

Expected: All tests pass (288 existing + new county website tests)

- [ ] **Step 23: Commit wiring and acceptance test**

```bash
git add src/tdc_auction_calendar/collectors/__init__.py tests/
git commit -m "feat(collectors): wire up CountyWebsiteCollector exports + acceptance test (issue #13)"
```
