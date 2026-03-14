"""JSON exporter — converts Auction models to JSON string."""

from __future__ import annotations

import json

from tdc_auction_calendar.models.auction import Auction


def auctions_to_json(auctions: list[Auction], compact: bool = False) -> str:
    """Convert a list of Auction models to a JSON string."""
    data = [auction.model_dump(mode="json") for auction in auctions]
    if compact:
        return json.dumps(data, separators=(",", ":"))
    return json.dumps(data, indent=2)
