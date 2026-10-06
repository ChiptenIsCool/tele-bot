# The Telegram Documentaries

Upload a portrait photo to a Telegram bot and get back a narrated, comedy
wildlife-documentary about yourself — a hybrid animal portrait plus a dramatic
British-documentary voice note.

## Pipeline

1. **The Bouncer** — vision gate. Confirms a human is in the frame; cheekily
   rejects anything else and resets the session.
2. **The Interviewer** — the orchestrator. Asks 5–7 questions one at a time
   and builds a behavioural dossier tied to your `chat_id`.
3. **The Converter** — merges your photo with the dossier into a hybrid animal
   portrait, sent straight back into the chat.
4. **The Scripter** — writes a ~60–90 word dramatic narration.
5. **The Narrator** — renders the script to speech and delivers it as a
   Telegram voice note.

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/ChiptenIsCool/tele-bot.git
cd tele-bot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure your secrets (required)

This project needs two API keys. They are **not** included in the repository —
you must supply your own by creating a `.env` file in the project root:

```
TELEGRAM_BOT_TOKEN = "<your telegram bot token>"
GEMINI_API_KEY = "<your google gemini api key>"
```

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Key | What it is | Where to get it |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Token for your Telegram bot | Talk to [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` → copy the token it gives you |
| `GEMINI_API_KEY` | Google Gemini API key | [Google AI Studio](https://aistudio.google.com/apikey) → **Create API key** |

> **Never commit your `.env` file.** It is listed in `.gitignore` and must
> stay out of version control. If a secret is ever pushed, revoke and rotate
> it immediately.

### 4. Run the bot

```bash
python3 -m tele_bot.main  # long polling (no webhooks)
```

The bot uses Telegram long polling — no webhook or public URL is required.

## Commands

| Command | Effect |
| --- | --- |
| `/start` | Begin a fresh session — clears your state and temporary files |
| `/restart` | Same as `/start`: reset and start over, without restarting the process |

> **_Implemented so far — the Bouncer only.**_ The bot currently accepts one
> thing: a photo. It downloads the image, asks Gemini 3.1 Flash Lite whether a
> human is in the frame, and replies accordingly:
>
> - **Human found** → "Right then — one human, duly noted. Let's get started."
>   and the session advances to the interview phase.
> - **No human** (animals, landscapes, objects, empty frames) → a cheeky
>   rejection and the session resets to square one, ready to try again.
> - **Gemini unavailable/unparseable** → a gentle "couldn't make that out"
>   reply; the process never crashes on the user's behalf.
>
> The Interviewer, Converter, Scripter, and Narrator are planned (see
> `SPECS/ROADMAP.md`) but not built yet — so `/start` and `/restart` are
> documented contracts that arrive with the resilience phase.

## Development

| Script | Runs |
| --- | --- |
| `scripts/test` | Runs the pytest suite (`python3 -m pytest`) |
| `scripts/hooks` | Runs lint and type checks (`ruff check .`, `ruff format --check .`, `mypy`) |

The unit suite mocks Telegram and Gemini (fast, offline). Live checks against
the real Gemini API live in `tests/integration/` and are skipped
automatically when `GEMINI_API_KEY` is absent:

```bash
pytest tests/integration -m live   # real Gemini; generates its own images
```
