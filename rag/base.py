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
METADATA_MUSICIAN = "musician"
METADATA_ALBUM = "album"
TEXT_DOCUMENT_TYPE = "text"
PICTURE_DOCUMENT_TYPE = "picture"
SONG_DOCUMENT_TYPE = "song"
# A document that has no folder path, such as a movie or a song.
NO_PATH = ""


class ResourceKind(StrEnum):
    """Selects the embedder and the collection of a resource's documents."""

    TEXT = "text"
    IMAGE = "image"


@dataclass(frozen=True)
class Document:
    text: str
    metadata: dict[str, MetadataValue] = field(default_factory=dict)


class ResourceSkipped(Exception):
    """A source that is not set up yet, such as Notion before the Learner connects it.

    The build leaves it out and still counts as complete; the message says why, for the embedding log.
    """


class Resource(ABC):
    """A data source. New sources subclass this; nothing existing changes."""

    name: str
    kind: ResourceKind

    @abstractmethod
    def read_documents(self) -> list[Document]:
        """Read every document of this source."""

    def read_summary(self) -> str:
        """What the last read cost, for the embedding log; empty when the source does not measure it."""
        return ""


@dataclass(frozen=True)
class RetrievedItem:
    """One retrieve result: the stored document, its metadata and its similarity (1 - cosine distance)."""

    document: str
    metadata: dict[str, MetadataValue]
    similarity: float
