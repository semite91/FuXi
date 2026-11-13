import copy

import httpx
import pytest
from langchain_text_splitters import RecursiveCharacterTextSplitter
from notion_client import APIResponseError

from base import Document, Resource, ResourceKind
from fakes import FakeNotionClient, load_fixture
from resources.notion_resource import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    MAX_ATTEMPTS,
    NotionResource,
)

PAGE_A = "1a2b3c4d-0001-4000-8000-00000000000a"
PAGE_C = "1a2b3c4d-0003-4000-8000-00000000000c"
PAGE_D = "1a2b3c4d-0004-4000-8000-00000000000d"
RATE_LIMITED_STATUS = 429


def recorded():
    return copy.deepcopy(load_fixture("notion_recorded.json"))


def make_resource(client, sleeps=None):
    sleeps = [] if sleeps is None else sleeps
    return NotionResource(client_factory=lambda: client, sleep=sleeps.append)


def by_name(documents):
    return {document.metadata["name"]: document for document in documents}


def rate_limited(retry_after: str) -> APIResponseError:
    return APIResponseError(
        code="rate_limited",
        status=RATE_LIMITED_STATUS,
        message="You have been rate limited.",
        headers=httpx.Headers({"Retry-After": retry_after}),
        raw_body_text="",
    )


def test_every_shared_page_is_read_once_over_two_search_pages():
    # C1
    client = FakeNotionClient(recorded())

    documents = make_resource(client).read_documents()

    searches = [kwargs for name, kwargs in client.calls if name == "search"]
    assert len(searches) == 2
    assert searches[0]["filter"] == {"property": "object", "value": "page"}
    assert searches[1]["start_cursor"] == "cursor-search-2"
    assert sorted(by_name(documents)) == ["Lisbon", "Poems", "Travel Notes"]
    read_pages = [kwargs["block_id"] for name, kwargs in client.calls if name == "blocks.children.list"]
    assert read_pages.count(PAGE_A) == 2  # two result pages of one page, read once


def test_nested_block_text_is_included_in_order():
    # C2
    documents = make_resource(FakeNotionClient(recorded())).read_documents()

    assert by_name(documents)["Travel Notes"].text == (
        "The Paris trip started in the rain.\n"
        "Hidden memory\n"
        "A stranger lent me an umbrella.\n"
        "Food\n"
        "Croissants every morning"
    )


def test_child_pages_are_not_read_as_nested_blocks():
    # C2
    documents = make_resource(FakeNotionClient(recorded())).read_documents()

    assert by_name(documents)["Lisbon"].text == "Tram 28 climbs the hills of Alfama."


def test_block_children_over_two_result_pages_are_all_read():
    # C3
    client = FakeNotionClient(recorded())

    make_resource(client).read_documents()

    cursors = [
        kwargs.get("start_cursor")
        for name, kwargs in client.calls
        if name == "blocks.children.list" and kwargs["block_id"] == PAGE_A
    ]
    assert cursors == [None, "cursor-a-2"]


def test_document_metadata_has_name_path_type_and_timestamp():
    # C4
    client = FakeNotionClient(recorded())

    documents = by_name(make_resource(client).read_documents())

    assert documents["Travel Notes"].metadata == {
        "name": "Travel Notes",
        "path": "",
        "type": "text",
        "timestamp": "2026-10-01T09:30:00.000Z",
    }
    assert documents["Lisbon"].metadata["path"] == "Travel Notes"
    assert documents["Poems"].metadata["path"] == "Archive"
    retrieved = [kwargs["page_id"] for name, kwargs in client.calls if name == "pages.retrieve"]
    assert retrieved == [PAGE_D]  # pages from the search are not fetched again


def test_short_page_gives_one_document():
    # C5
    documents = make_resource(FakeNotionClient(recorded())).read_documents()

    assert [d.metadata["name"] for d in documents].count("Poems") == 1


def long_page_recording(text_length: int) -> dict:
    data = recorded()
    words = " ".join(f"word{index}" for index in range(text_length // 6))
    block = data["block_children"][PAGE_C]["start"]["results"][0]
    block["quote"]["rich_text"][0]["plain_text"] = words
    return data


def test_long_page_is_split_with_overlap():
    # C6
    data = long_page_recording(5000)
    text = data["block_children"][PAGE_C]["start"]["results"][0]["quote"]["rich_text"][0]["plain_text"]

    poems = [d for d in make_resource(FakeNotionClient(data)).read_documents() if d.metadata["name"] == "Poems"]

    expected = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200).split_text(text)
    assert (CHUNK_SIZE, CHUNK_OVERLAP) == (2000, 200)
    assert [d.text for d in poems] == expected
    assert len(poems) > 1
    assert all(len(d.text) <= CHUNK_SIZE for d in poems)
    assert poems[1].text[:100] in poems[0].text  # the overlap repeats the end of the part before
    assert all(d.metadata["name"] == "Poems" for d in poems)


def test_page_without_text_gives_no_document():
    # C7
    documents = make_resource(FakeNotionClient(recorded())).read_documents()

    assert "Empty page" not in by_name(documents)


def test_rate_limit_waits_retry_after_and_tries_again():
    # C8
    sleeps: list[float] = []
    client = FakeNotionClient(recorded(), errors=[rate_limited("3")])

    documents = make_resource(client, sleeps).read_documents()

    assert sleeps == [3.0]
    assert len(by_name(documents)) == 3


def test_rate_limit_retries_are_bounded():
    # C8
    errors = [rate_limited("1") for _ in range(MAX_ATTEMPTS)]
    sleeps: list[float] = []

    with pytest.raises(APIResponseError):
        make_resource(FakeNotionClient(recorded(), errors=errors), sleeps).read_documents()

    assert len(sleeps) == MAX_ATTEMPTS - 1


def test_new_resource_only_implements_the_base():
    # C9
    class DiaryResource(Resource):
        name = "diary"
        kind = ResourceKind.TEXT

        def read_documents(self) -> list[Document]:
            return [Document(text="Dear diary", metadata={"name": "Day 1"})]

    assert isinstance(NotionResource(client_factory=lambda: None), Resource)
    assert DiaryResource().read_documents()[0].text == "Dear diary"


def test_resource_without_read_documents_cannot_be_created():
    # C9
    class BrokenResource(Resource):
        name = "broken"
        kind = ResourceKind.TEXT

    with pytest.raises(TypeError):
        BrokenResource()
