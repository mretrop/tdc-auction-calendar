# Counties Seed Data Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `counties.json` with 200+ county records covering all counties in FL/IL/NJ/CO/CA plus top metro counties from other states.

**Architecture:** Single JSON seed file + test file. No changes to existing code — seed_loader already supports counties.

**Tech Stack:** Python, Pydantic, SQLAlchemy, pytest, zoneinfo

**Spec:** `docs/superpowers/specs/2026-03-10-counties-seed-data-design.md`

---

## Chunk 1: Test File + Seed Data

### Task 1: Write the test file

**Files:**
- Create: `tests/test_seed_counties.py`
- Reference: `tests/test_seed_states.py` (pattern to follow)
- Reference: `src/tdc_auction_calendar/models/jurisdiction.py` (CountyInfo, CountyInfoRow)
- Reference: `src/tdc_auction_calendar/models/enums.py` (Priority)
- Reference: `src/tdc_auction_calendar/db/seed_loader.py` (SEED_DIR)

- [ ] **Step 1: Create test file with all 14 tests**

The FIPS state prefix mapping is needed for test 7. Use a dict mapping 2-letter state codes to their 2-digit FIPS state prefix. The test file should contain all tests from the spec.

```python
"""Validate counties.json seed data against CountyInfo model and domain invariants."""

import json
from zoneinfo import ZoneInfo

import pytest

from tdc_auction_calendar.db.seed_loader import SEED_DIR
from tdc_auction_calendar.models.enums import Priority
from tdc_auction_calendar.models.jurisdiction import CountyInfo, CountyInfoRow

SEED_FILE = SEED_DIR / "counties.json"
STATES_SEED_FILE = SEED_DIR / "states.json"

ALLOWED_VENDORS = {"RealAuction", "Bid4Assets", "GovEase", "Grant Street", "SRI", "direct"}

# FIPS state codes (first 2 digits of a 5-digit county FIPS)
FIPS_STATE_CODES = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "DC": "11", "FL": "12",
    "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18",
    "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23",
    "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28",
    "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55",
    "WY": "56",
}

# Minimum county counts for full-coverage states
FULL_COVERAGE_MINIMUMS = {
    "FL": 67,
    "IL": 102,
    "NJ": 21,
    "CO": 64,
    "CA": 58,
}

SPOT_CHECK_COUNTIES = {
    "12086": ("FL", "Miami-Dade"),
    "17031": ("IL", "Cook"),
    "06037": ("CA", "Los Angeles"),
    "08031": ("CO", "Denver"),
    "34013": ("NJ", "Essex"),
    "48201": ("TX", "Harris"),
    "04013": ("AZ", "Maricopa"),
    "36061": ("NY", "New York"),
}


@pytest.fixture
def seed_data() -> list[dict]:
    assert SEED_FILE.exists(), f"Seed file not found: {SEED_FILE}"
    return json.loads(SEED_FILE.read_text())


@pytest.fixture
def states_data() -> set[str]:
    assert STATES_SEED_FILE.exists(), f"States seed file not found: {STATES_SEED_FILE}"
    data = json.loads(STATES_SEED_FILE.read_text())
    return {entry["state"] for entry in data}


def test_seed_file_exists():
    assert SEED_FILE.exists()


def test_entry_count(seed_data):
    """Guard against accidental deletions."""
    assert len(seed_data) >= 200, f"Expected at least 200 counties, got {len(seed_data)}"


def test_all_entries_validate(seed_data):
    """Every entry must pass Pydantic CountyInfo validation."""
    for entry in seed_data:
        fips = entry.get("fips_code", "<unknown>")
        try:
            CountyInfo(**entry)
        except Exception as exc:
            pytest.fail(f"County {fips} failed validation: {exc}")


def test_all_entries_orm_compatible(seed_data):
    """Every entry must be instantiable as a CountyInfoRow (ORM layer used by seed_loader)."""
    for entry in seed_data:
        fips = entry.get("fips_code", "<unknown>")
        try:
            CountyInfoRow(**entry)
        except Exception as exc:
            pytest.fail(f"County {fips} failed ORM instantiation: {exc}")


def test_no_duplicate_fips_codes(seed_data):
    """No duplicate FIPS codes."""
    codes = [e["fips_code"] for e in seed_data]
    dupes = [c for c in codes if codes.count(c) > 1]
    assert len(codes) == len(set(codes)), f"Duplicate FIPS codes: {set(dupes)}"


def test_fips_codes_valid_format(seed_data):
    """FIPS codes must be exactly 5 digits, all numeric."""
    for entry in seed_data:
        fips = entry["fips_code"]
        assert len(fips) == 5 and fips.isdigit(), (
            f"County {entry['county_name']}: invalid FIPS code '{fips}'"
        )


def test_fips_state_prefix_matches(seed_data):
    """First 2 digits of FIPS code must match the state's FIPS state code."""
    for entry in seed_data:
        state = entry["state"]
        fips = entry["fips_code"]
        expected_prefix = FIPS_STATE_CODES.get(state)
        assert expected_prefix is not None, f"No FIPS state code mapping for {state}"
        assert fips[:2] == expected_prefix, (
            f"County {entry['county_name']} ({state}): FIPS prefix '{fips[:2]}' "
            f"doesn't match expected '{expected_prefix}'"
        )


def test_states_exist_in_states_seed(seed_data, states_data):
    """All states referenced in counties.json must exist in states.json."""
    county_states = {e["state"] for e in seed_data}
    missing = county_states - states_data
    assert not missing, f"States in counties.json but not in states.json: {missing}"


def test_valid_priority_values(seed_data):
    """All priority values must be valid Priority enum members."""
    valid = {e.value for e in Priority}
    for entry in seed_data:
        assert entry["priority"] in valid, (
            f"County {entry['county_name']}: invalid priority '{entry['priority']}'"
        )


def test_valid_timezone_strings(seed_data):
    """All timezone values must be valid IANA timezone strings."""
    for entry in seed_data:
        tz = entry["timezone"]
        try:
            ZoneInfo(tz)
        except (KeyError, Exception):
            pytest.fail(
                f"County {entry['county_name']} ({entry['state']}): "
                f"invalid timezone '{tz}'"
            )


def test_full_coverage_state_minimums(seed_data):
    """Full-coverage states must have at least their expected county count."""
    state_counts: dict[str, int] = {}
    for entry in seed_data:
        state_counts[entry["state"]] = state_counts.get(entry["state"], 0) + 1
    for state, minimum in FULL_COVERAGE_MINIMUMS.items():
        actual = state_counts.get(state, 0)
        assert actual >= minimum, (
            f"State {state}: expected >= {minimum} counties, got {actual}"
        )


def test_spot_check_counties(seed_data):
    """Known major counties must be present with correct FIPS codes."""
    fips_map = {e["fips_code"]: (e["state"], e["county_name"]) for e in seed_data}
    for fips, (expected_state, expected_name) in SPOT_CHECK_COUNTIES.items():
        assert fips in fips_map, f"Missing spot-check county: {expected_name} ({expected_state}), FIPS {fips}"
        actual_state, actual_name = fips_map[fips]
        assert actual_state == expected_state, (
            f"FIPS {fips}: expected state {expected_state}, got {actual_state}"
        )
        assert actual_name == expected_name, (
            f"FIPS {fips}: expected name '{expected_name}', got '{actual_name}'"
        )


def test_valid_vendor_values(seed_data):
    """Non-null known_auction_vendor values must be in the allowed set."""
    for entry in seed_data:
        vendor = entry.get("known_auction_vendor")
        if vendor is not None:
            assert vendor in ALLOWED_VENDORS, (
                f"County {entry['county_name']} ({entry['state']}): "
                f"invalid vendor '{vendor}'"
            )


def test_no_duplicate_county_names_per_state(seed_data):
    """No duplicate county names within the same state."""
    seen: dict[str, set[str]] = {}
    for entry in seed_data:
        state = entry["state"]
        name = entry["county_name"]
        if state not in seen:
            seen[state] = set()
        assert name not in seen[state], (
            f"Duplicate county name '{name}' in state {state}"
        )
        seen[state].add(name)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_seed_counties.py -v`
Expected: `test_seed_file_exists` FAILS (counties.json doesn't exist yet). Most other tests will also fail or error.

- [ ] **Step 3: Commit test file**

```bash
git add tests/test_seed_counties.py
git commit -m "test: add counties.json seed data validation tests (issue #5)"
```

### Task 2: Generate counties.json — FL (67 counties)

**Files:**
- Create: `src/tdc_auction_calendar/db/seed/counties.json`

- [ ] **Step 1: Create counties.json with all 67 FL counties**

Generate the full FL county list. All FL counties get `"known_auction_vendor": "RealAuction"`. Priority: all `"high"` (FL is the biggest tax sale market). Timezone: `"America/New_York"` for most, `"America/Chicago"` for panhandle counties (Bay, Calhoun, Escambia, Franklin, Gadsden, Gulf, Holmes, Jackson, Liberty, Okaloosa, Santa Rosa, Walton, Washington).

The file starts with `[` and each entry is a JSON object. Sort alphabetically by county_name within FL.

FIPS codes for FL counties range from 12001 to 12133 (odd numbers: 12001, 12003, 12005, ..., 12133).

Write the complete FL section to `counties.json`.

- [ ] **Step 2: Run tests to check partial progress**

Run: `uv run pytest tests/test_seed_counties.py::test_seed_file_exists tests/test_seed_counties.py::test_all_entries_validate tests/test_seed_counties.py::test_fips_codes_valid_format tests/test_seed_counties.py::test_fips_state_prefix_matches -v`
Expected: All PASS. `test_entry_count` will still fail (only 67 so far).

- [ ] **Step 3: Commit**

```bash
git add src/tdc_auction_calendar/db/seed/counties.json
git commit -m "feat: add FL counties to counties.json seed data (67 counties)"
```

### Task 3: Add IL counties (102 counties)

**Files:**
- Modify: `src/tdc_auction_calendar/db/seed/counties.json`

- [ ] **Step 1: Append all 102 IL counties**

IL FIPS codes range from 17001 to 17203 (odd numbers). Timezone: `"America/Chicago"` for all IL counties. `known_auction_vendor`: null (varies by county in IL). Priority: Cook County (`17031`) is `"high"`, remaining are `"medium"`. Sort alphabetically by county_name within IL section.

- [ ] **Step 2: Run validation tests**

Run: `uv run pytest tests/test_seed_counties.py::test_all_entries_validate tests/test_seed_counties.py::test_no_duplicate_fips_codes tests/test_seed_counties.py::test_fips_state_prefix_matches -v`
Expected: All PASS.

- [ ] **Step 3: Commit**

```bash
git add src/tdc_auction_calendar/db/seed/counties.json
git commit -m "feat: add IL counties to counties.json seed data (102 counties)"
```

### Task 4: Add NJ counties (21 counties)

**Files:**
- Modify: `src/tdc_auction_calendar/db/seed/counties.json`

- [ ] **Step 1: Append all 21 NJ counties**

NJ FIPS codes range from 34001 to 34041 (odd numbers). Timezone: `"America/New_York"` for all. `known_auction_vendor`: null (varies). Priority: Bergen (`34003`), Essex (`34013`), Hudson (`34017`), Middlesex (`34023`), Union (`34039`) are `"high"`, rest `"medium"`. Sort alphabetically.

- [ ] **Step 2: Run validation tests**

Run: `uv run pytest tests/test_seed_counties.py::test_all_entries_validate tests/test_seed_counties.py::test_no_duplicate_fips_codes -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/tdc_auction_calendar/db/seed/counties.json
git commit -m "feat: add NJ counties to counties.json seed data (21 counties)"
```

### Task 5: Add CO counties (64 counties)

**Files:**
- Modify: `src/tdc_auction_calendar/db/seed/counties.json`

- [ ] **Step 1: Append all 64 CO counties**

CO FIPS codes range from 08001 to 08125 (odd numbers). Timezone: `"America/Denver"` for all. `known_auction_vendor`: null. Priority: Denver (`08031`), Arapahoe (`08005`), El Paso (`08041`), Jefferson (`08059`), Adams (`08001`) are `"high"`, rest `"medium"`. Sort alphabetically.

- [ ] **Step 2: Run validation tests**

Run: `uv run pytest tests/test_seed_counties.py::test_all_entries_validate tests/test_seed_counties.py::test_fips_state_prefix_matches -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/tdc_auction_calendar/db/seed/counties.json
git commit -m "feat: add CO counties to counties.json seed data (64 counties)"
```

### Task 6: Add CA counties (58 counties)

**Files:**
- Modify: `src/tdc_auction_calendar/db/seed/counties.json`

- [ ] **Step 1: Append all 58 CA counties**

CA FIPS codes range from 06001 to 06115 (odd numbers). Timezone: `"America/Los_Angeles"` for all. `known_auction_vendor`: null (varies by county). Priority: Los Angeles (`06037`), San Diego (`06073`), Orange (`06059`), Riverside (`06065`), San Bernardino (`06071`), Santa Clara (`06085`), Alameda (`06001`), Sacramento (`06067`) are `"high"`, rest `"medium"`. Sort alphabetically.

- [ ] **Step 2: Run validation tests — entry count should now pass**

Run: `uv run pytest tests/test_seed_counties.py::test_entry_count tests/test_seed_counties.py::test_full_coverage_state_minimums -v`
Expected: PASS (we now have 67+102+21+64+58 = 312 counties, exceeding 200).

- [ ] **Step 3: Commit**

```bash
git add src/tdc_auction_calendar/db/seed/counties.json
git commit -m "feat: add CA counties to counties.json seed data (58 counties)"
```

### Task 7: Add top metro counties from remaining states (~50 counties)

**Files:**
- Modify: `src/tdc_auction_calendar/db/seed/counties.json`

- [ ] **Step 1: Append ~50 top metro counties**

Add the largest counties by population from states not yet covered. Include at minimum:
- **TX:** Harris (48201), Dallas (48113), Tarrant (48439), Bexar (48029), Travis (48453) — `America/Chicago`
- **AZ:** Maricopa (04013), Pima (04019) — `America/Phoenix`
- **NY:** New York (36061), Kings (36047), Queens (36081), Bronx (36005), Suffolk (36103), Nassau (36059), Westchester (36119), Erie (36029) — `America/New_York`
- **GA:** Fulton (13121), DeKalb (13089), Gwinnett (13135), Cobb (13067) — `America/New_York`
- **PA:** Philadelphia (42101), Allegheny (42003) — `America/New_York`
- **OH:** Cuyahoga (39035), Franklin (39049), Hamilton (39061) — `America/New_York`
- **MI:** Wayne (26163), Oakland (26125), Macomb (26099) — `America/Detroit`
- **WA:** King (53033), Pierce (53053) — `America/Los_Angeles`
- **NC:** Mecklenburg (37119), Wake (37183) — `America/New_York`
- **TN:** Shelby (47157), Davidson (47037) — `America/Chicago`
- **MD:** Baltimore County (24005), Montgomery (24031), Prince George's (24033) — `America/New_York`
- **IN:** Marion (18097), Lake (18089) — `America/Indiana/Indianapolis`, `America/Chicago` respectively
- **SC:** Charleston (45019), Greenville (45045) — `America/New_York`
- **MO:** St. Louis County (29189), Jackson (29095) — `America/Chicago`
- **VA:** Fairfax (51059), Virginia Beach (51810) — `America/New_York`
- **NV:** Clark (32003) — `America/Los_Angeles`
- **AL:** Jefferson (01073), Mobile (01097) — `America/Chicago`
- **LA:** Orleans (22071), East Baton Rouge (22033) — `America/Chicago`
- **WI:** Milwaukee (55079), Dane (55025) — `America/Chicago`
- **MN:** Hennepin (27053), Ramsey (27123) — `America/Chicago`
- **MA:** Suffolk (25025), Middlesex (25017) — `America/New_York`

All metro counties: priority `"high"`. Vendor: `"Bid4Assets"` for TX counties, null for most others. Insert each state's entries in the correct alphabetical position within the overall state-sorted array.

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest tests/test_seed_counties.py -v`
Expected: ALL PASS.

- [ ] **Step 3: If any tests fail, fix the data and re-run**

Common issues to check:
- Incorrect FIPS codes (verify state prefix matches)
- Invalid timezone strings (use `python -c "from zoneinfo import ZoneInfo; ZoneInfo('...')"` to test)
- Duplicate county names within a state
- Sort order violations

- [ ] **Step 4: Commit**

```bash
git add src/tdc_auction_calendar/db/seed/counties.json
git commit -m "feat: add top metro counties from remaining states (issue #5)"
```

### Task 8: Final validation and sort order check

**Files:**
- Modify: `src/tdc_auction_calendar/db/seed/counties.json` (if sort order needs fixing)

- [ ] **Step 1: Verify sort order (state asc, county_name asc)**

Run a quick check:
```bash
uv run python -c "
import json
from pathlib import Path
data = json.loads(Path('src/tdc_auction_calendar/db/seed/counties.json').read_text())
sorted_data = sorted(data, key=lambda x: (x['state'], x['county_name']))
if data != sorted_data:
    print('SORT ORDER INCORRECT — fixing...')
    Path('src/tdc_auction_calendar/db/seed/counties.json').write_text(
        json.dumps(sorted_data, indent=2) + '\n'
    )
    print('Fixed.')
else:
    print('Sort order OK')
print(f'Total counties: {len(data)}')
states = {}
for c in data:
    states[c[\"state\"]] = states.get(c[\"state\"], 0) + 1
for s, count in sorted(states.items()):
    print(f'  {s}: {count}')
"
```

- [ ] **Step 2: Run the full test suite one final time**

Run: `uv run pytest tests/test_seed_counties.py -v`
Expected: ALL 14 tests PASS.

- [ ] **Step 3: Run existing tests to ensure no regressions**

Run: `uv run pytest -v`
Expected: ALL tests PASS (including existing test_seed_states.py).

- [ ] **Step 4: Commit if sort was fixed**

```bash
git add src/tdc_auction_calendar/db/seed/counties.json
git commit -m "fix: ensure counties.json sort order (state, county_name)"
```
