# GitHub Actions Cron Workflow — Design Spec

**Issue:** #23
**Date:** 2026-03-13

## Overview

Four separate GitHub Actions workflow files that automate auction data collection and Supabase sync on scheduled intervals. Each workflow handles one collector tier at its own frequency, matching data volatility. The SQLite database is ephemeral per run — Supabase is the source of truth.

**Why four files instead of one?** GitHub Actions triggers _all_ jobs in a workflow for each `schedule` entry. With four cron entries in one workflow, the most frequent cron (every 12h for public notices) would trigger all four jobs every 12 hours. Separate files are simpler — each workflow runs exactly when its cron fires.

## Files

| File | Purpose |
|------|---------|
| `.github/workflows/collect-statutory.yml` | Weekly statutory collection |
| `.github/workflows/collect-state-agencies.yml` | Daily state agency collection |
| `.github/workflows/collect-public-notices.yml` | Twice-daily public notice collection |
| `.github/workflows/collect-county-websites.yml` | Daily county website collection |

## Workflows & Schedules

| Workflow | Cron (UTC) | Collectors | Concurrency Group |
|----------|-----------|------------|-------------------|
| `collect-statutory` | `0 3 * * 0` (Sunday 3am) | `statutory` | `collect-statutory` |
| `collect-state-agencies` | `0 4 * * *` (daily 4am) | `arkansas_state_agency`, `california_state_agency`, `colorado_state_agency`, `iowa_state_agency` | `collect-state-agencies` |
| `collect-public-notices` | `0 6,18 * * *` (6am, 6pm) | `florida_public_notice`, `minnesota_public_notice`, `new_jersey_public_notice`, `north_carolina_public_notice`, `pennsylvania_public_notice`, `south_carolina_public_notice`, `utah_public_notice` | `collect-public-notices` |
| `collect-county-websites` | `0 5 * * *` (daily 5am) | `county_website` | `collect-county-websites` |

## Runner & Python

- `runs-on: ubuntu-latest`
- Python 3.13 (from `pyproject.toml`), installed via `setup-uv` with `python-version-file`
- `permissions: contents: read`

## Workflow Steps (per workflow)

1. `actions/checkout@v4`
2. `astral-sh/setup-uv@v4` — install uv + Python 3.13
3. `uv sync --no-dev` — install production dependencies only
4. `uv run tdc-auction-calendar collect --collectors <name1> --collectors <name2> ...` — run tier-specific collectors (repeated `--collectors` flag per collector name, not comma-separated)
5. `uv run tdc-auction-calendar sync supabase` — push collected data to Supabase (skipped if step 4 fails via default GitHub Actions behavior)

**Note:** Alembic migrations are not needed. The `collect` command calls `_ensure_tables()` which uses `Base.metadata.create_all()` to create the schema directly — appropriate for ephemeral databases.

## Manual Trigger

Each workflow supports `workflow_dispatch` for manual triggering. Since each tier is a separate workflow file, no input dropdown or `if:` conditions are needed — just dispatch the specific workflow you want to run.

## Secrets

| Secret | Required | Purpose |
|--------|----------|---------|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Supabase write access |
| `CLOUDFLARE_ACCOUNT_ID` | Yes | Browser Rendering fetcher |
| `CLOUDFLARE_API_TOKEN` | Yes | Browser Rendering fetcher |
| `ANTHROPIC_API_KEY` | No | LLM fallback extraction |

## Error Handling

- **Concurrency**: `cancel-in-progress: false` — queues new runs instead of canceling active ones, avoiding mid-scrape kills.
- **Partial failure**: `collect` exits 0 if at least one collector succeeds. `sync supabase` runs after, pushing whatever was collected. If all collectors fail, `collect` exits 1 and sync is skipped.
- **Timeout**: `timeout-minutes: 30` per job to prevent hung scrapes from consuming Actions minutes.
- **Notifications**: GitHub Actions default email notifications on failure.

## Database

Ephemeral per run. Each job starts with a fresh SQLite database (default path `data/auction_calendar.db`), collects into it, syncs to Supabase, and discards it. No DB commit to the repo.

## CI Dependency Notes

`crawl4ai` is a project dependency and will be installed by `uv sync`. It should install cleanly on `ubuntu-latest` without Chromium since the workflow never invokes it (Cloudflare is the only fetcher in CI). If `crawl4ai` install proves problematic, it can be moved to an optional dependency group excluded via `uv sync --no-group scraping-fallback`.

If Cloudflare secrets are missing, the `statutory` job still works (reads JSON seed files, no scraping). All other jobs will fail because their collectors depend on the Cloudflare fetcher.

## Out of Scope

- Crawl4AI / headless browser in CI (Cloudflare handles fetching)
- Custom Slack/Discord notifications (GitHub default email is sufficient)
- Scheduled sync without collection (sync always follows collect)
- DB artifact upload or commit
- Retry strategy (GitHub Actions can be re-run manually; transient failures are picked up on next scheduled run)
