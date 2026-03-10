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


def test_entry_count(seed_data):
    """Guard against accidental deletions."""
    assert len(seed_data) >= 45, f"Expected at least 45 states, got {len(seed_data)}"


def test_all_entries_validate(seed_data):
    """Every entry must pass Pydantic StateRules validation."""
    for entry in seed_data:
        state = entry.get("state", "<unknown>")
        try:
            StateRules(**entry)
        except Exception as exc:
            pytest.fail(f"State {state} failed validation: {exc}")


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


def test_notice_requirement_weeks_positive(seed_data):
    """notice_requirement_weeks must be a positive integer."""
    for entry in seed_data:
        weeks = entry.get("notice_requirement_weeks")
        if weeks is not None:
            assert isinstance(weeks, int) and weeks >= 1, f"State {entry['state']}: invalid notice_requirement_weeks {weeks}"
