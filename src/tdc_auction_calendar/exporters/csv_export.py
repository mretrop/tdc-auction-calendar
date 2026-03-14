"""CSV exporter — converts Auction models to CSV string."""

from __future__ import annotations

import csv
import io

from tdc_auction_calendar.models.auction import Auction

CSV_COLUMNS = (
    "state",
    "county",
    "sale_type",
    "start_date",
    "end_date",
    "registration_deadline",
    "deposit_amount",
    "interest_rate",
    "property_count",
    "vendor",
    "confidence_score",
    "source_url",
)


def auctions_to_csv(auctions: list[Auction]) -> str:
    """Convert a list of Auction models to a CSV string."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, restval="", extrasaction="ignore")
    writer.writeheader()
    for auction in auctions:
        writer.writerow(auction.model_dump(mode="json"))
    return buf.getvalue()
