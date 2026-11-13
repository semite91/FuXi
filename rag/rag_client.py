"""RAG client: cached collections (singleton), retrieve and generate."""

import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from chromadb.api import ClientAPI

from base import RetrievedItem
from chroma_store import IMAGE_COLLECTION_NAME, TEXT_COLLECTION_NAME, open_collection
from embedding_pipeline import Embedders
from settings import Settings

TOP_K = 20
# Chroma stores float32 vectors; rounding keeps a similarity of exactly the threshold.
SIMILARITY_DECIMALS = 6
QUERY_INCLUDE = ["documents", "metadatas", "distances"]

logger = logging.getLogger(__name__)

ChromaClientFactory = Callable[[], ClientAPI]


@dataclass(frozen=True)
class Collections:
    text: Any
    image: Any


@dataclass(frozen=True)
class Word:
    name: str
    translation: str


@dataclass(frozen=True)
class WordContent:
    name: str
    content: str | None


class RagClient:
    def __init__(
        self,
        chroma_client_factory: ChromaClientFactory,
        embedders: Embedders,
        settings: Settings,
        llm_client: Any,
    ) -> None:
        self._chroma_client_factory = chroma_client_factory
        self._chroma_client: ClientAPI | None = None
        self._embedders = embedders
        self._settings = settings
        self._llm_client = llm_client
        self._collections: Collections | None = None
        self._lock = threading.Lock()

    def init(self) -> Collections:
        """Open both collections once and return the same cached object afterwards."""
        with self._lock:
            if self._collections is None:
                self._collections = self._open_collections()
            return self._collections

    def refresh(self) -> Collections:
        """Point the singleton to the collections that exist now (after an update)."""
        with self._lock:
            self._collections = self._open_collections()
            return self._collections

    def retrieve(self, query: str) -> tuple[list[RetrievedItem], list[RetrievedItem]]:
        collections = self.init()
        texts = _query(collections.text, self._embedders.text.embed_query(query), self._settings.text_threshold)
        images = _query(collections.image, self._embedders.image.embed_text(query), self._settings.image_threshold)
        return texts, images

    def generate(self, words: Sequence[Word]) -> list[WordContent]:
        return [WordContent(word.name, self._generate_word(word)) for word in words]

    def _generate_word(self, word: Word) -> str | None:
        try:
            query = self._llm_client.build_search_query(word.name, word.translation)
            texts, images = self.retrieve(query)
            return self._llm_client.generate(word.name, word.translation, texts, images)
        except Exception as error:
            logger.warning("Content for %s failed: %s: %s", word.name, type(error).__name__, error)
            return None

    def _open_collections(self) -> Collections:
        if self._chroma_client is None:
            self._chroma_client = self._chroma_client_factory()
        return Collections(
            text=open_collection(self._chroma_client, TEXT_COLLECTION_NAME),
            image=open_collection(self._chroma_client, IMAGE_COLLECTION_NAME),
        )


def _query(collection: Any, embedding: list[float], threshold: float) -> list[RetrievedItem]:
    # Chroma returns fewer results, or none, when the collection holds fewer than TOP_K.
    answer = collection.query(query_embeddings=[embedding], n_results=TOP_K, include=QUERY_INCLUDE)
    items = (
        RetrievedItem(document, metadata or {}, round(1 - distance, SIMILARITY_DECIMALS))
        for document, metadata, distance in zip(
            answer["documents"][0], answer["metadatas"][0], answer["distances"][0]
        )
    )
    return [item for item in items if item.similarity >= threshold]
