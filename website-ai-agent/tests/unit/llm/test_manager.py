"""ModelManager: structured output, repair, record/replay, retries, streaming, parsing."""

from __future__ import annotations

from pathlib import Path

import openai
import pytest
from pydantic import BaseModel
from tests.unit.llm._fakes import FakeTransport, response

from website_agent.config.settings import LlmMode, LlmSettings
from website_agent.core.clock import FixedClock
from website_agent.core.errors import (
    ConfigError,
    ModelError,
    ModelRateLimitError,
    ModelTransientError,
    OutputParseError,
)
from website_agent.llm.ledger import TokenLedger
from website_agent.llm.manager import ModelManager, map_openai_error, parse_structured
from website_agent.llm.pricing import PriceTable
from website_agent.llm.rate_limit import AsyncRateLimiter
from website_agent.prompts.manager import RenderedPrompt


class Plan(BaseModel):
    goal: str
    steps: int


def _prompt() -> RenderedPrompt:
    return RenderedPrompt(name="planner", version="v1", system="You plan.", user="Plan the site.")


def _manager(
    transport: FakeTransport | None,
    clock: FixedClock,
    *,
    mode: LlmMode = LlmMode.LIVE,
    cassette_dir: Path | None = None,
    rpm: int = 0,
) -> tuple[ModelManager, TokenLedger]:
    settings = LlmSettings(model="m", mode=mode, cassette_dir=cassette_dir, requests_per_minute=rpm)
    ledger = TokenLedger(PriceTable({"m": (1.0, 2.0)}), clock)
    limiter = AsyncRateLimiter(rpm, clock)
    manager = ModelManager(settings, ledger, limiter, transport=transport)
    return manager, ledger


# --------------------------------------------------------------- parse_structured


def test_parse_structured_plain_json() -> None:
    result = parse_structured('{"goal": "explore", "steps": 3}', Plan)
    assert result == Plan(goal="explore", steps=3)


def test_parse_structured_strips_code_fences() -> None:
    fenced = '```json\n{"goal": "explore", "steps": 3}\n```'
    assert parse_structured(fenced, Plan).goal == "explore"


def test_parse_structured_slices_surrounding_prose() -> None:
    noisy = 'Sure! Here is the plan: {"goal": "explore", "steps": 3} Hope that helps.'
    assert parse_structured(noisy, Plan).steps == 3


# ------------------------------------------------------------------ structured


async def test_complete_returns_validated_model(fixed_clock: FixedClock) -> None:
    transport = FakeTransport([response('{"goal": "explore", "steps": 2}', 100, 20)])
    manager, ledger = _manager(transport, fixed_clock)
    result = await manager.complete("planner", _prompt(), Plan)
    assert result == Plan(goal="explore", steps=2)
    assert ledger.totals().calls == 1
    assert ledger.totals().prompt_tokens == 100
    # json_object response_format requested when json_mode on (default).
    assert transport.calls[0]["response_format"] == {"type": "json_object"}


async def test_complete_repairs_invalid_output_once(fixed_clock: FixedClock) -> None:
    transport = FakeTransport(
        [
            response("not json at all", 100, 5),
            response('{"goal": "explore", "steps": 1}', 40, 8),
        ]
    )
    manager, ledger = _manager(transport, fixed_clock)
    result = await manager.complete("planner", _prompt(), Plan)
    assert result.steps == 1
    assert ledger.totals().calls == 2  # original + repair both accounted
    assert len(transport.calls) == 2
    # Repair call includes the assistant's bad reply and a correction instruction.
    repair_messages = transport.calls[1]["messages"]
    assert any(m["role"] == "assistant" for m in repair_messages)


async def test_complete_raises_parse_error_after_failed_repair(fixed_clock: FixedClock) -> None:
    transport = FakeTransport([response("garbage", 10, 2), response("still garbage", 10, 2)])
    manager, _ = _manager(transport, fixed_clock)
    with pytest.raises(OutputParseError, match="after repair") as excinfo:
        await manager.complete("planner", _prompt(), Plan)
    assert excinfo.value.context["schema"] == "Plan"


async def test_schema_violation_triggers_repair(fixed_clock: FixedClock) -> None:
    # Valid JSON, wrong shape (steps missing) -> repair.
    transport = FakeTransport(
        [response('{"goal": "x"}', 10, 2), response('{"goal": "x", "steps": 0}', 10, 2)]
    )
    manager, ledger = _manager(transport, fixed_clock)
    result = await manager.complete("planner", _prompt(), Plan)
    assert result.steps == 0
    assert ledger.totals().calls == 2


# ------------------------------------------------------------------- retries


async def test_transient_error_is_retried_then_succeeds(fixed_clock: FixedClock) -> None:
    err = ModelTransientError("503")
    transport = FakeTransport([err, response('{"goal": "ok", "steps": 1}', 10, 2)])
    manager, ledger = _manager(transport, fixed_clock)
    result = await manager.complete("planner", _prompt(), Plan)
    assert result.goal == "ok"
    assert ledger.totals().calls == 1  # only the successful call is accounted


async def test_non_transient_error_propagates(fixed_clock: FixedClock) -> None:
    transport = FakeTransport([ModelError("bad request")])
    manager, _ = _manager(transport, fixed_clock)
    with pytest.raises(ModelError, match="bad request"):
        await manager.complete("planner", _prompt(), Plan)


# ------------------------------------------------------------ record / replay


async def test_record_then_replay_round_trip(fixed_clock: FixedClock, tmp_path: Path) -> None:
    # Record: real transport produces output, cassette saved.
    transport = FakeTransport([response('{"goal": "recorded", "steps": 4}', 100, 20)])
    rec_manager, _ = _manager(transport, fixed_clock, mode=LlmMode.RECORD, cassette_dir=tmp_path)
    await rec_manager.complete("planner", _prompt(), Plan)

    # Replay: no transport at all, same result, usage restored.
    replay_manager, ledger = _manager(None, fixed_clock, mode=LlmMode.REPLAY, cassette_dir=tmp_path)
    result = await replay_manager.complete("planner", _prompt(), Plan)
    assert result == Plan(goal="recorded", steps=4)
    assert ledger.totals().prompt_tokens == 100
    assert ledger.totals().completion_tokens == 20


async def test_replay_miss_raises(fixed_clock: FixedClock, tmp_path: Path) -> None:
    from website_agent.core.errors import StateError

    manager, _ = _manager(None, fixed_clock, mode=LlmMode.REPLAY, cassette_dir=tmp_path)
    with pytest.raises(StateError, match="cassette replay miss"):
        await manager.complete("planner", _prompt(), Plan)


def test_record_mode_requires_cassette_dir(fixed_clock: FixedClock) -> None:
    settings = LlmSettings(model="m", mode=LlmMode.RECORD, cassette_dir=None)
    ledger = TokenLedger(PriceTable(), fixed_clock)
    with pytest.raises(ConfigError, match="cassette_dir is required"):
        ModelManager(settings, ledger, AsyncRateLimiter(0, fixed_clock))


# --------------------------------------------------------------------- text


async def test_complete_text_returns_content(fixed_clock: FixedClock) -> None:
    transport = FakeTransport([response("plain answer", 5, 3)])
    manager, ledger = _manager(transport, fixed_clock)
    text = await manager.complete_text("docs", _prompt())
    assert text == "plain answer"
    assert ledger.totals().calls == 1
    assert "response_format" not in transport.calls[0]  # no json mode for plain text


# ------------------------------------------------------------------ streaming


async def test_stream_text_yields_chunks_and_accounts_usage(fixed_clock: FixedClock) -> None:
    from types import SimpleNamespace

    def _chunk(content: str | None, usage: object = None) -> SimpleNamespace:
        delta = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=usage)

    class StreamingTransport:
        calls: list[dict] = []

        async def create(self, **kwargs: object):  # type: ignore[no-untyped-def]
            assert kwargs["stream"] is True

            async def gen():  # type: ignore[no-untyped-def]
                yield _chunk("Hello")
                yield _chunk(" world")
                yield _chunk(None, usage=SimpleNamespace(prompt_tokens=7, completion_tokens=2))

            return gen()

    settings = LlmSettings(model="m", requests_per_minute=0)
    ledger = TokenLedger(PriceTable({"m": (1.0, 2.0)}), fixed_clock)
    manager = ModelManager(
        settings, ledger, AsyncRateLimiter(0, fixed_clock), transport=StreamingTransport()
    )

    chunks = [chunk async for chunk in manager.stream_text("docs", _prompt())]
    assert "".join(chunks) == "Hello world"
    assert ledger.totals().prompt_tokens == 7
    assert ledger.totals().completion_tokens == 2


async def test_stream_text_unavailable_in_replay(fixed_clock: FixedClock, tmp_path: Path) -> None:
    manager, _ = _manager(None, fixed_clock, mode=LlmMode.REPLAY, cassette_dir=tmp_path)
    with pytest.raises(ConfigError, match="not available in replay"):
        async for _ in manager.stream_text("docs", _prompt()):
            pass


# ------------------------------------------------------------- error mapping


def test_map_rate_limit_error_extracts_retry_after() -> None:
    from types import SimpleNamespace

    exc = openai.RateLimitError.__new__(openai.RateLimitError)
    exc.response = SimpleNamespace(headers={"retry-after": "12"})  # type: ignore[attr-defined]
    mapped = map_openai_error(exc, action="complete:planner")
    assert isinstance(mapped, ModelRateLimitError)
    assert mapped.retry_after == 12.0


def test_map_timeout_and_server_errors_are_transient() -> None:
    timeout = openai.APITimeoutError.__new__(openai.APITimeoutError)
    server = openai.InternalServerError.__new__(openai.InternalServerError)
    assert isinstance(map_openai_error(timeout, action="x"), ModelTransientError)
    assert isinstance(map_openai_error(server, action="x"), ModelTransientError)


def test_map_auth_error_is_terminal() -> None:
    auth = openai.AuthenticationError.__new__(openai.AuthenticationError)
    mapped = map_openai_error(auth, action="x")
    assert isinstance(mapped, ModelError)
    assert not isinstance(mapped, ModelTransientError)


def test_map_unknown_error_is_terminal_model_error() -> None:
    mapped = map_openai_error(RuntimeError("weird"), action="x")
    assert isinstance(mapped, ModelError)
    assert mapped.context["provider_error"] == "RuntimeError"


# ------------------------------------------------------ transport construction


def test_openai_transport_builds_client_without_network() -> None:
    from website_agent.llm.manager import OpenAiTransport

    # Local endpoint, no key: constructing the transport must not require credentials
    # or make a network call.
    transport = OpenAiTransport(
        LlmSettings(base_url="http://localhost:11434/v1", api_key=None, model="llama3.1")
    )
    assert transport._client.base_url is not None


# ----------------------------------------------------------- text record/replay


async def test_complete_text_record_then_replay(fixed_clock: FixedClock, tmp_path: Path) -> None:
    transport = FakeTransport([response("recorded text", 6, 4)])
    rec, _ = _manager(transport, fixed_clock, mode=LlmMode.RECORD, cassette_dir=tmp_path)
    assert await rec.complete_text("docs", _prompt()) == "recorded text"

    replay, ledger = _manager(None, fixed_clock, mode=LlmMode.REPLAY, cassette_dir=tmp_path)
    assert await replay.complete_text("docs", _prompt()) == "recorded text"
    assert ledger.totals().prompt_tokens == 6


# -------------------------------------------------------------- usage handling


async def test_missing_usage_accounts_zero(fixed_clock: FixedClock) -> None:
    from types import SimpleNamespace

    class NoUsageTransport:
        async def create(self, **kwargs: object):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content='{"goal": "g", "steps": 1}'))
                ],
                usage=None,
            )

    settings = LlmSettings(model="m")
    ledger = TokenLedger(PriceTable({"m": (1.0, 2.0)}), fixed_clock)
    manager = ModelManager(
        settings, ledger, AsyncRateLimiter(0, fixed_clock), transport=NoUsageTransport()
    )
    await manager.complete("planner", _prompt(), Plan)
    assert ledger.totals().prompt_tokens == 0
    assert ledger.totals().cost_usd == 0.0


async def test_stream_retries_transient_start_error(fixed_clock: FixedClock) -> None:
    from types import SimpleNamespace

    class FlakyStream:
        def __init__(self) -> None:
            self.attempts = 0

        async def create(self, **kwargs: object):  # type: ignore[no-untyped-def]
            self.attempts += 1
            if self.attempts == 1:
                raise ModelTransientError("stream 503")

            async def gen():  # type: ignore[no-untyped-def]
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="hi"))], usage=None
                )
                yield SimpleNamespace(
                    choices=[], usage=SimpleNamespace(prompt_tokens=3, completion_tokens=1)
                )

            return gen()

    settings = LlmSettings(model="m")
    ledger = TokenLedger(PriceTable({"m": (1.0, 2.0)}), fixed_clock)
    manager = ModelManager(
        settings, ledger, AsyncRateLimiter(0, fixed_clock), transport=FlakyStream()
    )
    chunks = [c async for c in manager.stream_text("docs", _prompt())]
    assert "".join(chunks) == "hi"
    assert ledger.totals().completion_tokens == 1
