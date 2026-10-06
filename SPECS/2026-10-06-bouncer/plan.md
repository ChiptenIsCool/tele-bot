# Plan — The Bouncer (vision gate)

**Branch:** `feature/2026-10-06-bouncer`

Red/Green TDD: each task group writes tests first, watches them fail, then
implements until green. Run checks only via the dev scripts in `scripts/` —
they are the ground truth (see `README.md` and `SPECS/TECH.md`).

---

## Task group 1 — Foundation & dev scripts

**Tests first:** a test asserting `scripts/test` and `scripts/hooks` exist and
are executable; a test that `.env` keys are required by the loader.

1. Create the Python project layout and a **pinned** dependency manifest
   (Google ADK, python-telegram-bot, pydantic, pytest, ruff, mypy as needed).
2. Write `scripts/test` — runs the pytest suite.
3. Write `scripts/hooks` — runs lint and type checks (ruff + mypy).
4. Confirm both scripts run and match what `README.md` claims; correct the
   README if they differ.
5. Add a settings loader that reads `TELEGRAM_BOT_TOKEN` and `GEMINI_API_KEY`
   from `.env` and fails loudly if missing. No secrets in code.

**Exit criteria:** `scripts/test` and `scripts/hooks` both run.

---

## Task group 2 — Session state driver & phase enum

**Tests first:** state transitions, per-`chat_id` isolation, reset-to-initial.

1. Define a typed `PipelinePhase` enum
   (`AWAITING_PHOTO`, `AWAITING_INTERVIEW`, …).
2. Define the versioned, per-`chat_id` session-state schema (Pydantic).
3. Implement the **single shared state driver**: get, set, advance, reset.
4. Tests must prove one `chat_id`'s state never bleeds into another's.

**Exit criteria:** transitions and isolation green.

---

## Task group 3 — Boundary contracts

**Tests first:** valid and invalid payloads for each model.

1. `PhotoMessage` — `chat_id`, `file_id`, image bytes, `mime_type`;
   non-empty, size ceiling, image-only.
2. `HumanPresenceVerdict` — `human_present`, `confidence`, `reason`;
   strict parse of Gemini output.
3. Rejection cases (empty bytes, wrong mime, oversized, missing field) must
   fail loudly at the edge, before any Gemini call.

**Exit criteria:** contract tests green, including every rejection path.

---

## Task group 4 — Bouncer classification (mocked)

**Tests first:**

- **Negative test:** a landscape/object image → `human_present=False`,
  cheeky rejection sent, session state reset.
- **Positive test:** a person image → `human_present=True`, confirmation
  sent, state advanced to `AWAITING_INTERVIEW`.
- Malformed Gemini output → logged, degraded gracefully, never raised.
- Gemini call failure/timeout → logged loudly, conversation path survives.

1. Implement the Gemini 3.1 Flash Lite multimodal classification call.
2. Implement decorator-based structured logging around it (keep logging out
   of business logic).
3. Implement the reject path: cheeky rejection copy + state reset.
4. Implement the pass path: confirmation + state advance.
5. All Gemini calls mocked in these tests — no network.

**Exit criteria:** negative and positive tests green with Gemini mocked.

---

## Task group 5 — Telegram download & ADK wiring

**Tests first:** fake Telegram update → bytes validated → Bouncer invoked.

1. Download the photo bytes from Telegram.
2. Validate through `PhotoMessage` before use.
3. Wire the Bouncer into the ADK project as the first pipeline stage.
4. Connect the long-polling entry point: photo update → download → validate →
   Bouncer → reply + state transition.

**Exit criteria:** end-to-end path green with both Telegram and Gemini
mocked.

---

## Task group 6 — Optional live verification

**Skipped by default** (requires a real `GEMINI_API_KEY`).

1. One integration test exercising real Gemini with two real images:
   a landscape/object (expect reject) and a person (expect pass).
2. Must be tagged and auto-skipped when no key is present, so `scripts/test`
   and `scripts/hooks` stay green offline.

**Exit criteria:** skipped cleanly without a key; passes with one.

---

## Task group 7 — Docs & final checks

1. Update `README.md`: how to run the bot, the dev scripts, required keys.
2. Update `SPECS/TECH.md` / `SPECS/ROADMAP.md` only if implementation
   diverged from the constitution (surface to the user first).
3. Run `scripts/test` and `scripts/hooks` — both green.
4. Confirm `.env` is still ignored and no secrets are staged.
