"""Media and SDK contract regressions, including real local Opus encoding."""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image, UnidentifiedImageError

from tele_bot.contracts import HumanPresenceVerdict, InterviewTurn
from tele_bot.gemini_services import (
    EmptySpeechError,
    GeminiServices,
    encode_voice,
    response_schema,
    validate_image,
)
from tele_bot.settings import Settings


def test_gemini_schema_strips_unsupported_keyword_but_local_contract_stays_strict() -> None:
    assert "additionalProperties" not in response_schema(HumanPresenceVerdict)
    with pytest.raises(ValueError):
        HumanPresenceVerdict.model_validate_json(
            '{"human_present": true, "reason": "human", "extra": 123}'
        )


def test_interview_output_must_be_one_question() -> None:
    with pytest.raises(ValueError):
        InterviewTurn(question="When do you wake? What do you eat?")


def test_image_bytes_are_verified() -> None:
    with pytest.raises(UnidentifiedImageError):
        validate_image(b"\xff\xd8\xffbroken image")
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "blue").save(buffer, format="PNG")
    assert validate_image(buffer.getvalue()) == "image/png"


@pytest.mark.parametrize(
    "mime", ["audio/L16;codec=pcm;rate=24000", "audio/l16; rate=24000; channels=1"]
)
async def test_pcm_to_real_ogg_opus(mime: str) -> None:
    # 0.2 seconds of silence still produces a valid Opus stream.
    voice = await encode_voice(b"\x00\x00" * 4800, mime)
    assert voice.data.startswith(b"OggS")
    assert b"OpusHead" in voice.data
    assert voice.mime_type == "audio/ogg"


async def test_odd_length_pcm_rejected_before_encoding() -> None:
    with pytest.raises(ValueError, match="truncated"):
        await encode_voice(b"123", "audio/L16;rate=24000")


async def test_structured_output_gets_one_correction_on_invalid_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = GeminiServices(
        Settings(_env_file=None, telegram_bot_token="test", gemini_api_key="test")
    )
    generate = AsyncMock(
        side_effect=[
            SimpleNamespace(text='{"question":"What do you eat? When do you sleep?"}'),
            SimpleNamespace(text='{"question":"What do you eat for breakfast?"}'),
        ]
    )
    monkeypatch.setattr(services.client.aio.models, "generate_content", generate)
    try:
        turn = await services.question(())
        assert turn.question == "What do you eat for breakfast?"
        assert generate.await_count == 2
        config = generate.call_args.kwargs["config"]
        assert "previous result violated" in config.system_instruction
    finally:
        await services.close()


async def test_empty_tts_response_gets_one_bounded_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    from tele_bot.contracts import DocumentaryScript, Media

    services = GeminiServices(
        Settings(_env_file=None, telegram_bot_token="test", gemini_api_key="test")
    )
    speak = AsyncMock(
        side_effect=[EmptySpeechError("no audio"), Media(data=b"OggSvoice", mime_type="audio/ogg")]
    )
    monkeypatch.setattr(services, "_narrate_once", speak)
    try:
        script = DocumentaryScript(
            text=" ".join(
                ["The curious badger searches its habitat for another midnight snack."] * 6
            )
        )
        assert (await services.narrate(script)).data.startswith(b"OggS")
        assert speak.await_count == 2
    finally:
        await services.close()
