from pathlib import Path

import pytest

from settings import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_IMAGE_THRESHOLD,
    DEFAULT_REBUILD_COOLDOWN_MINUTES,
    DEFAULT_TEXT_THRESHOLD,
    REPO_ROOT,
    DatabaseSettings,
    MissingSettingError,
    SettingsError,
    load_settings,
)

FULL_ENV = """# comment line
FUXI_DB_HOST=db.fuxi.test
FUXI_DB_PORT=5433
FUXI_DB_NAME=fuxi_test
FUXI_DB_USER=fuxi_reader
FUXI_DB_PASSWORD=db-test-password
RAG_GEMINI_API_KEY="gemini-test-key"
RAG_GEMINI_MODEL=gemini-test-model
RAG_TEXT_THRESHOLD=0.6
RAG_IMAGE_THRESHOLD=0.3
RAG_BATCH_SIZE=8
RAG_LIVE_TESTS=true
FUXI_CORS_ORIGINS=http://localhost:5173, https://fuxi.example
RAG_REBUILD_COOLDOWN_MINUTES=2.5
"""


def write_env(tmp_path: Path, content: str) -> Path:
    env_path = tmp_path / ".env"
    env_path.write_text(content, encoding="utf-8")
    return env_path


def test_every_rag_key_is_parsed(tmp_path):
    # B1
    settings = load_settings(write_env(tmp_path, FULL_ENV), environ={})

    assert settings.require_database() == DatabaseSettings(
        host="db.fuxi.test", port=5433, name="fuxi_test", user="fuxi_reader", password="db-test-password"
    )  # Phase 6b D3
    assert settings.require_gemini_api_key() == "gemini-test-key"
    assert settings.gemini_model == "gemini-test-model"
    assert settings.text_threshold == 0.6
    assert settings.image_threshold == 0.3
    assert settings.batch_size == 8
    assert isinstance(settings.batch_size, int)
    assert settings.live_tests is True
    assert settings.cors_origins == ("http://localhost:5173", "https://fuxi.example")
    assert settings.rebuild_cooldown_minutes == 2.5  # H18


def test_process_environment_overrides_the_env_file(tmp_path):
    # B1
    settings = load_settings(write_env(tmp_path, FULL_ENV), environ={"RAG_BATCH_SIZE": "4"})

    assert settings.batch_size == 4


def test_missing_numbers_use_defaults(tmp_path):
    # B2
    settings = load_settings(write_env(tmp_path, "RAG_TEXT_THRESHOLD=\n"), environ={})

    assert settings.text_threshold == DEFAULT_TEXT_THRESHOLD == 0.5
    assert settings.image_threshold == DEFAULT_IMAGE_THRESHOLD == 0.25
    assert settings.batch_size == DEFAULT_BATCH_SIZE == 16
    assert settings.rebuild_cooldown_minutes == DEFAULT_REBUILD_COOLDOWN_MINUTES == 10  # H18


def test_missing_env_file_uses_defaults(tmp_path):
    # B2
    settings = load_settings(tmp_path / "absent.env", environ={})

    assert settings.batch_size == DEFAULT_BATCH_SIZE
    assert settings.live_tests is False
    assert settings.cors_origins == ()


def test_missing_model_uses_default(tmp_path):
    # B3
    settings = load_settings(write_env(tmp_path, ""), environ={})

    assert settings.gemini_model == DEFAULT_GEMINI_MODEL == "gemini-3.8-flash"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("RAG_TEXT_THRESHOLD", "1.5"),
        ("RAG_TEXT_THRESHOLD", "-0.1"),
        ("RAG_IMAGE_THRESHOLD", "2"),
        ("RAG_IMAGE_THRESHOLD", "abc"),
        ("RAG_BATCH_SIZE", "0"),
        ("RAG_BATCH_SIZE", "1.5"),
        ("RAG_REBUILD_COOLDOWN_MINUTES", "-1"),  # H18
        ("RAG_REBUILD_COOLDOWN_MINUTES", "soon"),  # H18
    ],
)
def test_invalid_value_error_names_the_key(tmp_path, key, value):
    # B4
    with pytest.raises(SettingsError, match=key):
        load_settings(write_env(tmp_path, f"{key}={value}\n"), environ={})


def test_missing_secrets_do_not_stop_loading(tmp_path):
    # B5
    settings = load_settings(write_env(tmp_path, ""), environ={})

    with pytest.raises(MissingSettingError, match="RAG_GEMINI_API_KEY"):
        settings.require_gemini_api_key()


@pytest.mark.parametrize("key", ["FUXI_DB_HOST", "FUXI_DB_PORT", "FUXI_DB_NAME", "FUXI_DB_USER", "FUXI_DB_PASSWORD"])
def test_missing_database_key_fails_only_when_used(tmp_path, key):
    # Phase 6b D3, D8
    content = "".join(line + "\n" for line in FULL_ENV.splitlines() if not line.startswith(key))
    settings = load_settings(write_env(tmp_path, content), environ={})

    with pytest.raises(MissingSettingError, match=key):
        settings.require_database()


def test_database_port_must_be_a_whole_number(tmp_path):
    # Phase 6b D3
    settings = load_settings(write_env(tmp_path, FULL_ENV.replace("5433", "port")), environ={})

    with pytest.raises(SettingsError, match="FUXI_DB_PORT"):
        settings.require_database()


def test_printed_settings_hide_the_database_password(tmp_path):
    # Phase 6b D8
    settings = load_settings(write_env(tmp_path, FULL_ENV), environ={})

    assert "db-test-password" not in repr(settings)
    assert "db-test-password" not in repr(settings.require_database())


def test_notion_token_is_no_env_setting(tmp_path):
    # Phase 6b D9: the token lives in the Settings table, not in .env
    settings = load_settings(write_env(tmp_path, "RAG_NOTION_TOKEN=old-env-token\n"), environ={})

    assert not hasattr(settings, "notion_token")
    assert not hasattr(settings, "require_notion_token")
    assert "old-env-token" not in repr(settings)


def test_settings_with_database_values_can_be_hashed(tmp_path):
    # Phase 6b review SRS-13: a frozen Settings stays usable as a dict key or set member
    env_file = write_env(tmp_path, "FUXI_DB_HOST=localhost\nFUXI_DB_NAME=fuxi\n")

    first, second = (load_settings(env_file, environ={}) for _ in range(2))

    assert {first: "cached"}[second] == "cached"


def test_inline_comment_and_export_lines_are_read(tmp_path):
    # B6
    content = "RAG_BATCH_SIZE=8 # smaller batches\nexport RAG_GEMINI_MODEL=gemini-export-model\n"

    settings = load_settings(write_env(tmp_path, content), environ={})

    assert settings.batch_size == 8
    assert settings.gemini_model == "gemini-export-model"


def test_key_without_value_uses_the_default(tmp_path):
    # B6
    settings = load_settings(write_env(tmp_path, "RAG_BATCH_SIZE\n"), environ={})

    assert settings.batch_size == DEFAULT_BATCH_SIZE


def test_zero_cooldown_is_accepted(tmp_path):
    # B4 H18
    settings = load_settings(write_env(tmp_path, "RAG_REBUILD_COOLDOWN_MINUTES=0\n"), environ={})

    assert settings.rebuild_cooldown_minutes == 0


GOOGLE_ENV = "GOOGLE_CLIENT_ID=google-test-client.apps.googleusercontent.com\nGOOGLE_CLIENT_SECRET=google-test-secret\n"


def test_google_client_keys_are_read(tmp_path):
    # Phase 6c D1: the same keys the API reads
    settings = load_settings(write_env(tmp_path, GOOGLE_ENV), environ={})

    assert settings.require_google_client() == ("google-test-client.apps.googleusercontent.com", "google-test-secret")


@pytest.mark.parametrize(("content", "key"), [
    ("GOOGLE_CLIENT_SECRET=google-test-secret\n", "GOOGLE_CLIENT_ID"),
    ("GOOGLE_CLIENT_ID=google-test-client\nGOOGLE_CLIENT_SECRET=\n", "GOOGLE_CLIENT_SECRET"),
])
def test_missing_google_client_key_fails_only_when_used_and_names_the_key(tmp_path, content, key):
    # Phase 6c D8
    settings = load_settings(write_env(tmp_path, content), environ={})

    with pytest.raises(MissingSettingError, match=key):
        settings.require_google_client()


def test_printed_settings_hide_the_google_client_secret(tmp_path):
    # Phase 6c H5
    settings = load_settings(write_env(tmp_path, GOOGLE_ENV), environ={})

    assert "google-test-secret" not in repr(settings)
    assert "google-test-secret" not in str(settings)


def test_google_service_account_file_is_no_setting(tmp_path):
    # Phase 6c D14: the Learner's own Google account replaces the service account
    settings = load_settings(write_env(tmp_path, "RAG_GOOGLE_SERVICE_ACCOUNT_FILE=rag/secrets/drive.json\n"), environ={})

    assert not hasattr(settings, "google_service_account_file")
    assert not hasattr(settings, "require_google_service_account_file")


MOVIE_ENV = "RAG_TMDB_TOKEN=tmdb-test-token\nRAG_LETTERBOXD_WATCHED_FILE=rag/data/letterboxd/watched.csv\n"


def test_tmdb_token_and_watched_file_are_read(tmp_path):
    # Phase 5c B1
    content = f"RAG_TMDB_TOKEN=tmdb-test-token\nRAG_LETTERBOXD_WATCHED_FILE={tmp_path / 'watched.csv'}\n"

    settings = load_settings(write_env(tmp_path, content), environ={})

    assert settings.require_tmdb_token() == "tmdb-test-token"
    assert settings.require_letterboxd_watched_file() == tmp_path / "watched.csv"


def test_relative_watched_file_is_resolved_from_the_repository_root(tmp_path):
    # Phase 5c B2
    settings = load_settings(write_env(tmp_path, MOVIE_ENV), environ={})

    assert settings.require_letterboxd_watched_file() == REPO_ROOT / "rag" / "data" / "letterboxd" / "watched.csv"


def test_missing_tmdb_token_and_watched_file_fail_only_when_used(tmp_path):
    # Phase 5c B3
    settings = load_settings(write_env(tmp_path, "RAG_TMDB_TOKEN=\nRAG_LETTERBOXD_WATCHED_FILE\n"), environ={})

    with pytest.raises(MissingSettingError, match="RAG_TMDB_TOKEN"):
        settings.require_tmdb_token()
    with pytest.raises(MissingSettingError, match="RAG_LETTERBOXD_WATCHED_FILE"):
        settings.require_letterboxd_watched_file()


def test_printed_settings_hide_the_tmdb_token(tmp_path):
    # Phase 5c B4
    settings = load_settings(write_env(tmp_path, MOVIE_ENV), environ={})

    assert "tmdb-test-token" not in repr(settings)
    assert "tmdb-test-token" not in str(settings)
