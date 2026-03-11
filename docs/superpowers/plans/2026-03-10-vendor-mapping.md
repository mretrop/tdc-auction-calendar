# Vendor Mapping Seed Data Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `vendor_mapping.json` seed data with 50+ vendor-to-jurisdiction mappings, backed by Pydantic + ORM models, seed loader integration, and validation tests.

**Architecture:** New `VendorMapping` (Pydantic) and `VendorMappingRow` (ORM) models in `models/vendor.py`. Seed loader extended with a new entry. Alembic migration creates the `vendor_mapping` table. TDD throughout — tests written before implementation.

**Tech Stack:** SQLAlchemy, Pydantic, Alembic, pytest, uv

**Spec:** `docs/superpowers/specs/2026-03-10-vendor-mapping-design.md`

---

## Chunk 1: Models and Seed Loader

### Task 1: Create VendorMapping Pydantic + ORM models

**Files:**
- Create: `src/tdc_auction_calendar/models/vendor.py`
- Modify: `src/tdc_auction_calendar/models/__init__.py`

- [ ] **Step 1: Create `models/vendor.py` with both models**

```python
"""Vendor mapping models."""

from __future__ import annotations

import sqlalchemy as sa
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Mapped, mapped_column

from tdc_auction_calendar.models.jurisdiction import Base


ALLOWED_VENDORS = frozenset({"RealAuction", "Bid4Assets", "GovEase", "Grant Street", "SRI"})


# --- SQLAlchemy ORM model ---


class VendorMappingRow(Base):
    __tablename__ = "vendor_mapping"

    vendor: Mapped[str] = mapped_column(sa.String(100), primary_key=True)
    state: Mapped[str] = mapped_column(sa.String(2), primary_key=True)
    county: Mapped[str] = mapped_column(sa.String(100), primary_key=True)
    vendor_url: Mapped[str] = mapped_column(sa.Text)
    portal_url: Mapped[str] = mapped_column(sa.Text)


# --- Pydantic validation model ---


class VendorMapping(BaseModel):
    vendor: str
    vendor_url: str = Field(pattern=r"^https?://")
    state: str = Field(min_length=2, max_length=2)
    county: str = Field(min_length=1)
    portal_url: str = Field(pattern=r"^https?://")

    @field_validator("vendor")
    @classmethod
    def vendor_must_be_allowed(cls, v: str) -> str:
        if v not in ALLOWED_VENDORS:
            raise ValueError(f"Unknown vendor '{v}', must be one of {ALLOWED_VENDORS}")
        return v
```

- [ ] **Step 2: Update `models/__init__.py` to re-export new models**

Add to `src/tdc_auction_calendar/models/__init__.py`:

```python
from tdc_auction_calendar.models.vendor import (
    ALLOWED_VENDORS,
    VendorMapping,
    VendorMappingRow,
)
```

And add `"ALLOWED_VENDORS"`, `"VendorMapping"`, `"VendorMappingRow"` to the `__all__` list.

- [ ] **Step 3: Verify imports work**

Run: `uv run python -c "from tdc_auction_calendar.models import VendorMapping, VendorMappingRow, ALLOWED_VENDORS; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/tdc_auction_calendar/models/vendor.py src/tdc_auction_calendar/models/__init__.py
git commit -m "feat: add VendorMapping Pydantic + ORM models (issue #6)"
```

### Task 2: Update seed loader

**Files:**
- Modify: `src/tdc_auction_calendar/db/seed_loader.py:10-21`

- [ ] **Step 1: Add VendorMappingRow import and _SEED_MAP entry**

In `src/tdc_auction_calendar/db/seed_loader.py`:

Add to the import on line 11:
```python
from tdc_auction_calendar.models.vendor import VendorMappingRow
```

Add to `_SEED_MAP` dict (after line 20):
```python
    "vendor_mapping": (VendorMappingRow, ["vendor", "state", "county"]),
```

- [ ] **Step 2: Verify import works**

Run: `uv run python -c "from tdc_auction_calendar.db.seed_loader import _SEED_MAP; print(list(_SEED_MAP.keys()))"`
Expected: `['states', 'counties', 'vendor_mapping']`

- [ ] **Step 3: Commit**

```bash
git add src/tdc_auction_calendar/db/seed_loader.py
git commit -m "feat: register vendor_mapping in seed loader (issue #6)"
```

### Task 3: Create Alembic migration

**Files:**
- Create: `alembic/versions/<auto>_add_vendor_mapping_table.py`

- [ ] **Step 1: Generate migration**

Run: `uv run alembic revision --autogenerate -m "add vendor_mapping table"`

- [ ] **Step 2: Verify the generated migration creates the vendor_mapping table**

Read the generated file and confirm it contains:
- `op.create_table('vendor_mapping', ...)` with columns: vendor, state, county, vendor_url, portal_url
- Composite primary key on (vendor, state, county)

- [ ] **Step 3: Run the migration**

Run: `uv run alembic upgrade head`
Expected: Successfully applies migration

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/
git commit -m "feat: add vendor_mapping table migration (issue #6)"
```

## Chunk 2: Tests (TDD — written before seed data)

### Task 4: Write validation tests for vendor_mapping.json

**Files:**
- Create: `tests/test_seed_vendor_mapping.py`

- [ ] **Step 1: Write the full test file**

```python
"""Validate vendor_mapping.json seed data against VendorMapping model and domain invariants."""

import json
import re

import pytest

from tdc_auction_calendar.db.seed_loader import SEED_DIR
from tdc_auction_calendar.models.vendor import ALLOWED_VENDORS, VendorMapping, VendorMappingRow

SEED_FILE = SEED_DIR / "vendor_mapping.json"
STATES_SEED_FILE = SEED_DIR / "states.json"
COUNTIES_SEED_FILE = SEED_DIR / "counties.json"

URL_PATTERN = re.compile(r"^https?://\S+")


@pytest.fixture
def seed_data() -> list[dict]:
    assert SEED_FILE.exists(), f"Seed file not found: {SEED_FILE}"
    return json.loads(SEED_FILE.read_text())


@pytest.fixture
def states_data() -> set[str]:
    assert STATES_SEED_FILE.exists()
    data = json.loads(STATES_SEED_FILE.read_text())
    return {entry["state"] for entry in data}


@pytest.fixture
def counties_data() -> list[dict]:
    assert COUNTIES_SEED_FILE.exists()
    return json.loads(COUNTIES_SEED_FILE.read_text())


def test_seed_file_exists():
    assert SEED_FILE.exists()


def test_entry_count(seed_data):
    """At least 50 vendor-to-jurisdiction mappings per acceptance criteria."""
    assert len(seed_data) >= 50, f"Expected at least 50 entries, got {len(seed_data)}"


def test_all_entries_validate(seed_data):
    """Every entry must pass Pydantic VendorMapping validation."""
    for entry in seed_data:
        key = f"{entry.get('vendor')}/{entry.get('state')}/{entry.get('county')}"
        try:
            VendorMapping(**entry)
        except Exception as exc:
            pytest.fail(f"Entry {key} failed validation: {exc}")


def test_all_entries_orm_compatible(seed_data):
    """Every entry must be instantiable as a VendorMappingRow."""
    for entry in seed_data:
        key = f"{entry.get('vendor')}/{entry.get('state')}/{entry.get('county')}"
        try:
            VendorMappingRow(**entry)
        except Exception as exc:
            pytest.fail(f"Entry {key} failed ORM instantiation: {exc}")


def test_no_duplicate_keys(seed_data):
    """No duplicate (vendor, state, county) composite keys."""
    keys = [(e["vendor"], e["state"], e["county"]) for e in seed_data]
    dupes = [k for k in keys if keys.count(k) > 1]
    assert len(keys) == len(set(keys)), f"Duplicate keys: {set(dupes)}"


def test_valid_vendor_names(seed_data):
    """All vendor names must be in the allowed set."""
    for entry in seed_data:
        assert entry["vendor"] in ALLOWED_VENDORS, (
            f"Invalid vendor '{entry['vendor']}' — allowed: {ALLOWED_VENDORS}"
        )


def test_states_exist_in_states_seed(seed_data, states_data):
    """All state codes must exist in states.json."""
    mapping_states = {e["state"] for e in seed_data}
    missing = mapping_states - states_data
    assert not missing, f"States in vendor_mapping.json but not in states.json: {missing}"


def test_valid_urls(seed_data):
    """All vendor_url and portal_url values must be valid HTTP(S) URLs."""
    for entry in seed_data:
        key = f"{entry['vendor']}/{entry['state']}/{entry['county']}"
        assert URL_PATTERN.match(entry["vendor_url"]), (
            f"Entry {key}: invalid vendor_url '{entry['vendor_url']}'"
        )
        assert URL_PATTERN.match(entry["portal_url"]), (
            f"Entry {key}: invalid portal_url '{entry['portal_url']}'"
        )


def test_counties_exist_in_counties_seed(seed_data, counties_data):
    """Non-'all' county values must exist in counties.json for that state.

    Note: vendor_mapping uses 'county' field which must match 'county_name' in counties.json.
    """
    county_set = {(e["state"], e["county_name"]) for e in counties_data}
    for entry in seed_data:
        if entry["county"] == "all":
            continue
        pair = (entry["state"], entry["county"])
        assert pair in county_set, (
            f"Vendor mapping references {entry['state']}/{entry['county']} "
            f"which is not in counties.json"
        )


def test_spot_check_known_mappings(seed_data):
    """Spot-check a few known vendor-jurisdiction relationships."""
    keys = {(e["vendor"], e["state"], e["county"]) for e in seed_data}

    # FL uses RealAuction — at least Miami-Dade should be present
    assert ("RealAuction", "FL", "Miami-Dade") in keys, "Missing RealAuction/FL/Miami-Dade"

    # TX has Bid4Assets presence
    assert ("Bid4Assets", "TX", "Harris") in keys or ("Bid4Assets", "TX", "all") in keys, (
        "Missing Bid4Assets TX mapping"
    )


def test_all_five_vendors_represented(seed_data):
    """All five vendors must have at least one entry."""
    vendors_present = {e["vendor"] for e in seed_data}
    missing = ALLOWED_VENDORS - vendors_present
    assert not missing, f"Vendors with no entries: {missing}"


def test_counties_vendor_cross_validation(seed_data, counties_data):
    """Every known_auction_vendor in counties.json should have at least one
    corresponding entry in vendor_mapping.json."""
    mapping_vendors = {e["vendor"] for e in seed_data}
    county_vendors = {
        e["known_auction_vendor"]
        for e in counties_data
        if e.get("known_auction_vendor") is not None
    }
    # "direct" is not a vendor in vendor_mapping
    county_vendors.discard("direct")
    missing = county_vendors - mapping_vendors
    assert not missing, (
        f"Vendors in counties.json but not in vendor_mapping.json: {missing}"
    )
```

- [ ] **Step 2: Run tests to verify they fail (seed file doesn't exist yet)**

Run: `uv run pytest tests/test_seed_vendor_mapping.py -v`
Expected: `test_seed_file_exists` FAILS (file not found), most others FAIL or ERROR

- [ ] **Step 3: Commit**

```bash
git add tests/test_seed_vendor_mapping.py
git commit -m "test: add vendor_mapping.json seed data validation tests (issue #6)"
```

## Chunk 3: Seed Data

### Task 5: Create vendor_mapping.json with 50+ entries

**Files:**
- Create: `src/tdc_auction_calendar/db/seed/vendor_mapping.json`

**Important context for data research:**
- Vendor portal URLs must be researched from actual vendor websites
- The 5 vendors: RealAuction (realauction.com/realforeclose.com), Bid4Assets (bid4assets.com), GovEase (govease.com), Grant Street Group (grantstreet.com), SRI Services (sriservices.com)
- Counties referenced must exist in `counties.json` (or use `"all"` for statewide)
- All URLs must be real, valid HTTP(S) URLs
- Target 55-65 entries across all 5 vendors

- [ ] **Step 1: Research vendor portal URLs**

Use web search to find actual portal URLs for each vendor across their jurisdictions. Key sources:
- RealAuction: `realforeclose.com` — FL county subdomains (e.g., `miamidade.realforeclose.com`)
- Bid4Assets: `bid4assets.com` — individual auction listing pages per jurisdiction
- GovEase: `govease.com` — Midwest/South counties
- Grant Street Group: `grantstreet.com` — PA, NJ jurisdictions
- SRI: `sriservices.com` — TX counties

- [ ] **Step 2: Create the JSON file**

Create `src/tdc_auction_calendar/db/seed/vendor_mapping.json` as a JSON array with 50+ entries. Each entry:
```json
{
  "vendor": "<vendor name from ALLOWED_VENDORS>",
  "vendor_url": "<vendor homepage URL>",
  "state": "<2-letter state code>",
  "county": "<county name matching counties.json, or 'all'>",
  "portal_url": "<direct auction portal URL for this jurisdiction>"
}
```

Ensure:
- All 5 vendors represented
- All referenced counties exist in counties.json (check state+county_name pairs)
- All FL RealAuction entries match the 67 FL counties in counties.json
- TX Bid4Assets entries match the 5 TX counties already tagged in counties.json

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/test_seed_vendor_mapping.py -v`
Expected: ALL PASS

- [ ] **Step 4: Run full test suite to check for regressions**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/db/seed/vendor_mapping.json
git commit -m "feat: add vendor_mapping.json seed data with 50+ entries (issue #6)"
```

## Chunk 4: Final Verification

### Task 6: Update CLAUDE.md and verify everything

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md progress section**

Change:
```
Issues are tracked as GitHub issues organized by milestones (M1–M4). Issues #1–5 are complete. Next up: issue #6.
```
To:
```
Issues are tracked as GitHub issues organized by milestones (M1–M4). Issues #1–6 are complete. Next up: issue #7.
```

- [ ] **Step 2: Add vendor_mapping to seed file references in CLAUDE.md**

In the `db/` architecture section, update `seed/` description:
```
  - `seed/`: JSON seed files (states.json, counties.json, vendor_mapping.json)
```

- [ ] **Step 3: Run full test suite one final time**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md — issue #6 complete, next up #7"
```
