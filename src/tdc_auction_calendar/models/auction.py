"""Auction model — the central data type."""

from __future__ import annotations

import datetime
from decimal import Decimal

import sqlalchemy as sa
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Mapped, mapped_column

from tdc_auction_calendar.models.enums import AuctionStatus, SaleType, SourceType
from tdc_auction_calendar.models.jurisdiction import Base


class AuctionRow(Base):
    __tablename__ = "auctions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    state: Mapped[str] = mapped_column(sa.String(2), index=True)
    county: Mapped[str] = mapped_column(sa.String(100), index=True)
    start_date: Mapped[datetime.date] = mapped_column(sa.Date, index=True)
    end_date: Mapped[datetime.date | None] = mapped_column(sa.Date)
    sale_type: Mapped[str] = mapped_column(sa.String(10))
    status: Mapped[str] = mapped_column(sa.String(15), default=AuctionStatus.UPCOMING)
    source_type: Mapped[str] = mapped_column(sa.String(20))
    source_url: Mapped[str | None] = mapped_column(sa.Text)
    registration_deadline: Mapped[datetime.date | None] = mapped_column(sa.Date)
    deposit_deadline: Mapped[datetime.date | None] = mapped_column(sa.Date)
    deposit_amount: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 2))
    min_bid: Mapped[Decimal | None] = mapped_column(sa.Numeric(12, 2))
    interest_rate: Mapped[Decimal | None] = mapped_column(sa.Numeric(5, 2))
    confidence_score: Mapped[float] = mapped_column(sa.Float, default=1.0)
    property_count: Mapped[int | None] = mapped_column(sa.Integer)
    vendor: Mapped[str | None] = mapped_column(sa.String(100))
    notes: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime, server_default=sa.func.now(), onupdate=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("state", "county", "start_date", "sale_type", name="uq_auction_dedup"),
    )


class Auction(BaseModel):
    """Pydantic model for auction validation."""

    state: str = Field(min_length=2, max_length=2)
    county: str
    start_date: datetime.date
    end_date: datetime.date | None = None
    sale_type: SaleType
    status: AuctionStatus = AuctionStatus.UPCOMING
    source_type: SourceType
    source_url: str | None = None
    registration_deadline: datetime.date | None = None
    deposit_deadline: datetime.date | None = None
    deposit_amount: Decimal | None = None
    min_bid: Decimal | None = None
    interest_rate: Decimal | None = None
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    property_count: int | None = None
    vendor: str | None = None
    notes: str | None = None

    @property
    def dedup_key(self) -> tuple[str, str, datetime.date, SaleType]:
        """Natural key for deduplication: (state, county, start_date, sale_type)."""
        return (self.state, self.county, self.start_date, self.sale_type)
