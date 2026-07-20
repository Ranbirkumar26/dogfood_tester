"""LLM capability layer: provider-agnostic model access with accounting (designs D3, D13)."""

from website_agent.llm.ledger import LedgerTotals, LlmUsage, TokenLedger
from website_agent.llm.manager import (
    ChatTransport,
    ModelManager,
    OpenAiTransport,
    map_openai_error,
    parse_structured,
)
from website_agent.llm.pricing import PriceTable
from website_agent.llm.rate_limit import AsyncRateLimiter
from website_agent.llm.recorder import CassetteEntry, CassetteStore, request_key

__all__ = [
    "AsyncRateLimiter",
    "CassetteEntry",
    "CassetteStore",
    "ChatTransport",
    "LedgerTotals",
    "LlmUsage",
    "ModelManager",
    "OpenAiTransport",
    "PriceTable",
    "TokenLedger",
    "map_openai_error",
    "parse_structured",
    "request_key",
]
