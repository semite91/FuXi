"""Device and precision selection, token-aware chunking, de-duplication and vector reuse."""

from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pytest

import embedders
from base import Document, Resource, ResourceKind
from chroma_store import TEXT_COLLECTION_NAME, create_chroma_client, open_collection
from embedders import (
    ModelCache,
    TextEmbedder,
    load_sentence_transformer,
    resolve_device,
    resolve_precision,
    split_by_tokens,
)
from embedding_pipeline import Embedders, Mode, run
from fakes import FakeEmbedder
from settings import EmbeddingSettings, SettingsError, load_settings


def fake_torch(*, available=True, capability=(8, 6), arch_list=("sm_80", "sm_90"), kernel_error=None):
    def zeros(*args, **kwargs):
        if kernel_error:
            raise kernel_error
        return SimpleNamespace(add_=lambda value: SimpleNamespace(item=lambda: 1.0))

    cuda = SimpleNamespace(
        is_available=lambda: available,
        get_device_capability=lambda index: capability,
        get_arch_list=lambda: list(arch_list),
    )
    return SimpleNamespace(cuda=cuda, zeros=zeros)


# --- hardware detection ---------------------------------------------------------------------------------------


def test_auto_uses_cuda_only_when_torch_and_gpu_really_work():
    assert resolve_device("auto", fake_torch()) == "cuda"


@pytest.mark.parametrize(
    "torch",
    [
        fake_torch(available=False),  # CPU-only build or no driver
        fake_torch(capability=(12, 0), arch_list=("sm_80", "sm_90")),  # GPU newer than the build's kernels
        fake_torch(kernel_error=RuntimeError("no kernel image is available")),  # arch listed, kernel still fails
    ],
)
def test_auto_falls_back_to_the_cpu_when_cuda_cannot_run(torch):
    assert resolve_device("auto", torch) == "cpu"


def test_cpu_is_never_replaced_and_cuda_without_support_warns_and_uses_the_cpu(caplog):
    assert resolve_device("cpu", fake_torch()) == "cpu"
    assert resolve_device("cuda", fake_torch(available=False)) == "cpu"
    assert "CUDA is not usable" in caplog.text


def test_ptx_makes_a_newer_gpu_usable():
    assert resolve_device("auto", fake_torch(capability=(12, 0), arch_list=("sm_90", "compute_90"))) == "cuda"


def test_fp16_is_not_used_on_the_cpu():
    assert resolve_precision("fp16", "cpu") == "fp32"
    assert resolve_precision("fp16", "cuda") == "fp16"
    assert resolve_precision("bf16", "cpu") == "bf16"


# --- settings -------------------------------------------------------------------------------------------------


def test_embedding_settings_default_to_fp32_512_tokens_batch_8(tmp_path):
    settings = load_settings(tmp_path / "missing.env", environ={})

    assert settings.embedding == EmbeddingSettings("auto", "fp32", 512, 8)


def test_embedding_settings_are_read_from_the_environment(tmp_path):
    settings = load_settings(
        tmp_path / "missing.env",
        environ={
            "RAG_EMBEDDING_DEVICE": "CPU",
            "RAG_EMBEDDING_PRECISION": "bf16",
            "RAG_MAX_SEQ_LENGTH": "256",
            "RAG_BATCH_SIZE": "4",
        },
    )

    assert settings.embedding == EmbeddingSettings("cpu", "bf16", 256, 4)


@pytest.mark.parametrize(
    ("key", "value"),
    [("RAG_EMBEDDING_DEVICE", "tpu"), ("RAG_EMBEDDING_PRECISION", "int8"), ("RAG_MAX_SEQ_LENGTH", "0"), ("RAG_MAX_SEQ_LENGTH", "abc")],
)
def test_invalid_embedding_settings_are_rejected(tmp_path, key, value):
    with pytest.raises(SettingsError, match=key):
        load_settings(tmp_path / "missing.env", environ={key: value})


# --- real model loading, tiny Qwen3 checkpoint saved in BF16 like the real one -------------------------------


@pytest.fixture(scope="module")
def tiny_qwen(tmp_path_factory):
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers

    path = tmp_path_factory.mktemp("tiny_qwen")
    tokenizer = Tokenizer(models.BPE(unk_token="[UNK]"))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    tokenizer.train_from_iterator(
        ["the quick brown fox jumps over the lazy dog " * 4, "notes about movies songs and pictures " * 4],
        trainers.BpeTrainer(vocab_size=120, special_tokens=["[UNK]", "[PAD]"]),
    )
    fast = transformers.PreTrainedTokenizerFast(tokenizer_object=tokenizer, unk_token="[UNK]", pad_token="[PAD]")
    fast.save_pretrained(path)
    config = transformers.Qwen3Config(
        vocab_size=fast.vocab_size + 2, hidden_size=32, intermediate_size=64, num_hidden_layers=2,
        num_attention_heads=4, num_key_value_heads=2, head_dim=8, max_position_embeddings=512,
    )
    torch.manual_seed(0)
    transformers.Qwen3Model(config).to(torch.bfloat16).save_pretrained(path)
    return str(path)


def test_the_model_loads_as_fp32_although_the_checkpoint_is_bf16(tiny_qwen):
    import torch

    model = load_sentence_transformer(tiny_qwen, "cpu", "fp32", 64)

    assert embedders.parameter_dtypes(model) == {torch.float32}
    assert model.max_seq_length == 64


def test_the_precision_is_configurable(tiny_qwen):
    import torch

    assert embedders.parameter_dtypes(load_sentence_transformer(tiny_qwen, "cpu", "bf16", 64)) == {torch.bfloat16}


def test_a_dtype_that_cannot_be_applied_is_an_error(tiny_qwen, monkeypatch):
    model = load_sentence_transformer(tiny_qwen, "cpu", "fp32", 64)
    monkeypatch.setattr(embedders, "parameter_dtypes", lambda loaded: {"torch.bfloat16"})
    monkeypatch.setattr("sentence_transformers.SentenceTransformer", lambda *a, **k: model)

    with pytest.raises(RuntimeError, match="expected"):
        load_sentence_transformer(tiny_qwen, "cpu", "fp32", 64)


def test_long_text_is_split_into_overlapping_windows_that_lose_nothing(tiny_qwen):
    model = load_sentence_transformer(tiny_qwen, "cpu", "fp32", 64)
    text = " ".join(f"fox{index}" for index in range(300))

    pieces = split_by_tokens(text, model.tokenizer, 40)

    assert len(pieces) > 1
    for piece in pieces:
        assert len(model.tokenizer(piece, add_special_tokens=False)["input_ids"]) <= 41
    assert text.startswith(pieces[0]) and text.endswith(pieces[-1])
    assert all(f"fox{index}" in " ".join(pieces) for index in range(300))
    assert split_by_tokens("the lazy dog", model.tokenizer, 40) == ["the lazy dog"]


def test_text_embedder_splits_by_the_configured_limit_and_keeps_vectors_normalized(tiny_qwen):
    cache = ModelCache(settings=EmbeddingSettings("cpu", "fp32", 32, 2))
    text_embedder = TextEmbedder(cache)
    text_embedder_model_id = embedders.TEXT_MODEL_ID
    cache._models[text_embedder_model_id] = load_sentence_transformer(tiny_qwen, "cpu", "fp32", 32)
    text = " ".join(f"fox{index}" for index in range(200))

    pieces = text_embedder.split_text(text)
    vectors = text_embedder.embed_documents(pieces)

    assert len(pieces) > 1
    assert len(vectors) == len(pieces) and len({len(vector) for vector in vectors}) == 1


# --- batch embedding de-duplication ---------------------------------------------------------------------------


class CountingModel:
    def __init__(self):
        self.encoded: list[list[str]] = []

    def encode(self, inputs, **kwargs):
        self.encoded.append(list(inputs))
        return np.array([[float(len(text.removeprefix('passage: '))), 1.0] for text in inputs], dtype=np.float32)


def test_identical_texts_in_one_call_are_embedded_once_and_keep_their_order():
    model = CountingModel()
    cache = ModelCache(lambda *args: model, EmbeddingSettings("cpu", "fp32", 512, 8))

    vectors = TextEmbedder(cache).embed_documents(["aa", "b", "aa"])

    assert model.encoded == [["passage: aa", "passage: b"]]
    assert vectors == [[2.0, 1.0], [1.0, 1.0], [2.0, 1.0]]


# --- reuse of unchanged documents -----------------------------------------------------------------------------

FIXED_TIME = datetime(2026, 11, 21, 9, 0)


class TextResource(Resource):
    name = "notes"
    kind = ResourceKind.TEXT

    def __init__(self, texts):
        self.texts = texts

    def read_documents(self):
        return [Document(text=text, metadata={"name": text}) for text in self.texts]


class FingerprintedEmbedder(FakeEmbedder):
    def __init__(self, fingerprint="model-a", limit=None):
        super().__init__()
        self.fingerprint = fingerprint
        self.limit = limit

    def split_text(self, text):
        if self.limit and len(text) > self.limit:
            return [text[start:start + self.limit] for start in range(0, len(text), self.limit)]
        return [text]


def build(tmp_path, client, texts, text_embedder):
    return run(
        Mode.CREATE,
        resources=[TextResource(texts)],
        embedders=Embedders(text=text_embedder, image=FakeEmbedder()),
        chroma_client=client,
        batch_size=8,
        logs_dir=tmp_path / "logs",
        clock=lambda: FIXED_TIME,
    )


def test_unchanged_documents_are_not_embedded_again(tmp_path):
    client = create_chroma_client(tmp_path / "chroma")
    first = FingerprintedEmbedder()
    build(tmp_path, client, ["one", "two"], first)

    second = FingerprintedEmbedder()
    result = build(tmp_path, client, ["one", "two", "three"], second)

    assert result.complete
    assert second.document_batches == [["three"]]
    assert open_collection(client, TEXT_COLLECTION_NAME).count() == 3


def test_nothing_is_embedded_when_nothing_changed(tmp_path):
    client = create_chroma_client(tmp_path / "chroma")
    build(tmp_path, client, ["one", "two"], FingerprintedEmbedder())

    second = FingerprintedEmbedder()
    build(tmp_path, client, ["one", "two"], second)

    assert second.document_batches == []
    assert open_collection(client, TEXT_COLLECTION_NAME).count() == 2


def test_a_changed_model_fingerprint_embeds_everything_again(tmp_path):
    client = create_chroma_client(tmp_path / "chroma")
    build(tmp_path, client, ["one", "two"], FingerprintedEmbedder("model-a"))

    second = FingerprintedEmbedder("model-b")
    build(tmp_path, client, ["one", "two"], second)

    assert second.document_batches == [["one", "two"]]


def test_embedders_without_a_fingerprint_never_reuse(tmp_path):
    client = create_chroma_client(tmp_path / "chroma")
    build(tmp_path, client, ["one"], FakeEmbedder())

    second = FakeEmbedder()
    build(tmp_path, client, ["one"], second)

    assert second.document_batches == [["one"]]


def test_a_document_over_the_token_limit_becomes_several_documents_with_the_same_metadata(tmp_path):
    client = create_chroma_client(tmp_path / "chroma")

    build(tmp_path, client, ["x" * 25], FingerprintedEmbedder(limit=10))

    stored = open_collection(client, TEXT_COLLECTION_NAME).get()
    assert sorted(stored["documents"], key=len) == ["x" * 5, "x" * 10, "x" * 10]
    assert {metadata["name"] for metadata in stored["metadatas"]} == {"x" * 25}


# --- switching the model: stale collections are rebuilt, windows leave room for the prefix ----------------------


def test_a_collection_built_by_another_model_is_not_ready_and_is_built_again(tmp_path):
    from chroma_store import is_build_complete

    client = create_chroma_client(tmp_path / "chroma")
    build(tmp_path, client, ["one", "two"], FingerprintedEmbedder("Qwen/Qwen3-Embedding-0.6B"))

    assert is_build_complete(client, "Qwen/Qwen3-Embedding-0.6B")
    assert not is_build_complete(client, "intfloat/multilingual-e5-small")
    assert is_build_complete(client)  # without a fingerprint the old rule applies


def test_a_collection_without_a_fingerprint_is_not_ready_for_a_fingerprinted_embedder(tmp_path):
    from chroma_store import is_build_complete

    client = create_chroma_client(tmp_path / "chroma")
    build(tmp_path, client, ["one"], FakeEmbedder())  # no fingerprint is stored, like a build before this change

    assert not is_build_complete(client, "intfloat/multilingual-e5-small")


def test_a_window_with_the_passage_prefix_still_fits_the_token_limit(tiny_qwen):
    model = load_sentence_transformer(tiny_qwen, "cpu", "fp32", 64)
    cache = ModelCache(settings=EmbeddingSettings("cpu", "fp32", 64, 8))
    cache._models[embedders.TEXT_MODEL_ID] = model
    text = " ".join(f"fox{index}" for index in range(300))

    for piece in TextEmbedder(cache).split_text(text):
        with_prefix = embedders.DOCUMENT_PREFIX + piece
        assert len(model.tokenizer(with_prefix)["input_ids"]) <= 64  # special tokens included


def test_the_text_embedder_fingerprint_names_the_model_and_the_limit():
    cache = ModelCache(settings=EmbeddingSettings("cpu", "fp32", 256, 8))

    assert TextEmbedder(cache).fingerprint == "intfloat/multilingual-e5-small|max_seq_length=256"
