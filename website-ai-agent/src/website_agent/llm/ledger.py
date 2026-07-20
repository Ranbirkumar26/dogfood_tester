"""Token and cost ledger: every model call accounted, split by role.

Design rationale: budgets (design D10) and the eval harness both need running totals of
tokens and dollars, and role-level attribution localizes cost regressions (a chatty
reviewer prompt shows up immediately). The ledger is append-only in memory; the run
lifecycle persists entries into the artifact directory at checkpoints (Phase 5 wiring).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from website_agent.core.clock import Clock
from website_agent.llm.pricing import PriceTable


class LlmUsage(BaseModel):
    """One completed model call."""

    model_config = ConfigDict(frozen=True)

    role: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    at: datetime


class LedgerTotals(BaseModel):
    """Aggregate over any set of usage entries."""

    model_config = ConfigDict(frozen=True)

    calls: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float

    @property
    def total_tokens(self) -> int:
        """Prompt plus completion tokens."""
        return self.prompt_tokens + self.completion_tokens


class TokenLedger:
    """Accumulates usage; the budget router and reports read totals from here."""

    def __init__(self, prices: PriceTable, clock: Clock) -> None:
        self._prices = prices
        self._clock = clock
        self._entries: list[LlmUsage] = []

    def record(
        self, *, role: str, model: str, prompt_tokens: int, completion_tokens: int
    ) -> LlmUsage:
        """Price and append one call; returns the recorded entry."""
        entry = LlmUsage(
            role=role,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=self._prices.cost(model, prompt_tokens, completion_tokens),
            at=self._clock.now(),
        )
        self._entries.append(entry)
        return entry

    def entries(self) -> list[LlmUsage]:
        """All entries in call order (copy; the ledger stays append-only)."""
        return list(self._entries)

    def totals(self) -> LedgerTotals:
        """Grand totals across all roles."""
        return self._aggregate(self._entries)

    def by_role(self) -> dict[str, LedgerTotals]:
        """Totals per role, for role-level cost attribution."""
        roles: dict[str, list[LlmUsage]] = {}
        for entry in self._entries:
            roles.setdefault(entry.role, []).append(entry)
        return {role: self._aggregate(entries) for role, entries in sorted(roles.items())}

    @staticmethod
    def _aggregate(entries: list[LlmUsage]) -> LedgerTotals:
        return LedgerTotals(
            calls=len(entries),
            prompt_tokens=sum(e.prompt_tokens for e in entries),
            completion_tokens=sum(e.completion_tokens for e in entries),
            cost_usd=round(sum(e.cost_usd for e in entries), 8),
        )
