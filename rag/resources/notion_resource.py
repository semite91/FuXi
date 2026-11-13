"""Notion resource: every page shared with the integration, as text documents."""

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_text_splitters import RecursiveCharacterTextSplitter
from notion_client import APIResponseError, Client
from notion_client.errors import RequestTimeoutError

from base import (
    METADATA_NAME,
    METADATA_PATH,
    METADATA_TIMESTAMP,
    METADATA_TYPE,
    TEXT_DOCUMENT_TYPE,
    Document,
    Resource,
    ResourceKind,
)
from settings import Settings

RESOURCE_NAME = "notion"
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200
PAGE_SIZE = 100
MAX_ATTEMPTS = 5
DEFAULT_RETRY_AFTER_SECONDS = 1.0
MIN_RETRY_AFTER_SECONDS = 0.0
MAX_RETRY_AFTER_SECONDS = 60.0
RATE_LIMITED_STATUS = 429
# A dropped connection or a timeout is tried again after 1, 2, 4 and 8 seconds.
NETWORK_RETRY_SECONDS = 1.0
NETWORK_RETRY_GROWTH = 2
NETWORK_ERRORS = (httpx.TransportError, RequestTimeoutError)
# A parent page answering with one of these is not shared with the integration; other errors fail the resource.
UNREADABLE_PAGE_STATUSES = frozenset({403, 404})
UNREADABLE_PAGE_CODES = frozenset({"object_not_found", "restricted_resource"})
RETRY_AFTER_HEADER = "retry-after"

PAGE_FILTER = {"property": "object", "value": "page"}
TITLE_PROPERTY_TYPE = "title"
PAGE_PARENT_TYPE = "page_id"
RICH_TEXT_KEY = "rich_text"
PLAIN_TEXT_KEY = "plain_text"
# Child pages are pages of their own; the search returns them separately.
SKIPPED_CHILD_TYPES = frozenset({"child_page", "child_database"})
TEXT_SEPARATOR = "\n"
PATH_SEPARATOR = " / "

NotionClientFactory = Callable[[], Any]
# None marks a parent page the integration cannot read.
PageCache = dict[str, dict[str, Any] | None]
# Seconds that only move forward; differences between two readings are measured.
Clock = Callable[[], float]


@dataclass
class ReadStats:
    """What one read cost: Notion calls, waits and time."""

    pages: int = 0
    calls: int = 0
    rate_limit_waits: int = 0
    rate_limit_seconds: float = 0.0
    network_retries: int = 0
    seconds: float = 0.0

    def summary(self) -> str:
        return (
            f"{self.pages} pages, {self.calls} calls, "
            f"{self.rate_limit_waits} rate limit waits ({self.rate_limit_seconds:.1f} s), "
            f"{self.network_retries} network retries, {self.seconds:.1f} s"
        )


class NotionResource(Resource):
    name = RESOURCE_NAME
    kind = ResourceKind.TEXT

    def __init__(
        self,
        client_factory: NotionClientFactory,
        sleep: Callable[[float], None] = time.sleep,
        clock: Clock = time.monotonic,
    ) -> None:
        self._client_factory = client_factory
        self._sleep = sleep
        self._clock = clock
        self._stats = ReadStats()
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
        )

    def read_documents(self) -> list[Document]:
        self._stats = ReadStats()
        started = self._clock()
        try:
            return self._read_documents()
        finally:
            self._stats.seconds = self._clock() - started

    def read_summary(self) -> str:
        return self._stats.summary()

    def _read_documents(self) -> list[Document]:
        client = self._client_factory()
        pages = list(self._search_pages(client))
        self._stats.pages = len(pages)
        page_cache: PageCache = {page["id"]: page for page in pages}
        documents: list[Document] = []
        for page in pages:
            text = TEXT_SEPARATOR.join(self._read_block_texts(client, page["id"]))
            if text.strip():
                metadata = self._build_metadata(client, page, page_cache)
                documents.extend(Document(chunk, dict(metadata)) for chunk in self._chunk(text))
        return documents

    def _search_pages(self, client: Any) -> Iterator[dict[str, Any]]:
        for page in self._paginate(lambda cursor: client.search(
            filter=PAGE_FILTER, start_cursor=cursor, page_size=PAGE_SIZE
        )):
            if not page.get("in_trash") and not page.get("archived"):
                yield page

    def _read_block_texts(self, client: Any, block_id: str) -> Iterator[str]:
        """Plain text of every block, in order, nested children right after their parent."""
        for block in self._paginate(lambda cursor: client.blocks.children.list(
            block_id=block_id, start_cursor=cursor, page_size=PAGE_SIZE
        )):
            text = _block_text(block)
            if text:
                yield text
            if block.get("has_children") and block.get("type") not in SKIPPED_CHILD_TYPES:
                yield from self._read_block_texts(client, block["id"])

    def _paginate(self, fetch: Callable[[str | None], dict[str, Any]]) -> Iterator[dict[str, Any]]:
        cursor: str | None = None
        while True:
            answer = self._call_with_retry(lambda: fetch(cursor))
            yield from answer.get("results", [])
            if not answer.get("has_more"):
                return
            cursor = answer.get("next_cursor")

    def _call_with_retry(self, call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        """On 429 waits Retry-After, on a network error waits longer each time; the last attempt's error is raised."""
        for attempt in range(MAX_ATTEMPTS - 1):
            self._stats.calls += 1
            try:
                return call()
            except APIResponseError as error:
                if error.status != RATE_LIMITED_STATUS:
                    raise
                seconds = _retry_after_seconds(error)
                self._stats.rate_limit_waits += 1
                self._stats.rate_limit_seconds += seconds
            except NETWORK_ERRORS:
                seconds = NETWORK_RETRY_SECONDS * NETWORK_RETRY_GROWTH**attempt
                self._stats.network_retries += 1
            self._sleep(seconds)
        self._stats.calls += 1
        return call()

    def _build_metadata(
        self, client: Any, page: dict[str, Any], page_cache: PageCache
    ) -> dict[str, str]:
        return {
            METADATA_NAME: _page_title(page),
            METADATA_PATH: PATH_SEPARATOR.join(self._parent_titles(client, page, page_cache)),
            METADATA_TYPE: TEXT_DOCUMENT_TYPE,
            METADATA_TIMESTAMP: page.get("last_edited_time", ""),
        }

    def _parent_titles(self, client: Any, page: dict[str, Any], page_cache: PageCache) -> list[str]:
        """Titles of the parent pages, from the top page down; the path stops at the first unreadable parent."""
        titles: list[str] = []
        parent = page.get("parent", {})
        while parent.get("type") == PAGE_PARENT_TYPE:
            parent_page = self._parent_page(client, parent[PAGE_PARENT_TYPE], page_cache)
            if parent_page is None:
                break
            titles.insert(0, _page_title(parent_page))
            parent = parent_page.get("parent", {})
        return titles

    def _parent_page(self, client: Any, parent_id: str, page_cache: PageCache) -> dict[str, Any] | None:
        """The parent page, or None when it is not shared with the integration (403 or 404); other errors raise."""
        if parent_id not in page_cache:
            try:
                page_cache[parent_id] = self._call_with_retry(lambda: client.pages.retrieve(page_id=parent_id))
            except APIResponseError as error:
                if not _is_unreadable_page(error):
                    raise
                page_cache[parent_id] = None
        return page_cache[parent_id]

    def _chunk(self, text: str) -> list[str]:
        if len(text) <= CHUNK_SIZE:
            return [text]
        return self._splitter.split_text(text)


def create_notion_resource(settings: Settings) -> NotionResource:
    """The token is read only when the resource reads, so a missing token fails only then."""
    return NotionResource(
        client_factory=lambda: Client(auth=settings.require_notion_token(), retry=False)
    )


def _block_text(block: dict[str, Any]) -> str:
    content = block.get(block.get("type", ""), {})
    if not isinstance(content, dict):
        return ""
    return _plain_text(content.get(RICH_TEXT_KEY, []))


def _page_title(page: dict[str, Any]) -> str:
    for page_property in page.get("properties", {}).values():
        if page_property.get("type") == TITLE_PROPERTY_TYPE:
            return _plain_text(page_property.get(TITLE_PROPERTY_TYPE, []))
    return ""


def _plain_text(rich_text: list[dict[str, Any]]) -> str:
    return "".join(item.get(PLAIN_TEXT_KEY, "") for item in rich_text)


def _is_unreadable_page(error: APIResponseError) -> bool:
    return error.status in UNREADABLE_PAGE_STATUSES or error.code in UNREADABLE_PAGE_CODES


def _retry_after_seconds(error: APIResponseError) -> float:
    try:
        seconds = float(error.headers.get(RETRY_AFTER_HEADER, DEFAULT_RETRY_AFTER_SECONDS))
    except (TypeError, ValueError):
        seconds = DEFAULT_RETRY_AFTER_SECONDS
    return min(max(seconds, MIN_RETRY_AFTER_SECONDS), MAX_RETRY_AFTER_SECONDS)
