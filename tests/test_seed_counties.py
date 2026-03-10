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
