"""Test doubles shared by the test modules: no network, no real models."""

import json
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
START_CURSOR = "start"
FAKE_VECTOR_SIZE = 8


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class FakeNotionClient:
    """Answers search, block children and page calls from recorded JSON."""

    def __init__(self, recorded: dict[str, Any], errors: list[Exception] | None = None):
        self.recorded = recorded
        self.errors = list(errors or [])
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.blocks = _FakeBlocks(self)
        self.pages = _FakePages(self)

    def search(self, **kwargs: Any) -> dict[str, Any]:
        self._record("search", kwargs)
        return self.recorded["search"][kwargs.get("start_cursor") or START_CURSOR]

    def _record(self, name: str, kwargs: dict[str, Any]) -> None:
        self.calls.append((name, kwargs))
        if self.errors:
            raise self.errors.pop(0)


class _FakeBlocks:
    def __init__(self, owner: FakeNotionClient):
        self.children = _FakeChildren(owner)


class _FakeChildren:
    def __init__(self, owner: FakeNotionClient):
        self.owner = owner

    def list(self, block_id: str, **kwargs: Any) -> dict[str, Any]:
        self.owner._record("blocks.children.list", {"block_id": block_id, **kwargs})
        return self.owner.recorded["block_children"][block_id][kwargs.get("start_cursor") or START_CURSOR]


class _FakePages:
    def __init__(self, owner: FakeNotionClient):
        self.owner = owner

    def retrieve(self, page_id: str, **kwargs: Any) -> dict[str, Any]:
        self.owner._record("pages.retrieve", {"page_id": page_id})
        return self.owner.recorded["pages"][page_id]


class FakeEmbedder:
    """Records every call and returns fixed-size vectors."""

    def __init__(self, vector: list[float] | None = None):
        self.vector = vector or [1.0] * FAKE_VECTOR_SIZE
        self.document_batches: list[list[str]] = []
        self.queries: list[str] = []
        self.text_queries: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_batches.append(list(texts))
        return [list(self.vector) for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return list(self.vector)

    def embed_text(self, text: str) -> list[float]:
        self.text_queries.append(text)
        return list(self.vector)

    def embed_images(self, images: list[Any]) -> list[list[float]]:
        self.document_batches.append(list(images))
        return [list(self.vector) for _ in images]


class FakeGeminiResponse:
    def __init__(self, text: str | None):
        self.text = text


class FakeGeminiClient:
    """Mimics genai.Client: models.generate_content answers from a queue of texts or errors."""

    def __init__(self, answers: list[str | Exception]):
        self.answers = list(answers)
        self.calls: list[dict[str, Any]] = []
        self.models = self

    def generate_content(self, *, model: str, contents: Any, config: Any = None) -> FakeGeminiResponse:
        self.calls.append({"model": model, "contents": contents, "config": config})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return FakeGeminiResponse(answer)


class ScriptedRandom:
    """A random source whose choice returns the scripted values in order."""

    def __init__(self, choices: list[Any]):
        self.choices = list(choices)
        self.offered: list[list[Any]] = []

    def choice(self, options):
        self.offered.append(list(options))
        value = self.choices.pop(0)
        assert value in options
        return value
