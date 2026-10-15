# ROADMAP

The lesson's seven phases are implemented locally. Automated verification is
recorded in `2026-10-15-documentary/validation.md`. A phase is fully accepted
only after the real Telegram demonstration; that final manual gate is pending.

| Phase | Delivered behaviour | Automated evidence |
| --- | --- | --- |
| 1. Gateway | Local Python, long polling, private chat commands, ignored `.env` | Gateway tests; Telegram getMe and polling startup |
| 2. Bouncer | Async vision verdict; rejects non-human inputs | Offline pass/reject tests; live synthetic drawing rejection |
| 3. Interviewer | Five sequential questions; stored answers; animal dossier; root ADK orchestration | Real ADK offline flow; live question and dossier generation |
| 4. Converter | Original photo plus dossier in one native multimodal request | Offline delivery tests; live generated JPEG decoded successfully |
| 5. Scripter | Single 60–90 word paragraph delivered in chat | Contract tests; live 79-word script |
| 6. Narrator | Course Gemini TTS model; PCM to OGG/Opus; Telegram voice dispatch | Local Opus stream tests; live speech encoding |
| 7. Resilience | Cancel/reset, isolated chats, wrong-input guards, retry, idle expiry | Offline flow and runtime cancellation/retry/isolation tests |

## Final manual acceptance

- [ ] Send `/start`, reject an object photo, then accept a real portrait.
- [ ] Answer all five questions in Telegram.
- [ ] Inspect the hybrid portrait, read the script and listen to the voice note.
- [ ] `/restart` and complete a second run without restarting Python.
- [ ] Try `/restart` while generating, and a photo during the interview.

## Delivery status

The bot is running locally as `@Music314Bot`. The workspace contains specs,
source, tests, cross-platform check scripts, installed pre-commit checks and
Gitleaks. API keys are stored only in the ignored local `.env` file.
The public GitHub repository is the submission source. Codio and TA checkouts
must supply their own local `.env`; credentials and local process logs are
excluded from the committed files. The manual class demonstration remains pending.
