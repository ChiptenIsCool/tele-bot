"""Responsive Telegram adapter: one cancellable ADK operation per private chat."""

import asyncio
import io
import logging
import time
from contextlib import aclosing, suppress

from google.adk.runners import InMemoryRunner
from google.genai import types
from telegram import Bot, BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from agents.documentary_agent import InterviewerAgent
from tele_bot.contracts import PhotoMessage
from tele_bot.gemini_services import DocumentaryServices, GeminiServices, validate_image
from tele_bot.settings import Settings, load_settings
from tele_bot.state import PipelinePhase, SessionDriver

APP_NAME = "telegram_documentaries"
logger = logging.getLogger(__name__)
GREETING = (
    "Welcome to the Telegram Documentaries! Send a clear photo of yourself, "
    "answer five quick questions, and discover your animal alter ego — portrait and voiceover. "
    "Your photo and answers go to Google Gemini. Use /restart to begin again."
)


class SecretFormatter(logging.Formatter):
    """Redact SDK exception URLs and tracebacks as well as ordinary messages."""

    def __init__(self, secrets: tuple[str, ...]) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")
        self.secrets = secrets

    def format(self, record: logging.LogRecord) -> str:
        result = super().format(record)
        for secret in self.secrets:
            result = result.replace(secret, "[REDACTED]")
        return result


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(SecretFormatter((settings.telegram_bot_token, settings.gemini_api_key)))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    for name in ("httpx", "httpcore", "google_genai", "google.genai"):
        logging.getLogger(name).setLevel(logging.WARNING)


class DocumentaryRuntime:
    def __init__(self, services: DocumentaryServices) -> None:
        self.services = services
        self.state = SessionDriver()
        self.runner = InMemoryRunner(
            agent=InterviewerAgent(services, self.state), app_name=APP_NAME
        )
        self.jobs: dict[int, asyncio.Task[None]] = {}
        self.touched: dict[int, float] = {}

    def busy(self, chat_id: int) -> bool:
        job = self.jobs.get(chat_id)
        return job is not None and not job.done()

    async def clear_history(self, chat_id: int) -> None:
        uid = str(chat_id)
        if await self.runner.session_service.get_session(
            app_name=APP_NAME, user_id=uid, session_id=uid
        ):
            await self.runner.session_service.delete_session(
                app_name=APP_NAME, user_id=uid, session_id=uid
            )

    async def reset(self, chat_id: int) -> None:
        task = self.jobs.pop(chat_id, None)
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self.state.reset(chat_id)
        await self.clear_history(chat_id)
        self.touched[chat_id] = time.monotonic()

    async def dispatch(
        self, bot: Bot, chat_id: int, content: types.Content, file_id: str = ""
    ) -> None:
        self.touched[chat_id] = time.monotonic()
        if self.busy(chat_id):
            await bot.send_message(
                chat_id, "I'm still working on that stage. You can use /restart to cancel it."
            )
            return
        self.jobs[chat_id] = asyncio.create_task(self.run(bot, chat_id, content, file_id))

    async def run(self, bot: Bot, chat_id: int, content: types.Content, file_id: str) -> None:
        try:
            uid = str(chat_id)
            if not await self.runner.session_service.get_session(
                app_name=APP_NAME, user_id=uid, session_id=uid
            ):
                await self.runner.session_service.create_session(
                    app_name=APP_NAME, user_id=uid, session_id=uid
                )
            events = self.runner.run_async(
                user_id=uid,
                session_id=uid,
                new_message=content,
                state_delta={"photo_file_id": file_id},
            )
            async with aclosing(events):
                async for event in events:
                    if event.author != "interviewer" or event.content is None:
                        continue
                    for part in event.content.parts or []:
                        if part.text:
                            await bot.send_message(chat_id, part.text)
                        elif part.inline_data and part.inline_data.data:
                            media = part.inline_data
                            buffer = io.BytesIO(media.data or b"")
                            if media.mime_type and media.mime_type.startswith("image/"):
                                buffer.name = "animal-portrait.png"
                                await bot.send_photo(chat_id, buffer, write_timeout=60)
                            elif media.mime_type == "audio/ogg":
                                buffer.name = "documentary.ogg"
                                await bot.send_voice(chat_id, buffer, write_timeout=60)
        except Exception as exc:
            logger.exception(
                "pipeline.failed chat_id=%d phase=%s", chat_id, self.state.get(chat_id).phase.value
            )
            status = getattr(exc, "code", None)
            detail = (
                "The Gemini API quota is exhausted; check billing/quota before retrying. "
                if status == 429
                else "That stage couldn't finish. "
            )
            with suppress(Exception):
                await bot.send_message(
                    chat_id, detail + "Use /retry to resume or /restart for a new run."
                )
        finally:
            self.touched[chat_id] = time.monotonic()
            # ADK history can retain original photo bytes. Retain only typed pipeline
            # state between turns: no model here depends on ADK conversation history.
            await self.clear_history(chat_id)

    async def expire(self, bot: Bot) -> None:
        while True:
            await asyncio.sleep(30)
            for chat_id, touched in list(self.touched.items()):
                if time.monotonic() - touched > 3600:
                    await self.reset(chat_id)
                    self.state.discard(chat_id)
                    self.touched.pop(chat_id, None)
                    with suppress(Exception):
                        await bot.send_message(
                            chat_id,
                            "Your expedition expired after an hour. Use /start for a fresh one.",
                        )

    async def close(self) -> None:
        for chat_id in list(self.jobs):
            await self.reset(chat_id)
        await self.services.close()


def runtime(context: ContextTypes.DEFAULT_TYPE) -> DocumentaryRuntime:
    value = context.bot_data["runtime"]
    if not isinstance(value, DocumentaryRuntime):
        raise TypeError("documentary runtime not initialized")
    return value


async def reset_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return
    await runtime(context).reset(update.effective_chat.id)
    await context.bot.send_message(update.effective_chat.id, GREETING)


async def input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat, msg = update.effective_chat, update.effective_message
    if chat is None or msg is None:
        return
    engine = runtime(context)
    if engine.busy(chat.id):
        await context.bot.send_message(
            chat.id, "Still studying the specimen! Wait a moment, or use /restart to cancel."
        )
        return
    state = engine.state.get(chat.id)
    if msg.photo and state.phase is PipelinePhase.AWAITING_PHOTO:
        photo = msg.photo[-1]
        if photo.file_size and photo.file_size > 10 * 1024 * 1024:
            await context.bot.send_message(chat.id, "Please send a photo smaller than 10 MB.")
            return
        file = await context.bot.get_file(photo.file_id)
        data = bytes(await file.download_as_bytearray())
        mime = await asyncio.to_thread(validate_image, data)
        validated = PhotoMessage(chat_id=chat.id, file_id=photo.file_id, data=data, mime_type=mime)
        await engine.dispatch(
            context.bot,
            chat.id,
            types.Content(
                role="user",
                parts=[types.Part.from_bytes(data=validated.data, mime_type=validated.mime_type)],
            ),
            photo.file_id,
        )
        return
    if msg.photo:
        await context.bot.send_message(
            chat.id,
            "Please finish the current question with text, "
            "or use /restart.\n" + (state.question or ""),
        )
        return
    text = msg.text or ""
    if text == "/retry" or text.startswith("/retry@"):
        text = "/retry"
    elif state.phase not in {
        PipelinePhase.AWAITING_PHOTO,
        PipelinePhase.AWAITING_INTERVIEW,
        PipelinePhase.COMPLETE,
    }:
        await context.bot.send_message(chat.id, "Use /retry to resume generation or /restart.")
        return
    if not text:
        await context.bot.send_message(
            chat.id, "Send a portrait photo to begin, or a text answer during the interview."
        )
        return
    await engine.dispatch(
        context.bot, chat.id, types.Content(role="user", parts=[types.Part(text=text)])
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        await context.bot.send_message(
            update.effective_chat.id,
            "/start or /restart — clear your session and begin\n"
            "/retry — retry a failed stage\n"
            "Send a portrait, answer five questions, "
            "then receive your image, script and voiceover.",
        )


async def group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        await context.bot.send_message(
            update.effective_chat.id, "Please message me privately to make your documentary."
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("telegram.failed type=%s", type(context.error).__name__)
    if isinstance(update, Update) and update.effective_chat:
        with suppress(Exception):
            await context.bot.send_message(
                update.effective_chat.id,
                "I couldn't process that message. Try again, or use /restart.",
            )


def build_application(settings: Settings) -> Application:  # type: ignore[type-arg]
    engine = DocumentaryRuntime(GeminiServices(settings))
    expiry: asyncio.Task[None] | None = None

    async def startup(app: Application) -> None:  # type: ignore[type-arg]
        nonlocal expiry
        me = await app.bot.get_me()
        await app.bot.set_my_commands(
            [
                BotCommand("start", "Start a documentary"),
                BotCommand("restart", "Reset and start again"),
                BotCommand("retry", "Retry a failed stage"),
                BotCommand("help", "Show help"),
            ]
        )
        expiry = asyncio.create_task(engine.expire(app.bot))
        logger.info("Documentary bot @%s online; long polling active", me.username)

    async def shutdown(app: Application) -> None:  # type: ignore[type-arg]
        if expiry:
            expiry.cancel()
            with suppress(asyncio.CancelledError):
                await expiry
        await engine.close()

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(startup)
        .post_stop(shutdown)
        .build()
    )
    app.bot_data["runtime"] = engine
    private = filters.ChatType.PRIVATE
    app.add_handler(MessageHandler(~private, group_handler))
    app.add_handler(CommandHandler(["start", "restart"], reset_handler, filters=private))
    app.add_handler(CommandHandler("retry", input_handler, filters=private))
    app.add_handler(CommandHandler("help", help_handler, filters=private))
    app.add_handler(MessageHandler(private & ~filters.COMMAND, input_handler))
    app.add_handler(MessageHandler(private & filters.COMMAND, help_handler))
    app.add_error_handler(error_handler)
    return app


def main() -> None:
    settings = load_settings()
    configure_logging(settings)
    build_application(settings).run_polling(drop_pending_updates=False)
