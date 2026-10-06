"""Long-polling gateway: Telegram update -> download -> gate -> reply.

This is the process entry point (``python3 -m tele_bot.main``). The PTB
handler is a thin adapter: it downloads the photo, hands bytes + file_id to
the Bouncer agent running inside ADK, and sends back whatever reply the agent
produces — the 'photo -> download -> validate -> Bouncer -> reply' route.
"""

import logging

from google.adk.runners import InMemoryRunner
from google.genai import types
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from agents.bouncer_agent import BouncerAgent
from tele_bot.bouncer import Bouncer
from tele_bot.contracts import PhotoMessage
from tele_bot.gemini_classifier import GeminiHumanPresenceClassifier
from tele_bot.settings import Settings, SettingsError, load_settings
from tele_bot.state import SessionDriver
from tele_bot.telegram_io import download_photo_bytes, sniff_image_mime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

APP_NAME = "telegram_documentaries"
NO_REPLY_FALLBACK = "I couldn't make that out — try sending a photo again."


def build_pipeline(settings: Settings) -> tuple[InMemoryRunner, SessionDriver]:
    """Wire the ADK pipeline: Bouncer agent + shared in-memory session state."""
    state = SessionDriver()
    classifier = GeminiHumanPresenceClassifier(settings.gemini_api_key)
    agent = BouncerAgent(bouncer=Bouncer(classifier, state))
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    return runner, state


async def ensure_session(runner: InMemoryRunner, chat_id: int) -> None:
    """ADK requires the session to exist before the agent can run."""
    uid = str(chat_id)
    existing = await runner.session_service.get_session(
        app_name=APP_NAME, user_id=uid, session_id=uid
    )
    if existing is None:
        await runner.session_service.create_session(app_name=APP_NAME, user_id=uid, session_id=uid)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Download -> validate -> Bouncer -> reply, inside the ADK runner."""
    if update.effective_chat is None or update.message is None or update.message.photo is None:
        logger.warning("photo update missing chat/message/photo — ignoring")
        return
    chat_id = update.effective_chat.id
    file_id = update.message.photo[-1].file_id
    if "runner" not in context.bot_data:
        logger.error("runner missing from bot_data — pipeline not initialised")
        return
    runner: InMemoryRunner = context.bot_data["runner"]

    data = await download_photo_bytes(context.bot, file_id)
    # Validate as soon as the bytes leave Telegram — before Gemini or ADK see
    # them (SPECS/TECH.md: parse at the edge). The agent re-validates too.
    mime_type = sniff_image_mime(data)
    PhotoMessage(chat_id=chat_id, file_id=file_id, mime_type=mime_type, data=data)
    await ensure_session(runner, chat_id)

    content = types.Content(
        role="user",
        parts=[types.Part.from_bytes(data=data, mime_type=mime_type)],
    )
    reply = NO_REPLY_FALLBACK
    async for event in runner.run_async(
        user_id=str(chat_id),
        session_id=str(chat_id),
        new_message=content,
        state_delta={"photo_file_id": file_id},
    ):
        if event.content and event.content.parts and event.content.parts[0].text:
            reply = event.content.parts[0].text

    await context.bot.send_message(chat_id=chat_id, text=reply)


async def handle_photo_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Conversation path: never raise into the user's flow (SPECS/TECH.md)."""
    try:
        await handle_photo(update, context)
    except Exception:
        chat = update.effective_chat
        logger.exception("photo handling failed chat_id=%s", chat.id if chat else None)
        if chat is not None:
            await context.bot.send_message(
                chat_id=chat.id,
                text="Something went wrong on my end — try sending the photo again.",
            )


def main() -> None:
    """Boot the polling process (long polling only — no webhooks)."""
    try:
        settings = load_settings()
    except SettingsError as exc:
        logger.error("Cannot start: %s", exc)
        raise SystemExit(1) from exc

    runner, state = build_pipeline(settings)
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data["runner"] = runner
    app.bot_data["state"] = state

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_wrapper))
    logger.info("Bouncer online — polling Telegram for photos...")
    app.run_polling()


if __name__ == "__main__":
    main()
