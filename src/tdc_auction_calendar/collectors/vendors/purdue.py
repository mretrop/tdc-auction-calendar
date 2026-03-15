"""Purdue vendor collector — Texas tax foreclosure sales from pbfcm.com."""

from __future__ import annotations

import re

_BASE_URL = "https://www.pbfcm.com"
_LISTING_URL = f"{_BASE_URL}/taxsale.html"

# Matches "* COUNTY NAME COUNTY" at start of line (top-level list item)
_COUNTY_RE = re.compile(r"^\*\s+([A-Z\s]+?)\s*COUNTY\s*$", re.MULTILINE)

# Matches "[link text](relative/path.pdf)" nested under a county
_PDF_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+\.pdf)\)")


def parse_listing_markdown(markdown: str) -> list[tuple[str, str]]:
    """Parse the listing page markdown into (county_name, full_pdf_url) tuples.

    Returns one entry per PDF link. Multi-precinct counties produce
    multiple entries with the same county name.
    """
    results: list[tuple[str, str]] = []
    current_county: str | None = None

    for line in markdown.splitlines():
        county_match = _COUNTY_RE.match(line.strip())
        if county_match:
            current_county = county_match.group(1).strip().title()
            continue

        if current_county:
            pdf_match = _PDF_LINK_RE.search(line)
            if pdf_match:
                relative_url = pdf_match.group(2)
                full_url = f"{_BASE_URL}/{relative_url}"
                results.append((current_county, full_url))

    return results
