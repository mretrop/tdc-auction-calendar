# Purdue Vendor Collector Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a collector that scrapes pbfcm.com/taxsale.html, downloads per-county PDFs, and extracts exact sale dates to produce Auction records for Texas tax foreclosure sales.

**Architecture:** Two-phase approach — ScrapeClient fetches the HTML listing page, then httpx downloads individual PDFs which are parsed with pypdf for exact sale dates. New `collectors/vendors/` directory for this and future vendor collectors.

**Tech Stack:** Python, pypdf, httpx, ScrapeClient, Pydantic, pytest

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/tdc_auction_calendar/collectors/vendors/__init__.py` | Export PurdueCollector |
| Create | `src/tdc_auction_calendar/collectors/vendors/purdue.py` | Collector: HTML parsing, PDF download, date extraction, normalization |
| Modify | `src/tdc_auction_calendar/models/enums.py:19-37` | Add `VENDOR` to SourceType, `PURDUE` to Vendor |
| Modify | `src/tdc_auction_calendar/collectors/orchestrator.py:1-48` | Register PurdueCollector |
| Modify | `src/tdc_auction_calendar/collectors/__init__.py` | Export PurdueCollector |
| Create | `tests/collectors/vendors/__init__.py` | Test package init |
| Create | `tests/collectors/vendors/test_purdue.py` | All unit tests |
| ~~Create~~ | ~~`tests/fixtures/vendors/sample_purdue_sale.pdf`~~ | Not needed — tests use mocked pypdf and string inputs |
| Modify | `pyproject.toml` | Add pypdf dependency |

---

## Chunk 1: Foundation (Enums + Dependency)

### Task 1: Add pypdf dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pypdf to dependencies**

In `pyproject.toml`, add `"pypdf>=4.0"` to the `dependencies` list.

- [ ] **Step 2: Sync dependencies**

Run: `uv sync`
Expected: Clean install with pypdf added to lockfile.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pypdf dependency for PDF text extraction"
```

### Task 2: Add SourceType.VENDOR and Vendor.PURDUE enums

**Files:**
- Modify: `src/tdc_auction_calendar/models/enums.py:19-37`
- Test: `tests/models/test_enums.py` (if exists, otherwise inline verification)

- [ ] **Step 1: Write the failing test**

Create or append to tests that verify the new enum values exist:

```python
# In a test file or verify interactively
from tdc_auction_calendar.models.enums import SourceType, Vendor
assert SourceType.VENDOR == "vendor"
assert Vendor.PURDUE == "Purdue, Brandon, Fielder, Collins & Mott"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -c "from tdc_auction_calendar.models.enums import SourceType; print(SourceType.VENDOR)"`
Expected: AttributeError

- [ ] **Step 3: Add enum values**

In `src/tdc_auction_calendar/models/enums.py`:

Add to `SourceType` (after `COUNTY_WEBSITE`):
```python
    VENDOR = "vendor"
```

Add to `Vendor` (after `SRI`):
```python
    PURDUE = "Purdue, Brandon, Fielder, Collins & Mott"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -c "from tdc_auction_calendar.models.enums import SourceType, Vendor; print(SourceType.VENDOR); print(Vendor.PURDUE)"`
Expected: `vendor` and `Purdue, Brandon, Fielder, Collins & Mott`

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/models/enums.py
git commit -m "feat: add SourceType.VENDOR and Vendor.PURDUE enums"
```

---

## Chunk 2: HTML Parsing + Date Extraction (Pure Functions)

### Task 3: Write and test HTML link extraction

**Files:**
- Create: `src/tdc_auction_calendar/collectors/vendors/__init__.py`
- Create: `src/tdc_auction_calendar/collectors/vendors/purdue.py`
- Create: `tests/collectors/vendors/__init__.py`
- Create: `tests/collectors/vendors/test_purdue.py`

- [ ] **Step 1: Write the failing tests for `parse_listing_markdown()`**

```python
# tests/collectors/vendors/test_purdue.py
"""Tests for Purdue vendor collector."""

from tdc_auction_calendar.collectors.vendors.purdue import parse_listing_markdown

# Sample markdown matching the structure from data/research/purdue.md
SAMPLE_MARKDOWN = """\
* BRAZORIA COUNTY
   * [Brazoria County](docs/taxdocs/sales/04-2026brazoriataxsale.pdf)
* FORT BEND COUNTY
   * [Ft Bend County Pct 2](docs/taxdocs/sales/04-2026ftbendpct2taxsale.pdf)
   * [Ft Bend County Pct 3](docs/taxdocs/sales/04-2026ftbendpct3taxsale.pdf)
* CALDWELL COUNTY
   * [Manufactured Home Sale - March 17, 2026 at 10:00 am](docs/taxdocs/sales/03-17-2025lulingmanufacturedhomesale.pdf)
"""


def test_parse_listing_extracts_counties_and_urls():
    results = parse_listing_markdown(SAMPLE_MARKDOWN)
    counties = [r[0] for r in results]
    assert "Brazoria" in counties
    assert "Fort Bend" in counties
    assert "Caldwell" in counties


def test_parse_listing_builds_full_urls():
    results = parse_listing_markdown(SAMPLE_MARKDOWN)
    urls = [r[1] for r in results]
    assert all(url.startswith("https://www.pbfcm.com/") for url in urls)


def test_parse_listing_multi_precinct_produces_multiple_entries():
    results = parse_listing_markdown(SAMPLE_MARKDOWN)
    fort_bend_entries = [r for r in results if r[0] == "Fort Bend"]
    assert len(fort_bend_entries) == 2


def test_parse_listing_empty_markdown():
    results = parse_listing_markdown("")
    assert results == []
```

- [ ] **Step 2: Create package files and run tests to verify they fail**

Create `src/tdc_auction_calendar/collectors/vendors/__init__.py` (empty for now).
Create `tests/collectors/vendors/__init__.py` (empty).

Run: `uv run pytest tests/collectors/vendors/test_purdue.py -v`
Expected: ImportError — `parse_listing_markdown` doesn't exist yet.

- [ ] **Step 3: Implement `parse_listing_markdown()`**

```python
# src/tdc_auction_calendar/collectors/vendors/purdue.py
"""Purdue vendor collector — Texas tax foreclosure sales from pbfcm.com."""

from __future__ import annotations

import re

_BASE_URL = "https://www.pbfcm.com"
_LISTING_URL = f"{_BASE_URL}/taxsale.html"

# Matches "* COUNTY NAME COUNTY" at start of line (top-level list item)
_COUNTY_RE = re.compile(r"^\*\s+([A-Z\s]+?)\s*COUNTY\s*$", re.MULTILINE)

# Matches "[link text](relative/path.pdf)" nested under a county
_PDF_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+\.pdf)\)")


def parse_listing_markdown(markdown: str) -> list[tuple[str, str]]:
    """Parse the listing page markdown into (county_name, full_pdf_url) tuples.

    Returns one entry per PDF link. Multi-precinct counties produce
    multiple entries with the same county name.
    """
    results: list[tuple[str, str]] = []
    current_county: str | None = None

    for line in markdown.splitlines():
        county_match = _COUNTY_RE.match(line.strip())
        if county_match:
            current_county = county_match.group(1).strip().title()
            continue

        if current_county:
            pdf_match = _PDF_LINK_RE.search(line)
            if pdf_match:
                relative_url = pdf_match.group(2)
                full_url = f"{_BASE_URL}/{relative_url}"
                results.append((current_county, full_url))

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_purdue.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/ tests/collectors/vendors/
git commit -m "feat: add parse_listing_markdown for Purdue HTML extraction"
```

### Task 4: Write and test PDF date extraction

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/purdue.py`
- Modify: `tests/collectors/vendors/test_purdue.py`

- [ ] **Step 1: Write the failing tests for `extract_sale_date()`**

Add to `tests/collectors/vendors/test_purdue.py`:

```python
from datetime import date
from tdc_auction_calendar.collectors.vendors.purdue import extract_sale_date


def test_extract_date_with_sale_date_label():
    text = "NOTICE OF SALE\nSale Date: April 7, 2026\nLocation: County Courthouse"
    assert extract_sale_date(text) == date(2026, 4, 7)


def test_extract_date_with_date_of_sale_label():
    text = "Date of Sale: March 17, 2026 at 10:00 AM"
    assert extract_sale_date(text) == date(2026, 3, 17)


def test_extract_date_month_name_no_label():
    text = "Tax Foreclosure\nThe sale will be held on June 3, 2026"
    assert extract_sale_date(text) == date(2026, 6, 3)


def test_extract_date_numeric_format():
    text = "Sale scheduled for 04/07/2026 at the courthouse"
    assert extract_sale_date(text) == date(2026, 4, 7)


def test_extract_date_with_ordinal():
    text = "Sale Date: April 7th, 2026"
    assert extract_sale_date(text) == date(2026, 4, 7)


def test_extract_date_returns_none_when_no_date():
    text = "This PDF has no date information whatsoever."
    assert extract_sale_date(text) is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_purdue.py::test_extract_date_with_sale_date_label -v`
Expected: ImportError — `extract_sale_date` doesn't exist.

- [ ] **Step 4: Implement `extract_sale_date()`**

Add to `src/tdc_auction_calendar/collectors/vendors/purdue.py`:

```python
from datetime import date, datetime

_MONTHS = (
    "January|February|March|April|May|June|"
    "July|August|September|October|November|December"
)

# Pattern 1: "Sale Date: April 7, 2026" or "Date of Sale: April 7, 2026"
_DATE_CONTEXTUAL_RE = re.compile(
    rf"(?:Sale\s+Date|Date\s+of\s+Sale)[:\s]+"
    rf"({_MONTHS})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s*(\d{{4}})",
    re.IGNORECASE,
)

# Pattern 2: "April 7, 2026" (month name, no label required)
_DATE_MONTH_NAME_RE = re.compile(
    rf"({_MONTHS})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s*(\d{{4}})",
    re.IGNORECASE,
)

# Pattern 3: "04/07/2026"
_DATE_NUMERIC_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def extract_sale_date(text: str) -> date | None:
    """Extract the sale date from PDF text content.

    Tries contextual patterns first (with "Sale Date" label),
    then general month-name patterns, then numeric.
    Returns None if no date found.
    """
    # Try contextual match first
    m = _DATE_CONTEXTUAL_RE.search(text)
    if m:
        return _parse_month_name_match(m)

    # Try general month name
    m = _DATE_MONTH_NAME_RE.search(text)
    if m:
        return _parse_month_name_match(m)

    # Try numeric
    m = _DATE_NUMERIC_RE.search(text)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(year, month, day)

    return None


def _parse_month_name_match(m: re.Match) -> date:
    """Convert a regex match with (month_name, day, year) groups to a date."""
    month_str, day_str, year_str = m.group(1), m.group(2), m.group(3)
    dt = datetime.strptime(f"{month_str} {day_str} {year_str}", "%B %d %Y")
    return dt.date()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_purdue.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/purdue.py tests/collectors/vendors/test_purdue.py
git commit -m "feat: add extract_sale_date for Purdue PDF date parsing"
```

---

## Chunk 3: PDF Download + Collector Class

### Task 5: Write and test PDF download + text extraction

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/purdue.py`
- Modify: `tests/collectors/vendors/test_purdue.py`

- [ ] **Step 1: Write the failing test for `download_and_parse_pdf()`**

```python
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from tdc_auction_calendar.collectors.vendors.purdue import download_and_parse_pdf


async def test_download_and_parse_pdf_extracts_date(tmp_path):
    """Test PDF download + date extraction with a mocked httpx response and pypdf."""
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()

    # Mock httpx response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"%PDF-fake-content"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    # Mock pypdf to return known text
    with patch(
        "tdc_auction_calendar.collectors.vendors.purdue.PdfReader"
    ) as mock_reader_cls:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Sale Date: April 7, 2026\nProperties:"
        mock_reader_cls.return_value.pages = [mock_page]

        result = await download_and_parse_pdf(
            mock_client, "https://www.pbfcm.com/docs/test.pdf", pdf_dir
        )

    assert result == date(2026, 4, 7)


async def test_download_and_parse_pdf_returns_none_on_http_error(tmp_path):
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()

    mock_response = MagicMock()
    mock_response.status_code = 404

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    result = await download_and_parse_pdf(
        mock_client, "https://www.pbfcm.com/docs/missing.pdf", pdf_dir
    )
    assert result is None


async def test_download_and_parse_pdf_uses_cache(tmp_path):
    """If PDF already exists and is fresh, don't re-download."""
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()

    # Pre-create cached file
    cached = pdf_dir / "test.pdf"
    cached.write_bytes(b"%PDF-cached")

    mock_client = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.vendors.purdue.PdfReader"
    ) as mock_reader_cls:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Sale Date: June 1, 2026"
        mock_reader_cls.return_value.pages = [mock_page]

        result = await download_and_parse_pdf(
            mock_client, "https://www.pbfcm.com/docs/test.pdf", pdf_dir
        )

    # Should NOT have called httpx get (used cache)
    mock_client.get.assert_not_called()
    assert result == date(2026, 6, 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_purdue.py::test_download_and_parse_pdf_extracts_date -v`
Expected: ImportError.

- [ ] **Step 3: Implement `download_and_parse_pdf()`**

Add to `src/tdc_auction_calendar/collectors/vendors/purdue.py`:

```python
import asyncio
import time
from pathlib import Path

import httpx
import structlog
from pypdf import PdfReader

logger = structlog.get_logger()

_PDF_CACHE_DIR = Path("data/research/purdue_pdfs")
_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
_DOWNLOAD_DELAY = 0.5  # seconds between PDF downloads


def _is_cache_fresh(path: Path) -> bool:
    """Check if a cached PDF is less than 7 days old."""
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < _CACHE_TTL_SECONDS


async def download_and_parse_pdf(
    client: httpx.AsyncClient,
    url: str,
    cache_dir: Path | None = None,
) -> date | None:
    """Download a PDF (with caching), extract text, and parse the sale date.

    Returns None if download fails, text extraction fails, or no date found.
    """
    if cache_dir is None:
        cache_dir = _PDF_CACHE_DIR

    cache_dir.mkdir(parents=True, exist_ok=True)
    filename = url.rsplit("/", 1)[-1]
    cached_path = cache_dir / filename

    # Download if not cached or stale
    if not _is_cache_fresh(cached_path):
        response = await client.get(url)
        if response.status_code != 200:
            logger.warning(
                "pdf_download_failed",
                url=url,
                status_code=response.status_code,
            )
            return None
        cached_path.write_bytes(response.content)

    # Extract text
    try:
        reader = PdfReader(cached_path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        logger.warning("pdf_text_extraction_failed", url=url, error=str(exc))
        return None

    # Parse date
    sale_date = extract_sale_date(text)
    if sale_date is None:
        logger.warning("pdf_no_date_found", url=url)
    return sale_date
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_purdue.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/purdue.py tests/collectors/vendors/test_purdue.py
git commit -m "feat: add download_and_parse_pdf with caching and TTL"
```

### Task 6: Implement PurdueCollector class

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/purdue.py`
- Modify: `tests/collectors/vendors/test_purdue.py`

- [ ] **Step 1: Write the failing tests for PurdueCollector**

```python
import pytest
from pydantic import ValidationError
from tdc_auction_calendar.collectors.vendors.purdue import PurdueCollector
from tdc_auction_calendar.collectors.scraping.client import ScrapeResult
from tdc_auction_calendar.collectors.scraping.fetchers.protocol import FetchResult
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor


@pytest.fixture()
def collector():
    return PurdueCollector()


def test_name(collector):
    assert collector.name == "purdue_vendor"


def test_source_type(collector):
    assert collector.source_type == SourceType.VENDOR


def test_normalize(collector):
    raw = {
        "county": "Brazoria",
        "date": "2026-04-07",
        "pdf_url": "https://www.pbfcm.com/docs/taxdocs/sales/04-2026brazoriataxsale.pdf",
    }
    auction = collector.normalize(raw)
    assert auction.state == "TX"
    assert auction.county == "Brazoria"
    assert auction.start_date == date(2026, 4, 7)
    assert auction.sale_type == SaleType.DEED
    assert auction.source_type == SourceType.VENDOR
    assert auction.confidence_score == 0.80
    assert auction.vendor == Vendor.PURDUE
    assert auction.source_url == raw["pdf_url"]


def test_normalize_missing_county_raises(collector):
    raw = {"date": "2026-04-07", "pdf_url": "https://example.com/test.pdf"}
    with pytest.raises((KeyError, ValueError, ValidationError)):
        collector.normalize(raw)


async def test_fetch_end_to_end(collector):
    """Full _fetch with mocked ScrapeClient and mocked PDF downloads."""
    markdown = """\
* BRAZORIA COUNTY
   * [Brazoria County](docs/taxdocs/sales/04-2026brazoriataxsale.pdf)
* DALLAS COUNTY
   * [Dallas County](docs/taxdocs/sales/04-2026dallastaxsale.pdf)
"""
    mock_scrape_client = AsyncMock()
    mock_scrape_client.scrape.return_value = ScrapeResult(
        fetch=FetchResult(
            url="https://www.pbfcm.com/taxsale.html",
            status_code=200,
            fetcher="cloudflare",
            markdown=markdown,
        ),
    )
    mock_scrape_client.close = AsyncMock()

    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_response.content = b"%PDF-fake"

    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(return_value=mock_http_response)
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.create_scrape_client",
            return_value=mock_scrape_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.httpx.AsyncClient",
            return_value=mock_http_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.PdfReader"
        ) as mock_reader_cls,
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.asyncio.sleep",
            new_callable=AsyncMock,
        ),
    ):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Sale Date: April 7, 2026"
        mock_reader_cls.return_value.pages = [mock_page]

        auctions = await collector._fetch()

    assert len(auctions) == 2
    assert all(a.state == "TX" for a in auctions)
    assert all(a.sale_type == SaleType.DEED for a in auctions)
    counties = {a.county for a in auctions}
    assert counties == {"Brazoria", "Dallas"}


async def test_fetch_skips_pdf_failures(collector):
    """If one PDF fails, other counties still produce records."""
    markdown = """\
* BRAZORIA COUNTY
   * [Brazoria County](docs/taxdocs/sales/04-2026brazoriataxsale.pdf)
* DALLAS COUNTY
   * [Dallas County](docs/taxdocs/sales/04-2026dallastaxsale.pdf)
"""
    mock_scrape_client = AsyncMock()
    mock_scrape_client.scrape.return_value = ScrapeResult(
        fetch=FetchResult(
            url="https://www.pbfcm.com/taxsale.html",
            status_code=200,
            fetcher="cloudflare",
            markdown=markdown,
        ),
    )
    mock_scrape_client.close = AsyncMock()

    # First PDF succeeds, second fails (404)
    success_response = MagicMock()
    success_response.status_code = 200
    success_response.content = b"%PDF-fake"

    fail_response = MagicMock()
    fail_response.status_code = 404

    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(side_effect=[success_response, fail_response])
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.create_scrape_client",
            return_value=mock_scrape_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.httpx.AsyncClient",
            return_value=mock_http_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.PdfReader"
        ) as mock_reader_cls,
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.asyncio.sleep",
            new_callable=AsyncMock,
        ),
    ):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Sale Date: April 7, 2026"
        mock_reader_cls.return_value.pages = [mock_page]

        auctions = await collector._fetch()

    assert len(auctions) == 1
    assert auctions[0].county == "Brazoria"


async def test_collect_deduplicates_same_date_precincts(collector):
    """Multi-precinct counties with same sale date collapse to one record via dedup."""
    markdown = """\
* FORT BEND COUNTY
   * [Ft Bend County Pct 2](docs/taxdocs/sales/04-2026ftbendpct2taxsale.pdf)
   * [Ft Bend County Pct 3](docs/taxdocs/sales/04-2026ftbendpct3taxsale.pdf)
"""
    mock_scrape_client = AsyncMock()
    mock_scrape_client.scrape.return_value = ScrapeResult(
        fetch=FetchResult(
            url="https://www.pbfcm.com/taxsale.html",
            status_code=200,
            fetcher="cloudflare",
            markdown=markdown,
        ),
    )
    mock_scrape_client.close = AsyncMock()

    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_response.content = b"%PDF-fake"

    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(return_value=mock_http_response)
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.create_scrape_client",
            return_value=mock_scrape_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.httpx.AsyncClient",
            return_value=mock_http_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.PdfReader"
        ) as mock_reader_cls,
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.asyncio.sleep",
            new_callable=AsyncMock,
        ),
    ):
        mock_page = MagicMock()
        # Both precincts have same sale date
        mock_page.extract_text.return_value = "Sale Date: April 7, 2026"
        mock_reader_cls.return_value.pages = [mock_page]

        # Use collect() (not _fetch()) to trigger dedup
        auctions = await collector.collect()

    # Two precincts, same county + date → deduped to 1
    assert len(auctions) == 1
    assert auctions[0].county == "Fort Bend"


async def test_fetch_returns_empty_when_all_pdfs_fail(collector):
    """If every PDF fails, return empty list and log error."""
    markdown = """\
* BRAZORIA COUNTY
   * [Brazoria County](docs/taxdocs/sales/04-2026brazoriataxsale.pdf)
"""
    mock_scrape_client = AsyncMock()
    mock_scrape_client.scrape.return_value = ScrapeResult(
        fetch=FetchResult(
            url="https://www.pbfcm.com/taxsale.html",
            status_code=200,
            fetcher="cloudflare",
            markdown=markdown,
        ),
    )
    mock_scrape_client.close = AsyncMock()

    fail_response = MagicMock()
    fail_response.status_code = 404

    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(return_value=fail_response)
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.create_scrape_client",
            return_value=mock_scrape_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.httpx.AsyncClient",
            return_value=mock_http_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.purdue.asyncio.sleep",
            new_callable=AsyncMock,
        ),
    ):
        auctions = await collector._fetch()

    assert auctions == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/collectors/vendors/test_purdue.py::test_name -v`
Expected: ImportError — `PurdueCollector` doesn't exist.

- [ ] **Step 3: Implement PurdueCollector class**

Add to `src/tdc_auction_calendar/collectors/vendors/purdue.py`:

```python
from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping import create_scrape_client
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import (
    SaleType,
    SourceType,
    Vendor,
)


class PurdueCollector(BaseCollector):
    """Collects Texas tax foreclosure sale dates from pbfcm.com."""

    @property
    def name(self) -> str:
        return "purdue_vendor"

    @property
    def source_type(self) -> SourceType:
        return SourceType.VENDOR

    async def _fetch(self) -> list[Auction]:
        # Phase 1: Fetch listing page
        client = create_scrape_client()
        try:
            result = await client.scrape(_LISTING_URL)
        finally:
            await client.close()

        markdown = result.fetch.markdown or ""
        entries = parse_listing_markdown(markdown)

        if not entries:
            logger.warning("purdue_no_entries_found", url=_LISTING_URL)
            return []

        # Phase 2: Download and parse PDFs
        auctions: list[Auction] = []
        failure_count = 0

        async with httpx.AsyncClient() as http_client:
            for i, (county, pdf_url) in enumerate(entries):
                if i > 0:
                    await asyncio.sleep(_DOWNLOAD_DELAY)

                sale_date = await download_and_parse_pdf(http_client, pdf_url)
                if sale_date is None:
                    failure_count += 1
                    continue

                raw = {
                    "county": county,
                    "date": sale_date.isoformat(),
                    "pdf_url": pdf_url,
                }
                auctions.append(self.normalize(raw))

        if failure_count:
            logger.error(
                "purdue_pdf_failures",
                total=len(entries),
                succeeded=len(auctions),
                failed=failure_count,
            )

        return auctions

    def normalize(self, raw: dict) -> Auction:
        """Convert a raw record into a validated Auction."""
        return Auction(
            state="TX",
            county=raw["county"],
            start_date=date.fromisoformat(raw["date"]),
            sale_type=SaleType.DEED,
            source_type=SourceType.VENDOR,
            source_url=raw["pdf_url"],
            confidence_score=0.80,
            vendor=Vendor.PURDUE,
        )
```

- [ ] **Step 4: Update `collectors/vendors/__init__.py`**

```python
from tdc_auction_calendar.collectors.vendors.purdue import PurdueCollector

__all__ = ["PurdueCollector"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_purdue.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/ tests/collectors/vendors/
git commit -m "feat: implement PurdueCollector with two-phase HTML+PDF extraction"
```

---

## Chunk 4: Registration + Final Wiring

### Task 7: Register PurdueCollector in orchestrator and exports

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/orchestrator.py:1-48`
- Modify: `src/tdc_auction_calendar/collectors/__init__.py`

- [ ] **Step 1: Add import and registration to orchestrator**

In `src/tdc_auction_calendar/collectors/orchestrator.py`:

Add import after the state_agencies import block:
```python
from tdc_auction_calendar.collectors.vendors import PurdueCollector
```

Add to `COLLECTORS` dict:
```python
    "purdue_vendor": PurdueCollector,
```

- [ ] **Step 2: Add export to collectors `__init__.py`**

In `src/tdc_auction_calendar/collectors/__init__.py`:

Add import:
```python
from tdc_auction_calendar.collectors.vendors import PurdueCollector
```

Add `"PurdueCollector"` to the `__all__` list.

- [ ] **Step 3: Verify registration works**

Run: `uv run python -c "from tdc_auction_calendar.collectors import COLLECTORS; print('purdue_vendor' in COLLECTORS)"`
Expected: `True`

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS (existing + new).

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/orchestrator.py src/tdc_auction_calendar/collectors/__init__.py
git commit -m "feat: register PurdueCollector in orchestrator and exports"
```

### Task 8: Generate Alembic migration for new SourceType value

**Files:**
- Generate: `alembic/versions/` (new migration file)

- [ ] **Step 1: Check if migration is needed**

The `source_type` column is `String(20)`, so `"vendor"` is just a new string value — no schema migration needed. The StrEnum validates at the Python layer, not DB layer.

Verify: `uv run python -c "print(len('vendor'))"`  → `6`, fits in `String(20)`.

No migration needed. Skip this task.

- [ ] **Step 2: Commit (if migration was generated)**

N/A — no migration needed.
