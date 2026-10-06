# Plan — The Bouncer (vision gate)

**Branch:** `feature/2026-10-06-bouncer`

Red/Green TDD: each task group writes tests first, watches them fail, then
implements until green. Run checks only via the dev scripts in `scripts/` —
they are the ground truth (see `README.md` and `SPECS/TECH.md`).

> **Execution status (final):** all seven task groups shipped on
> `feature/2026-10-06-bouncer` (commits `c043509`..`8fa20cf`). Details of
> divergences are inline below and in `validation.md` §7-§8.

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

> **Shipped:** `scripts/test`, `scripts/hooks`, `pyproject.toml`,
> pinned `requirements.txt`, `tele_bot/settings.py` + tests. `pillow` was
> added to the dev requirements for the live tests' generated images.

---

## Task group 2 — Session state driver & phase enum

> **Shipped:** `tele_bot/state.py` + 10 tests (transitions, isolation,
> reset, schema version).

---

## Task group 3 — Boundary contracts

> **Shipped:** `tele_bot/contracts.py` + 14 tests. Note: the telegram→Bouncer
> contract field is named `data` in code (the requirements table calls it
> `bytes`, which is a Python builtin and awkward as a field name). Both are
> `bytes`, non-empty, ≤ 10 MB, image-only. `extra="forbid"` added; boolean
> `confidence` rejected before lax float coercion.

---

## Task group 4 — Bouncer classification (mocked)

> **Shipped:** `tele_bot/bouncer.py`, `tele_bot/gemini_classifier.py`,
> `tele_bot/logging_decorators.py` + 10 Bouncer tests and 8 offline
> classifier tests. `ServerError` is wrapped into `GeminiClassifierError`
> alongside `ClientError`; requests carry a bounded 30 s timeout.

---

## Task group 5 — Telegram download & ADK wiring

> **Shipped:** `tele_bot/telegram_io.py` (incl. `sniff_image_mime`),
> `agents/bouncer_agent.py`, `tele_bot/main.py` + 7 wiring tests and 8
> gateway tests. The gateway validates the `PhotoMessage` immediately after
> download (magic-byte MIME sniff) before ADK/Gemini run; the agent
> re-validates. The blocking classifier runs off the event loop via
> `asyncio.to_thread`.

---

## Task group 6 — Optional live verification

**Skipped by default** (requires a real `GEMINI_API_KEY`).

1. One integration test exercising real Gemini with two real images:
   a landscape/object (expect reject) and a person (expect pass).
2. Must be tagged and auto-skipped when no key is present, so `scripts/test`
   and `scripts/hooks` stay green offline.

**Exit criteria:** skipped cleanly without a key; passes with one.

> **Shipped:** `tests/integration/test_live_bouncer.py` (2 tests, `-m live`).
> Implementation detail: D3's "skipped by default" is enforced both ways —
> `addopts = "-m 'not live'"` in `pyproject.toml` and a module-level skip
> when the key is absent. Verified green against the real API.

---

## Task group 7 — Docs & final checks

1. Update `README.md`: how to run the bot, the dev scripts, required keys.
2. Update `SPECS/TECH.md` / `SPECS/ROADMAP.md` only if implementation
   diverged from the constitution (surface to the user first).
3. Run `scripts/test` and `scripts/hooks` — both green.
4. Confirm `.env` is still ignored and no secrets are staged.

> **Shipped:** README sync (run command, dev scripts, live-test opt-in,
> Bouncer behaviour); ROADMAP Phase 1/2 → `done` (verified); validation.md
> checkboxes ticked with divergence notes. No constitution divergence was
> found — `TECH.md` unchanged.
