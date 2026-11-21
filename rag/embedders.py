"""Text (multilingual-e5-small) and image (CLIP) embedders. Models load lazily, once per process.

The device and precision come from EmbeddingSettings: CUDA is used only when torch can really run on the GPU,
the weights are loaded in the configured precision (FP32 by default) and the loaded dtype is verified.
"""

import base64
import hashlib
import io
import logging
import threading
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from PIL import Image

from settings import (
    DEVICE_AUTO,
    DEVICE_CPU,
    DEVICE_CUDA,
    PRECISION_BF16,
    PRECISION_FP16,
    PRECISION_FP32,
    EmbeddingSettings,
)

logger = logging.getLogger(__name__)

TEXT_MODEL_ID = "intfloat/multilingual-e5-small"
# 384 dimensions, 12 layers, 512 tokens. E5 was trained with these prefixes; without them quality drops.
QUERY_PREFIX = "query: "
DOCUMENT_PREFIX = "passage: "
TEXT_VECTOR_SIZE = 384
IMAGE_MODEL_ID = "sentence-transformers/clip-ViT-B-32"
CPU_DEVICE = DEVICE_CPU
# Token windows of a long text overlap by this share of the window, so a sentence cut at a border is in both.
CHUNK_OVERLAP_SHARE = 0.1
RGB_MODE = "RGB"
# Pillow raises these for data it cannot open (UnidentifiedImageError is an OSError); bad Base64 is a ValueError.
PICTURE_ERRORS = (OSError, ValueError, Image.DecompressionBombError)

Vector = list[float]
# (model id, device, precision, max sequence length or None for the model's own) -> loaded model
ModelLoader = Callable[[str, str, str, int | None], Any]


class PictureDataError(ValueError):
    """A picture document's text is not Base64 picture data."""


class DocumentEmbedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[Vector]: ...


class QueryEmbedder(Protocol):
    def embed_query(self, text: str) -> Vector: ...


class TextQueryEmbedder(Protocol):
    def embed_text(self, text: str) -> Vector: ...


def cuda_usable(torch: Any) -> bool:
    """True only when torch has CUDA, was built for this GPU's architecture and can run an operation on it.

    An installed NVIDIA driver alone proves nothing: a CPU-only torch build or a build without kernels for a
    new GPU reports CUDA as missing or fails on the first kernel.
    """
    try:
        if not torch.cuda.is_available():
            return False
        major, minor = torch.cuda.get_device_capability(0)
        if not _arch_supported(torch.cuda.get_arch_list(), major * 10 + minor):
            return False
        torch.zeros(1, device=DEVICE_CUDA).add_(1).item()  # a real kernel launch
        return True
    except Exception:  # an old driver, a broken runtime or a missing kernel image: use the CPU
        return False


def _arch_supported(arch_list: Sequence[str], capability: int) -> bool:
    """Binary kernels run on the same major generation with an equal or newer minor; PTX runs on any newer GPU."""
    for arch in arch_list:
        kind, _, number = arch.partition("_")
        digits = "".join(character for character in number if character.isdigit())
        if not digits:
            continue
        value = int(digits)
        if kind == "sm" and value // 10 == capability // 10 and value <= capability:
            return True
        if kind == "compute" and value <= capability:
            return True
    return False


def resolve_device(requested: str, torch: Any) -> str:
    """The device to load on: the requested one when usable, otherwise the CPU (with a warning for cuda)."""
    if requested == DEVICE_CPU:
        return DEVICE_CPU
    if cuda_usable(torch):
        return DEVICE_CUDA
    if requested == DEVICE_CUDA:
        logger.warning("RAG_EMBEDDING_DEVICE=cuda but CUDA is not usable with this torch and GPU; using the CPU")
    return DEVICE_CPU


def resolve_precision(requested: str, device: str) -> str:
    """The precision to load in; FP16 is not run on the CPU, where it is slow or unsupported."""
    if requested == PRECISION_FP16 and device == DEVICE_CPU:
        logger.warning("RAG_EMBEDDING_PRECISION=fp16 is not used on the CPU; using fp32")
        return PRECISION_FP32
    return requested


def _torch_dtype(torch: Any, precision: str) -> Any:
    return {PRECISION_FP32: torch.float32, PRECISION_FP16: torch.float16, PRECISION_BF16: torch.bfloat16}[precision]


def parameter_dtypes(model: Any) -> set[Any]:
    """Every dtype among the model's parameters."""
    return {parameter.dtype for parameter in model.parameters()}


def load_sentence_transformer(
    model_id: str, device: str, precision: str = PRECISION_FP32, max_seq_length: int | None = None
) -> Any:
    # Imported here so the engine starts without loading torch.
    import torch
    from sentence_transformers import SentenceTransformer

    target_device = resolve_device(device, torch)
    target_precision = resolve_precision(precision, target_device)
    dtype = _torch_dtype(torch, target_precision)
    # dtype is passed explicitly: without it the checkpoint's own dtype (a model may be stored in BF16) is loaded, which is slow on the CPU.
    model = SentenceTransformer(model_id, device=target_device, model_kwargs={"dtype": dtype})
    if parameter_dtypes(model) != {dtype}:
        model.to(dtype)
    loaded = parameter_dtypes(model)
    if loaded != {dtype}:
        raise RuntimeError(f"{model_id} loaded as {sorted(str(item) for item in loaded)}, expected {dtype}")
    if max_seq_length is not None:
        model.max_seq_length = max_seq_length
    logger.info("loaded %s on %s as %s (max_seq_length=%s)", model_id, target_device, dtype, model.max_seq_length)
    return model


class ModelCache:
    """Loads each model once and shares it between embedders and threads."""

    def __init__(
        self, loader: ModelLoader = load_sentence_transformer, settings: EmbeddingSettings = EmbeddingSettings()
    ) -> None:
        self._loader = loader
        self.settings = settings
        self._models: dict[str, Any] = {}
        self._lock = threading.Lock()

    def get(self, model_id: str) -> Any:
        with self._lock:
            if model_id not in self._models:
                if model_id == TEXT_MODEL_ID:
                    self._models[model_id] = self._loader(
                        model_id, self.settings.device, self.settings.precision, self.settings.max_seq_length
                    )
                else:  # CLIP keeps its own 77-token text limit and always runs in FP32
                    self._models[model_id] = self._loader(model_id, self.settings.device, PRECISION_FP32, None)
            return self._models[model_id]


DEFAULT_MODEL_CACHE = ModelCache()


class TextEmbedder:
    def __init__(self, model_cache: ModelCache = DEFAULT_MODEL_CACHE) -> None:
        self._model_cache = model_cache

    @property
    def fingerprint(self) -> str:
        """Changes when stored vectors would differ for the same text; stored with each collection for reuse."""
        return f"{TEXT_MODEL_ID}|max_seq_length={self._model_cache.settings.max_seq_length}"

    def embed_query(self, text: str) -> Vector:
        return _encode(
            self._model_cache.get(TEXT_MODEL_ID), [QUERY_PREFIX + text], normalize_embeddings=True
        )[0]

    def embed_documents(self, texts: list[str]) -> list[Vector]:
        """Vectors in the order of texts; a text that appears more than once is embedded once.

        Documents get the "passage: " prefix; vectors are normalized to unit length for the cosine collections.
        """
        unique = list(dict.fromkeys(texts))
        vectors = _encode(
            self._model_cache.get(TEXT_MODEL_ID),
            [DOCUMENT_PREFIX + text for text in unique],
            batch_size=self._model_cache.settings.batch_size,
            normalize_embeddings=True,
        )
        by_text = dict(zip(unique, vectors))
        return [list(by_text[text]) for text in texts]

    def split_text(self, text: str) -> list[str]:
        """The text as pieces that each fit max_seq_length tokens; a text that fits is returned whole.

        Long texts are cut into overlapping token windows instead of being truncated, so no content is lost.
        """
        tokenizer = self._model_cache.get(TEXT_MODEL_ID).tokenizer
        # Every embedded document is "passage: " + window, plus the tokenizer's special tokens: measure both.
        special_tokens = len(tokenizer("")["input_ids"])
        prefix_tokens = len(tokenizer(DOCUMENT_PREFIX, add_special_tokens=False)["input_ids"])
        limit = self._model_cache.settings.max_seq_length - special_tokens - prefix_tokens
        return split_by_tokens(text, tokenizer, limit)


def split_by_tokens(text: str, tokenizer: Any, limit: int) -> list[str]:
    """Overlapping windows of at most limit tokens, cut at token borders of the original text."""
    encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True, truncation=False)
    offsets = encoded["offset_mapping"]
    if len(offsets) <= limit:
        return [text]
    overlap = max(1, int(limit * CHUNK_OVERLAP_SHARE))
    pieces: list[str] = []
    start = 0
    while True:
        end = min(start + limit, len(offsets))
        pieces.append(text[offsets[start][0]:offsets[end - 1][1]])
        if end == len(offsets):
            return pieces
        start = end - overlap


def text_digest(text: str) -> str:
    """A short stable key of a document's text, for finding unchanged documents."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ImageEmbedder:
    def __init__(self, model_cache: ModelCache = DEFAULT_MODEL_CACHE) -> None:
        self._model_cache = model_cache

    @property
    def fingerprint(self) -> str:
        return IMAGE_MODEL_ID

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
