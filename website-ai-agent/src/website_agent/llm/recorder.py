"""Cassette record/replay for model responses (design D13).

Design rationale: CI and the default test suite must run keyless, cost-free, and
deterministic. A cassette is one JSON file per request key; the key hashes role, model,
messages, and output schema name, so any prompt or schema change invalidates the cassette
loudly (replay miss with the key in the error) instead of silently replaying stale
behavior. Cassettes live under version control for tests; a run can also record its own
for offline debugging.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from website_agent.core.errors import StateError


class CassetteEntry(BaseModel):
    """One recorded model response."""

    model_config = ConfigDict(frozen=True)

    content: str
    prompt_tokens: int
    completion_tokens: int
    model: str


def request_key(
    role: str, model: str, messages: list[dict[str, Any]], schema_name: str | None
) -> str:
    """Deterministic cassette key for one request."""
    basis = json.dumps(
        {"role": role, "model": model, "messages": messages, "schema": schema_name},
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(basis.encode()).hexdigest()[:24]


class CassetteStore:
    """Filesystem cassette storage: ``<dir>/<key>.json``."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    def load(self, key: str) -> CassetteEntry | None:
        """The recorded entry for ``key``, or None if absent."""
        path = self._dir / f"{key}.json"
        if not path.is_file():
            return None
        return CassetteEntry.model_validate_json(path.read_text())

    def require(self, key: str) -> CassetteEntry:
        """Load or fail with an actionable replay-miss error."""
        entry = self.load(key)
        if entry is None:
            raise StateError(
                "cassette replay miss: prompt, model, or schema changed since recording; "
                "re-record with WA_LLM__MODE=record",
                context={"key": key, "cassette_dir": str(self._dir)},
            )
        return entry

    def save(self, key: str, entry: CassetteEntry) -> None:
        """Persist ``entry`` under ``key`` (pretty-printed for reviewable diffs)."""
        path = self._dir / f"{key}.json"
        path.write_text(json.dumps(entry.model_dump(), indent=2, sort_keys=True) + "\n")
