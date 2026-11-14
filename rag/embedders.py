"""Text (Qwen3) and image (CLIP) embedders. Models load lazily, once per process, on the CPU."""

import base64
import io
import threading
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from PIL import Image

TEXT_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
IMAGE_MODEL_ID = "sentence-transformers/clip-ViT-B-32"
CPU_DEVICE = "cpu"
QUERY_PROMPT_NAME = "query"
RGB_MODE = "RGB"
# Pillow raises these for data it cannot open (UnidentifiedImageError is an OSError); bad Base64 is a ValueError.
PICTURE_ERRORS = (OSError, ValueError, Image.DecompressionBombError)

Vector = list[float]
ModelLoader = Callable[[str, str], Any]


class PictureDataError(ValueError):
    """A picture document's text is not Base64 picture data."""


class DocumentEmbedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[Vector]: ...


class QueryEmbedder(Protocol):
    def embed_query(self, text: str) -> Vector: ...


class TextQueryEmbedder(Protocol):
    def embed_text(self, text: str) -> Vector: ...


def load_sentence_transformer(model_id: str, device: str) -> Any:
    # Imported here so the engine starts without loading torch.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_id, device=device)


class ModelCache:
    """Loads each model once and shares it between embedders and threads."""

    def __init__(self, loader: ModelLoader = load_sentence_transformer) -> None:
        self._loader = loader
        self._models: dict[str, Any] = {}
        self._lock = threading.Lock()

    def get(self, model_id: str) -> Any:
        with self._lock:
            if model_id not in self._models:
                self._models[model_id] = self._loader(model_id, CPU_DEVICE)
            return self._models[model_id]


DEFAULT_MODEL_CACHE = ModelCache()


class TextEmbedder:
    def __init__(self, model_cache: ModelCache = DEFAULT_MODEL_CACHE) -> None:
        self._model_cache = model_cache

    def embed_query(self, text: str) -> Vector:
        return _encode(self._model_cache.get(TEXT_MODEL_ID), [text], prompt_name=QUERY_PROMPT_NAME)[0]

    def embed_documents(self, texts: list[str]) -> list[Vector]:
        return _encode(self._model_cache.get(TEXT_MODEL_ID), texts)


class ImageEmbedder:
    def __init__(self, model_cache: ModelCache = DEFAULT_MODEL_CACHE) -> None:
        self._model_cache = model_cache

    def embed_text(self, text: str) -> Vector:
        """CLIP text encoder, for searching the image collection."""
        return _encode(self._model_cache.get(IMAGE_MODEL_ID), [text])[0]

    def embed_images(self, images: Sequence[Image.Image]) -> list[Vector]:
        """CLIP image encoder; picture documents are decoded with decode_picture first."""
        return _encode(self._model_cache.get(IMAGE_MODEL_ID), list(images))


def decode_picture(text: str) -> Image.Image:
    """A picture document's Base64 text as an RGB picture."""
    try:
        with Image.open(io.BytesIO(base64.b64decode(text, validate=True))) as picture:
            return picture.convert(RGB_MODE)
    except PICTURE_ERRORS as error:
        raise PictureDataError("the text is not Base64 picture data") from error


def _encode(model: Any, inputs: list[Any], **options: Any) -> list[Vector]:
    return model.encode(inputs, **options).tolist()
