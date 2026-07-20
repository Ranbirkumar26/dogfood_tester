"""ModelManager: every model call in the system goes through here.

Design rationale (design D3): one thin abstraction over the OpenAI wire protocol serves
every provider users realistically run (OpenAI, Ollama, Groq, OpenRouter, vLLM) via
``base_url``. The manager owns the full call pipeline: rate limit -> transport with
taxonomy-mapped retries -> token/cost accounting -> parse and validate -> bounded repair
reprompt. Structured output does not rely on provider-side schema enforcement (support
varies wildly across OpenAI-compatible servers); the schema is stated in the prompt,
json_object mode is requested when configured, and validation plus one repair pass makes
the result trustworthy on any backend. Record/replay (design D13) wraps the transport so
tests and CI never need a key.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from website_agent.config.settings import LlmMode, LlmSettings
from website_agent.core.errors import (
    ConfigError,
    ModelError,
    ModelRateLimitError,
    ModelTransientError,
    OutputParseError,
)
from website_agent.core.retry import LLM_TRANSIENT_POLICY, retry_async
from website_agent.llm.ledger import TokenLedger
from website_agent.llm.rate_limit import AsyncRateLimiter
from website_agent.llm.recorder import CassetteEntry, CassetteStore, request_key
from website_agent.logging import get_logger
from website_agent.prompts.manager import RenderedPrompt

T = TypeVar("T", bound=BaseModel)

log = get_logger("llm.manager")


class ChatTransport(Protocol):
    """The single seam to the provider; tests substitute fakes here."""

    async def create(self, **kwargs: Any) -> Any:  # pragma: no cover - protocol
        ...


class OpenAiTransport:
    """Production transport over the openai SDK against any compatible base_url."""

    def __init__(self, settings: LlmSettings) -> None:
        from openai import AsyncOpenAI

        # Local endpoints (Ollama, vLLM) ignore the key but the SDK requires one;
        # never fall back to the OPENAI_API_KEY env var implicitly.
        key = settings.api_key.get_secret_value() if settings.api_key else "not-needed"
        self._client = AsyncOpenAI(
            base_url=settings.base_url, api_key=key, timeout=settings.request_timeout_s
        )

    async def create(self, **kwargs: Any) -> Any:
        """Forward to chat.completions.create."""
        return await self._client.chat.completions.create(**kwargs)


def map_openai_error(exc: BaseException, *, action: str) -> ModelError:
    """Classify openai SDK exceptions into the failure taxonomy (F3 vs terminal)."""
    import openai

    # Already-classified model errors pass through unchanged so pre-classified failures
    # (and test fakes) keep their taxonomy instead of being flattened to terminal.
    if isinstance(exc, ModelError):
        return exc

    context = {"action": action, "provider_error": type(exc).__name__}
    if isinstance(exc, openai.RateLimitError):
        retry_after = None
        headers = getattr(getattr(exc, "response", None), "headers", None)
        if headers is not None:
            raw = headers.get("retry-after")
            if raw is not None:
                try:
                    retry_after = float(raw)
                except ValueError:
                    retry_after = None
        return ModelRateLimitError("provider rate limit", retry_after=retry_after, context=context)
    if isinstance(exc, openai.APITimeoutError | openai.APIConnectionError):
        return ModelTransientError("provider unreachable or timed out", context=context)
    if isinstance(exc, openai.InternalServerError):
        return ModelTransientError("provider internal error", context=context)
    if isinstance(exc, openai.AuthenticationError):
        return ModelError("authentication failed; check WA_LLM__API_KEY", context=context)
    if isinstance(exc, openai.APIStatusError):
        return ModelError(f"provider rejected the request ({exc.status_code})", context=context)
    return ModelError("unexpected provider error", context=context)


def parse_structured(content: str, schema: type[T]) -> T:
    """Validate model output text against ``schema``.

    Tolerates markdown code fences and leading/trailing prose by slicing the outermost
    JSON object; anything further from valid is a ValidationError for the repair pass.
    """
    text = content.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    return schema.model_validate(json.loads(text))


def _schema_instruction(schema: type[BaseModel]) -> str:
    return (
        "Respond with exactly one JSON object and nothing else. "
        f"It must validate against this JSON schema:\n{json.dumps(schema.model_json_schema())}"
    )


class ModelManager:
    """Provider-agnostic completion API with accounting, retries, and replay."""

    def __init__(
        self,
        settings: LlmSettings,
        ledger: TokenLedger,
        rate_limiter: AsyncRateLimiter,
        *,
        transport: ChatTransport | None = None,
    ) -> None:
        self._settings = settings
        self._ledger = ledger
        self._limiter = rate_limiter
        self._cassettes: CassetteStore | None = None
        if settings.mode is not LlmMode.LIVE:
            if settings.cassette_dir is None:
                raise ConfigError(
                    "cassette_dir is required in record/replay mode",
                    context={"mode": settings.mode},
                )
            self._cassettes = CassetteStore(settings.cassette_dir)
        # Transport built lazily in replay mode: replay must work without the SDK key.
        self._transport = transport
        if self._transport is None and settings.mode is not LlmMode.REPLAY:
            self._transport = OpenAiTransport(settings)

    async def complete(self, role: str, prompt: RenderedPrompt, schema: type[T]) -> T:
        """Structured completion: returns a validated ``schema`` instance.

        Pipeline: replay short-circuit -> rate limit -> transport (retried on F3) ->
        ledger -> parse -> one repair reprompt -> OutputParseError (F4).
        """
        messages = [
            {"role": "system", "content": f"{prompt.system}\n\n{_schema_instruction(schema)}"},
            {"role": "user", "content": prompt.user},
        ]
        key = request_key(role, self._settings.model, messages, schema.__name__)

        if self._settings.mode is LlmMode.REPLAY:
            entry = self._require_cassettes().require(key)
            self._record_usage(role, entry.model, entry.prompt_tokens, entry.completion_tokens)
            return parse_structured(entry.content, schema)

        content, usage = await self._call(role, messages, structured=True)
        try:
            result = parse_structured(content, schema)
        except (ValidationError, json.JSONDecodeError, ValueError) as first_error:
            log.warning("output_parse_failed_repairing", role=role, error=str(first_error)[:200])
            repair_messages = [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "Your previous reply was not a valid JSON object for the schema. "
                        f"Validation error: {str(first_error)[:500]}\n"
                        "Reply again with only the corrected JSON object."
                    ),
                },
            ]
            content, repair_usage = await self._call(role, repair_messages, structured=True)
            usage = (usage[0] + repair_usage[0], usage[1] + repair_usage[1])
            try:
                result = parse_structured(content, schema)
            except (ValidationError, json.JSONDecodeError, ValueError) as second_error:
                raise OutputParseError(
                    "model output failed schema validation after repair",
                    context={"role": role, "schema": schema.__name__},
                ) from second_error

        if self._settings.mode is LlmMode.RECORD:
            self._require_cassettes().save(
                key,
                CassetteEntry(
                    content=content,
                    prompt_tokens=usage[0],
                    completion_tokens=usage[1],
                    model=self._settings.model,
                ),
            )
        return result

    async def complete_text(self, role: str, prompt: RenderedPrompt) -> str:
        """Plain text completion (no schema, no repair)."""
        messages = [
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": prompt.user},
        ]
        key = request_key(role, self._settings.model, messages, None)
        if self._settings.mode is LlmMode.REPLAY:
            entry = self._require_cassettes().require(key)
            self._record_usage(role, entry.model, entry.prompt_tokens, entry.completion_tokens)
            return entry.content

        content, usage = await self._call(role, messages, structured=False)
        if self._settings.mode is LlmMode.RECORD:
            self._require_cassettes().save(
                key,
                CassetteEntry(
                    content=content,
                    prompt_tokens=usage[0],
                    completion_tokens=usage[1],
                    model=self._settings.model,
                ),
            )
        return content

    async def stream_text(self, role: str, prompt: RenderedPrompt) -> AsyncIterator[str]:
        """Streamed text completion, yielding content chunks as they arrive.

        Live and record-mode only; replay raises (streaming is a UX affordance, not a
        correctness path, and replaying it would fake latency behavior).
        Usage is accounted from the final chunk when the provider supplies it.
        """
        if self._settings.mode is LlmMode.REPLAY:
            raise ConfigError("streaming is not available in replay mode")
        await self._limiter.acquire()
        transport = self._require_transport()

        async def start() -> Any:
            try:
                return await transport.create(
                    model=self._settings.model,
                    messages=[
                        {"role": "system", "content": prompt.system},
                        {"role": "user", "content": prompt.user},
                    ],
                    temperature=self._settings.temperature,
                    max_tokens=self._settings.max_output_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                )
            except Exception as exc:
                raise map_openai_error(exc, action=f"stream:{role}") from exc

        stream = await retry_async(
            start, policy=LLM_TRANSIENT_POLICY, retry_on=(ModelTransientError,)
        )
        prompt_tokens = completion_tokens = 0
        async for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                prompt_tokens = usage.prompt_tokens
                completion_tokens = usage.completion_tokens
            choices = getattr(chunk, "choices", None)
            if choices:
                delta = choices[0].delta
                if delta is not None and delta.content:
                    yield delta.content
        self._record_usage(role, self._settings.model, prompt_tokens, completion_tokens)

    async def _call(
        self, role: str, messages: list[dict[str, Any]], *, structured: bool
    ) -> tuple[str, tuple[int, int]]:
        """Rate-limited, retried transport call; returns (content, (prompt, completion))."""
        await self._limiter.acquire()
        transport = self._require_transport()

        request: dict[str, Any] = {
            "model": self._settings.model,
            "messages": messages,
            "temperature": self._settings.temperature,
            "max_tokens": self._settings.max_output_tokens,
        }
        if structured and self._settings.json_mode:
            request["response_format"] = {"type": "json_object"}

        async def attempt() -> Any:
            try:
                return await transport.create(**request)
            except Exception as exc:
                raise map_openai_error(exc, action=f"complete:{role}") from exc

        def on_retry(exc: BaseException, attempt_number: int, delay: float) -> None:
            log.warning(
                "llm_retry",
                role=role,
                attempt=attempt_number,
                delay_s=round(delay, 2),
                reason=str(exc),
            )

        response = await retry_async(
            attempt,
            policy=LLM_TRANSIENT_POLICY,
            retry_on=(ModelTransientError,),
            on_retry=on_retry,
        )

        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        self._record_usage(role, self._settings.model, prompt_tokens, completion_tokens)
        return content, (prompt_tokens, completion_tokens)

    def _record_usage(
        self, role: str, model: str, prompt_tokens: int, completion_tokens: int
    ) -> None:
        entry = self._ledger.record(
            role=role,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        log.info(
            "llm_call_accounted",
            role=role,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=entry.cost_usd,
        )

    def _require_transport(self) -> ChatTransport:
        if self._transport is None:
            raise ConfigError("no transport available (replay mode has no provider client)")
        return self._transport

    def _require_cassettes(self) -> CassetteStore:
        if self._cassettes is None:  # pragma: no cover - guarded by constructor
            raise ConfigError("cassette store not configured")
        return self._cassettes
