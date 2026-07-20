"""Model price table: USD per million tokens, input and output.

Design rationale: cost tracking is a project constraint (design D10); every completion is
priced at record time so budgets can stop a run mid-flight. Prices are baked defaults with
prefix matching (dated model snapshots like gpt-4o-mini-2024-07-18 inherit the family
price) and unknown models price at zero with a one-time warning: local models (Ollama,
vLLM) are free and must not spam logs, while a genuinely unknown paid model shows up as
cost 0 in reports, which the warning makes auditable.
"""

from __future__ import annotations

from website_agent.logging import get_logger

log = get_logger("llm.pricing")

# (input USD per 1M tokens, output USD per 1M tokens)
DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "o4-mini": (1.10, 4.40),
    "o3": (2.00, 8.00),
}


class PriceTable:
    """Model-name to price lookup with longest-prefix matching."""

    def __init__(self, prices: dict[str, tuple[float, float]] | None = None) -> None:
        self._prices = dict(DEFAULT_PRICES if prices is None else prices)
        self._warned: set[str] = set()

    def register(self, model: str, input_per_million: float, output_per_million: float) -> None:
        """Add or override a model's pricing (config-driven for future models)."""
        self._prices[model] = (input_per_million, output_per_million)

    def get(self, model: str) -> tuple[float, float]:
        """Prices for ``model``; exact match, then longest known prefix, then (0, 0)."""
        if model in self._prices:
            return self._prices[model]
        candidates = [known for known in self._prices if model.startswith(known)]
        if candidates:
            return self._prices[max(candidates, key=len)]
        if model not in self._warned:
            self._warned.add(model)
            log.warning("unknown_model_priced_at_zero", model=model)
        return (0.0, 0.0)

    def cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Cost in USD for one completion."""
        input_price, output_price = self.get(model)
        return (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000
