# Validation — The Bouncer (vision gate)

Validation is complete only when every item is checked **and** the dev scripts
pass. Run them exactly as documented in `README.md`:

```bash
scripts/test     # test suite
scripts/hooks    # lint + type checks
```

## 1. Foundation

- [x] `scripts/test` exists, is executable, and runs the suite.
- [x] `scripts/hooks` exists, is executable, and runs lint + type checks.
- [x] Both scripts match what `README.md` documents.
- [x] Dependencies are pinned/reproducible.
- [x] Settings loader reads `TELEGRAM_BOT_TOKEN` and `GEMINI_API_KEY` from
      `.env` and fails loudly when absent.
- [x] No secret value appears anywhere in tracked files
      (`git grep` for both key values returns nothing).

## 2. Contracts

- [x] `PhotoMessage` rejects empty bytes, non-image mime, and oversized
      payloads at the edge — before any Gemini call.
- [x] `HumanPresenceVerdict` is a strict typed parse; malformed Gemini
      output does not become a raw dict downstream.
- [x] No raw `dict` or `Any` crosses a module boundary.
- [x] Phase is a typed enum; state carries a schema version.

> Note: the wire schema sent to Gemini strips `additionalProperties`
> (pydantic emits it for `extra="forbid"`; the API rejects it).

## 3. Bouncer behaviour — the two required tests

- [x] **Negative test (object/landscape):** verdict
      `human_present=False` → cheeky rejection sent, session state reset to
      the initial phase, Gemini mocked (no network).
- [x] **Positive test (person):** verdict `human_present=True` →
      confirmation sent, state advanced to `AWAITING_INTERVIEW`, Gemini
      mocked (no network).
- [x] Both tests pass under `scripts/test`.

## 4. Failure handling (conversation path)

- [x] Gemini returns unparseable output → error logged, graceful reply,
      never raised to the user.
- [x] Gemini call fails/times out → logged loudly, polling loop survives.
- [x] No bare `except: pass`; every suppressed exception is logged.
- [x] Logging is applied via decorators, not sprinkled through business
      logic.

## 5. State & isolation

- [x] Rejection resets only the offending `chat_id`'s state.
- [x] Two `chat_id`s never share or observe each other's state.
- [x] Pass advances exactly one session to `AWAITING_INTERVIEW`.

## 6. Wiring

- [x] ADK layout contains the Bouncer as the first pipeline stage.
- [x] Long-polling entry point routes a photo update through download →
      validate → Bouncer → reply.
- [x] Webhook is not used; no public URL required.

> Note: validation now happens at the gateway immediately after download
> (`sniff_image_mime` + `PhotoMessage`), with the agent's re-validation kept
> as defense in depth.

## 7. Optional live check (skipped by default)

- [x] Integration test tagged and auto-skipped without `GEMINI_API_KEY`
      (also deselected by default via `addopts = "-m 'not live'"` — opt in
      with `pytest -m live`).
- [x] With a key: real Gemini rejects a landscape/object image and accepts a
      person image. Run with `python3 -m pytest tests/integration -m live -q`
      — both pass against the real API.

## 8. Docs & constitution alignment

- [x] `README.md` documents setup, required keys, run command, dev scripts.
- [x] Implementation matches `SPECS/TECH.md`; any divergence surfaced to the
      user and the spec updated with approval.
- [x] `SPECS/ROADMAP.md` Phase 1/2 marked `done` **only** if verified here.

## Merge gate

- [ ] `scripts/test` green.
- [ ] `scripts/hooks` green.
- [ ] No blocking findings from code review.
- [ ] `.env` untracked and gitignored.
