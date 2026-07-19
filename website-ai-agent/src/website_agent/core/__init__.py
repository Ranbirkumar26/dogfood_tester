"""Foundation layer: exception hierarchy, shared types, DI, retry policies, clock, IDs, artifacts.

Design rationale: these units are consolidated in one package (rather than one directory each)
because they form a single cohesive foundation with no internal layering; everything above
Layer 1 imports from here and nothing here imports from above (docs/architecture/components.md,
dependency rule 1). This package must stay free of LLM, browser, and framework dependencies.
"""

from website_agent.core.artifacts import ArtifactStore, FileArtifactStore
from website_agent.core.clock import Clock, FixedClock, SystemClock
from website_agent.core.di import Container
from website_agent.core.errors import (
    AgentError,
    BrowserFatalError,
    BrowserTransientError,
    ConfigError,
    DependencyError,
    FatalError,
    ModelRateLimitError,
    ModelTransientError,
    OutputParseError,
    PolicyViolationError,
    StateError,
)
from website_agent.core.ids import generate_run_id, generate_step_id
from website_agent.core.retry import (
    BROWSER_TRANSIENT_POLICY,
    LLM_REPAIR_POLICY,
    LLM_TRANSIENT_POLICY,
    RetryPolicy,
    retry_async,
)
from website_agent.core.types import (
    ArtifactRef,
    GoalMode,
    RiskClass,
    Severity,
    StopReason,
)

__all__ = [
    "AgentError",
    "ArtifactRef",
    "ArtifactStore",
    "BROWSER_TRANSIENT_POLICY",
    "BrowserFatalError",
    "BrowserTransientError",
    "Clock",
    "ConfigError",
    "Container",
    "DependencyError",
    "FatalError",
    "FileArtifactStore",
    "FixedClock",
    "GoalMode",
    "LLM_REPAIR_POLICY",
    "LLM_TRANSIENT_POLICY",
    "ModelRateLimitError",
    "ModelTransientError",
    "OutputParseError",
    "PolicyViolationError",
    "RetryPolicy",
    "RiskClass",
    "Severity",
    "StateError",
    "StopReason",
    "SystemClock",
    "generate_run_id",
    "generate_step_id",
    "retry_async",
]
