# Typer CLI Interface Design (Issue #17)

## Overview

Implement the main CLI entry point in `src/tdc_auction_calendar/cli.py` (single flat file). Provides commands for collecting auctions, querying data, and checking system health. Export and sync commands are registered as stubs pending issues #18-20 and #22.

## Command Structure

```
tdc-auction-calendar
├── --verbose / -v            (global, existing)
├── --db-path PATH            (global, overrides DATABASE_URL)
├── collect                   [--collectors NAME...]
├── list                      [--state] [--sale-type] [--from-date] [--to-date] [--limit]
├── status                    (no args)
├── states                    (no args)
├── counties                  [--state]
├── export
│   ├── ical                  stub
│   ├── csv                   stub
│   ├── json                  stub
│   └── rss                   stub
└── sync
    └── supabase              stub
```

- `export` and `sync` are Typer sub-apps via `app.add_typer()`.
- Global `--db-path` is handled in `@app.callback()`, sets `DATABASE_URL` env var so `get_session()` picks it up. Env var mutation is intentional — the orchestrator internally calls DB functions that read `DATABASE_URL`, so passing the URL directly to a single session isn't sufficient.

## Command Behaviors

### `collect`

Async command. Calls `run_and_persist(session, collectors=filter_list)`. Prints a Rich summary table: collector name, records found, status (pass/fail). Ends with totals line (new/updated/skipped) and duration.

Options:
- `--collectors NAME` (repeatable): filter to specific collector names. Omit to run all registered collectors.

### `list`

Queries `AuctionRow` with optional filters. Defaults to upcoming auctions from today forward, limit 50.

Rich table columns: State, County, Date, Sale Type, Status, Source, Confidence (displayed as percentage, e.g., "85%").

Options:
- `--state`: filter by 2-letter state code
- `--sale-type`: filter by lien/deed/hybrid (Typer validates via SaleType enum)
- `--from-date` / `--to-date`: date range filter (YYYY-MM-DD)
- `--limit`: max rows (default 50)

### `status`

Two sections:
1. **DB stats**: total auctions, count by state, count by source type.
2. **Collector health**: Rich table from `get_collector_health()` showing collector name, last run, last success, records collected, and error (if any).

### `states`

Queries `StateRulesRow`. Rich table: State, Sale Type, Typical Months (formatted as month abbreviations), Redemption Period.

### `counties`

Queries `CountyInfoRow` with optional `--state` filter. Rich table: State, County, Vendor, Tax Sale Page URL (`tax_sale_page_url`), Priority.

### Stubs

`export ical`, `export csv`, `export json`, `export rss`, `sync supabase` — print "Not yet implemented. See issue #N." and `raise typer.Exit(1)`.

## Global Options

### `--db-path`

Added to `@app.callback()`. When provided, sets `DATABASE_URL` env var before any command runs. This way `get_session()` (which reads `DATABASE_URL`) picks it up transparently.

### `--verbose / -v`

Already exists. Configures structlog for DEBUG level.

## Error Handling

- **No DB file**: Commands that query DB detect missing database and print "Database not found. Run `tdc-auction-calendar collect` first." Exit code 1.
- **DB initialization**: `collect` auto-creates tables via `Base.metadata.create_all(engine)` if the DB is empty or new. No manual migration step needed for first run.
- **`collect` partial failure**: Orchestrator isolates per-collector failures. CLI prints summary with failed collectors marked. Exit 0 unless all collectors fail (exit 1).
- **Unknown collector names**: `ValueError` from orchestrator is caught and printed as a user-friendly error listing valid collector names. Exit code 1.
- **Empty results**: `list`, `states`, `counties` print "No {items} found." instead of empty table.
- **Invalid filters**: Typer handles enum validation for `--sale-type`. Bad dates get Typer's built-in error message. `--state` is passed through as a filter without validation (typos return empty results).

## Architecture Decisions

- **Single file**: All commands in `cli.py`. Commands are thin wrappers (~10-20 lines each) around orchestrator/DB calls. Split later if needed.
- **Rich tables**: Use Typer's built-in Rich integration (already a dependency) for table output.
- **Stubs for future work**: Export and sync commands registered now for complete `--help`, implemented in their respective issues.
- **Async**: `collect` is async (Typer >=0.12 handles async commands natively — no manual `asyncio.run()` wrapping needed). Query commands are sync since SQLAlchemy queries are synchronous.

## File Changes

- **Modified**: `src/tdc_auction_calendar/cli.py` — add all commands, sub-apps, global --db-path option
- **No new files**: everything in the single existing CLI file

## Acceptance Criteria (from issue)

- [ ] `uv run python -m tdc_auction_calendar --help` shows all commands
- [ ] `collect` runs statutory collector and reports counts
- [ ] `list` shows tabular output with upcoming auctions
- [ ] `status` shows DB stats and collector health
