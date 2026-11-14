"""LIVE tests: real models, real Notion, Google Drive and Gemini. They run only when RAG_LIVE_TESTS=true."""

import base64
import json
import math

import httpx
import pytest

from base import RetrievedItem
from embedders import ImageEmbedder, TextEmbedder, decode_picture
from fakes import ScriptedRandom, picture_text
from llm_client import METHODS, LlmClient
from resources.google_drive_resource import create_google_drive_resource, prepare_picture
from resources.notion_resource import create_notion_resource
from settings import TEST_ENV_PATH, load_settings

QWEN_VECTOR_SIZE = 1024
CLIP_VECTOR_SIZE = 512
# A public domain photo of a dog on Wikimedia Commons.
DOG_PICTURE_URL = "https://upload.wikimedia.org/wikipedia/commons/2/26/YellowLabradorLooking_new.jpg"
DOWNLOAD_HEADERS = {"User-Agent": "fuxi-live-tests/1.0"}
DOWNLOAD_TIMEOUT_SECONDS = 60.0
HTTPS_PREFIX = "https://"
JPEG_DATA_URL_PREFIX = "data:image/jpeg;base64,"
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


def cosine_similarity(first: list[float], second: list[float]) -> float:
    dot = sum(a * b for a, b in zip(first, second))
    return dot / (math.sqrt(sum(a * a for a in first)) * math.sqrt(sum(b * b for b in second)))


def test_real_google_drive_returns_picture_documents():
    # Phase 5b C21 (reads and downloads every image shared with the service account)
    documents = create_google_drive_resource(LIVE_SETTINGS).read_documents()

    assert len(documents) >= 1
    assert all(document.metadata["type"] == "picture" for document in documents)


def test_real_clip_picture_vector_has_512_numbers():
    # Phase 5b D3
    vector = ImageEmbedder().embed_images([decode_picture(picture_text())])[0]

    assert len(vector) == CLIP_VECTOR_SIZE


def test_real_clip_puts_a_dog_picture_closer_to_a_dog_than_to_a_car():
    # Phase 5b D4
    download = httpx.get(DOG_PICTURE_URL, headers=DOWNLOAD_HEADERS, timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True)
    download.raise_for_status()
    embedder = ImageEmbedder()
    picture = decode_picture(base64.b64encode(prepare_picture(download.content)).decode("ascii"))
    picture_vector = embedder.embed_images([picture])[0]

    assert cosine_similarity(picture_vector, embedder.embed_text("a dog")) > cosine_similarity(
        picture_vector, embedder.embed_text("a car")
    )


def test_real_gemini_photo_with_a_drive_image_gives_valid_content_or_none():
    # Phase 5b G8
    image = RetrievedItem(
        document=picture_text(),
        metadata={"name": "umbrella.jpg", "path": "Photos / Paris", "type": "picture", "timestamp": "2026-09-14T18:42:10"},
        similarity=0.3,
    )
    client = LlmClient(LIVE_SETTINGS, random_source=ScriptedRandom(["photo", "story"]))

    content = client.generate("serendipity", "finding something good by chance", [], [image])

    if content is not None:
        answer = json.loads(content)
        assert answer["method"] in METHODS
        if answer["method"] == "photo":
            assert answer["image_url"].startswith((HTTPS_PREFIX, JPEG_DATA_URL_PREFIX))
