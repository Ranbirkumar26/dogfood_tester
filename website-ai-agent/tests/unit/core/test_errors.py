"""Exception hierarchy: taxonomy mapping, retryable markers, context rendering."""

from __future__ import annotations

import pytest

from website_agent.core.errors import (
    AgentError,
    BrowserError,
    BrowserFatalError,
    BrowserTransientError,
    ConfigError,
    DependencyError,
    FatalError,
    ModelError,
    ModelRateLimitError,
    ModelTransientError,
    OutputParseError,
    PolicyViolationError,
    StateError,
)


def test_every_error_derives_from_agent_error() -> None:
    for exc_type in (
        ConfigError,
        DependencyError,
        PolicyViolationError,
        BrowserTransientError,
        BrowserFatalError,
        ModelTransientError,
        ModelRateLimitError,
        OutputParseError,
        StateError,
        FatalError,
    ):
        assert issubclass(exc_type, AgentError)


def test_family_bases_group_the_taxonomy() -> None:
    assert issubclass(BrowserTransientError, BrowserError)
    assert issubclass(BrowserFatalError, BrowserError)
    assert issubclass(ModelRateLimitError, ModelTransientError)
    assert issubclass(OutputParseError, ModelError)


@pytest.mark.parametrize(
    ("exc_type", "expected"),
    [
        (BrowserTransientError, True),
        (ModelTransientError, True),
        (ModelRateLimitError, True),
        (BrowserFatalError, False),
        (OutputParseError, False),
        (PolicyViolationError, False),
        (FatalError, False),
        (ConfigError, False),
    ],
)
def test_retryable_markers_match_failure_taxonomy(
    exc_type: type[AgentError], expected: bool
) -> None:
    assert exc_type.retryable is expected


def test_context_appears_in_str_sorted_and_repr_formatted() -> None:
    err = AgentError("boom", context={"b": 2, "a": "x"})
    assert str(err) == "boom (a='x', b=2)"
    assert AgentError("plain").context == {}
    assert str(AgentError("plain")) == "plain"


def test_rate_limit_carries_retry_after() -> None:
    err = ModelRateLimitError("429", retry_after=7.5, context={"provider": "openai"})
    assert err.retry_after == 7.5
    assert err.context["provider"] == "openai"
    assert ModelTransientError("503").retry_after is None
