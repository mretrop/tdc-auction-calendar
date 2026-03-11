# BaseCollector Abstract Class Design

**Issue**: #9 — [M2] Abstract base collector class
**Date**: 2026-03-10
**Status**: Approved

## Purpose

Create the abstract base collector interface that all collectors extend. Provides a shared `deduplicate()` method and defines the contract for `collect()` and `normalize()`.

## File

`src/tdc_auction_calendar/collectors/base.py`

## Interface

```python
class BaseCollector(ABC):
    async def collect(self) -> list[Auction]: ...       # abstract
    def normalize(self, raw: dict) -> Auction: ...      # abstract
    def deduplicate(self, auctions: list[Auction]) -> list[Auction]: ...  # concrete
```

## Dedup Logic

- Group auctions by `auction.dedup_key` → `(state, county, start_date, sale_type)`
- For each group with duplicates, keep the auction with the highest `confidence_score`
- On tie, keep first encountered
- Log dropped count via structlog

## Tests

File: `tests/test_base_collector.py`

1. `deduplicate()` with no duplicates returns all auctions unchanged
2. `deduplicate()` with duplicates keeps highest confidence_score
3. `deduplicate()` with equal confidence keeps first encountered
4. ABC prevents direct instantiation (TypeError)
5. Concrete subclass can implement and call all methods
