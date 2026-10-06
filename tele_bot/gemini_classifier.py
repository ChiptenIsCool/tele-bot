"""The Gemini 3.1 Flash Lite classifier backing the Bouncer.

Kept out of ``bouncer.py`` so the gate's logic stays free of SDK imports and
is mocked cleanly in tests. The response is parsed with a strict schema at
the boundary (``HumanPresenceVerdict``); nothing past this point is a dict.
"""

import logging

from google.genai import types
from google.genai.client import Client
from google.genai.errors import ClientError, ServerError

from tele_bot.contracts import HumanPresenceVerdict, PhotoMessage
from tele_bot.logging_decorators import log_call

logger = logging.getLogger(__name__)

GEMINI_FLASH_LITE_MODEL = "gemini-3.1-flash-lite"

# Gemini is a bounded side-effect of the gate; without a cap the polling loop
# (or a thread borrowing its semantics) can stall for a long as the SDK lets
# it. 30 s is generous for a small JSON verdict and still bounded.
_REQUEST_TIMEOUT_MS = 30_000

_PROMPT = (
    "Analyze this photo. Is a discernible human face or human body present? "
    "Reply in JSON only, exactly matching the given schema: "
    '{"human_present": true/false, "reason": "short justification", '
    '"confidence": 0.0-1.0}. Photos of animals, landscapes, objects, or empty '
    "frames mean human_present=false. Cartoons and drawings of humans still "
    "count as humans."
)


def _verdict_schema() -> dict[str, object]:
    """The Gemini response schema, without pydantic's internal keys.

    ``model_json_schema()`` on a model with ``extra="forbid"`` includes
    ``additionalProperties: false``; the Gemini API rejects that field
    (''Invalid JSON payload ... Unknown name "additional_properties"'').
    The model keeps its strictness for our own parsing; only the wire schema
    is sanitised.
    """
    schema = HumanPresenceVerdict.model_json_schema()
    schema.pop("additionalProperties", None)
    # pydantic's definitions live under $defs and may repeat the key.
    for definition in schema.get("$defs", {}).values():
        if isinstance(definition, dict):
            definition.pop("additionalProperties", None)
    return schema


class GeminiClassifierError(RuntimeError):
    """Raised when Gemini cannot answer. Never swallowed silently."""


class GeminiHumanPresenceClassifier:
    """Classifies whether a photo contains a human, via Gemini Flash Lite."""

    def __init__(
        self,
        api_key: str,
        model: str = GEMINI_FLASH_LITE_MODEL,
        client: Client | None = None,
    ) -> None:
        self._client = client or Client(
            api_key=api_key, http_options={"timeout": _REQUEST_TIMEOUT_MS}
        )
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
                    response_schema=_verdict_schema(),
                ),
            )
        except ClientError as exc:
            raise GeminiClassifierError(f"Gemini API error: {exc}") from exc
        except ServerError as exc:
            # 5xx / transient — the gate must survive these, loud and reset.
            raise GeminiClassifierError(f"Gemini API unavailable: {exc}") from exc

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
