# src/tdc_auction_calendar/collectors/vendors/linebarger.py
"""Linebarger vendor collector — tax sale auctions from taxsales.lgbs.com API."""

from __future__ import annotations

import re


def normalize_county_name(raw: str) -> str:
    """Strip ' COUNTY' suffix and title-case the name.

    Examples:
        "HARRIS COUNTY" -> "Harris"
        "FORT BEND COUNTY" -> "Fort Bend"
        "JIM HOGG COUNTY" -> "Jim Hogg"
    """
    cleaned = re.sub(r"\s+county$", "", raw.strip(), flags=re.IGNORECASE)
    return cleaned.title()
