import base64
import uuid
from datetime import datetime
from pathlib import Path

import httpx
import pytest

import chroma_store
from base import Document, Resource, ResourceKind
from chroma_store import (
    DEFAULT_CHROMA_PATH,
    IMAGE_COLLECTION_NAME,
    TEXT_COLLECTION_NAME,
    create_chroma_client,
    is_build_complete,
    open_collection,
)
from embedding_pipeline import Embedders, Mode, run
from fakes import (
    FIXTURES_DIR,
    TEST_PICTURE_SIZE,
    FakeDriveApi,
    FakeEmbedder,
    FakeNotionClient,
    FakeTmdbApi,
    FakeTokens,
    RenameFailingClient,
    load_fixture,
    picture_text,
)
from resources.google_drive_resource import GoogleDriveResource
from resources.letterboxd_tmdb_resource import LetterboxdTmdbResource
from resources.notion_resource import NotionResource

FIXED_TIME = datetime(2026, 11, 13, 9, 5, 42)
LOG_FILE_NAME = "2026_11_13_09_05.txt"


class ListResource(Resource):
    kind = ResourceKind.TEXT

    def __init__(self, name: str, count: int, kind: ResourceKind = ResourceKind.TEXT):
        self.name = name
        self.kind = kind
        self.count = count

    def read_documents(self) -> list[Document]:
        return [
            Document(f"{self.name} note {index}", {"name": f"{self.name}-{index}", "type": "text"})
            for index in range(self.count)
        ]


class PictureResource(Resource):
    name = "google_drive"
    kind = ResourceKind.IMAGE

    def __init__(self, count: int, broken_name: str | None = None):
        self.count = count
        self.broken_name = broken_name

    def read_documents(self) -> list[Document]:
        documents = [
            Document(picture_text(), {"name": f"photo-{index}.jpg", "type": "picture"}) for index in range(self.count)
        ]
        if self.broken_name:
            documents.append(Document("not a picture", {"name": self.broken_name, "type": "picture"}))
        return documents


class FailingResource(Resource):
    name = "broken"
    kind = ResourceKind.TEXT

    def read_documents(self) -> list[Document]:
        raise RuntimeError("source is down")


@pytest.fixture
def chroma_client(tmp_path):
    return create_chroma_client(tmp_path / "chroma")


@pytest.fixture
def embedders():
    return Embedders(text=FakeEmbedder(), image=FakeEmbedder([0.5] * 8))


def run_pipeline(mode, resources, chroma_client, embedders, logs_dir: Path, batch_size=16):
    return run(
        mode,
        resources=resources,
        embedders=embedders,
        chroma_client=chroma_client,
        batch_size=batch_size,
        logs_dir=logs_dir,
        clock=lambda: FIXED_TIME,
    )


def test_documents_are_embedded_in_batches(chroma_client, embedders, tmp_path):
    # E1
    run_pipeline(Mode.CREATE, [ListResource("notion", 40)], chroma_client, embedders, tmp_path)

    assert [len(batch) for batch in embedders.text.document_batches] == [16, 16, 8]
    assert open_collection(chroma_client, TEXT_COLLECTION_NAME).count() == 40


def test_each_document_gets_a_new_unique_guid(chroma_client, embedders, tmp_path):
    # E2
    run_pipeline(Mode.CREATE, [ListResource("notion", 20)], chroma_client, embedders, tmp_path)
    first_ids = open_collection(chroma_client, TEXT_COLLECTION_NAME).get()["ids"]
    run_pipeline(Mode.CREATE, [ListResource("notion", 20)], chroma_client, embedders, tmp_path)

    ids = open_collection(chroma_client, TEXT_COLLECTION_NAME).get()["ids"]
    assert len(ids) == len(set(ids)) == 20
    assert set(ids).isdisjoint(first_ids)  # the same documents get new ids in a new build
    assert all(uuid.UUID(item).version == 4 for item in ids + first_ids)


def test_text_document_goes_to_the_text_collection_together(chroma_client, embedders, tmp_path):
    # E3
    run_pipeline(Mode.CREATE, [ListResource("notion", 2)], chroma_client, embedders, tmp_path)

    stored = open_collection(chroma_client, TEXT_COLLECTION_NAME).get(
        include=["documents", "metadatas", "embeddings"]
    )
    by_document = dict(zip(stored["documents"], stored["metadatas"]))
    assert by_document == {
        "notion note 0": {"name": "notion-0", "type": "text"},
        "notion note 1": {"name": "notion-1", "type": "text"},
    }
    assert [list(vector) for vector in stored["embeddings"]] == [pytest.approx([1.0] * 8)] * 2
    assert open_collection(chroma_client, IMAGE_COLLECTION_NAME).count() == 0


def test_image_documents_go_to_the_image_collection(chroma_client, embedders, tmp_path):
    # E3
    resource = PictureResource(3)

    run_pipeline(Mode.CREATE, [resource], chroma_client, embedders, tmp_path)

    assert len(embedders.image.document_batches) == 1
    assert embedders.text.document_batches == []
    assert open_collection(chroma_client, IMAGE_COLLECTION_NAME).count() == 3


def test_collections_use_cosine_space(chroma_client, embedders, tmp_path):
    # E4
    run_pipeline(Mode.CREATE, [ListResource("notion", 1)], chroma_client, embedders, tmp_path)

    for name in (TEXT_COLLECTION_NAME, IMAGE_COLLECTION_NAME):
        assert chroma_client.get_collection(name, embedding_function=None).configuration["hnsw"]["space"] == "cosine"


def collection_names(chroma_client) -> list[str]:
    return sorted(collection.name for collection in chroma_client.list_collections())


def stored_documents(chroma_client) -> list[str]:
    return sorted(open_collection(chroma_client, TEXT_COLLECTION_NAME).get()["documents"])


def test_update_replaces_every_collection_after_reading_everything(chroma_client, embedders, tmp_path):
    # E5
    run_pipeline(Mode.CREATE, [ListResource("stale", 5)], chroma_client, embedders, tmp_path)
    chroma_client.create_collection("leftover", embedding_function=None)

    result = run_pipeline(Mode.UPDATE, [ListResource("fresh", 3)], chroma_client, embedders, tmp_path)

    assert result.complete is True
    assert collection_names(chroma_client) == [IMAGE_COLLECTION_NAME, TEXT_COLLECTION_NAME]
    assert stored_documents(chroma_client) == ["fresh note 0", "fresh note 1", "fresh note 2"]
    assert is_build_complete(chroma_client)
    for name in (TEXT_COLLECTION_NAME, IMAGE_COLLECTION_NAME):
        assert chroma_client.get_collection(name, embedding_function=None).configuration["hnsw"]["space"] == "cosine"


class StoreCheckingResource(ListResource):
    """Records the stored documents at the moment it is read."""

    def __init__(self, chroma_client):
        super().__init__("fresh", 2)
        self.chroma_client = chroma_client
        self.seen: list[str] = []

    def read_documents(self) -> list[Document]:
        self.seen = stored_documents(self.chroma_client)
        return super().read_documents()


def test_update_reads_before_touching_the_stored_collections(chroma_client, embedders, tmp_path):
    # E5
    run_pipeline(Mode.CREATE, [ListResource("stale", 2)], chroma_client, embedders, tmp_path)
    resource = StoreCheckingResource(chroma_client)

    run_pipeline(Mode.UPDATE, [resource], chroma_client, embedders, tmp_path)

    assert resource.seen == ["stale note 0", "stale note 1"]
    assert stored_documents(chroma_client) == ["fresh note 0", "fresh note 1"]


def test_failing_resource_in_update_keeps_the_old_collections(chroma_client, embedders, tmp_path):
    # E10
    run_pipeline(Mode.CREATE, [ListResource("stale", 2)], chroma_client, embedders, tmp_path)

    result = run_pipeline(
        Mode.UPDATE, [ListResource("fresh", 3), FailingResource()], chroma_client, embedders, tmp_path
    )

    assert result.complete is False
    assert result.failed_resources == ["broken"]
    assert stored_documents(chroma_client) == ["stale note 0", "stale note 1"]
    assert is_build_complete(chroma_client)
    assert collection_names(chroma_client) == [IMAGE_COLLECTION_NAME, TEXT_COLLECTION_NAME]
    log = (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "update failed, the old collections are kept" in log


def test_update_with_zero_documents_keeps_the_old_collections(chroma_client, embedders, tmp_path):
    # E11
    run_pipeline(Mode.CREATE, [ListResource("stale", 2)], chroma_client, embedders, tmp_path)

    result = run_pipeline(Mode.UPDATE, [ListResource("fresh", 0)], chroma_client, embedders, tmp_path)

    assert result.complete is False
    assert result.added_documents == 0
    assert stored_documents(chroma_client) == ["stale note 0", "stale note 1"]
    assert collection_names(chroma_client) == [IMAGE_COLLECTION_NAME, TEXT_COLLECTION_NAME]


def test_build_is_marked_complete_only_when_it_ends_with_documents_and_no_failure(chroma_client, embedders, tmp_path):
    # H13 H14
    empty = run_pipeline(Mode.CREATE, [], chroma_client, embedders, tmp_path)
    assert (empty.complete, is_build_complete(chroma_client)) == (False, False)

    resources = [FailingResource(), ListResource("notion", 1)]
    failed = run_pipeline(Mode.CREATE, resources, chroma_client, embedders, tmp_path)
    assert (failed.complete, is_build_complete(chroma_client)) == (False, False)

    built = run_pipeline(Mode.CREATE, [ListResource("notion", 1)], chroma_client, embedders, tmp_path)
    assert (built.complete, is_build_complete(chroma_client)) == (True, True)


def test_every_step_is_logged_to_a_dated_file(chroma_client, embedders, tmp_path):
    # E6
    logs_dir = tmp_path / "logs" / "embedding"
    run_pipeline(Mode.CREATE, [ListResource("old", 1)], chroma_client, embedders, tmp_path)

    run_pipeline(Mode.UPDATE, [ListResource("notion", 20)], chroma_client, embedders, logs_dir)

    lines = (logs_dir / LOG_FILE_NAME).read_text(encoding="utf-8").splitlines()
    assert "start mode=update" in lines[0]
    assert any("deleted collections: ['fuxi_image_old', 'fuxi_text_old']" in line for line in lines)
    assert any("notion: 20 documents read" in line for line in lines)
    assert any("batch 2 added 4 documents to fuxi_text" in line for line in lines)
    assert "end" in lines[-1] and "20 documents" in lines[-1]
    assert all(line.startswith("2026-11-13 09:05:42") for line in lines)


def test_failing_resource_is_logged_and_others_continue(chroma_client, embedders, tmp_path):
    # E7
    result = run_pipeline(
        Mode.CREATE, [FailingResource(), ListResource("notion", 4)], chroma_client, embedders, tmp_path
    )

    assert result.failed_resources == ["broken"]
    assert result.added_documents == 4
    assert result.complete is False
    assert collection_names(chroma_client) == []  # an incomplete build is not stored
    log = (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "broken failed: RuntimeError: source is down" in log


def test_unknown_mode_is_rejected(chroma_client, embedders, tmp_path):
    # E5
    with pytest.raises(ValueError):
        run_pipeline("rebuild", [], chroma_client, embedders, tmp_path)


def test_chroma_client_is_persistent_without_telemetry(monkeypatch, tmp_path):
    # E8
    calls = []
    monkeypatch.setattr(chroma_store.chromadb, "PersistentClient", lambda **kwargs: calls.append(kwargs))

    create_chroma_client(tmp_path)

    assert calls[0]["path"] == str(tmp_path)
    assert calls[0]["settings"].anonymized_telemetry is False
    assert DEFAULT_CHROMA_PATH == Path(chroma_store.__file__).resolve().parent / "chroma_data"


def test_failed_create_keeps_the_existing_collections(chroma_client, embedders, tmp_path):
    # E12
    run_pipeline(Mode.CREATE, [ListResource("stale", 2)], chroma_client, embedders, tmp_path)

    result = run_pipeline(
        Mode.CREATE, [ListResource("fresh", 3), FailingResource()], chroma_client, embedders, tmp_path
    )

    assert result.complete is False
    assert stored_documents(chroma_client) == ["stale note 0", "stale note 1"]
    assert is_build_complete(chroma_client)
    assert collection_names(chroma_client) == [IMAGE_COLLECTION_NAME, TEXT_COLLECTION_NAME]
    assert "create failed, the old collections are kept" in (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")


def test_create_reads_before_touching_the_stored_collections(chroma_client, embedders, tmp_path):
    # E12
    run_pipeline(Mode.CREATE, [ListResource("stale", 2)], chroma_client, embedders, tmp_path)
    resource = StoreCheckingResource(chroma_client)

    run_pipeline(Mode.CREATE, [resource], chroma_client, embedders, tmp_path)

    assert resource.seen == ["stale note 0", "stale note 1"]
    assert stored_documents(chroma_client) == ["fresh note 0", "fresh note 1"]


@pytest.mark.parametrize(
    "failing_name",
    ["fuxi_image_old", "fuxi_text", "fuxi_image"],
    ids=["live-to-old", "first-staging", "second-staging"],
)
def test_failed_rename_restores_the_old_collections(chroma_client, embedders, tmp_path, failing_name):
    # E13
    run_pipeline(Mode.CREATE, [ListResource("stale", 2)], chroma_client, embedders, tmp_path)
    failing_client = RenameFailingClient(chroma_client, {failing_name})

    with pytest.raises(RuntimeError, match="rename"):
        run_pipeline(Mode.UPDATE, [ListResource("fresh", 3)], failing_client, embedders, tmp_path)

    assert collection_names(chroma_client) == [IMAGE_COLLECTION_NAME, TEXT_COLLECTION_NAME]
    assert stored_documents(chroma_client) == ["stale note 0", "stale note 1"]
    assert is_build_complete(chroma_client)
    assert "swap failed, the old collections are restored" in (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")


class CollectionNamesResource(ListResource):
    """Records the collection names at the moment it is read."""

    def __init__(self, chroma_client):
        super().__init__("fresh", 2)
        self.chroma_client = chroma_client
        self.seen: list[str] = []

    def read_documents(self) -> list[Document]:
        self.seen = collection_names(self.chroma_client)
        return super().read_documents()


def test_leftover_old_and_staging_collections_are_removed_before_a_build(chroma_client, embedders, tmp_path):
    # E13
    run_pipeline(Mode.CREATE, [ListResource("stale", 2)], chroma_client, embedders, tmp_path)
    open_collection(chroma_client, "fuxi_text_old").add(ids=["x"], documents=["older"], embeddings=[[1.0] * 8])
    open_collection(chroma_client, "fuxi_image_next").add(ids=["y"], documents=["partial"], embeddings=[[1.0] * 8])
    resource = CollectionNamesResource(chroma_client)

    run_pipeline(Mode.UPDATE, [resource], chroma_client, embedders, tmp_path)

    assert "fuxi_text_old" not in resource.seen
    assert set(resource.seen) >= {TEXT_COLLECTION_NAME, IMAGE_COLLECTION_NAME}
    assert collection_names(chroma_client) == [IMAGE_COLLECTION_NAME, TEXT_COLLECTION_NAME]
    assert stored_documents(chroma_client) == ["fresh note 0", "fresh note 1"]


def test_old_collection_without_a_live_one_is_restored_before_a_build(chroma_client, embedders, tmp_path):
    # E13
    run_pipeline(Mode.CREATE, [ListResource("stale", 2)], chroma_client, embedders, tmp_path)
    chroma_store.rename_collection(chroma_client, TEXT_COLLECTION_NAME, "fuxi_text_old")

    result = run_pipeline(Mode.UPDATE, [FailingResource()], chroma_client, embedders, tmp_path)

    assert result.complete is False
    assert collection_names(chroma_client) == [IMAGE_COLLECTION_NAME, TEXT_COLLECTION_NAME]
    assert stored_documents(chroma_client) == ["stale note 0", "stale note 1"]
    assert is_build_complete(chroma_client)


class SummaryResource(ListResource):
    def read_summary(self) -> str:
        return "3 pages, 9 calls"


class FailingSummaryResource(FailingResource):
    def read_summary(self) -> str:
        return "1 pages, 5 calls"


def test_read_summary_is_logged_after_a_read_and_after_a_failed_read(chroma_client, embedders, tmp_path):
    # E14
    run_pipeline(
        Mode.CREATE, [FailingSummaryResource(), SummaryResource("notion", 2), ListResource("plain", 1)],
        chroma_client, embedders, tmp_path,
    )

    log = (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "resource notion: read summary: 3 pages, 9 calls" in log
    assert "resource broken: read summary: 1 pages, 5 calls" in log
    assert "resource plain: read summary" not in log


def test_image_documents_are_decoded_into_pictures_before_clip(chroma_client, embedders, tmp_path):
    # Phase 5b D1
    run_pipeline(Mode.CREATE, [PictureResource(2)], chroma_client, embedders, tmp_path)

    pictures = embedders.image.document_batches[0]
    assert [(picture.mode, picture.size) for picture in pictures] == [("RGB", TEST_PICTURE_SIZE)] * 2


def test_invalid_picture_data_fails_the_batch_and_names_the_document(chroma_client, embedders, tmp_path):
    # Phase 5b D2
    result = run_pipeline(
        Mode.CREATE, [PictureResource(2, broken_name="broken.png")], chroma_client, embedders, tmp_path
    )

    assert result.failed_resources == ["google_drive"]
    assert embedders.image.document_batches == []
    log = (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "resource google_drive failed: PictureDataError" in log
    assert "broken.png" in log


DRIVE_PICTURE_IDS = [
    "1dRvImgParisRain0000000000000001",
    "1dRvImgUmbrella00000000000000002",
    "1dRvImgCafe000000000000000000003",
    "1dRvImgSketch00000000000000000004",
]


def drive_resource(failures=None) -> GoogleDriveResource:
    api = FakeDriveApi(
        load_fixture("drive_recorded.json"),
        {file_id: base64.b64decode(picture_text()) for file_id in DRIVE_PICTURE_IDS},
        failures,
    )
    return GoogleDriveResource(token_source_factory=FakeTokens, http_client_factory=api.client, sleep=lambda _: None)


def notion_resource() -> NotionResource:
    client = FakeNotionClient(load_fixture("notion_recorded.json"))
    return NotionResource(client_factory=lambda: client, sleep=lambda _: None)


def test_notion_and_drive_are_both_read_and_drive_documents_go_to_fuxi_image(chroma_client, embedders, tmp_path):
    # Phase 5b E1
    result = run_pipeline(Mode.CREATE, [notion_resource(), drive_resource()], chroma_client, embedders, tmp_path)

    assert result.complete is True
    images = open_collection(chroma_client, IMAGE_COLLECTION_NAME).get()
    texts = open_collection(chroma_client, TEXT_COLLECTION_NAME).get()
    assert sorted(metadata["name"] for metadata in images["metadatas"]) == [
        "cafe.heic", "paris_rain.jpg", "sketch.gif", "umbrella.png"
    ]
    assert {metadata["type"] for metadata in texts["metadatas"]} == {"text"}


def test_image_document_is_stored_with_id_base64_text_embedding_and_metadata_together(
    chroma_client, embedders, tmp_path
):
    # Phase 5b E2
    run_pipeline(Mode.CREATE, [drive_resource()], chroma_client, embedders, tmp_path)

    stored = open_collection(chroma_client, IMAGE_COLLECTION_NAME).get(
        include=["documents", "metadatas", "embeddings"]
    )
    by_name = {metadata["name"]: (text, metadata) for text, metadata in zip(stored["documents"], stored["metadatas"])}
    text, metadata = by_name["umbrella.png"]
    assert base64.b64decode(text, validate=True)[:2] == b"\xff\xd8"  # a JPEG
    assert metadata == {
        "name": "umbrella.png", "path": "Photos / Paris", "type": "picture", "timestamp": "2026-09-21T10:05:00.000Z"
    }
    assert len(stored["ids"]) == len(stored["embeddings"]) == 4
    assert [list(vector) for vector in stored["embeddings"]] == [pytest.approx([0.5] * 8)] * 4


def test_twenty_images_are_embedded_with_clip_in_batches_of_16_and_4(chroma_client, embedders, tmp_path):
    # Phase 5b E3
    run_pipeline(Mode.CREATE, [PictureResource(20)], chroma_client, embedders, tmp_path, batch_size=16)

    assert [len(batch) for batch in embedders.image.document_batches] == [16, 4]
    assert open_collection(chroma_client, IMAGE_COLLECTION_NAME).count() == 20


def test_failing_drive_keeps_notion_embedding_but_the_build_is_incomplete_and_old_collections_stay(
    chroma_client, embedders, tmp_path
):
    # Phase 5b E4
    run_pipeline(Mode.CREATE, [ListResource("stale", 2)], chroma_client, embedders, tmp_path)
    failing_drive = drive_resource(failures={"files.list": [httpx.Response(401)]})

    result = run_pipeline(Mode.UPDATE, [notion_resource(), failing_drive], chroma_client, embedders, tmp_path)

    assert result.failed_resources == ["google_drive"]
    assert result.added_documents > 0  # Notion was still embedded
    assert result.complete is False
    assert stored_documents(chroma_client) == ["stale note 0", "stale note 1"]
    assert is_build_complete(chroma_client)


def test_drive_read_summary_is_written_to_the_embedding_log(chroma_client, embedders, tmp_path):
    # Phase 5b E5
    run_pipeline(Mode.CREATE, [drive_resource()], chroma_client, embedders, tmp_path)

    log = (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "resource google_drive: read summary: 4 images, 0 skipped files," in log


MOVIE_NAMES = ["Paper Harbor", "The Lantern Keeper", "The Lost Stars", "Winter Sun"]
MOVIE_TEST_TOKEN = "tmdb-test-token"


def movie_resource(failures=None) -> LetterboxdTmdbResource:
    api = FakeTmdbApi(load_fixture("tmdb_recorded.json"), failures)
    return LetterboxdTmdbResource(
        watched_file_factory=lambda: FIXTURES_DIR / "watched.csv",
        token_factory=lambda: MOVIE_TEST_TOKEN,
        http_client_factory=api.client,
        sleep=lambda _: None,
    )


def test_notion_drive_and_movies_are_all_read_and_movie_documents_go_to_fuxi_text(chroma_client, embedders, tmp_path):
    # Phase 5c F1
    resources = [notion_resource(), drive_resource(), movie_resource()]

    result = run_pipeline(Mode.CREATE, resources, chroma_client, embedders, tmp_path)

    assert result.complete is True
    texts = open_collection(chroma_client, TEXT_COLLECTION_NAME).get()
    images = open_collection(chroma_client, IMAGE_COLLECTION_NAME).get()
    movies = {
        metadata["name"]: (text, metadata)
        for text, metadata in zip(texts["documents"], texts["metadatas"])
        if "director" in metadata
    }
    assert sorted(movies) == MOVIE_NAMES
    assert len(texts["documents"]) > len(movies)  # the Notion documents are in fuxi_text too
    assert len(images["documents"]) == len(DRIVE_PICTURE_IDS)
    assert not any("director" in metadata for metadata in images["metadatas"])
    text, metadata = movies["The Lost Stars"]
    assert text.startswith("The Lost Stars (2008)\nDirector: Étienne Roussel\nMusic: Bastien Morel\n")
    assert metadata == {
        "name": "The Lost Stars", "path": "", "director": "Étienne Roussel", "musician": "Bastien Morel",
        "genre": "Science Fiction, Romance", "timestamp": "2026-03-20", "type": "text",
    }
    assert any(text in batch for batch in embedders.text.document_batches)  # embedded by the text embedder


def test_failing_movies_keep_the_other_sources_embedding_but_the_build_is_incomplete_and_old_collections_stay(
    chroma_client, embedders, tmp_path
):
    # Phase 5c F2
    run_pipeline(Mode.CREATE, [ListResource("stale", 2)], chroma_client, embedders, tmp_path)
    failing_movies = movie_resource(failures={"search:The Lantern Keeper": [httpx.Response(401)]})

    result = run_pipeline(
        Mode.UPDATE, [notion_resource(), failing_movies, drive_resource()], chroma_client, embedders, tmp_path
    )

    assert result.failed_resources == ["letterboxd_tmdb"]
    assert result.added_documents > len(DRIVE_PICTURE_IDS)  # Notion and Drive were still embedded
    assert embedders.image.document_batches  # Drive, read after the failed movies
    assert result.complete is False
    assert stored_documents(chroma_client) == ["stale note 0", "stale note 1"]
    assert is_build_complete(chroma_client)


def test_movie_read_summary_is_written_to_the_embedding_log(chroma_client, embedders, tmp_path):
    # Phase 5c F3
    run_pipeline(Mode.CREATE, [movie_resource()], chroma_client, embedders, tmp_path)

    log = (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert (
        "resource letterboxd_tmdb: read summary: 4 rows, 4 movies, "
        "0 skipped rows (0 bad rows, 0 no match, 0 not found, 0 refused), 0 repeated rows, 8 calls,"
    ) in log


def test_failed_movie_read_summary_is_written_to_the_embedding_log(chroma_client, embedders, tmp_path):
    # Phase 5c F3
    # The last row fails, so the three movies before it have finished (Phase 5c D16, D17).
    failing_movies = movie_resource(failures={"search:Les Étoiles Perdues": [httpx.Response(401)]})

    run_pipeline(Mode.CREATE, [failing_movies], chroma_client, embedders, tmp_path)

    log = (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "resource letterboxd_tmdb failed: TmdbError: TMDB call failed: 401 on /3/search/movie\n" in log
    assert "resource letterboxd_tmdb: read summary: 4 rows, 3 movies," in log
    assert "toiles" not in log
    assert MOVIE_TEST_TOKEN not in log
