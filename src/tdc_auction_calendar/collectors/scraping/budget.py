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
