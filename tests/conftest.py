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
