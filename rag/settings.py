"""RAG engine settings, read from the process environment and the root .env file."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

RAG_DIR = Path(__file__).resolve().parent
REPO_ROOT = RAG_DIR.parent
ROOT_ENV_PATH = REPO_ROOT / ".env"
TEST_ENV_PATH = REPO_ROOT / ".env.test"

NOTION_TOKEN_KEY = "RAG_NOTION_TOKEN"
GEMINI_API_KEY_KEY = "RAG_GEMINI_API_KEY"
GOOGLE_SERVICE_ACCOUNT_FILE_KEY = "RAG_GOOGLE_SERVICE_ACCOUNT_FILE"
GEMINI_MODEL_KEY = "RAG_GEMINI_MODEL"
TEXT_THRESHOLD_KEY = "RAG_TEXT_THRESHOLD"
IMAGE_THRESHOLD_KEY = "RAG_IMAGE_THRESHOLD"
BATCH_SIZE_KEY = "RAG_BATCH_SIZE"
LIVE_TESTS_KEY = "RAG_LIVE_TESTS"
CORS_ORIGINS_KEY = "FUXI_CORS_ORIGINS"
REBUILD_COOLDOWN_MINUTES_KEY = "RAG_REBUILD_COOLDOWN_MINUTES"

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_TEXT_THRESHOLD = 0.5
DEFAULT_IMAGE_THRESHOLD = 0.25
DEFAULT_BATCH_SIZE = 16
MIN_THRESHOLD = 0.0
MAX_THRESHOLD = 1.0
MIN_BATCH_SIZE = 1
DEFAULT_REBUILD_COOLDOWN_MINUTES = 10.0
MIN_REBUILD_COOLDOWN_MINUTES = 0.0

TRUE_VALUE = "true"
LIST_SEPARATOR = ","
ENV_FILE_ENCODING = "utf-8"


class SettingsError(ValueError):
    """A setting has an invalid value."""


class MissingSettingError(RuntimeError):
    """A required setting is used but has no value."""


@dataclass(frozen=True)
class Settings:
    gemini_model: str = DEFAULT_GEMINI_MODEL
    text_threshold: float = DEFAULT_TEXT_THRESHOLD
    image_threshold: float = DEFAULT_IMAGE_THRESHOLD
    batch_size: int = DEFAULT_BATCH_SIZE
    live_tests: bool = False
    cors_origins: tuple[str, ...] = ()
    # After a failed or empty build, Init_RAG answers empty for this long before it builds again.
    rebuild_cooldown_minutes: float = DEFAULT_REBUILD_COOLDOWN_MINUTES
    notion_token: str | None = field(default=None, repr=False)
    gemini_api_key: str | None = field(default=None, repr=False)
    google_service_account_file: str | None = field(default=None, repr=False)

    def require_notion_token(self) -> str:
        return _require(self.notion_token, NOTION_TOKEN_KEY)

    def require_gemini_api_key(self) -> str:
        return _require(self.gemini_api_key, GEMINI_API_KEY_KEY)

    def require_google_service_account_file(self) -> Path:
        """The key file path; a relative path is resolved from the repository root."""
        path = Path(_require(self.google_service_account_file, GOOGLE_SERVICE_ACCOUNT_FILE_KEY))
        return path if path.is_absolute() else REPO_ROOT / path


def load_settings(
    env_path: Path = ROOT_ENV_PATH, environ: Mapping[str, str] | None = None
) -> Settings:
    """Read settings; process environment values win over the .env file."""
    values = {**read_env_file(env_path), **(os.environ if environ is None else environ)}
    return Settings(
        notion_token=_text(values, NOTION_TOKEN_KEY),
        gemini_api_key=_text(values, GEMINI_API_KEY_KEY),
        google_service_account_file=_text(values, GOOGLE_SERVICE_ACCOUNT_FILE_KEY),
        gemini_model=_text(values, GEMINI_MODEL_KEY) or DEFAULT_GEMINI_MODEL,
        text_threshold=_threshold(values, TEXT_THRESHOLD_KEY, DEFAULT_TEXT_THRESHOLD),
        image_threshold=_threshold(values, IMAGE_THRESHOLD_KEY, DEFAULT_IMAGE_THRESHOLD),
        batch_size=_batch_size(values),
        live_tests=(_text(values, LIVE_TESTS_KEY) or "").lower() == TRUE_VALUE,
        cors_origins=_list(values, CORS_ORIGINS_KEY),
        rebuild_cooldown_minutes=_rebuild_cooldown_minutes(values),
    )


def read_env_file(env_path: Path) -> dict[str, str]:
    """The .env values (python-dotenv: comments, quotes, export lines); a key without a value is left out."""
    if not env_path.is_file():
        return {}
    values = dotenv_values(env_path, interpolate=False, encoding=ENV_FILE_ENCODING)
    return {key: value for key, value in values.items() if value is not None}


def _require(value: str | None, key: str) -> str:
    if not value:
        raise MissingSettingError(f"{key} is not set")
    return value


def _text(values: Mapping[str, str], key: str) -> str | None:
    value = values.get(key, "").strip()
    return value or None


def _threshold(values: Mapping[str, str], key: str, default: float) -> float:
    raw = _text(values, key)
    if raw is None:
        return default
    try:
        threshold = float(raw)
    except ValueError as error:
        raise SettingsError(f"{key} must be a number from 0 to 1") from error
    if not MIN_THRESHOLD <= threshold <= MAX_THRESHOLD:
        raise SettingsError(f"{key} must be a number from 0 to 1")
    return threshold


def _batch_size(values: Mapping[str, str]) -> int:
    raw = _text(values, BATCH_SIZE_KEY)
    if raw is None:
        return DEFAULT_BATCH_SIZE
    try:
        batch_size = int(raw)
    except ValueError as error:
        raise SettingsError(f"{BATCH_SIZE_KEY} must be a whole number of at least 1") from error
    if batch_size < MIN_BATCH_SIZE:
        raise SettingsError(f"{BATCH_SIZE_KEY} must be a whole number of at least 1")
    return batch_size


def _rebuild_cooldown_minutes(values: Mapping[str, str]) -> float:
    raw = _text(values, REBUILD_COOLDOWN_MINUTES_KEY)
    if raw is None:
        return DEFAULT_REBUILD_COOLDOWN_MINUTES
    message = f"{REBUILD_COOLDOWN_MINUTES_KEY} must be a number of minutes, at least 0"
    try:
        minutes = float(raw)
    except ValueError as error:
        raise SettingsError(message) from error
    if not minutes >= MIN_REBUILD_COOLDOWN_MINUTES:  # also rejects nan
        raise SettingsError(message)
    return minutes


def _list(values: Mapping[str, str], key: str) -> tuple[str, ...]:
    raw = _text(values, key) or ""
    return tuple(item.strip() for item in raw.split(LIST_SEPARATOR) if item.strip())
