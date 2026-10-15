"""Session state: versioned, per-chat_id, mutated only by the shared driver.

SPECS/TECH.md: one shared state driver for every pipeline stage, keyed by
``chat_id``, carrying a schema version so resets and migrations are explicit.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from tele_bot.contracts import DocumentaryScript, Dossier, InterviewAnswer, PhotoMessage

SCHEMA_VERSION = 2


class PipelinePhase(StrEnum):
    """The explicit state machine — no implicit control flow."""

    AWAITING_PHOTO = "awaiting_photo"
    AWAITING_INTERVIEW = "awaiting_interview"
    CHECKING_PHOTO = "checking_photo"
    PROFILING = "profiling"
    CONVERTING = "converting"
    SCRIPTING = "scripting"
    NARRATING = "narrating"
    COMPLETE = "complete"


class SessionState(BaseModel):
    """One user's conversation state. Never shared between chat_ids."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = SCHEMA_VERSION
    chat_id: int
    phase: PipelinePhase = PipelinePhase.AWAITING_PHOTO
    photo: PhotoMessage | None = None
    answers: tuple[InterviewAnswer, ...] = ()
    question: str | None = None
    dossier: Dossier | None = None
    script: DocumentaryScript | None = None


class SessionDriver:
    """The single shared state driver (SPECS/TECH.md).

    All stages read and write through this object rather than touching a
    session dict directly, so isolation and reset semantics live in one place.
    """

    def __init__(self) -> None:
        self._states: dict[int, SessionState] = {}

    def get(self, chat_id: int) -> SessionState:
        """Return this chat's state, creating it on first use."""
        state = self._states.get(chat_id)
        if state is None:
            state = SessionState(chat_id=chat_id)
            self._states[chat_id] = state
        return state

    def advance(self, chat_id: int, phase: PipelinePhase) -> SessionState:
        """Move this chat's session to ``phase`` and return the new state."""
        current = self.get(chat_id)
        updated = current.model_copy(update={"phase": phase})
        self._states[chat_id] = updated
        return updated

    def reset(self, chat_id: int) -> SessionState:
        """Purge this chat's conversation state back to the initial phase.

        Only the named chat is affected — other sessions are left alone.
        """
        fresh = SessionState(chat_id=chat_id)
        self._states[chat_id] = fresh
        return fresh

    def save(self, state: SessionState) -> None:
        """Publish a validated immutable snapshot for the orchestrator."""
        self._states[state.chat_id] = state

    def discard(self, chat_id: int) -> None:
        """Release abandoned session memory entirely."""
        self._states.pop(chat_id, None)
