"""Telegram lifecycle, delivery and cancellation through real ADK."""

import asyncio
import gc
import io
from typing import cast

import pytest
from google.genai import types
from telegram import Bot
from test_documentary import FakeServices

from tele_bot.gateway import DocumentaryRuntime
from tele_bot.state import PipelinePhase


class FakeBot:
    def __init__(self) -> None:
        self.text: list[tuple[int, str]] = []
        self.media: list[tuple[int, str, bytes]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.text.append((chat_id, text))

    async def send_photo(self, chat_id: int, photo: io.BytesIO, write_timeout: int) -> None:
        self.media.append((chat_id, "photo", photo.getvalue()))

    async def send_voice(self, chat_id: int, voice: io.BytesIO, write_timeout: int) -> None:
        self.media.append((chat_id, "voice", voice.getvalue()))


def content(text: str = "answer", *, photo: bool = False) -> types.Content:
    return types.Content(
        role="user",
        parts=[
            types.Part.from_bytes(data=b"portrait", mime_type="image/jpeg")
            if photo
            else types.Part(text=text)
        ],
    )


async def dispatch(
    engine: DocumentaryRuntime, bot: FakeBot, turn: types.Content, chat: int = 1
) -> None:
    await engine.dispatch(cast(Bot, bot), chat, turn, "photo")
    await engine.jobs[chat]


async def test_gateway_delivers_full_documentary_and_releases_adk_history(
    caplog: pytest.LogCaptureFixture,
) -> None:
    engine = DocumentaryRuntime(FakeServices())
    bot = FakeBot()
    await dispatch(engine, bot, content(photo=True))
    for _ in range(5):
        await dispatch(engine, bot, content())
    assert [kind for _, kind, _ in bot.media] == ["photo", "voice"]
    assert all(chat == 1 for chat, _ in bot.text)
    assert engine.state.get(1).phase is PipelinePhase.COMPLETE
    session = await engine.runner.session_service.get_session(
        app_name="telegram_documentaries", user_id="1", session_id="1"
    )
    assert session is None
    await engine.reset(1)
    await dispatch(engine, bot, content(photo=True))
    assert engine.state.get(1).question is not None
    for _ in range(5):
        await dispatch(engine, bot, content())
    assert [kind for _, kind, _ in bot.media] == ["photo", "voice", "photo", "voice"]
    assert engine.state.get(1).phase is PipelinePhase.COMPLETE
    gc.collect()
    await asyncio.sleep(0)
    assert not any("Failed to detach context" in record.message for record in caplog.records)


async def test_gateway_reset_cancels_active_generation_and_preserves_other_chat() -> None:
    services = FakeServices()
    engine = DocumentaryRuntime(services)
    bot = FakeBot()
    await dispatch(engine, bot, content(photo=True))
    await dispatch(engine, bot, content(photo=True), chat=2)
    for _ in range(4):
        await dispatch(engine, bot, content())
    services.block = asyncio.Event()
    await engine.dispatch(cast(Bot, bot), 1, content())
    for _ in range(100):
        if services.images:
            break
        await asyncio.sleep(0)
    assert engine.busy(1)
    await engine.reset(1)
    services.block.set()
    await asyncio.sleep(0)
    assert engine.state.get(1).phase is PipelinePhase.AWAITING_PHOTO
    assert engine.state.get(2).question is not None
    assert not bot.media
    assert not engine.busy(1)


async def test_gateway_error_offers_retry_and_keeps_polling_usable() -> None:
    services = FakeServices()
    engine = DocumentaryRuntime(services)
    bot = FakeBot()
    await dispatch(engine, bot, content(photo=True))
    for _ in range(4):
        await dispatch(engine, bot, content())
    services.fail_image = True
    await dispatch(engine, bot, content())
    assert any("/retry" in text for _, text in bot.text)
    assert engine.state.get(1).phase is PipelinePhase.CONVERTING
    services.fail_image = False
    await dispatch(engine, bot, content("/retry"))
    assert engine.state.get(1).phase is PipelinePhase.COMPLETE


async def test_gateway_busy_chat_does_not_accept_duplicate_answer() -> None:
    services = FakeServices()
    engine = DocumentaryRuntime(services)
    bot = FakeBot()
    await dispatch(engine, bot, content(photo=True))
    for _ in range(4):
        await dispatch(engine, bot, content())
    services.block = asyncio.Event()
    await engine.dispatch(cast(Bot, bot), 1, content())
    for _ in range(100):
        if services.images:
            break
        await asyncio.sleep(0)
    await engine.dispatch(cast(Bot, bot), 1, content("extra answer"))
    assert len(engine.state.get(1).answers) == 5
    assert services.images == 1
    await engine.reset(1)


@pytest.mark.parametrize("text", ["hello", "/retry"])
async def test_gateway_text_before_photo_prompts_for_portrait(text: str) -> None:
    engine = DocumentaryRuntime(FakeServices())
    bot = FakeBot()
    await dispatch(engine, bot, content(text))
    assert any("portrait" in reply for _, reply in bot.text)
    assert engine.state.get(1).phase is PipelinePhase.AWAITING_PHOTO


@pytest.mark.parametrize("stage", ["script", "audio"])
async def test_later_stage_retry_does_not_regenerate_portrait(stage: str) -> None:
    services = FakeServices()
    engine = DocumentaryRuntime(services)
    bot = FakeBot()
    await dispatch(engine, bot, content(photo=True))
    for _ in range(4):
        await dispatch(engine, bot, content())
    services.fail_script = stage == "script"
    services.fail_audio = stage == "audio"
    await dispatch(engine, bot, content())
    assert [kind for _, kind, _ in bot.media] == ["photo"]
    services.fail_script = services.fail_audio = False
    await dispatch(engine, bot, content("/retry"))
    assert [kind for _, kind, _ in bot.media] == ["photo", "voice"]
    assert services.images == 1
    assert services.questions == 5
