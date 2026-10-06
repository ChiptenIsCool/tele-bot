"""Typed contracts at the Telegram, Gemini and media boundaries.

SPECS/TECH.md: treat all external input as untrusted and arbitrary. Every
payload crossing a module boundary is parsed into one of these models first;
raw dicts never travel further.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Telegram bot photo downloads are capped at 10 MB; anything larger is either
# not a photo this pipeline wants or a hostile payload.
MAX_IMAGE_BYTES = 10 * 1024 * 1024

_IMAGE_PREFIX = "image/"


class PhotoMessage(BaseModel):
    """A user's uploaded photo, validated the moment it leaves Telegram.

    chat_id is deliberately an ``int``: Telegram sends it as a number, and a
    string/int mismatch would silently break session lookups.
    """

    model_config = ConfigDict(frozen=True)

    chat_id: int = Field(strict=True)
    file_id: str = Field(min_length=1)
    mime_type: str
    data: bytes = Field(min_length=1, max_length=MAX_IMAGE_BYTES)

    @field_validator("mime_type")
    @classmethod
    def _must_be_an_image(cls, value: str) -> str:
        if not value.startswith(_IMAGE_PREFIX):
            raise ValueError(f"expected an image/* content type, got {value!r}")
        return value


class HumanPresenceVerdict(BaseModel):
    """Gemini's structured answer to 'is a human in this picture?'.

    Parsed strictly at the boundary so a model that returns something odd
    fails here — loudly — instead of flowing downstream as a raw dict.
    """

    model_config = ConfigDict(frozen=True)

    human_present: bool = Field(strict=True)
    reason: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
