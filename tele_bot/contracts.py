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

    model_config = ConfigDict(frozen=True, extra="forbid")

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

    model_config = ConfigDict(frozen=True, extra="forbid")

    human_present: bool = Field(strict=True)
    reason: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def _reject_boolean_confidence(cls, value: object) -> object:
        """``True`` coerces to ``1.0`` under lax mode — a verdict, not a float."""
        if isinstance(value, bool):
            raise ValueError("confidence must be a number, not a boolean")
        return value


class InterviewTurn(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    question: str = Field(min_length=5, max_length=500)

    @field_validator("question")
    @classmethod
    def _one_question(cls, value: str) -> str:
        if value.count("?") != 1 or "\n" in value:
            raise ValueError("ask exactly one question on one line")
        return value


class InterviewAnswer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=2000)


class Dossier(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    summary: str = Field(min_length=10, max_length=3000)
    animal: str = Field(min_length=2, max_length=100)
    rationale: str = Field(min_length=5, max_length=500)


class DocumentaryScript(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    text: str

    @field_validator("text")
    @classmethod
    def _one_paragraph(cls, value: str) -> str:
        value = value.strip()
        if "\n" in value or not 60 <= len(value.split()) <= 90:
            raise ValueError("script must be one paragraph of 60–90 words")
        return value


class Media(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    data: bytes = Field(min_length=1, max_length=20 * 1024 * 1024)
    mime_type: str = Field(pattern=r"^(image/(png|jpeg|webp)|audio/ogg)$")
