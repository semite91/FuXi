import threading

import pytest
from fastapi.testclient import TestClient

import engine
from base import Document, Resource, ResourceKind
from embedding_pipeline import Embedders
from engine import BUILD_WAIT_SECONDS, EngineDependencies, create_app
from fakes import FakeEmbedder
from chroma_store import create_chroma_client
from resources.notion_resource import create_notion_resource
from settings import Settings

ALLOWED_ORIGIN = "http://localhost:5173"
SECRET = "super-secret-test-key"
WORDS_BODY = {"words": [{"name": "serendipity", "translation": "şans"}, {"name": "gloomy", "translation": "kasvetli"}]}


class NotesResource(Resource):
    name = "notion"
    kind = ResourceKind.TEXT

    def __init__(self, gate: threading.Event | None = None):
        self.gate = gate
        self.reads = 0

    def read_documents(self):
        self.reads += 1
        if self.gate is not None:
            self.gate.wait(BUILD_WAIT_SECONDS)
        return [Document(f"note {self.reads}", {"name": "Notes"})]


class FakeLlm:
    def __init__(self, contents=None, error=None):
        self.contents = contents or {}
        self.error = error

    def build_search_query(self, word, meaning):
        return word

    def generate(self, word, meaning, text_results, image_results):
        if self.error:
            raise self.error
        return self.contents.get(word)


class Harness:
    def __init__(self, tmp_path, resource=None, llm=None, settings=None, resource_factory=None):
        self.resource = resource or NotesResource()
        self.factory_calls = 0
        self.chroma_path = tmp_path / "chroma"

        def resources(_settings):
            self.factory_calls += 1
            return [self.resource]

        self.dependencies = EngineDependencies(
            settings=settings or Settings(cors_origins=(ALLOWED_ORIGIN,)),
            chroma_client_factory=lambda: create_chroma_client(self.chroma_path),
            embedders=Embedders(text=FakeEmbedder(), image=FakeEmbedder()),
            resource_factory=resource_factory or resources,
            llm_client=llm or FakeLlm(),
            logs_dir=tmp_path / "logs",
        )
        self.app = create_app(self.dependencies)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def wait_for_build(self):
        assert self.app.state.engine.wait_for_build(BUILD_WAIT_SECONDS)

    def build_ready(self):
        assert self.client.post("/Init_RAG").status_code == 202
        self.wait_for_build()


def test_routes_exist():
    # H1
    routes = {(route.path, method) for route in engine.app.routes for method in getattr(route, "methods", ())}

    assert {("/GetWordContent", "POST"), ("/Init_RAG", "POST"), ("/Update_Collections", "POST")} <= routes


def test_get_word_content_returns_only_words_with_content(tmp_path):
    # H2
    harness = Harness(tmp_path, llm=FakeLlm({"serendipity": '{"method":"story","title":"t","content":"c"}'}))
    harness.build_ready()

    answer = harness.client.post("/GetWordContent", json=WORDS_BODY)

    assert answer.status_code == 200
    assert answer.json() == [{"name": "serendipity", "content": '{"method":"story","title":"t","content":"c"}'}]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"words": []},
        {"words": [{"name": "", "translation": "x"}]},
        {"words": [{"name": "   ", "translation": "x"}]},
        {"words": [{"name": "a"}]},
        {"words": [{"name": f"w{index}", "translation": ""} for index in range(51)]},
    ],
)
def test_invalid_body_is_rejected(tmp_path, body):
    # H3
    assert Harness(tmp_path).client.post("/GetWordContent", json=body).status_code == 422


def test_fifty_words_and_empty_translation_are_accepted(tmp_path):
    # H3
    body = {"words": [{"name": f"w{index}", "translation": ""} for index in range(50)]}

    assert Harness(tmp_path).client.post("/GetWordContent", json=body).status_code == 200


def test_init_on_empty_collections_starts_one_background_build(tmp_path):
    # H4
    harness = Harness(tmp_path)

    answer = harness.client.post("/Init_RAG")

    assert answer.status_code == 202
    assert answer.json() == {"status": "building"}
    harness.wait_for_build()
    assert harness.factory_calls == 1
    assert harness.client.post("/Init_RAG").json() == {"status": "ready"}


def test_running_build_answers_building_and_blocks_other_calls(tmp_path):
    # H5 H7 H9
    gate = threading.Event()
    harness = Harness(tmp_path, resource=NotesResource(gate))

    first = harness.client.post("/Init_RAG")
    second = harness.client.post("/Init_RAG")
    content = harness.client.post("/GetWordContent", json=WORDS_BODY)
    update = harness.client.post("/Update_Collections")
    gate.set()
    harness.wait_for_build()

    assert (first.status_code, second.status_code) == (202, 202)
    assert second.json() == {"status": "building"}
    assert harness.factory_calls == 1
    assert content.status_code == 503
    assert update.status_code == 503
    assert "Traceback" not in content.text


def test_init_with_data_is_ready_and_builds_nothing(tmp_path):
    # H6
    harness = Harness(tmp_path)
    harness.build_ready()

    answer = harness.client.post("/Init_RAG")

    assert answer.status_code == 200
    assert answer.json() == {"status": "ready"}
    assert harness.factory_calls == 1


def test_update_rebuilds_and_answers_when_done(tmp_path):
    # H8
    harness = Harness(tmp_path)
    harness.build_ready()

    answer = harness.client.post("/Update_Collections")

    assert answer.status_code == 200
    assert answer.json() == {"status": "updated", "documents": 1, "failed_resources": []}
    assert harness.factory_calls == 2
    texts, _ = harness.app.state.engine.rag_client.retrieve("q")
    assert [item.document for item in texts] == ["note 2"]  # the singleton reads the new collection


def test_cors_allows_only_configured_origins(tmp_path):
    # H10
    client = Harness(tmp_path).client
    preflight = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Content-Type"}

    allowed = client.options("/GetWordContent", headers={"Origin": ALLOWED_ORIGIN, **preflight})
    denied = client.options("/GetWordContent", headers={"Origin": "https://evil.example", **preflight})

    assert allowed.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "POST" in allowed.headers["access-control-allow-methods"]
    assert "access-control-allow-origin" not in denied.headers


def test_engine_error_hides_stack_trace_and_secret(tmp_path):
    # H11
    harness = Harness(tmp_path, llm=FakeLlm(error=RuntimeError(f"api_key={SECRET}")))
    harness.app.state.engine.rag_client.generate = lambda words: (_ for _ in ()).throw(RuntimeError(SECRET))

    answer = harness.client.post("/GetWordContent", json=WORDS_BODY)

    assert answer.status_code == 500
    assert SECRET not in answer.text
    assert "Traceback" not in answer.text
    assert answer.json() == {"detail": "The RAG engine could not complete the request."}


def test_failed_update_hides_details_and_frees_the_build(tmp_path):
    # H11
    harness = Harness(tmp_path)
    harness.app.state.engine.run_pipeline = lambda mode: (_ for _ in ()).throw(RuntimeError(SECRET))

    answer = harness.client.post("/Update_Collections")

    assert answer.status_code == 500
    assert SECRET not in answer.text
    assert harness.app.state.engine.is_building() is False


def test_engine_starts_without_secrets_and_names_the_missing_key(tmp_path):
    # B5
    harness = Harness(tmp_path, settings=Settings(), resource_factory=lambda settings: [create_notion_resource(settings)])

    assert harness.client.post("/Init_RAG").status_code == 202
    harness.wait_for_build()

    log = "".join(path.read_text(encoding="utf-8") for path in (tmp_path / "logs").iterdir())
    assert "RAG_NOTION_TOKEN is not set" in log
