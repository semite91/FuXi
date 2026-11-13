from pathlib import Path

import pytest

from settings import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_IMAGE_THRESHOLD,
    DEFAULT_TEXT_THRESHOLD,
    MissingSettingError,
    SettingsError,
    load_settings,
)

FULL_ENV = """# comment line
RAG_NOTION_TOKEN=notion-test-token
RAG_GEMINI_API_KEY="gemini-test-key"
RAG_GEMINI_MODEL=gemini-test-model
RAG_TEXT_THRESHOLD=0.6
RAG_IMAGE_THRESHOLD=0.3
RAG_BATCH_SIZE=8
RAG_LIVE_TESTS=true
FUXI_CORS_ORIGINS=http://localhost:5173, https://fuxi.example
"""


def write_env(tmp_path: Path, content: str) -> Path:
    env_path = tmp_path / ".env"
    env_path.write_text(content, encoding="utf-8")
    return env_path


def test_every_rag_key_is_parsed(tmp_path):
    # B1
    settings = load_settings(write_env(tmp_path, FULL_ENV), environ={})

    assert settings.require_notion_token() == "notion-test-token"
    assert settings.require_gemini_api_key() == "gemini-test-key"
    assert settings.gemini_model == "gemini-test-model"
    assert settings.text_threshold == 0.6
    assert settings.image_threshold == 0.3
    assert settings.batch_size == 8
    assert isinstance(settings.batch_size, int)
    assert settings.live_tests is True
    assert settings.cors_origins == ("http://localhost:5173", "https://fuxi.example")


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
    ],
)
def test_invalid_value_error_names_the_key(tmp_path, key, value):
    # B4
    with pytest.raises(SettingsError, match=key):
        load_settings(write_env(tmp_path, f"{key}={value}\n"), environ={})


def test_missing_secrets_do_not_stop_loading(tmp_path):
    # B5
    settings = load_settings(write_env(tmp_path, ""), environ={})

    with pytest.raises(MissingSettingError, match="RAG_NOTION_TOKEN"):
        settings.require_notion_token()
    with pytest.raises(MissingSettingError, match="RAG_GEMINI_API_KEY"):
        settings.require_gemini_api_key()


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
