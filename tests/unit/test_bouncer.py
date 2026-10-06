"""Task group 4: The Bouncer — the vision gate itself.

The two required cases are the negative (landscape/object -> cheeky rejection
+ state reset) and the positive (person -> confirmation + state advance).
Gemini is fully mocked here; the live check lives in
``tests/integration/test_live_bouncer.py``.
"""

import pytest

from tele_bot.bouncer import (
    CONFIRMATION_REPLY,
    REJECTION_REPLY,
    Bouncer,
    BouncerResult,
)
from tele_bot.contracts import HumanPresenceVerdict, PhotoMessage
from tele_bot.state import PipelinePhase, SessionDriver

LANDSCAPE_BYTES = b"\xff\xd8\xff\xe0not-really-a-jpeg-but-shaped-like-one"
PORTRAIT_BYTES = b"\xff\xd8\xff\xe0a-person-was-here"


class StubClassifier:
    """A Gemini stand-in: hands back a canned verdict, records what it got."""

    def __init__(self, verdict: HumanPresenceVerdict | Exception) -> None:
        self._verdict = verdict
        self.received: list[PhotoMessage] = []

    def classify(self, photo: PhotoMessage) -> HumanPresenceVerdict:
        self.received.append(photo)
        if isinstance(self._verdict, Exception):
            raise self._verdict
        return self._verdict


def _photo(data: bytes = LANDSCAPE_BYTES, chat_id: int = 1) -> PhotoMessage:
    return PhotoMessage(
        chat_id=chat_id,
        file_id="file-1",
        mime_type="image/jpeg",
        data=data,
    )


def _verdict(human_present: bool, reason: str) -> HumanPresenceVerdict:
    return HumanPresenceVerdict(human_present=human_present, reason=reason)


# --- The two required tests ------------------------------------------------


def test_negative_landscape_is_rejected_and_state_resets() -> None:
    """No human in frame -> cheeky rejection, session back to square one."""
    driver = SessionDriver()
    driver.advance(1, PipelinePhase.AWAITING_INTERVIEW)  # to prove the reset
    bouncer = Bouncer(StubClassifier(_verdict(False, "a mountain range")), driver)

    result = bouncer.handle(_photo())

    assert result.admitted is False
    assert driver.get(1).phase is PipelinePhase.AWAITING_PHOTO
    assert "human" in result.reply.lower()


def test_positive_person_is_confirmed_and_state_advances() -> None:
    """A discernible human -> brief confirmation, pipeline moves on."""
    driver = SessionDriver()
    bouncer = Bouncer(StubClassifier(_verdict(True, "one adult human")), driver)

    result = bouncer.handle(_photo(data=PORTRAIT_BYTES))

    assert result.admitted is True
    assert driver.get(1).phase is PipelinePhase.AWAITING_INTERVIEW
    assert result.reply == CONFIRMATION_REPLY


# --- Rejection copy --------------------------------------------------------


def test_rejection_is_cheeky_and_explains_the_human_requirement() -> None:
    bouncer = Bouncer(StubClassifier(_verdict(False, "a sandwich")), SessionDriver())

    result = bouncer.handle(_photo())

    lowered = result.reply.lower()
    assert "human" in lowered, "the rejection must say a human is required"
    assert result.reply == REJECTION_REPLY


def test_confirmation_is_sent_unchanged_for_every_admitted_photo() -> None:
    driver = SessionDriver()
    bouncer = Bouncer(StubClassifier(_verdict(True, "a face")), driver)

    first = bouncer.handle(_photo(chat_id=1))
    second = bouncer.handle(_photo(chat_id=2))

    assert first.reply == second.reply == CONFIRMATION_REPLY


# --- The classifier receives what it should --------------------------------


def test_classifier_is_handed_the_original_image_bytes() -> None:
    classifier = StubClassifier(_verdict(True, "a face"))
    bouncer = Bouncer(classifier, SessionDriver())

    bouncer.handle(_photo(data=PORTRAIT_BYTES))

    assert len(classifier.received) == 1
    assert classifier.received[0].data == PORTRAIT_BYTES
    assert classifier.received[0].chat_id == 1


def test_each_chat_is_gated_independently() -> None:
    """One chat's rejection must not touch another chat's session."""
    driver = SessionDriver()
    driver.advance(2, PipelinePhase.AWAITING_INTERVIEW)
    bouncer = Bouncer(StubClassifier(_verdict(False, "a hedge")), driver)

    bouncer.handle(_photo(chat_id=1))

    assert driver.get(1).phase is PipelinePhase.AWAITING_PHOTO
    assert driver.get(2).phase is PipelinePhase.AWAITING_INTERVIEW


# --- Failure policy: degrade on the conversation path, never crash ---------


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("Gemini timed out"),
        ValueError("response was not JSON"),
    ],
    ids=["api-timeout", "unparseable-output"],
)
def test_classifier_failure_degrades_to_a_graceful_reply(
    failure: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    """Logged loudly, user still gets an answer, nothing raises at the user."""
    driver = SessionDriver()
    bouncer = Bouncer(StubClassifier(failure), driver)

    with caplog.at_level("ERROR"):
        result = bouncer.handle(_photo())

    assert result.admitted is False
    assert result.reply, "the user must still receive a reply"
    assert any(rec.levelno >= 40 for rec in caplog.records), "the failure must be logged"
    assert driver.get(1).phase is PipelinePhase.AWAITING_PHOTO


def test_a_failed_classification_does_not_advance_the_pipeline() -> None:
    driver = SessionDriver()
    bouncer = Bouncer(StubClassifier(RuntimeError("boom")), driver)

    bouncer.handle(_photo())

    assert driver.get(1).phase is PipelinePhase.AWAITING_PHOTO


def test_bouncer_returns_a_typed_result_not_a_bare_string() -> None:
    bouncer = Bouncer(StubClassifier(_verdict(True, "a face")), SessionDriver())

    result = bouncer.handle(_photo())

    assert isinstance(result, BouncerResult)
    assert isinstance(result.admitted, bool)
