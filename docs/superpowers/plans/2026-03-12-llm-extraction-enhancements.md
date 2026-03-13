# LLM Extraction Enhancements Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance `LLMExtraction` with budget logging, API key gating, error handling, and a cheaper default model.

**Architecture:** Add a standalone `BudgetLogger` class that appends JSONL cost records. Wire it into `LLMExtraction` via an `on_usage` constructor callback. Gate LLM extraction on `ANTHROPIC_API_KEY` presence in `client.py`. Catch `anthropic.APIError` and convert to `RuntimeError` for existing error handling.

**Tech Stack:** Python, Pydantic, anthropic SDK, structlog, pytest

---

## Chunk 1: BudgetLogger + LLMExtraction Enhancements

### Task 1: BudgetLogger

**Files:**
- Create: `src/tdc_auction_calendar/collectors/scraping/budget.py`
- Test: `tests/scraping/test_budget.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/scraping/test_budget.py`:

```python
"""Tests for BudgetLogger."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tdc_auction_calendar.collectors.scraping.budget import BudgetLogger


@pytest.fixture()
def budget_path(tmp_path):
    return tmp_path / "costs" / "llm_costs.jsonl"


def _make_usage(input_tokens=100, output_tokens=50):
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    return usage


def test_budget_logger_appends_jsonl(budget_path):
    """BudgetLogger writes a valid JSONL line with expected fields."""
    logger = BudgetLogger(path=budget_path)
    logger.log("claude-haiku-4-5-20251001", "NoticeRecord", _make_usage())

    lines = budget_path.read_text().strip().split("\n")
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["model"] == "claude-haiku-4-5-20251001"
    assert record["schema"] == "NoticeRecord"
    assert record["input_tokens"] == 100
    assert record["output_tokens"] == 50
    assert "timestamp" in record
    assert "estimated_cost_usd" in record


def test_budget_logger_creates_directory(budget_path):
    """BudgetLogger creates parent directories if missing."""
    assert not budget_path.parent.exists()

    logger = BudgetLogger(path=budget_path)
    logger.log("claude-haiku-4-5-20251001", "NoticeRecord", _make_usage())

    assert budget_path.exists()


def test_budget_logger_appends_multiple(budget_path):
    """Multiple log calls append separate lines."""
    logger = BudgetLogger(path=budget_path)
    logger.log("claude-haiku-4-5-20251001", "SchemaA", _make_usage(100, 50))
    logger.log("claude-haiku-4-5-20251001", "SchemaB", _make_usage(200, 80))

    lines = budget_path.read_text().strip().split("\n")
    assert len(lines) == 2


def test_budget_logger_handles_write_failure(tmp_path):
    """BudgetLogger logs warning and does not raise on write failure."""
    read_only = tmp_path / "readonly" / "costs.jsonl"
    read_only.parent.mkdir()
    read_only.parent.chmod(0o444)

    logger = BudgetLogger(path=read_only)

    # Should not raise
    logger.log("claude-haiku-4-5-20251001", "Schema", _make_usage())

    # Restore permissions for cleanup
    read_only.parent.chmod(0o755)


def test_budget_logger_unknown_model_null_cost(budget_path):
    """Unknown models log null for estimated_cost_usd."""
    logger = BudgetLogger(path=budget_path)
    logger.log("unknown-model-v9", "Schema", _make_usage())

    record = json.loads(budget_path.read_text().strip())
    assert record["estimated_cost_usd"] is None


def test_budget_logger_known_model_cost(budget_path):
    """Known models compute a non-null cost estimate."""
    logger = BudgetLogger(path=budget_path)
    logger.log("claude-haiku-4-5-20251001", "Schema", _make_usage(1000, 100))

    record = json.loads(budget_path.read_text().strip())
    assert record["estimated_cost_usd"] is not None
    assert record["estimated_cost_usd"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scraping/test_budget.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tdc_auction_calendar.collectors.scraping.budget'`

- [ ] **Step 3: Write BudgetLogger implementation**

Create `src/tdc_auction_calendar/collectors/scraping/budget.py`:

```python
"""Budget logging for LLM extraction API calls."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# Per-token costs in USD. Last updated: 2026-03-12.
_TOKEN_COSTS: dict[str, tuple[float, float]] = {
    # (input_cost_per_token, output_cost_per_token)
    "claude-haiku-4-5-20251001": (1.00 / 1_000_000, 5.00 / 1_000_000),
    "claude-sonnet-4-20250514": (3.00 / 1_000_000, 15.00 / 1_000_000),
}


class BudgetLogger:
    """Appends one JSONL record per LLM extraction call."""

    def __init__(self, path: Path = Path("data/llm_costs.jsonl")) -> None:
        self._path = path

    def log(self, model: str, schema_name: str, usage: Any) -> None:
        """Append a cost record. Never raises."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)

            cost = self._estimate_cost(model, usage.input_tokens, usage.output_tokens)
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "model": model,
                "schema": schema_name,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "estimated_cost_usd": cost,
            }

            with self._path.open("a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as exc:
            logger.warning("budget_log_write_failed", error=str(exc))

    def _estimate_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float | None:
        rates = _TOKEN_COSTS.get(model)
        if rates is None:
            return None
        input_rate, output_rate = rates
        return round(input_tokens * input_rate + output_tokens * output_rate, 6)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/scraping/test_budget.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/budget.py tests/scraping/test_budget.py
git commit -m "feat: add BudgetLogger for LLM extraction cost tracking (issue #14)"
```

---

### Task 2: LLMExtraction enhancements

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/scraping/extraction.py:22-77`
- Test: `tests/scraping/test_extraction.py` (add new tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/scraping/test_extraction.py`:

```python
async def test_llm_extraction_default_model():
    """Default model is claude-haiku-4-5-20251001."""
    extractor = LLMExtraction(client=AsyncMock())
    assert extractor._model == "claude-haiku-4-5-20251001"


async def test_llm_extraction_on_usage_callback():
    """on_usage callback receives model, schema name, and usage."""
    usage_calls = []

    def on_usage(model, schema_name, usage):
        usage_calls.append((model, schema_name, usage))

    mock_usage = MagicMock()
    mock_usage.input_tokens = 500
    mock_usage.output_tokens = 100

    mock_client = AsyncMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[
            MagicMock(
                type="tool_use",
                input={"county": "Test", "date": "2026-01-01", "sale_type": "deed"},
            )
        ],
        usage=mock_usage,
    )

    extractor = LLMExtraction(client=mock_client, on_usage=on_usage)
    await extractor.extract("content", schema=AuctionInfo)

    assert len(usage_calls) == 1
    assert usage_calls[0][0] == "claude-haiku-4-5-20251001"
    assert usage_calls[0][1] == "AuctionInfo"
    assert usage_calls[0][2].input_tokens == 500


async def test_llm_extraction_on_usage_fires_before_validation():
    """on_usage fires even if Pydantic validation fails."""
    usage_calls = []

    mock_client = AsyncMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[
            MagicMock(
                type="tool_use",
                input={"bad_field": "value"},  # Will fail AuctionInfo validation
            )
        ],
        usage=MagicMock(input_tokens=100, output_tokens=50),
    )

    extractor = LLMExtraction(
        client=mock_client,
        on_usage=lambda m, s, u: usage_calls.append((m, s, u)),
    )

    with pytest.raises(Exception):  # Pydantic ValidationError
        await extractor.extract("content", schema=AuctionInfo)

    assert len(usage_calls) == 1


async def test_llm_extraction_api_error():
    """anthropic.APIError is caught and raised as RuntimeError."""
    import anthropic

    mock_client = AsyncMock()
    mock_client.messages.create.side_effect = anthropic.APIError(
        message="rate limited",
        request=MagicMock(),
        body=None,
    )

    extractor = LLMExtraction(client=mock_client)

    with pytest.raises(RuntimeError, match="Claude API error"):
        await extractor.extract("content", schema=AuctionInfo)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scraping/test_extraction.py::test_llm_extraction_default_model tests/scraping/test_extraction.py::test_llm_extraction_on_usage_callback tests/scraping/test_extraction.py::test_llm_extraction_on_usage_fires_before_validation tests/scraping/test_extraction.py::test_llm_extraction_api_error -v`
Expected: FAIL — default model is wrong, `on_usage` not accepted, `APIError` not caught

- [ ] **Step 3: Update LLMExtraction**

In `src/tdc_auction_calendar/collectors/scraping/extraction.py`, modify the `LLMExtraction` class:

```python
class LLMExtraction:
    """Extracts structured data using Claude's tool_use feature."""

    def __init__(
        self,
        client: Any = None,
        model: str = "claude-haiku-4-5-20251001",
        on_usage: Callable[[str, str, Any], None] | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._on_usage = on_usage

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic()
        return self._client

    async def extract(
        self, content: str, *, schema: type[BaseModel] | None = None
    ) -> BaseModel:
        """Extract structured data from content using a Pydantic schema."""
        if schema is None:
            raise ValueError("LLMExtraction requires a schema parameter")

        import anthropic

        client = self._get_client()
        json_schema = schema.model_json_schema()
        json_schema.pop("title", None)

        tool = {
            "name": schema.__name__,
            "description": f"Extract {schema.__name__} data from the page content.",
            "input_schema": json_schema,
        }

        logger.info("llm_extraction_start", schema=schema.__name__, model=self._model)

        try:
            response = await client.messages.create(
                model=self._model,
                max_tokens=1024,
                tools=[tool],
                tool_choice={"type": "tool", "name": schema.__name__},
                messages=[
                    {
                        "role": "user",
                        "content": f"Extract structured data from this page content:\n\n{content}",
                    }
                ],
            )
        except anthropic.APIError as exc:
            logger.warning(
                "llm_extraction_api_error",
                schema=schema.__name__,
                error=str(exc),
            )
            raise RuntimeError(
                f"Claude API error during {schema.__name__} extraction: {exc}"
            ) from exc

        if self._on_usage is not None:
            self._on_usage(self._model, schema.__name__, response.usage)

        for block in response.content:
            if block.type == "tool_use":
                logger.info("llm_extraction_complete", schema=schema.__name__)
                return schema.model_validate(block.input)

        raise RuntimeError(f"No tool_use block in Claude response for {schema.__name__}")
```

Also add `Callable` to the imports at the top of the file:

```python
from typing import Any, Callable, Protocol
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/scraping/test_extraction.py -v`
Expected: All tests PASS (both old and new)

- [ ] **Step 5: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/extraction.py tests/scraping/test_extraction.py
git commit -m "feat: enhance LLMExtraction with usage callback, API error handling, Haiku default (issue #14)"
```

---

## Chunk 2: Client Orchestration Changes

### Task 3: API key gating and BudgetLogger wiring in client.py

**Files:**
- Modify: `src/tdc_auction_calendar/collectors/scraping/client.py:237-265`
- Test: `tests/scraping/test_client.py` (add new tests)

- [ ] **Step 1: Update existing test and write new failing tests**

First, update the existing `test_scrape_schema_without_extraction_defaults_to_llm` test in `tests/scraping/test_client.py` — it will break because `_run_extraction` now checks for `ANTHROPIC_API_KEY` before creating `LLMExtraction`. Replace it with:

```python
async def test_scrape_schema_without_extraction_defaults_to_llm(ok_fetcher, rate_limiter, cache, monkeypatch):
    """Passing schema without extraction creates a default LLMExtraction."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    class MySchema(BaseModel):
        county: str

    client = _make_client(ok_fetcher, rate_limiter=rate_limiter, cache=cache)

    with patch(
        "tdc_auction_calendar.collectors.scraping.client.LLMExtraction"
    ) as MockLLM, patch(
        "tdc_auction_calendar.collectors.scraping.client.BudgetLogger"
    ):
        mock_instance = AsyncMock()
        mock_instance.extract.return_value = MySchema(county="Test")
        MockLLM.return_value = mock_instance

        result = await client.scrape("https://example.com", schema=MySchema)

    assert result.data.county == "Test"
```

Then append the new tests:

```python
async def test_client_skips_llm_without_api_key(ok_fetcher, rate_limiter, cache, monkeypatch):
    """Without ANTHROPIC_API_KEY, schema-based extraction returns None."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    class MySchema(BaseModel):
        county: str

    client = _make_client(ok_fetcher, rate_limiter=rate_limiter, cache=cache)
    result = await client.scrape("https://example.com", schema=MySchema)

    assert result.data is None


async def test_client_llm_extraction_with_api_key(ok_fetcher, rate_limiter, cache, monkeypatch):
    """With ANTHROPIC_API_KEY, schema-based extraction creates LLMExtraction with BudgetLogger."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    class MySchema(BaseModel):
        county: str

    client = _make_client(ok_fetcher, rate_limiter=rate_limiter, cache=cache)

    with patch(
        "tdc_auction_calendar.collectors.scraping.client.LLMExtraction"
    ) as MockLLM, patch(
        "tdc_auction_calendar.collectors.scraping.client.BudgetLogger"
    ) as MockBudget:
        mock_instance = AsyncMock()
        mock_instance.extract.return_value = MySchema(county="Test")
        MockLLM.return_value = mock_instance
        mock_budget_instance = MagicMock()
        MockBudget.return_value = mock_budget_instance

        result = await client.scrape("https://example.com", schema=MySchema)

    MockBudget.assert_called_once()
    MockLLM.assert_called_once_with(on_usage=mock_budget_instance.log)
    assert result.data.county == "Test"


async def test_client_explicit_extraction_bypasses_api_key_check(ok_fetcher, rate_limiter, cache, monkeypatch):
    """Passing an explicit extraction strategy bypasses the API key check."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    extractor = AsyncMock()
    extractor.extract.return_value = {"county": "Test"}

    client = _make_client(ok_fetcher, rate_limiter=rate_limiter, cache=cache)
    result = await client.scrape("https://example.com", extraction=extractor)

    extractor.extract.assert_called_once()
    assert result.data == {"county": "Test"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/scraping/test_client.py::test_client_skips_llm_without_api_key tests/scraping/test_client.py::test_client_llm_extraction_with_api_key tests/scraping/test_client.py::test_client_explicit_extraction_bypasses_api_key_check -v`
Expected: FAIL — API key check doesn't exist yet, `BudgetLogger` not wired

- [ ] **Step 3: Update client.py**

In `src/tdc_auction_calendar/collectors/scraping/client.py`, modify `_run_extraction()`:

```python
async def _run_extraction(
    self,
    fetch_result: FetchResult,
    extraction: ExtractionStrategy | None,
    schema: type[BaseModel] | None,
) -> BaseModel | dict | list[dict] | None:
    """Run extraction on fetched content."""
    if extraction is None and schema is not None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            logger.warning("llm_extraction_skipped", reason="ANTHROPIC_API_KEY not set")
            return None
        budget = BudgetLogger()
        extraction = LLMExtraction(on_usage=budget.log)

    content = fetch_result.markdown or fetch_result.html
    if not content:
        raise ExtractionError(
            f"No content available for extraction from {fetch_result.url} "
            f"(fetcher: {fetch_result.fetcher})"
        )

    try:
        return await extraction.extract(content, schema=schema)
    except (ValueError, RuntimeError, httpx.HTTPStatusError) as exc:
        logger.error(
            "extraction_failed",
            url=fetch_result.url,
            extraction_type=type(extraction).__name__,
            error=str(exc),
        )
        raise ExtractionError(
            f"Extraction failed for {fetch_result.url}: {exc}"
        ) from exc
```

Also add the `BudgetLogger` import at the top of `client.py`:

```python
from tdc_auction_calendar.collectors.scraping.budget import BudgetLogger
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/scraping/test_client.py -v`
Expected: All tests PASS (both old and new)

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS — no regressions

- [ ] **Step 6: Commit**

```bash
git add src/tdc_auction_calendar/collectors/scraping/client.py tests/scraping/test_client.py
git commit -m "feat: add API key gating and BudgetLogger wiring in ScrapeClient (issue #14)"
```
