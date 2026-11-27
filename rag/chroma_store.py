"""Embedded ChromaDB access: client, collection names and cosine collections.

Embeddings are always precomputed: no Chroma embedding function and no Chroma server.
"""

from collections.abc import Collection as Names
from pathlib import Path

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings as ChromaSettings

from base import ResourceKind

DEFAULT_CHROMA_PATH = Path(__file__).resolve().parent / "chroma_data"
TEXT_COLLECTION_NAME = "fuxi_text"
IMAGE_COLLECTION_NAME = "fuxi_image"
COLLECTION_BY_KIND = {
    ResourceKind.TEXT: TEXT_COLLECTION_NAME,
    ResourceKind.IMAGE: IMAGE_COLLECTION_NAME,
}
# A build writes into these collections first; the live ones are replaced only when it succeeded.
STAGING_SUFFIX = "_next"
STAGING_COLLECTION_BY_KIND = {kind: f"{name}{STAGING_SUFFIX}" for kind, name in COLLECTION_BY_KIND.items()}
# During the swap the live collections are kept under these names until the new ones are in place.
OLD_SUFFIX = "_old"
OLD_COLLECTION_BY_KIND = {kind: f"{name}{OLD_SUFFIX}" for kind, name in COLLECTION_BY_KIND.items()}
# fuxi_text carries this metadata only after a build reached its end with documents and no failed resource.
BUILD_MARKER_KEY = "fuxi_build"
BUILD_COMPLETE_VALUE = "complete"
# A collection carries the model that made its vectors (EmbeddingCache and the update check read it).
EMBEDDING_KEY = "fuxi_embedding"
# Vectors of a build in progress, by the hash of their text; a successful swap deletes it with the other leftovers.
PROGRESS_COLLECTION_NAME = "fuxi_progress"
COSINE_SPACE = "cosine"
COLLECTION_CONFIGURATION = {"hnsw": {"space": COSINE_SPACE}}


def create_chroma_client(path: Path = DEFAULT_CHROMA_PATH) -> ClientAPI:
    return chromadb.PersistentClient(
        path=str(path), settings=ChromaSettings(anonymized_telemetry=False)
    )


def open_collection(client: ClientAPI, name: str) -> Collection:
    """Open the collection, creating it with cosine distance when missing."""
    return client.get_or_create_collection(
        name, configuration=COLLECTION_CONFIGURATION, embedding_function=None
    )


def collection_names(client: ClientAPI) -> set[str]:
    return {collection.name for collection in client.list_collections()}


def delete_collections(
    client: ClientAPI, names: Names[str] | None = None, *, kept: Names[str] = ()
) -> list[str]:
    """Deletes the named collections that exist (every collection when names is None) except kept; sorted names."""
    deleted = sorted(
        name for name in collection_names(client) if (names is None or name in names) and name not in kept
    )
    for name in deleted:
        client.delete_collection(name)
    return deleted


def rename_collection(client: ClientAPI, name: str, new_name: str) -> None:
    open_collection(client, name).modify(name=new_name)


def _add_metadata(collection: Collection, items: dict[str, str]) -> None:
    collection.modify(metadata={**(collection.metadata or {}), **items})


def mark_build_complete(client: ClientAPI) -> None:
    _add_metadata(open_collection(client, TEXT_COLLECTION_NAME), {BUILD_MARKER_KEY: BUILD_COMPLETE_VALUE})


def set_embedding_identity(client: ClientAPI, name: str, identity: str) -> None:
    _add_metadata(open_collection(client, name), {EMBEDDING_KEY: identity})


def embedding_identity(client: ClientAPI, name: str) -> str | None:
    """The model that made the vectors of the collection, or None when it was not recorded."""
    for collection in client.list_collections():
        if collection.name == name:
            return (collection.metadata or {}).get(EMBEDDING_KEY)
    return None


def is_build_complete(client: ClientAPI) -> bool:
    """Ready means the last build reached its end; a build that stopped partway has no marker."""
    for collection in client.list_collections():
        if collection.name == TEXT_COLLECTION_NAME:
            return (collection.metadata or {}).get(BUILD_MARKER_KEY) == BUILD_COMPLETE_VALUE
    return False
