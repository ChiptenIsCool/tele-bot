"""Typed settings — the only place secrets are read.

Keys come from the process environment and/or a ``.env`` file (never from
code, never from a committed file). Missing or empty keys fail loudly at
startup with a message naming exactly what is absent.
"""

from pathlib import Path
from typing import Any

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ENV_FILE = Path(".env")

REQUIRED_KEYS = ("TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY")

# Map model field names to the environment keys users actually set, so error
# messages name the `.env` key rather than the internal Python attribute.
_FIELD_TO_ENV_KEY = {
    "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
    "gemini_api_key": "GEMINI_API_KEY",
}


class SettingsError(RuntimeError):
    """Raised when required secrets are missing or invalid. Never swallowed."""


class Settings(BaseSettings):
    """The validated secret contract for the process."""

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE, extra="ignore", case_sensitive=False
    )

    telegram_bot_token: str
    gemini_api_key: str

    def __init__(self, _env_file: Path | None = DEFAULT_ENV_FILE, **data: Any) -> None:
        """Typed ``_env_file`` so strict type checking accepts it.

        pydantic-settings reads the env file only through this keyword, but its
        generated signature is not visible to mypy. Naming it here keeps the
        contract explicit instead of casting or ignoring the check.
        """
        super().__init__(_env_file=_env_file, **data)

    @field_validator("telegram_bot_token", "gemini_api_key")
    @classmethod
    def _reject_blank_value(cls, value: str) -> str:
        """An empty or whitespace-only secret is as useless as a missing one."""
        if not value.strip():
            raise ValueError("must not be empty")
        return value


def load_settings(env_file: Path | None = DEFAULT_ENV_FILE) -> Settings:
    """Load and validate settings from the environment and ``env_file``.

    Raises:
        SettingsError: if any required key is missing or empty. Callers on the
            user's conversation path must not exist for this — it is a
            startup/programmer error and must be loud.
    """
    try:
        return Settings(_env_file=env_file)
    except ValidationError as exc:
        offending = _offending_env_keys(exc)
        raise SettingsError(
            "Missing or empty required secret(s): "
            + ", ".join(offending)
            + ". Provide them via the process environment or "
            + f"{env_file or '.env'} (see .env.example)."
        ) from exc


def _offending_env_keys(exc: ValidationError) -> list[str]:
    """Translate pydantic error locations into `.env` key names."""
    found: list[str] = []
    for error in exc.errors():
        loc: tuple[Any, ...] = error.get("loc", ())
        field = str(loc[0]).lower() if loc else ""
        env_key = _FIELD_TO_ENV_KEY.get(field)
        if env_key is None and field:
            # Unknown field (e.g. a config-level error): surface it uppercased.
            env_key = field.upper()
        if env_key:
            found.append(env_key)
    # Preserve order, drop duplicates; if nothing mapped, name every key so the
    # message is still actionable.
    return list(dict.fromkeys(found)) or list(REQUIRED_KEYS)
