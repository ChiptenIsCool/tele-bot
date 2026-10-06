# TECH

The technical contract. Every later spec, agent, and PR is judged against
this file.

## Stack

| Layer | Choice |
| --- | --- |
| Language | Python |
| Agent framework | Google Agent Development Kit (ADK) |
| Transport | Telegram Bot API, **long polling** (no webhooks, no public URL) |
| Bouncer / Interviewer / Scripter | Gemini 3.1 Flash Lite |
| Converter | Gemini 3.1 Flash Image |
| Narrator | Gemini TTS — `gemini-3.1-flash-tts-preview` |
| Session state | In memory, keyed by `chat_id` |
| Secrets | `.env` → `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY` |
| Validation | Pydantic models at every boundary |

## Architecture

- **Hub-and-spoke.** The **Interviewer is the orchestrator**: it owns the
  conversation flow, decides which stage runs next, and holds the session
  state. Every other stage is a discrete agent/module it calls into.
- **Five stages, one direction:**

  ```
  Telegram update → Bouncer → Interviewer → Converter → Scripter → Narrator
                     (gate)    (orchestrator)  (image)     (script)    (TTS)
  ```

- **The Narrator is not an agent.** The Scripter's output routes directly to
  Gemini TTS, is encoded to a Telegram-compatible format (OGG/MP3), and is
  sent to the chat.
- **Explicit state machine.** Pipeline phases are a typed enum, not implicit
  control flow. State transitions are deliberate and logged; there is exactly
  **one shared state driver** used by all stages.

## Contracts at boundaries

- Parse Telegram updates, Gemini responses, and TTS output into **Pydantic
  models at the edge**. Never pass a raw `dict`, an unvalidated payload, or an
  untyped `Any` across a module boundary.
- Treat all external input — Telegram messages, user photos, Gemini output —
  as **untrusted and arbitrary**. Validate type, size, and shape before use.
- Model IDs and prompt formats are part of the contract: changing a model or a
  stage's output shape is a change to `TECH.md` first, then the code.

## Logging & error policy

- **Comprehensive structured logging.** Prefer **decorators** (or equivalent
  cross-cutting helpers) over weaving log calls through business logic.
- **Fail loudly and log** for non-critical, user-invisible work — raise so the
  failure is visible in tests and logs.
- **On a validated user's conversation path**, catch errors and degrade
  gracefully so the conversation continues: log loudly, never raise into the
  user's flow.
- **Never:** bare `except: pass`, swallowed exceptions, or un-logged
  fallbacks. Every handler that suppresses an error must log it.

## Session state

- **Versioned, per-`chat_id` schema.** State carries a schema version so
  changes are detectable and migration/reset behaviour is explicit.
- **One shared state driver** — stages read and write state through it, never
  ad hoc.
- **Reset semantics:** `/start` and `/restart` purge that `chat_id`'s session
  state *and* its temporary media files, in place, without restarting the
  process. After a reset the user can immediately begin a fresh run.

## Testing

- **Red/Green TDD.** Tests are written **before** the code they cover.
- Dev scripts live in `scripts/` and are the **ground truth** for the
  pipeline:
  - `scripts/test` — runs the test suite.
  - `scripts/hooks` — lint and type checks.
- These scripts must be documented here **and** in the README, and must stay
  in sync with what they actually run.

## Repo hygiene

- `.env` is listed in `.gitignore` and **never committed**. Ship an
  `.env.example` documenting required keys instead.
- Dependencies are declared and reproducible (lockfile or pinned
  requirements) so a fresh clone installs identically.

## README policy

The README documents, and stays in sync with:

- Setup: obtaining `TELEGRAM_BOT_TOKEN` and `GEMINI_API_KEY`, filling `.env`.
- The dev scripts (`scripts/test`, `scripts/hooks`) and what they run.
- How to run the bot (long polling) and the available commands
  (`/start`, `/restart`).
- A short description of the five pipeline stages.
