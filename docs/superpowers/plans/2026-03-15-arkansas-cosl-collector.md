# Arkansas COSL Collector — Regex Rewrite Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the LLM-based ArkansasCollector with a deterministic regex parser for the COSL catalog page.

**Architecture:** Fetch markdown from `https://www.cosl.org/Home/Contents` via ScrapeClient (no extraction). Parse with regex to extract date-county pairs. Normalize into Auction objects. Same collector name/registration — drop-in replacement.

**Tech Stack:** Python stdlib (`re`, `datetime`), existing ScrapeClient, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/tdc_auction_calendar/collectors/state_agencies/arkansas.py` | Modify | Collector + `parse_catalog()` |
| `tests/collectors/state_agencies/test_arkansas.py` | Rewrite | All tests for new parsing logic |
| `tests/fixtures/state_agencies/arkansas_cosl.md` | Create | Markdown fixture (replaces `arkansas_cosl.json`) |
| `tests/fixtures/state_agencies/arkansas_cosl.json` | Delete | Old JSON fixture for LLM extraction |

---

## Chunk 1: parse_catalog() with TDD

### Task 1: Create markdown fixture

**Files:**
- Create: `tests/fixtures/state_agencies/arkansas_cosl.md`
- Delete: `tests/fixtures/state_agencies/arkansas_cosl.json`

- [ ] **Step 1: Create the markdown fixture**

Trimmed from `data/research/sub/cosl_catalog.md`. Includes: the first entry with location info (SEVIER 3/5/2026), a multi-county date (7/14/2026 with PRAIRIE, LONOKE, ARKANSAS), a two-word county (8/19/2026 with ST FRANCIS), and a single-county date (7/28/2026 with GARLAND). Also includes some header text before the first date to test that counties-before-date are skipped.

```markdown
# Public Auction Catalog

## Table Of Contents

[Past Sale Results](https://www.cosl.org/Home/Contents/Home/SaleResults)

3/5/2026 11:00 AM

Sevier County Courthouse, Conference Room 103

De Queen

[ SEVIER](#)

[  View Sale Results](https://www.cosl.org/Home/Contents/Home/PostSaleResult?county=SEVI)

7/14/2026 12:00 AM

[ PRAIRIE](#)

[  View Catalog](https://www.cosl.org/Home/Contents/Home/CatalogView?county=PRAI&saledate=7%2F14%2F2026%2012%3A00%3A00%20AM)

[ LONOKE](#)

[  View Catalog](https://www.cosl.org/Home/Contents/Home/CatalogView?county=LONO&saledate=7%2F14%2F2026%2012%3A00%3A00%20AM)

[ ARKANSAS](#)

[  View Catalog](https://www.cosl.org/Home/Contents/Home/CatalogView?county=ARKA&saledate=7%2F14%2F2026%2012%3A00%3A00%20AM)

7/28/2026 12:00 AM

[ GARLAND](#)

[  View Catalog](https://www.cosl.org/Home/Contents/Home/CatalogView?county=GARL&saledate=7%2F28%2F2026%2012%3A00%3A00%20AM)

8/19/2026 12:00 AM

[ CRITTENDEN](#)

[  View Catalog](https://www.cosl.org/Home/Contents/Home/CatalogView?county=CRIT&saledate=8%2F19%2F2026%2012%3A00%3A00%20AM)

[ CROSS](#)

[  View Catalog](https://www.cosl.org/Home/Contents/Home/CatalogView?county=CROS&saledate=8%2F19%2F2026%2012%3A00%3A00%20AM)

[ ST FRANCIS](#)

[  View Catalog](https://www.cosl.org/Home/Contents/Home/CatalogView?county=STFR&saledate=8%2F19%2F2026%2012%3A00%3A00%20AM)

9/23/2026 12:00 AM

[ SEVIER](#)

[  View Catalog](https://www.cosl.org/Home/Contents/Home/CatalogView?county=SEVI&saledate=9%2F23%2F2026%2012%3A00%3A00%20AM)
```

- [ ] **Step 2: Delete old JSON fixture**

```bash
git rm tests/fixtures/state_agencies/arkansas_cosl.json
```

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/state_agencies/arkansas_cosl.md
git commit -m "test: replace Arkansas JSON fixture with markdown fixture (#47)"
```

### Task 2: Write parse_catalog() tests

**Files:**
- Modify: `tests/collectors/state_agencies/test_arkansas.py`

- [ ] **Step 1: Rewrite test file with parse_catalog tests**

Replace the entire test file. The old tests for LLM-based `_fetch()` no longer apply.

```python
"""Tests for Arkansas COSL collector."""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from tdc_auction_calendar.collectors.state_agencies.arkansas import (
    ArkansasCollector,
    parse_catalog,
)
from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.models.enums import SaleType, SourceType

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "state_agencies"


def _load_fixture() -> str:
    return (FIXTURES_DIR / "arkansas_cosl.md").read_text()


@pytest.fixture()
def collector():
    return ArkansasCollector()


# ── collector identity tests ─────────────────────────────────────────


def test_name(collector):
    assert collector.name == "arkansas_state_agency"


def test_source_type(collector):
    assert collector.source_type == SourceType.STATE_AGENCY


# ── parse_catalog unit tests ──────────────────────────────────────────


def test_parse_catalog_basic():
    md = "7/28/2026 12:00 AM\n\n[ GARLAND](#)\n"
    result = parse_catalog(md)
    assert result == [{"sale_date": "2026-07-28", "county": "Garland"}]


def test_parse_catalog_multi_county_date():
    md = (
        "7/14/2026 12:00 AM\n\n"
        "[ PRAIRIE](#)\n\n"
        "[  View Catalog](https://example.com)\n\n"
        "[ LONOKE](#)\n\n"
        "[ ARKANSAS](#)\n"
    )
    result = parse_catalog(md)
    assert len(result) == 3
    assert all(r["sale_date"] == "2026-07-14" for r in result)
    assert [r["county"] for r in result] == ["Prairie", "Lonoke", "Arkansas"]


def test_parse_catalog_county_title_case():
    md = (
        "8/19/2026 12:00 AM\n\n"
        "[ ST FRANCIS](#)\n\n"
        "[ HOT SPRING](#)\n"
    )
    result = parse_catalog(md)
    assert [r["county"] for r in result] == ["St Francis", "Hot Spring"]


def test_parse_catalog_empty():
    assert parse_catalog("") == []
    assert parse_catalog("no dates or counties here") == []


def test_parse_catalog_date_format():
    """M/D/YYYY correctly converts to YYYY-MM-DD with zero-padded month/day."""
    md = "3/5/2026 11:00 AM\n\n[ SEVIER](#)\n"
    result = parse_catalog(md)
    assert result[0]["sale_date"] == "2026-03-05"


def test_parse_catalog_counties_before_date_skipped():
    md = "[ ORPHAN](#)\n\n7/14/2026 12:00 AM\n\n[ PRAIRIE](#)\n"
    result = parse_catalog(md)
    assert len(result) == 1
    assert result[0]["county"] == "Prairie"


def test_parse_catalog_duplicate_county_different_dates():
    md = (
        "3/5/2026 11:00 AM\n\n[ SEVIER](#)\n\n"
        "9/23/2026 12:00 AM\n\n[ SEVIER](#)\n"
    )
    result = parse_catalog(md)
    assert len(result) == 2
    assert result[0] == {"sale_date": "2026-03-05", "county": "Sevier"}
    assert result[1] == {"sale_date": "2026-09-23", "county": "Sevier"}


def test_parse_catalog_full_fixture():
    """Fixture has 5 dates, 9 total county entries."""
    md = _load_fixture()
    result = parse_catalog(md)
    assert len(result) == 9
    # Spot-check first and last
    assert result[0] == {"sale_date": "2026-03-05", "county": "Sevier"}
    assert result[-1] == {"sale_date": "2026-09-23", "county": "Sevier"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/collectors/state_agencies/test_arkansas.py -v
```

Expected: FAIL — `parse_catalog` doesn't exist yet.

- [ ] **Step 3: Commit**

```bash
git add tests/collectors/state_agencies/test_arkansas.py
git commit -m "test: add parse_catalog unit tests for Arkansas COSL collector (#47)"
```

### Task 3: Implement parse_catalog()

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/state_agencies/arkansas.py`

- [ ] **Step 1: Add parse_catalog function**

Add this function to the module (above the class). Remove `ArkansasAuctionRecord`, `_PROMPT`, and the `ExtractionError` import. Update `_URL`.

The full file should become:

```python
"""Arkansas state agency collector — COSL tax deed sales."""

from __future__ import annotations

import re
from datetime import date, datetime

import structlog
from pydantic import ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping import create_scrape_client
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType

logger = structlog.get_logger()

_URL = "https://www.cosl.org/Home/Contents"

_DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
_COUNTY_RE = re.compile(r"\[\s*([A-Z ]+?)\s*\]\(#\)")


def parse_catalog(markdown: str) -> list[dict]:
    """Extract (sale_date, county) pairs from COSL catalog markdown.

    Walks lines sequentially. A date line sets current_date; each subsequent
    county link line emits a record pairing that date with the county (title-cased).
    Counties appearing before any date line are skipped.
    """
    records: list[dict] = []
    current_date: str | None = None

    for line in markdown.splitlines():
        date_match = _DATE_RE.search(line)
        if date_match:
            parsed = datetime.strptime(date_match.group(1), "%m/%d/%Y")
            current_date = parsed.strftime("%Y-%m-%d")
            continue

        if current_date is None:
            continue

        county_match = _COUNTY_RE.search(line)
        if county_match:
            county = county_match.group(1).strip().title()
            records.append({"sale_date": current_date, "county": county})

    return records


class ArkansasCollector(BaseCollector):
    """Collects Arkansas tax deed sale dates from COSL."""

    @property
    def name(self) -> str:
        return "arkansas_state_agency"

    @property
    def source_type(self) -> SourceType:
        return SourceType.STATE_AGENCY

    async def _fetch(self) -> list[Auction]:
        client = create_scrape_client()
        try:
            result = await client.scrape(_URL)
        finally:
            await client.close()

        markdown = result.fetch.markdown or ""
        raw_records = parse_catalog(markdown)

        if markdown and not raw_records:
            logger.warning(
                "no_records_parsed",
                collector=self.name,
                url=_URL,
                markdown_length=len(markdown),
            )

        auctions: list[Auction] = []
        for raw in raw_records:
            try:
                auctions.append(self.normalize(raw))
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                logger.error(
                    "normalize_failed",
                    collector=self.name,
                    raw=raw,
                    error=str(exc),
                )

        return auctions

    def normalize(self, raw: dict) -> Auction:
        """Convert a raw COSL record into a validated Auction."""
        return Auction(
            state="AR",
            county=raw["county"],
            start_date=date.fromisoformat(raw["sale_date"]),
            sale_type=SaleType(raw.get("sale_type", "deed")),
            source_type=SourceType.STATE_AGENCY,
            source_url=_URL,
            confidence_score=0.85,
        )
```

- [ ] **Step 2: Run parse_catalog tests**

```bash
uv run pytest tests/collectors/state_agencies/test_arkansas.py -v -k "parse_catalog"
```

Expected: All 8 `test_parse_catalog_*` tests PASS.

- [ ] **Step 3: Commit**

```bash
git add src/tdc_auction_calendar/collectors/state_agencies/arkansas.py
git commit -m "feat: rewrite ArkansasCollector with regex-based parse_catalog (#47)"
```

---

## Chunk 2: Integration tests + cleanup

### Task 4: Write integration tests

**Files:**
- Modify: `tests/collectors/state_agencies/test_arkansas.py`

- [ ] **Step 1: Add integration tests to test file**

Append these tests to the existing test file:

```python
# ── normalize tests ───────────────────────────────────────────────────


def test_normalize_valid_record(collector):
    raw = {"county": "Pulaski", "sale_date": "2026-06-10"}
    auction = collector.normalize(raw)
    assert auction.state == "AR"
    assert auction.county == "Pulaski"
    assert auction.start_date == date(2026, 6, 10)
    assert auction.sale_type == SaleType.DEED
    assert auction.source_type == SourceType.STATE_AGENCY
    assert auction.confidence_score == 0.85
    assert auction.source_url == "https://www.cosl.org/Home/Contents"


def test_normalize_missing_county_raises(collector):
    with pytest.raises((ValidationError, ValueError, KeyError)):
        collector.normalize({"sale_date": "2026-06-10"})


def test_normalize_invalid_date_raises(collector):
    raw = {"county": "Pulaski", "sale_date": "not-a-date"}
    with pytest.raises((ValidationError, ValueError)):
        collector.normalize(raw)


# ── _fetch integration tests ─────────────────────────────────────────


def _mock_scrape_result(markdown: str) -> ScrapeResult:
    return ScrapeResult(
        fetch=FetchResult(
            url="https://www.cosl.org/Home/Contents",
            status_code=200,
            fetcher="cloudflare",
            markdown=markdown,
        ),
    )


async def test_fetch_returns_auctions(collector):
    fixture_md = _load_fixture()
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(fixture_md)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.arkansas.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 9
    assert all(a.state == "AR" for a in auctions)
    assert all(a.source_type == SourceType.STATE_AGENCY for a in auctions)
    assert all(a.source_url == "https://www.cosl.org/Home/Contents" for a in auctions)


async def test_fetch_empty_markdown_returns_empty(collector):
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result("")
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.arkansas.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert auctions == []


async def test_collect_dedup(collector):
    """Duplicate county+date pairs are deduplicated."""
    md = "7/14/2026 12:00 AM\n\n[ PRAIRIE](#)\n\n[ PRAIRIE](#)\n"
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(md)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.state_agencies.arkansas.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    assert len(auctions) == 1
```

- [ ] **Step 2: Run all tests**

```bash
uv run pytest tests/collectors/state_agencies/test_arkansas.py -v
```

Expected: All tests PASS.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest
```

Expected: No regressions.

- [ ] **Step 4: Commit**

```bash
git add tests/collectors/state_agencies/test_arkansas.py
git commit -m "test: add integration tests for rewritten ArkansasCollector (#47)"
```

### Task 5: Run full test suite and commit

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest
```

Expected: No regressions. All Arkansas tests pass, existing tests unaffected.

- [ ] **Step 2: Verify no stale imports remain in arkansas.py**

Open `src/tdc_auction_calendar/collectors/state_agencies/arkansas.py` and confirm:
- No `BaseModel` import from pydantic (only `ValidationError`)
- No `ExtractionError` import
- No `_PROMPT` or `ArkansasAuctionRecord`

**Note:** The `ExtractionError` raise-on-all-fail behavior from the old `_fetch()` is intentionally removed. With deterministic parsing, normalization failures indicate a code bug, not LLM output variance. The per-record error logging is retained.
