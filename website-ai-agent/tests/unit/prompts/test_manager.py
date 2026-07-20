"""Prompt manager: section split, strict variable checking, versioning."""

from __future__ import annotations

from pathlib import Path

import pytest

from website_agent.core.errors import ConfigError
from website_agent.prompts.manager import PromptManager


@pytest.fixture
def templates_dir(tmp_path: Path) -> Path:
    (tmp_path / "greet.md").write_text(
        "You are a $role assistant.\n---USER---\nGreet $name in $lang."
    )
    (tmp_path / "no_marker.md").write_text("system only, no user section")
    return tmp_path


def test_render_substitutes_both_sections(templates_dir: Path) -> None:
    manager = PromptManager(templates_dir)
    rendered = manager.render("greet", {"role": "qa", "name": "Ada", "lang": "English"})
    assert rendered.system == "You are a qa assistant."
    assert rendered.user == "Greet Ada in English."
    assert rendered.name == "greet"


def test_missing_variable_is_an_error(templates_dir: Path) -> None:
    manager = PromptManager(templates_dir)
    with pytest.raises(ConfigError, match="missing") as excinfo:
        manager.render("greet", {"role": "qa", "name": "Ada"})
    assert "lang" in excinfo.value.context["missing"]


def test_unused_variable_is_an_error(templates_dir: Path) -> None:
    manager = PromptManager(templates_dir)
    with pytest.raises(ConfigError, match="unused") as excinfo:
        manager.render("greet", {"role": "qa", "name": "Ada", "lang": "English", "extra": "x"})
    assert "extra" in excinfo.value.context["unused"]


def test_unknown_template_is_an_error(templates_dir: Path) -> None:
    manager = PromptManager(templates_dir)
    with pytest.raises(ConfigError, match="not found"):
        manager.render("absent", {"x": "y"})


def test_missing_section_marker_is_an_error(templates_dir: Path) -> None:
    manager = PromptManager(templates_dir)
    with pytest.raises(ConfigError, match="section marker"):
        manager.render("no_marker")


def test_version_is_stable_and_content_addressed(templates_dir: Path) -> None:
    manager = PromptManager(templates_dir)
    version = manager.version_of("greet")
    assert manager.render("greet", {"role": "qa", "name": "Ada", "lang": "en"}).version == version

    (templates_dir / "greet.md").write_text(
        "You are a $role assistant now.\n---USER---\nGreet $name in $lang."
    )
    fresh_manager = PromptManager(templates_dir)  # new instance: no cache
    assert fresh_manager.version_of("greet") != version


def test_templates_are_cached_after_first_load(templates_dir: Path) -> None:
    manager = PromptManager(templates_dir)
    manager.version_of("greet")
    (templates_dir / "greet.md").write_text("changed\n---USER---\nx")
    # Same instance keeps the cached version despite the on-disk edit.
    assert (
        manager.render("greet", {"role": "a", "name": "b", "lang": "c"}).system
        == "You are a a assistant."
    )
