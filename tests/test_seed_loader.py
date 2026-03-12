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
