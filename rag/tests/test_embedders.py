import base64
import threading

import numpy as np
import pytest

from embedders import (
    IMAGE_MODEL_ID,
    DOCUMENT_PREFIX,
    QUERY_PREFIX,
    TEXT_MODEL_ID,
    ImageEmbedder,
    ModelCache,
    PictureDataError,
    TextEmbedder,
    decode_picture,
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
        self.loads: list[tuple] = []
        self.models: dict[str, FakeModel] = {}

    def __call__(self, model_id: str, device: str, precision: str, max_seq_length) -> FakeModel:
        self.loads.append((model_id, device, precision, max_seq_length))
        return self.models.setdefault(model_id, FakeModel())


def test_query_and_documents_get_their_e5_prefixes_and_are_normalized():
    # D1
    loader = RecordingLoader()
    embedder = TextEmbedder(ModelCache(loader))

    query_vector = embedder.embed_query("lucky coincidences")
    document_vectors = embedder.embed_documents(["first note", "second note"])

    model = loader.models[TEXT_MODEL_ID]
    assert model.calls[0] == (["query: lucky coincidences"], {"normalize_embeddings": True})
    assert (QUERY_PREFIX, DOCUMENT_PREFIX) == ("query: ", "passage: ")
    assert model.calls[1] == (
        ["passage: first note", "passage: second note"],
        {"batch_size": 8, "normalize_embeddings": True},
    )
    assert query_vector == [1.0] * VECTOR_SIZE
    assert document_vectors == [[1.0] * VECTOR_SIZE] * 2


def test_image_embedder_embeds_text_with_clip():
    # D2
    loader = RecordingLoader()

    vector = ImageEmbedder(ModelCache(loader)).embed_text("a red umbrella in the rain")

    assert loader.loads == [(IMAGE_MODEL_ID, "auto", "fp32", None)]
    assert IMAGE_MODEL_ID == "sentence-transformers/clip-ViT-B-32"
    assert loader.models[IMAGE_MODEL_ID].calls == [(["a red umbrella in the rain"], {})]
    assert vector == [1.0] * VECTOR_SIZE


def test_models_load_lazily_and_only_once():
    # D3
    loader = RecordingLoader()
    cache = ModelCache(loader)
    first, second = TextEmbedder(cache), TextEmbedder(cache)
    assert loader.loads == []  # nothing loads before the first use

    first.embed_query("a")
    second.embed_documents(["b"])
    first.embed_documents(["c"])

    assert loader.loads == [(TEXT_MODEL_ID, "auto", "fp32", 512)]
    assert TEXT_MODEL_ID == "intfloat/multilingual-e5-small"


def test_parallel_first_use_loads_once():
    # D3
    loader = RecordingLoader()
    cache = ModelCache(loader)
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

    vectors = ImageEmbedder(ModelCache(loader)).embed_images([picture])

    assert loader.models[IMAGE_MODEL_ID].calls == [([picture], {})]
    assert vectors == [[1.0] * VECTOR_SIZE]
