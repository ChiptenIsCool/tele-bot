# ROADMAP

The ordered build plan — one phase per pipeline capability. A phase is marked
complete only when its acceptance criteria are verified.

Status legend: `todo` · `in progress` · `done`

## Phase 1 — Repository & gateway — `todo`

Project skeleton, `.env` loading, Telegram long-polling loop.

**Acceptance criteria**
- Repo structure, dependencies, and `scripts/test` + `scripts/hooks` in place.
- Bot polls Telegram and replies to a hardcoded test reply.
- Secrets read from `.env`; `.env` gitignored.

**Serves:** happy-path entry point; repo hygiene.

## Phase 2 — Bouncer — `todo`

Gemini 3.1 Flash Lite vision gate.

**Acceptance criteria**
- A photo containing a human passes through to the Interviewer.
- Non-human / invalid images get a cheeky rejection and the session resets.
- Result parsed into a typed Pydantic model at the boundary.

**Serves:** happy path; graceful wrong-input handling.

## Phase 3 — Interviewer — `todo`

Stateful sequential Q&A and orchestration.

**Acceptance criteria**
- Asks 5–7 questions, one at a time, accumulating a behavioural dossier tied
  to `chat_id`.
- Outputs a suggested animal.
- Owns the state machine; only one question outstanding at a time.
- Session is per-`chat_id` with no cross-user leakage.

**Serves:** happy path; session isolation.

## Phase 4 — Converter — `todo`

Gemini 3.1 Flash Image hybrid portrait.

**Acceptance criteria**
- Fuses the original photo + interview dossier into a hybrid animal portrait.
- Portrait is delivered directly to Telegram with no intermediate text hop.
- Image handling validated (type, size) before use.

**Serves:** happy path.

## Phase 5 — Scripter — `todo`

Gemini 3.1 Flash Lite narration.

**Acceptance criteria**
- Produces a one-paragraph, ~60–90 word dramatic British-documentary
  narration built from the dossier.
- Output validated as text before being handed to the Narrator.

**Serves:** happy path.

## Phase 6 — Narrator — `todo`

Gemini TTS synthesis and audio delivery.

**Acceptance criteria**
- Script routes to `gemini-3.1-flash-tts-preview` (the Narrator is not an
  agent).
- TTS output is encoded to a Telegram-compatible format (OGG/MP3) and sent
  as a voice note.

**Serves:** happy path completion.

## Phase 7 — Resilience — `todo`

Resets, wrong-stage guards, and fallbacks.

**Acceptance criteria**
- `/start` and `/restart` purge that `chat_id`'s state **and** temporary
  files, in place, without restarting the process; an immediate fresh run
  works.
- Wrong-payload-at-wrong-stage inputs (text during image stage, photo during
  interview, etc.) are handled gracefully — conversation continues or resets,
  never crashes.
- Gemini/Telegram API timeouts degrade gracefully on the conversation path,
  logged loudly.

**Serves:** `/restart` reset criterion; out-of-order input criterion;
graceful degradation.
