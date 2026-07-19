"""Settings layering: defaults, TOML file, environment, explicit overrides."""

from __future__ import annotations

from pathlib import Path

import pytest

from website_agent.config.settings import LogFormat, Settings, load_settings
from website_agent.core.errors import ConfigError


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # load_settings reads ./.env; run each test in an empty directory so a developer's
    # local .env can never influence assertions.
    monkeypatch.chdir(tmp_path)


def test_defaults_load_without_any_sources() -> None:
    settings = load_settings()
    assert settings.llm.base_url == "https://api.openai.com/v1"
    assert settings.llm.api_key is None
    assert settings.browser.headless is True
    assert settings.budgets.max_steps == 100
    assert settings.logging.format is LogFormat.RICH
    assert settings.paths.reports_dir == Path("reports")


def test_env_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WA_LLM__MODEL", "llama3.1:8b")
    monkeypatch.setenv("WA_LLM__BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("WA_BUDGETS__MAX_USD", "0.0")
    monkeypatch.setenv("WA_LOGGING__FORMAT", "json")
    settings = load_settings()
    assert settings.llm.model == "llama3.1:8b"
    assert settings.llm.base_url == "http://localhost:11434/v1"
    assert settings.budgets.max_usd == 0.0
    assert settings.logging.format is LogFormat.JSON


def test_toml_file_overrides_defaults(tmp_path: Path) -> None:
    config = tmp_path / "wa.toml"
    config.write_text('[llm]\nmodel = "from-toml"\n\n[budgets]\nmax_steps = 7\n')
    settings = load_settings(config_file=config)
    assert settings.llm.model == "from-toml"
    assert settings.budgets.max_steps == 7
    assert settings.browser.headless is True  # untouched sections keep defaults


def test_env_beats_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "wa.toml"
    config.write_text('[llm]\nmodel = "from-toml"\n')
    monkeypatch.setenv("WA_LLM__MODEL", "from-env")
    assert load_settings(config_file=config).llm.model == "from-env"


def test_dotenv_beats_toml_and_env_beats_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "wa.toml").write_text('[llm]\nmodel = "from-toml"\n')
    (tmp_path / ".env").write_text("WA_LLM__MODEL=from-dotenv\nWA_LLM__TEMPERATURE=0.5\n")
    settings = load_settings(config_file=tmp_path / "wa.toml")
    assert settings.llm.model == "from-dotenv"
    assert settings.llm.temperature == 0.5

    monkeypatch.setenv("WA_LLM__MODEL", "from-env")
    assert load_settings(config_file=tmp_path / "wa.toml").llm.model == "from-env"


def test_explicit_overrides_beat_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WA_LLM__MODEL", "from-env")
    settings = load_settings(llm={"model": "from-override"})
    assert settings.llm.model == "from-override"


def test_settings_are_frozen() -> None:
    settings = load_settings()
    with pytest.raises(Exception, match="frozen"):
        settings.llm = settings.llm  # type: ignore[misc]


def test_api_key_is_masked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WA_LLM__API_KEY", "sk-super-secret-value-123456")
    settings = load_settings()
    assert settings.llm.api_key is not None
    blob = repr(settings) + repr(settings.llm)
    assert "sk-super-secret-value-123456" not in blob
    assert settings.llm.api_key.get_secret_value() == "sk-super-secret-value-123456"


def test_missing_config_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="config file not found"):
        load_settings(config_file=tmp_path / "absent.toml")


def test_invalid_values_raise_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WA_BUDGETS__MAX_STEPS", "0")
    with pytest.raises(ConfigError, match="invalid configuration"):
        load_settings()


def test_toml_source_state_resets_after_load(tmp_path: Path) -> None:
    config = tmp_path / "wa.toml"
    config.write_text('[llm]\nmodel = "from-toml"\n')
    load_settings(config_file=config)
    # Class-level source wiring must not leak into subsequent plain loads.
    assert Settings._toml_file is None
    assert load_settings().llm.model == "gpt-4o-mini"
