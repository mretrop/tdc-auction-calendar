"""Vendor mapping models."""

from __future__ import annotations

import sqlalchemy as sa
from pydantic import BaseModel, Field
from sqlalchemy.orm import Mapped, mapped_column

from tdc_auction_calendar.models.enums import Vendor
from tdc_auction_calendar.models.jurisdiction import Base

ALLOWED_VENDORS = frozenset(Vendor)


# --- SQLAlchemy ORM model ---


class VendorMappingRow(Base):
    __tablename__ = "vendor_mapping"

    vendor: Mapped[str] = mapped_column(sa.String(100), primary_key=True)
    state: Mapped[str] = mapped_column(sa.String(2), primary_key=True)
    county: Mapped[str] = mapped_column(sa.String(100), primary_key=True)
    vendor_url: Mapped[str] = mapped_column(sa.Text)
    portal_url: Mapped[str] = mapped_column(sa.Text)


# --- Pydantic validation model ---


class VendorMapping(BaseModel):
    vendor: Vendor
    vendor_url: str = Field(pattern=r"^https?://\S+$")
    state: str = Field(min_length=2, max_length=2)
    county: str = Field(min_length=1)
    portal_url: str = Field(pattern=r"^https?://\S+$")
