"""Health tracking and orchestrator report models."""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Mapped, mapped_column

from tdc_auction_calendar.models.jurisdiction import Base


class CollectorHealthRow(Base):
    """Tracks per-collector run health."""

    __tablename__ = "collector_health"

    collector_name: Mapped[str] = mapped_column(sa.String(100), primary_key=True)
    last_run: Mapped[datetime.datetime] = mapped_column(sa.DateTime)
    last_success: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime)
    records_collected: Mapped[int] = mapped_column(sa.Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(sa.Text)


class CollectorHealth(BaseModel):
    """Pydantic model for collector health status."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    collector_name: str = Field(min_length=1, max_length=100)
    last_run: datetime.datetime
    last_success: datetime.datetime | None = None
    records_collected: int = Field(default=0, ge=0)
    error_message: str | None = None


class CollectorError(BaseModel):
    """A single collector failure in a run."""

    model_config = ConfigDict(frozen=True)

    collector_name: str = Field(min_length=1)
    error: str
    error_type: str


class RunReport(BaseModel):
    """Result of an orchestrator run."""

    total_records: int = Field(ge=0)
    new_records: int = Field(default=0, ge=0)
    updated_records: int = Field(default=0, ge=0)
    skipped_records: int = Field(default=0, ge=0)
    collectors_succeeded: list[str]
    collectors_failed: list[CollectorError]
    per_collector_counts: dict[str, int] = {}
    duration_seconds: float = Field(ge=0)


class UpsertResult(BaseModel):
    """Counts from a batch upsert operation."""

    model_config = ConfigDict(frozen=True)

    new: int = Field(ge=0)
    updated: int = Field(ge=0)
    skipped: int = Field(ge=0)
