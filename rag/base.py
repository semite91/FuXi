"""Resource base class and the document model shared by every resource."""

from abc import ABC, abstractmethod
from collections.abc import Iterator
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
METADATA_PAGE_ID = "page_id"
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
    # Set when the document is a stored one that did not change: the pipeline keeps its id and embedding.
    stored_id: str | None = None


class ResourceSkipped(Exception):
    """A source that is not set up yet, such as Notion before the Learner connects it.

    The build leaves it out and still counts as complete; the message says why, for the embedding log.
    """


class Resource(ABC):
    """A data source. New sources subclass this; nothing existing changes."""

    name: str
    kind: ResourceKind
    # True when the source can tell which of its documents did not change since the last build (see use_stored).
    reuses_stored = False
    # True when stream_documents gives documents while it is still reading, so the pipeline embeds the first ones
    # during the rest of the read.
    streams = False

    @abstractmethod
    def read_documents(self) -> list[Document]:
        """Read every document of this source."""

    def stream_documents(self) -> Iterator[Document]:
        """The documents one by one as they are read; a source with streams overrides it, and read_documents is then
        the list of what it gives."""
        yield from self.read_documents()

    def use_stored(self, stored: list[Document]) -> None:
        """The documents the live collection holds (their stored_id set), given before an update reads; a source with
        reuses_stored returns the ones that did not change from read_documents, so they are not read or embedded again."""

    def read_summary(self) -> str:
        """What the last read cost, for the embedding log; empty when the source does not measure it."""
        return ""


@dataclass(frozen=True)
class RetrievedItem:
    """One retrieve result: the stored document, its metadata and its similarity (1 - cosine distance)."""

    document: str
    metadata: dict[str, MetadataValue]
    similarity: float
