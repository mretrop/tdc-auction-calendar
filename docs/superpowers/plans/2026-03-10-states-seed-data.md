# States Seed Data Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `states.json` seed file with statutory auction metadata for all US states that hold tax lien/deed/hybrid sales, validated against the existing Pydantic `StateRules` model.

**Architecture:** Single JSON seed file consumed by the existing idempotent seed loader. A validation test ensures data integrity against the Pydantic model. Web search spot-checks the 6 required states.

**Tech Stack:** Python, Pydantic, pytest, existing `StateRules` model and `seed_loader.py`

---

## File Structure

- **Create:** `src/tdc_auction_calendar/db/seed/states.json` — seed data for all applicable states
- **Create:** `tests/test_seed_states.py` — validation tests for the seed file
- No modifications to existing files needed

---

## Chunk 1: Validation Test + Seed Data

### Task 1: Write the validation test

**Files:**
- Create: `tests/test_seed_states.py`

- [x] **Step 1: Write the failing test file**

```python
"""Validate states.json seed data against StateRules Pydantic model."""

import json
from pathlib import Path

import pytest

from tdc_auction_calendar.models.jurisdiction import StateRules
from tdc_auction_calendar.models.enums import SaleType

SEED_FILE = Path(__file__).parent.parent / "src" / "tdc_auction_calendar" / "db" / "seed" / "states.json"

REQUIRED_FIELDS = {"state", "sale_type", "statutory_timing_description", "typical_months", "notice_requirement_weeks", "governing_statute"}
SPOT_CHECK_STATES = {"FL", "TX", "CA", "CO", "IL", "NJ"}


@pytest.fixture
def seed_data() -> list[dict]:
    assert SEED_FILE.exists(), f"Seed file not found: {SEED_FILE}"
    return json.loads(SEED_FILE.read_text())


def test_seed_file_exists():
    assert SEED_FILE.exists()


def test_all_entries_validate(seed_data):
    """Every entry must pass Pydantic StateRules validation."""
    for entry in seed_data:
        StateRules(**entry)


def test_no_duplicate_states(seed_data):
    """No duplicate state codes."""
    states = [e["state"] for e in seed_data]
    assert len(states) == len(set(states)), f"Duplicate states: {[s for s in states if states.count(s) > 1]}"


def test_required_fields_non_null(seed_data):
    """Data quality: these fields must not be null even though the Pydantic model allows Optional."""
    for entry in seed_data:
        for field in REQUIRED_FIELDS:
            assert entry.get(field) is not None, f"State {entry['state']}: {field} is null"


def test_valid_sale_types(seed_data):
    """All sale_type values must be valid SaleType enum members."""
    valid = {e.value for e in SaleType}
    for entry in seed_data:
        assert entry["sale_type"] in valid, f"State {entry['state']}: invalid sale_type '{entry['sale_type']}'"


def test_typical_months_valid(seed_data):
    """typical_months must be list of ints 1-12."""
    for entry in seed_data:
        months = entry.get("typical_months")
        if months is None:
            pytest.fail(f"State {entry['state']}: typical_months is null")
        assert isinstance(months, list) and len(months) > 0, f"State {entry['state']}: typical_months must be non-empty list"
        for m in months:
            assert isinstance(m, int) and 1 <= m <= 12, f"State {entry['state']}: invalid month {m}"


def test_spot_check_states_present(seed_data):
    """FL, TX, CA, CO, IL, NJ must all be present."""
    states = {e["state"] for e in seed_data}
    missing = SPOT_CHECK_STATES - states
    assert not missing, f"Missing spot-check states: {missing}"


def test_state_codes_are_valid(seed_data):
    """All state codes must be exactly 2 uppercase letters."""
    for entry in seed_data:
        s = entry["state"]
        assert len(s) == 2 and s.isalpha() and s.isupper(), f"Invalid state code: {s}"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_seed_states.py -v`
Expected: FAIL — seed file does not exist

- [x] **Step 3: Commit the test**

```bash
git add tests/test_seed_states.py
git commit -m "test: add validation tests for states.json seed data"
```

---

### Task 2: Spot-check the 6 required states

- [x] **Step 4: Web search FL, TX, CA, CO, IL, NJ**

For each state, verify:
- `sale_type` (lien/deed/hybrid)
- `redemption_period_months`
- `governing_statute`

Use web search to confirm against primary sources (state statutes, official .gov sites).

- [x] **Step 5: Document spot-check findings**

Record findings as a comment in the task or note discrepancies to fix in the seed data.

---

### Task 3: Create states.json

- [x] **Step 6: Create the seed file**

**Files:**
- Create: `src/tdc_auction_calendar/db/seed/states.json`

Write the complete JSON array with all applicable US states. Each entry must include:
- `state`: 2-letter uppercase code
- `sale_type`: "lien", "deed", or "hybrid"
- `statutory_timing_description`: human-readable description of when auctions occur
- `typical_months`: array of integer months (1-12)
- `notice_requirement_weeks`: integer
- `redemption_period_months`: integer or null (typically null for deed states, but some like TX have statutory redemption periods)
- `public_notice_url`: string or null
- `state_agency_url`: string or null
- `governing_statute`: statute reference string

States to include: all US states with tax lien, deed, or hybrid sale processes. Omit states without tax sale auctions.

- [x] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_seed_states.py -v`
Expected: ALL PASS

- [x] **Step 8: Commit the seed file**

```bash
git add src/tdc_auction_calendar/db/seed/states.json
git commit -m "feat: add states.json seed data for all tax sale states"
```

---

### Task 4: Final verification

- [x] **Step 9: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS (both existing tests and new seed tests)

- [x] **Step 10: Verify seed loader works with new data**

Run a quick Python check:
```bash
uv run python -c "
import json
from pathlib import Path
from tdc_auction_calendar.models.jurisdiction import StateRules

data = json.loads(Path('src/tdc_auction_calendar/db/seed/states.json').read_text())
for entry in data:
    StateRules(**entry)
print(f'Validated {len(data)} states successfully')
"
```

- [x] **Step 11: Commit any fixes if needed, then final commit**

```bash
git add tests/test_seed_states.py src/tdc_auction_calendar/db/seed/states.json
git commit -m "feat: complete states.json seed data (closes #4)"
```
