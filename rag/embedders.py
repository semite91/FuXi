"""Text (multilingual-e5-small) and image (CLIP) embedders. Models load lazily, once per process, on the GPU when this machine can
run one and on the CPU otherwise, with the precision and the sequence length of EmbeddingConfig."""

import base64
import io
import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from PIL import Image

# The text model unless RAG_TEXT_MODEL says otherwise: 384 numbers per text and about ten times faster than Qwen3 on a CPU.
TEXT_MODEL_ID = "intfloat/multilingual-e5-small"
# The model of a collection built before collections recorded theirs.
LEGACY_TEXT_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
IMAGE_MODEL_ID = "sentence-transformers/clip-ViT-B-32"
CPU_DEVICE = "cpu"
CUDA_DEVICE = "cuda"
AUTO_DEVICE = "auto"
DEVICE_CHOICES = (AUTO_DEVICE, CPU_DEVICE, CUDA_DEVICE)
# Precision names (torch.<name>). float32 is the default: the model file asks for bfloat16, which is very slow on a
# CPU without bfloat16 support.
FLOAT32 = "float32"
DTYPE_CHOICES = (FLOAT32, "float16", "bfloat16")
DEFAULT_MAX_SEQ_LENGTH = 512
DEFAULT_ENCODE_BATCH_SIZE = 8
# The text models add a start and an end token to each text; a chunk keeps this many tokens free for them.
SPECIAL_TOKENS_MARGIN = 2
QUERY_PROMPT_NAME = "query"
UNTUNED_TEXT_THRESHOLD = 0.5
RGB_MODE = "RGB"
# Pillow raises these for data it cannot open (UnidentifiedImageError is an OSError); bad Base64 is a ValueError.
PICTURE_ERRORS = (OSError, ValueError, Image.DecompressionBombError)

logger = logging.getLogger(__name__)

Vector = list[float]


@dataclass(frozen=True)
class EmbeddingConfig:
    """How the models run. device: auto (GPU when it works, else CPU), cpu or cuda; dtype: a name of DTYPE_CHOICES;
    max_seq_length: tokens of the text model (longer text is cut, so documents are chunked to fit);
    batch_size: texts or pictures per forward pass; text_model: the text model's id (another model gives vectors of
    another size, so every stored text vector must be built again)."""

    device: str = AUTO_DEVICE
    dtype: str = FLOAT32
    max_seq_length: int = DEFAULT_MAX_SEQ_LENGTH
    batch_size: int = DEFAULT_ENCODE_BATCH_SIZE
    text_model: str = TEXT_MODEL_ID


@dataclass(frozen=True)
class LoadOptions:
    """What a model loader needs: the device chosen, the precision name and the sequence length (text model only)."""

    device: str
    dtype: str
    max_seq_length: int | None = None


@dataclass(frozen=True)
class TextModelSpec:
    """How a text model wants its input: a prompt name of the model's own config, or a prefix put before the text,
    for questions and for documents; reserved_tokens is what that adds to every text (chunks leave room for it)."""

    query_prompt_name: str | None = None
    document_prompt_name: str | None = None
    query_prefix: str = ""
    document_prefix: str = ""
    reserved_tokens: int = 0
    # The least similarity (1 minus the cosine distance) for a text to be kept. It depends on the model: the cosine of
    # e5 vectors sits between about 0.7 and 0.9 whatever the question, Qwen3's spreads over the whole range.
    default_threshold: float = UNTUNED_TEXT_THRESHOLD


# Known text models, by a part of the model id. A model that is not listed gets plain text.
TEXT_MODEL_SPECS = (
    (("qwen3-embedding",), TextModelSpec(query_prompt_name=QUERY_PROMPT_NAME)),
    (
        ("multilingual-e5", "/e5-"),
        # 0.72 is below the 0.84 that kept 93% of the texts a 12-word quotation finds and let 30% of unrelated questions return something
        # (measured on 500 real Notion chunks); tune it with RAG_TEXT_THRESHOLD.
        TextModelSpec(query_prefix="query: ", document_prefix="passage: ", reserved_tokens=4, default_threshold=0.72),
    ),
    (
        ("embeddinggemma",),
        TextModelSpec(query_prompt_name=QUERY_PROMPT_NAME, document_prompt_name="document", reserved_tokens=16),
    ),
)


def text_model_spec(model_id: str) -> TextModelSpec:
    lowered = model_id.lower()
    for markers, prompts in TEXT_MODEL_SPECS:
        if any(marker in lowered for marker in markers):
            return prompts
    return TextModelSpec()


ModelLoader = Callable[[str, LoadOptions], Any]


class ModelPrecisionError(RuntimeError):
    """A model loaded with another precision than the configured one."""


class PictureDataError(ValueError):
    """A picture document's text is not Base64 picture data."""


class DocumentEmbedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[Vector]: ...


class QueryEmbedder(Protocol):
    def embed_query(self, text: str) -> Vector: ...


class TextQueryEmbedder(Protocol):
    def embed_text(self, text: str) -> Vector: ...


def select_device(requested: str, torch_module: Any = None) -> str:
    """The device to use. cpu always; auto and cuda use the GPU only when torch can run a kernel on it (a driver or an
    nvidia-smi alone proves nothing: the installed torch may be a CPU build or not compiled for this GPU), else cpu."""
    if requested == CPU_DEVICE:
        return CPU_DEVICE
    if torch_module is None:
        import torch as torch_module  # imported here so the engine starts without loading torch
    reason = _cuda_problem(torch_module)
    if reason is None:
        logger.info("Embedding device: cuda (%s)", torch_module.cuda.get_device_name(0))
        return CUDA_DEVICE
    log = logger.warning if requested == CUDA_DEVICE else logger.info
    log("Embedding device: cpu (%s)", reason)
    return CPU_DEVICE


def _cuda_problem(torch: Any) -> str | None:
    """Why the GPU cannot be used, or None when a kernel ran on it."""
    if not torch.cuda.is_available():
        return "this torch build has no usable CUDA GPU"
    try:
        probe = torch.zeros(1, device=CUDA_DEVICE) + 1
        torch.cuda.synchronize()
        probe.item()
    except Exception as error:  # an unsupported GPU architecture or a broken driver raises many error types
        return f"the GPU did not run a test kernel: {type(error).__name__}"
    return None


def load_sentence_transformer(model_id: str, options: LoadOptions) -> Any:
    """Loads with the configured precision (not the one the model file asks for) and checks what was loaded."""
    # Imported here so the engine starts without loading torch.
    import torch
    from sentence_transformers import SentenceTransformer

    dtype = getattr(torch, options.dtype)
    model = SentenceTransformer(model_id, device=options.device, model_kwargs={"dtype": dtype})
    actual = next(model.parameters()).dtype
    if actual != dtype:
        raise ModelPrecisionError(f"{model_id} loaded as {actual}, not {dtype}")
    if options.max_seq_length is not None:
        model.max_seq_length = options.max_seq_length
    logger.info("Loaded %s on %s as %s, max sequence length %s", model_id, options.device, actual, model.max_seq_length)
    return model


class ModelCache:
    """Loads each model once and shares it between embedders and threads."""

    def __init__(
        self,
        loader: ModelLoader = load_sentence_transformer,
        config: EmbeddingConfig = EmbeddingConfig(),
        device_selector: Callable[[str], str] = select_device,
    ) -> None:
        self._loader = loader
        self.config = config
        self._device_selector = device_selector
        self._device: str | None = None
        self._models: dict[str, Any] = {}
        self._lock = threading.Lock()

    def get(self, model_id: str) -> Any:
        with self._lock:
            if model_id not in self._models:
                if self._device is None:
                    self._device = self._device_selector(self.config.device)
                max_seq_length = self.config.max_seq_length if model_id == self.config.text_model else None
                options = LoadOptions(self._device, self.config.dtype, max_seq_length)
                self._models[model_id] = self._loader(model_id, options)
            return self._models[model_id]

    @property
    def text_identity(self) -> str:
        """Names the vectors the text model gives: another model gives other vectors, perhaps of another size."""
        return self.config.text_model


DEFAULT_MODEL_CACHE = ModelCache()


class TextEmbedder:
    def __init__(self, model_cache: ModelCache = DEFAULT_MODEL_CACHE) -> None:
        self._model_cache = model_cache

    @property
    def identity(self) -> str:
        return self._model_cache.text_identity

    def embed_query(self, text: str) -> Vector:
        config = self._model_cache.config
        prompts = text_model_spec(config.text_model)
        options = {"prompt_name": prompts.query_prompt_name} if prompts.query_prompt_name else {}
        return _encode(self._model_cache.get(config.text_model), [prompts.query_prefix + text], config, **options)[0]

    def embed_documents(self, texts: list[str]) -> list[Vector]:
        config = self._model_cache.config
        prompts = text_model_spec(config.text_model)
        options = {"prompt_name": prompts.document_prompt_name} if prompts.document_prompt_name else {}
        inputs = [prompts.document_prefix + text for text in texts] if prompts.document_prefix else texts
        return _encode(self._model_cache.get(config.text_model), inputs, config, **options)


class ImageEmbedder:
    identity = IMAGE_MODEL_ID

    def __init__(self, model_cache: ModelCache = DEFAULT_MODEL_CACHE) -> None:
        self._model_cache = model_cache

    def embed_text(self, text: str) -> Vector:
        """CLIP text encoder, for searching the image collection."""
        return _encode(self._model_cache.get(IMAGE_MODEL_ID), [text], self._model_cache.config)[0]

    def embed_images(self, images: Sequence[Image.Image]) -> list[Vector]:
        """CLIP image encoder; picture documents are decoded with decode_picture first."""
        return _encode(self._model_cache.get(IMAGE_MODEL_ID), list(images), self._model_cache.config)


def decode_picture(text: str) -> Image.Image:
    """A picture document's Base64 text as an RGB picture."""
    try:
        with Image.open(io.BytesIO(base64.b64decode(text, validate=True))) as picture:
            return picture.convert(RGB_MODE)
    except PICTURE_ERRORS as error:
        raise PictureDataError("the text is not Base64 picture data") from error


def _encode(model: Any, inputs: list[Any], config: EmbeddingConfig, **options: Any) -> list[Vector]:
    return model.encode(inputs, batch_size=config.batch_size, **options).tolist()


# Larger than any text counted; only the counting tokenizer is given it, never the model.
COUNTING_MAX_LENGTH = 10**9


class TokenCounter:
    """Tokens of a text for the text model, so chunks can be cut to fit its sequence length. The tokenizer (not the
    model) loads at the first count."""

    def __init__(self, model_id: str = TEXT_MODEL_ID) -> None:
        self._model_id = model_id
        self._tokenizer: Any = None
        self._lock = threading.Lock()

    def __call__(self, text: str) -> int:
        return len(self._get_tokenizer()(text, add_special_tokens=False)["input_ids"])

    def _get_tokenizer(self) -> Any:
        with self._lock:
            if self._tokenizer is None:
                from transformers import AutoTokenizer  # a dependency of sentence-transformers

                tokenizer = AutoTokenizer.from_pretrained(self._model_id)
                # Texts are counted before they are cut to fit the model, so a long one is expected here; without
                # this the tokenizer warns about every text longer than the model's limit.
                tokenizer.model_max_length = COUNTING_MAX_LENGTH
                self._tokenizer = tokenizer
            return self._tokenizer
