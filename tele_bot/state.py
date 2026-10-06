"""Session state: versioned, per-chat_id, mutated only by the shared driver.

SPECS/TECH.md: one shared state driver for every pipeline stage, keyed by
``chat_id``, carrying a schema version so resets and migrations are explicit.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = 1


class PipelinePhase(StrEnum):
    """The explicit state machine — no implicit control flow."""

    AWAITING_PHOTO = "awaiting_photo"
    AWAITING_INTERVIEW = "awaiting_interview"


class SessionState(BaseModel):
    """One user's conversation state. Never shared between chat_ids."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = SCHEMA_VERSION
    chat_id: int
    phase: PipelinePhase = PipelinePhase.AWAITING_PHOTO


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
