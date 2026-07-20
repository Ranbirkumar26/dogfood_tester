"""Price table: exact match, prefix inheritance, unknown-model zero pricing."""

from __future__ import annotations

import logging

import pytest

from website_agent.llm.pricing import DEFAULT_PRICES, PriceTable


def test_exact_model_lookup() -> None:
    table = PriceTable()
    assert table.get("gpt-4o-mini") == DEFAULT_PRICES["gpt-4o-mini"]


def test_dated_snapshot_inherits_family_price() -> None:
    table = PriceTable()
    assert table.get("gpt-4o-mini-2024-07-18") == table.get("gpt-4o-mini")


def test_longest_prefix_wins() -> None:
    table = PriceTable({"gpt-4": (1.0, 2.0), "gpt-4o-mini": (0.15, 0.60)})
    assert table.get("gpt-4o-mini-2024") == (0.15, 0.60)
    assert table.get("gpt-4-turbo") == (1.0, 2.0)


def test_unknown_model_prices_zero_and_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="website_agent.llm.pricing")
    table = PriceTable()
    assert table.get("llama3.1:8b") == (0.0, 0.0)
    assert table.get("llama3.1:8b") == (0.0, 0.0)  # second call must not re-warn
    warnings = [r for r in caplog.records if r.getMessage() == "unknown_model_priced_at_zero"]
    assert len(warnings) == 1


def test_cost_computation() -> None:
    table = PriceTable({"m": (1.0, 2.0)})  # $1/1M in, $2/1M out
    # 1_000_000 prompt tokens -> $1.00; 500_000 completion tokens -> $1.00
    assert table.cost("m", 1_000_000, 500_000) == 2.0
    assert table.cost("m", 0, 0) == 0.0


def test_register_overrides_price() -> None:
    table = PriceTable()
    table.register("custom-model", 5.0, 10.0)
    assert table.get("custom-model") == (5.0, 10.0)
