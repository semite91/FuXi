import base64
import threading

import numpy as np
import pytest

from embedders import (
    CPU_DEVICE,
    CUDA_DEVICE,
    DEFAULT_ENCODE_BATCH_SIZE,
    DEFAULT_MAX_SEQ_LENGTH,
    IMAGE_MODEL_ID,
    LEGACY_TEXT_MODEL_ID,
    QUERY_PROMPT_NAME,
    TEXT_MODEL_ID,
    EmbeddingConfig,
    ImageEmbedder,
    LoadOptions,
    ModelCache,
    PictureDataError,
    TextEmbedder,
    TextModelSpec,
    decode_picture,
    select_device,
    text_model_spec,
)
from fakes import TEST_PICTURE_SIZE, picture_text

VECTOR_SIZE = 4


class FakeModel:
    def __init__(self):
        self.calls: list[tuple[list, dict]] = []

    def encode(self, inputs, **kwargs):
        self.calls.append((list(inputs), kwargs))
        return np.ones((len(inputs), VECTOR_SIZE), dtype=np.float32)


class RecordingLoader:
    def __init__(self):
        self.loads: list[tuple[str, LoadOptions]] = []
        self.models: dict[str, FakeModel] = {}

    def __call__(self, model_id: str, options: LoadOptions) -> FakeModel:
        self.loads.append((model_id, options))
        return self.models.setdefault(model_id, FakeModel())


def cache_for(loader, **config):
    return ModelCache(loader, EmbeddingConfig(**config), device_selector=lambda requested: CPU_DEVICE)


def test_query_uses_the_query_prompt_and_documents_use_no_prompt():
    # D1
    loader = RecordingLoader()
    embedder = TextEmbedder(cache_for(loader, text_model=QWEN_MODEL))

    query_vector = embedder.embed_query("lucky coincidences")
    document_vectors = embedder.embed_documents(["first note", "second note"])

    model = loader.models[QWEN_MODEL]
    assert model.calls[0] == (["lucky coincidences"], {"batch_size": 8, "prompt_name": QUERY_PROMPT_NAME})
    assert QUERY_PROMPT_NAME == "query"
    assert model.calls[1] == (["first note", "second note"], {"batch_size": 8})
    assert query_vector == [1.0] * VECTOR_SIZE
    assert document_vectors == [[1.0] * VECTOR_SIZE] * 2


def test_image_embedder_embeds_text_with_clip():
    # D2
    loader = RecordingLoader()

    vector = ImageEmbedder(cache_for(loader)).embed_text("a red umbrella in the rain")

    assert loader.loads == [(IMAGE_MODEL_ID, LoadOptions(CPU_DEVICE, "float32", None))]
    assert IMAGE_MODEL_ID == "sentence-transformers/clip-ViT-B-32"
    assert loader.models[IMAGE_MODEL_ID].calls == [(["a red umbrella in the rain"], {"batch_size": 8})]
    assert vector == [1.0] * VECTOR_SIZE


def test_models_load_lazily_on_the_cpu_and_only_once():
    # D3
    loader = RecordingLoader()
    cache = cache_for(loader)
    first, second = TextEmbedder(cache), TextEmbedder(cache)
    assert loader.loads == []  # nothing loads before the first use

    first.embed_query("a")
    second.embed_documents(["b"])
    first.embed_documents(["c"])

    assert loader.loads == [(TEXT_MODEL_ID, LoadOptions(CPU_DEVICE, "float32", 512))]
    assert (TEXT_MODEL_ID, CPU_DEVICE) == ("intfloat/multilingual-e5-small", "cpu")


def test_parallel_first_use_loads_once():
    # D3
    loader = RecordingLoader()
    cache = cache_for(loader)
    threads = [threading.Thread(target=TextEmbedder(cache).embed_query, args=("x",)) for _ in range(8)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(loader.loads) == 1


def test_picture_text_is_decoded_into_an_rgb_picture():
    # Phase 5b D1
    picture = decode_picture(picture_text())

    assert picture.size == TEST_PICTURE_SIZE
    assert picture.mode == "RGB"


@pytest.mark.parametrize("text", ["", "not base64 ***", base64.b64encode(b"not a picture").decode("ascii")])
def test_text_that_is_not_base64_picture_data_raises_a_picture_data_error(text):
    # Phase 5b D2
    with pytest.raises(PictureDataError):
        decode_picture(text)


def test_image_embedder_embeds_pictures_with_clip():
    # Phase 5b D1
    loader = RecordingLoader()
    picture = decode_picture(picture_text())

    vectors = ImageEmbedder(cache_for(loader)).embed_images([picture])

    assert loader.models[IMAGE_MODEL_ID].calls == [([picture], {"batch_size": 8})]
    assert vectors == [[1.0] * VECTOR_SIZE]


def test_defaults_are_float32_auto_device_512_tokens_and_batches_of_8():
    # Phase 8 embedding speed
    config = EmbeddingConfig()

    assert (config.device, config.dtype, config.max_seq_length, config.batch_size) == ("auto", "float32", 512, 8)
    assert (DEFAULT_MAX_SEQ_LENGTH, DEFAULT_ENCODE_BATCH_SIZE) == (512, 8)


def test_configured_precision_length_and_batch_reach_the_loader_and_the_encode_call():
    # Phase 8 embedding speed
    loader = RecordingLoader()
    cache = cache_for(loader, dtype="float16", max_seq_length=256, batch_size=4)

    TextEmbedder(cache).embed_documents(["a"])
    ImageEmbedder(cache).embed_text("b")

    assert loader.loads == [
        (TEXT_MODEL_ID, LoadOptions(CPU_DEVICE, "float16", 256)),
        (IMAGE_MODEL_ID, LoadOptions(CPU_DEVICE, "float16", None)),  # CLIP keeps its own sequence length
    ]
    assert loader.models[TEXT_MODEL_ID].calls == [(["passage: a"], {"batch_size": 4})]


class FakeCuda:
    def __init__(self, available=True, kernel_error=None):
        self.available = available
        self.kernel_error = kernel_error

    def is_available(self):
        return self.available

    def synchronize(self):
        if self.kernel_error:
            raise self.kernel_error

    def get_device_name(self, index):
        return "Fake GPU"


class FakeTorch:
    def __init__(self, available=True, kernel_error=None):
        self.cuda = FakeCuda(available, kernel_error)

    def zeros(self, size, device=None):
        class Tensor:
            def __add__(self, other):
                return self

            def item(self):
                return 1.0

        return Tensor()


@pytest.mark.parametrize("requested", ["auto", "cuda"])
def test_gpu_is_used_when_torch_can_run_a_kernel_on_it(requested):
    # Phase 8 embedding speed
    assert select_device(requested, FakeTorch()) == CUDA_DEVICE


@pytest.mark.parametrize("requested", ["auto", "cuda"])
def test_cpu_is_used_when_torch_sees_no_gpu(requested):
    # Phase 8 embedding speed
    assert select_device(requested, FakeTorch(available=False)) == CPU_DEVICE


@pytest.mark.parametrize("requested", ["auto", "cuda"])
def test_cpu_is_used_when_the_gpu_is_visible_but_runs_no_kernel(requested):
    # Phase 8 embedding speed: a GPU the installed torch was not built for
    error = RuntimeError("no kernel image is available for execution on the device")

    assert select_device(requested, FakeTorch(kernel_error=error)) == CPU_DEVICE


def test_cpu_request_never_asks_torch():
    # Phase 8 embedding speed
    assert select_device("cpu", torch_module=object()) == CPU_DEVICE


E5_MODEL = "intfloat/multilingual-e5-small"
QWEN_MODEL = "Qwen/Qwen3-Embedding-0.6B"
GEMMA_MODEL = "google/embeddinggemma-300m"


def test_the_configured_text_model_is_loaded_and_the_default_is_multilingual_e5_small():
    # Phase 8 text model choice
    loader = RecordingLoader()

    TextEmbedder(cache_for(loader, text_model=QWEN_MODEL)).embed_documents(["a"])

    assert [model_id for model_id, _ in loader.loads] == [QWEN_MODEL]
    assert EmbeddingConfig().text_model == TEXT_MODEL_ID == E5_MODEL
    assert LEGACY_TEXT_MODEL_ID == QWEN_MODEL  # what a collection without a recorded model was built with


def test_e5_models_get_query_and_passage_prefixes_and_no_prompt_names():
    # Phase 8 text model choice
    loader = RecordingLoader()
    embedder = TextEmbedder(cache_for(loader, text_model=E5_MODEL))

    embedder.embed_query("lucky coincidences")
    embedder.embed_documents(["first note"])

    calls = loader.models[E5_MODEL].calls
    assert calls[0] == (["query: lucky coincidences"], {"batch_size": 8})
    assert calls[1] == (["passage: first note"], {"batch_size": 8})


def test_gemma_models_use_their_own_prompt_names_and_an_unknown_model_gets_plain_text():
    # Phase 8 text model choice
    loader = RecordingLoader()
    TextEmbedder(cache_for(loader, text_model=GEMMA_MODEL)).embed_query("q")
    TextEmbedder(cache_for(loader, text_model=GEMMA_MODEL)).embed_documents(["d"])
    TextEmbedder(cache_for(loader, text_model="someone/unknown-model")).embed_documents(["d"])

    gemma_calls = loader.models[GEMMA_MODEL].calls
    assert gemma_calls[0] == (["q"], {"batch_size": 8, "prompt_name": "query"})
    assert gemma_calls[1] == (["d"], {"batch_size": 8, "prompt_name": "document"})
    assert loader.models["someone/unknown-model"].calls == [(["d"], {"batch_size": 8})]
    assert text_model_spec("someone/unknown-model") == TextModelSpec()
    assert text_model_spec(E5_MODEL).reserved_tokens > 0 and text_model_spec(QWEN_MODEL).reserved_tokens == 0
    assert (text_model_spec(E5_MODEL).default_threshold, text_model_spec(QWEN_MODEL).default_threshold) == (0.72, 0.5)
    assert text_model_spec("someone/unknown-model").default_threshold == 0.5


def test_text_identity_names_the_model_and_clip_has_its_own():
    # Phase 8 embedding cache
    assert TextEmbedder(cache_for(RecordingLoader())).identity == TEXT_MODEL_ID
    assert TextEmbedder(cache_for(RecordingLoader(), text_model=E5_MODEL)).identity == E5_MODEL
    assert ImageEmbedder(cache_for(RecordingLoader())).identity == IMAGE_MODEL_ID
