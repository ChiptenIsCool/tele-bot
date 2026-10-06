"""Task group 2: session state — versioned, per-chat_id, one shared driver.

SPECS/TECH.md: state is keyed by chat_id, carries a schema version, and is
mutated only through the single shared driver. One user's session must never
bleed into another's.
"""

from tele_bot.state import SCHEMA_VERSION, PipelinePhase, SessionDriver, SessionState


def test_new_session_starts_awaiting_photo() -> None:
    driver = SessionDriver()

    state = driver.get(1)

    assert state.phase is PipelinePhase.AWAITING_PHOTO


def test_state_carries_schema_version() -> None:
    driver = SessionDriver()

    state = driver.get(1)

    assert state.schema_version == SCHEMA_VERSION


def test_state_records_the_chat_id_it_belongs_to() -> None:
    driver = SessionDriver()

    state = driver.get(42)

    assert state.chat_id == 42


def test_advance_moves_to_awaiting_interview() -> None:
    driver = SessionDriver()

    state = driver.advance(1, PipelinePhase.AWAITING_INTERVIEW)

    assert state.phase is PipelinePhase.AWAITING_INTERVIEW


def test_advance_is_durable_for_that_chat_only() -> None:
    driver = SessionDriver()
    driver.advance(1, PipelinePhase.AWAITING_INTERVIEW)

    assert driver.get(1).phase is PipelinePhase.AWAITING_INTERVIEW


def test_reset_returns_the_initial_phase() -> None:
    driver = SessionDriver()
    driver.advance(1, PipelinePhase.AWAITING_INTERVIEW)

    state = driver.reset(1)

    assert state.phase is PipelinePhase.AWAITING_PHOTO


def test_reset_leaves_other_chats_untouched() -> None:
    driver = SessionDriver()
    driver.advance(1, PipelinePhase.AWAITING_INTERVIEW)
    driver.advance(2, PipelinePhase.AWAITING_INTERVIEW)

    driver.reset(1)

    assert driver.get(2).phase is PipelinePhase.AWAITING_INTERVIEW


def test_chat_ids_never_bleed_into_each_other() -> None:
    """The isolation non-negotiable: no cross-chat_id state leakage."""
    driver = SessionDriver()
    driver.advance(1, PipelinePhase.AWAITING_INTERVIEW)
    driver.get(2)  # 2 materialises an independent session
    driver.reset(2)

    assert driver.get(1).phase is PipelinePhase.AWAITING_INTERVIEW
    assert driver.get(2).phase is PipelinePhase.AWAITING_PHOTO
    assert driver.get(1) is not driver.get(2)


def test_driver_state_is_immutable_to_callers() -> None:
    """Stored state is frozen: callers cannot mutate it behind the driver."""
    driver = SessionDriver()

    first = driver.get(1)

    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        first.phase = PipelinePhase.AWAITING_INTERVIEW

    assert driver.get(1).phase is PipelinePhase.AWAITING_PHOTO


def test_session_state_rejects_an_unknown_phase() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SessionState(chat_id=1, phase="not_a_phase")  # type: ignore[arg-type]
