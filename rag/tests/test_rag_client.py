import math
import threading

import pytest

from base import Document, Resource, ResourceKind, RetrievedItem
from chroma_store import IMAGE_COLLECTION_NAME, TEXT_COLLECTION_NAME, create_chroma_client, open_collection
from embedding_pipeline import Embedders, Mode, run
from fakes import FakeEmbedder, picture_text
from rag_client import TOP_K, RagClient, Word
from settings import Settings

DIMENSIONS = 8
QUERY_VECTOR = [1.0] + [0.0] * (DIMENSIONS - 1)


def vector_with_similarity(similarity: float) -> list[float]:
    return [similarity, math.sqrt(1 - similarity**2)] + [0.0] * (DIMENSIONS - 2)


def add(collection, similarities):
    collection.add(
        ids=[f"id-{index}" for index in range(len(similarities))],
        documents=[f"doc {value}" for value in similarities],
        embeddings=[vector_with_similarity(value) for value in similarities],
        metadatas=[{"name": f"n{value}"} for value in similarities],
    )


class FakeLlm:
    def __init__(self, failing_word=None):
        self.failing_word = failing_word
        self.generated = []

    def build_search_query(self, word, meaning):
        return f"query for {word}"

    def generate(self, word, meaning, text_results, image_results):
        if word == self.failing_word:
            raise RuntimeError("Gemini is down")
        self.generated.append((word, meaning, text_results, image_results))
        return f'{{"method":"story","title":"{word}"}}'


@pytest.fixture
def chroma_path(tmp_path):
    return tmp_path / "chroma"


@pytest.fixture
def embedders():
    return Embedders(text=FakeEmbedder(QUERY_VECTOR), image=FakeEmbedder(QUERY_VECTOR))


def make_client(chroma_path, embedders, llm=None, settings=Settings(), factory_calls=None):
    calls = [] if factory_calls is None else factory_calls

    def factory():
        calls.append(1)
        return create_chroma_client(chroma_path)

    return RagClient(factory, embedders, settings, llm or FakeLlm())


def test_init_opens_collections_once(chroma_path, embedders):
    # F1
    calls = []
    client = make_client(chroma_path, embedders, factory_calls=calls)

    first = client.init()
    second = client.init()

    assert first is second
    assert len(calls) == 1
    assert (first.text.name, first.image.name) == (TEXT_COLLECTION_NAME, IMAGE_COLLECTION_NAME)


def test_parallel_init_opens_collections_once(chroma_path, embedders):
    # F1
    calls = []
    client = make_client(chroma_path, embedders, factory_calls=calls)
    threads = [threading.Thread(target=client.init) for _ in range(8)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(calls) == 1


def test_query_is_embedded_with_qwen_and_clip(chroma_path, embedders):
    # F2
    make_client(chroma_path, embedders).retrieve("lucky coincidences")

    assert embedders.text.queries == ["lucky coincidences"]
    assert embedders.text.text_queries == []
    assert embedders.image.text_queries == ["lucky coincidences"]
    assert embedders.image.queries == []


def test_each_collection_returns_at_most_top_k(chroma_path, embedders):
    # F3
    client = make_client(chroma_path, embedders)
    collections = client.init()
    add(collections.text, [0.9] * 25)
    add(collections.image, [0.9] * 3)

    texts, images = client.retrieve("q")

    assert TOP_K == 20
    assert len(texts) == 20
    assert len(images) == 3


def test_text_threshold_keeps_results_at_or_above_it(chroma_path, embedders):
    # F4
    client = make_client(chroma_path, embedders, settings=Settings(text_threshold=0.5))
    add(client.init().text, [0.7, 0.5, 0.3])

    texts, _ = client.retrieve("q")

    assert [item.similarity for item in texts] == pytest.approx([0.7, 0.5])


def test_image_threshold_drops_results_below_it(chroma_path, embedders):
    # F5
    client = make_client(chroma_path, embedders, settings=Settings(image_threshold=0.25))
    add(client.init().image, [0.4, 0.25, 0.2])

    _, images = client.retrieve("q")

    assert [item.similarity for item in images] == pytest.approx([0.4, 0.25])


def test_retrieve_returns_text_and_image_lists(chroma_path, embedders):
    # F6
    client = make_client(chroma_path, embedders)
    collections = client.init()
    add(collections.text, [0.8])
    add(collections.image, [0.6])

    texts, images = client.retrieve("q")

    assert texts == [RetrievedItem(document="doc 0.8", metadata={"name": "n0.8"}, similarity=pytest.approx(0.8))]
    assert images[0].document == "doc 0.6"
    assert images[0].metadata == {"name": "n0.6"}


def test_empty_collections_give_empty_lists(chroma_path, embedders):
    # F7
    assert make_client(chroma_path, embedders).retrieve("q") == ([], [])


class OneNote(Resource):
    name = "notion"
    kind = ResourceKind.TEXT

    def read_documents(self):
        return [Document("fresh note", {"name": "Fresh"})]


def test_refresh_points_to_the_new_collections_after_update(chroma_path, embedders, tmp_path):
    # F8
    client = make_client(chroma_path, embedders)
    old = client.init()

    run(Mode.UPDATE, resources=[OneNote()], embedders=embedders, chroma_client=create_chroma_client(chroma_path),
        batch_size=16, logs_dir=tmp_path / "logs")
    new = client.refresh()

    assert new is not old
    assert new.text.id == open_collection(create_chroma_client(chroma_path), TEXT_COLLECTION_NAME).id
    assert [item.document for item in client.retrieve("q")[0]] == ["fresh note"]


def test_one_failing_word_does_not_stop_the_others(chroma_path, embedders):
    # G16
    llm = FakeLlm(failing_word="beta")
    client = make_client(chroma_path, embedders, llm=llm)

    results = client.generate([Word("alpha", "a"), Word("beta", "b"), Word("gamma", "g")])

    assert [(result.name, result.content is not None) for result in results] == [
        ("alpha", True), ("beta", False), ("gamma", True)
    ]
    assert [entry[:2] for entry in llm.generated] == [("alpha", "a"), ("gamma", "g")]
    assert embedders.text.queries == ["query for alpha", "query for beta", "query for gamma"]


def test_image_results_above_the_threshold_hold_their_base64_document_and_metadata(chroma_path, embedders):
    # Phase 5b F1
    client = make_client(chroma_path, embedders, settings=Settings(image_threshold=0.25))
    picture = picture_text()
    metadata = {"name": "umbrella.png", "path": "Photos / Paris", "type": "picture", "timestamp": "2026-09-21T10:05:00.000Z"}
    client.init().image.add(
        ids=["kept", "dropped"],
        documents=[picture, picture_text(color=(1, 2, 3))],
        embeddings=[vector_with_similarity(0.4), vector_with_similarity(0.1)],
        metadatas=[metadata, {**metadata, "name": "dark.png"}],
    )

    _, images = client.retrieve("q")

    assert images == [RetrievedItem(document=picture, metadata=metadata, similarity=pytest.approx(0.4))]
