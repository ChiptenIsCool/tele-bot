"""Task group 5: Telegram download + ADK wiring.

Telegram is fully mocked (a fake bot) and Gemini is stubbed; the whole gate
runs through a real ADK InMemoryRunner.
"""

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from agents.bouncer_agent import BouncerAgent, NoPhotoError
from tele_bot.bouncer import CONFIRMATION_REPLY, REJECTION_REPLY, Bouncer
from tele_bot.contracts import HumanPresenceVerdict
from tele_bot.state import PipelinePhase, SessionDriver
from tele_bot.telegram_io import download_photo_bytes

LANDSCAPE_BYTES = b"\xff\xd8landscape-jpeg-bytes"
PORTRAIT_BYTES = b"\xff\xd8person-jpeg-bytes"

APP_NAME = "telegram_documentaries"


class FakeFile:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def download_as_bytearray(self) -> bytearray:
        return bytearray(self._payload)


class FakeBot:
    """A Telegram stand-in exposing just get_file -> download."""

    def __init__(self, payload: bytes) -> None:
        self._file = FakeFile(payload)
        self.requested: list[str] = []

    async def get_file(self, file_id: str) -> FakeFile:
        self.requested.append(file_id)
        if not file_id:
            raise ValueError("empty file_id")
        return self._file


class StubClassifier:
    def __init__(self, verdict: HumanPresenceVerdict) -> None:
        self._verdict = verdict
        self.photo_data: bytes | None = None

    def classify(self, photo: object) -> HumanPresenceVerdict:
        self.photo_data = photo.data  # type: ignore[attr-defined]
        return self._verdict


def _verdict(present: bool) -> HumanPresenceVerdict:
    return HumanPresenceVerdict(human_present=present, reason="stub says so")


# --- Download --------------------------------------------------------------


async def test_download_returns_the_image_bytes() -> None:
    bot = FakeBot(PORTRAIT_BYTES)

    data = await download_photo_bytes(bot, "file-abc")

    assert data == PORTRAIT_BYTES
    assert bot.requested == ["file-abc"]


async def test_download_rejects_an_empty_file_id() -> None:
    bot = FakeBot(PORTRAIT_BYTES)

    with pytest.raises(ValueError):
        await download_photo_bytes(bot, "")


# --- The two required end-to-end cases through ADK -------------------------


async def _run_gate(bouncer: Bouncer, data: bytes, chat_id: int = 1) -> str:
    runner = InMemoryRunner(agent=BouncerAgent(bouncer=bouncer), app_name=APP_NAME)
    uid = str(chat_id)
    await runner.session_service.create_session(app_name=APP_NAME, user_id=uid, session_id=uid)

    content = types.Content(
        role="user",
        parts=[types.Part.from_bytes(data=data, mime_type="image/jpeg")],
    )
    replies: list[str] = []
    async for event in runner.run_async(
        user_id=uid, session_id=uid, new_message=content, state_delta={"photo_file_id": "f1"}
    ):
        if event.content and event.content.parts and event.content.parts[0].text:
            replies.append(event.content.parts[0].text)
    return "\n".join(replies)


async def test_negative_through_adk_rejects_and_resets() -> None:
    driver = SessionDriver()
    driver.advance(1, PipelinePhase.AWAITING_INTERVIEW)
    bouncer = Bouncer(StubClassifier(_verdict(False)), driver)

    reply = await _run_gate(bouncer, LANDSCAPE_BYTES)

    assert reply == REJECTION_REPLY
    assert driver.get(1).phase is PipelinePhase.AWAITING_PHOTO


async def test_positive_through_adk_confirms_and_advances() -> None:
    driver = SessionDriver()
    bouncer = Bouncer(StubClassifier(_verdict(True)), driver)

    reply = await _run_gate(bouncer, PORTRAIT_BYTES)

    assert reply == CONFIRMATION_REPLY
    assert driver.get(1).phase is PipelinePhase.AWAITING_INTERVIEW


async def test_session_is_per_chat_id_through_adk() -> None:
    driver = SessionDriver()

    await _run_gate(Bouncer(StubClassifier(_verdict(False)), driver), LANDSCAPE_BYTES, chat_id=1)
    await _run_gate(Bouncer(StubClassifier(_verdict(True)), driver), PORTRAIT_BYTES, chat_id=2)

    assert driver.get(1).phase is PipelinePhase.AWAITING_PHOTO
    assert driver.get(2).phase is PipelinePhase.AWAITING_INTERVIEW


async def test_photo_bytes_reach_the_classifier_through_adk() -> None:
    classifier = StubClassifier(_verdict(True))
    bouncer = Bouncer(classifier, SessionDriver())

    await _run_gate(bouncer, PORTRAIT_BYTES)

    assert classifier.photo_data == PORTRAIT_BYTES


async def test_gate_rejects_content_without_an_image() -> None:
    """A text-only payload must fail loudly — never silently pass the gate."""
    agent = BouncerAgent(Bouncer(StubClassifier(_verdict(True)), SessionDriver()))
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    uid = "1"
    await runner.session_service.create_session(app_name=APP_NAME, user_id=uid, session_id=uid)

    content = types.Content(role="user", parts=[types.Part(text="no image here")])

    # file_id IS present in session state, so the failure must come from the
    # missing-image branch (_photo_bytes) — not from an absent file_id.
    with pytest.raises(NoPhotoError, match="image"):
        async for _ in runner.run_async(
            user_id=uid,
            session_id=uid,
            new_message=content,
            state_delta={"photo_file_id": "f1"},
        ):
            pass
