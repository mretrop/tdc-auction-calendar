"""Purdue vendor collector — Texas tax foreclosure sales from pbfcm.com."""

from __future__ import annotations

import asyncio
import re
import time
from datetime import date, datetime
from pathlib import Path

import httpx
import structlog
from pypdf import PdfReader

_BASE_URL = "https://www.pbfcm.com"
_LISTING_URL = f"{_BASE_URL}/taxsale.html"

logger = structlog.get_logger()

_PDF_CACHE_DIR = Path("data/research/purdue_pdfs")
_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
_DOWNLOAD_DELAY = 0.5  # seconds between PDF downloads

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


_MONTHS = (
    "January|February|March|April|May|June|"
    "July|August|September|October|November|December"
)

# Pattern 1: "Sale Date: April 7, 2026" or "Date of Sale: April 7, 2026"
_DATE_CONTEXTUAL_RE = re.compile(
    rf"(?:Sale\s+Date|Date\s+of\s+Sale)[:\s]+"
    rf"({_MONTHS})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s*(\d{{4}})",
    re.IGNORECASE,
)

# Pattern 2: "April 7, 2026" (month name, no label required)
_DATE_MONTH_NAME_RE = re.compile(
    rf"({_MONTHS})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s*(\d{{4}})",
    re.IGNORECASE,
)

# Pattern 3: "04/07/2026"
_DATE_NUMERIC_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def extract_sale_date(text: str) -> date | None:
    """Extract the sale date from PDF text content.

    Tries contextual patterns first (with "Sale Date" label),
    then general month-name patterns, then numeric.
    Returns None if no date found.
    """
    # Try contextual match first
    m = _DATE_CONTEXTUAL_RE.search(text)
    if m:
        return _parse_month_name_match(m)

    # Try general month name
    m = _DATE_MONTH_NAME_RE.search(text)
    if m:
        return _parse_month_name_match(m)

    # Try numeric
    m = _DATE_NUMERIC_RE.search(text)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(year, month, day)

    return None


def _parse_month_name_match(m: re.Match) -> date:
    """Convert a regex match with (month_name, day, year) groups to a date."""
    month_str, day_str, year_str = m.group(1), m.group(2), m.group(3)
    dt = datetime.strptime(f"{month_str} {day_str} {year_str}", "%B %d %Y")
    return dt.date()


def _is_cache_fresh(path: Path) -> bool:
    """Check if a cached PDF is less than 7 days old."""
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < _CACHE_TTL_SECONDS


async def download_and_parse_pdf(
    client: httpx.AsyncClient,
    url: str,
    cache_dir: Path | None = None,
) -> date | None:
    """Download a PDF (with caching), extract text, and parse the sale date.

    Returns None if download fails, text extraction fails, or no date found.
    """
    if cache_dir is None:
        cache_dir = _PDF_CACHE_DIR

    cache_dir.mkdir(parents=True, exist_ok=True)
    filename = url.rsplit("/", 1)[-1]
    cached_path = cache_dir / filename

    # Download if not cached or stale
    if not _is_cache_fresh(cached_path):
        response = await client.get(url)
        if response.status_code != 200:
            logger.warning(
                "pdf_download_failed",
                url=url,
                status_code=response.status_code,
            )
            return None
        cached_path.write_bytes(response.content)

    # Extract text
    try:
        reader = PdfReader(cached_path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        logger.warning("pdf_text_extraction_failed", url=url, error=str(exc))
        return None

    # Parse date
    sale_date = extract_sale_date(text)
    if sale_date is None:
        logger.warning("pdf_no_date_found", url=url)
    return sale_date
