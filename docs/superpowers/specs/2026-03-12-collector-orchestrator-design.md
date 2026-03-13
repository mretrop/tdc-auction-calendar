# Collector Orchestrator Design Spec (Issue #15)

## Overview

The collector orchestrator runs all enabled collectors sequentially, handles failures independently, deduplicates results across collectors, and upserts to the database. It also tracks per-collector health for CLI status reporting.

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Collector registration | Explicit registry dict | Predictable, matches existing `__init__.py` exports |
| Upsert strategy | Higher confidence wins | Prevents lower-tier sources from overwriting better data |
| Health persistence | DB table (`collector_health`) | Survives across runs, queryable by CLI without a run active |
| Concurrency | Sequential | Simpler, rate limiting already per-domain, easy to add concurrency later |
| Cross-collector dedup | In-memory before DB | One pass, predictable, scale is hundreds not millions |
| DB coupling | Orchestrator returns data, separate upsert layer persists | Testable without DB, clean separation of concerns |

## New Files

| File | Purpose |
|------|---------|
| `src/tdc_auction_calendar/collectors/orchestrator.py` | Collector registry, sequential execution, cross-dedup, RunReport |
| `src/tdc_auction_calendar/db/upsert.py` | Auction upsert (confidence-gated), health persistence, health query |
| `src/tdc_auction_calendar/models/health.py` | `CollectorHealthRow` (ORM) + `CollectorHealth` (Pydantic) |
| `alembic/versions/xxx_add_collector_health.py` | Migration for `collector_health` table |

## Data Models

### CollectorHealthRow (ORM) / CollectorHealth (Pydantic)

Located in `models/health.py`. Follows the project convention: `Row` suffix for ORM, plain name for Pydantic.

| Column | Type | Notes |
|--------|------|-------|
| `collector_name` | `str` | Primary key |
| `last_run` | `datetime` | UTC, updated on every run attempt |
| `last_success` | `datetime \| None` | UTC, updated only on success |
| `records_collected` | `int` | Count from last successful run |
| `error_message` | `str \| None` | Set on failure, cleared on success |

### RunReport (Pydantic, not persisted)

Returned by `run_all` and enriched by `run_and_persist`.

| Field | Type | Notes |
|-------|------|-------|
| `total_records` | `int` | After cross-collector dedup |
| `new_records` | `int` | Inserted to DB |
| `updated_records` | `int` | Overwritten (higher confidence) |
| `skipped_records` | `int` | Existing had equal/higher confidence |
| `collectors_succeeded` | `list[str]` | Names that completed |
| `collectors_failed` | `list[CollectorError]` | Name + error for each failure |
| `duration_seconds` | `float` | Wall-clock time for entire run |

### CollectorError (Pydantic)

| Field | Type |
|-------|------|
| `name` | `str` |
| `error` | `str` |

### UpsertResult (Pydantic)

| Field | Type |
|-------|------|
| `new` | `int` |
| `updated` | `int` |
| `skipped` | `int` |

## Orchestrator (`orchestrator.py`)

### Registry

Module-level dict mapping name to class:

```python
COLLECTORS: dict[str, type[BaseCollector]] = {
    "FloridaCollector": FloridaCollector,
    "ArkansasCollector": ArkansasCollector,
    # ... all 12 collectors
}
```

### `run_all(collectors: list[str] | None = None) -> tuple[list[Auction], RunReport]`

1. **Resolve collector list.** If `collectors` is provided, filter `COLLECTORS` to those names. Raise `ValueError` for unknown names. Otherwise use all.
2. **Execute sequentially.** For each collector:
   - Instantiate and call `await collector.collect()`
   - On success: append results to combined list, record as succeeded
   - On `Exception`: log via structlog, record as failed with error message, continue
3. **Cross-collector dedup.** Merge all results by dedup key `(state, county, start_date, sale_type)`, keeping highest `confidence_score`.
4. **Build RunReport.** Populate `total_records` (post-dedup count), `collectors_succeeded`, `collectors_failed`, `duration_seconds`. Leave DB-related counts (`new_records`, `updated_records`, `skipped_records`) at 0 — filled by `run_and_persist`.
5. **Return** `(deduped_auctions, report)`.

The orchestrator does NOT touch the database. It returns clean data.

### `run_and_persist(session, collectors: list[str] | None = None) -> RunReport`

Convenience function for callers that want the full pipeline:

1. Call `run_all(collectors)` to get auctions and report.
2. Call `upsert_auctions(session, auctions)` to persist.
3. Call `save_collector_health(session, ...)` for each succeeded/failed collector.
4. Populate `new_records`, `updated_records`, `skipped_records` on the report from the `UpsertResult`.
5. Return the enriched report.

## Upsert Layer (`db/upsert.py`)

### `upsert_auctions(session, auctions: list[Auction]) -> UpsertResult`

For each auction:

1. Query `AuctionRow` by dedup key `(state, county, start_date, sale_type)`.
2. **No existing row:** Insert new `AuctionRow` → count as `new`.
3. **Existing row with lower `confidence_score`:** Update all fields → count as `updated`.
4. **Existing row with equal/higher `confidence_score`:** Skip → count as `skipped`.
5. Commit once at the end.
6. Return `UpsertResult(new=N, updated=N, skipped=N)`.

### `save_collector_health(session, name: str, success: bool, records: int, error: str | None) -> None`

Upserts a `CollectorHealthRow`:

- Always updates `last_run` to `datetime.now(UTC)`.
- On success: sets `last_success`, `records_collected`, clears `error_message`.
- On failure: sets `error_message`, leaves `last_success` and `records_collected` unchanged.

### `get_collector_health(session) -> list[CollectorHealth]`

Returns all `CollectorHealthRow` records as Pydantic `CollectorHealth` models. Used by the CLI `status` command (issue #17).

## Error Handling

- **Collector failure isolation.** Each collector runs in its own try/except. Any `Exception` is caught, logged via structlog (`collector_failed` event with collector name and error string), and recorded in health. The loop continues to the next collector.
- **Upsert errors propagate.** If the DB write fails, that is a real problem and should not be silently swallowed. The exception propagates to the caller.

## Logging (structlog events)

| Event | When | Key fields |
|-------|------|------------|
| `collector_start` | Before each collector runs | `collector` |
| `collector_complete` | After successful collect | `collector`, `records` |
| `collector_failed` | After collector exception | `collector`, `error` |
| `cross_dedup_complete` | After cross-collector dedup | `before`, `after` |
| `upsert_complete` | After DB upsert | `new`, `updated`, `skipped` |

## Testing Strategy

### Orchestrator tests

- Mock collectors (some succeed with fixture data, some raise).
- Verify: failure isolation (one failure doesn't stop others), cross-dedup logic (highest confidence wins), RunReport accuracy, collector name filtering, unknown name raises ValueError.

### Upsert tests

- Use a real SQLite in-memory DB with the ORM models.
- Verify: insert new record, update when higher confidence, skip when equal/lower confidence, health persistence on success, health persistence on failure (error set, previous success preserved), health clearing on subsequent success.

### No integration tests hitting real websites

All collector behavior is already tested in their own test files. The orchestrator tests use mock collectors only.

## Out of Scope

- Concurrency (sequential for now, can add semaphore later)
- CLI wiring (issue #17)
- Merge/field-filling across confidence tiers (just replace or skip)
- Retry of failed collectors within a single run
