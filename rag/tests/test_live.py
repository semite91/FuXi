"""LIVE tests: real models, real Notion and Gemini. They run only when RAG_LIVE_TESTS=true."""

import json

import pytest

from embedders import ImageEmbedder, TextEmbedder
from llm_client import METHODS, LlmClient
from resources.notion_resource import create_notion_resource
from settings import TEST_ENV_PATH, load_settings

QWEN_VECTOR_SIZE = 1024
CLIP_VECTOR_SIZE = 512
LIVE_SETTINGS = load_settings(TEST_ENV_PATH)

pytestmark = pytest.mark.skipif(not LIVE_SETTINGS.live_tests, reason="RAG_LIVE_TESTS is not true")


def test_real_notion_returns_documents():
    # C10
    documents = create_notion_resource(LIVE_SETTINGS).read_documents()

    assert len(documents) >= 1


def test_real_qwen_vector_has_1024_numbers():
    # D4
    assert len(TextEmbedder().embed_query("serendipity")) == QWEN_VECTOR_SIZE


def test_real_clip_vector_has_512_numbers():
    # D5
    assert len(ImageEmbedder().embed_text("a red umbrella")) == CLIP_VECTOR_SIZE


def test_real_gemini_gives_valid_content_or_none():
    # G17
    client = LlmClient(LIVE_SETTINGS)
    query = client.build_search_query("serendipity", "finding something good by chance")

    content = client.generate("serendipity", "finding something good by chance", [], [])

    assert query
    assert content is None or json.loads(content)["method"] in METHODS
