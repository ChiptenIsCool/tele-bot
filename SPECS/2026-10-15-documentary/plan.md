# Implementation plan

1. Write offline flow tests before implementation; observe failure.
2. Extend typed state and contracts; add async Gemini/ADK specialist adapters.
3. Add the Interviewer orchestrator with deterministic five-turn limits.
4. Wire Telegram commands, background operations, cancellation and retries.
5. Add OGG/Opus encoding, configurable models and portable development scripts.
6. Run offline tests, lint, format and mypy; inspect secrets hygiene.
7. Verify Telegram credentials, Gemini text/vision/image/audio access and start
   local polling. Report live limitations separately from offline results.
