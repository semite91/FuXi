"""Notion resource: every page shared with the integration, as text documents."""

import threading
import time
from dataclasses import dataclass
from collections.abc import Callable, Iterator
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from notion_client import APIResponseError, Client
from notion_client.errors import RequestTimeoutError

from base import (
    METADATA_NAME,
    METADATA_PAGE_ID,
    METADATA_PATH,
    METADATA_TIMESTAMP,
    METADATA_TYPE,
    TEXT_DOCUMENT_TYPE,
    Document,
    Resource,
    ResourceKind,
    ResourceSkipped,
)
from resources.parallel import iter_parallel
from resources.http_retry import (
    RATE_LIMITED_STATUS,
    Clock,
    RETRY_AFTER_HEADER,
    TRANSIENT_NETWORK_ERRORS,
    ReadStats,
    Wait,
    backoff_seconds,
    call_with_retry,
    retry_after_seconds,
    timed_read,
)
from embedders import SPECIAL_TOKENS_MARGIN, text_model_spec
from settings import Settings
from settings_store import read_notion_token

RESOURCE_NAME = "notion"
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200
PAGE_SIZE = 100
# A 429 without Retry-After waits this long; a dropped connection or a timeout backs off (http_retry).
DEFAULT_RETRY_AFTER_SECONDS = 1.0
# The shared transient network errors, and the timeout that notion_client raises in place of httpx's.
NETWORK_ERRORS = (*TRANSIENT_NETWORK_ERRORS, RequestTimeoutError)
# A parent page answering with one of these is not shared with the integration; other errors fail the resource.
UNREADABLE_PAGE_STATUSES = frozenset({403, 404})
UNREADABLE_PAGE_CODES = frozenset({"object_not_found", "restricted_resource"})

UNAUTHORIZED_STATUS = 401
TOKEN_REJECTED_MESSAGE = "Notion token rejected: connect Notion again on the Settings page"
NOT_CONNECTED = "not connected"

PAGE_FILTER = {"property": "object", "value": "page"}
TITLE_PROPERTY_TYPE = "title"
PAGE_PARENT_TYPE = "page_id"
# A page that is a row of a database almost never has a body (142 of 143 in a sample), so it is not read.
DATABASE_ROW_PARENT_TYPES = frozenset({"data_source_id", "database_id"})
RICH_TEXT_KEY = "rich_text"
PLAIN_TEXT_KEY = "plain_text"
# Child pages are pages of their own; the search returns them separately.
SKIPPED_CHILD_TYPES = frozenset({"child_page", "child_database"})
TEXT_SEPARATOR = "\n"
PATH_SEPARATOR = " / "

NotionClientFactory = Callable[[], Any]

# Where the read time goes: the page search, the block reading of the pages, the unshared parent lookups.
PHASE_SEARCH = "search"
PHASE_MARKDOWN = "markdown"
PHASE_BLOCKS = "blocks"
PHASE_PARENTS = "parents"
PHASES = (PHASE_SEARCH, PHASE_MARKDOWN, PHASE_BLOCKS, PHASE_PARENTS)
# The one-call page reading is not used for a page when Notion answers with one of these; the blocks are read instead.
MARKDOWN_UNAVAILABLE_STATUSES = frozenset({400, 403, 404})
EMPTY_BLOCK_MARKUP = "<empty-block/>"
SLOWEST_PAGES_SHOWN = 3
# Two chunks do not overlap (an overlap of a tenth of the limit made 10% more tokens to embed).
TOKEN_OVERLAP = 0
# A page whose text is shorter than this says nothing a search could find; it is not embedded.
MIN_PAGE_CHARS = 10
# Pages are read this many at a time by the engine's resource. A shared gate keeps the calls under what Notion allows
# on every plan but Business and Enterprise (3 a second on average) and pauses all of them when one gets a 429.
NOTION_WORKERS = 4
MIN_CALL_INTERVAL_SECONDS = 1 / 3


# None marks a parent page the integration cannot read.
PageCache = dict[str, dict[str, Any] | None]


class NotionTokenRejected(RuntimeError):
    """Notion answered 401: the saved token no longer works."""


@dataclass
class PhaseStats:
    """Calls (retries included) and seconds (waits included) of one phase of the read."""

    calls: int = 0
    seconds: float = 0.0


@dataclass
class PageCost:
    """What one page cost; only the thread that reads the page changes it."""

    title: str
    calls: int = 0
    seconds: float = 0.0


class CallGate:
    """Spaces the starts of the calls of all threads and holds them all back while a 429 asks for a pause."""

    def __init__(self, clock: Clock, sleep: Callable[[float], None], min_interval: float) -> None:
        self._clock = clock
        self._sleep = sleep
        self._min_interval = min_interval
        self._next_start = 0.0
        self._lock = threading.Lock()

    def wait_turn(self) -> None:
        with self._lock:
            now = self._clock()
            start = max(now, self._next_start)
            self._next_start = start + self._min_interval
        if start > now:
            self._sleep(start - now)

    def pause(self, seconds: float) -> None:
        with self._lock:
            self._next_start = max(self._next_start, self._clock() + seconds)


class NotionResource(Resource):
    name = RESOURCE_NAME
    kind = ResourceKind.TEXT
    reuses_stored = True
    streams = True

    def __init__(
        self,
        client_factory: NotionClientFactory,
        sleep: Callable[[float], None] = time.sleep,
        clock: Clock = time.monotonic,
        workers: int = 1,
        token_counter: Callable[[str], int] | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._sleep = sleep
        self._clock = clock
        self._stats = ReadStats()
        self._pages = 0
        self._skipped_pages = 0
        self._reused_pages = 0
        self._near_empty_pages = 0
        self._workers = workers
        self._gate = CallGate(clock, sleep, MIN_CALL_INTERVAL_SECONDS)
        self._lock = threading.Lock()
        self._stored: dict[str, list[Document]] = {}
        self._phases: dict[str, PhaseStats] = {}
        self._page_costs: list[PageCost] = []
        self._token_counter = token_counter
        self._chunk_size = CHUNK_SIZE
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
        )
        if token_counter is not None and max_tokens is not None:
            # Chunks are measured in tokens of the embedding model, so none is longer than the model reads.
            self._chunk_size = max_tokens - SPECIAL_TOKENS_MARGIN
            self._splitter = RecursiveCharacterTextSplitter(
                chunk_size=self._chunk_size,
                chunk_overlap=TOKEN_OVERLAP,
                length_function=token_counter,
            )

    def read_documents(self) -> list[Document]:
        return list(self.stream_documents())

    def stream_documents(self) -> Iterator[Document]:
        """The documents of each page as soon as the page and the pages before it are read."""
        self._pages = 0
        self._skipped_pages = 0
        self._reused_pages = 0
        self._near_empty_pages = 0
        self._phases = {phase: PhaseStats() for phase in PHASES}
        self._page_costs = []
        with timed_read(self._clock) as self._stats:
            try:
                yield from self._stream_documents()
            except APIResponseError as error:
                if error.status == UNAUTHORIZED_STATUS:
                    raise NotionTokenRejected(TOKEN_REJECTED_MESSAGE) from None
                raise
            finally:
                self._stored = {}

    def read_summary(self) -> str:
        phases = [f"{phase} {stats.calls} calls {stats.seconds:.1f} s" for phase, stats in self._phases.items()]
        slowest = sorted(self._page_costs, key=lambda cost: cost.seconds, reverse=True)[:SLOWEST_PAGES_SHOWN]
        slowest_texts = [f"{cost.title!r} {cost.calls} calls {cost.seconds:.1f} s" for cost in slowest]
        return self._stats.summary(
            f"{self._pages} pages",
            f"{self._skipped_pages} database rows skipped without a call",
            f"{self._reused_pages} unchanged pages reused from the stored collection",
            f"{self._near_empty_pages} near-empty pages not embedded",
            f"phases: {'; '.join(phases)}",
            f"slowest pages: {'; '.join(slowest_texts)}",
        )

    def use_stored(self, stored: list[Document]) -> None:
        """Keeps the stored documents of each page, by page id, for the next read."""
        self._stored = {}
        for document in stored:
            page_id = document.metadata.get(METADATA_PAGE_ID)
            if isinstance(page_id, str):
                self._stored.setdefault(page_id, []).append(document)

    def _stream_documents(self) -> Iterator[Document]:
        client = self._client_factory()
        pages = list(self._search_pages(client))
        self._pages = len(pages)
        page_cache: PageCache = {page["id"]: page for page in pages}
        to_read = [page for page in pages if not _is_database_row(page)]
        self._skipped_pages = len(pages) - len(to_read)

        def page_documents(page: dict[str, Any]) -> list[Document]:
            return self._page_documents(client, page, page_cache)

        if self._workers > 1:
            per_page = iter_parallel(page_documents, to_read, self._workers)
        else:
            per_page = (page_documents(page) for page in to_read)
        for documents in per_page:
            yield from documents

    def _page_documents(self, client: Any, page: dict[str, Any], page_cache: PageCache) -> list[Document]:
        unchanged = self._unchanged_documents(page)
        if unchanged is not None:
            with self._lock:
                self._reused_pages += 1
            return unchanged
        cost = PageCost(_page_title(page))
        text = self._read_page_text(client, page, cost)
        with self._lock:
            self._page_costs.append(cost)
        if len(text.strip()) < MIN_PAGE_CHARS:
            if text.strip():
                with self._lock:
                    self._near_empty_pages += 1
            return []
        metadata = self._build_metadata(client, page, page_cache)
        return [Document(chunk, dict(metadata)) for chunk in self._chunk(text)]

    def _unchanged_documents(self, page: dict[str, Any]) -> list[Document] | None:
        """The stored documents of a page that was not edited since they were stored."""
        stored = self._stored.get(page["id"])
        edited = page.get("last_edited_time", "")
        if not stored or not edited or any(d.metadata.get(METADATA_TIMESTAMP) != edited for d in stored):
            return None
        if any(self._length(d.text) > self._chunk_size for d in stored):
            return None  # stored in longer chunks than the embedding model reads: read and cut again
        return [Document(d.text, dict(d.metadata), d.stored_id) for d in stored]

    def _read_page_text(self, client: Any, page: dict[str, Any], cost: PageCost) -> str:
        text = self._read_markdown_text(client, page["id"], cost)
        if text is None:
            text = TEXT_SEPARATOR.join(self._read_block_texts(client, page["id"], cost))
        return text

    def _read_markdown_text(self, client: Any, page_id: str, cost: PageCost) -> str | None:
        """The whole page in one call. None when the page must be read block by block: Notion cut the answer
        (truncated, or blocks it did not open) or does not give this page as markdown."""
        try:
            answer = self._call_with_retry(
                lambda: client.pages.retrieve_markdown(page_id=page_id), PHASE_MARKDOWN, cost
            )
        except APIResponseError as error:
            if error.status in MARKDOWN_UNAVAILABLE_STATUSES:
                return None
            raise
        if answer.get("truncated") or answer.get("unknown_block_ids"):
            return None
        return _clean_markdown(answer.get("markdown", ""))

    def _search_pages(self, client: Any) -> Iterator[dict[str, Any]]:
        for page in self._paginate(lambda cursor: client.search(
            filter=PAGE_FILTER, start_cursor=cursor, page_size=PAGE_SIZE
        ), PHASE_SEARCH):
            if not page.get("in_trash") and not page.get("archived"):
                yield page

    def _read_block_texts(self, client: Any, block_id: str, cost: PageCost) -> Iterator[str]:
        """Plain text of every block, in order, nested children right after their parent."""
        for block in self._paginate(lambda cursor: client.blocks.children.list(
            block_id=block_id, start_cursor=cursor, page_size=PAGE_SIZE
        ), PHASE_BLOCKS, cost):
            text = _block_text(block)
            if text:
                yield text
            if block.get("has_children") and block.get("type") not in SKIPPED_CHILD_TYPES:
                yield from self._read_block_texts(client, block["id"], cost)

    def _paginate(
        self, fetch: Callable[[str | None], dict[str, Any]], phase: str, cost: PageCost | None = None
    ) -> Iterator[dict[str, Any]]:
        cursor: str | None = None
        while True:
            answer = self._call_with_retry(lambda: fetch(cursor), phase, cost)
            yield from answer.get("results", [])
            if not answer.get("has_more"):
                return
            cursor = answer.get("next_cursor")

    def _call_with_retry(
        self, call: Callable[[], dict[str, Any]], phase: str, cost: PageCost | None = None
    ) -> dict[str, Any]:
        """Counted apart for this call, then added: many threads read at once. The seconds of a phase add up the
        seconds of every thread, so with many workers they are more than the read took."""
        own = ReadStats()
        started = self._clock()
        try:
            return call_with_retry(self._paced(call), self._gated_retry_wait, own, self._sleep)
        finally:
            elapsed = self._clock() - started
            self._stats.add(own)
            with self._lock:
                phase_stats = self._phases[phase]
                phase_stats.calls += own.calls
                phase_stats.seconds += elapsed
            if cost is not None:
                cost.calls += own.calls
                cost.seconds += elapsed

    def _paced(self, call: Callable[[], dict[str, Any]]) -> Callable[[], dict[str, Any]]:
        if self._workers <= 1:
            return call

        def paced_call() -> dict[str, Any]:
            self._gate.wait_turn()
            return call()

        return paced_call

    def _gated_retry_wait(self, error: Exception, attempt: int) -> Wait | None:
        """A 429 also holds back the other threads for the same time."""
        wait = _retry_wait(error, attempt)
        if wait is not None and wait.rate_limited and self._workers > 1:
            self._gate.pause(wait.seconds)
        return wait

    def _build_metadata(
        self, client: Any, page: dict[str, Any], page_cache: PageCache
    ) -> dict[str, str]:
        return {
            METADATA_NAME: _page_title(page),
            METADATA_PATH: PATH_SEPARATOR.join(self._parent_titles(client, page, page_cache)),
            METADATA_TYPE: TEXT_DOCUMENT_TYPE,
            METADATA_TIMESTAMP: page.get("last_edited_time", ""),
            METADATA_PAGE_ID: page["id"],
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
                page_cache[parent_id] = self._call_with_retry(lambda: client.pages.retrieve(page_id=parent_id), PHASE_PARENTS)
            except APIResponseError as error:
                if not _is_unreadable_page(error):
                    raise
                page_cache[parent_id] = None
        return page_cache[parent_id]

    def _length(self, text: str) -> int:
        return self._token_counter(text) if self._token_counter is not None else len(text)

    def _chunk(self, text: str) -> list[str]:
        if self._length(text) <= self._chunk_size:
            return [text]
        return self._splitter.split_text(text)


def create_notion_resource(
    settings: Settings,
    read_token: Callable[[Settings], str | None] = read_notion_token,
    make_client: Callable[..., Any] = Client,
    token_counter: Callable[[str], int] | None = None,
) -> NotionResource:
    """The token is read from the Settings table at each read, so a new sign-in needs no restart.

    Without a token the resource is skipped; a database error fails it.
    """

    def client_factory() -> Any:
        token = read_token(settings)
        if not token:
            raise ResourceSkipped(NOT_CONNECTED)
        return make_client(auth=token, retry=False)

    return NotionResource(
        client_factory=client_factory,
        workers=NOTION_WORKERS,
        token_counter=token_counter,
        max_tokens=settings.max_seq_length - text_model_spec(settings.text_model).reserved_tokens,
    )


def _block_text(block: dict[str, Any]) -> str:
    content = block.get(block.get("type", ""), {})
    if not isinstance(content, dict):
        return ""
    return _plain_text(content.get(RICH_TEXT_KEY, []))


def _clean_markdown(markdown: str) -> str:
    """The markdown without the lines that only mark an empty block."""
    lines = (line for line in markdown.splitlines() if line.strip() != EMPTY_BLOCK_MARKUP)
    return TEXT_SEPARATOR.join(lines)


def _is_database_row(page: dict[str, Any]) -> bool:
    """Known from the search answer alone, so an empty page costs no call."""
    return page.get("parent", {}).get("type") in DATABASE_ROW_PARENT_TYPES


def _page_title(page: dict[str, Any]) -> str:
    for page_property in page.get("properties", {}).values():
        if page_property.get("type") == TITLE_PROPERTY_TYPE:
            return _plain_text(page_property.get(TITLE_PROPERTY_TYPE, []))
    return ""


def _plain_text(rich_text: list[dict[str, Any]]) -> str:
    return "".join(item.get(PLAIN_TEXT_KEY, "") for item in rich_text)


def _is_unreadable_page(error: APIResponseError) -> bool:
    return error.status in UNREADABLE_PAGE_STATUSES or error.code in UNREADABLE_PAGE_CODES


def _retry_wait(error: Exception, attempt: int) -> Wait | None:
    """A 429 waits Retry-After; a transient network error waits longer each time; other errors raise."""
    if isinstance(error, APIResponseError) and error.status == RATE_LIMITED_STATUS:
        raw = error.headers.get(RETRY_AFTER_HEADER)
        return Wait(retry_after_seconds(raw, DEFAULT_RETRY_AFTER_SECONDS), rate_limited=True)
    if isinstance(error, NETWORK_ERRORS):
        return Wait(backoff_seconds(attempt), rate_limited=False)
    return None
