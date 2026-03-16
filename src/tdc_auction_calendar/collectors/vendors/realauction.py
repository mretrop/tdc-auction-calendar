"""RealAuction vendor collector — tax deed auctions from county subdomains."""

from __future__ import annotations

from datetime import date, datetime

from bs4 import BeautifulSoup

_ACCEPTED_SALE_TYPES = frozenset({"Tax Deed", "Treasurer Deed"})


def parse_calendar_html(html: str) -> list[dict]:
    """Parse a RealAuction calendar page HTML into auction dicts.

    Returns list of dicts with keys: date, sale_type, property_count, time.
    Filters out Foreclosure entries; accepts Tax Deed and Treasurer Deed.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    cells = soup.select(".CALSELT")
    results: list[dict] = []

    for cell in cells:
        caltext = cell.select_one(".CALTEXT")
        if caltext is None:
            continue
        sale_type = caltext.find(string=True, recursive=False)
        if sale_type is None:
            continue
        sale_type = sale_type.strip()
        if sale_type not in _ACCEPTED_SALE_TYPES:
            continue

        label = cell.get("aria-label", "")
        try:
            auction_date = datetime.strptime(label, "%B-%d-%Y").date()
        except ValueError:
            continue

        calsch = cell.select_one(".CALSCH")
        property_count = int(calsch.get_text()) if calsch else 0

        caltime = cell.select_one(".CALTIME")
        auction_time = caltime.get_text().strip() if caltime else ""

        results.append({
            "date": auction_date,
            "sale_type": sale_type,
            "property_count": property_count,
            "time": auction_time,
        })

    return results
