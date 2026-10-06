"""Task group 1: settings loader — secrets come from .env only, and fail loudly."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from tele_bot.settings import Settings, SettingsError, load_settings


def test_loads_both_keys_from_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        'TELEGRAM_BOT_TOKEN = "from-file-token"\nGEMINI_API_KEY = "from-file-key"\n'
    )

    settings = load_settings(env_file=env_file)

    assert settings.telegram_bot_token == "from-file-token"
    assert settings.gemini_api_key == "from-file-key"


def test_real_environment_takes_precedence_over_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "from-os-env-token")
    monkeypatch.setenv("GEMINI_API_KEY", "from-os-env-key")
    env_file = tmp_path / ".env"
    env_file.write_text("TELEGRAM_BOT_TOKEN=file-token\nGEMINI_API_KEY=file-key\n")

    settings = load_settings(env_file=env_file)

    assert settings.telegram_bot_token == "from-os-env-token"
    assert settings.gemini_api_key == "from-os-env-key"


def test_fails_loudly_when_gemini_key_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("TELEGRAM_BOT_TOKEN=only-a-token\n")

    with pytest.raises(SettingsError) as exc_info:
        load_settings(env_file=env_file)

    assert "GEMINI_API_KEY" in str(exc_info.value)


def test_fails_loudly_when_telegram_token_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("GEMINI_API_KEY=only-a-key\n")

    with pytest.raises(SettingsError) as exc_info:
        load_settings(env_file=env_file)

    assert "TELEGRAM_BOT_TOKEN" in str(exc_info.value)


def test_fails_loudly_when_no_keys_anywhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(SettingsError) as exc_info:
        load_settings(env_file=tmp_path / "does-not-exist.env")

    message = str(exc_info.value)
    assert "TELEGRAM_BOT_TOKEN" in message
    assert "GEMINI_API_KEY" in message


def test_empty_values_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("TELEGRAM_BOT_TOKEN=\nGEMINI_API_KEY=\n")

    with pytest.raises(SettingsError):
        load_settings(env_file=env_file)


def test_settings_model_requires_both_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """The schema itself — not just the loader — rejects missing secrets."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, telegram_bot_token="only-token")

    with pytest.raises(ValidationError):
        Settings(_env_file=None, gemini_api_key="only-key")
