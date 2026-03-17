"""Validate vendor_mapping.json seed data against VendorMapping model and domain invariants."""

import json
import re

import pytest
from pydantic import ValidationError

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


def test_all_portal_vendors_represented(seed_data):
    """All portal-based vendors must have at least one seed entry.

    Vendors with dedicated collectors (e.g., Purdue) don't use the
    vendor_mapping seed and are excluded from this check.
    """
    from tdc_auction_calendar.models.enums import Vendor

    # Vendors that have their own dedicated collectors, not portal mappings
    dedicated_collector_vendors = {Vendor.PURDUE, Vendor.MVBA, Vendor.PUBLIC_SURPLUS}
    portal_vendors = ALLOWED_VENDORS - dedicated_collector_vendors

    vendors_present = {e["vendor"] for e in seed_data}
    missing = portal_vendors - vendors_present
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


# --- Negative validation tests ---

_VALID_KWARGS = {
    "vendor": "RealAuction",
    "vendor_url": "https://www.realauction.com",
    "state": "FL",
    "county": "Duval",
    "portal_url": "https://duval.realforeclose.com",
}


def test_rejects_unknown_vendor():
    with pytest.raises(ValidationError):
        VendorMapping(**{**_VALID_KWARGS, "vendor": "UnknownCo"})


def test_rejects_invalid_vendor_url():
    with pytest.raises(ValidationError):
        VendorMapping(**{**_VALID_KWARGS, "vendor_url": "not-a-url"})


def test_rejects_invalid_portal_url():
    with pytest.raises(ValidationError):
        VendorMapping(**{**_VALID_KWARGS, "portal_url": "ftp://example.com"})


def test_rejects_state_too_long():
    with pytest.raises(ValidationError):
        VendorMapping(**{**_VALID_KWARGS, "state": "FLA"})


def test_rejects_empty_county():
    with pytest.raises(ValidationError):
        VendorMapping(**{**_VALID_KWARGS, "county": ""})
