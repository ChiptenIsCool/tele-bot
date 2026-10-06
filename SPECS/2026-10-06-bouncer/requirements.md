# Requirements — The Bouncer (vision gate)

**Spec:** `SPECS/2026-10-06-bouncer/`
**Branch:** `feature/2026-10-06-bouncer`
**Roadmap:** Phase 1 (Repository & gateway) + Phase 2 (Bouncer)

## Context

The repository currently contains the project constitution (`SPECS/MISSION.md`,
`SPECS/TECH.md`, `SPECS/ROADMAP.md`), a README, and secrets hygiene — but **no
application code**. There is no `scripts/`, no dependency manifest, no polling
loop, and no agents.

This spec therefore covers two things together, because the Bouncer cannot
exist without them:

1. **Minimal foundation** — enough of Phase 1 to run and test the Bouncer.
2. **The Bouncer itself** — the vision gate that starts the pipeline.

The Interviewer, Converter, Scripter, and Narrator are **explicitly out of
scope** and arrive in later phases.

## Scope

### In scope

**Foundation (minimal Phase 1)**

- Python project layout with a reproducible, pinned dependency set.
- `scripts/test` and `scripts/hooks` — the ground-truth dev scripts named in
  `TECH.md` and the README. They must run for real and their contents must
  match what the README claims.
- `.env` loading for `TELEGRAM_BOT_TOKEN` and `GEMINI_API_KEY`. Secrets read
  from the environment only; never hardcoded, never committed.
- A Telegram **long-polling** entry point that receives updates.
- An **ADK** project layout for the pipeline agents, with the Bouncer wired
  into it as the first stage.

**Bouncer**

- When a user uploads a photo, download the image bytes from Telegram.
- Validate the download through a **Pydantic typed contract** before anything
  else touches it (content type, non-empty, size ceiling). All external input
  is untrusted.
- Pass the bytes to **Gemini 3.1 Flash Lite** as a multimodal classification:
  is a discernible human face or body present?
- Parse Gemini's verdict into a **typed Pydantic model at the boundary** —
  never a raw dict.
- **No human detected:**
  - Reset that `chat_id`'s ephemeral conversation state via the single shared
    state driver.
  - Reply with a humorous, cheeky rejection that explains the submission must
    contain a human.
- **Human detected:**
  - Reply with a brief confirmation.
  - Advance session state to the next phase.
  - No interview behaviour — that is the Interviewer's job in a later phase.

### Out of scope (YAGNI)

- Interviewer, Converter, Scripter, Narrator.
- `/restart` full reset semantics beyond the state purge this spec needs
  (Phase 7 owns the complete reset contract).
- Webhooks, databases, persistent storage.
- Photo storage on disk — image bytes stay in memory.
- Retry/backoff configuration, feature flags, model-selection config.
- Multiple concurrent pipeline stages or async fan-out.

## Decisions

| # | Decision | Rationale |
| --- | --- | --- |
| D1 | Minimal scaffolding is in this spec, not a separate one | The Bouncer is untestable without `scripts/test` and a dependency set; splitting would leave a spec that cannot be validated. |
| D2 | Positive result → confirm + advance state | The Interviewer does not exist yet. Confirming keeps the conversation path real and makes the state transition observable and testable. |
| D3 | Primary tests are **mocked**; one optional live test is tagged and skipped by default | Deterministic, network-free suite that runs in hooks; live behaviour still verifiable with a real key when wanted. |
| D4 | Image bytes held **in memory**, validated by Pydantic | No temp-file lifecycle to leak; consistent with `TECH.md`'s "parse at the edge" and Phase 7's later temp-file reset work. |
| D5 | Gemini verdict is a typed model, not a free-text/regex parse | `TECH.md` forbids regex-as-schema and untyped payloads across boundaries. |
| D6 | Logging via decorators, not inline calls | `TECH.md` logging policy: keep logging out of business logic. |
| D7 | On the user's conversation path, Bouncer/API failures degrade gracefully and are logged loudly | `TECH.md`: never raise into the user's flow. A Gemini outage must not kill the polling loop. |

## Contracts

> **Implemented as specified** — see `validation.md` for the verified
> checklist. One naming divergence from the table below: the Telegram→Bouncer
> contract field is `data` in code (`bytes` is a Python builtin); same type,
> same rules.

### `HumanPresenceVerdict` (Gemini → Bouncer)

Typed parse of the model's structured response.

| Field | Type | Rule |
| --- | --- | --- |
| `human_present` | `bool` | required |
| `confidence` | `float` | optional, `0.0–1.0` if present |
| `reason` | `str` | short justification, required |

Malformed or unparseable model output is a **loud, logged** failure that is
handled gracefully on the conversation path (treated as a rejection with a
generic message, never a crash).

### `PhotoMessage` (Telegram → Bouncer)

| Field | Type | Rule |
| --- | --- | --- |
| `chat_id` | `int` | required; the session key |
| `file_id` | `str` | required, non-empty |
| `data` | `bytes` | required, non-empty, ≤ size ceiling (named `data` in code — see note above) |
| `mime_type` | `str` | must be an image type |

Violations are rejected at the edge before Gemini is called.

### Session state

- Versioned, per-`chat_id`, mutated only through the shared state driver.
- Phase is a **typed enum**; the Bouncer transitions
  `AWAITING_PHOTO → AWAITING_INTERVIEW` on pass, and resets to the initial
  phase on rejection.

## Non-negotiables

- `.env` never committed; `.gitignore` entry stays.
- No raw dicts or `Any` across module boundaries.
- No bare `except: pass`; every suppressed error is logged.
- Tests written before the code they cover (Red/Green TDD).
