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
COLLECTION_NAMES = (TEXT_COLLECTION_NAME, IMAGE_COLLECTION_NAME)
COLLECTION_BY_KIND = {
    ResourceKind.TEXT: TEXT_COLLECTION_NAME,
    ResourceKind.IMAGE: IMAGE_COLLECTION_NAME,
}
# An update builds into these collections first and renames them only when it succeeded.
STAGING_SUFFIX = "_next"
STAGING_COLLECTION_BY_KIND = {kind: f"{name}{STAGING_SUFFIX}" for kind, name in COLLECTION_BY_KIND.items()}
# fuxi_text carries this metadata only after a build reached its end with documents and no failed resource.
BUILD_MARKER_KEY = "fuxi_build"
BUILD_COMPLETE_VALUE = "complete"
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


def delete_all_collections(client: ClientAPI) -> list[str]:
    return delete_collections_except(client, ())


def delete_collections_except(client: ClientAPI, kept: Names[str]) -> list[str]:
    names = [collection.name for collection in client.list_collections() if collection.name not in kept]
    for name in names:
        client.delete_collection(name)
    return names


def delete_collections(client: ClientAPI, names: Names[str]) -> None:
    for collection in client.list_collections():
        if collection.name in names:
            client.delete_collection(collection.name)


def rename_collection(client: ClientAPI, name: str, new_name: str) -> None:
    open_collection(client, name).modify(name=new_name)


def mark_build_complete(client: ClientAPI) -> None:
    open_collection(client, TEXT_COLLECTION_NAME).modify(metadata={BUILD_MARKER_KEY: BUILD_COMPLETE_VALUE})


def is_build_complete(client: ClientAPI) -> bool:
    """Ready means the last build reached its end; a build that stopped partway has no marker."""
    for collection in client.list_collections():
        if collection.name == TEXT_COLLECTION_NAME:
            return (collection.metadata or {}).get(BUILD_MARKER_KEY) == BUILD_COMPLETE_VALUE
    return False
