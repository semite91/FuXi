import logging
import threading
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

import engine
from base import Document, Resource, ResourceKind
from embedding_pipeline import Embedders
from engine import BUILD_WAIT_SECONDS, MAX_NAME_LENGTH, EngineDependencies, create_app
from fakes import FakeEmbedder, RenameFailingClient
from chroma_store import TEXT_COLLECTION_NAME, create_chroma_client, is_build_complete, open_collection
from resources.notion_resource import create_notion_resource
from settings import Settings

ALLOWED_ORIGIN = "http://localhost:5173"
SECRET = "super-secret-test-key"
POLL_SECONDS = 0.01
SECONDS_PER_MINUTE = 60
WORDS_BODY = {"words": [{"name": "serendipity", "translation": "şans"}, {"name": "gloomy", "translation": "kasvetli"}]}


class NotesResource(Resource):
    name = "notion"
    kind = ResourceKind.TEXT

    def __init__(self, gate: threading.Event | None = None, events: list[str] | None = None):
        self.gate = gate
        self.reads = 0
        self.count = 1
        self.error: Exception | None = None
        self.events = events if events is not None else []

    def read_documents(self):
        self.reads += 1
        self.events.append("resource read")
        if self.gate is not None:
            self.gate.wait(BUILD_WAIT_SECONDS)
        if self.error is not None:
            raise self.error
        return [Document(f"note {self.reads}", {"name": "Notes"}) for _ in range(self.count)]


class FakeLlm:
    def __init__(self, contents=None, error=None):
        self.contents = contents or {}
        self.error = error
        self.words: list[str] = []
        self.pairs: list[tuple[str, str]] = []

    def build_search_query(self, word, meaning):
        self.words.append(word)
        self.pairs.append((word, meaning))
        return word

    def generate(self, word, meaning, text_results, image_results):
        if self.error:
            raise self.error
        return self.contents.get((word, meaning), self.contents.get(word))


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class BlockingLlm(FakeLlm):
    """Holds the first GetWordContent request inside the engine until released."""

    def __init__(self, events: list[str]):
        super().__init__({"serendipity": "content"})
        self.events = events
        self.entered = threading.Event()
        self.release = threading.Event()

    def build_search_query(self, word, meaning):
        if not self.entered.is_set():
            self.entered.set()
            assert self.release.wait(BUILD_WAIT_SECONDS)
        return super().build_search_query(word, meaning)

    def generate(self, word, meaning, text_results, image_results):
        self.events.append(f"content {word}")
        return super().generate(word, meaning, text_results, image_results)


def wait_until(condition: Callable[[], bool]) -> None:
    waiter = threading.Event()
    for _ in range(int(BUILD_WAIT_SECONDS / POLL_SECONDS)):
        if condition():
            return
        waiter.wait(POLL_SECONDS)
    raise AssertionError("condition not reached")


def in_thread(call: Callable[[], object]) -> tuple[threading.Thread, list]:
    answers: list = []
    thread = threading.Thread(target=lambda: answers.append(call()), daemon=True)
    thread.start()
    return thread, answers


class Harness:
    def __init__(
        self, tmp_path, resource=None, llm=None, settings=None, resource_factory=None, clock=None, failing_renames=None
    ):
        self.resource = resource or NotesResource()
        self.factory_calls = 0
        self.chroma_path = tmp_path / "chroma"
        self.failing_renames = failing_renames if failing_renames is not None else set()

        def resources(_settings):
            self.factory_calls += 1
            return [self.resource]

        self.dependencies = EngineDependencies(
            settings=settings or Settings(cors_origins=(ALLOWED_ORIGIN,)),
            chroma_client_factory=lambda: RenameFailingClient(
                create_chroma_client(self.chroma_path), self.failing_renames
            ),
            embedders=Embedders(text=FakeEmbedder(), image=FakeEmbedder()),
            resource_factory=resource_factory or resources,
            llm_client=llm or FakeLlm(),
            logs_dir=tmp_path / "logs",
            **({"clock": clock} if clock is not None else {}),
        )
        self.app = create_app(self.dependencies)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def wait_for_build(self):
        assert self.app.state.engine.wait_for_build(BUILD_WAIT_SECONDS)

    def build_ready(self):
        assert self.client.post("/Init_RAG").status_code == 202
        self.wait_for_build()

    def stored_documents(self):
        return open_collection(create_chroma_client(self.chroma_path), TEXT_COLLECTION_NAME).get()["documents"]


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
    assert answer.json() == [
        {"name": "serendipity", "translation": "şans", "content": '{"method":"story","title":"t","content":"c"}'}
    ]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"words": []},
        {"words": [{"name": "", "translation": "x"}]},
        {"words": [{"name": "   ", "translation": "x"}]},
        {"words": [{"name": "a"}]},
        {"words": [{"name": f"w{index}", "translation": ""} for index in range(51)]},
        {"words": [{"name": "a" * (MAX_NAME_LENGTH + 1), "translation": "x"}]},
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


def test_failed_update_keeps_the_old_collections_and_answers_an_error(tmp_path):
    # E10
    harness = Harness(tmp_path)
    harness.build_ready()
    harness.resource.error = RuntimeError(SECRET)

    answer = harness.client.post("/Update_Collections")

    assert answer.status_code == 502
    assert answer.json() == {"detail": "The RAG collections could not be updated. The old collections are kept."}
    assert SECRET not in answer.text
    assert harness.stored_documents() == ["note 1"]
    assert harness.client.post("/Init_RAG").json() == {"status": "ready"}


def test_update_with_zero_documents_keeps_the_old_collections(tmp_path):
    # E11
    harness = Harness(tmp_path)
    harness.build_ready()
    harness.resource.count = 0

    answer = harness.client.post("/Update_Collections")

    assert answer.status_code == 502
    assert harness.stored_documents() == ["note 1"]


def test_update_waits_for_content_in_flight_and_new_content_requests_answer_503(tmp_path):
    # H12
    events: list[str] = []
    llm = BlockingLlm(events)
    harness = Harness(tmp_path, resource=NotesResource(events=events), llm=llm)
    harness.build_ready()
    events.clear()
    reader, reader_answers = in_thread(lambda: harness.client.post("/GetWordContent", json=WORDS_BODY))
    assert llm.entered.wait(BUILD_WAIT_SECONDS)

    writer, writer_answers = in_thread(lambda: harness.client.post("/Update_Collections"))
    wait_until(harness.app.state.engine.is_building)
    refused = harness.client.post("/GetWordContent", json=WORDS_BODY)
    reads_while_reader_runs = harness.resource.reads
    llm.release.set()
    reader.join(BUILD_WAIT_SECONDS)
    writer.join(BUILD_WAIT_SECONDS)

    assert refused.status_code == 503
    assert reads_while_reader_runs == 1  # the update has not read yet
    assert reader_answers[0].status_code == 200
    assert writer_answers[0].status_code == 200
    assert events == ["content serendipity", "content gloomy", "resource read"]


def test_init_build_waits_for_content_in_flight(tmp_path):
    # H12
    events: list[str] = []
    llm = BlockingLlm(events)
    harness = Harness(tmp_path, resource=NotesResource(events=events), llm=llm)
    reader, _ = in_thread(lambda: harness.client.post("/GetWordContent", json=WORDS_BODY))
    assert llm.entered.wait(BUILD_WAIT_SECONDS)

    init = harness.client.post("/Init_RAG")
    refused = harness.client.post("/GetWordContent", json=WORDS_BODY)
    reads_while_reader_runs = harness.resource.reads
    llm.release.set()
    reader.join(BUILD_WAIT_SECONDS)
    harness.wait_for_build()

    assert init.status_code == 202
    assert refused.status_code == 503
    assert reads_while_reader_runs == 0
    assert events == ["content serendipity", "content gloomy", "resource read"]


def test_build_that_stopped_partway_is_started_again_from_empty(tmp_path):
    # H13
    harness = Harness(tmp_path)
    partial = open_collection(create_chroma_client(harness.chroma_path), TEXT_COLLECTION_NAME)
    partial.add(ids=["partial"], documents=["half-built note"], embeddings=[[1.0] * 8])

    answer = harness.client.post("/Init_RAG")
    harness.wait_for_build()

    assert answer.status_code == 202
    assert harness.factory_calls == 1
    assert harness.stored_documents() == ["note 1"]
    assert is_build_complete(create_chroma_client(harness.chroma_path))
    assert harness.client.post("/Init_RAG").json() == {"status": "ready"}


@pytest.mark.parametrize("failure", ["zero documents", "failed resource"])
def test_empty_build_is_not_started_again_in_the_same_run(tmp_path, failure):
    # H14
    harness = Harness(tmp_path)
    if failure == "zero documents":
        harness.resource.count = 0
    else:
        harness.resource.error = RuntimeError("source is down")
    harness.build_ready()

    again = harness.client.post("/Init_RAG")

    assert again.status_code == 200
    assert again.json() == {"status": "empty"}
    assert harness.factory_calls == 1


def test_update_after_an_empty_build_allows_ready_again(tmp_path):
    # H14
    harness = Harness(tmp_path)
    harness.resource.count = 0
    harness.build_ready()
    harness.resource.count = 1

    assert harness.client.post("/Update_Collections").status_code == 200
    assert harness.client.post("/Init_RAG").json() == {"status": "ready"}


def test_name_is_returned_exactly_as_sent(tmp_path):
    # H15
    llm = FakeLlm({"gloomy": '{"method":"story","title":"t","content":"c"}'})
    harness = Harness(tmp_path, llm=llm)
    harness.build_ready()

    answer = harness.client.post("/GetWordContent", json={"words": [{"name": "gloomy ", "translation": "kasvetli"}]})

    assert answer.json() == [
        {"name": "gloomy ", "translation": "kasvetli", "content": '{"method":"story","title":"t","content":"c"}'}
    ]
    assert llm.words == ["gloomy"]


def test_duplicate_names_are_generated_and_returned_once(tmp_path):
    # H15
    llm = FakeLlm({"gloomy": "content"})
    harness = Harness(tmp_path, llm=llm)
    harness.build_ready()
    word = {"name": "gloomy", "translation": "kasvetli"}

    answer = harness.client.post("/GetWordContent", json={"words": [word, word]})

    assert answer.json() == [{"name": "gloomy", "translation": "kasvetli", "content": "content"}]
    assert llm.words == ["gloomy"]


def test_failed_create_build_keeps_the_existing_collections(tmp_path):
    # E12
    harness = Harness(tmp_path)
    existing = open_collection(create_chroma_client(harness.chroma_path), TEXT_COLLECTION_NAME)
    existing.add(ids=["existing"], documents=["existing note"], embeddings=[[1.0] * 8])
    harness.resource.error = RuntimeError("source is down")

    harness.build_ready()

    assert harness.stored_documents() == ["existing note"]
    assert harness.client.post("/Init_RAG").json() == {"status": "empty"}


def test_failed_rename_during_update_restores_the_old_collections_and_answers_an_error(tmp_path):
    # E13
    harness = Harness(tmp_path)
    harness.build_ready()
    harness.failing_renames.add(TEXT_COLLECTION_NAME)

    answer = harness.client.post("/Update_Collections")

    assert answer.status_code == 500
    assert answer.json() == {"detail": "The RAG engine could not complete the request."}
    assert harness.stored_documents() == ["note 1"]
    assert harness.client.post("/Init_RAG").json() == {"status": "ready"}
    texts, _ = harness.app.state.engine.rag_client.retrieve("q")
    assert [item.document for item in texts] == ["note 1"]


def failing_refresh():
    raise RuntimeError("refresh broke")


def test_refresh_failure_after_a_successful_update_is_logged_and_answers_200(tmp_path, caplog):
    # H16
    harness = Harness(tmp_path)
    harness.build_ready()
    harness.app.state.engine.rag_client.refresh = failing_refresh

    with caplog.at_level(logging.ERROR, logger="engine"):
        answer = harness.client.post("/Update_Collections")

    assert answer.status_code == 200
    assert answer.json()["status"] == "updated"
    assert "RAG client refresh failed: RuntimeError" in caplog.text


def test_refresh_failure_does_not_hide_the_builds_own_error(tmp_path):
    # H16
    harness = Harness(tmp_path)
    engine_under_test = harness.app.state.engine
    engine_under_test.rag_client.refresh = failing_refresh
    engine_under_test.run_pipeline = lambda mode: (_ for _ in ()).throw(ValueError("build broke"))

    with pytest.raises(ValueError, match="build broke"):
        engine_under_test.update()
    assert engine_under_test.is_building() is False


def test_same_name_with_different_translations_is_generated_and_answered_separately(tmp_path):
    # H17
    llm = FakeLlm({("bank", "banka"): "money content", ("bank", "kıyı"): "river content"})
    harness = Harness(tmp_path, llm=llm)
    harness.build_ready()
    body = {"words": [{"name": "bank", "translation": "banka"}, {"name": "bank", "translation": "kıyı"}]}

    answer = harness.client.post("/GetWordContent", json=body)

    assert answer.json() == [
        {"name": "bank", "translation": "banka", "content": "money content"},
        {"name": "bank", "translation": "kıyı", "content": "river content"},
    ]
    assert llm.pairs == [("bank", "banka"), ("bank", "kıyı")]


def test_translation_is_echoed_exactly_as_sent(tmp_path):
    # H17
    llm = FakeLlm({("bank", "Banka"): "money content"})
    harness = Harness(tmp_path, llm=llm)
    harness.build_ready()
    body = {"words": [{"name": "bank", "translation": " Banka "}]}

    answer = harness.client.post("/GetWordContent", json=body)

    assert answer.json() == [{"name": "bank", "translation": " Banka ", "content": "money content"}]
    assert llm.pairs == [("bank", "Banka")]


def test_failed_build_is_retried_only_after_the_cooldown(tmp_path):
    # H18
    clock = FakeClock()
    harness = Harness(tmp_path, settings=Settings(rebuild_cooldown_minutes=10), clock=clock)
    harness.resource.count = 0
    harness.build_ready()

    clock.now += 10 * SECONDS_PER_MINUTE - 1
    before = harness.client.post("/Init_RAG")
    clock.now += 1
    harness.resource.count = 1
    after = harness.client.post("/Init_RAG")
    harness.wait_for_build()

    assert (before.status_code, before.json()) == (200, {"status": "empty"})
    assert (after.status_code, after.json()) == (202, {"status": "building"})
    assert harness.factory_calls == 2
    assert harness.client.post("/Init_RAG").json() == {"status": "ready"}


def test_zero_cooldown_starts_a_new_build_at_once(tmp_path):
    # H18
    harness = Harness(tmp_path, settings=Settings(rebuild_cooldown_minutes=0), clock=FakeClock())
    harness.resource.count = 0
    harness.build_ready()

    assert harness.client.post("/Init_RAG").status_code == 202
    harness.wait_for_build()
    assert harness.factory_calls == 2


def test_names_differing_only_by_spaces_are_generated_once_and_both_answered(tmp_path):
    # H19
    llm = FakeLlm({"Ephemeral": "content"})
    harness = Harness(tmp_path, llm=llm)
    harness.build_ready()
    body = {"words": [
        {"name": "Ephemeral", "translation": "geçici"},
        {"name": "Ephemeral ", "translation": "geçici"},
    ]}

    answer = harness.client.post("/GetWordContent", json=body)

    assert answer.json() == [
        {"name": "Ephemeral", "translation": "geçici", "content": "content"},
        {"name": "Ephemeral ", "translation": "geçici", "content": "content"},
    ]
    assert llm.words == ["Ephemeral"]


def test_name_length_is_checked_after_trimming(tmp_path):
    # H19
    name = "a" * MAX_NAME_LENGTH
    harness = Harness(tmp_path, llm=FakeLlm({name: "content"}))
    harness.build_ready()

    answer = harness.client.post("/GetWordContent", json={"words": [{"name": f"  {name}  ", "translation": "x"}]})

    assert answer.status_code == 200
    assert answer.json() == [{"name": f"  {name}  ", "translation": "x", "content": "content"}]
