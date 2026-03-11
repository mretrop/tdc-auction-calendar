"""Vendor mapping models."""

from __future__ import annotations

import sqlalchemy as sa
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Mapped, mapped_column

from tdc_auction_calendar.models.jurisdiction import Base


ALLOWED_VENDORS = frozenset({"RealAuction", "Bid4Assets", "GovEase", "Grant Street", "SRI"})


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
    vendor: str
    vendor_url: str = Field(pattern=r"^https?://")
    state: str = Field(min_length=2, max_length=2)
    county: str = Field(min_length=1)
    portal_url: str = Field(pattern=r"^https?://")

    @field_validator("vendor")
    @classmethod
    def vendor_must_be_allowed(cls, v: str) -> str:
        if v not in ALLOWED_VENDORS:
            raise ValueError(f"Unknown vendor '{v}', must be one of {ALLOWED_VENDORS}")
        return v
