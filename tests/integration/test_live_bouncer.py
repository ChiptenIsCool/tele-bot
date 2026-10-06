"""Task group 6: LIVE integration check against real Gemini.

Skipped automatically when ``GEMINI_API_KEY`` is absent so scripts/test stays
green offline. With a key it confirms the Bouncer's two required behaviours
end-to-end using real generated images: a landscape (no human -> reject) and
a person (human -> admit).

Run it explicitly with: pytest tests/integration -m live
"""

import io

import pytest
from PIL import Image, ImageDraw  # type: ignore[import-untyped]

from tele_bot.bouncer import Bouncer
from tele_bot.contracts import PhotoMessage
from tele_bot.gemini_classifier import GeminiHumanPresenceClassifier
from tele_bot.settings import SettingsError, load_settings
from tele_bot.state import PipelinePhase, SessionDriver

try:
    GEMINI_API_KEY = load_settings().gemini_api_key
except SettingsError:
    pytest.skip("GEMINI_API_KEY not set (offline suite)", allow_module_level=True)

pytestmark = pytest.mark.live


def _landscape_jpeg() -> bytes:
    """An unmistakably empty landscape: sky, sun, hills. No living thing."""
    img = Image.new("RGB", (640, 480), (135, 206, 235))  # sky blue
    draw = ImageDraw.Draw(img)
    draw.ellipse((480, 60, 560, 140), fill=(255, 230, 0))  # sun
    draw.polygon([(0, 480), (160, 260), (320, 480)], fill=(34, 139, 34))  # hills
    draw.polygon([(220, 480), (420, 220), (620, 480)], fill=(46, 139, 87))
    draw.rectangle((0, 400, 640, 480), fill=(60, 179, 113))  # grass
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _person_jpeg() -> bytes:
    """A clearly discernible human figure: head, hair, torso, arms, legs."""
    img = Image.new("RGB", (640, 480), (240, 248, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse((280, 60, 380, 160), fill=(120, 81, 45))  # hair
    draw.ellipse((285, 90, 375, 185), fill=(255, 224, 189))  # face
    draw.ellipse((305, 120, 320, 135), fill=(30, 30, 30))  # eye
    draw.ellipse((355, 120, 370, 135), fill=(30, 30, 30))  # eye
    draw.arc((310, 135, 365, 165), start=20, end=160, fill=(180, 60, 60), width=4)  # smile
    draw.polygon([(285, 190), (395, 190), (440, 330), (240, 330)], fill=(70, 110, 220))  # torso
    draw.polygon([(240, 300), (170, 360), (185, 380), (255, 340)], fill=(70, 110, 220))  # arm
    draw.polygon([(440, 300), (510, 360), (495, 380), (425, 340)], fill=(70, 110, 220))  # arm
    draw.rectangle((260, 330, 300, 460), fill=(60, 60, 60))  # leg
    draw.rectangle((340, 330, 380, 460), fill=(60, 60, 60))  # leg
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _photo(data: bytes, chat_id: int) -> PhotoMessage:
    return PhotoMessage(chat_id=chat_id, file_id="live", mime_type="image/jpeg", data=data)


def test_live_landscape_is_rejected_and_state_resets() -> None:
    driver = SessionDriver()
    driver.advance(1, PipelinePhase.AWAITING_INTERVIEW)
    bouncer = Bouncer(GeminiHumanPresenceClassifier(GEMINI_API_KEY), driver)

    result = bouncer.handle(_photo(_landscape_jpeg(), chat_id=1))

    assert result.admitted is False, f"landscape should be rejected, got: {result.reply}"
    assert driver.get(1).phase is PipelinePhase.AWAITING_PHOTO


def test_live_person_is_confirmed_and_state_advances() -> None:
    driver = SessionDriver()
    bouncer = Bouncer(GeminiHumanPresenceClassifier(GEMINI_API_KEY), driver)

    result = bouncer.handle(_photo(_person_jpeg(), chat_id=2))

    assert result.admitted is True, f"person should be admitted, got: {result.reply}"
    assert driver.get(2).phase is PipelinePhase.AWAITING_INTERVIEW
