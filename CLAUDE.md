# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

TDC Auction Calendar — a Python tool that collects, merges, and exports tax deed auction dates from county/state sources into iCal, JSON, CSV, and RSS feeds.

## Build & Development Commands

```bash
uv sync                              # Install all dependencies
uv run pytest                        # Run all tests
uv run pytest tests/test_foo.py      # Run a single test file
uv run pytest -k "test_name"         # Run a specific test
uv run python -m tdc_auction_calendar --help  # CLI help
uv run tdc-auction-calendar --help            # CLI help (via entry point)
uv run alembic upgrade head          # Run DB migrations
uv run alembic revision --autogenerate -m "description"  # Generate new migration
```

## Architecture

- **Package**: `src/tdc_auction_calendar/` (src layout, managed by uv)
- **models/**: Pydantic + SQLAlchemy dual models (validation and ORM)
  - `enums.py`: SaleType, AuctionStatus, SourceType, Priority (all StrEnum)
  - `auction.py`: AuctionRow (ORM) + Auction (Pydantic) with dedup key `(state, county, start_date, sale_type)`
  - `jurisdiction.py`: StateRulesRow/CountyInfoRow (ORM) + StateRules/CountyInfo (Pydantic), also houses `Base` (DeclarativeBase)
- **collectors/**: Scraping modules that gather auction dates from various sources
- **exporters/**: Output formatters (iCal, JSON, CSV, RSS)
- **db/**: Database layer
  - `database.py`: Engine/session factory, reads `DATABASE_URL` env var (default: `sqlite:///data/auction_calendar.db`)
  - `seed_loader.py`: Idempotent JSON seed loader, reads from `db/seed/` directory
  - `seed/`: JSON seed files (states.json, counties.json)
- **cli.py**: Typer CLI entry point with `--verbose/-v` flag
- **log_config.py**: structlog configured for JSON output
- **alembic/**: Migration scripts, `env.py` uses `get_database_url()` from db/database.py

## Key Dependencies

- **SQLAlchemy + Alembic** for DB / migrations
- **Pydantic** for data validation
- **Typer** for CLI
- **crawl4ai** for web scraping
- **anthropic** for Claude API fallback parsing
- **structlog** for structured JSON logging
- **supabase** for cloud sync

## Conventions

- All models have both a Pydantic version (validation) and SQLAlchemy ORM version (DB mapping)
- ORM classes are suffixed with `Row` (e.g., `AuctionRow`), Pydantic classes are plain names (e.g., `Auction`)
- `Base` (DeclarativeBase) lives in `models/jurisdiction.py` and is re-exported from `models/__init__.py`
- Seed loader is idempotent — checks primary key existence before inserting
- `uv` is the package manager (not pip)

## Progress

Issues are tracked as GitHub issues organized by milestones (M1–M4). Issues #1–3 are complete. Next up: issue #4 (Seed data: states.json for all 50 states).
