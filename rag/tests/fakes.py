"""Test doubles shared by the test modules: no network, no real models."""

import base64
import io
import json
import threading
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
START_CURSOR = "start"
FAKE_VECTOR_SIZE = 8
DRIVE_FILES_PATH = "/drive/v3/files"
DRIVE_THUMBNAIL_HOST = "lh3.googleusercontent.com"
THUMBNAIL_SIZE_MARK = "=s"
FAKE_ACCESS_TOKEN = "test-access-token"
TMDB_SEARCH_PATH = "/3/search/movie"
TMDB_NOT_FOUND_STATUS = 404
TEST_PICTURE_SIZE = (32, 24)
TEST_PICTURE_COLOR = (40, 120, 200)


def picture_text(size: tuple[int, int] = TEST_PICTURE_SIZE, color: tuple[int, int, int] = TEST_PICTURE_COLOR) -> str:
    """A picture document's text: the Base64 of a small JPEG."""
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="JPEG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


class FakeNotionClient:
    """Answers search, block children and page calls from recorded JSON."""

    def __init__(
        self,
        recorded: dict[str, Any],
        errors: list[Exception] | None = None,
        page_errors: dict[str, Exception | list[Exception]] | None = None,
    ):
        self.recorded = recorded
        self.errors = list(errors or [])
        self.page_errors = dict(page_errors or {})
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
        error = self.owner.page_errors.get(page_id)
        if isinstance(error, list):  # one error per call while the list lasts
            error = error.pop(0) if error else None
        if error is not None:
            raise error
        return self.owner.recorded["pages"][page_id]


class FakeDriveApi:
    """Answers Drive REST calls from recorded JSON through httpx.MockTransport; pictures are bytes by file id.

    Routes: "files.list", "files.get:<id>" (folders), "media:<id>" (alt=media) and "thumbnail:<id>".
    failures[route] answers (responses or errors) are used one per call before the recorded answer.
    """

    def __init__(
        self,
        recorded: dict[str, Any],
        pictures: dict[str, bytes],
        failures: dict[str, list[httpx.Response | Exception]] | None = None,
    ):
        self.recorded = recorded
        self.pictures = pictures
        self.failures = {route: list(answers) for route, answers in (failures or {}).items()}
        self.requests: list[httpx.Request] = []
        self.routes: list[str] = []
        # The resource downloads in parallel threads.
        self._lock = threading.Lock()
        self._thumbnail_ids = {
            file["thumbnailLink"].rsplit(THUMBNAIL_SIZE_MARK, 1)[0]: file["id"]
            for page in recorded["files_list"].values()
            for file in page["files"]
            if file.get("thumbnailLink")
        }

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        route = self._route(request)
        with self._lock:
            self.requests.append(request)
            self.routes.append(route)
            answer = self.failures[route].pop(0) if self.failures.get(route) else None
        if isinstance(answer, Exception):
            raise answer
        return answer if answer is not None else self._answer(request, route)

    def _route(self, request: httpx.Request) -> str:
        if request.url.host == DRIVE_THUMBNAIL_HOST:
            return f"thumbnail:{self._thumbnail_ids[str(request.url).rsplit(THUMBNAIL_SIZE_MARK, 1)[0]]}"
        if request.url.path == DRIVE_FILES_PATH:
            return "files.list"
        file_id = request.url.path.rsplit("/", 1)[-1]
        return f"media:{file_id}" if request.url.params.get("alt") == "media" else f"files.get:{file_id}"

    def _answer(self, request: httpx.Request, route: str) -> httpx.Response:
        kind, _, file_id = route.partition(":")
        if kind == "files.list":
            return httpx.Response(200, json=self.recorded["files_list"][request.url.params.get("pageToken", START_CURSOR)])
        if kind == "files.get":
            folder = self.recorded["folders"].get(file_id)
            return httpx.Response(200, json=folder) if folder else httpx.Response(404, json=self.recorded["not_found"])
        return httpx.Response(200, content=self.pictures[file_id], headers={"Content-Type": "image/jpeg"})


class FakeTmdbApi:
    """Answers TMDB calls from recorded JSON through httpx.MockTransport.

    Routes: "search:<query>" and "movie:<id>". A query or an id that is not recorded answers TMDB's empty
    search page or its 404. failures[route] answers (responses or errors) are used one per call first.
    """

    def __init__(self, recorded: dict[str, Any], failures: dict[str, list[httpx.Response | Exception]] | None = None):
        self.recorded = recorded
        self.failures = {route: list(answers) for route, answers in (failures or {}).items()}
        self.requests: list[httpx.Request] = []
        self.routes: list[str] = []
        # The resource looks movies up in parallel threads.
        self._lock = threading.Lock()

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        route = self._route(request)
        with self._lock:
            self.requests.append(request)
            self.routes.append(route)
            answer = self.failures[route].pop(0) if self.failures.get(route) else None
        if isinstance(answer, Exception):
            raise answer
        return answer if answer is not None else self._answer(route)

    def _route(self, request: httpx.Request) -> str:
        if request.url.path == TMDB_SEARCH_PATH:
            return f"search:{request.url.params.get('query')}"
        return f"movie:{request.url.path.rsplit('/', 1)[-1]}"

    def _answer(self, route: str) -> httpx.Response:
        kind, _, key = route.partition(":")
        if kind == "search":
            return httpx.Response(200, json=self.recorded["search"].get(key, self.recorded["empty_search"]))
        movie = self.recorded["movies"].get(key)
        if movie is None:
            return httpx.Response(TMDB_NOT_FOUND_STATUS, json=self.recorded["not_found"])
        return httpx.Response(200, json=movie)


class FakeTokens:
    """An access token source that counts its uses."""

    def __init__(self, token: str = FAKE_ACCESS_TOKEN):
        self.token = token
        self.uses = 0

    def access_token(self) -> str:
        self.uses += 1
        return self.token


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


class RenameFailingClient:
    """Wraps a real Chroma client; the first rename to each of failing_names raises, later ones work."""

    def __init__(self, client: Any, failing_names: set[str] | None = None):
        self._client = client
        # The caller's set is kept, so names added later fail too.
        self.failing_names = failing_names if failing_names is not None else set()

    def get_or_create_collection(self, *args: Any, **kwargs: Any) -> "_RenameFailingCollection":
        return _RenameFailingCollection(self._client.get_or_create_collection(*args, **kwargs), self)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class _RenameFailingCollection:
    def __init__(self, collection: Any, owner: RenameFailingClient):
        self._collection = collection
        self._owner = owner

    def modify(self, name: str | None = None, **kwargs: Any) -> None:
        if name in self._owner.failing_names:
            self._owner.failing_names.discard(name)
            raise RuntimeError(f"rename to {name} failed")
        self._collection.modify(name=name, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._collection, name)
