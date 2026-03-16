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


def calendar_url(base_url: str, year: int | None = None, month: int | None = None) -> str:
    """Build a RealAuction calendar page URL."""
    path = "/index.cfm?zaction=user&zmethod=calendar"
    if year is not None and month is not None:
        path += f"&selCalDate={{ts '{year:04d}-{month:02d}-01 00:00:00'}}"
    return f"{base_url}{path}"


SITES: list[tuple[str, str, str]] = [
    # Arizona
    ("AZ", "Apache", "https://apache.realtaxdeed.com"),
    ("AZ", "Coconino", "https://coconino.realtaxdeed.com"),
    ("AZ", "Mohave", "https://mohave.realtaxdeed.com"),
    # Colorado
    ("CO", "Adams", "https://adams.treasurersdeedsale.realtaxdeed.com"),
    ("CO", "Denver", "https://denver.treasurersdeedsale.realtaxdeed.com"),
    ("CO", "Eagle", "https://eagle.treasurersdeedsale.realtaxdeed.com"),
    ("CO", "El Paso", "https://elpasoco.treasurersdeedsale.realtaxdeed.com"),
    ("CO", "Larimer", "https://larimer.treasurersdeedsale.realtaxdeed.com"),
    ("CO", "Mesa", "https://mesa.treasurersdeedsale.realtaxdeed.com"),
    ("CO", "Pitkin", "https://pitkin.treasurersdeedsale.realtaxdeed.com"),
    ("CO", "Weld", "https://weld.treasurersdeedsale.realtaxdeed.com"),
    # Florida — dedicated .realtaxdeed.com
    ("FL", "Alachua", "https://alachua.realtaxdeed.com"),
    ("FL", "Baker", "https://baker.realtaxdeed.com"),
    ("FL", "Bay", "https://bay.realtaxdeed.com"),
    ("FL", "Brevard", "https://brevard.realtaxdeed.com"),
    ("FL", "Citrus", "https://citrus.realtaxdeed.com"),
    ("FL", "Clay", "https://clay.realtaxdeed.com"),
    ("FL", "Duval", "https://duval.realtaxdeed.com"),
    ("FL", "Escambia", "https://escambia.realtaxdeed.com"),
    ("FL", "Flagler", "https://flagler.realtaxdeed.com"),
    ("FL", "Gilchrist", "https://gilchrist.realtaxdeed.com"),
    ("FL", "Gulf", "https://gulf.realtaxdeed.com"),
    ("FL", "Hendry", "https://hendry.realtaxdeed.com"),
    ("FL", "Hernando", "https://hernando.realtaxdeed.com"),
    ("FL", "Highlands", "https://highlands.realtaxdeed.com"),
    ("FL", "Hillsborough", "https://hillsborough.realtaxdeed.com"),
    ("FL", "Indian River", "https://indianriver.realtaxdeed.com"),
    ("FL", "Jackson", "https://jackson.realtaxdeed.com"),
    ("FL", "Lake", "https://lake.realtaxdeed.com"),
    ("FL", "Lee", "https://lee.realtaxdeed.com"),
    ("FL", "Leon", "https://leon.realtaxdeed.com"),
    ("FL", "Marion", "https://marion.realtaxdeed.com"),
    ("FL", "Martin", "https://martin.realtaxdeed.com"),
    ("FL", "Monroe", "https://monroe.realtaxdeed.com"),
    ("FL", "Nassau", "https://nassau.realtaxdeed.com"),
    ("FL", "Orange", "https://orange.realtaxdeed.com"),
    ("FL", "Osceola", "https://osceola.realtaxdeed.com"),
    ("FL", "Palm Beach", "https://palmbeach.realtaxdeed.com"),
    ("FL", "Pasco", "https://pasco.realtaxdeed.com"),
    ("FL", "Pinellas", "https://pinellas.realtaxdeed.com"),
    ("FL", "Polk", "https://polk.realtaxdeed.com"),
    ("FL", "Putnam", "https://putnam.realtaxdeed.com"),
    ("FL", "Santa Rosa", "https://santarosa.realtaxdeed.com"),
    ("FL", "Sarasota", "https://sarasota.realtaxdeed.com"),
    ("FL", "Seminole", "https://seminole.realtaxdeed.com"),
    ("FL", "Suwannee", "https://suwannee.realtaxdeed.com"),
    ("FL", "Volusia", "https://volusia.realtaxdeed.com"),
    ("FL", "Washington", "https://washington.realtaxdeed.com"),
    # Florida — combined portals (.realforeclose.com)
    ("FL", "Broward", "https://broward.realforeclose.com"),
    ("FL", "Calhoun", "https://calhoun.realforeclose.com"),
    ("FL", "Charlotte", "https://charlotte.realforeclose.com"),
    ("FL", "Collier", "https://collier.realforeclose.com"),
    ("FL", "Manatee", "https://manatee.realforeclose.com"),
    ("FL", "Miami-Dade", "https://miamidade.realforeclose.com"),
    ("FL", "Okeechobee", "https://okeechobee.realforeclose.com"),
    ("FL", "St. Lucie", "https://stlucie.realforeclose.com"),
    ("FL", "Walton", "https://walton.realforeclose.com"),
    # New Jersey
    ("NJ", "Hardyston", "https://hardystonnj.realforeclose.com"),
    ("NJ", "Newark", "https://newarknj.realforeclose.com"),
]
