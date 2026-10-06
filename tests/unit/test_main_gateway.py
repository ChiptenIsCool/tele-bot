"""Task group 5 gateway tests: the PTB long-polling handler end-to-end.

Telegram is mocked (fake bot with download surface), Gemini is stubbed, and
the whole 'photo update -> download -> validate -> gate -> reply' route runs
through a real ADK InMemoryRunner — matching validation.md §6.
"""

from datetime import UTC, datetime

import pytest
from google.adk.runners import InMemoryRunner
from telegram import Chat, Message, PhotoSize, Update

from agents.bouncer_agent import BouncerAgent
from tele_bot.bouncer import CONFIRMATION_REPLY, REJECTION_REPLY, Bouncer
from tele_bot.contracts import HumanPresenceVerdict
from tele_bot.main import ensure_session, handle_photo
from tele_bot.state import PipelinePhase, SessionDriver
from tele_bot.telegram_io import sniff_image_mime

LANDSCAPE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01landscape"
PORTRAIT_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01portrait"

APP_NAME = "telegram_documentaries"


class FakeFile:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    async def download_as_bytearray(self) -> bytearray:
        return bytearray(self._payload)


class FakeBot:
    """Telegram stand-in exposing the download + reply surface the gateway uses."""

    def __init__(self, payload: bytes) -> None:
        self._file = FakeFile(payload)
        self.sent: list[tuple[int, str]] = []

    async def get_file(self, file_id: str) -> FakeFile:
        return self._file

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


class StubClassifier:
    def __init__(self, verdict: HumanPresenceVerdict) -> None:
        self._verdict = verdict

    def classify(self, photo: object) -> HumanPresenceVerdict:
        del photo  # stubbed: the verdict is fixed before the call
        return self._verdict


def _verdict(present: bool) -> HumanPresenceVerdict:
    return HumanPresenceVerdict(human_present=present, reason="stub says so")


def _photo_update(chat_id: int = 1, file_id: str = "f1") -> Update:
    message = Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=chat_id, type="private"),
        photo=[PhotoSize(file_id=file_id, file_unique_id="u1", width=640, height=480)],
    )
    return Update(update_id=1, message=message)


class _Context:
    """Minimal stand-in for the PTB handler context (bot_data + bot)."""

    def __init__(self, bot: FakeBot, runner: InMemoryRunner) -> None:
        self.bot_data = {"runner": runner}
        self.bot = bot


# --- sniff_image_mime (foundation for gateway validation) -------------------


def test_sniff_image_mime_detects_jpeg() -> None:
    assert sniff_image_mime(LANDSCAPE_JPEG) == "image/jpeg"


def test_sniff_image_mime_rejects_foreign_bytes() -> None:
    with pytest.raises(ValueError):
        sniff_image_mime(b"<html>not an image</html>")

    with pytest.raises(ValueError):
        sniff_image_mime(b"")


# --- the full route (validation.md §6) --------------------------------------


async def _run_gateway(
    payload: bytes, verdict: bool, chat_id: int = 1, file_id: str = "f1"
) -> tuple[str, SessionDriver]:
    driver = SessionDriver()
    classifier = StubClassifier(_verdict(verdict))
    agent = BouncerAgent(Bouncer(classifier, driver), name="bouncer")
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    bot = FakeBot(payload)
    await ensure_session(runner, chat_id)

    await handle_photo(_photo_update(chat_id, file_id), _Context(bot, runner))  # type: ignore[arg-type]

    assert bot.sent, "the gateway must reply to every valid photo"
    return bot.sent[0][1], driver


async def test_gateway_negative_rejects_and_resets() -> None:
    reply, driver = await _run_gateway(LANDSCAPE_JPEG, verdict=False)

    assert reply == REJECTION_REPLY
    assert driver.get(1).phase is PipelinePhase.AWAITING_PHOTO


async def test_gateway_positive_confirms_and_advances() -> None:
    reply, driver = await _run_gateway(PORTRAIT_JPEG, verdict=True)

    assert reply == CONFIRMATION_REPLY
    assert driver.get(1).phase is PipelinePhase.AWAITING_INTERVIEW


async def test_gateway_sends_the_reply_to_the_right_chat() -> None:
    driver = SessionDriver()
    classifier = StubClassifier(_verdict(True))
    agent = BouncerAgent(Bouncer(classifier, driver), name="bouncer")
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    bot = FakeBot(PORTRAIT_JPEG)
    await ensure_session(runner, 42)

    await handle_photo(_photo_update(chat_id=42, file_id="f9"), _Context(bot, runner))  # type: ignore[arg-type]

    assert bot.sent == [(42, CONFIRMATION_REPLY)]


async def test_gateway_ignores_updates_without_a_photo() -> None:
    """A non-photo update (e.g. sticker, text) must not crash or reply."""
    driver = SessionDriver()
    agent = BouncerAgent(Bouncer(StubClassifier(_verdict(True)), driver), name="bouncer")
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    bot = FakeBot(PORTRAIT_JPEG)
    await ensure_session(runner, 1)

    update = Update(update_id=2, message=None)
    await handle_photo(update, _Context(bot, runner))  # type: ignore[arg-type]

    assert bot.sent == []


async def test_gateway_validation_runs_before_the_gate_sees_data() -> None:
    """Non-image bytes must be rejected before Gemini/ADK ever runs."""
    driver = SessionDriver()
    classifier = StubClassifier(_verdict(True))
    agent = BouncerAgent(Bouncer(classifier, driver), name="bouncer")
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    bot = FakeBot(b"<html>not an image</html>")
    await ensure_session(runner, 1)

    # The handler validates the sniffed mime at the edge and refuses to pass
    # foreign bytes to the gate; an exception here is the loud, early failure.
    with pytest.raises(ValueError):
        await handle_photo(_photo_update(1, "evil"), _Context(bot, runner))  # type: ignore[arg-type]

    assert bot.sent == []
    assert driver.get(1).phase is PipelinePhase.AWAITING_PHOTO


async def test_gateway_runs_even_without_explicit_session_pre_creation() -> None:
    """ensure_session lazily creates the ADK session when missing."""
    driver = SessionDriver()
    agent = BouncerAgent(Bouncer(StubClassifier(_verdict(True)), driver), name="bouncer")
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    bot = FakeBot(PORTRAIT_JPEG)

    await handle_photo(_photo_update(1, "f1"), _Context(bot, runner))  # type: ignore[arg-type]

    assert bot.sent == [(1, CONFIRMATION_REPLY)]
    assert driver.get(1).phase is PipelinePhase.AWAITING_INTERVIEW
