# Issue #8: Test Coverage for Models, Seed Data & Statutory Collector

## Problem

Issue #8 requires unit tests for all M1 components with >= 80% coverage on models and statutory collector. Existing tests cover seed data validation, base collector deduplication, and statutory collector behavior well. Gaps remain in: Pydantic model negative-case validation, seed loader idempotency, shared fixtures, and coverage tooling.

## Approach

Minimal gap-fill — add only what's missing without reorganizing existing tests.

## Design

### 1. Shared Fixtures (`tests/conftest.py`)

New file providing reusable fixtures:

- **`db_engine`** — in-memory SQLite engine with `Base.metadata.create_all()`, disposed after use
- **`db_session`** — fresh SQLAlchemy session per test, rolled back and closed after each test
- **`sample_auction_data`** — valid Auction field dict, overridable per-test via spread syntax

Scope: each test gets a clean session with no cross-test pollution.

### 2. Model Validation Tests (`tests/test_models.py`)

Negative-case Pydantic validation tests using `pytest.raises(ValidationError)`:

**Auction:**
- Rejects `confidence_score` outside [0.0, 1.0] (e.g., -0.1, 1.5)
- Rejects `state` not exactly 2 chars (e.g., "X", "ABC")
- Rejects invalid `sale_type`, `status`, `source_type` enums
- Rejects missing required fields (state, county, start_date, sale_type)
- Accepts valid data (positive sanity check)

**CountyInfo:**
- Rejects `fips_code` not exactly 5 chars
- Rejects `state` not exactly 2 chars
- Rejects invalid `priority`

**StateRules:**
- Rejects `state` not exactly 2 chars
- Rejects invalid `sale_type`

**VendorMapping:** Already covered by existing negative tests in `test_seed_vendor_mapping.py` — no new tests needed.

### 3. Seed Loader Idempotency Test (`tests/test_seed_loader.py`)

Tests `load_seeds()` with in-memory SQLite session from conftest:

- **First load** — call `load_seeds(session)`, count rows in state_rules/county_info/vendor_mapping, assert > 0
- **Second load** — call `load_seeds(session)` again, assert row counts unchanged
- **Spot check** — verify known record (e.g., FL in state_rules) exists

Tests real seed JSON against real ORM layer with ephemeral database. No mocking.

### 4. Coverage Tooling

- Add `pytest-cov` to dev dependencies in `pyproject.toml`
- Run: `uv run pytest --cov=tdc_auction_calendar --cov-report=term-missing`
- Target: >= 80% on `models/` and `collectors/statutory/`

## Acceptance Criteria (from issue)

- [x] `uv run pytest` passes with >= 80% coverage on models and statutory collector
- [x] Tests use fixtures, no real DB or HTTP calls
- [x] CI-friendly (no interactive prompts, no hardcoded paths)

## Files to Create/Modify

| File | Action |
|------|--------|
| `tests/conftest.py` | Create — shared fixtures |
| `tests/test_models.py` | Create — model validation negative cases |
| `tests/test_seed_loader.py` | Create — seed loader idempotency |
| `pyproject.toml` | Modify — add pytest-cov |
