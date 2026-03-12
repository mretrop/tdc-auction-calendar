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

    def test_rejects_state_too_short(self, sample_auction_data):
        with pytest.raises(ValidationError, match="state"):
            Auction(**{**sample_auction_data, "state": "X"})

    def test_rejects_state_too_long(self, sample_auction_data):
        with pytest.raises(ValidationError, match="state"):
            Auction(**{**sample_auction_data, "state": "ABC"})

    def test_rejects_invalid_sale_type(self, sample_auction_data):
        with pytest.raises(ValidationError, match="sale_type"):
            Auction(**{**sample_auction_data, "sale_type": "BOGUS"})

    def test_rejects_invalid_status(self, sample_auction_data):
        with pytest.raises(ValidationError, match="status"):
            Auction(**{**sample_auction_data, "status": "BOGUS"})

    def test_rejects_invalid_source_type(self, sample_auction_data):
        with pytest.raises(ValidationError, match="source_type"):
            Auction(**{**sample_auction_data, "source_type": "BOGUS"})

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
