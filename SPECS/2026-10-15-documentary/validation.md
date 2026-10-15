# Validation — complete documentary pipeline

Verified locally on 15 October 2026, Python 3.12 / Windows.

## Automated checks

- [x] 84 offline tests pass; the two original live Bouncer tests are deselected.
- [x] Ruff lint, Ruff format check and strict mypy pass.
- [x] Full flow runs through a real ADK runner with stubbed Gemini services.
- [x] Two complete photo/interview/image/script/audio runs succeed in one process
  with only a session reset between them (automated rubric regression check).
- [x] Five questions, exactly one at a time; photo, script and audio delivered.
- [x] Non-human rejection and wrong-stage inputs preserve/reset appropriate state.
- [x] Independent chats cannot share answers or media.
- [x] Reset cancels active image work and prevents late output in the tested flow.
- [x] Image, script and speech failures support retry without repeating completed stages.
- [x] Actual local FFmpeg encoding produces an OGG stream with an Opus header.
- [x] SDK schema compatibility, single-question validation and bounded correction tested.
- [x] Completed sessions release profile/answers; ADK history cleared after each turn.
- [x] `.env` is ignored; neither credential occurs in tracked/unignored project files.
- [x] Gitleaks scan of all 46 tracked/unignored working files passes.
- [x] Pre-commit hook installed with project checks and Gitleaks.

## Live integration checks

`python -X utf8 scripts/check_live.py` succeeded with the local keys:

- [x] Telegram credentials resolve to `@Music314Bot`; no webhook configured.
- [x] All three course models are listed by the Gemini API.
- [x] Gemini returns a concrete interview question and a personality dossier.
- [x] Gemini Scripter returns a validated 79-word paragraph.
- [x] Vision correctly rejects the synthetic drawing as not a real human photo.
- [x] Converter returns a valid JPEG (803,533 bytes) using image plus dossier.
- [x] Narrator returns audio encoded to valid OGG/Opus (266,692 bytes).
- [x] Local long-polling process starts successfully.

A real Telegram run also reached portrait and script delivery. Its TTS request
returned no audio. The implementation now retries empty speech output once;
this recovery is tested offline. ADK specialists now exhaust their generators
in the calling task, with a regression assertion against tracing-context detach
errors. The local bot was restarted to load these fixes; its prior in-memory
session was cleared. The final real-user audio walkthrough still needs repeating.

These checks generate media in memory and send no Telegram messages. The live
sample is a drawing. Acceptance of a real portrait, perceived hybrid likeness,
voice playback and the complete two-run phone demonstration remain manual checks.

## Remaining manual checks

See the checklist in `SPECS/ROADMAP.md`. No claim of a completed real-user
end-to-end demonstration is made until the user performs that walkthrough.

## Implementation decisions

- Retained the original Bouncer modules and their unit/integration tests. The
  production gateway uses the new async ADK pipeline; removed the old photo-only
  gateway to keep the process entry point unambiguous.
- Exactly five questions satisfies the lesson's 5–7 requirement.
- Media stays in memory and conversion uses pipes; reset has no on-disk user
  media to clean. SDK-owned ADK history is explicitly cleared as well.
- SDK schema strips unsupported `additionalProperties` while local contracts
  continue to reject extra fields. PCM MIME matching is case-insensitive.
- Added `/retry`, private-chat guards and inactivity expiry as modest resilience
  measures. Expiry is configured at one hour; its timer is not live-time tested.
- Default models follow the lesson; optional environment settings support explicit
  changes if course/model access changes. No automatic provider substitution.
- `requirements-lock.txt` records the tested Windows Python 3.12 dependency set;
  `requirements.txt` remains the cross-platform direct dependency manifest.
