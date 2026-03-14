# Supabase Sync Command — Design Spec

**Issue:** #22
**Date:** 2026-03-13
**Related:** mretrop/tax-deed-club#103 (Supabase table migration)

## Overview

CLI command to upsert auction data from local SQLite to a Supabase `auctions` table. The local database is the source of truth — synced records always overwrite what exists in Supabase on the dedup key.

## Module

`src/tdc_auction_calendar/sync/supabase_sync.py`

### `sync_to_supabase(session, supabase_url, service_role_key, **filters) -> SyncResult`

1. Query local auctions using `query_auctions()` from `exporters/filters.py` with the provided filters (states, sale_type, from_date, to_date, upcoming_only).
2. Create a Supabase client via `supabase.create_client(url, key)`.
3. Convert each `Auction` to a dict via `model_dump(mode="json")`, dropping `id` (Supabase generates its own PK).
4. Upsert in batches of 100 rows using `.upsert()` with `on_conflict="state,county,start_date,sale_type"`.
5. Return a result object with counts: synced, failed.

### `SyncResult`

Simple dataclass or NamedTuple with `synced: int` and `failed: int` fields.

## CLI Integration

Replace the stub in `cli.py`:

```
tdc-auction-calendar sync supabase [--state FL] [--sale-type deed] [--from-date ...] [--to-date ...] [--upcoming-only]
```

Same filter flags as the export commands. Reads `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from environment. Prints summary to console.

## Data Mapping

`Auction.model_dump(mode="json")` produces:
- Dates as ISO 8601 strings (compatible with Postgres `date`)
- Decimals as floats (compatible with Postgres `numeric`)
- Enums as strings (compatible with Postgres `text`)

The `id` field is dropped before upsert since Supabase generates its own PK.

## Conflict Resolution

Local SQLite is the source of truth. Upserts always overwrite on the dedup key `(state, county, start_date, sale_type)`. No timestamp or confidence comparison needed.

## Error Handling

- **Missing env vars:** Exit with a clear error message before attempting any sync.
- **Supabase client errors:** Catch per-batch errors, log them, continue with remaining batches. Report failed count in the summary.
- **Empty query result:** Log info, exit cleanly (not an error).

## Environment Variables

- `SUPABASE_URL` — project URL (e.g., `https://xyz.supabase.co`)
- `SUPABASE_SERVICE_ROLE_KEY` — service role key (bypasses RLS)

Update `.env.example` to replace `SUPABASE_KEY` with `SUPABASE_SERVICE_ROLE_KEY`.

## Testing

All tests mock the Supabase client. No real HTTP calls.

- Successful upsert with correct payload shape
- Filtered subsets pass through to query
- Missing env vars produce clear error
- Batch chunking for large datasets
- Client error handling (partial failure)
- Empty auction list handled gracefully

## Out of Scope

- Supabase table creation / migration (tracked in mretrop/tax-deed-club#103)
- Bidirectional sync (Supabase → SQLite)
- Scheduled / automated sync (future issue)
