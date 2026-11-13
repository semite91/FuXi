"""Resource base class and the document model shared by every resource."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum

# Chroma accepts only these metadata value types.
MetadataValue = str | int | float | bool

METADATA_NAME = "name"
METADATA_PATH = "path"
METADATA_TYPE = "type"
METADATA_TIMESTAMP = "timestamp"
TEXT_DOCUMENT_TYPE = "text"


class ResourceKind(StrEnum):
    """Selects the embedder and the collection of a resource's documents."""

    TEXT = "text"
    IMAGE = "image"


@dataclass(frozen=True)
class Document:
    text: str
    metadata: dict[str, MetadataValue] = field(default_factory=dict)


class Resource(ABC):
    """A data source. New sources subclass this; nothing existing changes."""

    name: str
    kind: ResourceKind

    @abstractmethod
    def read_documents(self) -> list[Document]:
        """Read every document of this source."""


@dataclass(frozen=True)
class RetrievedItem:
    """One retrieve result: the stored document, its metadata and its similarity (1 - cosine distance)."""

    document: str
    metadata: dict[str, MetadataValue]
    similarity: float
