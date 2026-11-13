"""Embedded ChromaDB access: client, collection names and cosine collections.

Embeddings are always precomputed: no Chroma embedding function and no Chroma server.
"""

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
    names = [collection.name for collection in client.list_collections()]
    for name in names:
        client.delete_collection(name)
    return names


def has_data(client: ClientAPI) -> bool:
    existing = {collection.name for collection in client.list_collections()}
    return any(open_collection(client, name).count() > 0 for name in COLLECTION_NAMES if name in existing)
