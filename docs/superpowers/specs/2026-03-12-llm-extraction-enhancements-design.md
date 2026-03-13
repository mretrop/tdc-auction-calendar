# LLM Extraction Enhancements Design

**Issue:** #14 — [M2] Claude API fallback parser
**Date:** 2026-03-12

## Overview

Enhance the existing `LLMExtraction` class with budget logging, opt-in API key gating, and rate-limit handling. Rather than creating a redundant `llm_fallback.py` module (as the original issue suggested), this integrates the needed functionality into the existing extraction pipeline where it fits naturally.

## Deviations from Original Issue

- **No new `collectors/llm_fallback.py` module.** The existing `LLMExtraction` already serves as the Claude API extraction layer. A separate module would duplicate it.
- **No confidence threshold trigger.** The issue specified "Triggered when Crawl4AI extraction confidence < 0.5", but the current architecture has no extraction-level confidence scoring — Crawl4AI is purely a fetcher, and `LLMExtraction` is already the extraction fallback. Confidence scores are static per-collector, not per-extraction. This deviation is intentional.

## Decisions

- **Budget logging as a separate concern.** A standalone `BudgetLogger` class in a new `budget.py` file, not mixed into extraction logic.
- **Opt-in gating in the orchestrator.** `client.py` checks for `ANTHROPIC_API_KEY` before instantiating `LLMExtraction`. If missing, extraction is skipped gracefully (returns `None`).
- **API error handling in extraction.** `LLMExtraction.extract()` catches `anthropic.APIError` (base class, covers rate limits, auth errors, connection errors) and raises `RuntimeError` so it is caught by the existing `except` clause in `_run_extraction()`.
- **Default model → Haiku.** Extraction is a lightweight task; `claude-haiku-4-5-20251001` is sufficient and cheaper.
- **Callback on `__init__`, not `extract()`.** The `on_usage` callback is passed at construction time so the `ExtractionStrategy` protocol stays unchanged and `ScrapeClient` can wire it once when creating the instance.

## Files

### New

| File | Purpose |
|------|---------|
| `src/tdc_auction_calendar/collectors/scraping/budget.py` | `BudgetLogger` — appends JSONL cost records |
| `tests/collectors/scraping/test_budget.py` | BudgetLogger tests |
| `tests/collectors/scraping/test_llm_extraction.py` | LLMExtraction enhancement tests |

### Modified

| File | Change |
|------|--------|
| `src/tdc_auction_calendar/collectors/scraping/extraction.py` | Default model → Haiku, add `on_usage` constructor callback, catch `anthropic.APIError` |
| `src/tdc_auction_calendar/collectors/scraping/client.py` | API key gating in `_run_extraction()`, wire up `BudgetLogger` via `on_usage` |

## BudgetLogger

**File:** `collectors/scraping/budget.py`

```python
class BudgetLogger:
    def __init__(self, path: Path = Path("data/llm_costs.jsonl")) -> None: ...
    def log(self, model: str, schema_name: str, usage: Usage) -> None: ...
```

Each call appends one JSON line:

```json
{"timestamp": "2026-03-12T14:30:00Z", "model": "claude-haiku-4-5-20251001", "schema": "NoticeRecord", "input_tokens": 1200, "output_tokens": 85, "estimated_cost_usd": 0.0013}
```

**Cost estimation:** Hardcoded per-token rates for known models (`claude-haiku-4-5-20251001`, `claude-sonnet-4-20250514`). Unknown models log `null` for cost. Include a comment noting when rates were last updated.

**Error handling:** If file write fails (permissions, disk), log a warning via structlog and return. Never raises.

**Directory creation:** Creates parent directories if they don't exist (`path.parent.mkdir(parents=True, exist_ok=True)`).

## LLMExtraction Changes

**Default model:** `claude-haiku-4-5-20251001`

**New `on_usage` callback on `__init__`:**

```python
def __init__(
    self,
    client: Any = None,
    model: str = "claude-haiku-4-5-20251001",
    on_usage: Callable[[str, str, Any], None] | None = None,
) -> None:
    self._client = client
    self._model = model
    self._on_usage = on_usage
```

After a successful API call, if `_on_usage` is set, call `self._on_usage(self._model, schema.__name__, response.usage)`. This fires before validation so usage is logged even if validation fails.

**API error handling:**

```python
try:
    response = await client.messages.create(...)
except anthropic.APIError as exc:
    logger.warning("llm_extraction_api_error", schema=schema.__name__, error=str(exc))
    raise RuntimeError(f"Claude API error during {schema.__name__} extraction: {exc}") from exc
```

This raises `RuntimeError`, which is already caught by the `except (ValueError, RuntimeError, httpx.HTTPStatusError)` clause in `_run_extraction()`. That handler logs the error and raises `ExtractionError`, which propagates to the collector. No retry — the extraction is skipped.

## Client Orchestration Changes

In `_run_extraction()`, before the existing `LLMExtraction` auto-instantiation:

```python
import os
if not os.environ.get("ANTHROPIC_API_KEY"):
    logger.warning("llm_extraction_skipped", reason="ANTHROPIC_API_KEY not set")
    return None
```

When instantiating `LLMExtraction`, create a `BudgetLogger` and pass it as the `on_usage` callback:

```python
budget = BudgetLogger()
extraction = LLMExtraction(on_usage=budget.log)
```

The `BudgetLogger` is created per `_run_extraction()` call. This is fine since it just opens, appends, and closes a file — no persistent state needed.

## Testing

| Test | What it verifies |
|------|-----------------|
| `test_budget_logger_appends_jsonl` | Writes valid JSONL line with expected fields |
| `test_budget_logger_creates_directory` | Creates parent dirs if missing |
| `test_budget_logger_handles_write_failure` | Logs warning, doesn't raise |
| `test_llm_extraction_default_model` | Default is `claude-haiku-4-5-20251001` |
| `test_llm_extraction_on_usage_callback` | Callback receives model, schema name, usage |
| `test_llm_extraction_api_error` | `anthropic.APIError` → `RuntimeError` raised |
| `test_client_skips_without_api_key` | No `ANTHROPIC_API_KEY` → returns `None`, no `LLMExtraction` created |
| `test_client_wires_budget_logger` | With `ANTHROPIC_API_KEY` set, `BudgetLogger` callback is wired to `LLMExtraction` |

All tests use mocked Anthropic client — no real API calls.
