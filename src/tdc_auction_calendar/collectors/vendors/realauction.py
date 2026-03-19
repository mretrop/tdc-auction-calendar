"""RealAuction vendor collector — tax deed auctions from county subdomains."""

from __future__ import annotations

import asyncio
from datetime import date, datetime

import structlog
from bs4 import BeautifulSoup
from pydantic import ValidationError

from tdc_auction_calendar.collectors.base import BaseCollector
from tdc_auction_calendar.collectors.scraping.client import ScrapeClient, ScrapeError
from tdc_auction_calendar.collectors.scraping.cache import ResponseCache
from tdc_auction_calendar.collectors.scraping.fetchers.crawl4ai import Crawl4AiFetcher, StealthLevel
from tdc_auction_calendar.collectors.scraping.rate_limiter import RateLimiter
from tdc_auction_calendar.models.auction import Auction
from tdc_auction_calendar.models.enums import SaleType, SourceType, Vendor

logger = structlog.get_logger()

_MONTHS_AHEAD = 2
_MAX_CONCURRENT = 5

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
            logger.warning("realauction_date_parse_failed", aria_label=label)
            continue

        calsch = cell.select_one(".CALSCH")
        try:
            property_count = int(calsch.get_text()) if calsch else 0
        except ValueError:
            property_count = 0

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
    from urllib.parse import quote

    path = "/index.cfm?zaction=user&zmethod=calendar"
    if year is not None and month is not None:
        raw_param = f"{{ts '{year:04d}-{month:02d}-01 00:00:00'}}"
        path += f"&selCalDate={quote(raw_param)}"
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
    # New Jersey (municipality portals mapped to parent counties)
    ("NJ", "Sussex", "https://hardystonnj.realforeclose.com"),
    ("NJ", "Essex", "https://newarknj.realforeclose.com"),
]


class RealAuctionCollector(BaseCollector):
    """Collects tax deed auction dates from RealAuction county portals."""

    @property
    def name(self) -> str:
        return "realauction"

    @property
    def source_type(self) -> SourceType:
        return SourceType.VENDOR

    async def _fetch(self) -> list[Auction]:
        # Force Crawl4AI — Cloudflare Browser Rendering doesn't wait long enough
        # for RealAuction's jQuery/ColdFusion calendar to render.
        # StealthLevel.OFF required — magic mode triggers splash page redirect.
        client = ScrapeClient(
            primary=Crawl4AiFetcher(stealth=StealthLevel.OFF),
            rate_limiter=RateLimiter(default_delay=2.0),
            cache=ResponseCache(cache_dir="data/cache", ttl=21600),
        )
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

        async def _fetch_one(state: str, county: str, base_url: str, url: str) -> list[Auction]:
            async with semaphore:
                try:
                    result = await client.scrape(url)
                except ScrapeError as exc:
                    logger.error(
                        "realauction_fetch_failed",
                        state=state,
                        county=county,
                        url=url,
                        error=str(exc),
                    )
                    return []

                html = result.fetch.html or ""
                if not html:
                    logger.warning(
                        "realauction_empty_html",
                        state=state,
                        county=county,
                        url=url,
                    )
                    return []

                entries = parse_calendar_html(html)
                auctions: list[Auction] = []
                for entry in entries:
                    preview_url = (
                        f"{base_url}/index.cfm?zaction=AUCTION"
                        f"&Zmethod=PREVIEW"
                        f"&AUCTIONDATE={entry['date'].strftime('%m/%d/%Y')}"
                    )
                    raw = {
                        "state": state,
                        "county": county,
                        "date": entry["date"].isoformat(),
                        "sale_type": entry["sale_type"],
                        "property_count": entry["property_count"],
                        "time": entry["time"],
                        "source_url": preview_url,
                    }
                    try:
                        auctions.append(self.normalize(raw))
                    except (KeyError, TypeError, ValueError, ValidationError) as exc:
                        logger.error(
                            "realauction_normalize_failed",
                            raw=raw,
                            error=str(exc),
                        )
                return auctions

        # Build all fetch tasks
        now = date.today()
        tasks: list = []
        for state, county, base_url in SITES:
            tasks.append(_fetch_one(state, county, base_url, calendar_url(base_url)))
            month = now.month
            year = now.year
            for _ in range(_MONTHS_AHEAD):
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                tasks.append(_fetch_one(state, county, base_url, calendar_url(base_url, year, month)))

        results: list[list[Auction]] = []
        try:
            results = await asyncio.gather(*tasks)
        finally:
            await client.close()

        all_auctions: list[Auction] = []
        for batch in results:
            all_auctions.extend(batch)

        failed_tasks = sum(1 for b in results if not b)
        logger.info(
            "realauction_fetch_complete",
            sites=len(SITES),
            months=_MONTHS_AHEAD + 1,
            total_tasks=len(tasks),
            failed_tasks=failed_tasks,
            auctions=len(all_auctions),
        )
        return all_auctions

    def normalize(self, raw: dict) -> Auction:
        return Auction(
            state=raw["state"],
            county=raw["county"],
            start_date=date.fromisoformat(raw["date"]),
            sale_type=SaleType.DEED,
            source_type=SourceType.VENDOR,
            source_url=raw["source_url"],
            confidence_score=0.90,
            vendor=Vendor.REALAUCTION,
            property_count=raw.get("property_count"),
            notes=raw.get("time", ""),
        )
