"""ADK hub-and-spoke agents with an Interviewer-owned state machine."""

from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai import types
from pydantic import PrivateAttr

from tele_bot.bouncer import REJECTION_REPLY
from tele_bot.contracts import (
    DocumentaryScript,
    HumanPresenceVerdict,
    InterviewAnswer,
    Media,
    PhotoMessage,
)
from tele_bot.gemini_services import DocumentaryServices
from tele_bot.state import PipelinePhase as Phase
from tele_bot.state import SessionDriver, SessionState


def message(author: str, text: str) -> Event:
    return Event(author=author, content=types.Content(role="model", parts=[types.Part(text=text)]))


def media_event(author: str, media: Media) -> Event:
    return Event(
        author=author,
        content=types.Content(
            role="model", parts=[types.Part.from_bytes(data=media.data, mime_type=media.mime_type)]
        ),
    )


class SpecialistAgent(BaseAgent):
    """Three discrete ADK specialists; each has one fixed capability."""

    _services: DocumentaryServices = PrivateAttr()
    _state: SessionDriver = PrivateAttr()

    def __init__(self, name: str, services: DocumentaryServices, state: SessionDriver) -> None:
        super().__init__(name=name)
        self._services = services
        self._state = state

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = self._state.get(int(ctx.session.user_id))
        if self.name == "bouncer":
            if state.photo is None:
                raise ValueError("Bouncer needs a photo")
            verdict = await self._services.classify(state.photo)
            yield message(self.name, verdict.model_dump_json())
        elif self.name == "converter":
            if state.photo is None or state.dossier is None:
                raise ValueError("Converter needs photo and dossier")
            yield media_event(self.name, await self._services.convert(state.photo, state.dossier))
        elif self.name == "scripter":
            if state.dossier is None:
                raise ValueError("Scripter needs dossier")
            script = await self._services.script(state.dossier)
            yield message(self.name, script.model_dump_json())
        else:
            raise ValueError("Unknown specialist")


class InterviewerAgent(BaseAgent):
    """Root agent: five interview turns, specialist delegation, then TTS."""

    _services: DocumentaryServices = PrivateAttr()
    _state: SessionDriver = PrivateAttr()

    def __init__(self, services: DocumentaryServices, state: SessionDriver) -> None:
        super().__init__(
            name="interviewer",
            sub_agents=[
                SpecialistAgent(name, services, state)
                for name in ("bouncer", "converter", "scripter")
            ],
        )
        self._services = services
        self._state = state

    def save(self, state: SessionState) -> None:
        self._state.save(state)

    async def specialist(self, name: str, ctx: InvocationContext) -> types.Part:
        agent = next(agent for agent in self.sub_agents if agent.name == name)
        result: types.Part | None = None
        async for event in agent.run_async(ctx):
            if event.content and event.content.parts:
                result = event.content.parts[0]
        # Exhaust the ADK generator in this task so its tracing context closes
        # here, rather than in a different async-generator finalizer task.
        if result is not None:
            return result
        raise ValueError(f"{name} returned no result")

    async def ask(self, state: SessionState) -> Event:
        turn = await self._services.question(state.answers)
        self.save(
            state.model_copy(update={"question": turn.question, "phase": Phase.AWAITING_INTERVIEW})
        )
        return message(self.name, f"Field notes {len(state.answers) + 1}/5: {turn.question}")

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        chat_id = int(ctx.session.user_id)
        state = self._state.get(chat_id)
        parts = ctx.user_content.parts if ctx.user_content and ctx.user_content.parts else []
        image = next((p.inline_data for p in parts if p.inline_data), None)
        text = " ".join(p.text for p in parts if p.text).strip()

        if state.phase is Phase.COMPLETE:
            yield message(self.name, "Documentary complete! Send /restart for a new expedition.")
            return

        if state.phase is Phase.AWAITING_PHOTO:
            if image is None or not image.data:
                yield message(self.name, "Send a clear portrait photo so I can study the specimen.")
                return
            photo = PhotoMessage(
                chat_id=chat_id,
                file_id=ctx.session.state.get("photo_file_id", "photo"),
                data=image.data,
                mime_type=image.mime_type or "image/jpeg",
            )
            state = state.model_copy(update={"photo": photo, "phase": Phase.CHECKING_PHOTO})
            self.save(state)
            yield message(self.name, "Inspecting the specimen...")

        # Retrying the Bouncer reuses the retained photo.
        if state.phase is Phase.CHECKING_PHOTO:
            part = await self.specialist("bouncer", ctx)
            verdict = HumanPresenceVerdict.model_validate_json(part.text or "")
            if not verdict.human_present:
                self._state.reset(chat_id)
                yield message(self.name, REJECTION_REPLY)
                return
            state = state.model_copy(update={"phase": Phase.AWAITING_INTERVIEW})
            self.save(state)
            yield message(
                self.name, "A human! Excellent. Five quick questions for our field research."
            )
            yield await self.ask(state)
            return

        if state.phase is Phase.AWAITING_INTERVIEW:
            if state.question is None:
                yield await self.ask(state)
                return
            if image is not None or not text or text.startswith("/"):
                yield message(
                    self.name,
                    "Please answer the current question with text, "
                    "or use /restart.\n" + state.question,
                )
                return
            if len(text) > 2000:
                yield message(self.name, "Keep your field notes under 2,000 characters, please.")
                return
            answers = (*state.answers, InterviewAnswer(question=state.question, answer=text))
            state = state.model_copy(update={"answers": answers, "question": None})
            if len(answers) == 5:
                state = state.model_copy(update={"phase": Phase.PROFILING})
            self.save(state)
            if state.phase is Phase.AWAITING_INTERVIEW:
                yield await self.ask(state)
                return

        if state.phase is Phase.PROFILING:
            yield message(self.name, "Compiling the behavioural dossier...")
            dossier = await self._services.profile(state.answers)
            state = state.model_copy(update={"dossier": dossier, "phase": Phase.CONVERTING})
            self.save(state)
            yield message(
                self.name, f"Your animal alter ego: {dossier.animal}. {dossier.rationale}"
            )

        if state.phase is Phase.CONVERTING:
            yield message(self.name, "Developing your hybrid portrait. This may take a minute...")
            part = await self.specialist("converter", ctx)
            if part.inline_data is None:
                raise ValueError("Converter returned no image")
            # Save the next phase only after the consumer successfully sends this event.
            yield Event(author=self.name, content=types.Content(role="model", parts=[part]))
            state = state.model_copy(update={"phase": Phase.SCRIPTING, "photo": None})
            self.save(state)

        if state.phase is Phase.SCRIPTING:
            part = await self.specialist("scripter", ctx)
            script = DocumentaryScript.model_validate_json(part.text or "")
            yield message(self.name, script.text)
            state = state.model_copy(update={"script": script, "phase": Phase.NARRATING})
            self.save(state)

        if state.phase is Phase.NARRATING:
            if state.script is None:
                raise ValueError("Narration needs a script")
            yield message(self.name, "Recording the documentary voiceover...")
            yield media_event(self.name, await self._services.narrate(state.script))
            self.save(SessionState(chat_id=chat_id, phase=Phase.COMPLETE))
            yield message(
                self.name, "Expedition complete! Use /restart to discover another creature."
            )
