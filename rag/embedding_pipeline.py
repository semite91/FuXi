"""Embedding pipeline: reads every resource, embeds in batches and stores in ChromaDB."""

import logging
import queue
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from chromadb.api import ClientAPI

from base import METADATA_NAME, Document, Resource, ResourceKind, ResourceSkipped
from embedding_cache import EmbeddingCache, open_embedding_cache, same_embedding
from chroma_store import (
    is_build_complete,
    COLLECTION_BY_KIND,
    OLD_COLLECTION_BY_KIND,
    STAGING_COLLECTION_BY_KIND,
    collection_names,
    delete_collections,
    mark_build_complete,
    open_collection,
    rename_collection,
    set_embedding_identity,
)
from embedders import PictureDataError, Vector, decode_picture
from settings import REPO_ROOT

logger = logging.getLogger(__name__)

DEFAULT_LOGS_DIR = REPO_ROOT / "logs" / "embedding"
LOG_FILE_NAME_FORMAT = "%Y_%m_%d_%H_%M"
LOG_FILE_SUFFIX = ".txt"
LOG_LINE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_ENCODING = "utf-8"

LIVE_NAMES = list(COLLECTION_BY_KIND.values())
STAGING_NAMES = list(STAGING_COLLECTION_BY_KIND.values())
OLD_NAMES = list(OLD_COLLECTION_BY_KIND.values())

# A streaming resource's documents are embedded in windows of this many batches: the texts of a window are sorted by
# length, and a window is embedded while the next documents are still being read.
WINDOW_BATCHES = 16

Clock = Callable[[], datetime]
CollectionNames = dict[ResourceKind, str]
EmbedFunction = Callable[[list[Document]], list[Vector]]


class Mode(StrEnum):
    CREATE = "create"
    UPDATE = "update"


@dataclass(frozen=True)
class Embedders:
    text: Any  # TextEmbedder-like: embed_documents, embed_query
    image: Any  # ImageEmbedder-like: embed_images, embed_text


@dataclass
class PipelineResult:
    added_documents: int = 0
    failed_resources: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """A build counts when at least one document was stored. A resource that failed is logged and listed in
        failed_resources, and the build goes on with the others."""
        return self.added_documents > 0


class EmbeddingLog:
    """Writes each step as a plain line to logs/embedding/yyyy_MM_dd_HH_mm.txt."""

    def __init__(self, logs_dir: Path, clock: Clock) -> None:
        self._clock = clock
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.path = logs_dir / f"{clock().strftime(LOG_FILE_NAME_FORMAT)}{LOG_FILE_SUFFIX}"

    def write(self, message: str) -> None:
        with self.path.open("a", encoding=LOG_ENCODING) as log_file:
            log_file.write(f"{self._clock().strftime(LOG_LINE_TIME_FORMAT)} {message}\n")


def run(
    mode: Mode | str,
    *,
    resources: Sequence[Resource],
    embedders: Embedders,
    chroma_client: ClientAPI,
    batch_size: int,
    logs_dir: Path = DEFAULT_LOGS_DIR,
    clock: Clock = datetime.now,
) -> PipelineResult:
    """Create and update both build into staging collections; the live ones change only when the build succeeded."""
    run_mode = Mode(mode)
    log = EmbeddingLog(logs_dir, clock)
    log.write(f"start mode={run_mode}")
    try:
        result = _build(run_mode, resources, embedders, chroma_client, batch_size, log)
    except Exception as error:
        log.write(f"run failed: {type(error).__name__}: {error}")
        logger.error("Embedding %s failed: %s: %s", run_mode, type(error).__name__, error)
        raise
    log.write(
        f"end: {result.added_documents} documents, failed resources: {result.failed_resources}, "
        f"complete: {result.complete}"
    )
    return result


def _build(
    mode: Mode,
    resources: Sequence[Resource],
    embedders: Embedders,
    chroma_client: ClientAPI,
    batch_size: int,
    log: EmbeddingLog,
) -> PipelineResult:
    _clean_leftovers(chroma_client, log)
    try:
        identity = getattr(embedders.text, "identity", None)
        reuse_stored = mode is Mode.UPDATE and is_build_complete(chroma_client)
        if reuse_stored and not same_embedding(chroma_client, identity):
            reuse_stored = False
            log.write(f"the text model is now {identity}: every text vector is built again")
        result = _embed_all(
            resources, embedders, chroma_client, batch_size, log, STAGING_COLLECTION_BY_KIND, reuse_stored, identity
        )
    except Exception:
        delete_collections(chroma_client, STAGING_NAMES)
        raise
    if not result.complete:
        delete_collections(chroma_client, STAGING_NAMES)
        log.write(f"{mode} failed, the old collections are kept")
        return result
    _swap(chroma_client, log)
    return result


def _clean_leftovers(chroma_client: ClientAPI, log: EmbeddingLog) -> None:
    """Removes what an interrupted build left; an old collection whose live one is missing is put back."""
    existing = collection_names(chroma_client)
    for kind, old_name in OLD_COLLECTION_BY_KIND.items():
        if old_name in existing and COLLECTION_BY_KIND[kind] not in existing:
            rename_collection(chroma_client, old_name, COLLECTION_BY_KIND[kind])
            log.write(f"restored {COLLECTION_BY_KIND[kind]} from {old_name}")
    deleted = delete_collections(chroma_client, STAGING_NAMES + OLD_NAMES)
    if deleted:
        log.write(f"deleted leftover collections: {deleted}")


def _swap(chroma_client: ClientAPI, log: EmbeddingLog) -> None:
    """Live to *_old, staging to live, marker, then *_old and any other collection are deleted."""
    existing = collection_names(chroma_client)
    moved: list[ResourceKind] = []
    try:
        for kind, name in COLLECTION_BY_KIND.items():
            if name in existing:
                rename_collection(chroma_client, name, OLD_COLLECTION_BY_KIND[kind])
                moved.append(kind)
        for kind, name in COLLECTION_BY_KIND.items():
            rename_collection(chroma_client, STAGING_COLLECTION_BY_KIND[kind], name)
        _mark_complete(chroma_client, log)
    except Exception:
        _restore(chroma_client, existing, moved)
        log.write("swap failed, the old collections are restored")
        raise
    log.write(f"collections replaced: {', '.join(LIVE_NAMES)}")
    log.write(f"deleted collections: {delete_collections(chroma_client, kept=LIVE_NAMES)}")


def _restore(chroma_client: ClientAPI, existing: set[str], moved: list[ResourceKind]) -> None:
    """Deletes the new live collections, renames *_old back and deletes the staging ones."""
    replaced = [
        name for kind, name in COLLECTION_BY_KIND.items() if kind in moved or name not in existing
    ]
    delete_collections(chroma_client, replaced)
    for kind in moved:
        rename_collection(chroma_client, OLD_COLLECTION_BY_KIND[kind], COLLECTION_BY_KIND[kind])
    delete_collections(chroma_client, STAGING_NAMES)


def _mark_complete(chroma_client: ClientAPI, log: EmbeddingLog) -> None:
    mark_build_complete(chroma_client)
    log.write("build marked complete")


def _embed_all(
    resources: Sequence[Resource],
    embedders: Embedders,
    chroma_client: ClientAPI,
    batch_size: int,
    log: EmbeddingLog,
    collection_names: CollectionNames,
    reuse_stored: bool = False,
    identity: str | None = None,
) -> PipelineResult:
    for name in collection_names.values():
        open_collection(chroma_client, name)
    if identity is not None:
        set_embedding_identity(chroma_client, collection_names[ResourceKind.TEXT], identity)
    log.write(f"collections ready: {', '.join(collection_names.values())}")
    cache, from_progress, from_live = open_embedding_cache(chroma_client, identity)
    log.write(
        f"embedding cache: {from_progress} vectors from an interrupted build, {from_live} from the live collection"
    )
    result = PipelineResult()
    for resource in resources:
        try:
            result.added_documents += _embed_resource(
                resource, embedders, chroma_client, batch_size, log, collection_names[resource.kind], reuse_stored,
                cache,
            )
        except ResourceSkipped as skipped:
            log.write(f"resource {resource.name}: {skipped}, skipped")
        except Exception as error:
            result.failed_resources.append(resource.name)
            log.write(f"resource {resource.name} failed: {type(error).__name__}: {error}")
            logger.error("Resource %s failed: %s: %s", resource.name, type(error).__name__, error)
            _log_read_summary(resource, log)
    return result


@dataclass
class StepStats:
    """Seconds spent reading, embedding and storing one resource's documents, and the size of what was read.

    A streaming resource is read by its own thread, so its read seconds overlap the embedding seconds."""

    read_seconds: float = 0.0
    embed_seconds: float = 0.0
    store_seconds: float = 0.0
    documents: int = 0
    bytes: int = 0

    def add_documents(self, documents: Sequence[Document]) -> None:
        self.documents += len(documents)
        self.bytes += sum(len(document.text.encode(LOG_ENCODING)) for document in documents)

    def describe(self) -> str:
        return (
            f"steps: read {self.read_seconds:.2f}s, embed {self.embed_seconds:.2f}s, store {self.store_seconds:.2f}s; "
            f"{self.documents} documents, {self.bytes} bytes"
        )


def _embed_resource(
    resource: Resource,
    embedders: Embedders,
    chroma_client: ClientAPI,
    batch_size: int,
    log: EmbeddingLog,
    collection_name: str,
    reuse_stored: bool = False,
    cache: EmbeddingCache | None = None,
) -> int:
    stored_collection = _give_stored_documents(resource, chroma_client, log) if reuse_stored else None
    log.write(f"resource {resource.name}: reading")
    collection = open_collection(chroma_client, collection_name)
    embed = _embed_function(resource.kind, embedders)
    text_cache = cache if resource.kind is ResourceKind.TEXT else None  # pictures are not hashed
    stats = StepStats()
    if resource.streams:
        windows = _windows(_read_in_background(resource, stats), batch_size * WINDOW_BATCHES)
    else:
        started = time.perf_counter()
        documents = resource.read_documents()
        stats.read_seconds = time.perf_counter() - started
        _log_read(resource, len(documents), log)
        windows = [documents]
    count = 0
    batch_number = 0
    for window in windows:
        count += len(window)
        stats.add_documents(window)
        ordered = _in_embedding_order(window, text_cache)
        for start in range(0, len(ordered), batch_size):
            batch = ordered[start:start + batch_size]
            _add_batch(collection, batch, embed, stored_collection, text_cache, stats)
            batch_number += 1
            log.write(f"resource {resource.name}: batch {batch_number} added {len(batch)} documents to {collection_name}")
    if resource.streams:
        _log_read(resource, count, log)
    log.write(f"resource {resource.name}: {stats.describe()}")
    return count


def _log_read(resource: Resource, count: int, log: EmbeddingLog) -> None:
    log.write(f"resource {resource.name}: {count} documents read")
    _log_read_summary(resource, log)


class _ReadFailed:
    def __init__(self, error: BaseException) -> None:
        self.error = error


_END = object()


def _read_in_background(resource: Resource, stats: StepStats) -> Iterator[Document]:
    """The documents of a streaming resource, read by a thread of their own so the embedding of the first ones runs
    while the rest are read. A failed read raises here, after the documents read before it; when the caller stops
    early, the read is stopped and awaited, so nothing of it runs on."""
    found: queue.Queue[Any] = queue.Queue()
    stop = threading.Event()

    def read() -> None:
        stream = resource.stream_documents()
        try:
            while not stop.is_set():
                started = time.perf_counter()
                document = next(stream, _END)
                stats.read_seconds += time.perf_counter() - started
                if document is _END:
                    break
                found.put(document)
        except BaseException as error:  # handed to the caller, which raises it
            found.put(_ReadFailed(error))
        finally:
            stream.close()
            found.put(_END)

    reader = threading.Thread(target=read, name=f"read-{resource.name}", daemon=True)
    reader.start()
    try:
        while (item := found.get()) is not _END:
            if isinstance(item, _ReadFailed):
                raise item.error
            yield item
    finally:
        stop.set()
        reader.join()


def _windows(documents: Iterable[Document], size: int) -> Iterator[list[Document]]:
    window: list[Document] = []
    for document in documents:
        window.append(document)
        if len(window) >= size:
            yield window
            window = []
    if window:
        yield window


def _in_embedding_order(documents: list[Document], cache: EmbeddingCache | None) -> list[Document]:
    """The documents that need no embedding first, then the others longest first: a forward pass pads every text to the
    longest of its batch, so batches of texts of nearly one length waste the least."""
    if cache is None:
        return documents
    ready = [d for d in documents if d.stored_id is not None or cache.has(d.text)]
    fresh = [d for d in documents if d.stored_id is None and not cache.has(d.text)]
    return ready + sorted(fresh, key=lambda document: len(document.text), reverse=True)


def _give_stored_documents(resource: Resource, chroma_client: ClientAPI, log: EmbeddingLog) -> Any:
    """An update lets a resource that can tell what did not change reuse the live collection's documents; returns
    that collection (where the kept embeddings are read), or None when nothing is reused."""
    live_name = COLLECTION_BY_KIND[resource.kind]
    if not resource.reuses_stored or live_name not in collection_names(chroma_client):
        return None
    live = open_collection(chroma_client, live_name)
    stored = live.get(include=["documents", "metadatas"])
    resource.use_stored([
        Document(text, dict(metadata or {}), stored_id=stored_id)
        for stored_id, text, metadata in zip(stored["ids"], stored["documents"], stored["metadatas"])
    ])
    log.write(f"resource {resource.name}: {len(stored['ids'])} stored documents offered for reuse")
    return live


def _log_read_summary(resource: Resource, log: EmbeddingLog) -> None:
    summary = resource.read_summary()
    if summary:
        log.write(f"resource {resource.name}: read summary: {summary}")


def _embed_function(kind: ResourceKind, embedders: Embedders) -> EmbedFunction:
    if kind is ResourceKind.IMAGE:
        return lambda batch: embedders.image.embed_images([_picture(document) for document in batch])
    return lambda batch: embedders.text.embed_documents([document.text for document in batch])


def _picture(document: Document) -> Any:
    """The decoded picture; invalid data fails the batch with an error naming the document."""
    try:
        return decode_picture(document.text)
    except PictureDataError as error:
        name = document.metadata.get(METADATA_NAME, "")
        raise PictureDataError(f"document {name!r} is not Base64 picture data") from error


def _add_batch(
    collection: Any,
    batch: list[Document],
    embed: EmbedFunction,
    stored_collection: Any = None,
    cache: EmbeddingCache | None = None,
    stats: StepStats | None = None,
) -> None:
    """Documents with a stored_id keep it and their stored embedding; the others get a new id and are embedded, unless
    the cache holds a vector for the same text."""
    stats = stats or StepStats()
    to_embed = [document for document in batch if document.stored_id is None]
    started = time.perf_counter()
    fresh_vectors = iter(_embed_new(to_embed, embed, cache))
    stats.embed_seconds += time.perf_counter() - started
    kept = _stored_embeddings(stored_collection, [d.stored_id for d in batch if d.stored_id is not None])
    started = time.perf_counter()
    collection.add(
        ids=[document.stored_id or str(uuid4()) for document in batch],
        documents=[document.text for document in batch],
        embeddings=[kept[d.stored_id] if d.stored_id is not None else next(fresh_vectors) for d in batch],
        metadatas=[document.metadata for document in batch],
    )
    stats.store_seconds += time.perf_counter() - started


def _embed_new(documents: list[Document], embed: EmbedFunction, cache: EmbeddingCache | None) -> list[Vector]:
    """A vector for each document; with a cache, a text is embedded once and its vector is saved at once."""
    if not documents:
        return []
    if cache is None:
        return embed(documents)
    missing = {document.text: document for document in documents if not cache.has(document.text)}
    if missing:
        cache.store(list(missing), embed(list(missing.values())))
    return [cache.get(document.text) for document in documents]


def _stored_embeddings(stored_collection: Any, ids: list[str]) -> dict[str, Vector]:
    if not ids:
        return {}
    stored = stored_collection.get(ids=ids, include=["embeddings"])
    return {
        stored_id: [float(value) for value in vector]
        for stored_id, vector in zip(stored["ids"], stored["embeddings"])
    }
