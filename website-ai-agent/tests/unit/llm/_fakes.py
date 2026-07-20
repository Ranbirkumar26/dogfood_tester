"""Shared fakes for LLM-layer unit tests: an in-memory chat transport.

Plain importable module (not a conftest) so test files can import these helpers by name;
kept out of conftest to avoid double-import under importlib mode.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


class FakeTransport:
    """Scriptable ChatTransport: returns queued responses or raises queued errors.

    Each queue item is either an exception (raised) or a (content, prompt_tokens,
    completion_tokens) tuple shaped into the openai response object the manager reads.
    """

    def __init__(self, script: list[Any]) -> None:
        self._script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self._script:
            raise AssertionError("FakeTransport exhausted: unexpected extra call")
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        content, prompt_tokens, completion_tokens = item
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
        )


def response(content: str, prompt_tokens: int = 10, completion_tokens: int = 5) -> tuple:
    """Convenience for a scripted successful response."""
    return (content, prompt_tokens, completion_tokens)
