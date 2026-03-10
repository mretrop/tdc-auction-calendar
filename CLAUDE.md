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
```

## Architecture

- **Package**: `src/tdc_auction_calendar/` (src layout, managed by uv)
- **models/**: Pydantic/SQLAlchemy models (Auction, StateRules, CountyInfo)
- **collectors/**: Scraping modules that gather auction dates from various sources
- **exporters/**: Output formatters (iCal, JSON, CSV, RSS)
- **db/**: Database and Alembic migration support
- **cli.py**: Typer CLI entry point
- **log_config.py**: structlog configured for JSON output

## Key Dependencies

- **SQLAlchemy + Alembic** for DB / migrations
- **Pydantic** for data validation
- **Typer** for CLI
- **crawl4ai** for web scraping
- **anthropic** for Claude API fallback parsing
- **structlog** for structured JSON logging
- **supabase** for cloud sync
