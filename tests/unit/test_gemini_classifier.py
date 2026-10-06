"""Gemini classifier unit tests — the SDK boundary, offline.

Covers the promise in validation.md §4-7 & the reviewer's gap: malformed
Gemini output, missing text, client/server errors — all before any network.
"""

from types import SimpleNamespace

import pytest
from google.genai import types
from google.genai.errors import ClientError, ServerError

from tele_bot.contracts import HumanPresenceVerdict, PhotoMessage
from tele_bot.gemini_classifier import GeminiClassifierError, GeminiHumanPresenceClassifier

PHOTO = PhotoMessage(
    chat_id=1,
    file_id="f1",
    mime_type="image/jpeg",
    data=b"\xff\xd8\xff",
)


class _FakeModels:
    def __init__(self, *, response_text: str, error: Exception | None = None) -> None:
        self._text = response_text
        self._error = error

    def generate_content(self, **_: object) -> types.GenerateContentResponse:
        if self._error is not None:
            raise self._error
        parts = [types.Part(text=self._text)] if self._text else []
        candidate = types.Candidate(content=types.Content(role="model", parts=parts))
        return types.GenerateContentResponse(candidates=[candidate])


def _classifier(text: str, error: Exception | None = None) -> GeminiHumanPresenceClassifier:
    fake_models = _FakeModels(response_text=text, error=error)
    fake_client = SimpleNamespace(models=fake_models)
    # The real class type-checks its client as google.genai.Client; for unit
    # tests we hand it a bare stub with the same surface (#f47ed).
    return GeminiHumanPresenceClassifier(api_key="test-key", client=fake_client)  # type: ignore[arg-type]


def _verdict_json(*, present: bool = True, reason: str = "a person is visible") -> str:
    return f'{{"human_present": {str(present).lower()}, "reason": "{reason}"}}'


# --- _parse ---------------------------------------------------------------


def test_parse_accepts_a_well_formed_verdict() -> None:
    classifier = _classifier(_verdict_json())

    verdict = classifier._parse(_verdict_json())

    assert verdict == HumanPresenceVerdict(human_present=True, reason="a person is visible")


def test_parse_rejects_malformed_json() -> None:
    classifier = _classifier("not json at all")

    with pytest.raises(GeminiClassifierError):
        classifier._parse("not json at all")


def test_parse_rejects_json_missing_required_fields() -> None:
    classifier = _classifier('{"human_present": true}')

    with pytest.raises(GeminiClassifierError):
        classifier._parse('{"human_present": true}')


def test_parse_rejects_a_boolean_confidence() -> None:
    classifier = _classifier('{"human_present": true, "reason": "x", "confidence": true}')

    with pytest.raises(GeminiClassifierError):
        classifier._parse('{"human_present": true, "reason": "x", "confidence": true}')


# --- classify (SDK call, offline via injected client) ----------------------


def test_classify_returns_a_typed_verdict() -> None:
    classifier = _classifier(_verdict_json())

    verdict = classifier.classify(PHOTO)

    assert verdict.human_present is True
    assert verdict.reason == "a person is visible"


def test_classify_raises_when_gemini_returns_no_text() -> None:
    classifier = _classifier("")

    with pytest.raises(GeminiClassifierError):
        classifier.classify(PHOTO)


def test_classify_wraps_a_client_error() -> None:
    classifier = _classifier("", error=ClientError(code=400, response_json={}))

    with pytest.raises(GeminiClassifierError):
        classifier.classify(PHOTO)


def test_classify_wraps_a_server_error() -> None:
    classifier = _classifier("", error=ServerError(code=503, response_json={}))

    with pytest.raises(GeminiClassifierError):
        classifier.classify(PHOTO)
