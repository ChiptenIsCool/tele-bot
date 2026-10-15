"""Full documentary flow through a real ADK runner, with model calls stubbed."""

import asyncio

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from agents.documentary_agent import InterviewerAgent
from tele_bot.contracts import (
    DocumentaryScript,
    Dossier,
    HumanPresenceVerdict,
    InterviewAnswer,
    InterviewTurn,
    Media,
    PhotoMessage,
)
from tele_bot.state import PipelinePhase, SessionDriver

SCRIPT = " ".join(["The curious badger searches its habitat for another midnight snack."] * 6)


class FakeServices:
    def __init__(self) -> None:
        self.human = True
        self.fail_image = False
        self.fail_script = False
        self.fail_audio = False
        self.images = 0
        self.questions = 0
        self.block: asyncio.Event | None = None

    async def close(self) -> None:
        pass

    async def classify(self, photo: PhotoMessage) -> HumanPresenceVerdict:
        return HumanPresenceVerdict(human_present=self.human, reason="test")

    async def question(self, answers: tuple[InterviewAnswer, ...]) -> InterviewTurn:
        self.questions += 1
        return InterviewTurn(question=f"What is your habit number {len(answers) + 1}?")

    async def profile(self, answers: tuple[InterviewAnswer, ...]) -> Dossier:
        assert len(answers) == 5
        return Dossier(
            summary="A nocturnal snack collector.", animal="badger", rationale="Nocturnal"
        )

    async def convert(self, photo: PhotoMessage, dossier: Dossier) -> Media:
        self.images += 1
        if self.block:
            await self.block.wait()
        if self.fail_image:
            raise RuntimeError("image service unavailable")
        assert photo.data == b"portrait"
        return Media(data=b"generated image", mime_type="image/png")

    async def script(self, dossier: Dossier) -> DocumentaryScript:
        if self.fail_script:
            raise RuntimeError("script unavailable")
        return DocumentaryScript(text=SCRIPT)

    async def narrate(self, script: DocumentaryScript) -> Media:
        if self.fail_audio:
            raise RuntimeError("speech unavailable")
        return Media(data=b"OggSvoice", mime_type="audio/ogg")


class Harness:
    def __init__(self) -> None:
        self.services = FakeServices()
        self.state = SessionDriver()
        self.agent = InterviewerAgent(self.services, self.state)
        self.runner = InMemoryRunner(agent=self.agent, app_name="test")

    async def turn(self, text: str = "", *, photo: bool = False, chat: int = 1) -> list[types.Part]:
        uid = str(chat)
        if not await self.runner.session_service.get_session(
            app_name="test", user_id=uid, session_id=uid
        ):
            await self.runner.session_service.create_session(
                app_name="test", user_id=uid, session_id=uid
            )
        parts = (
            [types.Part.from_bytes(data=b"portrait", mime_type="image/jpeg")]
            if photo
            else [types.Part(text=text)]
        )
        output: list[types.Part] = []
        async for event in self.runner.run_async(
            user_id=uid,
            session_id=uid,
            new_message=types.Content(role="user", parts=parts),
            state_delta={"photo_file_id": "test-photo"},
        ):
            if event.content and event.content.parts:
                output.extend(event.content.parts)
        return output


async def test_full_flow_asks_five_questions_and_delivers_image_script_voice() -> None:
    h = Harness()
    first = await h.turn(photo=True)
    assert "1/5" in " ".join(p.text or "" for p in first)
    for index in range(4):
        result = await h.turn(f"answer {index}")
        assert f"{index + 2}/5" in " ".join(p.text or "" for p in result)
    result = await h.turn("final answer")
    media = [p.inline_data.mime_type for p in result if p.inline_data]
    assert media == ["image/png", "audio/ogg"]
    assert any(p.text == SCRIPT for p in result)
    assert h.services.questions == 5
    assert h.state.get(1).phase is PipelinePhase.COMPLETE
    assert h.state.get(1).photo is None
    assert not h.state.get(1).answers


async def test_wrong_input_and_cross_chat_isolation() -> None:
    h = Harness()
    await h.turn(photo=True)
    question = h.state.get(1).question
    await h.turn(photo=True)
    assert h.state.get(1).question == question
    assert not h.state.get(1).answers
    await h.turn("hello", chat=2)
    assert h.state.get(2).phase is PipelinePhase.AWAITING_PHOTO
    assert h.services.questions == 1


async def test_nonhuman_rejection_resets() -> None:
    h = Harness()
    h.services.human = False
    result = await h.turn(photo=True)
    assert "human" in " ".join(p.text or "" for p in result)
    assert h.state.get(1).phase is PipelinePhase.AWAITING_PHOTO
    assert h.state.get(1).photo is None


async def test_generation_retry_preserves_five_answers() -> None:
    h = Harness()
    await h.turn(photo=True)
    for _ in range(4):
        await h.turn("snacks")
    h.services.fail_image = True
    with pytest.raises(RuntimeError, match="unavailable"):
        await h.turn("sleep")
    assert h.state.get(1).phase is PipelinePhase.CONVERTING
    h.services.fail_image = False
    result = await h.turn("/retry")
    assert any(p.inline_data and p.inline_data.mime_type == "audio/ogg" for p in result)
    assert h.services.questions == 5


async def test_cancelled_generation_can_reset_without_late_results() -> None:
    h = Harness()
    await h.turn(photo=True)
    for _ in range(4):
        await h.turn("snacks")
    h.services.block = asyncio.Event()
    task = asyncio.create_task(h.turn("sleep"))
    for _ in range(100):
        if h.services.images:
            break
        await asyncio.sleep(0)
    assert h.services.images == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    h.state.reset(1)
    h.services.block.set()
    await asyncio.sleep(0)
    assert h.state.get(1).photo is None
    assert h.state.get(1).phase is PipelinePhase.AWAITING_PHOTO


def test_script_contract_rejects_wrong_length_or_paragraphs() -> None:
    with pytest.raises(ValueError):
        DocumentaryScript(text="too short")
    with pytest.raises(ValueError):
        DocumentaryScript(text=SCRIPT + "\n\nAnother paragraph.")
