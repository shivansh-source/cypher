"""Client for TypeSafe AI's Jev (a "System One" model), for typed calibrated
decisions rather than chat.

Jev is not chat-shaped: a caller sends a free-text ``state`` plus a batch of
typed questions, and gets back a typed, calibrated answer per question — a
probability-backed classification, not generated prose. That is a different
contract from :class:`ai.llm_client.LLMTransport` (system prompt, message
history, tool-calling loop), so this module defines its own protocol
(:class:`TypedDecisionTransport`) rather than shoehorning Jev into
``LLMTransport``. Nothing in ``ai/chat.py`` or ``ai/intent_classifier.py``
depends on this module, and this module does not implement
``LLMTransport`` — Jev is a separate concern from either of this
codebase's two LLM call sites (repo-root ``CLAUDE.md`` principle 2 covers
narration and intent-routing; this is neither).

Provider is TypeSafe AI's hosted REST API
(``POST https://api.typesafe.ai/v1/systemone``, Bearer auth), called via
``httpx`` directly rather than the ``typesafe-sdk`` PyPI package: that
package is very new (a handful of commits, launched alongside an
early-access/waitlisted API as of September 2026) and the REST contract is
small enough that hand-rolling it keeps this module's dependency surface
identical to what ``ai/groq_transport.py`` already requires (no new
third-party SDK). See ``docs/ASSUMPTIONS.md`` for the sourcing note on the
API contract itself.

As with ``ai/groq_transport.py``, the request/response translation
functions are pure (dicts in, dicts out) so they are unit-tested without a
network call or an API key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx

#: Jev API base endpoint. TypeSafe AI hosts a single System One endpoint
#: across models; which model answers is selected by the `model` field in
#: the request body, not by the URL. Sourced from TypeSafe AI's own API
#: reference (docs.typesafe.ai/api) — see docs/ASSUMPTIONS.md.
JEV_API_URL: str = "https://api.typesafe.ai/v1/systemone"

#: Default Jev model route. Overridable with TYPESAFE_MODEL. "jev-latest"
#: is TypeSafe AI's own early-access alias for their current System One
#: model, per docs.typesafe.ai — not a Su₹aksha-side default we chose
#: independently.
DEFAULT_JEV_MODEL: str = "jev-latest"

#: HTTP request timeout (seconds). Operational transport setting, not a
#: modelling constant — mirrors greenbone_connector.py's
#: _CONNECTION_TIMEOUT_SECONDS in spirit.
_REQUEST_TIMEOUT_SECONDS: float = 30.0

#: This module's `answer_type` vocabulary -> Jev's wire vocabulary for a
#: question. Jev's own type names ("noul" for yes/no, "choice" for enum,
#: "score" for a numeric rating) are TypeSafe AI's, not ours — kept as an
#: explicit translation table here rather than let Jev's vocabulary leak
#: into the rest of this module, matching how ai/groq_transport.py keeps
#: Groq's OpenAI-shaped vocabulary out of ai/chat.py.
_ANSWER_TYPE_TO_JEV_TYPE: dict[str, str] = {"bool": "noul", "enum": "choice", "number": "score"}
_JEV_TYPE_TO_ANSWER_TYPE: dict[str, str] = {v: k for k, v in _ANSWER_TYPE_TO_JEV_TYPE.items()}


class JevConfigurationError(RuntimeError):
    """Raised when Jev is not usable (no API key).

    Mirrors :class:`ai.llm_client.LLMConfigurationError`: callers must
    surface this as an explicit "not configured" state rather than
    degrading into a decision made without Jev.
    """


class JevProviderError(RuntimeError):
    """Raised when Jev was reachable but the call failed or answered unusably.

    Mirrors :class:`ai.llm_client.LLMProviderError`. Covers a non-2xx HTTP
    response, a request timeout, a malformed response body, and a response
    whose ``confidence`` falls outside ``[0, 1]`` — the last of these is
    treated as a provider failure, never silently clamped, since a
    calibrated model returning an uncalibrated number is exactly the kind
    of failure a caller must not act on unknowingly.
    """


@dataclass(frozen=True)
class TypedQuestion:
    """One typed question to ask Jev about a piece of state.

    Attributes:
        id: Stable identifier for this question within one
            :meth:`TypedDecisionTransport.classify` call — echoed back on
            the matching :class:`TypedAnswer`.
        prompt: The question itself, in plain language, describing what to
            decide from the accompanying state.
        answer_type: ``"bool"`` (yes/no), ``"enum"`` (pick one of
            ``enum_options``), or ``"number"`` (a calibrated score).
        enum_options: The allowed answers for ``answer_type="enum"``; must
            be non-empty and only set for that type.
    """

    id: str
    prompt: str
    answer_type: Literal["bool", "enum", "number"]
    enum_options: tuple[str, ...] | None = None


@dataclass(frozen=True)
class TypedAnswer:
    """Jev's typed, calibrated answer to one :class:`TypedQuestion`.

    Attributes:
        question_id: Matches the :class:`TypedQuestion.id` this answers.
        value: ``bool`` for a ``"bool"`` question, ``str`` (one of
            ``enum_options``) for ``"enum"``, ``float`` for ``"number"``.
        confidence: Jev's calibrated confidence in ``value``, in ``[0, 1]``.
            For a bool question this is the probability mass behind the
            predicted class (i.e. ``max(p_true, 1 - p_true)``), not
            ``p_true`` itself — see :func:`_answer_from_jev` for why.

    Must never:
        Be constructed with a ``confidence`` outside ``[0, 1]`` — see
        :class:`JevProviderError`.
    """

    question_id: str
    value: bool | str | float
    confidence: float


class TypedDecisionTransport(Protocol):
    """The Jev-shaped surface callers may depend on.

    A separate protocol from :class:`ai.llm_client.LLMTransport` — see this
    module's docstring for why. Exists so callers (e.g. a future
    ``interfaces/`` orchestration step) can be exercised against a fake in
    tests, the same way ``ai.chat.ChatEngine`` is tested against a fake
    ``LLMTransport``.
    """

    def classify(self, state: str, questions: list[TypedQuestion]) -> list[TypedAnswer]:
        """Ask Jev one or more typed questions about a piece of state.

        Args:
            state: Free-text context describing the situation to decide
                about (e.g. an identity-resolution evidence summary).
            questions: The questions to ask, evaluated against the same
                ``state`` in one call.

        Returns:
            One :class:`TypedAnswer` per question in ``questions``, in the
            same order.
        """
        ...


def _jev_criteria_for_question(question: TypedQuestion) -> dict[str, Any] | list[str]:
    """Build the wire-shaped ``criteria`` object for one question, by type.

    Jev's request schema requires ``criteria`` shaped differently per
    question type (see docs/ASSUMPTIONS.md for the sourced contract):
    ``noul`` wants a true/false description pair, ``choice`` wants one
    entry per allowed option, ``score`` wants a low/high description pair.
    :class:`TypedQuestion` does not carry per-branch description text (its
    shape is fixed by this module's callers), so the descriptions below are
    generic, derived only from the question's own ``prompt`` — a documented
    simplification, not a claim that richer per-branch criteria wouldn't
    improve Jev's calibration.
    """
    if question.answer_type == "bool":
        return {
            "true": f"The following is true: {question.prompt}",
            "false": f"The following is false: {question.prompt}",
        }
    if question.answer_type == "enum":
        if not question.enum_options:
            raise ValueError(f"question {question.id!r}: enum_options must be non-empty")
        return {option: None for option in question.enum_options}
    # "number" -> Jev's "score" type: a low/high description pair. No
    # per-question scale description exists on TypedQuestion, so this is a
    # generic placeholder — see the docstring above.
    return ["Low", "High"]


def _build_request(state: str, questions: list[TypedQuestion], model: str) -> dict[str, Any]:
    """Translate a :func:`TypedDecisionTransport.classify` call into a Jev request body.

    Pure (no I/O), so it is unit-tested without a network call — mirrors
    ``ai.groq_transport.to_groq_messages``/``to_groq_tools``.
    """
    return {
        "state": state,
        "model": model,
        "questions": {
            question.id: {
                "type": _ANSWER_TYPE_TO_JEV_TYPE[question.answer_type],
                "instructions": question.prompt,
                "criteria": _jev_criteria_for_question(question),
            }
            for question in questions
        },
    }


def _answer_from_jev(question: TypedQuestion, raw_answer: dict[str, Any]) -> TypedAnswer:
    """Translate one Jev wire-shaped answer into a :class:`TypedAnswer`.

    Args:
        question: The question this answer responds to (for its
            ``answer_type`` and ``id``).
        raw_answer: The ``answers[question.id]`` object from a Jev response.

    Raises:
        JevProviderError: If a required field for ``question.answer_type``
            is missing, or the resolved confidence is outside ``[0, 1]``.
    """
    jev_type = _ANSWER_TYPE_TO_JEV_TYPE[question.answer_type]
    if raw_answer.get("type") != jev_type:
        raise JevProviderError(
            f"question {question.id!r}: expected answer type {jev_type!r}, "
            f"got {raw_answer.get('type')!r}"
        )

    if question.answer_type == "bool":
        p_true = raw_answer.get("noul")
        if not isinstance(p_true, int | float):
            raise JevProviderError(f"question {question.id!r}: missing/non-numeric 'noul' field")
        value: bool | str | float = p_true >= 0.5
        # Jev reports the probability of "true" for a noul question, not a
        # separate confidence field. This module's TypedAnswer.confidence
        # is "how confident Jev is in the predicted value", i.e. the
        # probability mass behind whichever class was predicted — so a
        # p_true of 0.05 (predicting False) is reported as confidence 0.95,
        # not 0.05. See TypedAnswer's docstring.
        confidence = p_true if value else 1.0 - p_true
    elif question.answer_type == "enum":
        choice = raw_answer.get("choice")
        if not isinstance(choice, str):
            raise JevProviderError(f"question {question.id!r}: missing/non-string 'choice' field")
        value = choice
        confidence_raw = raw_answer.get("confidence")
        if confidence_raw is None:
            probabilities = raw_answer.get("probabilities") or {}
            confidence_raw = probabilities.get(choice)
        if not isinstance(confidence_raw, int | float):
            raise JevProviderError(
                f"question {question.id!r}: missing/non-numeric confidence for choice {choice!r}"
            )
        confidence = float(confidence_raw)
    else:  # "number"
        score = raw_answer.get("score")
        if not isinstance(score, int | float):
            raise JevProviderError(f"question {question.id!r}: missing/non-numeric 'score' field")
        value = float(score)
        confidence_raw = raw_answer.get("confidence")
        if not isinstance(confidence_raw, int | float):
            raise JevProviderError(
                f"question {question.id!r}: missing/non-numeric 'confidence' field"
            )
        confidence = float(confidence_raw)

    if not (0.0 <= confidence <= 1.0):
        raise JevProviderError(
            f"question {question.id!r}: confidence {confidence!r} is outside [0, 1] — "
            "refusing to treat an uncalibrated response as a calibrated one"
        )
    return TypedAnswer(question_id=question.id, value=value, confidence=float(confidence))


def _parse_response(
    response_body: dict[str, Any], questions: list[TypedQuestion]
) -> list[TypedAnswer]:
    """Translate a full Jev response body into ordered :class:`TypedAnswer` objects.

    Pure (no I/O) — mirrors ``ai.groq_transport.from_groq_message``.

    Raises:
        JevProviderError: If ``answers`` is missing, or any question in
            ``questions`` has no matching entry.
    """
    answers = response_body.get("answers")
    if not isinstance(answers, dict):
        raise JevProviderError("Jev response is missing an 'answers' object")
    results: list[TypedAnswer] = []
    for question in questions:
        raw_answer = answers.get(question.id)
        if not isinstance(raw_answer, dict):
            raise JevProviderError(f"Jev response has no answer for question {question.id!r}")
        results.append(_answer_from_jev(question, raw_answer))
    return results


class JevTransport:
    """:class:`TypedDecisionTransport` backed by TypeSafe AI's hosted Jev API.

    Args:
        api_key: TypeSafe AI API key; defaults to ``TYPESAFE_API_KEY``.
        model: Jev model route; defaults to ``TYPESAFE_MODEL``, then
            :data:`DEFAULT_JEV_MODEL`.

    Client construction is lazy, mirroring
    ``ai.groq_transport.GroqTransport._sdk_client``: a missing API key
    raises :class:`JevConfigurationError` at call time, not import time.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get("TYPESAFE_API_KEY")
        self._model = model or os.environ.get("TYPESAFE_MODEL") or DEFAULT_JEV_MODEL
        self._client: httpx.Client | None = None

    @property
    def model(self) -> str:
        """Identifier of the Jev model route this transport will call."""
        return self._model

    def _http_client(self) -> httpx.Client:
        """Build (once) the HTTP client, or explain why we cannot."""
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise JevConfigurationError(
                "TYPESAFE_API_KEY is not set. Jev-based identity resolution cannot "
                "run without it — see .env.example."
            )
        self._client = httpx.Client(
            base_url=JEV_API_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        return self._client

    def classify(self, state: str, questions: list[TypedQuestion]) -> list[TypedAnswer]:
        """Ask Jev one or more typed questions about a piece of state.

        Args:
            state: Free-text context describing the situation to decide
                about.
            questions: The questions to ask; must be non-empty.

        Returns:
            One :class:`TypedAnswer` per question, in ``questions`` order.

        Raises:
            ValueError: If ``questions`` is empty.
            JevConfigurationError: If ``TYPESAFE_API_KEY`` is not set.
            JevProviderError: If the request times out, Jev returns a
                non-2xx response, or the response body cannot be parsed
                into a valid answer for every question (including a
                confidence outside ``[0, 1]``).

        Must never:
            Retry automatically on a 429/529 (rate limited/overloaded)
            response — that decision belongs to the caller, exactly as
            ``infra.connectors`` connectors never retry a failed fetch
            internally; retrying silently here would hide from a caller
            how many real calls were made.
        """
        if not questions:
            raise ValueError("questions must be non-empty")
        client = self._http_client()
        body = _build_request(state, questions, self._model)
        try:
            response = client.post(JEV_API_URL, json=body)
        except httpx.TimeoutException as exc:
            raise JevProviderError(
                f"Jev request timed out after {_REQUEST_TIMEOUT_SECONDS}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise JevProviderError(f"Jev request failed: {exc}") from exc

        if response.status_code >= 400:
            raise JevProviderError(
                f"Jev returned HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            response_body = response.json()
        except ValueError as exc:
            raise JevProviderError(f"Jev response was not valid JSON: {exc}") from exc
        if not isinstance(response_body, dict):
            raise JevProviderError("Jev response body was not a JSON object")

        return _parse_response(response_body, questions)


_default_transport: TypedDecisionTransport | None = None


def get_jev_transport() -> TypedDecisionTransport:
    """Return the process-wide :class:`TypedDecisionTransport`, building it on first use.

    Mirrors ``ai.llm_client.get_transport``: construction never contacts
    the provider, so a missing API key surfaces at call time as
    :class:`JevConfigurationError`, not at import time.
    """
    global _default_transport
    if _default_transport is None:
        _default_transport = JevTransport()
    return _default_transport


def set_jev_transport(transport: TypedDecisionTransport | None) -> None:
    """Replace the process-wide transport (tests).

    Args:
        transport: The transport to use, or None to fall back to a freshly
            built :class:`JevTransport` on next use.
    """
    global _default_transport
    _default_transport = transport
