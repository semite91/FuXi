"""Embeddings found again by the hash of their text, so a text is embedded once however often it comes back.

Two sources feed it: the live text collection (a rebuild after a change of nothing but the page order, a touched page or a
duplicated text embeds nothing) and a progress collection that every build writes as it goes (a build that stopped
partway, after hours of embedding, starts again without losing them). A vector is used only when the model that made it
is the one configured now: another model gives other vectors, perhaps of another size.
"""

from array import array
from collections.abc import Sequence
from hashlib import sha256
from typing import Any

from chromadb.api import ClientAPI

from chroma_store import (
    PROGRESS_COLLECTION_NAME,
    TEXT_COLLECTION_NAME,
    collection_names,
    delete_collections,
    embedding_identity,
    open_collection,
    set_embedding_identity,
)
from embedders import LEGACY_TEXT_MODEL_ID, Vector

TEXT_ENCODING = "utf-8"
VECTOR_TYPE_CODE = "f"  # 32-bit floats, the precision Chroma stores


def text_hash(text: str) -> str:
    return sha256(text.encode(TEXT_ENCODING)).hexdigest()


def same_embedding(client: ClientAPI, identity: str | None) -> bool:
    """Whether the live text collection holds vectors of the configured model. A collection built before the model was
    recorded holds Qwen3-Embedding's; an embedder that does not say which model it is (None) is never refused."""
    if identity is None:
        return True
    return (embedding_identity(client, TEXT_COLLECTION_NAME) or LEGACY_TEXT_MODEL_ID) == identity


class EmbeddingCache:
    """Vectors by the hash of their text; what is stored is also written to the progress collection."""

    def __init__(self, progress: Any, vectors: dict[str, array] | None = None) -> None:
        self._progress = progress
        self._vectors = vectors or {}

    def has(self, text: str) -> bool:
        return text_hash(text) in self._vectors

    def get(self, text: str) -> Vector:
        return self._vectors[text_hash(text)].tolist()

    def store(self, texts: Sequence[str], vectors: Sequence[Vector]) -> None:
        hashes = [text_hash(text) for text in texts]
        if not hashes:
            return
        self._vectors.update({key: array(VECTOR_TYPE_CODE, vector) for key, vector in zip(hashes, vectors)})
        self._progress.upsert(ids=hashes, embeddings=[list(vector) for vector in vectors])


def open_embedding_cache(client: ClientAPI, identity: str | None) -> tuple[EmbeddingCache, int, int]:
    """The cache with what an interrupted build left and what the live text collection holds; also the number of
    vectors from each."""
    progress = _open_progress(client, identity)
    stored = progress.get(include=["embeddings"])
    vectors = _by_key(stored["ids"], stored["embeddings"])
    from_progress = len(vectors)
    from_live = 0
    if TEXT_COLLECTION_NAME in collection_names(client) and same_embedding(client, identity):
        live = open_collection(client, TEXT_COLLECTION_NAME).get(include=["documents", "embeddings"])
        keys = [text_hash(text) for text in live["documents"]]
        for key, vector in _by_key(keys, live["embeddings"]).items():
            if key not in vectors:
                vectors[key] = vector
                from_live += 1
    return EmbeddingCache(progress, vectors), from_progress, from_live


def _open_progress(client: ClientAPI, identity: str | None) -> Any:
    """The progress collection; one that holds another model's vectors is deleted first."""
    if identity is not None and PROGRESS_COLLECTION_NAME in collection_names(client):
        if embedding_identity(client, PROGRESS_COLLECTION_NAME) != identity:
            delete_collections(client, [PROGRESS_COLLECTION_NAME])
    progress = open_collection(client, PROGRESS_COLLECTION_NAME)
    if identity is not None:
        set_embedding_identity(client, PROGRESS_COLLECTION_NAME, identity)
    return progress


def _by_key(keys: Sequence[str], embeddings: Any) -> dict[str, array]:
    if embeddings is None:
        return {}
    return {key: array(VECTOR_TYPE_CODE, vector) for key, vector in zip(keys, embeddings)}
