"""Application settings: one frozen model, five layers of precedence.

Design rationale: precedence is explicit overrides > environment > .env file > TOML config
file > coded defaults. pydantic-settings implements the layering; this module only declares
the shape and wires the source order. The Settings object is frozen after load so no
component can mutate global config mid-run; per-run variation (budgets, goal) belongs to
run state, not settings. Secrets use SecretStr so accidental logging shows a mask.
"""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from website_agent.core.errors import ConfigError


class LogFormat(enum.StrEnum):
    """Console log rendering: rich for humans, json for machines."""

    RICH = "rich"
    JSON = "json"


class LlmSettings(BaseModel):
    """Provider endpoint and default generation parameters (design D3)."""

    model_config = ConfigDict(frozen=True)

    base_url: str = "https://api.openai.com/v1"
    api_key: SecretStr | None = None
    model: str = "gpt-4o-mini"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=4096, ge=1)
    request_timeout_s: float = Field(default=60.0, gt=0)


class BrowserSettings(BaseModel):
    """Playwright session defaults."""

    model_config = ConfigDict(frozen=True)

    headless: bool = True
    action_timeout_ms: int = Field(default=10_000, ge=100)
    nav_timeout_ms: int = Field(default=30_000, ge=1_000)
    viewport_width: int = Field(default=1280, ge=320)
    viewport_height: int = Field(default=900, ge=320)


class BudgetSettings(BaseModel):
    """Default hard stops for a run (design D10); per-run overrides allowed at run creation."""

    model_config = ConfigDict(frozen=True)

    max_steps: int = Field(default=100, ge=1)
    max_tokens: int = Field(default=500_000, ge=1)
    max_usd: float = Field(default=1.0, ge=0.0)
    max_wall_seconds: int = Field(default=1_800, ge=10)
    max_consecutive_failures: int = Field(default=5, ge=1)


class LoggingSettings(BaseModel):
    """Log level and sink format."""

    model_config = ConfigDict(frozen=True)

    level: str = "INFO"
    format: LogFormat = LogFormat.RICH


class PathSettings(BaseModel):
    """Filesystem locations for runtime output."""

    model_config = ConfigDict(frozen=True)

    reports_dir: Path = Path("reports")
    checkpoint_db: Path = Path("reports/checkpoints.sqlite3")


class Settings(BaseSettings):
    """Root settings. Load via :func:`load_settings`, never by direct construction,
    so the layering order stays uniform across CLI, API, and tests."""

    model_config = SettingsConfigDict(
        frozen=True,
        env_prefix="WA_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Optional TOML config file; class-level because pydantic-settings sources are
    # constructed before instance fields exist. Set by load_settings.
    _toml_file: ClassVar[Path | None] = None

    llm: LlmSettings = LlmSettings()
    browser: BrowserSettings = BrowserSettings()
    budgets: BudgetSettings = BudgetSettings()
    logging: LoggingSettings = LoggingSettings()
    paths: PathSettings = PathSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Source order = precedence order (first wins): init > env > .env > TOML."""
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
        ]
        if cls._toml_file is not None:
            sources.append(TomlConfigSettingsSource(settings_cls, toml_file=cls._toml_file))
        return tuple(sources)


def load_settings(config_file: Path | None = None, **overrides: Any) -> Settings:
    """Build the frozen Settings object.

    Args:
        config_file: optional TOML file layered below environment variables.
        overrides: highest-precedence values (nested dicts per section), used by
            CLI flags and tests.

    Raises:
        ConfigError: missing config file or validation failure, with the offending
            location in context.
    """
    if config_file is not None and not config_file.is_file():
        raise ConfigError("config file not found", context={"path": str(config_file)})

    Settings._toml_file = config_file
    try:
        return Settings(**overrides)
    except ValueError as exc:
        raise ConfigError("invalid configuration", context={"detail": str(exc)}) from exc
    finally:
        Settings._toml_file = None
