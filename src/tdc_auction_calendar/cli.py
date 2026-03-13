"""CLI interface for TDC Auction Calendar."""

import asyncio
import calendar
import datetime
import logging
import os

import typer
from rich.console import Console
from sqlalchemy import func

from tdc_auction_calendar.collectors.orchestrator import COLLECTORS, run_and_persist
from tdc_auction_calendar.db.database import get_engine, get_session
from tdc_auction_calendar.db.upsert import get_collector_health
from tdc_auction_calendar.log_config import configure_logging
from tdc_auction_calendar.models.auction import AuctionRow
from tdc_auction_calendar.models.enums import SaleType
from tdc_auction_calendar.models.jurisdiction import Base, CountyInfoRow, StateRulesRow

console = Console(width=200)

app = typer.Typer(
    name="tdc-auction-calendar",
    help="Tax deed auction calendar aggregator.",
)

export_app = typer.Typer(help="Export auctions to various formats.")
app.add_typer(export_app, name="export")

sync_app = typer.Typer(help="Sync auction data to external services.")
app.add_typer(sync_app, name="sync")


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
    db_path: str | None = typer.Option(None, "--db-path", help="Override DATABASE_URL"),
) -> None:
    """Tax deed auction calendar — collect, merge, and export auction dates."""
    configure_logging(level=logging.DEBUG if verbose else logging.INFO)
    if db_path is not None:
        os.environ["DATABASE_URL"] = db_path


def _ensure_tables() -> None:
    """Create tables if DB is empty (first run)."""
    try:
        engine = get_engine()
        Base.metadata.create_all(engine)
    except Exception as exc:
        console.print(f"[red]Failed to initialize database:[/red] {exc}")
        console.print("Check your --db-path or DATABASE_URL setting.")
        raise typer.Exit(1)


# --- Export stubs ---


@export_app.command("ical")
def export_ical(
    state: list[str] | None = typer.Option(None, "--state", help="Filter by state code (repeatable)"),
    sale_type: SaleType | None = typer.Option(None, "--sale-type", help="Filter by sale type"),
    from_date: str | None = typer.Option(None, "--from-date", help="Start date (YYYY-MM-DD)"),
    to_date: str | None = typer.Option(None, "--to-date", help="End date (YYYY-MM-DD)"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
) -> None:
    """Export auctions to iCalendar (.ics) format."""
    import sys

    from tdc_auction_calendar.exporters.ical import auctions_to_ical, query_auctions

    if not _check_db_exists():
        console.print("[red]Database not found.[/red] Run `tdc-auction-calendar collect` first.")
        raise typer.Exit(1)

    # Parse dates
    from_date_parsed: datetime.date | None = None
    to_date_parsed: datetime.date | None = None
    try:
        if from_date:
            from_date_parsed = datetime.date.fromisoformat(from_date)
        if to_date:
            to_date_parsed = datetime.date.fromisoformat(to_date)
    except ValueError:
        console.print(f"[red]Invalid date format.[/red] Use YYYY-MM-DD (e.g., {datetime.date.today().isoformat()}).")
        raise typer.Exit(1)

    session = get_session()
    try:
        auctions = query_auctions(
            session,
            states=state,
            sale_type=sale_type,
            from_date=from_date_parsed,
            to_date=to_date_parsed,
        )
    finally:
        session.close()

    ical_bytes = auctions_to_ical(auctions)

    if output:
        with open(output, "wb") as f:
            f.write(ical_bytes)
    else:
        sys.stdout.buffer.write(ical_bytes)

    typer.echo(f"Exported {len(auctions)} auction(s).", err=True)


@export_app.command("csv")
def export_csv() -> None:
    """Export auctions to CSV format."""
    console.print("Not yet implemented. See issue #19.")
    raise typer.Exit(1)


@export_app.command("json")
def export_json() -> None:
    """Export auctions to JSON format."""
    console.print("Not yet implemented. See issue #19.")
    raise typer.Exit(1)


@export_app.command("rss")
def export_rss() -> None:
    """Export auctions to RSS feed."""
    console.print("Not yet implemented. See issue #20.")
    raise typer.Exit(1)


# --- Sync stubs ---


@sync_app.command("supabase")
def sync_supabase() -> None:
    """Upsert auction data to Supabase."""
    console.print("Not yet implemented. See issue #22.")
    raise typer.Exit(1)


# --- Commands ---


@app.command()
def collect(
    collectors: list[str] | None = typer.Option(None, "--collectors", help="Collector names to run (repeatable). Omit for all."),
) -> None:
    """Run collectors and persist auction data to the database."""
    from rich.table import Table

    _ensure_tables()
    session = get_session()
    try:
        report = asyncio.run(run_and_persist(session, collectors=collectors))
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        console.print(f"Valid collectors: {', '.join(sorted(COLLECTORS.keys()))}")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]Collection failed:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        session.close()

    # Summary table
    table = Table(title="Collector Results")
    table.add_column("Collector", style="cyan")
    table.add_column("Records", justify="right")
    table.add_column("Status")

    for name in report.collectors_succeeded:
        count = report.per_collector_counts.get(name, 0)
        table.add_row(name, str(count), "[green]OK[/green]")

    for err in report.collectors_failed:
        table.add_row(err.collector_name, "0", f"[red]FAIL[/red] {err.error_type}")

    console.print(table)
    console.print(
        f"\nTotal: {report.total_records} records "
        f"({report.new_records} new, {report.updated_records} updated, "
        f"{report.skipped_records} skipped) in {report.duration_seconds:.1f}s"
    )

    if not report.collectors_succeeded:
        raise typer.Exit(1)


def _check_db_exists() -> bool:
    """Check if the database file exists (for SQLite)."""
    from tdc_auction_calendar.db.database import get_database_url
    url = get_database_url()
    if url.startswith("sqlite:///"):
        db_path = url.removeprefix("sqlite:///")
        if ":memory:" in db_path:
            return True
        return os.path.exists(db_path)
    return True  # non-SQLite assumed to exist


@app.command("list")
def list_auctions(
    state: str | None = typer.Option(None, "--state", help="Filter by state code (e.g., FL)"),
    sale_type: SaleType | None = typer.Option(None, "--sale-type", help="Filter by sale type"),
    from_date: str | None = typer.Option(None, "--from-date", help="Start date (YYYY-MM-DD)"),
    to_date: str | None = typer.Option(None, "--to-date", help="End date (YYYY-MM-DD)"),
    limit: int = typer.Option(50, "--limit", help="Max rows to display"),
) -> None:
    """List upcoming auctions."""
    from rich.table import Table

    if not _check_db_exists():
        console.print("[red]Database not found.[/red] Run `tdc-auction-calendar collect` first.")
        raise typer.Exit(1)

    # Parse date strings
    from_date_parsed: datetime.date | None = None
    to_date_parsed: datetime.date | None = None
    try:
        if from_date:
            from_date_parsed = datetime.date.fromisoformat(from_date)
        if to_date:
            to_date_parsed = datetime.date.fromisoformat(to_date)
    except ValueError:
        console.print(f"[red]Invalid date format.[/red] Use YYYY-MM-DD (e.g., {datetime.date.today().isoformat()}).")
        raise typer.Exit(1)

    session = get_session()
    try:
        query = session.query(AuctionRow)

        if state:
            query = query.filter(AuctionRow.state == state.upper())
        if sale_type:
            query = query.filter(AuctionRow.sale_type == sale_type.value)
        if from_date_parsed:
            query = query.filter(AuctionRow.start_date >= from_date_parsed)
        else:
            query = query.filter(AuctionRow.start_date >= datetime.date.today())
        if to_date_parsed:
            query = query.filter(AuctionRow.start_date <= to_date_parsed)

        rows = query.order_by(AuctionRow.start_date).limit(limit).all()
    except Exception as exc:
        console.print(f"[red]Database query failed:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        session.close()

    if not rows:
        console.print("No auctions found.")
        return

    table = Table(title="Upcoming Auctions")
    table.add_column("State", style="cyan")
    table.add_column("County")
    table.add_column("Date")
    table.add_column("Sale Type")
    table.add_column("Status")
    table.add_column("Source")
    table.add_column("Confidence", justify="right")

    for row in rows:
        table.add_row(
            row.state,
            row.county,
            str(row.start_date),
            row.sale_type,
            row.status,
            row.source_type,
            f"{row.confidence_score:.0%}",
        )

    console.print(table)


@app.command()
def status() -> None:
    """Show database stats and collector health."""
    from rich.table import Table

    if not _check_db_exists():
        console.print("[red]Database not found.[/red] Run `tdc-auction-calendar collect` first.")
        raise typer.Exit(1)

    session = get_session()
    try:
        # DB stats
        total = session.query(func.count(AuctionRow.id)).scalar() or 0
        console.print(f"\n[bold]Database Stats[/bold]")
        console.print(f"Total auctions: {total}")

        if total > 0:
            by_state = (
                session.query(AuctionRow.state, func.count(AuctionRow.id))
                .group_by(AuctionRow.state)
                .order_by(func.count(AuctionRow.id).desc())
                .all()
            )
            console.print("\nBy state:")
            for state, count in by_state:
                console.print(f"  {state}: {count}")

            by_source = (
                session.query(AuctionRow.source_type, func.count(AuctionRow.id))
                .group_by(AuctionRow.source_type)
                .order_by(func.count(AuctionRow.id).desc())
                .all()
            )
            console.print("\nBy source:")
            for source, count in by_source:
                console.print(f"  {source}: {count}")

        # Collector health
        health = get_collector_health(session)
    except Exception as exc:
        console.print(f"[red]Database query failed:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        session.close()

    if health:
        console.print(f"\n[bold]Collector Health[/bold]")
        table = Table()
        table.add_column("Collector", style="cyan")
        table.add_column("Last Run")
        table.add_column("Last Success")
        table.add_column("Records", justify="right")
        table.add_column("Error")

        for h in health:
            table.add_row(
                h.collector_name,
                str(h.last_run.strftime("%Y-%m-%d %H:%M")) if h.last_run else "-",
                str(h.last_success.strftime("%Y-%m-%d %H:%M")) if h.last_success else "-",
                str(h.records_collected),
                h.error_message or "",
            )
        console.print(table)
    else:
        console.print("\nNo collector health data. Run `collect` first.")


@app.command()
def states() -> None:
    """List all states with sale type and typical months."""
    from rich.table import Table

    if not _check_db_exists():
        console.print("[red]Database not found.[/red] Run `tdc-auction-calendar collect` first.")
        raise typer.Exit(1)

    session = get_session()
    try:
        rows = session.query(StateRulesRow).order_by(StateRulesRow.state).all()
    except Exception as exc:
        console.print(f"[red]Database query failed:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        session.close()

    if not rows:
        console.print("No states found.")
        return

    table = Table(title="State Rules")
    table.add_column("State", style="cyan")
    table.add_column("Sale Type")
    table.add_column("Typical Months")
    table.add_column("Redemption (months)", justify="right")

    for row in rows:
        months = ""
        if row.typical_months:
            months = ", ".join(calendar.month_abbr[m] for m in row.typical_months)
        redemption = str(row.redemption_period_months) if row.redemption_period_months is not None else "-"
        table.add_row(row.state, row.sale_type, months, redemption)

    console.print(table)


@app.command()
def counties(
    state: str | None = typer.Option(None, "--state", help="Filter by state code"),
) -> None:
    """List counties with vendor and tax sale page info."""
    from rich.table import Table

    if not _check_db_exists():
        console.print("[red]Database not found.[/red] Run `tdc-auction-calendar collect` first.")
        raise typer.Exit(1)

    session = get_session()
    try:
        query = session.query(CountyInfoRow)
        if state:
            query = query.filter(CountyInfoRow.state == state.upper())
        rows = query.order_by(CountyInfoRow.state, CountyInfoRow.county_name).all()
    except Exception as exc:
        console.print(f"[red]Database query failed:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        session.close()

    if not rows:
        console.print("No counties found.")
        return

    table = Table(title="Counties")
    table.add_column("State", style="cyan")
    table.add_column("County")
    table.add_column("Vendor")
    table.add_column("Tax Sale Page")
    table.add_column("Priority")

    for row in rows:
        table.add_row(
            row.state,
            row.county_name,
            row.known_auction_vendor or "-",
            row.tax_sale_page_url or "-",
            row.priority,
        )

    console.print(table)


if __name__ == "__main__":
    app()
