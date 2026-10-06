# Validation — The Bouncer (vision gate)

Validation is complete only when every item is checked **and** the dev scripts
pass. Run them exactly as documented in `README.md`:

```bash
scripts/test     # test suite
scripts/hooks    # lint + type checks
```

## 1. Foundation

- [ ] `scripts/test` exists, is executable, and runs the suite.
- [ ] `scripts/hooks` exists, is executable, and runs lint + type checks.
- [ ] Both scripts match what `README.md` documents.
- [ ] Dependencies are pinned/reproducible.
- [ ] Settings loader reads `TELEGRAM_BOT_TOKEN` and `GEMINI_API_KEY` from
      `.env` and fails loudly when absent.
- [ ] No secret value appears anywhere in tracked files
      (`git grep` for both key values returns nothing).

## 2. Contracts

- [ ] `PhotoMessage` rejects empty bytes, non-image mime, and oversized
      payloads at the edge — before any Gemini call.
- [ ] `HumanPresenceVerdict` is a strict typed parse; malformed Gemini
      output does not become a raw dict downstream.
- [ ] No raw `dict` or `Any` crosses a module boundary.
- [ ] Phase is a typed enum; state carries a schema version.

## 3. Bouncer behaviour — the two required tests

- [ ] **Negative test (object/landscape):** verdict
      `human_present=False` → cheeky rejection sent, session state reset to
      the initial phase, Gemini mocked (no network).
- [ ] **Positive test (person):** verdict `human_present=True` →
      confirmation sent, state advanced to `AWAITING_INTERVIEW`, Gemini
      mocked (no network).
- [ ] Both tests pass under `scripts/test`.

## 4. Failure handling (conversation path)

- [ ] Gemini returns unparseable output → error logged, graceful reply,
      never raised to the user.
- [ ] Gemini call fails/times out → logged loudly, polling loop survives.
- [ ] No bare `except: pass`; every suppressed exception is logged.
- [ ] Logging is applied via decorators, not sprinkled through business
      logic.

## 5. State & isolation

- [ ] Rejection resets only the offending `chat_id`'s state.
- [ ] Two `chat_id`s never share or observe each other's state.
- [ ] Pass advances exactly one session to `AWAITING_INTERVIEW`.

## 6. Wiring

- [ ] ADK layout contains the Bouncer as the first pipeline stage.
- [ ] Long-polling entry point routes a photo update through download →
      validate → Bouncer → reply.
- [ ] Webhook is not used; no public URL required.

## 7. Optional live check (skipped by default)

- [ ] Integration test tagged and auto-skipped without `GEMINI_API_KEY`.
- [ ] With a key: real Gemini rejects a landscape/object image and accepts a
      person image.

## 8. Docs & constitution alignment

- [ ] `README.md` documents setup, required keys, run command, dev scripts.
- [ ] Implementation matches `SPECS/TECH.md`; any divergence surfaced to the
      user and the spec updated with approval.
- [ ] `SPECS/ROADMAP.md` Phase 1/2 marked `done` **only** if verified here.

## Merge gate

- [ ] `scripts/test` green.
- [ ] `scripts/hooks` green.
- [ ] No blocking findings from code review.
- [ ] `.env` untracked and gitignored.
