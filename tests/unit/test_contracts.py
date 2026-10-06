"""Task group 3: boundary contracts — untrusted input fails loudly at the edge.

SPECS/TECH.md: Telegram updates, Gemini responses and user photos are all
untrusted. Every boundary crossing is validated by a Pydantic model before
anything else touches it.
"""

import pytest
from pydantic import ValidationError

from tele_bot.contracts import MAX_IMAGE_BYTES, HumanPresenceVerdict, PhotoMessage

JPEG = b"\xff\xd8\xff\xe0fakejpeg"


def _photo(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "chat_id": 7,
        "file_id": "photo-1",
        "mime_type": "image/jpeg",
        "data": JPEG,
    }
    base.update(overrides)
    return base


# --- PhotoMessage ---------------------------------------------------------


def test_valid_photo_message_is_accepted() -> None:
    photo = PhotoMessage.model_validate(_photo())

    assert photo.chat_id == 7
    assert photo.data == JPEG


def test_empty_bytes_are_rejected() -> None:
    with pytest.raises(ValidationError):
        PhotoMessage.model_validate(_photo(data=b""))


def test_non_image_mime_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PhotoMessage.model_validate(_photo(mime_type="text/html"))


def test_oversized_image_is_rejected_before_any_model_call() -> None:
    with pytest.raises(ValidationError):
        PhotoMessage.model_validate(_photo(data=b"x" * (MAX_IMAGE_BYTES + 1)))


def test_empty_file_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PhotoMessage.model_validate(_photo(file_id=""))


def test_missing_field_is_rejected() -> None:
    incomplete = _photo()
    del incomplete["data"]

    with pytest.raises(ValidationError):
        PhotoMessage.model_validate(incomplete)


def test_chat_id_must_be_an_int_not_a_str() -> None:
    """A string chat_id would silently break session lookups (TECH.md)."""
    with pytest.raises(ValidationError):
        PhotoMessage.model_validate(_photo(chat_id="7"))


# --- HumanPresenceVerdict -------------------------------------------------


def test_valid_verdict_is_accepted() -> None:
    verdict = HumanPresenceVerdict.model_validate(
        {"human_present": True, "confidence": 0.97, "reason": "a person is visible"}
    )

    assert verdict.human_present is True
    assert verdict.confidence == pytest.approx(0.97)


def test_verdict_may_omit_confidence() -> None:
    verdict = HumanPresenceVerdict.model_validate(
        {"human_present": False, "reason": "only mountains"}
    )

    assert verdict.confidence is None


def test_verdict_requires_a_reason() -> None:
    with pytest.raises(ValidationError):
        HumanPresenceVerdict.model_validate({"human_present": True})


def test_verdict_rejects_confidence_outside_zero_one() -> None:
    with pytest.raises(ValidationError):
        HumanPresenceVerdict.model_validate(
            {"human_present": True, "confidence": 4.2, "reason": "sure"}
        )


def test_verdict_rejects_a_truthy_string_for_human_present() -> None:
    """Gemini output must be a real bool, not 'yes' leaking through."""
    with pytest.raises(ValidationError):
        HumanPresenceVerdict.model_validate({"human_present": "yes", "reason": "hmm"})


def test_verdict_parses_strictly_from_json_text() -> None:
    """The boundary parse for Gemini's response body — no raw dicts past here."""
    verdict = HumanPresenceVerdict.model_validate_json(
        '{"human_present": false, "reason": "a very good cat"}'
    )

    assert verdict.human_present is False


def test_malformed_json_from_the_model_raises_rather_than_passing_through() -> None:
    with pytest.raises(ValidationError):
        HumanPresenceVerdict.model_validate_json("{not json")
