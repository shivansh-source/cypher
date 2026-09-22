"""Tests for ai/jev_transport.py.

No network and no API key: the translation functions are pure, and
JevTransport is driven through a mocked httpx.Client.post — same philosophy
as ai/tests/test_groq_transport.py's fake Groq client.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from ai.jev_transport import (
    JevConfigurationError,
    JevProviderError,
    JevTransport,
    TypedAnswer,
    TypedQuestion,
    _build_request,
    _parse_response,
    get_jev_transport,
    set_jev_transport,
)

_BOOL_QUESTION = TypedQuestion(
    id="same_asset", prompt="Are these the same real-world asset?", answer_type="bool"
)
_ENUM_QUESTION = TypedQuestion(
    id="team",
    prompt="Which team owns this?",
    answer_type="enum",
    enum_options=("billing", "infra"),
)
_NUMBER_QUESTION = TypedQuestion(id="severity", prompt="How severe is this?", answer_type="number")


def teardown_function() -> None:
    set_jev_transport(None)


# --- pure translation functions --------------------------------------------


def test_build_request_bool_question_shape() -> None:
    request = _build_request("some evidence", [_BOOL_QUESTION], "jev-latest")
    assert request["state"] == "some evidence"
    assert request["model"] == "jev-latest"
    question = request["questions"]["same_asset"]
    assert question["type"] == "noul"
    assert question["instructions"] == _BOOL_QUESTION.prompt
    assert set(question["criteria"]) == {"true", "false"}


def test_build_request_enum_question_uses_choice_criteria_per_option() -> None:
    request = _build_request("evidence", [_ENUM_QUESTION], "jev-latest")
    question = request["questions"]["team"]
    assert question["type"] == "choice"
    assert set(question["criteria"]) == {"billing", "infra"}


def test_build_request_number_question_uses_score_type() -> None:
    request = _build_request("evidence", [_NUMBER_QUESTION], "jev-latest")
    assert request["questions"]["severity"]["type"] == "score"


def test_build_request_enum_without_options_raises() -> None:
    bad = TypedQuestion(id="x", prompt="?", answer_type="enum", enum_options=None)
    with pytest.raises(ValueError, match="enum_options"):
        _build_request("evidence", [bad], "jev-latest")


def test_parse_response_bool_true_high_confidence() -> None:
    body = {"answers": {"same_asset": {"type": "noul", "noul": 0.95}}}
    [answer] = _parse_response(body, [_BOOL_QUESTION])
    assert answer == TypedAnswer(question_id="same_asset", value=True, confidence=0.95)


def test_parse_response_bool_false_confidence_is_1_minus_p_true() -> None:
    """A low p(true) means a confident False, not a low-confidence answer."""
    body = {"answers": {"same_asset": {"type": "noul", "noul": 0.03}}}
    [answer] = _parse_response(body, [_BOOL_QUESTION])
    assert answer.value is False
    assert answer.confidence == pytest.approx(0.97)


def test_parse_response_enum_uses_confidence_field_if_present() -> None:
    body = {
        "answers": {
            "team": {"type": "choice", "choice": "billing", "confidence": 0.8, "probabilities": {}}
        }
    }
    [answer] = _parse_response(body, [_ENUM_QUESTION])
    assert answer.value == "billing"
    assert answer.confidence == 0.8


def test_parse_response_enum_falls_back_to_probabilities_for_confidence() -> None:
    body = {
        "answers": {
            "team": {"type": "choice", "choice": "infra", "probabilities": {"infra": 0.6}}
        }
    }
    [answer] = _parse_response(body, [_ENUM_QUESTION])
    assert answer.confidence == 0.6


def test_parse_response_number_question() -> None:
    body = {"answers": {"severity": {"type": "score", "score": 7.5, "confidence": 0.7}}}
    [answer] = _parse_response(body, [_NUMBER_QUESTION])
    assert answer.value == 7.5
    assert answer.confidence == 0.7


# --- ugly paths --------------------------------------------------------------


def test_parse_response_missing_answers_object_raises() -> None:
    with pytest.raises(JevProviderError, match="answers"):
        _parse_response({}, [_BOOL_QUESTION])


def test_parse_response_missing_question_answer_raises() -> None:
    with pytest.raises(JevProviderError, match="same_asset"):
        _parse_response({"answers": {}}, [_BOOL_QUESTION])


def test_parse_response_wrong_type_field_raises() -> None:
    body = {"answers": {"same_asset": {"type": "choice", "choice": "x"}}}
    with pytest.raises(JevProviderError, match="expected answer type"):
        _parse_response(body, [_BOOL_QUESTION])


@pytest.mark.parametrize("bad_confidence", [1.5, -0.1])
def test_parse_response_confidence_out_of_range_raises(bad_confidence: float) -> None:
    body = {
        "answers": {
            "team": {"type": "choice", "choice": "billing", "confidence": bad_confidence}
        }
    }
    with pytest.raises(JevProviderError, match=r"outside \[0, 1\]"):
        _parse_response(body, [_ENUM_QUESTION])


def test_parse_response_non_numeric_noul_raises() -> None:
    body = {"answers": {"same_asset": {"type": "noul", "noul": "high"}}}
    with pytest.raises(JevProviderError, match="non-numeric 'noul'"):
        _parse_response(body, [_BOOL_QUESTION])


# --- JevTransport (mocked httpx) --------------------------------------------


def _mock_post_response(json_body: Any, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body
    response.text = "" if status_code < 400 else str(json_body)
    return response


def test_classify_requires_at_least_one_question() -> None:
    transport = JevTransport(api_key="secret")
    with pytest.raises(ValueError, match="non-empty"):
        transport.classify("state", [])


def test_classify_without_api_key_raises_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    transport = JevTransport(api_key=None)
    with pytest.raises(JevConfigurationError, match="TYPESAFE_API_KEY"):
        transport.classify("state", [_BOOL_QUESTION])


def test_classify_success_returns_typed_answers() -> None:
    transport = JevTransport(api_key="secret")
    body = {"answers": {"same_asset": {"type": "noul", "noul": 0.9}}}
    with patch.object(httpx.Client, "post", return_value=_mock_post_response(body)) as mock_post:
        [answer] = transport.classify("evidence text", [_BOOL_QUESTION])
    assert answer.value is True
    assert answer.confidence == 0.9
    sent_kwargs = mock_post.call_args.kwargs
    assert sent_kwargs["json"]["state"] == "evidence text"


def test_classify_non_2xx_status_raises_provider_error() -> None:
    transport = JevTransport(api_key="secret")
    with (
        patch.object(
            httpx.Client,
            "post",
            return_value=_mock_post_response({"error": "bad key"}, status_code=401),
        ),
        pytest.raises(JevProviderError, match="HTTP 401"),
    ):
        transport.classify("evidence", [_BOOL_QUESTION])


def test_classify_timeout_raises_provider_error() -> None:
    transport = JevTransport(api_key="secret")
    with (
        patch.object(httpx.Client, "post", side_effect=httpx.TimeoutException("timed out")),
        pytest.raises(JevProviderError, match="timed out"),
    ):
        transport.classify("evidence", [_BOOL_QUESTION])


def test_classify_malformed_json_raises_provider_error() -> None:
    transport = JevTransport(api_key="secret")
    response = MagicMock()
    response.status_code = 200
    response.json.side_effect = ValueError("not json")
    with (
        patch.object(httpx.Client, "post", return_value=response),
        pytest.raises(JevProviderError, match="not valid JSON"),
    ):
        transport.classify("evidence", [_BOOL_QUESTION])


def test_classify_confidence_out_of_range_raises_provider_error() -> None:
    transport = JevTransport(api_key="secret")
    body = {"answers": {"team": {"type": "choice", "choice": "billing", "confidence": 1.2}}}
    with (
        patch.object(httpx.Client, "post", return_value=_mock_post_response(body)),
        pytest.raises(JevProviderError, match=r"outside \[0, 1\]"),
    ):
        transport.classify("evidence", [_ENUM_QUESTION])


# --- process-wide accessor ---------------------------------------------------


def test_get_jev_transport_builds_lazily_and_is_cached() -> None:
    set_jev_transport(None)
    first = get_jev_transport()
    second = get_jev_transport()
    assert first is second


def test_set_jev_transport_overrides_for_tests() -> None:
    fake = MagicMock()
    set_jev_transport(fake)
    assert get_jev_transport() is fake
