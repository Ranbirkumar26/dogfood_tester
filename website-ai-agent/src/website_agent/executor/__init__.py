"""Executor: run one plan step via the tool layer, return structured results (design D2)."""

from website_agent.executor.executor import Executor
from website_agent.executor.models import ExecutionResult

__all__ = ["ExecutionResult", "Executor"]
