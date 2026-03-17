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
  - `enums.py`: SaleType, AuctionStatus, SourceType, Priority, Vendor (all StrEnum)
  - `auction.py`: AuctionRow (ORM) + Auction (Pydantic) with dedup key `(state, county, start_date, sale_type)`
  - `jurisdiction.py`: StateRulesRow/CountyInfoRow (ORM) + StateRules/CountyInfo (Pydantic), also houses `Base` (DeclarativeBase)
- **collectors/**: Scraping modules that gather auction dates from various sources
- **exporters/**: Output formatters (iCal, JSON, CSV, RSS)
- **db/**: Database layer
  - `database.py`: Engine/session factory, reads `DATABASE_URL` env var (default: `sqlite:///data/auction_calendar.db`)
  - `seed_loader.py`: Idempotent JSON seed loader, reads from `db/seed/` directory
  - `seed/`: JSON seed files (states.json, counties.json, vendor_mapping.json)
- **cli.py**: Typer CLI entry point with `--verbose/-v` flag
- **log_config.py**: structlog configured for JSON output
- **alembic/**: Migration scripts, `env.py` uses `get_database_url()` from db/database.py

## Scraping & Extraction Strategy

Collectors use a two-tier fetch+extract architecture built on `ScrapeClient`:

- **Primary fetcher:** Cloudflare Browser Rendering `/crawl` endpoint (when `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN` are set)
- **Fallback fetcher:** Crawl4AI (local headless browser, stealth mode enabled by default)
- **Primary extraction:** Cloudflare's built-in JSON extraction via `jsonOptions` (prompt + `response_format` schema) — server-side, no separate API call
- **Fallback extraction:** `LLMExtraction` (Claude API tool_use) — used when Crawl4AI is the fetcher (no built-in extraction)
- **Lightweight extraction:** `CSSExtraction` — available for sources with stable, simple HTML structure

Most collectors define a Pydantic schema and extraction prompt. When Cloudflare is primary, extraction happens in a single round trip. When falling back to Crawl4AI, `LLMExtraction` handles extraction as a separate step. Some collectors with stable, structured sources use deterministic parsing instead of LLM extraction (e.g., `ArkansasCollector`, `MVBACollector` use regex; `RealAuctionCollector` uses BeautifulSoup CSS selectors on raw HTML). `Bid4AssetsCollector` bypasses `ScrapeClient` entirely — it uses plain `httpx` because Akamai blocks headless browsers but allows standard HTTP requests. `PublicSurplusCollector` also uses plain `httpx` + BeautifulSoup (no bot protection observed) with a two-pass architecture: listing pages for discovery + JS end-date extraction, then detail pages for start dates. `LinebargerCollector` uses plain `httpx` against the site's REST API (`/api/filter_bar/`) — the AngularJS SPA has a public JSON backend, so no browser rendering needed.

Crawl4AI supports three stealth levels via `StealthLevel` enum: `OFF` (plain browser), `STEALTH` (default — `playwright-stealth` + `magic` mode), `UNDETECTED` (opt-in — adds `UndetectedAdapter` for Akamai-level protection). Collectors targeting bot-protected sites use `create_scrape_client(stealth=StealthLevel.UNDETECTED)`. Note: `magic` mode can interfere with some sites (e.g., RealAuction redirects to splash page) — use `StealthLevel.OFF` when magic causes issues.

Key files: `collectors/scraping/client.py` (orchestrator), `collectors/scraping/fetchers/cloudflare.py`, `collectors/scraping/fetchers/crawl4ai.py`, `collectors/scraping/extraction.py`

## Key Dependencies

- **SQLAlchemy + Alembic** for DB / migrations
- **Pydantic** for data validation
- **Typer** for CLI
- **crawl4ai** for web scraping (fallback fetcher)
- **anthropic** for Claude API fallback parsing (LLMExtraction)
- **structlog** for structured JSON logging
- **supabase** for cloud sync
- **beautifulsoup4** for HTML parsing (RealAuction, Bid4Assets, PublicSurplus collectors)
- **httpx** for Cloudflare API calls and direct HTTP fetching (Bid4Assets, PublicSurplus, Linebarger)

## Conventions

- All models have both a Pydantic version (validation) and SQLAlchemy ORM version (DB mapping)
- ORM classes are suffixed with `Row` (e.g., `AuctionRow`), Pydantic classes are plain names (e.g., `Auction`)
- `Base` (DeclarativeBase) lives in `models/jurisdiction.py` and is re-exported from `models/__init__.py`
- Seed loader is idempotent — checks primary key existence before inserting
- `uv` is the package manager (not pip)
- Seed data tests should validate against both Pydantic models AND ORM models (since seed_loader uses the ORM layer)
- Use `SEED_DIR` from `db/seed_loader.py` when referencing seed files in tests (don't hardcode paths)
- Worktrees go in `.worktrees/` (already in .gitignore)

## Domain Notes

- Not all 50 states have tax sales — only include states with active lien/deed/hybrid auctions in seed data
- `redemption_period_months` is typically null for deed states, but some (e.g., TX) have statutory redemption periods — this is correct, not a bug
- `typical_months` uses `list[int]` (1-12), not month name strings — format for humans downstream

## Progress

Issues are tracked as GitHub issues organized by milestones (M1–M5). Check `gh issue list` for current status.
