"""Gemini calls: the retrieval search queries and the Word Content for one word."""

import json
import logging
import random
import re
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from google import genai
from google.genai import errors, types

from base import METADATA_NAME, METADATA_PATH, RetrievedItem
from resources.http_retry import MIN_SERVER_ERROR_STATUS, RATE_LIMITED_STATUS, ReadStats, Wait, backoff_seconds, call_with_retry
from settings import REPO_ROOT, Settings
from web_finders import OpenverseImageFinder, SpotifySongFinder

PROMPTS_DIR = REPO_ROOT / "prompts"
RETRIEVAL_PROMPT_FILE = "retrieval.txt"
TEXT_PROMPT_FILE = "llm.txt"
SUGGEST_PROMPT_FILE = "llm_suggest.txt"
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
# Drive images are sent to Gemini with the image_url "drive:<n>", n being the image's 1-based place in the results.
DRIVE_IMAGE_URL_FORMAT = "drive:{position}"
DRIVE_IMAGE_URL_PATTERN = re.compile(r"drive:(\d+)")
FIRST_IMAGE_POSITION = 1
JPEG_DATA_URL_FORMAT = "data:image/jpeg;base64,{data}"
QUERY_FALLBACK_FORMAT = "{word}: {meaning}"
CODE_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
METHOD_SEPARATOR_PATTERN = re.compile(r"[\s_\-]+")

TEXT_FIELDS = ("title", "content")
SOURCE_REFERENCE_FIELD = "source_reference"
TARGET_METHOD_FIELD = "target_method"
QUERIES_FIELD = "queries"
QUERY_FIELD = "query"
MAX_QUERIES = 4
IMAGE_URL_FIELD = "image_url"
SONG_URL_FIELD = "song_url"
IMAGE_QUERY_FIELD = "image_query"
SONG_TITLE_FIELD = "song_title"
ARTIST_FIELD = "artist"

logger = logging.getLogger(__name__)

GeminiClientFactory = Callable[[], Any]
RetrievedResults = tuple[Sequence[RetrievedItem], Sequence[RetrievedItem]]
RetrieveForMethod = Callable[[str], RetrievedResults]
CLOSED_CLIENT_MESSAGE = "client has been closed"


def gemini_retry_wait(error: Exception, attempt: int) -> Wait | None:
    """Gemini answers 429 (quota) and 5xx (503 high demand) for a moment only: wait, backing off, and ask again."""
    if isinstance(error, errors.APIError) and (error.code == RATE_LIMITED_STATUS or error.code >= MIN_SERVER_ERROR_STATUS):
        return Wait(backoff_seconds(attempt), rate_limited=error.code == RATE_LIMITED_STATUS)
    if _is_closed_client(error):
        return Wait(backoff_seconds(attempt), rate_limited=False)
    return None


def _is_closed_client(error: Exception) -> bool:
    """httpx raises this RuntimeError for every call on a client that was closed."""
    return isinstance(error, RuntimeError) and CLOSED_CLIENT_MESSAGE in str(error)


class MethodFailedError(Exception):
    """Gemini's answer cannot be used as Word Content."""


class LlmClient:
    def __init__(
        self,
        settings: Settings,
        gemini_client_factory: GeminiClientFactory | None = None,
        random_source: Any = None,
        prompts_dir: Path = PROMPTS_DIR,
        sleep: Callable[[float], None] = time.sleep,
        song_finder: Any = None,
        image_finder: Any = None,
    ) -> None:
        self._sleep = sleep
        self._song_finder = song_finder or SpotifySongFinder(settings)
        self._image_finder = image_finder or OpenverseImageFinder()
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

    def build_search_queries(self, word: str, meaning: str, method: str | None = None) -> list[str]:
        """Several search queries for the word; with a method they look for material that suits it. One fallback query when Gemini's answer is unusable."""
        fallback = [QUERY_FALLBACK_FORMAT.format(word=word, meaning=meaning)]
        payload = {"word": word, "meaning": meaning}
        if method is not None:
            payload[TARGET_METHOD_FIELD] = method
        try:
            answer = self._ask(RETRIEVAL_PROMPT_FILE, payload)
        except Exception as error:
            logger.warning("Search queries for %s failed: %s", word, _describe(error))
            return fallback
        return _queries(answer) or fallback

    def generate(
        self,
        word: str,
        meaning: str,
        text_results: Sequence[RetrievedItem],
        image_results: Sequence[RetrievedItem],
        retrieve_for_method: RetrieveForMethod | None = None,
    ) -> str | None:
        """Word Content as a compact JSON string, or None when two methods fail.

        The first method uses the given results. The retry asks retrieve_for_method for results that suit its own method."""
        remaining = list(METHODS)
        for attempt in range(MAX_METHOD_ATTEMPTS):
            method = self._random.choice(remaining)
            remaining.remove(method)
            try:
                if attempt > 0 and retrieve_for_method is not None:
                    text_results, image_results = retrieve_for_method(method)
                context = _build_context(text_results, image_results)
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
        payload = {"word": word, "meaning": meaning, "available_methods": [method], "retrieved_context": context}
        answer = self._ask(SUGGEST_PROMPT_FILE if method in WEB_METHODS else TEXT_PROMPT_FILE, payload)
        memory_aid = _checked_memory_aid(method, answer)
        if method == PHOTO:
            return {"method": method, IMAGE_URL_FIELD: self._photo_url(memory_aid, image_results)}
        if method == MUSIC:
            return self._music_content(memory_aid)
        return _text_content(method, memory_aid)

    def _photo_url(self, memory_aid: dict[str, Any], image_results: Sequence[RetrievedItem]) -> str:
        """The Learner's own Drive image when Gemini chose one; otherwise the first web image found for its phrase."""
        reference = memory_aid.get(IMAGE_URL_FIELD)
        if isinstance(reference, str) and DRIVE_IMAGE_URL_PATTERN.fullmatch(reference.strip()):
            return _drive_image(reference.strip(), image_results)
        url = self._image_finder.find_image(_text(memory_aid, IMAGE_QUERY_FIELD))
        if url is None:
            raise MethodFailedError("no web image was found")
        return url

    def _music_content(self, memory_aid: dict[str, Any]) -> dict[str, Any]:
        """A song Gemini named, as Spotify has it; the lyrics are never quoted."""
        song = self._song_finder.find_song(_text(memory_aid, SONG_TITLE_FIELD), _text(memory_aid, ARTIST_FIELD))
        if song is None:
            raise MethodFailedError("the song was not found on Spotify")
        return {
            "method": MUSIC,
            "song_title": song.title,
            "artist": song.artist,
            SONG_URL_FIELD: song.url,
            "lyrics_excerpt": None,
        }

    def _ask(self, prompt_file: str, payload: dict[str, Any]) -> dict[str, Any]:
        config = self._config(prompt_file)
        contents = json.dumps(payload, ensure_ascii=False)
        response = call_with_retry(
            lambda: self._generate_content(contents, config),
            gemini_retry_wait,
            ReadStats(),
            self._sleep,
        )
        return _parse_json_object(response.text)

    def _generate_content(self, contents: str, config: types.GenerateContentConfig) -> Any:
        """A closed client is dropped, so the retry of this call builds a new one."""
        try:
            return self.gemini_client().models.generate_content(
                model=self._settings.gemini_model, contents=contents, config=config
            )
        except RuntimeError as error:
            if _is_closed_client(error):
                logger.warning("The Gemini client was closed; a new one is made for the next try")
                self._gemini_client = None
            raise

    def _config(self, prompt_file: str) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=self.prompt(prompt_file), response_mime_type=JSON_MIME_TYPE
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


def _queries(answer: dict[str, Any]) -> list[str]:
    """The distinct, non-empty queries of Gemini's answer; a single "query" text is accepted too."""
    raw = answer.get(QUERIES_FIELD, answer.get(QUERY_FIELD))
    candidates = [raw] if isinstance(raw, str) else raw if isinstance(raw, list) else []
    cleaned = [item.strip() for item in candidates if isinstance(item, str) and item.strip()]
    return list(dict.fromkeys(cleaned))[:MAX_QUERIES]


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


def _checked_memory_aid(method: str, answer: dict[str, Any]) -> dict[str, Any]:
    if answer.get("status") != SUCCESS_STATUS:
        raise MethodFailedError(f"status {answer.get('status')}")
    if _normalize_method(answer.get("method")) != _normalize_method(method):
        raise MethodFailedError(f"returned method {answer.get('method')}")
    memory_aid = answer.get("memory_aid")
    if not isinstance(memory_aid, dict):
        raise MethodFailedError("memory_aid is missing")
    return memory_aid


def _text_content(method: str, memory_aid: dict[str, Any]) -> dict[str, Any]:
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


def _drive_image(reference: str, image_results: Sequence[RetrievedItem]) -> str:
    """A "drive:<n>" reference becomes that sent image's JPEG data URL."""
    match = DRIVE_IMAGE_URL_PATTERN.fullmatch(reference)
    position = int(match.group(1)) if match else 0
    if not FIRST_IMAGE_POSITION <= position <= len(image_results):
        raise MethodFailedError(f"{IMAGE_URL_FIELD} refers to an image that was not sent")
    return JPEG_DATA_URL_FORMAT.format(data=image_results[position - FIRST_IMAGE_POSITION].document)


def _describe(error: Exception) -> str:
    """Short error text for logs: type and message, never a stack trace."""
    return f"{type(error).__name__}: {error}"
