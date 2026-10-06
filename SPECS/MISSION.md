# MISSION

## Vision

**The Telegram Documentaries** turns an ordinary portrait photo into a narrated,
comedy wildlife-documentary about the person in it. A user opens Telegram, sends
their photo to the bot, answers a short interview about themselves, and receives
back a hybrid animal portrait of themselves plus a dramatic British-documentary
voice note narrating their wildlife alter-ego.

The end-to-end user experience:

1. The user sends a photo.
2. **The Bouncer** checks that a human is actually in the frame — anything else
   gets a cheeky rejection and the session resets.
3. **The Interviewer** asks 5–7 questions one at a time, building a behavioural
   dossier tied to the user's `chat_id`, and suggests an animal.
4. **The Converter** merges the original photo with the dossier into a hybrid
   animal portrait, sent straight back into the chat.
5. **The Scripter** writes a ~60–90 word dramatic narration from the dossier.
6. **The Narrator** renders that script to speech and delivers it as a Telegram
   voice note.

## In scope

- The five pipeline stages above: Bouncer, Interviewer, Converter, Scripter,
  Narrator — in that order, as a single continuous conversation.
- The Interviewer acting as the orchestrator, one question at a time, stateful
  per `chat_id`.
- Hybrid animal portrait delivery directly to Telegram (no intermediate text
  hop for the image).
- Narration delivered as a Telegram-compatible audio note (OGG/MP3).
- Telegram **long polling** transport — no webhooks, no public URL.
- `/start` and `/restart` purging session state and temporary media without
  restarting the process.
- Graceful handling of out-of-order text and media (e.g. a photo during the
  interview, text during the image stage).

## Out of scope (YAGNI)

- Video generation of any kind.
- Webhooks or any publicly reachable URL.
- Persistent storage / database — session state lives in memory.
- Multi-language support; English only.
- Payments, subscriptions, or premium tiers.
- Any additional pipeline agents beyond the five listed.
- Hypothetical future features or speculative configuration.

## Success criteria

The project is "working" when, on the graded rubric:

- **Happy path:** a real user can send a portrait, complete the interview,
  receive a hybrid animal portrait, and receive a narrated voice note — the
  full pipeline end-to-end, with no manual intervention.
- **Reset:** `/restart` and `/start` fully clear that user's session state and
  temporary files, allowing an immediate fresh run without restarting the
  process.
- **Out-of-order input:** text or media arriving at the wrong pipeline stage
  is handled gracefully — the conversation continues or resets cleanly, never
  crashes.
- **Isolation:** one user's session is never visible to, or leaked into,
  another user's session.

## Non-negotiables

- Never leak or mix session state between `chat_id`s.
- Never hardcode secrets; `TELEGRAM_BOT_TOKEN` and `GEMINI_API_KEY` live in
  `.env` and must never be committed.
- Never swallow errors silently on a user's conversation path.
