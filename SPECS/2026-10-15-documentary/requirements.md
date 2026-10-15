# Complete documentary pipeline

Implement the remaining lesson requirements while retaining the Bouncer.
The Interviewer is the root Google ADK orchestrator; Bouncer, Converter and
Scripter are specialist ADK agents. Narration is an SDK integration, not an agent.

## Acceptance criteria

- `/start` and `/restart` clear only the requesting private chat's state, ADK
  history and media. Cancel active work; old results cannot arrive after reset.
- A human photo starts five Gemini-generated questions, delivered one per turn.
  Store each question and answer. The final dossier includes a suggested animal.
- Reject non-human photos and prompt for another; wrong-stage inputs preserve
  the current question. Support private chats only to avoid shared interviews.
- Converter sends the original image and dossier in one native multimodal call;
  validate the returned bytes and send the portrait to Telegram.
- Scripter returns exactly one paragraph of 60–90 words. Send it as text.
- TTS uses the course model by default, validates its audio and converts to
  OGG/Opus before Telegram voice delivery. Model IDs are configurable in `.env`.
  Empty preview-model audio receives one bounded automatic retry. Exhaust ADK
  specialist generators in the calling task so tracing contexts close correctly.
- Preserve completed stages on failure and allow `/retry` without repeating
  already delivered stages. Network errors are logged without secret values.
- Async API calls and background per-chat tasks keep polling responsive. One
  operation per chat; independent chats can progress concurrently.
- Media stays in memory; conversion uses pipes, leaving no temporary user files.
  Release media/history after completion and on reset. Sessions expire after an
  hour of inactivity; notify affected chats and allow a fresh run.
- Offline tests cover the full flow, isolation, input guards, retries and reset
  during generation. Live checks use the supplied local keys, never committed.

## State and contracts

`awaiting_photo -> checking_photo -> awaiting_interview -> profiling ->
converting -> scripting -> narrating -> complete`.

Typed contracts: InterviewTurn(question), InterviewAnswer(question, answer),
Dossier(summary, animal, rationale), DocumentaryScript(text), Media(data,
mime_type). Validate model output at each boundary. User answers and photo
contents are data, never instructions that can change the pipeline or count.

## Delivery

Local Python environment, Windows and POSIX check scripts, reproducible pinned
dependencies, `.env.example`, README with setup and demonstration checklist.
Live Telegram end-to-end verification requires the user to send a portrait.
