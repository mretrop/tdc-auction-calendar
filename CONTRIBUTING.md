# Contributing

## Development Setup

```bash
git clone https://github.com/mretrop/tdc-auction-calendar.git
cd tdc-auction-calendar
uv sync          # Installs all dependencies including dev tools
uv run pytest    # Verify everything works
```

## Adding a New Collector

This walkthrough uses the Arkansas state agency collector as a reference. You can find the full source at `src/tdc_auction_calendar/collectors/state_agencies/arkansas.py`.

### 1. Create the collector file

Create a new file in the appropriate subdirectory under `src/tdc_auction_calendar/collectors/`:

- `state_agencies/` — for state government data sources
- `public_notices/` — for public notice aggregators
- `county_websites/` — for individual county tax sale pages

### 2. Define an extraction schema

Create a Pydantic model describing what the scraper should extract from the page:

```python
from pydantic import BaseModel

class ArkansasAuctionRecord(BaseModel):
    """Schema for a single Arkansas auction record from COSL."""
    county: str
    sale_date: str
    sale_type: str = "deed"
```

### 3. Define the extraction prompt

Write a natural-language prompt that tells the LLM/Cloudflare what to extract:

```python
_URL = "https://cosl.org"
_PROMPT = (
    "Extract all county tax deed sale dates from this page. "
    "Each row should have county name, sale date, and sale type."
)
```

### 4. Subclass `BaseCollector`

Implement the required properties and methods:

```python
from pydantic import ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping import ExtractionError, create_scrape_client
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType

class ArkansasCollector(BaseCollector):

    @property
    def name(self) -> str:
        return "arkansas_state_agency"

    @property
    def source_type(self) -> SourceType:
        return SourceType.STATE_AGENCY

    async def _fetch(self) -> list[Auction]:
        json_options = {
            "prompt": _PROMPT,
            "response_format": ArkansasAuctionRecord.model_json_schema(),
        }
        client = create_scrape_client()
        try:
            result = await client.scrape(_URL, json_options=json_options)
        finally:
            await client.close()

        raw_records: list = (
            result.data
            if isinstance(result.data, list)
            else ([result.data] if result.data is not None else [])
        )

        auctions: list[Auction] = []
        for raw in raw_records:
            try:
                auctions.append(self.normalize(raw))
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                logger.error("normalize_failed", collector=self.name, raw=raw, error=str(exc))
        if raw_records and not auctions:
            raise ExtractionError(f"{self.name}: all records failed normalization")
        return auctions

    def normalize(self, raw: dict) -> Auction:
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

**Key points:**
- Implement `name` and `source_type` as properties
- Implement `_fetch()` (NOT `collect()` — that's already implemented in `BaseCollector` and handles deduplication)
- Implement `normalize()` to convert raw extracted data into an `Auction` model
- Use `create_scrape_client()` for web scraping — it handles Cloudflare/Crawl4AI fallback automatically

### 5. Register in the orchestrator

Add your collector to the `COLLECTORS` dict in `src/tdc_auction_calendar/collectors/orchestrator.py`:

```python
from tdc_auction_calendar.collectors.state_agencies import ArkansasCollector

COLLECTORS: dict[str, type[BaseCollector]] = {
    # ... existing collectors ...
    "arkansas_state_agency": ArkansasCollector,
}
```

### 6. Add to the GitHub Actions workflow

Add the collector name to the appropriate workflow in `.github/workflows/`:

- `collect-state-agencies.yml` for state agency collectors
- `collect-public-notices.yml` for public notice collectors
- `collect-county-websites.yml` for county website collectors

### 7. Write tests

Add tests in `tests/collectors/`. See [Recording Test Fixtures](#recording-test-fixtures) below.

## Adding a County URL

County data lives in `src/tdc_auction_calendar/db/seed/counties.json`. Each entry has:

| Field | Description |
|-------|-------------|
| `state` | Two-letter state code (e.g., `"FL"`) |
| `county_name` | County name (e.g., `"Alachua"`) |
| `known_auction_vendor` | Auction vendor if known (e.g., `"RealAuction"`) or `null` |
| `tax_sale_page_url` | Direct URL to the county's tax sale page, or `null` |
| `priority` | Collection priority: `"high"`, `"medium"`, or `"low"` |

To add or update a county, edit the JSON file and run the seed loader:

```bash
uv run tdc-auction-calendar collect --collectors statutory
```

The seed loader is idempotent — it checks primary key existence before inserting.

## Recording Test Fixtures

Test fixtures live in `tests/fixtures/`. To record a new fixture for a collector:

1. Run the collector with caching enabled (responses are cached in `data/cache/` by default)
2. Copy the cached response to `tests/fixtures/`
3. Write tests that load the fixture and verify `normalize()` output

Example test structure:

```python
import json
import pytest
from tdc_auction_calendar.collectors.state_agencies.arkansas import ArkansasCollector

@pytest.fixture
def collector():
    return ArkansasCollector()

def test_normalize_valid_record(collector):
    raw = {"county": "Pulaski", "sale_date": "2026-06-15", "sale_type": "deed"}
    auction = collector.normalize(raw)
    assert auction.state == "AR"
    assert auction.county == "Pulaski"
    assert auction.source_type.value == "state_agency"
```

## Known Limitations

- **Crawl4AI fallback** requires a local Chromium browser binary. Install with `playwright install chromium` if needed.
- **Rate limiting** — collectors use a built-in rate limiter, but aggressive scraping may still trigger site-level blocks.
- **Seed data coverage** — not all 50 US states have tax sales. Only states with active lien/deed/hybrid auctions are included in the seed data.
- **Redemption periods** — `redemption_period_months` is typically null for deed states, but some (e.g., TX) have statutory redemption periods. This is correct, not a bug.
