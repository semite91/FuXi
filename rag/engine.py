"""FastAPI RAG engine. Run from /rag with: uvicorn engine:app --port 8000"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from chromadb.api import ClientAPI
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, StringConstraints

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
STATUS_UNAVAILABLE = 503
READY_STATUS = "ready"
BUILDING_STATUS = "building"
UPDATED_STATUS = "updated"
BUILDING_DETAIL = "The RAG collections are being built. Try again later."
ERROR_DETAIL = "The RAG engine could not complete the request."

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


class WordRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=MIN_NAME_LENGTH, max_length=MAX_NAME_LENGTH)]
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


class RagEngine:
    """Owns the Chroma client, the RAG client and the single running build."""

    def __init__(self, dependencies: EngineDependencies) -> None:
        self._dependencies = dependencies
        self._chroma_client: ClientAPI | None = None
        self._chroma_lock = threading.Lock()
        self._build_lock = threading.Lock()
        self._building = False
        self._build_done = threading.Event()
        self._build_done.set()
        self.rag_client = RagClient(
            self.chroma_client, dependencies.embedders, dependencies.settings, dependencies.llm_client
        )

    def chroma_client(self) -> ClientAPI:
        with self._chroma_lock:
            if self._chroma_client is None:
                self._chroma_client = self._dependencies.chroma_client_factory()
            return self._chroma_client

    def is_building(self) -> bool:
        with self._build_lock:
            return self._building

    def wait_for_build(self, timeout: float) -> bool:
        return self._build_done.wait(timeout)

    def init_rag(self) -> str:
        """Ready when the collections have data; otherwise start one background build."""
        if self.is_building():
            return BUILDING_STATUS
        if chroma_store.has_data(self.chroma_client()):
            self.rag_client.init()
            return READY_STATUS
        if self._try_start_build():
            threading.Thread(target=self._background_build, name=BUILD_THREAD_NAME, daemon=True).start()
        return BUILDING_STATUS

    def update(self) -> PipelineResult | None:
        """Rebuild every collection; None when another build is running."""
        if not self._try_start_build():
            return None
        try:
            result = self.run_pipeline(Mode.UPDATE)
            self.rag_client.refresh()
            return result
        finally:
            self._finish_build()

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
            self.run_pipeline(Mode.CREATE)
            self.rag_client.refresh()
        except Exception as error:
            logger.error("Background build failed: %s", type(error).__name__)
        finally:
            self._finish_build()

    def _try_start_build(self) -> bool:
        with self._build_lock:
            if self._building:
                return False
            self._building = True
            self._build_done.clear()
            return True

    def _finish_build(self) -> None:
        with self._build_lock:
            self._building = False
            self._build_done.set()


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
        if rag_engine.is_building():
            return _unavailable()
        words = [Word(word.name, word.translation) for word in body.words]
        results = rag_engine.rag_client.generate(words)
        return [{"name": result.name, "content": result.content} for result in results if result.content]

    @app.post(INIT_RAG_PATH)
    def init_rag() -> JSONResponse:
        status = rag_engine.init_rag()
        status_code = STATUS_OK if status == READY_STATUS else STATUS_ACCEPTED
        return JSONResponse(status_code=status_code, content={"status": status})

    @app.post(UPDATE_COLLECTIONS_PATH)
    def update_collections() -> JSONResponse:
        result = rag_engine.update()
        if result is None:
            return _unavailable()
        return JSONResponse(
            status_code=STATUS_OK,
            content={
                "status": UPDATED_STATUS,
                "documents": result.added_documents,
                "failed_resources": result.failed_resources,
            },
        )

    return app


def _unavailable() -> JSONResponse:
    return JSONResponse(status_code=STATUS_UNAVAILABLE, content={"detail": BUILDING_DETAIL})


app = create_app()
