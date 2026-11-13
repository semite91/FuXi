"""FastAPI RAG engine. Run from /rag with: uvicorn engine:app --port 8000"""

import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from chromadb.api import ClientAPI
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, Field, StringConstraints

import chroma_store
from base import Resource
from embedders import ImageEmbedder, TextEmbedder
from embedding_pipeline import DEFAULT_LOGS_DIR, Embedders, Mode, PipelineResult, run
from llm_client import LlmClient
from rag_client import RagClient, Word
from resources.notion_resource import create_notion_resource
from settings import Settings, load_settings

GET_WORD_CONTENT_PATH = "/GetWordContent"
INIT_RAG_PATH = "/Init_RAG"
UPDATE_COLLECTIONS_PATH = "/Update_Collections"

STATUS_OK = 200
STATUS_ACCEPTED = 202
STATUS_SERVER_ERROR = 500
STATUS_BAD_GATEWAY = 502
STATUS_UNAVAILABLE = 503
READY_STATUS = "ready"
BUILDING_STATUS = "building"
EMPTY_STATUS = "empty"
UPDATED_STATUS = "updated"
BUILDING_DETAIL = "The RAG collections are being built. Try again later."
ERROR_DETAIL = "The RAG engine could not complete the request."
UPDATE_FAILED_DETAIL = "The RAG collections could not be updated. The old collections are kept."
BLANK_NAME_MESSAGE = "name must not be blank"

MIN_WORDS = 1
MAX_WORDS = 50
MIN_NAME_LENGTH = 1
MAX_NAME_LENGTH = 200
MAX_TRANSLATION_LENGTH = 1000
CORS_METHODS = ["POST"]
CORS_HEADERS = ["Content-Type"]
BUILD_WAIT_SECONDS = 30.0
BUILD_THREAD_NAME = "rag-build"

logger = logging.getLogger(__name__)

ResourceFactory = Callable[[Settings], list[Resource]]


def _require_text(value: str) -> str:
    """Rejects a blank name but keeps the name exactly as sent."""
    if not value.strip():
        raise ValueError(BLANK_NAME_MESSAGE)
    return value


class WordRequest(BaseModel):
    name: Annotated[
        str,
        StringConstraints(min_length=MIN_NAME_LENGTH, max_length=MAX_NAME_LENGTH),
        AfterValidator(_require_text),
    ]
    translation: Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_TRANSLATION_LENGTH)]


class GetWordContentRequest(BaseModel):
    words: list[WordRequest] = Field(min_length=MIN_WORDS, max_length=MAX_WORDS)


class WordContentResponse(BaseModel):
    name: str
    content: str


@dataclass
class EngineDependencies:
    """Every seam tests replace: settings, Chroma, embedders, resources and Gemini."""

    settings: Settings
    chroma_client_factory: Callable[[], ClientAPI]
    embedders: Embedders
    resource_factory: ResourceFactory
    llm_client: Any
    logs_dir: Path = DEFAULT_LOGS_DIR


def default_resources(settings: Settings) -> list[Resource]:
    return [create_notion_resource(settings)]


def default_dependencies(settings: Settings | None = None) -> EngineDependencies:
    settings = settings or load_settings()
    return EngineDependencies(
        settings=settings,
        chroma_client_factory=chroma_store.create_chroma_client,
        embedders=Embedders(text=TextEmbedder(), image=ImageEmbedder()),
        resource_factory=default_resources,
        llm_client=LlmClient(settings),
    )


class ReadWriteGuard:
    """GetWordContent requests read together; a build or update writes alone.

    A writer turns new readers away at once and then waits until the running readers finish.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._readers = 0
        self._writing = False
        self._idle = threading.Event()
        self._idle.set()

    def try_start_reading(self) -> bool:
        with self._condition:
            if self._writing:
                return False
            self._readers += 1
            return True

    def stop_reading(self) -> None:
        with self._condition:
            self._readers -= 1
            self._condition.notify_all()

    def try_start_writing(self) -> bool:
        with self._condition:
            if self._writing:
                return False
            self._writing = True
            self._idle.clear()
            return True

    def wait_for_readers(self) -> None:
        with self._condition:
            self._condition.wait_for(lambda: self._readers == 0)

    def stop_writing(self) -> None:
        with self._condition:
            self._writing = False
            self._idle.set()
            self._condition.notify_all()

    def is_writing(self) -> bool:
        with self._condition:
            return self._writing

    def wait_until_idle(self, timeout: float) -> bool:
        return self._idle.wait(timeout)


class RagEngine:
    """Owns the Chroma client, the RAG client, the single running build and the last build's outcome."""

    def __init__(self, dependencies: EngineDependencies) -> None:
        self._dependencies = dependencies
        self._chroma_client: ClientAPI | None = None
        self._chroma_lock = threading.Lock()
        self._guard = ReadWriteGuard()
        # True after a build or update of this process ended with 0 documents or a failed resource.
        self._last_build_failed = False
        self.rag_client = RagClient(
            self.chroma_client, dependencies.embedders, dependencies.settings, dependencies.llm_client
        )

    def chroma_client(self) -> ClientAPI:
        with self._chroma_lock:
            if self._chroma_client is None:
                self._chroma_client = self._dependencies.chroma_client_factory()
            return self._chroma_client

    def is_building(self) -> bool:
        return self._guard.is_writing()

    def wait_for_build(self, timeout: float) -> bool:
        return self._guard.wait_until_idle(timeout)

    @contextmanager
    def reading(self) -> Iterator[bool]:
        """Yields False when a build or update runs or waits; the request then answers 503."""
        allowed = self._guard.try_start_reading()
        try:
            yield allowed
        finally:
            if allowed:
                self._guard.stop_reading()

    def init_rag(self) -> str:
        """Ready when the last build completed; empty when this run's build failed; otherwise start one build."""
        if self.is_building():
            return BUILDING_STATUS
        if chroma_store.is_build_complete(self.chroma_client()):
            self.rag_client.init()
            return READY_STATUS
        if self._last_build_failed:
            return EMPTY_STATUS
        if self._guard.try_start_writing():
            threading.Thread(target=self._background_build, name=BUILD_THREAD_NAME, daemon=True).start()
        return BUILDING_STATUS

    def update(self) -> PipelineResult | None:
        """Rebuild every collection; None when another build is running."""
        if not self._guard.try_start_writing():
            return None
        try:
            return self._build(Mode.UPDATE)
        finally:
            self._guard.stop_writing()

    def run_pipeline(self, mode: Mode) -> PipelineResult:
        dependencies = self._dependencies
        return run(
            mode,
            resources=dependencies.resource_factory(dependencies.settings),
            embedders=dependencies.embedders,
            chroma_client=self.chroma_client(),
            batch_size=dependencies.settings.batch_size,
            logs_dir=dependencies.logs_dir,
        )

    def _background_build(self) -> None:
        try:
            self._build(Mode.CREATE)
        except Exception as error:
            logger.error("Background build failed: %s", type(error).__name__)
        finally:
            self._guard.stop_writing()

    def _build(self, mode: Mode) -> PipelineResult:
        """Runs once no GetWordContent request is in flight; a create starts from empty collections."""
        self._guard.wait_for_readers()
        self._last_build_failed = True
        try:
            if mode is Mode.CREATE:
                chroma_store.delete_all_collections(self.chroma_client())
            result = self.run_pipeline(mode)
            self._last_build_failed = not result.complete
            return result
        finally:
            self.rag_client.refresh()


def create_app(dependencies: EngineDependencies | None = None) -> FastAPI:
    dependencies = dependencies or default_dependencies()
    rag_engine = RagEngine(dependencies)
    app = FastAPI(title="FuXi RAG engine")
    app.state.engine = rag_engine
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(dependencies.settings.cors_origins),
        allow_methods=CORS_METHODS,
        allow_headers=CORS_HEADERS,
    )

    @app.exception_handler(Exception)
    async def hide_errors(_request: Request, error: Exception) -> JSONResponse:
        logger.error("Request failed: %s", type(error).__name__)
        return JSONResponse(status_code=STATUS_SERVER_ERROR, content={"detail": ERROR_DETAIL})

    # Sync handlers run in FastAPI's worker threads, so builds never block the event loop.
    @app.post(GET_WORD_CONTENT_PATH, response_model=list[WordContentResponse])
    def get_word_content(body: GetWordContentRequest) -> Any:
        with rag_engine.reading() as allowed:
            if not allowed:
                return _unavailable()
            return _generate_contents(rag_engine.rag_client, body.words)

    @app.post(INIT_RAG_PATH)
    def init_rag() -> JSONResponse:
        status = rag_engine.init_rag()
        status_code = STATUS_ACCEPTED if status == BUILDING_STATUS else STATUS_OK
        return JSONResponse(status_code=status_code, content={"status": status})

    @app.post(UPDATE_COLLECTIONS_PATH)
    def update_collections() -> JSONResponse:
        result = rag_engine.update()
        if result is None:
            return _unavailable()
        if not result.complete:
            return JSONResponse(status_code=STATUS_BAD_GATEWAY, content={"detail": UPDATE_FAILED_DETAIL})
        return JSONResponse(
            status_code=STATUS_OK,
            content={
                "status": UPDATED_STATUS,
                "documents": result.added_documents,
                "failed_resources": result.failed_resources,
            },
        )

    return app


def _generate_contents(rag_client: RagClient, words: list[WordRequest]) -> list[dict[str, str]]:
    """Each name once, generated from its trimmed form and answered exactly as sent."""
    unique_words: dict[str, WordRequest] = {}
    for word in words:
        unique_words.setdefault(word.name, word)
    results = rag_client.generate([Word(word.name.strip(), word.translation) for word in unique_words.values()])
    return [
        {"name": name, "content": result.content}
        for name, result in zip(unique_words, results)
        if result.content
    ]


def _unavailable() -> JSONResponse:
    return JSONResponse(status_code=STATUS_UNAVAILABLE, content={"detail": BUILDING_DETAIL})


app = create_app()
