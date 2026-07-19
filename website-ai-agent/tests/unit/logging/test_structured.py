"""Structured logger and correlation context: field transport, binding, nesting."""

from __future__ import annotations

import logging

import pytest

from website_agent.logging.structured import (
    ROOT_LOGGER_NAME,
    bind_run_context,
    current_run_context,
    get_logger,
)


@pytest.fixture
def captured(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG, logger=ROOT_LOGGER_NAME)
    return caplog


def test_events_carry_component_and_fields(captured: pytest.LogCaptureFixture) -> None:
    log = get_logger("browser.session")
    log.info("page_loaded", url="https://example.com", elapsed_ms=120)

    record = captured.records[-1]
    assert record.getMessage() == "page_loaded"
    assert record.wa_component == "browser.session"
    assert record.wa_fields == {"url": "https://example.com", "elapsed_ms": 120}
    assert record.name == f"{ROOT_LOGGER_NAME}.browser.session"


def test_levels_map_to_stdlib_levels(captured: pytest.LogCaptureFixture) -> None:
    log = get_logger("test")
    log.debug("d")
    log.info("i")
    log.warning("w")
    log.error("e")
    assert [r.levelno for r in captured.records[-4:]] == [
        logging.DEBUG,
        logging.INFO,
        logging.WARNING,
        logging.ERROR,
    ]


def test_error_attaches_exception_info(captured: pytest.LogCaptureFixture) -> None:
    log = get_logger("test")
    try:
        raise ValueError("boom")
    except ValueError:
        log.error("step_failed", exc_info=True, step="step_0001")
    record = captured.records[-1]
    assert record.exc_info is not None
    assert record.exc_info[0] is ValueError


def test_context_binding_and_nesting() -> None:
    assert current_run_context() == {}
    with bind_run_context(run_id="run_x"):
        assert current_run_context() == {"run_id": "run_x"}
        with bind_run_context(step="step_0002"):
            assert current_run_context() == {"run_id": "run_x", "step": "step_0002"}
        assert current_run_context() == {"run_id": "run_x"}
    assert current_run_context() == {}


def test_context_restored_even_on_exception() -> None:
    with pytest.raises(RuntimeError), bind_run_context(run_id="run_y"):
        raise RuntimeError("mid-run crash")
    assert current_run_context() == {}
