"""Database engine and session configuration."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DB_PATH = Path("data") / "auction_calendar.db"


def get_database_url() -> str:
    """Return the database URL from env or default to local SQLite."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    # Ensure the data directory exists for the default SQLite path
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_DB_PATH}"


def get_engine(url: str | None = None):
    """Create a SQLAlchemy engine."""
    return create_engine(url or get_database_url())


def get_session(url: str | None = None) -> Session:
    """Create a new database session."""
    engine = get_engine(url)
    return sessionmaker(bind=engine)()
