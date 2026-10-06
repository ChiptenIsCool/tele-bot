"""The Gemini 3.1 Flash Lite classifier backing the Bouncer.

Kept out of ``bouncer.py`` so the gate's logic stays free of SDK imports and
is mocked cleanly in tests. The response is parsed with a strict schema at
the boundary (``HumanPresenceVerdict``); nothing past this point is a dict.
"""

import logging

from google.genai import types
from google.genai.client import Client
from google.genai.errors import ClientError

from tele_bot.contracts import HumanPresenceVerdict, PhotoMessage
from tele_bot.logging_decorators import log_call

logger = logging.getLogger(__name__)

GEMINI_FLASH_LITE_MODEL = "gemini-3.1-flash-lite"

_PROMPT = (
    "Analyze this photo. Is a discernible human face or human body present? "
    "Reply in JSON only, exactly matching the given schema: "
    '{"human_present": true/false, "reason": "short justification", '
    '"confidence": 0.0-1.0}. Photos of animals, landscapes, objects, or empty '
    "frames mean human_present=false. Cartoons and drawings of humans still "
    "count as humans."
)


class GeminiClassifierError(RuntimeError):
    """Raised when Gemini cannot answer. Never swallowed silently."""


class GeminiHumanPresenceClassifier:
    """Classifies whether a photo contains a human, via Gemini Flash Lite."""

    def __init__(self, api_key: str, model: str = GEMINI_FLASH_LITE_MODEL) -> None:
        self._client = Client(api_key=api_key)
        self._model = model

    @log_call(logger)
    def classify(self, photo: PhotoMessage) -> HumanPresenceVerdict:
        """Ask Gemini whether a human is in the photo and parse the verdict.

        Raises GeminiClassifierError on transport failure or unparseable
        output; the Bouncer degrades gracefully on the user's path.
        """
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_bytes(data=photo.data, mime_type=photo.mime_type),
                    _PROMPT,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=HumanPresenceVerdict,
                ),
            )
        except ClientError as exc:
            raise GeminiClassifierError(f"Gemini API error: {exc}") from exc

        raw_text = getattr(response, "text", None)
        if raw_text is None:
            raise GeminiClassifierError("Gemini returned no text content")

        return self._parse(raw_text)

    def _parse(self, text: str) -> HumanPresenceVerdict:
        """Parse Gemini's JSON body into the boundary model."""
        try:
            return HumanPresenceVerdict.model_validate_json(text)
        except Exception as exc:
            raise GeminiClassifierError(f"Gemini returned unparseable verdict: {exc}") from exc
