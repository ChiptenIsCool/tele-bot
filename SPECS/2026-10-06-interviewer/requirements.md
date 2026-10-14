# Requirements — The Interviewer (orchestrating Q&A)

**Spec:** `SPECS/2026-10-06-interviewer/`
**Branch:** `feature/2026-10-06-interviewer`
**Roadmap:** Phase 3 (Interviewer)

## Context

Phase 1–2 are merged (`main`). A photo passes the **Bouncer's** vision gate and
the session advances to `AWAITING_INTERVIEW`. Nothing happens after that today:
text messages are ignored, and there is no Interviewer.

This spec delivers the **Interviewer**: the second pipeline stage and the
conversation orchestrator. It runs the 5–7 question behavioural interview that
sits between the Bouncer and the (later) Converter/Scripter/Narrator stages.

The user's goal, from the phase brief: a coherent interview with **state
management** — track which question is outstanding, accumulate answers per
`chat_id`, dispatch **one question at a time** and yield until the user
replies, then **synthesize** the collected answers into a behavioural profile
that suggests an animal.

## Scope

### In scope

**Interviewer core (state machine)**

- A typed, per-`chat_id` interview state machine, built on the existing shared
  `SessionDriver` (`tele_bot/state.py`). New phase `INTERVIEW_COMPLETE`; new
  typed fields `question_index` (int, 0..7, the number of questions dispatched
  so far) and `dossier` (immutable list of Q&A pairs).
- The Interviewer owns the transitions:
  - `begin()` — starting a fresh interview (new question index 0, empty
    dossier), after the Bouncer admits a photo.
  - per-answer step — record the answer, then either dispatch the next
    question or finish with the synthesis.
  - `finish()` — deliver the behavioural profile and set
    `INTERVIEW_COMPLETE`.
- **Turn-taking invariant:** exactly one question outstanding at any time.
  The bot never dispatches Q2 before the user has answered Q1, and never asks
  two questions in one message.

**Gemini-backed question generation & synthesis**

- **Model:** `gemini-3.1-flash-lite` (same as the Bouncer).
- Questions are **generated adaptively**, one at a time, from the dossier so
  far — sequential questions in an investigative, playful, slightly eccentric
  documentary-researcher tone.
- **5–7 question budget:** the model may signal "I have enough" only once at
  least 5 answers exist; the app hard-caps at 7. The app enforces both bounds;
  the model's judgement is advisory within them.
- **Synthesis (the final agent step):** from the dossier, produce a concise
  behavioural profile — a clean descriptive block covering the subject's
  quirks (e.g. sleep cycles, territory marking, favourite forage) plus a
  suggested animal.

**Wiring & gateway**

- A text handler in `tele_bot/main.py` so an answer to the outstanding
  question reaches the Interviewer; the existing photo handler stays the
  Bouncer's.
- `agents/interviewer_agent.py` — the Interviewer as an ADK agent, mirroring
  the Bouncer agent's shape (validate at the edge, run the core off the event
  loop, yield the reply as a model event).
- **Fresh photo = fresh interview:** once finished, or mid-interview, an
  admitted photo clears the old dossier and starts a brand-new interview.
  A rejected photo still resets the session (Bouncer behaviour, unchanged).
- Interviews are strictly per-`chat_id`; no cross-user leakage.

### Out of scope (YAGNI)

- Converter, Scripter, Narrator (Phases 4–6).
- `/start` and `/restart` reset semantics and photo-during-interview / text-
  during-photo graceful policies beyond the minimal unhandled-input default
  (Phase 7 owns the full resilience contract). Unhandled text while
  `AWAITING_PHOTO` is ignored and logged, nothing more.
- Retry/backoff configuration, question numbering formatting, multiple
  question variants, or per-question timeouts.
- Any photo content in the questions — questions adapt to **answers only**.
- Persistent storage; everything stays in memory.

## Decisions

| # | Decision | Rationale |
| --- | --- | --- |
| D1 | Coarse phase enum + typed counter | `AWAITING_PHOTO` / `AWAITING_INTERVIEW` / `INTERVIEW_COMPLETE` as the phase, with `question_index` (dispatched-so-far) as typed state. Matches "know whether the user is awaiting Q1, answering Q4, or finished" without 7 near-identical enum values. |
| D2 | Questions are Gemini-generated, one call per question, building on the dossier | The tone brief ("investigative, playful, slightly eccentric documentary researcher") is authored as tone in the prompt; adaptive questions are the natural reading of "sharp, sequential questions". |
| D3 | Model decides the stop point **within** 5–7; the app enforces the bounds | `InterviewStep.more` flag from Gemini; app never finishes before 5 answers (one forced re-invocation if the model tries to) and never asks an 8th question. |
| D4 | Per-stage ADK dispatch, Interviewer owns the Q&A machine | Keeps the merged Phase 1–2 pattern (photo→Bouncer, text→Interviewer via the gateway) and defers the full hub-and-spoke refactor; the Interviewer still owns all interview transitions and the dossier. |
| D5 | Answer is committed **only after** a successful next-step generation | If Gemini fails mid-question or at synthesis, the session is unchanged (same question outstanding, graceful reply, loud log) — no half-committed dossier, mirrors the Bouncer's degrade-don't-raise policy. |
| D6 | Fresh photo = fresh interview | A new admitted photo resets `question_index` and the dossier before Q1. Documented and deliberate; Phase 7 may refine in-conversation policies. |
| D7 | Gemini contract models are strict Pydantic (`extra="forbid"`), parsed at the boundary | `TECH.md`: no raw dicts / `Any` across boundaries; malformed model output fails loudly and degrades gracefully on the user's path. |

## Contracts

### `AnswerMessage` (Telegram text → Interviewer)

| Field | Type | Rule |
| --- | --- | --- |
| `chat_id` | `int` | required, strict; the session key |
| `text` | `str` | required; non-empty after stripping; ≤ 4096 chars (Telegram's message ceiling) |

Violations are rejected at the gateway before the Interviewer runs.

### `InterviewStep` (Gemini → Interviewer, one per step)

| Field | Type | Rule |
| --- | --- | --- |
| `question` | `str \| None` | required, non-empty when `more=True`; may be null when `more=False` |
| `more` | `bool` | required, strict; `True` = ask `question` next, `False` = ready to finish |

App-enforced bounds on top of the model's flag: `more=False` before 5 answers
is overridden by one forced re-invocation telling the model to continue; at 7
answers the app always finishes regardless of `more`.

### `BehavioralProfile` (Gemini → Interviewer, synthesis)

| Field | Type | Rule |
| --- | --- | --- |
| `description` | `str` | required, non-empty; the clean descriptive block (sleep cycles, territory marking, favourite forage, …) |
| `animal` | `str` | required, non-empty; the suggested animal |

The user-facing delivery is `description` plus a suggested-animal sentence
built from `animal`.

### Session state (extended)

- `phase`: `AWAITING_PHOTO` · `AWAITING_INTERVIEW` · `INTERVIEW_COMPLETE`.
- `question_index`: int, default 0; incremented by the driver when a question
  is dispatched; ceiling 7. Idle value for "awaiting this number" is
  `len(dossier) + 1`; `INTERVIEW_COMPLETE` means finished.
- `dossier`: `tuple[InterviewEntry, ...]` (frozen), `InterviewEntry` =
  `{question: str, answer: str}`. Appended only via the shared driver.
- Schema version stays explicit; all mutations go through `SessionDriver`.

## Non-negotiables

- `.env` never committed; no new secrets introduced.
- No raw dicts or `Any` across module boundaries; strict Pydantic contracts.
- No bare `except: pass`; every suppressed error logged loudly.
- Tests written before the code they cover (Red/Green TDD).
- Gemini failures on the user's conversation path degrade gracefully, never
  crash the polling loop.