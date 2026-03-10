"""State rules and county info models."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from pydantic import BaseModel, Field
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tdc_auction_calendar.models.enums import Priority, SaleType


# --- SQLAlchemy base ---


class Base(DeclarativeBase):
    pass


# --- SQLAlchemy ORM models ---


class StateRulesRow(Base):
    __tablename__ = "state_rules"

    state: Mapped[str] = mapped_column(sa.String(2), primary_key=True)
    sale_type: Mapped[str] = mapped_column(sa.String(10))
    statutory_timing_description: Mapped[str | None] = mapped_column(sa.Text)
    typical_months: Mapped[list | None] = mapped_column(sa.JSON)
    notice_requirement_weeks: Mapped[int | None] = mapped_column(sa.Integer)
    redemption_period_months: Mapped[int | None] = mapped_column(sa.Integer)
    public_notice_url: Mapped[str | None] = mapped_column(sa.Text)
    state_agency_url: Mapped[str | None] = mapped_column(sa.Text)
    governing_statute: Mapped[str | None] = mapped_column(sa.Text)


class CountyInfoRow(Base):
    __tablename__ = "county_info"

    fips_code: Mapped[str] = mapped_column(sa.String(5), primary_key=True)
    state: Mapped[str] = mapped_column(sa.String(2), index=True)
    county_name: Mapped[str] = mapped_column(sa.String(100))
    treasurer_url: Mapped[str | None] = mapped_column(sa.Text)
    tax_sale_page_url: Mapped[str | None] = mapped_column(sa.Text)
    known_auction_vendor: Mapped[str | None] = mapped_column(sa.String(100))
    timezone: Mapped[str] = mapped_column(sa.String(50))
    priority: Mapped[str] = mapped_column(sa.String(10))


# --- Pydantic validation models ---


class StateRules(BaseModel):
    state: str = Field(min_length=2, max_length=2)
    sale_type: SaleType
    statutory_timing_description: str | None = None
    typical_months: list[int] | None = None
    notice_requirement_weeks: int | None = None
    redemption_period_months: int | None = None
    public_notice_url: str | None = None
    state_agency_url: str | None = None
    governing_statute: str | None = None


class CountyInfo(BaseModel):
    fips_code: str = Field(min_length=5, max_length=5)
    state: str = Field(min_length=2, max_length=2)
    county_name: str
    treasurer_url: str | None = None
    tax_sale_page_url: str | None = None
    known_auction_vendor: str | None = None
    timezone: str = "America/New_York"
    priority: Priority = Priority.MEDIUM
