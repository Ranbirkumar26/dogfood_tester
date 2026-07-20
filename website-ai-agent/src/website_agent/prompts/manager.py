"""Prompt templates: versioned files, strict rendering.

Design rationale: prompts are load-bearing code and live as reviewable files, one per
template, inside the package (they ship in the wheel so the installed CLI works
standalone). A template has a system section and a user section split by a marker line.
Rendering is strict both ways: a missing variable and an unused variable are both errors,
because silent prompt drift (a renamed variable no longer substituted) is a class of bug
that otherwise only shows up as degraded agent behavior. Versions are content hashes:
they change exactly when the template changes, with no manual bookkeeping, and feed
cassette keys so stale recordings fail loudly (design D13).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from string import Template
from typing import Any

from pydantic import BaseModel, ConfigDict

from website_agent.core.errors import ConfigError

SECTION_MARKER = "---USER---"

_DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "templates"


class RenderedPrompt(BaseModel):
    """A fully substituted prompt ready for the model manager."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    system: str
    user: str


class PromptManager:
    """Loads ``<name>.md`` templates and renders them with strict variable checking."""

    def __init__(self, templates_dir: Path | None = None) -> None:
        self._dir = templates_dir or _DEFAULT_TEMPLATES_DIR
        self._cache: dict[str, tuple[str, str, str]] = {}  # name -> (version, system, user)

    def render(self, name: str, variables: Mapping[str, Any] | None = None) -> RenderedPrompt:
        """Render template ``name`` with ``variables``.

        Variables are passed as a mapping rather than keyword arguments so a template may
        use any identifier (including ``name``) without colliding with this method's
        parameters.

        Raises:
            ConfigError: unknown template, missing variable, or unused variable.
        """
        variables = variables or {}
        version, system_raw, user_raw = self._load(name)

        system_template = Template(system_raw)
        user_template = Template(user_raw)
        wanted = set(system_template.get_identifiers()) | set(user_template.get_identifiers())
        provided = set(variables)
        if missing := wanted - provided:
            raise ConfigError(
                "prompt variables missing",
                context={"template": name, "missing": sorted(missing)},
            )
        if unused := provided - wanted:
            raise ConfigError(
                "prompt variables unused (template drift?)",
                context={"template": name, "unused": sorted(unused)},
            )

        rendered_vars = {key: str(value) for key, value in variables.items()}
        return RenderedPrompt(
            name=name,
            version=version,
            system=system_template.substitute(rendered_vars).strip(),
            user=user_template.substitute(rendered_vars).strip(),
        )

    def version_of(self, name: str) -> str:
        """Content-hash version of a template (logged with every role call)."""
        return self._load(name)[0]

    def _load(self, name: str) -> tuple[str, str, str]:
        if name in self._cache:
            return self._cache[name]
        path = self._dir / f"{name}.md"
        if not path.is_file():
            raise ConfigError(
                "prompt template not found",
                context={"template": name, "dir": str(self._dir)},
            )
        raw = path.read_text()
        if SECTION_MARKER not in raw:
            raise ConfigError(
                f"prompt template missing the {SECTION_MARKER} section marker",
                context={"template": name},
            )
        system_raw, user_raw = raw.split(SECTION_MARKER, 1)
        version = hashlib.sha256(raw.encode()).hexdigest()[:8]
        self._cache[name] = (version, system_raw, user_raw)
        return self._cache[name]
