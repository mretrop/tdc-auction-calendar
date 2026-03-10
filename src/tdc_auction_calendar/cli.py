"""CLI interface for TDC Auction Calendar."""

import logging

import typer

from tdc_auction_calendar.log_config import configure_logging

app = typer.Typer(
    name="tdc-auction-calendar",
    help="Tax deed auction calendar aggregator.",
)


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Tax deed auction calendar — collect, merge, and export auction dates."""
    configure_logging(level=logging.DEBUG if verbose else logging.INFO)


if __name__ == "__main__":
    app()
