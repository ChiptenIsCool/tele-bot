# Plan — The Interviewer (orchestrating Q&A)

**Branch:** `feature/2026-10-06-interviewer`

Red/Green TDD: each task group writes tests first, watches them fail, then
implements until green. Run checks only via the dev scripts in `scripts/` —
they are the ground truth (see `README.md` and `SPECS/TECH.md`).

---

## Task group 1 — State machine extensions

**Tests first:** transition tests for the new interview phase, the question
index, and the dossier.

1. Extend `PipelinePhase` with `INTERVIEW_COMPLETE`.
2. Extend `SessionState` with `question_index: int = 0` and
   `dossier: tuple[InterviewEntry, ...] = ()` (frozen model, schema version
   bumped or kept explicit per `TECH.md`).
3. Add driver methods owned by the interview flow:
   - `begin_interview(chat_id)` — reset `question_index`+dossier, phase →
     `AWAITING_INTERVIEW` (D6: fresh photo = fresh interview).
   - `record_answer(chat_id, entry)` — append to dossier; enforce the 7-question
     ceiling loudly.
   - `complete_interview(chat_id)` — phase → `INTERVIEW_COMPLETE`.
4. Isolation test: two `chat_id`s never share dossier or index.

**Exit criteria:** driver + phase tests green; existing Bouncer tests still
pass.

---

## Task group 2 — Boundary contracts

**Tests first:** contract validation tests.

1. `AnswerMessage`: strict int `chat_id`, non-empty stripped text, 4096
   ceiling.
2. `InterviewStep`: `question` required when `more=True`; nullable when
   `more=False`; strict `more: bool`.
3. `BehavioralProfile`: both fields required, non-empty; `extra="forbid"` on
   all three models.
4. `InterviewEntry`: typed `{question, answer}`, non-empty strings.

**Exit criteria:** contract tests green; no raw dict/`Any` at any boundary.

---

## Task group 3 — Gemini-backed question generation & synthesis

**Tests first:** mocked-Gemini tests for the step generator and synthesizer.

1. `tele_bot/gemini_interviewer.py` mirroring `gemini_classifier.py`:
   - Same client construction (30 s bounded timeout, injected client for
     tests).
   - `next_step(dossier, last_question, candidate_answer, force_continue)`
     → `InterviewStep`, strict JSON schema parse.
   - `synthesize(dossier)` → `BehavioralProfile`, strict JSON schema parse.
   - `ClientError`/`ServerError` → typed wrapper error; `_schema()` strips
     `additionalProperties` exactly like the Bouncer's verdict schema fix.
2. Tone enforcement lives in the prompts: investigative, playful, slightly
   eccentric documentary researcher (D2).
3. Tests cover: valid parse, `more=True`/`more=False`, missing fields,
   boolean confidence rejection (mirror the classifier suite).

**Exit criteria:** generator/synthesizer unit tests green (mock transport).

---

## Task group 4 — Interviewer core (the state machine)

**Tests first:** mocked-generator tests of the turn-taking logic.

1. `tele_bot/interviewer.py`:
   - `begin()` → generates Q1, records `question_index=1`, returns the
     question reply.
   - `handle_answer(answer, context)` → appends to dossier **only after**
     generation succeeds (D5), then either dispatches the next question or
     produces the profile + animal delivery.
   - Bounds (D3): `more=False` before 5 answers → one forced re-invocation
     continuing; at 7 answers → always finish.
   - Gemini failure mid-question or at synthesis → graceful reply, session
     unchanged, loud log (never raise on the user's path).
2. The final delivery text: `description` + suggested-animal sentence built
   from `BehavioralProfile.animal`.

**Exit criteria:** core turn-taking tests green (both bounds + failure path).

---

## Task group 5 — ADK agent & gateway wiring

**Tests first:** wiring/gateway tests as in the Bouncer suite.

1. `agents/interviewer_agent.py` mirroring `bouncer_agent.py`: validates
   `AnswerMessage` from user text content + `chat_id` from session user_id,
   runs the core off the event loop (`asyncio.to_thread`), yields the reply.
2. `tele_bot/main.py`:
   - Text handler routing text → Interviewer when `AWAITING_INTERVIEW`;
     ignores (with a log) text while `AWAITING_PHOTO`; after
     `INTERVIEW_COMPLETE` a further photo restarts (D6).
   - Photo handler unchanged for the Bouncer; on admission the gateway wires
     the Interviewer so Q1 follows the confirmation.
   - Handler wrappers keep the "never raise into the user's flow" contract.
3. Correctly share `SessionDriver` + runner between both handlers.

**Exit criteria:** live-style mocked gateway tests green: photo→Q1,
answer→Q2, 5th-answer→profile, isolation, graceful failure.

---

## Task group 6 — Optional live verification

**Skipped by default** (requires a real `GEMINI_API_KEY`).

1. One integration test driving a tiny real interview: admit → Q1 → answer →
   … → profile with a suggested animal. Bounded to a few real calls.
2. Tagged `live` and auto-skipped without a key (`addopts` already excludes
   `-m live` by default; keep `scripts/test` green offline).

**Exit criteria:** skipped cleanly without a key; passes with one.

---

## Task group 7 — Docs & final checks

1. Update `README.md`: interview flow, the text handler, live-test opt-in if
   changed.
2. Update `SPECS/TECH.md` / `SPECS/ROADMAP.md` only if implementation
   diverged from the constitution (surface to the user first).
3. Run `scripts/test` and `scripts/hooks` — both green.
4. Confirm `.env` is still ignored and no secrets are staged.