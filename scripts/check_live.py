"""Opt-in live smoke check. Makes small billable calls, sends no Telegram messages."""

import asyncio
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402
from telegram import Bot  # noqa: E402

from tele_bot.contracts import InterviewAnswer, PhotoMessage  # noqa: E402
from tele_bot.gateway import configure_logging  # noqa: E402
from tele_bot.gemini_services import GeminiServices  # noqa: E402
from tele_bot.settings import load_settings  # noqa: E402


async def main() -> None:
    settings = load_settings()
    configure_logging(settings)
    async with Bot(settings.telegram_bot_token) as bot:
        me = await bot.get_me()
        webhook = await bot.get_webhook_info()
        print(f"Telegram OK: @{me.username}; webhook configured: {bool(webhook.url)}", flush=True)
    services = GeminiServices(settings)
    failures: list[str] = []

    try:
        question = await services.question(())
        print("Interviewer OK: " + question.question, flush=True)
        answers = tuple(
            InterviewAnswer(question=question, answer=answer)
            for question, answer in (
                ("When do you sleep?", "I stay up late and wake at noon."),
                ("What do you eat?", "I collect biscuits and drink coffee."),
                ("How do you socialize?", "I prefer a small group of close friends."),
                ("What is your routine?", "I code in a messy room and take evening walks."),
                ("What is your quirk?", "I carefully organize cables but lose my keys."),
            )
        )
        dossier = await services.profile(answers)
        print("Dossier OK; animal=" + dossier.animal, flush=True)
        script = await services.script(dossier)
        print(f"Scripter OK; words={len(script.text.split())}", flush=True)
        image = Image.new("RGB", (512, 512), "lightblue")
        draw = ImageDraw.Draw(image)
        draw.ellipse((170, 60, 340, 230), fill="peachpuff")
        draw.ellipse((210, 120, 225, 135), fill="black")
        draw.ellipse((285, 120, 300, 135), fill="black")
        draw.arc((220, 150, 290, 195), 0, 180, fill="black", width=4)
        draw.rectangle((140, 230, 370, 510), fill="navy")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        photo = PhotoMessage(
            chat_id=0, file_id="synthetic-smoke-test", data=buffer.getvalue(), mime_type="image/png"
        )

        async def vision() -> None:
            verdict = await services.classify(photo)
            print(f"Vision OK; synthetic drawing human={verdict.human_present}", flush=True)

        async def convert() -> None:
            portrait = await services.convert(photo, dossier)
            print(f"Converter OK; {portrait.mime_type}; bytes={len(portrait.data)}", flush=True)

        async def narrate() -> None:
            voice = await services.narrate(script)
            print(f"Narrator OK; {voice.mime_type}; bytes={len(voice.data)}", flush=True)

        results = await asyncio.gather(vision(), convert(), narrate(), return_exceptions=True)
        for name, result in zip(("Vision", "Converter", "Narrator"), results, strict=True):
            if isinstance(result, BaseException):
                failures.append(name)
                safe = str(result).replace(settings.gemini_api_key, "[REDACTED]")
                safe = safe.replace(settings.telegram_bot_token, "[REDACTED]")
                print(name + " FAILED: " + safe[:1000], flush=True)
    finally:
        await services.close()
    if failures:
        raise SystemExit("Failed checks: " + ", ".join(failures))


if __name__ == "__main__":
    asyncio.run(main())
