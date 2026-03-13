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
    """Known models compute correct cost estimate."""
    logger = BudgetLogger(path=budget_path)
    logger.log("claude-haiku-4-5-20251001", "Schema", _make_usage(1000, 100))

    record = json.loads(budget_path.read_text().strip())
    # 1000 * $1/M + 100 * $5/M = $0.001 + $0.0005 = $0.0015
    assert record["estimated_cost_usd"] == 0.0015
