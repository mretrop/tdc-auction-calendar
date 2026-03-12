# Issue #8: Test Coverage Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill test coverage gaps for M1 components — model validation negative cases, seed loader idempotency, shared fixtures, and coverage tooling.

**Architecture:** Add 3 new test files and 1 dependency. Shared conftest.py provides in-memory SQLite fixtures. test_models.py covers Pydantic rejection cases. test_seed_loader.py verifies idempotency against real ORM with ephemeral DB.

**Tech Stack:** pytest, pytest-cov, SQLAlchemy (in-memory SQLite), Pydantic ValidationError

**Spec:** `docs/superpowers/specs/2026-03-11-issue-8-test-coverage-design.md`

---

## Chunk 1: Fixtures and Coverage Tooling

### Task 1: Add pytest-cov dependency

**Files:**
- Modify: `pyproject.toml:31-35`

- [ ] **Step 1: Add pytest-cov to dev dependencies**

In `pyproject.toml`, update the `[dependency-groups]` section:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=6.0",
]
```

- [ ] **Step 2: Sync dependencies**

Run: `uv sync`
Expected: installs pytest-cov successfully

- [ ] **Step 3: Verify pytest-cov works**

Run: `uv run pytest --co -q`
Expected: lists collected tests with no errors

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add pytest-cov to dev dependencies (issue #8)"
```

---

### Task 2: Create shared fixtures (`tests/conftest.py`)

**Files:**
- Create: `tests/conftest.py`

- [ ] **Step 1: Write conftest.py**

```python
"""Shared test fixtures."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tdc_auction_calendar.models import Base


@pytest.fixture()
def db_engine():
    """In-memory SQLite engine with all tables created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """Fresh SQLAlchemy session, rolled back after each test."""
    with Session(db_engine) as session:
        yield session
        session.rollback()


@pytest.fixture()
def sample_auction_data():
    """Valid Auction field dict — override individual keys with spread syntax."""
    return {
        "state": "FL",
        "county": "Miami-Dade",
        "start_date": datetime.date(2027, 1, 1),
        "end_date": datetime.date(2027, 1, 31),
        "sale_type": "deed",
        "status": "upcoming",
        "source_type": "statutory",
        "confidence_score": 0.4,
    }
```

- [ ] **Step 2: Verify fixtures are discoverable**

Run: `uv run pytest --fixtures -q | grep -E "db_engine|db_session|sample_auction_data"`
Expected: all three fixtures listed

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add shared conftest fixtures — in-memory DB + sample data (issue #8)"
```

---

## Chunk 2: Model Validation Tests

### Task 3: Create model validation tests (`tests/test_models.py`)

**Files:**
- Create: `tests/test_models.py`

- [ ] **Step 1: Write Auction positive test**

```python
"""Pydantic model validation — negative cases."""

from __future__ import annotations

import datetime

import pytest
from pydantic import ValidationError

from tdc_auction_calendar.models import (
    Auction,
    CountyInfo,
    StateRules,
)


class TestAuctionValidation:
    """Auction Pydantic model rejects invalid data."""

    def test_valid_auction(self, sample_auction_data):
        auction = Auction(**sample_auction_data)
        assert auction.state == "FL"
        assert auction.confidence_score == 0.4
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py::TestAuctionValidation::test_valid_auction -v`
Expected: PASS

- [ ] **Step 3: Add confidence_score rejection tests**

Append to `TestAuctionValidation`:

```python
    def test_rejects_confidence_score_too_high(self, sample_auction_data):
        with pytest.raises(ValidationError, match="confidence_score"):
            Auction(**{**sample_auction_data, "confidence_score": 1.5})

    def test_rejects_confidence_score_too_low(self, sample_auction_data):
        with pytest.raises(ValidationError, match="confidence_score"):
            Auction(**{**sample_auction_data, "confidence_score": -0.1})

    def test_rejects_confidence_score_boundary_above(self, sample_auction_data):
        with pytest.raises(ValidationError, match="confidence_score"):
            Auction(**{**sample_auction_data, "confidence_score": 1.01})

    def test_accepts_confidence_score_boundaries(self, sample_auction_data):
        a0 = Auction(**{**sample_auction_data, "confidence_score": 0.0})
        a1 = Auction(**{**sample_auction_data, "confidence_score": 1.0})
        assert a0.confidence_score == 0.0
        assert a1.confidence_score == 1.0
```

- [ ] **Step 4: Run tests to verify**

Run: `uv run pytest tests/test_models.py::TestAuctionValidation -v`
Expected: all PASS

- [ ] **Step 5: Add state validation tests**

Append to `TestAuctionValidation`:

```python
    def test_rejects_state_too_short(self, sample_auction_data):
        with pytest.raises(ValidationError, match="state"):
            Auction(**{**sample_auction_data, "state": "X"})

    def test_rejects_state_too_long(self, sample_auction_data):
        with pytest.raises(ValidationError, match="state"):
            Auction(**{**sample_auction_data, "state": "ABC"})
```

- [ ] **Step 6: Add enum rejection tests**

Append to `TestAuctionValidation`:

```python
    def test_rejects_invalid_sale_type(self, sample_auction_data):
        with pytest.raises(ValidationError, match="sale_type"):
            Auction(**{**sample_auction_data, "sale_type": "BOGUS"})

    def test_rejects_invalid_status(self, sample_auction_data):
        with pytest.raises(ValidationError, match="status"):
            Auction(**{**sample_auction_data, "status": "BOGUS"})

    def test_rejects_invalid_source_type(self, sample_auction_data):
        with pytest.raises(ValidationError, match="source_type"):
            Auction(**{**sample_auction_data, "source_type": "BOGUS"})
```

- [ ] **Step 7: Add missing required fields tests**

Append to `TestAuctionValidation`:

```python
    def test_rejects_missing_state(self, sample_auction_data):
        data = {**sample_auction_data}
        del data["state"]
        with pytest.raises(ValidationError, match="state"):
            Auction(**data)

    def test_rejects_missing_county(self, sample_auction_data):
        data = {**sample_auction_data}
        del data["county"]
        with pytest.raises(ValidationError, match="county"):
            Auction(**data)

    def test_rejects_missing_start_date(self, sample_auction_data):
        data = {**sample_auction_data}
        del data["start_date"]
        with pytest.raises(ValidationError, match="start_date"):
            Auction(**data)

    def test_rejects_missing_sale_type(self, sample_auction_data):
        data = {**sample_auction_data}
        del data["sale_type"]
        with pytest.raises(ValidationError, match="sale_type"):
            Auction(**data)

    def test_rejects_missing_source_type(self, sample_auction_data):
        data = {**sample_auction_data}
        del data["source_type"]
        with pytest.raises(ValidationError, match="source_type"):
            Auction(**data)
```

- [ ] **Step 8: Run all Auction tests**

Run: `uv run pytest tests/test_models.py::TestAuctionValidation -v`
Expected: all PASS

- [ ] **Step 9: Add CountyInfo validation tests**

Append to file:

```python
class TestCountyInfoValidation:
    """CountyInfo Pydantic model rejects invalid data."""

    def test_valid_county_info(self):
        ci = CountyInfo(fips_code="12086", state="FL", county_name="Miami-Dade")
        assert ci.fips_code == "12086"
        assert ci.priority.value == "medium"  # default

    def test_rejects_fips_too_short(self):
        with pytest.raises(ValidationError, match="fips_code"):
            CountyInfo(fips_code="1208", state="FL", county_name="Miami-Dade")

    def test_rejects_fips_too_long(self):
        with pytest.raises(ValidationError, match="fips_code"):
            CountyInfo(fips_code="120860", state="FL", county_name="Miami-Dade")

    def test_rejects_state_too_short(self):
        with pytest.raises(ValidationError, match="state"):
            CountyInfo(fips_code="12086", state="F", county_name="Miami-Dade")

    def test_rejects_state_too_long(self):
        with pytest.raises(ValidationError, match="state"):
            CountyInfo(fips_code="12086", state="FLA", county_name="Miami-Dade")

    def test_rejects_invalid_priority(self):
        with pytest.raises(ValidationError, match="priority"):
            CountyInfo(
                fips_code="12086",
                state="FL",
                county_name="Miami-Dade",
                priority="INVALID",
            )
```

- [ ] **Step 10: Add StateRules validation tests**

Append to file:

```python
class TestStateRulesValidation:
    """StateRules Pydantic model rejects invalid data."""

    def test_valid_state_rules(self):
        sr = StateRules(state="FL", sale_type="deed")
        assert sr.state == "FL"

    def test_rejects_state_too_short(self):
        with pytest.raises(ValidationError, match="state"):
            StateRules(state="F", sale_type="deed")

    def test_rejects_state_too_long(self):
        with pytest.raises(ValidationError, match="state"):
            StateRules(state="FLA", sale_type="deed")

    def test_rejects_invalid_sale_type(self):
        with pytest.raises(ValidationError, match="sale_type"):
            StateRules(state="FL", sale_type="BOGUS")
```

- [ ] **Step 11: Run all model tests**

Run: `uv run pytest tests/test_models.py -v`
Expected: all PASS

- [ ] **Step 12: Commit**

```bash
git add tests/test_models.py
git commit -m "test: add Pydantic model validation negative cases (issue #8)"
```

---

## Chunk 3: Seed Loader Idempotency

### Task 4: Create seed loader tests (`tests/test_seed_loader.py`)

**Files:**
- Create: `tests/test_seed_loader.py`

- [ ] **Step 1: Write seed loader tests**

```python
"""Seed loader idempotency tests — uses in-memory SQLite, no real DB."""

from __future__ import annotations

from sqlalchemy import func, select

from tdc_auction_calendar.db.seed_loader import load_seeds
from tdc_auction_calendar.models import CountyInfoRow, StateRulesRow, VendorMappingRow


class TestSeedLoaderIdempotency:
    """Running load_seeds twice produces the same row counts."""

    def _count(self, session, model):
        return session.scalar(select(func.count()).select_from(model))

    def test_first_load_inserts_rows(self, db_session):
        load_seeds(db_session)

        states = self._count(db_session, StateRulesRow)
        counties = self._count(db_session, CountyInfoRow)
        vendors = self._count(db_session, VendorMappingRow)

        assert states > 0, "Expected state_rules rows after first load"
        assert counties > 0, "Expected county_info rows after first load"
        assert vendors > 0, "Expected vendor_mapping rows after first load"

    def test_second_load_no_duplicates(self, db_session):
        load_seeds(db_session)
        first_states = self._count(db_session, StateRulesRow)
        first_counties = self._count(db_session, CountyInfoRow)
        first_vendors = self._count(db_session, VendorMappingRow)

        load_seeds(db_session)
        second_states = self._count(db_session, StateRulesRow)
        second_counties = self._count(db_session, CountyInfoRow)
        second_vendors = self._count(db_session, VendorMappingRow)

        assert second_states == first_states, "State rows duplicated on second load"
        assert second_counties == first_counties, "County rows duplicated on second load"
        assert second_vendors == first_vendors, "Vendor rows duplicated on second load"

    def test_spot_check_known_record(self, db_session):
        load_seeds(db_session)
        fl = db_session.query(StateRulesRow).filter_by(state="FL").first()
        assert fl is not None, "Expected FL in state_rules"
        assert fl.sale_type is not None
```

- [ ] **Step 2: Run seed loader tests**

Run: `uv run pytest tests/test_seed_loader.py -v`
Expected: all 3 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_seed_loader.py
git commit -m "test: add seed loader idempotency tests with in-memory SQLite (issue #8)"
```

---

## Chunk 4: Coverage Verification

### Task 5: Run full test suite with coverage

- [ ] **Step 1: Run all tests with coverage**

Run: `uv run pytest --cov=tdc_auction_calendar.models --cov=tdc_auction_calendar.collectors.statutory --cov-report=term-missing`
Expected: all tests pass, >= 80% coverage on both modules

- [ ] **Step 2: If coverage < 80%, identify gaps and add targeted tests**

Check the `term-missing` output for uncovered lines. Add tests as needed.

- [ ] **Step 3: Run full suite one final time**

Run: `uv run pytest`
Expected: all PASS, no warnings, no hardcoded paths, CI-friendly

- [ ] **Step 4: Final commit (if any coverage gap-fill was needed)**

```bash
git add -A tests/
git commit -m "test: fill coverage gaps for >= 80% on models + statutory collector (issue #8)"
```
