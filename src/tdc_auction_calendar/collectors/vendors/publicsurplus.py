# src/tdc_auction_calendar/collectors/vendors/publicsurplus.py
"""PublicSurplus vendor collector — tax sale and lien auctions from publicsurplus.com."""

from __future__ import annotations

import re

US_STATES: frozenset[str] = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL",
    "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
})

_COUNTY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+County\b")


def extract_county(title: str) -> str:
    """Extract county name from an auction title, or 'Various' if not found."""
    m = _COUNTY_RE.search(title)
    return m.group(1) if m else "Various"
