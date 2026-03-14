# Documentation: README + CONTRIBUTING.md — Design Spec

**Issue:** #26
**Date:** 2026-03-14

## Overview

Two documentation files targeting two audiences: README.md for users who want to run the tool, CONTRIBUTING.md for developers who want to add collectors or maintain the project. The primary acceptance criterion is that a new contributor can go from `git clone` to their first `collect` run in under 10 minutes.

## Files

| File | Audience | Purpose |
|------|----------|---------|
| `README.md` | Users + contributors | What the tool does, how to install and use it |
| `CONTRIBUTING.md` | Contributors | How to add collectors, county URLs, test fixtures |

## README.md Structure

### 1. Header + Overview
One-paragraph description: what the tool does, what data sources it covers, what outputs it produces (iCal, JSON, CSV, RSS). Mention the confidence-tier system briefly.

### 2. Quick Start
Prerequisites: `uv` (link to installation instructions).

Step-by-step from clone to first output:
```
git clone → uv sync → uv run tdc-auction-calendar collect --collectors statutory → uv run tdc-auction-calendar export ical -o auctions.ics
```
The `statutory` collector requires no API keys (reads seed data), so this works with zero configuration. The database is created automatically on first `collect` run (no manual migration needed). Mention that other collectors need env vars (link to Configuration section).

### 3. CLI Reference
Table-based reference for all commands and subcommands:

**Top-level commands:** `collect`, `list`, `status`, `states`, `counties`
**Export subcommands:** `export ical`, `export csv`, `export json`, `export rss`
**Sync subcommands:** `sync supabase`
**Global options:** `--verbose/-v`, `--db-path`

Each command gets a one-line description and its key options. Not a full man page — just enough to know what's available. Point to `--help` for full details.

### 4. Configuration (Environment Variables)

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `DATABASE_URL` | No | `sqlite:///data/auction_calendar.db` | Database connection |
| `CLOUDFLARE_ACCOUNT_ID` | For scraping | — | Cloudflare Browser Rendering |
| `CLOUDFLARE_API_TOKEN` | For scraping | — | Cloudflare Browser Rendering |
| `ANTHROPIC_API_KEY` | For fallback extraction | — | Claude API (LLM extraction, only used when Crawl4AI is fetcher) |
| `SUPABASE_URL` | For sync | — | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | For sync | — | Supabase write access |
| `SCRAPE_CACHE_DIR` | No | `data/cache` | Scrape response cache directory |

### 5. Architecture

**Collector Tiers** — Mermaid diagram showing the four tiers and their data flow:

```
Sources (web/seed) → Collectors (4 tiers) → SQLite → Exporters (iCal/CSV/JSON/RSS)
                                                    → Supabase sync
```

Table of tiers:

| Tier | Schedule | Collectors | Data Source |
|------|----------|------------|-------------|
| Statutory | Weekly | 1 (seed-based) | JSON seed files |
| State Agencies | Daily | 4 | State government websites |
| Public Notices | Twice daily | 7 | Public notice aggregators |
| County Websites | Daily | 1 | County tax sale pages |

**Scraping Stack** — Mermaid diagram showing the two-tier fetch+extract architecture:

```
Fetch: Cloudflare Browser Rendering (primary) → Crawl4AI (fallback)
Extract: Cloudflare JSON extraction (primary) → Claude API tool_use (fallback) → CSS selectors (lightweight)
```

### 6. Deployment
Brief section covering:
- GitHub Actions cron workflows (link to `.github/workflows/`)
- Required secrets to configure in GitHub
- How the ephemeral SQLite + Supabase sync pattern works

## CONTRIBUTING.md Structure

### 1. Development Setup
```
uv sync (includes dev deps) → uv run pytest (verify everything works)
```

### 2. Adding a New Collector (walkthrough)
Step-by-step with a concrete example using a state agency collector (e.g., Arkansas) as the reference. Cover:
1. Create a new file in the appropriate `collectors/` subdirectory
2. Subclass `BaseCollector`, implement `_fetch()` and `normalize()` methods (NOT `collect()` — that's already implemented in `BaseCollector`)
3. Define the `name` and `source_type` properties
4. Define a Pydantic extraction schema and extraction prompt string
5. Register in `orchestrator.py`'s `COLLECTORS` dict
6. Add to the appropriate GitHub Actions workflow
7. Write tests with recorded fixtures

### 3. Adding a County URL
How to add/update entries in `db/seed/counties.json` — the fields, what they mean, how to find the tax sale page URL.

### 4. Recording Test Fixtures
How to capture and use test fixtures for collector tests.

### 5. Known Limitations
Include at minimum:
- Crawl4AI fallback requires a local browser binary (Chromium)
- Rate limiting considerations for web scraping
- Seed data coverage (not all 50 states have tax sales)

## Design Decisions

- **Mermaid over ASCII**: GitHub renders Mermaid natively, easier to maintain than ASCII art
- **CLI reference as tables, not `--help` dumps**: Scannable, doesn't go stale as fast as copy-pasted output
- **Quick start uses `statutory` collector**: Zero config needed, works immediately after `uv sync`
- **CONTRIBUTING focuses on the most common task**: Adding a new collector is the primary contribution path
