"""The Bouncer wired into Google ADK as the pipeline's first agent.

The agent adapts ADK's invocation context (user id, photo content, session
state) into our typed contracts, runs the gate logic, and yields a model
event carrying the reply. Every value crossing into the gate is re-validated
through ``PhotoMessage`` here — the agent does not trust the caller.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.genai import types

from tele_bot.bouncer import Bouncer
from tele_bot.contracts import PhotoMessage
from tele_bot.logging_decorators import log_async_gen_call

logger = logging.getLogger(__name__)


class NoPhotoError(ValueError):
    """Raised when an invocation carries no valid user photo."""


class BouncerAgent(BaseAgent):
    """Gates a user's photo inside an ADK session.

    chat_id travels as the ADK session's ``user_id`` (Telegram sends it as a
    number, stored as a string); the photo arrives as inline ``user`` content;
    the original ``file_id`` rides in session state. All are validated into
    typed values before the gate runs.
    """

    def __init__(self, bouncer: Bouncer, name: str = "bouncer") -> None:
        super().__init__(name=name)
        self._bouncer = bouncer

    @log_async_gen_call(logger)
    async def _run_async_impl(self, ctx: object) -> AsyncGenerator[Event, None]:
        photo = self._photo_from_context(ctx)
        # The classifier is a sync Gemini call (bounded by its own timeout);
        # run it off the event loop so one photo never stalls every chat.
        result = await asyncio.to_thread(self._bouncer.handle, photo)
        yield Event(
            author=self.name,
            content=types.Content(role="model", parts=[types.Part(text=result.reply)]),
        )

    def _photo_from_context(self, ctx: object) -> PhotoMessage:
        chat_id = self._chat_id(ctx)
        file_id = self._file_id(ctx)
        mime_type, data = self._photo_bytes(ctx)
        return PhotoMessage(chat_id=chat_id, file_id=file_id, mime_type=mime_type, data=data)

    def _chat_id(self, ctx: object) -> int:
        user_id = getattr(getattr(ctx, "session", None), "user_id", None)
        if user_id is None:
            raise NoPhotoError("invocation has no session user_id")
        return int(user_id)  # Telegram chat ids are numbers

    def _file_id(self, ctx: object) -> str:
        state = getattr(getattr(ctx, "session", None), "state", None) or {}
        file_id = state.get("photo_file_id")
        if not file_id:
            raise NoPhotoError("session state carries no photo_file_id")
        return str(file_id)

    def _photo_bytes(self, ctx: object) -> tuple[str, bytes]:
        content = getattr(ctx, "user_content", None)
        if content is None or not getattr(content, "parts", None):
            raise NoPhotoError("invocation carries no user content")
        for part in content.parts:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                return str(inline.mime_type), bytes(inline.data)
        raise NoPhotoError("user content contains no inline image data")
