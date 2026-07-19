"""Redaction: secret shapes masked, ordinary text untouched, recursion into containers."""

from __future__ import annotations

import pytest

from website_agent.logging.redaction import MASK, redact_text, redact_value


@pytest.mark.parametrize(
    ("raw", "must_hide"),
    [
        ("api_key=sk-abc123def456ghi789", "sk-abc123def456ghi789"),
        ('password: "hunter2secret"', "hunter2secret"),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload", "eyJhbGciOiJIUzI1NiJ9"),
        ("token = xoxb-not-a-real-slack-token", "xoxb-not-a-real-slack-token"),
        ("curl -H 'secret=topsecretvalue'", "topsecretvalue"),
        ("found key sk-proj-1234567890abcdef in config", "sk-proj-1234567890abcdef"),
    ],
)
def test_secret_shapes_are_masked(raw: str, must_hide: str) -> None:
    result = redact_text(raw)
    assert must_hide not in result
    assert MASK in result


@pytest.mark.parametrize(
    "raw",
    [
        "navigated to https://example.com/pricing",
        "clicked element e12 (role=button, name='Sign up')",
        "form field label missing for input#email",
        "response 404 for GET /enterprise",
    ],
)
def test_ordinary_log_text_is_untouched(raw: str) -> None:
    assert redact_text(raw) == raw


def test_key_names_survive_only_values_masked() -> None:
    result = redact_text("api_key=sk-abcdef123456789 model=gpt-4o-mini")
    assert "api_key=" in result
    assert "model=gpt-4o-mini" in result


def test_redaction_is_idempotent() -> None:
    once = redact_text("token=abcdef123456")
    assert redact_text(once) == once


def test_redact_value_recurses_into_containers() -> None:
    payload = {
        "url": "https://example.com",
        "headers": {"Authorization": "Bearer abcdefgh12345678"},
        "notes": ["password=hunter2secret", "plain text"],
        "count": 3,
        "nested": ("api_key: sk-abcdefgh12345678",),
    }
    result = redact_value(payload)
    assert result["url"] == "https://example.com"
    assert "abcdefgh12345678" not in result["headers"]["Authorization"]
    assert "hunter2secret" not in result["notes"][0]
    assert result["notes"][1] == "plain text"
    assert result["count"] == 3
    assert isinstance(result["nested"], tuple)
    assert "sk-abcdefgh12345678" not in result["nested"][0]
