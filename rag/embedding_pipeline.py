"""Embedding pipeline: reads every resource, embeds in batches and stores in ChromaDB."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from chromadb.api import ClientAPI

from base import Document, Resource, ResourceKind
from chroma_store import (
    COLLECTION_BY_KIND,
    OLD_COLLECTION_BY_KIND,
    STAGING_COLLECTION_BY_KIND,
    collection_names,
    delete_collections,
    mark_build_complete,
    open_collection,
    rename_collection,
)
from settings import REPO_ROOT

DEFAULT_LOGS_DIR = REPO_ROOT / "logs" / "embedding"
LOG_FILE_NAME_FORMAT = "%Y_%m_%d_%H_%M"
LOG_FILE_SUFFIX = ".txt"
LOG_LINE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_ENCODING = "utf-8"

LIVE_NAMES = list(COLLECTION_BY_KIND.values())
STAGING_NAMES = list(STAGING_COLLECTION_BY_KIND.values())
OLD_NAMES = list(OLD_COLLECTION_BY_KIND.values())

Clock = Callable[[], datetime]
CollectionNames = dict[ResourceKind, str]


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
        """A build counts only when every resource was read and at least one document was stored."""
        return not self.failed_resources and self.added_documents > 0


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
        result = _embed_all(resources, embedders, chroma_client, batch_size, log, STAGING_COLLECTION_BY_KIND)
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
) -> PipelineResult:
    for name in collection_names.values():
        open_collection(chroma_client, name)
    log.write(f"collections ready: {', '.join(collection_names.values())}")
    result = PipelineResult()
    for resource in resources:
        try:
            result.added_documents += _embed_resource(
                resource, embedders, chroma_client, batch_size, log, collection_names[resource.kind]
            )
        except Exception as error:
            result.failed_resources.append(resource.name)
            log.write(f"resource {resource.name} failed: {type(error).__name__}: {error}")
            _log_read_summary(resource, log)
    return result


def _embed_resource(
    resource: Resource,
    embedders: Embedders,
    chroma_client: ClientAPI,
    batch_size: int,
    log: EmbeddingLog,
    collection_name: str,
) -> int:
    log.write(f"resource {resource.name}: reading")
    documents = resource.read_documents()
    log.write(f"resource {resource.name}: {len(documents)} documents read")
    _log_read_summary(resource, log)
    collection = open_collection(chroma_client, collection_name)
    embed = _embed_function(resource.kind, embedders)
    for batch_number, start in enumerate(range(0, len(documents), batch_size), start=1):
        batch = documents[start:start + batch_size]
        _add_batch(collection, batch, embed)
        log.write(f"resource {resource.name}: batch {batch_number} added {len(batch)} documents to {collection_name}")
    return len(documents)


def _log_read_summary(resource: Resource, log: EmbeddingLog) -> None:
    summary = resource.read_summary()
    if summary:
        log.write(f"resource {resource.name}: read summary: {summary}")


def _embed_function(kind: ResourceKind, embedders: Embedders) -> Callable[[list[str]], list[list[float]]]:
    if kind is ResourceKind.IMAGE:
        return embedders.image.embed_images
    return embedders.text.embed_documents


def _add_batch(collection: Any, batch: list[Document], embed: Callable[[list[str]], list[list[float]]]) -> None:
    texts = [document.text for document in batch]
    collection.add(
        ids=[str(uuid4()) for _ in batch],
        documents=texts,
        embeddings=embed(texts),
        metadatas=[document.metadata for document in batch],
    )
