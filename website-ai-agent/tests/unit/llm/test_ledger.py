"""Token ledger: pricing at record time, grand totals, per-role attribution."""

from __future__ import annotations

from website_agent.core.clock import FixedClock
from website_agent.llm.ledger import TokenLedger
from website_agent.llm.pricing import PriceTable


def _ledger(clock: FixedClock) -> TokenLedger:
    return TokenLedger(PriceTable({"m": (1.0, 2.0)}), clock)


def test_record_prices_and_returns_entry(fixed_clock: FixedClock) -> None:
    ledger = _ledger(fixed_clock)
    entry = ledger.record(role="planner", model="m", prompt_tokens=1_000_000, completion_tokens=0)
    assert entry.cost_usd == 1.0
    assert entry.role == "planner"
    assert entry.at == fixed_clock.now()


def test_totals_aggregate_across_calls(fixed_clock: FixedClock) -> None:
    ledger = _ledger(fixed_clock)
    ledger.record(role="planner", model="m", prompt_tokens=100, completion_tokens=50)
    ledger.record(role="reviewer", model="m", prompt_tokens=200, completion_tokens=25)
    totals = ledger.totals()
    assert totals.calls == 2
    assert totals.prompt_tokens == 300
    assert totals.completion_tokens == 75
    assert totals.total_tokens == 375


def test_by_role_attribution(fixed_clock: FixedClock) -> None:
    ledger = _ledger(fixed_clock)
    ledger.record(role="planner", model="m", prompt_tokens=100, completion_tokens=10)
    ledger.record(role="planner", model="m", prompt_tokens=100, completion_tokens=10)
    ledger.record(role="reviewer", model="m", prompt_tokens=50, completion_tokens=5)
    by_role = ledger.by_role()
    assert set(by_role) == {"planner", "reviewer"}
    assert by_role["planner"].calls == 2
    assert by_role["planner"].prompt_tokens == 200
    assert by_role["reviewer"].calls == 1


def test_entries_are_copied_not_shared(fixed_clock: FixedClock) -> None:
    ledger = _ledger(fixed_clock)
    ledger.record(role="planner", model="m", prompt_tokens=1, completion_tokens=1)
    snapshot = ledger.entries()
    ledger.record(role="planner", model="m", prompt_tokens=1, completion_tokens=1)
    assert len(snapshot) == 1  # earlier copy unaffected by later record
    assert len(ledger.entries()) == 2


def test_empty_ledger_totals_are_zero(fixed_clock: FixedClock) -> None:
    totals = _ledger(fixed_clock).totals()
    assert totals.calls == 0
    assert totals.cost_usd == 0.0
    assert totals.total_tokens == 0


def test_seed_carries_prior_spend_across_resume(fixed_clock: FixedClock) -> None:
    ledger = _ledger(fixed_clock)
    ledger.seed(tokens=500, cost_usd=0.02)
    ledger.record(role="planner", model="m", prompt_tokens=100, completion_tokens=50)
    totals = ledger.totals()
    # The seed preserves prior tokens and cost; the new call adds its own on top.
    assert totals.total_tokens == 650
    assert totals.cost_usd == 0.0202  # 0.02 seeded + 0.0002 for the 100/50 token call


def test_seed_is_a_noop_for_zero_spend(fixed_clock: FixedClock) -> None:
    ledger = _ledger(fixed_clock)
    ledger.seed(tokens=0, cost_usd=0.0)
    assert ledger.totals().calls == 0
