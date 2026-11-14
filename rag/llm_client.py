"""Gemini calls: the retrieval search query and the Word Content for one word."""

import json
import logging
import random
import re
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from google import genai
from google.genai import types

from base import METADATA_NAME, METADATA_PATH, RetrievedItem
from settings import REPO_ROOT, Settings

PROMPTS_DIR = REPO_ROOT / "prompts"
RETRIEVAL_PROMPT_FILE = "retrieval.txt"
TEXT_PROMPT_FILE = "llm.txt"
WEB_PROMPT_FILE = "llm_web.txt"
PROMPT_ENCODING = "utf-8"

STORY = "story"
QUOTE = "quote"
FILM_REFERENCE = "film reference"
PHOTO = "photo"
MUSIC = "music"
TEXT_METHODS = (STORY, QUOTE, FILM_REFERENCE)
WEB_METHODS = (PHOTO, MUSIC)
METHODS = TEXT_METHODS + WEB_METHODS
MAX_METHOD_ATTEMPTS = 2

JSON_MIME_TYPE = "application/json"
COMPACT_JSON_SEPARATORS = (",", ":")
SUCCESS_STATUS = "success"
HTTPS_SCHEME = "https"
# Drive images are sent to Gemini with the image_url "drive:<n>", n being the image's 1-based place in the results.
DRIVE_IMAGE_URL_FORMAT = "drive:{position}"
DRIVE_IMAGE_URL_PATTERN = re.compile(r"drive:(\d+)")
FIRST_IMAGE_POSITION = 1
JPEG_DATA_URL_FORMAT = "data:image/jpeg;base64,{data}"
QUERY_FALLBACK_FORMAT = "{word}: {meaning}"
CODE_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
METHOD_SEPARATOR_PATTERN = re.compile(r"[\s_\-]+")

TEXT_FIELDS = ("title", "content")
MUSIC_TEXT_FIELDS = ("song_title", "artist", "lyrics_excerpt")
SOURCE_REFERENCE_FIELD = "source_reference"
IMAGE_URL_FIELD = "image_url"
SONG_URL_FIELD = "song_url"

logger = logging.getLogger(__name__)

GeminiClientFactory = Callable[[], Any]


class MethodFailedError(Exception):
    """Gemini's answer cannot be used as Word Content."""


class LlmClient:
    def __init__(
        self,
        settings: Settings,
        gemini_client_factory: GeminiClientFactory | None = None,
        random_source: Any = None,
        prompts_dir: Path = PROMPTS_DIR,
    ) -> None:
        self._settings = settings
        self._gemini_client_factory = gemini_client_factory or (
            lambda: genai.Client(api_key=settings.require_gemini_api_key())
        )
        self._gemini_client: Any = None
        self._random = random_source or random.SystemRandom()
        self._prompts_dir = prompts_dir
        self._prompts: dict[str, str] = {}
        self._prompts_lock = threading.Lock()

    def gemini_client(self) -> Any:
        """Created on first use, so a missing key fails only when Gemini is needed."""
        if self._gemini_client is None:
            self._gemini_client = self._gemini_client_factory()
        return self._gemini_client

    def prompt(self, prompt_file: str) -> str:
        """The prompt text; each file is read on its own first use and kept, so a missing file breaks only its calls."""
        with self._prompts_lock:
            if prompt_file not in self._prompts:
                self._prompts[prompt_file] = (self._prompts_dir / prompt_file).read_text(encoding=PROMPT_ENCODING)
            return self._prompts[prompt_file]

    def build_search_query(self, word: str, meaning: str) -> str:
        fallback = QUERY_FALLBACK_FORMAT.format(word=word, meaning=meaning)
        try:
            answer = self._ask(RETRIEVAL_PROMPT_FILE, {"word": word, "meaning": meaning}, use_search=False)
            query = answer.get("query")
        except Exception as error:
            logger.warning("Search query for %s failed: %s", word, _describe(error))
            return fallback
        return query.strip() if isinstance(query, str) and query.strip() else fallback

    def generate(
        self,
        word: str,
        meaning: str,
        text_results: Sequence[RetrievedItem],
        image_results: Sequence[RetrievedItem],
    ) -> str | None:
        """Word Content as a compact JSON string, or None when two methods fail."""
        context = _build_context(text_results, image_results)
        remaining = list(METHODS)
        for _ in range(MAX_METHOD_ATTEMPTS):
            method = self._random.choice(remaining)
            remaining.remove(method)
            try:
                content = self._generate_with_method(word, meaning, method, context, image_results)
                return json.dumps(content, ensure_ascii=False, separators=COMPACT_JSON_SEPARATORS)
            except Exception as error:
                logger.warning("Method %s for %s failed: %s", method, word, _describe(error))
        return None

    def _generate_with_method(
        self,
        word: str,
        meaning: str,
        method: str,
        context: dict[str, Any],
        image_results: Sequence[RetrievedItem],
    ) -> dict[str, Any]:
        is_web = method in WEB_METHODS
        payload = {"word": word, "meaning": meaning, "available_methods": [method], "retrieved_context": context}
        answer = self._ask(WEB_PROMPT_FILE if is_web else TEXT_PROMPT_FILE, payload, use_search=is_web)
        return _build_content(method, answer, image_results)

    def _ask(self, prompt_file: str, payload: dict[str, Any], use_search: bool) -> dict[str, Any]:
        response = self.gemini_client().models.generate_content(
            model=self._settings.gemini_model,
            contents=json.dumps(payload, ensure_ascii=False),
            config=self._config(prompt_file, use_search),
        )
        return _parse_json_object(response.text)

    def _config(self, prompt_file: str, use_search: bool) -> types.GenerateContentConfig:
        system_instruction = self.prompt(prompt_file)
        if use_search:
            # A JSON mime type is not combined with tools; the JSON text is parsed instead.
            return types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            )
        return types.GenerateContentConfig(
            system_instruction=system_instruction, response_mime_type=JSON_MIME_TYPE
        )


def _build_context(
    text_results: Sequence[RetrievedItem], image_results: Sequence[RetrievedItem]
) -> dict[str, list[dict[str, Any]]]:
    return {
        "texts": [
            {"document": item.document, "name": item.metadata.get(METADATA_NAME), "path": item.metadata.get(METADATA_PATH)}
            for item in text_results
        ],
        # Image documents are Base64 data, so only a drive: URL, the name and the path are sent.
        "images": [
            {
                IMAGE_URL_FIELD: DRIVE_IMAGE_URL_FORMAT.format(position=position),
                "name": item.metadata.get(METADATA_NAME),
                "path": item.metadata.get(METADATA_PATH),
            }
            for position, item in enumerate(image_results, start=FIRST_IMAGE_POSITION)
        ],
    }


def _parse_json_object(text: str | None) -> dict[str, Any]:
    cleaned = CODE_FENCE_PATTERN.sub("", (text or "").strip())
    if not cleaned:
        raise MethodFailedError("empty answer")
    try:
        answer = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise MethodFailedError("answer is not JSON") from error
    if not isinstance(answer, dict):
        raise MethodFailedError("answer is not a JSON object")
    return answer


def _build_content(method: str, answer: dict[str, Any], image_results: Sequence[RetrievedItem]) -> dict[str, Any]:
    if answer.get("status") != SUCCESS_STATUS:
        raise MethodFailedError(f"status {answer.get('status')}")
    if _normalize_method(answer.get("method")) != _normalize_method(method):
        raise MethodFailedError(f"returned method {answer.get('method')}")
    memory_aid = answer.get("memory_aid")
    if not isinstance(memory_aid, dict):
        raise MethodFailedError("memory_aid is missing")
    if method == PHOTO:
        return {"method": method, IMAGE_URL_FIELD: _photo_url(memory_aid, image_results)}
    if method == MUSIC:
        fields = {name: _text(memory_aid, name) for name in MUSIC_TEXT_FIELDS}
        return {
            "method": method,
            "song_title": fields["song_title"],
            "artist": fields["artist"],
            SONG_URL_FIELD: _https_url(memory_aid, SONG_URL_FIELD),
            "lyrics_excerpt": fields["lyrics_excerpt"],
        }
    reference = memory_aid.get(SOURCE_REFERENCE_FIELD)
    return {
        "method": method,
        **{name: _text(memory_aid, name) for name in TEXT_FIELDS},
        SOURCE_REFERENCE_FIELD: reference if isinstance(reference, str) and reference else None,
    }


def _normalize_method(method: Any) -> str:
    """'Film_Reference', 'film-reference' and 'film reference' are the same method."""
    if not isinstance(method, str):
        return ""
    return METHOD_SEPARATOR_PATTERN.sub(" ", method).strip().lower()


def _text(memory_aid: dict[str, Any], name: str) -> str:
    value = memory_aid.get(name)
    if not isinstance(value, str) or not value.strip():
        raise MethodFailedError(f"{name} is missing")
    return value.strip()


def _photo_url(memory_aid: dict[str, Any], image_results: Sequence[RetrievedItem]) -> str:
    """A "drive:<n>" reference becomes that sent image's JPEG data URL; anything else must be an https URL."""
    reference = DRIVE_IMAGE_URL_PATTERN.fullmatch(_text(memory_aid, IMAGE_URL_FIELD))
    if reference is None:
        return _https_url(memory_aid, IMAGE_URL_FIELD)
    position = int(reference.group(1))
    if not FIRST_IMAGE_POSITION <= position <= len(image_results):
        raise MethodFailedError(f"{IMAGE_URL_FIELD} refers to an image that was not sent")
    return JPEG_DATA_URL_FORMAT.format(data=image_results[position - FIRST_IMAGE_POSITION].document)


def _https_url(memory_aid: dict[str, Any], name: str) -> str:
    url = _text(memory_aid, name)
    parsed = urlparse(url)
    if parsed.scheme != HTTPS_SCHEME or not parsed.netloc:
        raise MethodFailedError(f"{name} is not an https URL")
    return url


def _describe(error: Exception) -> str:
    """Short error text for logs: type and message, never a stack trace."""
    return f"{type(error).__name__}: {error}"
