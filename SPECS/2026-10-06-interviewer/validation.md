# Validation — The Interviewer (orchestrating Q&A)

Validation is complete only when every item is checked **and** the dev scripts
pass. Run them exactly as documented in `README.md`:

```bash
scripts/test     # test suite
scripts/hooks    # lint + type checks
```

## 1. State machine

- [ ] `PipelinePhase` includes `INTERVIEW_COMPLETE`.
- [ ] `SessionState` carries `question_index` (int, 0..7) and a typed
      `dossier` of Q&A entries, per-`chat_id`, mutated only via the shared
      `SessionDriver`.
- [ ] `begin_interview` clears the dossier + index (fresh photo = fresh
      interview); `record_answer` enforces the 7-question ceiling;
      `complete_interview` sets the finished phase.
- [ ] Two `chat_id`s never share or observe each other's dossier/index.

## 2. Contracts

- [ ] `AnswerMessage` rejects empty/whitespace text and >4096-char payloads at
      the edge.
- [ ] `InterviewStep` enforces `question` non-empty when `more=True`.
- [ ] `BehavioralProfile` is a strict typed parse; malformed Gemini output
      never becomes a raw dict downstream.
- [ ] No raw `dict` or `Any` crosses a module boundary.
- [ ] Wire schema sent to Gemini strips `additionalProperties` (same fix as
      the Bouncer).

## 3. Turn-taking & the 5–7 budget

- [ ] Exactly one question outstanding at a time; the next is dispatched only
      after the previous is answered.
- [ ] First question follows a Bouncer admission; the profile follows the
      final answer.
- [ ] `more=False` before 5 answers is overridden (one forced re-invocation);
      at 7 answers the interview always finishes. No 8th question is ever
      asked.

## 4. Synthesis & delivery

- [ ] Once answers are collected, the Interviewer produces a `BehavioralProfile`
      (descriptive block + suggested animal) and delivers it as the final
      reply.
- [ ] After delivery the session is `INTERVIEW_COMPLETE`; a new photo starts a
      fresh interview (old dossier cleared).

## 5. Failure handling (conversation path)

- [ ] Gemini returns unparseable output or fails mid-question → graceful
      reply, session unchanged, logged loudly, never raised to the user.
- [ ] Synthesis failure → same policy (conversation survives, no half-committed
      dossier).
- [ ] No bare `except: pass`; every suppressed exception is logged.
- [ ] Logging applied via decorators, not sprinkled through business logic.

## 6. Wiring

- [ ] Text messages route to the Interviewer while `AWAITING_INTERVIEW`;
      text while `AWAITING_PHOTO` is ignored with a log; the polling loop
      keeps running.
- [ ] `agents/interviewer_agent.py` is a real ADK agent mirroring the Bouncer
      (edge validation, `asyncio.to_thread`, model-event reply).
- [ ] Webhook is not used; no public URL required.

## 7. Optional live check (skipped by default)

- [ ] Integration test tagged `live`, auto-skipped without `GEMINI_API_KEY`,
      and deselected by default via `addopts = "-m 'not live'"`.
- [ ] With a key: a tiny real interview (admit → Q1 → answer → … → profile
      with a suggested animal) passes. Run with
      `python3 -m pytest tests/integration -m live -q`.

## 8. Docs & constitution alignment

- [ ] `README.md` documents the interview flow and dev commands.
- [ ] Implementation matches `SPECS/TECH.md`; any divergence surfaced to the
      user and the spec updated with approval.
- [ ] `SPECS/ROADMAP.md` Phase 3 marked `done` **only** if verified here.

## Merge gate

- [ ] `scripts/test` green.
- [ ] `scripts/hooks` green.
- [ ] No blocking findings from code review.
- [ ] `.env` untracked and gitignored.