"""Logging pipeline configuration: sink selection, JSON shape, end-to-end redaction."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest

from website_agent.config.settings import LogFormat, LoggingSettings
from website_agent.logging.redaction import MASK
from website_agent.logging.setup import configure_logging
from website_agent.logging.structured import ROOT_LOGGER_NAME, bind_run_context, get_logger


@pytest.fixture(autouse=True)
def _reset_logger() -> Iterator[None]:
    yield
    root = logging.getLogger(ROOT_LOGGER_NAME)
    root.handlers.clear()
    root.filters.clear()


def _configure_json_with_buffer(level: str = "INFO") -> io.StringIO:
    # Redirect the configured handler's stream instead of replacing the handler,
    # so the production filter chain (redaction, context) stays under test.
    configure_logging(LoggingSettings(level=level, format=LogFormat.JSON))
    root = logging.getLogger(ROOT_LOGGER_NAME)
    handler = root.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    buffer = io.StringIO()
    handler.setStream(buffer)
    return buffer


def test_json_lines_contain_event_context_and_fields() -> None:
    buffer = _configure_json_with_buffer()
    with bind_run_context(run_id="run_z", step="step_0007"):
        get_logger("executor").info("action_done", action="click", element="e3")

    payload = json.loads(buffer.getvalue().strip())
    assert payload["level"] == "INFO"
    assert payload["component"] == "executor"
    assert payload["event"] == "action_done"
    assert payload["run_id"] == "run_z"
    assert payload["step"] == "step_0007"
    assert payload["fields"] == {"action": "click", "element": "e3"}
    assert "ts" in payload


def test_secrets_never_reach_the_sink() -> None:
    buffer = _configure_json_with_buffer()
    get_logger("llm").info(
        "provider_configured",
        detail="api_key=sk-verysecretkey123456",
        headers={"Authorization": "Bearer abcdefgh12345678"},
    )
    output = buffer.getvalue()
    assert "sk-verysecretkey123456" not in output
    assert "abcdefgh12345678" not in output
    assert MASK in output


def test_level_filtering_applies() -> None:
    buffer = _configure_json_with_buffer(level="WARNING")
    log = get_logger("test")
    log.info("ignored")
    log.warning("kept")
    lines = [json.loads(line) for line in buffer.getvalue().splitlines()]
    assert [entry["event"] for entry in lines] == ["kept"]


def test_rich_format_installs_a_rich_handler() -> None:
    from rich.logging import RichHandler

    configure_logging(LoggingSettings(level="INFO", format=LogFormat.RICH))
    root = logging.getLogger(ROOT_LOGGER_NAME)
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0], RichHandler)
    assert root.propagate is False


def test_reconfiguration_is_idempotent() -> None:
    configure_logging(LoggingSettings(level="INFO", format=LogFormat.JSON))
    configure_logging(LoggingSettings(level="DEBUG", format=LogFormat.JSON))
    root = logging.getLogger(ROOT_LOGGER_NAME)
    assert len(root.handlers) == 1
    assert root.level == logging.DEBUG
    assert len(root.handlers[0].filters) == 2  # redaction + context, not accumulated


def test_json_formatter_survives_unserializable_fields() -> None:
    buffer = _configure_json_with_buffer()
    get_logger("test").info("odd_payload", path=object())
    payload = json.loads(buffer.getvalue().strip())
    assert payload["event"] == "odd_payload"  # fell back to str(), did not raise


def test_json_formatter_includes_exception_repr() -> None:
    buffer = _configure_json_with_buffer()
    log = get_logger("test")
    try:
        raise ValueError("kaboom")
    except ValueError:
        log.error("step_failed", exc_info=True)
    payload = json.loads(buffer.getvalue().strip())
    assert payload["exception"] == "ValueError('kaboom')"


def test_rich_handler_appends_context_and_fields_to_message() -> None:
    from website_agent.logging.setup import RichFieldsHandler

    handler = RichFieldsHandler(markup=False)
    record = logging.LogRecord(
        name="website_agent.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="action_done",
        args=(),
        exc_info=None,
    )
    record.wa_context = {"run_id": "run_q"}
    record.wa_fields = {"element": "e3"}
    rendered = handler.render_message(record, record.getMessage())
    assert "action_done run_id=run_q element=e3" in str(rendered)
