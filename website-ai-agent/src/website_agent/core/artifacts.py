"""Artifact storage: files under the run directory, referenced by ArtifactRef.

Design rationale: state and checkpoints stay small by holding references, not bodies
(design D8). The store owns naming, placement, and traversal safety so no other component
ever constructs artifact paths by hand. The ABC is the seam; FileArtifactStore is the only
production implementation (local disk), and tests may substitute an in-memory fake.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from website_agent.core.clock import Clock
from website_agent.core.errors import AgentError
from website_agent.core.types import ArtifactRef

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


class ArtifactStore(ABC):
    """Write-side interface for run artifacts."""

    @abstractmethod
    def save_bytes(self, kind: str, name: str, data: bytes) -> ArtifactRef:
        """Persist binary data under ``<run_dir>/<kind>/<name>`` and return its reference."""

    @abstractmethod
    def save_text(self, kind: str, name: str, text: str) -> ArtifactRef:
        """Persist UTF-8 text and return its reference."""

    @abstractmethod
    def save_json(self, kind: str, name: str, payload: Any) -> ArtifactRef:
        """Persist a JSON-serializable payload (indent 2, sorted keys) and return its reference."""

    @abstractmethod
    def path_for(self, ref: ArtifactRef) -> Path:
        """Absolute path for a previously saved reference."""


class FileArtifactStore(ArtifactStore):
    """Artifacts on local disk under ``<reports_root>/<run_id>/``.

    Args:
        reports_root: base output directory (config ``paths.reports_dir``).
        run_id: owning run; becomes the directory name.
        clock: timestamp source for ArtifactRef.created_at.
    """

    def __init__(self, reports_root: Path, run_id: str, clock: Clock) -> None:
        self._run_dir = reports_root / run_id
        self._clock = clock
        self._run_dir.mkdir(parents=True, exist_ok=True)

    @property
    def run_dir(self) -> Path:
        """Absolute run directory owned by this store."""
        return self._run_dir

    def save_bytes(self, kind: str, name: str, data: bytes) -> ArtifactRef:
        """Persist binary data under ``<run_dir>/<kind>/<name>`` and return its reference."""
        target = self._target(kind, name)
        target.write_bytes(data)
        return self._ref(kind, name, len(data))

    def save_text(self, kind: str, name: str, text: str) -> ArtifactRef:
        """Persist UTF-8 text and return its reference."""
        return self.save_bytes(kind, name, text.encode("utf-8"))

    def save_json(self, kind: str, name: str, payload: Any) -> ArtifactRef:
        """Persist a JSON-serializable payload (indent 2, sorted keys) and return its reference."""
        text = json.dumps(payload, indent=2, sort_keys=True, default=str)
        return self.save_text(kind, name, text)

    def path_for(self, ref: ArtifactRef) -> Path:
        """Absolute path for a previously saved reference."""
        return self._run_dir / ref.relpath

    def _target(self, kind: str, name: str) -> Path:
        for label, value in (("kind", kind), ("name", name)):
            if not _SAFE_NAME.match(value):
                raise AgentError(
                    "unsafe artifact path segment",
                    context={label: value, "allowed": _SAFE_NAME.pattern},
                )
        directory = self._run_dir / kind
        directory.mkdir(parents=True, exist_ok=True)
        return directory / name

    def _ref(self, kind: str, name: str, size: int) -> ArtifactRef:
        return ArtifactRef(
            kind=kind,
            name=name,
            relpath=f"{kind}/{name}",
            size_bytes=size,
            created_at=self._clock.now(),
        )
