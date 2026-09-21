"""Thin client wrapping whichever LLM provider is configured, plus the
narration path.

This is the second (and last) place an LLM is invoked in this codebase,
alongside ``ai/intent_classifier.py``. Any text produced here that will be
shown to a user must be passed through ``ai/numeric_guard.py`` before
display — this module does not do that itself; callers are responsible for
calling the guard.

The provider is chosen by ``LLM_PROVIDER`` (``groq``, the default, or
``anthropic``). Every request goes through an :class:`LLMTransport`, so that
``ai/chat.py`` and ``ai/intent_classifier.py`` are provider-agnostic and can
be exercised in tests without a network call or an API key. Conversations
cross the transport boundary in the Messages API shape whichever provider
answers; ``ai/groq_transport.py`` translates to and from Groq's
OpenAI-shaped API. Each provider SDK is imported lazily inside its own
transport, so this module stays importable in an environment where either
SDK is missing.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

#: Provider used when LLM_PROVIDER is unset.
DEFAULT_PROVIDER = "groq"

#: Default Anthropic model, used only when LLM_PROVIDER=anthropic. Overridable with
#: the ANTHROPIC_MODEL environment variable (see .env.example). This is an
#: infrastructure/config choice, not a modelling constant — it has no
#: bearing on any rupee figure, which is why it does not live in
#: ``core/assumptions.py``.
DEFAULT_MODEL = "claude-opus-5"

#: Output token ceiling for non-streaming requests. Kept below the SDK's
#: default HTTP timeout budget; streamed requests use the larger ceiling
#: below because they are not subject to that timeout.
DEFAULT_MAX_TOKENS = 16_000
DEFAULT_STREAM_MAX_TOKENS = 64_000

#: Reasoning effort passed as ``output_config.effort``. "medium" suits an
#: interactive chat turn whose hard work (the risk computation) happens in
#: ``core/``, not in the model.
DEFAULT_EFFORT = "medium"


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM provider is not usable (no API key, no SDK installed).

    Callers in ``interfaces/`` must surface this as an explicit "the
    assistant is not configured" state rather than degrading into an
    answer produced without a model.
    """


class LLMProviderError(RuntimeError):
    """Raised when the provider was reachable but the call failed.

    Wraps the provider's own exception so that no caller outside this
    module has to import the provider SDK to handle an error.
    """


@dataclass(frozen=True)
class LLMResponse:
    """Raw response from the configured LLM provider.

    Attributes:
        text: The generated text, not yet passed through
            ``ai.numeric_guard``.
        model: Identifier of the model that produced this response, for
            logging/auditability.
        raw_provider_response: The unmodified provider response object,
            kept for debugging only — must never be parsed by any caller
            outside this module.
    """

    text: str
    model: str
    raw_provider_response: Any


@dataclass(frozen=True)
class StreamChunk:
    """One item from :meth:`LLMTransport.stream_message`.

    Attributes:
        kind: ``"text_delta"`` for an incremental piece of assistant text,
            ``"final_message"`` for the single terminating chunk carrying
            the fully accumulated provider message.
        text: The incremental text, for ``kind="text_delta"``; empty
            otherwise.
        message: The accumulated provider message as a JSON-shaped dict,
            for ``kind="final_message"``; None otherwise.

    Must never:
        Be yielded with ``kind="final_message"`` more than once per
        stream, or with any chunk following it — consumers treat it as the
        end of the turn.
    """

    kind: Literal["text_delta", "final_message"]
    text: str = ""
    message: dict[str, Any] | None = None


class LLMTransport(Protocol):
    """The provider surface the rest of ``ai/`` is allowed to depend on.

    Messages, tool definitions and tool results cross this boundary as
    plain JSON-shaped dicts (the Messages API wire shape), deliberately:
    it keeps ``ai/chat.py`` testable against a fake and keeps the provider
    SDK's types from leaking into modules that must not depend on them.
    """

    @property
    def model(self) -> str:
        """Identifier of the model this transport will call."""

    def create_message(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Send one non-streaming request and return the provider message as a dict."""

    def stream_message(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[StreamChunk]:
        """Send one streaming request, yielding text deltas then one final message."""


class AnthropicTransport:
    """:class:`LLMTransport` backed by Anthropic's Messages API.

    Args:
        api_key: Provider API key; defaults to ``ANTHROPIC_API_KEY``.
        model: Model identifier; defaults to ``ANTHROPIC_MODEL``, then
            :data:`DEFAULT_MODEL`.
        thinking: Whether to enable adaptive extended thinking. Defaults
            to ``ANTHROPIC_THINKING`` (``"off"`` disables it) — a model
            that does not support adaptive thinking (e.g. Haiku) needs it
            disabled.
        effort: ``output_config.effort``; defaults to ``ANTHROPIC_EFFORT``,
            then :data:`DEFAULT_EFFORT`.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        thinking: bool | None = None,
        effort: str | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY")
        self._model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
        self._thinking = (
            thinking
            if thinking is not None
            else os.environ.get("ANTHROPIC_THINKING", "adaptive").lower() != "off"
        )
        self._effort = effort or os.environ.get("ANTHROPIC_EFFORT") or DEFAULT_EFFORT
        self._client: Any | None = None

    @property
    def model(self) -> str:
        return self._model

    def _sdk_client(self) -> Any:
        """Build (once) the provider client, or explain why we cannot."""
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on install state
            raise LLMConfigurationError(
                "The 'anthropic' package is not installed. Install the backend "
                "dependencies (pip install -e '.[dev]') to enable the chat assistant."
            ) from exc
        if not self._api_key:
            raise LLMConfigurationError(
                "ANTHROPIC_API_KEY is not set. The chat assistant cannot answer "
                "without it — see .env.example."
            )
        self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def _request_kwargs(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None,
        max_tokens: int,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            # The system prompt is frozen for the life of the process, so it
            # sits ahead of everything volatile and caches cleanly.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": list(messages),
            "output_config": {"effort": self._effort},
        }
        if self._thinking:
            kwargs["thinking"] = {"type": "adaptive"}
        if tools:
            kwargs["tools"] = list(tools)
        return kwargs

    def create_message(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        client = self._sdk_client()
        kwargs = self._request_kwargs(
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens or DEFAULT_MAX_TOKENS,
        )
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        try:
            response = client.messages.create(**kwargs)
        except Exception as exc:  # re-raised as one of this module's error types
            raise _as_provider_error(exc) from exc
        dumped: dict[str, Any] = response.model_dump(mode="json", exclude_none=True)
        return dumped

    def stream_message(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[StreamChunk]:
        client = self._sdk_client()
        kwargs = self._request_kwargs(
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens or DEFAULT_STREAM_MAX_TOKENS,
        )
        try:
            with client.messages.stream(**kwargs) as stream:
                for event in stream:
                    if event.type == "text":
                        yield StreamChunk(kind="text_delta", text=event.text)
                final = stream.get_final_message()
        except Exception as exc:  # re-raised as one of this module's error types
            raise _as_provider_error(exc) from exc
        yield StreamChunk(
            kind="final_message",
            message=final.model_dump(mode="json", exclude_none=True),
        )


def _as_provider_error(exc: Exception) -> Exception:
    """Translate a provider exception into one of this module's error types."""
    if isinstance(exc, LLMConfigurationError | LLMProviderError):
        return exc
    return LLMProviderError(f"{type(exc).__name__}: {exc}")


_default_transport: LLMTransport | None = None


def get_transport() -> LLMTransport:
    """Return the process-wide :class:`LLMTransport`, building it on first use.

    Returns:
        The configured transport. Construction never contacts the provider,
        so a missing API key surfaces at call time as
        :class:`LLMConfigurationError`, not at import time.
    """
    global _default_transport
    if _default_transport is None:
        _default_transport = build_transport(os.environ.get("LLM_PROVIDER", DEFAULT_PROVIDER))
    return _default_transport


def build_transport(provider: str) -> LLMTransport:
    """Build the transport for a named provider.

    Args:
        provider: ``"groq"`` or ``"anthropic"`` (case-insensitive).

    Returns:
        An unconnected transport; nothing contacts the provider until a
        request is made.

    Raises:
        LLMConfigurationError: If ``provider`` is not one this codebase
            supports.
    """
    name = provider.strip().lower()
    if name == "groq":
        from ai.groq_transport import GroqTransport

        return GroqTransport()
    if name == "anthropic":
        return AnthropicTransport()
    raise LLMConfigurationError(
        f"Unknown LLM_PROVIDER '{provider}'. Supported providers: groq, anthropic."
    )


def set_transport(transport: LLMTransport | None) -> None:
    """Replace the process-wide transport (tests, or an alternate provider).

    Args:
        transport: The transport to use, or None to fall back to a freshly
            built :class:`AnthropicTransport` on next use.
    """
    global _default_transport
    _default_transport = transport


def message_text(message: dict[str, Any]) -> str:
    """Concatenate the text blocks of a provider message.

    Args:
        message: A provider message dict (as returned by
            :meth:`LLMTransport.create_message`).

    Returns:
        Every ``text`` content block joined in order. Thinking blocks are
        excluded — they are reasoning, not an answer, and must never be
        shown to a user as one.
    """
    parts: list[str] = []
    for block in message.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def narrate_risk_figure(
    risk_figure: dict[str, Any], user_context: str | None = None
) -> LLMResponse:
    """Generate prose narrating an already-computed risk figure.

    Args:
        risk_figure: A serialized ``core.engine.RiskFigure`` (or
            ``core.optimizer.PortfolioRecommendation``) — every number the
            narration may reference must appear here already computed.
        user_context: Optional free text describing what the user asked,
            used only to shape tone/framing, never to recompute or
            reinterpret any figure.

    Returns:
        An :class:`LLMResponse` whose ``text`` still requires verification
        via ``ai.numeric_guard.guard_narration`` before being shown to a
        user — this function does not call the guard itself.

    Must never:
        Ask the LLM to estimate, adjust, round in a way that changes the
        value, or fill in any number not already present in
        ``risk_figure``. See repo-root ``CLAUDE.md`` principles 1 and 2.
    """
    transport = get_transport()
    prompt_parts = [
        (
            "Narrate the following already-computed risk figure for a security "
            "leader. Every number you write must appear verbatim in the JSON "
            "below. Do not compute, estimate, adjust, extrapolate or round any "
            "value, and do not introduce a number that is not in the JSON. If "
            "something the reader would want is not in the JSON, say it was not "
            "computed rather than supplying a figure."
        ),
        "",
        "FIGURE (JSON):",
        json.dumps(risk_figure, indent=2, sort_keys=True, default=str),
    ]
    if user_context:
        prompt_parts += ["", "The user asked:", user_context]
    message = transport.create_message(
        system=NARRATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "\n".join(prompt_parts)}],
    )
    return LLMResponse(
        text=message_text(message),
        model=str(message.get("model", transport.model)),
        raw_provider_response=message,
    )


def complete(prompt: str, **kwargs: Any) -> LLMResponse:
    """Low-level passthrough to the configured LLM provider.

    Args:
        prompt: The full prompt to send.
        **kwargs: Provider-specific generation parameters (``system``,
            ``max_tokens``).

    Returns:
        An :class:`LLMResponse`.

    Must never:
        Be called directly by anything outside ``ai/`` — all other
        packages must go through a purpose-specific function
        (:func:`narrate_risk_figure`, ``ai.chat.ChatEngine``, or a
        classifier in ``ai/intent_classifier.py``) so that every LLM call
        site has a clearly bounded contract.
    """
    transport = get_transport()
    system = str(kwargs.pop("system", NARRATION_SYSTEM_PROMPT))
    max_tokens = kwargs.pop("max_tokens", None)
    message = transport.create_message(
        system=system,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    return LLMResponse(
        text=message_text(message),
        model=str(message.get("model", transport.model)),
        raw_provider_response=message,
    )


#: System prompt for the narration path. The chat assistant has its own,
#: larger prompt in ``ai/chat.py``; both encode the same prohibition.
NARRATION_SYSTEM_PROMPT = (
    "You narrate cyber-risk figures that have already been computed by a "
    "deterministic Open FAIR + Monte Carlo engine. You never compute, "
    "estimate or adjust a figure yourself, and every number in your prose "
    "must appear verbatim in the data you were given. A separate verifier "
    "checks every number you write against real engine output and flags any "
    "it cannot match, so inventing or rounding a figure does not help the "
    "reader — it just gets flagged. When the data does not contain something "
    "the reader would want, say plainly that it was not computed."
)
