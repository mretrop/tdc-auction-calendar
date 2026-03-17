# src/tdc_auction_calendar/collectors/vendors/publicsurplus.py
"""PublicSurplus vendor collector — tax sale and lien auctions from publicsurplus.com."""

from __future__ import annotations

import re

_COUNTY_RE = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+County\b")


def extract_county(title: str) -> str:
    """Extract county name from an auction title, or 'Various' if not found."""
    m = _COUNTY_RE.search(title)
    return m.group(1) if m else "Various"
