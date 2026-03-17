"""Shared enumerations for auction calendar models."""

from enum import StrEnum


class SaleType(StrEnum):
    LIEN = "lien"
    DEED = "deed"
    HYBRID = "hybrid"


class AuctionStatus(StrEnum):
    UPCOMING = "upcoming"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SourceType(StrEnum):
    STATUTORY = "statutory"
    STATE_AGENCY = "state_agency"
    PUBLIC_NOTICE = "public_notice"
    COUNTY_WEBSITE = "county_website"
    VENDOR = "vendor"


class Priority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Vendor(StrEnum):
    REALAUCTION = "RealAuction"
    BID4ASSETS = "Bid4Assets"
    GOVEASE = "GovEase"
    GRANT_STREET = "Grant Street"
    SRI = "SRI"
    PURDUE = "Purdue, Brandon, Fielder, Collins & Mott"
    MVBA = "McCreary, Veselka, Bragg & Allen"
    PUBLIC_SURPLUS = "PublicSurplus"
    LINEBARGER = "Linebarger Goggan Blair & Sampson"
