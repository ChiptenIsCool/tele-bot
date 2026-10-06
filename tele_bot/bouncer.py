"""The Bouncer: the pipeline's vision gate (Roadmap Phase 2).

A photo comes in; a human either is or isn't in it. No human -> cheeky
rejection and the session resets. Human -> brief confirmation and the
conversation moves on to the interview.
"""

import logging
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from tele_bot.contracts import HumanPresenceVerdict, PhotoMessage
from tele_bot.logging_decorators import log_call
from tele_bot.state import PipelinePhase, SessionDriver

logger = logging.getLogger(__name__)

REJECTION_REPLY = (
    "Sorry, mate — this is a wildlife documentary, not a still-life. "
    "I need a human in the frame: send me a photo with an actual person "
    "in it and I'll take it from there."
)

CONFIRMATION_REPLY = "Right then — one human, duly noted. Let's get started."

UNSURE_REPLY = (
    "Hmm, my eyes aren't what they were — I couldn't make out a human in "
    "that one. Mind sending it again?"
)


class BouncerResult(BaseModel):
    """What the gate decided. A typed result, never a bare string."""

    model_config = ConfigDict(frozen=True)

    admitted: bool
    reply: str


class HumanPresenceClassifier(Protocol):
    """Anything that can answer 'is there a human in this photo?'.

    Declared so tests and the Gemini implementation share one shape; the
    Bouncer never imports the Gemini client itself.
    """

    def classify(self, photo: PhotoMessage) -> HumanPresenceVerdict: ...


class Bouncer:
    """Runs the vision gate and applies its verdict to session state."""

    def __init__(self, classifier: HumanPresenceClassifier, state: SessionDriver) -> None:
        self._classifier = classifier
        self._state = state

    @log_call(logger)
    def handle(self, photo: PhotoMessage) -> BouncerResult:
        """Gate one photo. Never raises on the user's conversation path."""
        try:
            verdict = self._classify(photo)
        except Exception:
            # Logged loudly by the @log_call on _classify. On a validated
            # user's path we degrade instead of raising (TECH.md error policy).
            return self._reject(photo, UNSURE_REPLY, cause="classification_failed")

        if verdict.human_present:
            self._state.advance(photo.chat_id, PipelinePhase.AWAITING_INTERVIEW)
            logger.info("bouncer.admitted chat_id=%d reason=%s", photo.chat_id, verdict.reason)
            return BouncerResult(admitted=True, reply=CONFIRMATION_REPLY)

        return self._reject(photo, REJECTION_REPLY, cause="no_human")

    @log_call(logger)
    def _classify(self, photo: PhotoMessage) -> HumanPresenceVerdict:
        """Logs the call and any classification failure at ERROR, then re-raises.

        ``handle`` catches the re-raised error and degrades on the user's path.
        """
        return self._classifier.classify(photo)

    def _reject(self, photo: PhotoMessage, reply: str, *, cause: str) -> BouncerResult:
        """Reset this chat's session and answer. Other chats are untouched."""
        self._state.reset(photo.chat_id)
        logger.info("bouncer.rejected chat_id=%d cause=%s", photo.chat_id, cause)
        return BouncerResult(admitted=False, reply=reply)
