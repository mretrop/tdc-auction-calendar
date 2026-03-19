# Precise Source Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve `source_url` precision across RealAuction, MVBA, and SRI collectors so calendar links take users directly to event-specific pages.

**Architecture:** Each collector is modified independently — no shared code changes. RealAuction constructs a preview URL from `base_url` + entry date. MVBA extends its regex to capture per-county links already present in the markdown. SRI constructs a filtered URL with state/county/saleType params.

**Tech Stack:** Python, regex, urllib.parse, pytest

**Spec:** `docs/superpowers/specs/2026-03-18-precise-source-links-design.md`

---

### Task 1: RealAuction — Deep link to auction preview

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/realauction.py:205-213`
- Modify: `tests/collectors/vendors/test_realauction.py`

- [ ] **Step 1: Write a test for the new source_url format**

In `tests/collectors/vendors/test_realauction.py`, add a test that verifies the source_url uses the preview pattern:

```python
def test_normalize_source_url_is_preview_link(collector):
    raw = {
        "state": "FL",
        "county": "Hillsborough",
        "date": "2026-03-05",
        "sale_type": "Tax Deed",
        "property_count": 13,
        "time": "10:00 AM ET",
        "source_url": "https://hillsborough.realtaxdeed.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=03/05/2026",
    }
    auction = collector.normalize(raw)
    assert auction.source_url == "https://hillsborough.realtaxdeed.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=03/05/2026"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/collectors/vendors/test_realauction.py::test_normalize_source_url_is_preview_link -v`
Expected: PASS (normalize just passes source_url through from raw — no change needed there)

- [ ] **Step 3: Write a test for _fetch building preview URLs**

Add a test that verifies `_fetch` constructs preview URLs instead of calendar URLs:

```python
async def test_fetch_source_url_is_preview_link(collector):
    html = _load("realauction_hillsborough_march.html")
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(html)
    mock_client.close = AsyncMock()

    with (
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.ScrapeClient",
            return_value=mock_client,
        ),
        patch(
            "tdc_auction_calendar.collectors.vendors.realauction.SITES",
            [("FL", "Hillsborough", "https://hillsborough.realtaxdeed.com")],
        ),
    ):
        auctions = await collector.collect()

    assert len(auctions) >= 1
    for a in auctions:
        assert "zaction=AUCTION" in a.source_url
        assert "Zmethod=PREVIEW" in a.source_url
        assert "AUCTIONDATE=" in a.source_url
        # Should NOT be the calendar URL
        assert "zaction=user" not in a.source_url
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/collectors/vendors/test_realauction.py::test_fetch_source_url_is_preview_link -v`
Expected: FAIL — source_url currently contains the calendar page URL

- [ ] **Step 5: Implement the change in _fetch_one**

In `src/tdc_auction_calendar/collectors/vendors/realauction.py`, modify `_fetch_one` (around line 205-213). Change the `source_url` in the `raw` dict from `url` (calendar page) to a constructed preview URL using `base_url` and the entry date:

```python
                for entry in entries:
                    preview_url = (
                        f"{base_url}/index.cfm?zaction=AUCTION"
                        f"&Zmethod=PREVIEW"
                        f"&AUCTIONDATE={entry['date'].strftime('%m/%d/%Y')}"
                    )
                    raw = {
                        "state": state,
                        "county": county,
                        "date": entry["date"].isoformat(),
                        "sale_type": entry["sale_type"],
                        "property_count": entry["property_count"],
                        "time": entry["time"],
                        "source_url": preview_url,
                    }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/collectors/vendors/test_realauction.py -v`
Expected: ALL PASS

- [ ] **Step 7: Update existing test fixtures that assert on source_url**

Check `test_normalize_tax_deed` and `test_normalize_treasurer_deed` — their `raw` dicts have `source_url` set to the calendar page. Update them to use preview URLs for consistency (the normalize function passes source_url through, so the test value just needs to be a valid URL — these tests still pass either way, but updating keeps fixtures realistic):

In `test_normalize_tax_deed`, change:
```python
        "source_url": "https://hillsborough.realtaxdeed.com/index.cfm?zaction=user&zmethod=calendar",
```
to:
```python
        "source_url": "https://hillsborough.realtaxdeed.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=03/05/2026",
```

In `test_normalize_treasurer_deed`, change:
```python
        "source_url": "https://denver.treasurersdeedsale.realtaxdeed.com/index.cfm?zaction=user&zmethod=calendar",
```
to:
```python
        "source_url": "https://denver.treasurersdeedsale.realtaxdeed.com/index.cfm?zaction=AUCTION&Zmethod=PREVIEW&AUCTIONDATE=04/15/2026",
```

- [ ] **Step 8: Run full test suite to verify no regressions**

Run: `uv run pytest tests/collectors/vendors/test_realauction.py -v`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/realauction.py tests/collectors/vendors/test_realauction.py
git commit -m "feat: use auction preview deep links for RealAuction source URLs"
```

---

### Task 2: MVBA — Extract per-county links from markdown

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/mvba.py:32-65,100-121`
- Modify: `tests/collectors/vendors/test_mvba.py`

- [ ] **Step 1: Write a test for parse_monthly_sales returning URLs**

In `tests/collectors/vendors/test_mvba.py`, add a test:

```python
def test_parse_extracts_urls():
    results = parse_monthly_sales(SAMPLE_MARKDOWN)
    assert len(results) == 4
    # Each result is now (date, county, url)
    assert results[0] == (
        date(2026, 4, 7),
        "Eastland",
        "https://mvbalaw.com/wp-content/TaxUploads/0426_Eastland.pdf",
    )
    assert results[1] == (
        date(2026, 4, 7),
        "Harrison",
        "https://www.mvbataxsales.com/auction/harrison-county-online-property-tax-sale-april-7-2026-171/bidgallery/",
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/collectors/vendors/test_mvba.py::test_parse_extracts_urls -v`
Expected: FAIL — currently returns 2-tuples

- [ ] **Step 3: Extend _COUNTY_RE regex to capture URLs**

In `src/tdc_auction_calendar/collectors/vendors/mvba.py`, update `_COUNTY_RE` (line 32-34) to also capture the markdown link URL:

```python
# Matches county links: "* [Eastland County](url)" or "* [Harrison County (MVBA Online Auction)](url)"
# URL group is optional — some entries may lack a link
_COUNTY_RE = re.compile(
    r"^\*\s+\[([A-Za-z\s]+?)\s+County(?:\s*\([^)]*\))?\](?:\(([^)]+)\))?",
    re.MULTILINE,
)
```

The addition is `(?:\(([^)]+)\))?` after the `]` — optionally captures the URL in parentheses. If no URL is present, `group(2)` returns `None`.

- [ ] **Step 4: Update parse_monthly_sales to return 3-tuples**

Update the function signature and body (lines 38-67):

```python
def parse_monthly_sales(markdown: str) -> list[tuple[date, str, str | None]]:
    """Parse MVBA monthly sales markdown into (sale_date, county_name, url) tuples."""
    results: list[tuple[date, str, str | None]] = []

    # Find all heading positions
    headings = list(_HEADING_RE.finditer(markdown))
    if not headings:
        return []

    for i, heading in enumerate(headings):
        month_str, day_str, year_str = heading.group(1), heading.group(2), heading.group(3)
        try:
            sale_date = datetime.strptime(f"{month_str} {day_str} {year_str}", "%B %d %Y").date()
        except ValueError:
            logger.error(
                "mvba_invalid_heading_date",
                raw_date=f"{month_str} {day_str} {year_str}",
            )
            continue

        # Extract counties between this heading and the next (or end of string)
        start = heading.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(markdown)
        section = markdown[start:end]

        for county_match in _COUNTY_RE.finditer(section):
            county_name = county_match.group(1).strip()
            county_url = county_match.group(2).strip()
            results.append((sale_date, county_name, county_url))

    return results
```

- [ ] **Step 5: Run the new test to verify it passes**

Run: `uv run pytest tests/collectors/vendors/test_mvba.py::test_parse_extracts_urls -v`
Expected: PASS

- [ ] **Step 6: Update _fetch and normalize to use extracted URLs**

In `mvba.py`, update `_fetch` (line 100) and `normalize` (line 114-124):

In `_fetch`, change the loop:
```python
        for sale_date, county, county_url in entries:
            raw = {
                "county": county,
                "date": sale_date.isoformat(),
                "source_url": county_url or _SOURCE_URL,
            }
```

In `normalize`, change `source_url`:
```python
    def normalize(self, raw: dict) -> Auction:
        return Auction(
            state="TX",
            county=raw["county"],
            start_date=date.fromisoformat(raw["date"]),
            sale_type=SaleType.DEED,
            source_type=SourceType.VENDOR,
            source_url=raw.get("source_url", _SOURCE_URL),
            confidence_score=0.90,
            vendor=Vendor.MVBA,
        )
```

- [ ] **Step 7: Update existing tests for 3-tuple return type**

Fix all tests that destructure or compare 2-tuples. Key changes:

In `test_parse_extracts_date_and_counties`:
```python
def test_parse_extracts_date_and_counties():
    results = parse_monthly_sales(SAMPLE_MARKDOWN)
    assert len(results) == 4
    assert all(r[0] == date(2026, 4, 7) for r in results)
    counties = [r[1] for r in results]
    assert counties == ["Eastland", "Harrison", "Hill", "Medina"]
```
(This one actually still works with index access — no change needed.)

In `test_parse_multiple_months` (line 60-61), fix destructuring:
```python
    march = [(d, c, u) for d, c, u in results if d == date(2026, 3, 3)]
    april = [(d, c, u) for d, c, u in results if d == date(2026, 4, 7)]
```

In `test_parse_day_name_variations` (line 85), fix equality check:
```python
    assert results[0][:2] == (date(2026, 5, 6), "Travis")
```

In `test_parse_invalid_date_skips_section` (line 153), fix equality check:
```python
    assert results[0][:2] == (date(2026, 5, 6), "Travis")
```

In `test_normalize` (line 101-114), add `source_url` to the raw dict:
```python
def test_normalize(collector):
    raw = {
        "county": "Eastland",
        "date": "2026-04-07",
        "source_url": "https://mvbalaw.com/wp-content/TaxUploads/0426_Eastland.pdf",
    }
    auction = collector.normalize(raw)
    assert auction.state == "TX"
    assert auction.county == "Eastland"
    assert auction.start_date == date(2026, 4, 7)
    assert auction.sale_type == SaleType.DEED
    assert auction.source_type == SourceType.VENDOR
    assert auction.confidence_score == 0.90
    assert auction.vendor == Vendor.MVBA
    assert auction.source_url == "https://mvbalaw.com/wp-content/TaxUploads/0426_Eastland.pdf"
```

- [ ] **Step 8: Add test for normalize fallback when no URL**

```python
def test_normalize_fallback_source_url(collector):
    raw = {
        "county": "Eastland",
        "date": "2026-04-07",
    }
    auction = collector.normalize(raw)
    assert auction.source_url == "https://mvbalaw.com/tax-sales/month-sales/"
```

- [ ] **Step 9: Add test for fetch using per-county URLs**

```python
async def test_fetch_uses_county_urls(collector):
    mock_client = AsyncMock()
    mock_client.scrape.return_value = _mock_scrape_result(SAMPLE_MARKDOWN)
    mock_client.close = AsyncMock()

    with patch(
        "tdc_auction_calendar.collectors.vendors.mvba.create_scrape_client",
        return_value=mock_client,
    ):
        auctions = await collector.collect()

    eastland = next(a for a in auctions if a.county == "Eastland")
    assert eastland.source_url == "https://mvbalaw.com/wp-content/TaxUploads/0426_Eastland.pdf"

    harrison = next(a for a in auctions if a.county == "Harrison")
    assert "mvbataxsales.com" in harrison.source_url
```

- [ ] **Step 10: Run full test suite**

Run: `uv run pytest tests/collectors/vendors/test_mvba.py -v`
Expected: ALL PASS

- [ ] **Step 11: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/mvba.py tests/collectors/vendors/test_mvba.py
git commit -m "feat: extract per-county deep links from MVBA markdown"
```

---

### Task 3: SRI Services — Auction list deep link

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/vendors/sri.py:20-31,82-92`
- Modify: `tests/collectors/vendors/test_sri.py`

- [ ] **Step 1: Write a test for the new source_url format**

In `tests/collectors/vendors/test_sri.py`, add inside `TestParseApiResponse`:

```python
    def test_source_url_is_deep_link(self):
        data = [
            {
                "id": 100,
                "saleTypeCode": "A",
                "county": "Marion",
                "state": "IN",
                "auctionDate": "2026-04-07T10:00:00",
            },
        ]
        auctions = parse_api_response(data)
        assert len(auctions) == 1
        assert auctions[0].source_url == "https://sriservices.com/properties?state=IN&saleType=tax&county=Marion&modal=auctionList"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/collectors/vendors/test_sri.py::TestParseApiResponse::test_source_url_is_deep_link -v`
Expected: FAIL — source_url is currently the generic properties page

- [ ] **Step 3: Add URL sale type mapping and builder function**

In `src/tdc_auction_calendar/collectors/vendors/sri.py`, add after `_SALE_TYPE_MAP` (around line 31):

```python
from urllib.parse import quote_plus

# Maps saleTypeCode to the URL filter label used on sriservices.com
_URL_SALE_TYPE: dict[str, str] = {
    "A": "tax",
    "C": "redemption",
    "D": "deed",
    "J": "adjudicated",
}


def _build_source_url(state: str, county: str, sale_type_code: str) -> str:
    """Build a deep link to the SRI auction list filtered by state/county/type."""
    sale_label = _URL_SALE_TYPE.get(sale_type_code, "")
    county_encoded = quote_plus(county)
    return f"{_SOURCE_URL}?state={state}&saleType={sale_label}&county={county_encoded}&modal=auctionList"
```

- [ ] **Step 4: Update parse_api_response to use deep links**

In `parse_api_response` (around line 82-92), change `source_url=_SOURCE_URL` to use the new builder:

```python
        try:
            auctions.append(
                Auction(
                    state=state,
                    county=county,
                    start_date=auction_date,
                    sale_type=sale_type,
                    source_type=SourceType.VENDOR,
                    source_url=_build_source_url(state, county, code),
                    confidence_score=1.0,
                    vendor=Vendor.SRI,
                )
            )
```

- [ ] **Step 5: Run the new test to verify it passes**

Run: `uv run pytest tests/collectors/vendors/test_sri.py::TestParseApiResponse::test_source_url_is_deep_link -v`
Expected: PASS

- [ ] **Step 6: Add test for URL-encoded county names**

```python
    def test_source_url_encodes_county(self):
        data = [
            {
                "id": 100,
                "saleTypeCode": "C",
                "county": "St. Johns",
                "state": "FL",
                "auctionDate": "2026-04-07T10:00:00",
            },
        ]
        auctions = parse_api_response(data)
        assert auctions[0].source_url == "https://sriservices.com/properties?state=FL&saleType=redemption&county=St.+Johns&modal=auctionList"
```

- [ ] **Step 7: Run test**

Run: `uv run pytest tests/collectors/vendors/test_sri.py::TestParseApiResponse::test_source_url_encodes_county -v`
Expected: PASS

- [ ] **Step 8: Update existing test that asserts generic source_url**

In `TestParseApiResponse.test_basic_parsing` (line 60), update the assertion:

Change:
```python
        assert marion.source_url == "https://sriservices.com/properties"
```
to:
```python
        assert "sriservices.com/properties?" in marion.source_url
        assert "state=IN" in marion.source_url
        assert "county=Marion" in marion.source_url
        assert "modal=auctionList" in marion.source_url
```

In `TestSRICollector.test_normalize` (line 186), update — normalize still uses `_SOURCE_URL` hardcoded, so update `normalize` too:

Change `normalize` in `sri.py` (around line 131) to accept `source_url` from raw:
```python
    def normalize(self, raw: dict) -> Auction:
        return Auction(
            state=raw["state"],
            county=raw["county"],
            start_date=raw["start_date"],
            sale_type=raw["sale_type"],
            source_type=SourceType.VENDOR,
            source_url=raw.get("source_url", _SOURCE_URL),
            confidence_score=1.0,
            vendor=Vendor.SRI,
        )
```

Note: `normalize` is not actually called by `parse_api_response` — it's only called via the base class path. Since `parse_api_response` builds `Auction` objects directly, the normalize change is defensive only. Update `test_normalize` to pass `source_url`:

```python
    def test_normalize(self):
        collector = SRICollector()
        raw = {
            "state": "IN",
            "county": "Marion",
            "start_date": date(2026, 4, 7),
            "sale_type": SaleType.DEED,
            "source_url": "https://sriservices.com/properties?state=IN&saleType=tax&county=Marion&modal=auctionList",
        }
        auction = collector.normalize(raw)
        assert auction.state == "IN"
        assert auction.county == "Marion"
        assert auction.start_date == date(2026, 4, 7)
        assert auction.vendor == Vendor.SRI
        assert auction.confidence_score == 1.0
        assert "state=IN" in auction.source_url
```

- [ ] **Step 9: Export _build_source_url for test imports**

Update the import in `test_sri.py`:

```python
from tdc_auction_calendar.collectors.vendors.sri import (
    SRICollector,
    parse_api_response,
    _build_source_url,
)
```

Add a direct unit test for the builder:

```python
def test_build_source_url():
    url = _build_source_url("FL", "St. Johns", "C")
    assert url == "https://sriservices.com/properties?state=FL&saleType=redemption&county=St.+Johns&modal=auctionList"
```

- [ ] **Step 10: Run full test suite**

Run: `uv run pytest tests/collectors/vendors/test_sri.py -v`
Expected: ALL PASS

- [ ] **Step 11: Commit**

```bash
git add src/tdc_auction_calendar/collectors/vendors/sri.py tests/collectors/vendors/test_sri.py
git commit -m "feat: use auction list deep links for SRI source URLs"
```

---

### Task 4: Final verification

- [ ] **Step 1: Run entire test suite**

Run: `uv run pytest -v`
Expected: ALL PASS — no regressions across any collector

- [ ] **Step 2: Commit plan doc (if not already committed)**

```bash
git add docs/superpowers/plans/2026-03-18-precise-source-links.md
git commit -m "docs: add precise source links implementation plan"
```
