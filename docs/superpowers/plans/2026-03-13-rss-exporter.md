# RSS Exporter Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add RSS 2.0 feed export for auction records with a `--days` convenience flag.

**Architecture:** Create `exporters/rss.py` with `auctions_to_rss()` using stdlib `xml.etree.ElementTree` and `email.utils.format_datetime` for RFC 822 dates. Wire into CLI replacing the stub, reusing shared helpers.

**Tech Stack:** Python stdlib `xml.etree.ElementTree`, `email.utils`, `html`, Typer CLI

---

## Chunk 1: RSS Exporter Module

### Task 1: RSS exporter with XML validation tests

**Files:**
- Create: `src/tdc_auction_calendar/exporters/rss.py`
- Create: `tests/test_rss_export.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rss_export.py`:

```python
"""Tests for RSS exporter."""

from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
from decimal import Decimal

from tdc_auction_calendar.exporters.rss import auctions_to_rss
from tdc_auction_calendar.models.auction import Auction


def _make_auction(**overrides) -> Auction:
    """Build an Auction with sensible defaults."""
    defaults = {
        "state": "FL",
        "county": "Miami-Dade",
        "start_date": datetime.date(2027, 4, 15),
        "end_date": datetime.date(2027, 4, 17),
        "sale_type": "deed",
        "status": "upcoming",
        "source_type": "statutory",
        "confidence_score": 1.0,
    }
    defaults.update(overrides)
    return Auction(**defaults)


class TestAuctionsToRss:
    def test_empty_list_returns_valid_rss(self):
        result = auctions_to_rss([])
        root = ET.fromstring(result)
        assert root.tag == "rss"
        assert root.attrib["version"] == "2.0"
        channel = root.find("channel")
        assert channel is not None
        assert channel.find("title").text == "Tax Auction Calendar"
        items = channel.findall("item")
        assert items == []

    def test_custom_title(self):
        result = auctions_to_rss([], title="Tax Auction Calendar — FL")
        root = ET.fromstring(result)
        assert root.find("channel/title").text == "Tax Auction Calendar — FL"

    def test_single_auction_produces_item(self):
        auction = _make_auction()
        result = auctions_to_rss([auction])
        root = ET.fromstring(result)
        items = root.findall("channel/item")
        assert len(items) == 1

    def test_item_title_format(self):
        auction = _make_auction(county="Miami-Dade", state="FL", sale_type="deed",
                                start_date=datetime.date(2027, 4, 15))
        result = auctions_to_rss([auction])
        root = ET.fromstring(result)
        item = root.find("channel/item")
        assert item.find("title").text == "Miami-Dade FL Tax Deed Sale — 2027-04-15"

    def test_guid_is_stable(self):
        auction = _make_auction(state="FL", county="Miami-Dade",
                                start_date=datetime.date(2027, 4, 15), sale_type="deed")
        result1 = auctions_to_rss([auction])
        result2 = auctions_to_rss([auction])
        root1 = ET.fromstring(result1)
        root2 = ET.fromstring(result2)
        guid1 = root1.find("channel/item/guid").text
        guid2 = root2.find("channel/item/guid").text
        assert guid1 == guid2
        assert guid1 == "FL-Miami-Dade-2027-04-15-deed"

    def test_guid_is_not_permalink(self):
        auction = _make_auction()
        result = auctions_to_rss([auction])
        root = ET.fromstring(result)
        guid = root.find("channel/item/guid")
        assert guid.attrib["isPermaLink"] == "false"

    def test_description_contains_key_fields(self):
        auction = _make_auction(
            registration_deadline=datetime.date(2027, 4, 1),
            deposit_amount=Decimal("5000.00"),
            vendor="RealAuction",
            source_url="https://example.com/auction",
        )
        result = auctions_to_rss([auction])
        root = ET.fromstring(result)
        desc = root.find("channel/item/description").text
        assert "2027-04-01" in desc
        assert "5000.00" in desc
        assert "RealAuction" in desc
        assert "https://example.com/auction" in desc

    def test_item_link_from_source_url(self):
        auction = _make_auction(source_url="https://example.com/auction")
        result = auctions_to_rss([auction])
        root = ET.fromstring(result)
        link = root.find("channel/item/link")
        assert link.text == "https://example.com/auction"

    def test_item_link_absent_when_no_source_url(self):
        auction = _make_auction(source_url=None)
        result = auctions_to_rss([auction])
        root = ET.fromstring(result)
        link = root.find("channel/item/link")
        assert link is None

    def test_pubdate_is_rfc822(self):
        auction = _make_auction(start_date=datetime.date(2027, 4, 15))
        result = auctions_to_rss([auction])
        root = ET.fromstring(result)
        pubdate = root.find("channel/item/pubDate").text
        # RFC 822: "Tue, 15 Apr 2027 00:00:00 GMT"
        assert "15 Apr 2027" in pubdate
        assert "GMT" in pubdate

    def test_multiple_auctions(self):
        a1 = _make_auction(state="FL")
        a2 = _make_auction(state="TX", county="Harris")
        result = auctions_to_rss([a1, a2])
        root = ET.fromstring(result)
        items = root.findall("channel/item")
        assert len(items) == 2

    def test_channel_has_last_build_date(self):
        result = auctions_to_rss([])
        root = ET.fromstring(result)
        lbd = root.find("channel/lastBuildDate")
        assert lbd is not None
        assert "GMT" in lbd.text

    def test_description_html_escapes_special_chars(self):
        auction = _make_auction(county="O'Brien & Sons")
        result = auctions_to_rss([auction])
        # Should be valid XML (ET.fromstring would fail if not escaped)
        root = ET.fromstring(result)
        item = root.find("channel/item")
        assert item is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_rss_export.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement RSS exporter**

Create `src/tdc_auction_calendar/exporters/rss.py`:

```python
"""RSS exporter — converts Auction models to RSS 2.0 XML string."""

from __future__ import annotations

import datetime
import html
import xml.etree.ElementTree as ET
from email.utils import format_datetime

from tdc_auction_calendar.models.auction import Auction


def _build_description(auction: Auction) -> str:
    """Build HTML description from auction fields."""
    parts: list[str] = []
    if auction.registration_deadline is not None:
        parts.append(f"<b>Registration deadline:</b> {auction.registration_deadline}")
    if auction.deposit_amount is not None:
        parts.append(f"<b>Deposit:</b> ${auction.deposit_amount:,.2f}")
    if auction.vendor is not None:
        parts.append(f"<b>Vendor:</b> {html.escape(auction.vendor)}")
    if auction.property_count is not None:
        parts.append(f"<b>Properties:</b> {auction.property_count}")
    if auction.source_url is not None:
        url = html.escape(auction.source_url)
        parts.append(f'<a href="{url}">Source</a>')
    return "<br>".join(parts) if parts else "No additional details."


def _date_to_rfc822(d: datetime.date) -> str:
    """Convert a date to RFC 822 format string."""
    dt = datetime.datetime.combine(d, datetime.time.min, tzinfo=datetime.timezone.utc)
    return format_datetime(dt, usegmt=True)


def auctions_to_rss(auctions: list[Auction], title: str = "Tax Auction Calendar") -> str:
    """Convert a list of Auction models to an RSS 2.0 XML string."""
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "description").text = (
        "Tax deed auction dates aggregated from county and state sources"
    )
    ET.SubElement(channel, "link").text = "https://github.com/mretrop/tdc-auction-calendar"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(
        datetime.datetime.now(datetime.timezone.utc), usegmt=True
    )

    for auction in auctions:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = (
            f"{auction.county} {auction.state} Tax {auction.sale_type.title()} Sale"
            f" — {auction.start_date}"
        )
        ET.SubElement(item, "description").text = _build_description(auction)
        ET.SubElement(item, "pubDate").text = _date_to_rfc822(auction.start_date)
        guid = ET.SubElement(item, "guid", isPermaLink="false")
        guid.text = f"{auction.state}-{auction.county}-{auction.start_date}-{auction.sale_type}"
        if auction.source_url:
            ET.SubElement(item, "link").text = auction.source_url

    return ET.tostring(rss, encoding="unicode", xml_declaration=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rss_export.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/exporters/rss.py tests/test_rss_export.py
git commit -m "feat: RSS 2.0 exporter (issue #20)"
```

---

## Chunk 2: CLI Wiring

### Task 2: Wire RSS command into CLI with `--days` flag

**Files:**
- Modify: `src/tdc_auction_calendar/cli.py:185-189`

- [ ] **Step 1: Replace RSS stub in `cli.py`**

Replace the `export_rss` function (lines 185-189) with:

```python
@export_app.command("rss")
def export_rss(
    state: list[str] | None = typer.Option(None, "--state", help="Filter by state code (repeatable)"),
    sale_type: SaleType | None = typer.Option(None, "--sale-type", help="Filter by sale type"),
    from_date: str | None = typer.Option(None, "--from-date", help="Start date (YYYY-MM-DD)"),
    to_date: str | None = typer.Option(None, "--to-date", help="End date (YYYY-MM-DD)"),
    days: int | None = typer.Option(None, "--days", help="Shortcut: auctions from last N days (overrides --from-date)"),
    upcoming_only: bool = typer.Option(False, "--upcoming-only", help="Only include upcoming auctions"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
) -> None:
    """Export auctions to RSS feed."""
    from tdc_auction_calendar.exporters.rss import auctions_to_rss

    if days is not None:
        from_date = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()

    from_parsed, to_parsed = _parse_dates(from_date, to_date)

    # Build feed title based on state filter
    if state and len(state) == 1:
        title = f"Tax Auction Calendar — {state[0].upper()}"
    else:
        title = "Tax Auction Calendar"

    auctions = _query_export_auctions(state, sale_type, from_parsed, to_parsed, upcoming_only)
    _write_output(auctions_to_rss(auctions, title=title), output)
    typer.echo(f"Exported {len(auctions)} auction(s).", err=True)
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/tdc_auction_calendar/cli.py
git commit -m "feat: wire RSS export command into CLI with --days flag (issue #20)"
```
