import base64
import io
import json
import random
from pathlib import Path

import pytest
from google.genai import errors
from PIL import Image

from base import RetrievedItem
from fakes import (
    DRIVE_TEST_FOLDER_ID,
    FakeDriveApi,
    FakeGeminiClient,
    ScriptedRandom,
    fake_drive_resource,
    load_fixture,
    picture_text,
)
from llm_client import METHODS, PROMPTS_DIR, LlmClient
from web_finders import FoundSong
from resources.google_drive_resource import MAX_PICTURE_SIDE
from settings import MissingSettingError, Settings

RECORDED = load_fixture("gemini_recorded.json")
WORD = "serendipity"
MEANING = "şans eseri güzel bir şey bulma"
TEXT_RESULTS = [
    RetrievedItem(
        document="A stranger lent me an umbrella.",
        metadata={"name": "Travel Notes", "path": "", "type": "text", "timestamp": "2026-10-01T09:30:00.000Z"},
        similarity=0.71,
    )
]
SETTINGS = Settings(gemini_model="gemini-test-model", gemini_api_key="test-key")
DRIVE_IMAGES = [
    RetrievedItem(
        document=picture_text(color=(10 * index, 20, 30)),
        metadata={"name": name, "path": path, "type": "picture", "timestamp": "2026-09-14T18:42:10"},
        similarity=0.3,
    )
    for index, (name, path) in enumerate(
        [("paris_rain.jpg", "Photos"), ("umbrella.png", "Photos / Paris"), ("cafe.heic", "Photos / Paris")]
    )
]


def prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


EXAMPLE_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/a/a9/Example.jpg"
EXAMPLE_SONG = FoundSong("Serendipity", "BTS", "https://open.spotify.com/track/4d8b0ZFHJaGG4H3CSHfSwV")


class FakeSongFinder:
    def __init__(self, song=EXAMPLE_SONG):
        self.song = song
        self.calls = []

    def find_song(self, title, artist):
        self.calls.append((title, artist))
        return self.song


class FakeImageFinder:
    def __init__(self, url=EXAMPLE_IMAGE_URL):
        self.url = url
        self.calls = []

    def find_image(self, query):
        self.calls.append(query)
        return self.url


def make_client(answers, choices=None, settings=SETTINGS, song_finder=None, image_finder=None):
    gemini = FakeGeminiClient(answers)
    random_source = ScriptedRandom(choices or [])
    client = LlmClient(
        settings,
        gemini_client_factory=lambda: gemini,
        random_source=random_source,
        sleep=lambda _: None,
        song_finder=song_finder or FakeSongFinder(),
        image_finder=image_finder or FakeImageFinder(),
    )
    return client, gemini, random_source


def generate(client):
    return client.generate(WORD, MEANING, TEXT_RESULTS, [])


def test_search_query_sends_retrieval_prompt_with_word_and_meaning():
    # G1
    client, gemini, _ = make_client([RECORDED["retrieval_query"]])

    client.build_search_queries(WORD, MEANING)

    call = gemini.calls[0]
    assert call["config"].system_instruction == prompt("retrieval.txt")
    assert json.loads(call["contents"]) == {"word": WORD, "meaning": MEANING}


def test_search_query_uses_geminis_query():
    # G2
    client, _, _ = make_client([RECORDED["retrieval_query"]])

    assert client.build_search_queries(WORD, MEANING)[0].startswith("unexpected discoveries")


@pytest.mark.parametrize("answer", [RECORDED["retrieval_invalid"], "", '{"query": ""}', '{"queries": []}', errors.ServerError(503, {})])
def test_invalid_search_answer_falls_back_to_word_and_meaning(answer):
    # G3
    client, _, _ = make_client([answer])

    assert client.build_search_queries(WORD, MEANING) == [f"{WORD}: {MEANING}"]


def test_method_is_chosen_from_the_five_methods():
    # G4
    seen = set()
    for seed in range(30):
        gemini = FakeGeminiClient([RECORDED["insufficient_context"]] * 2)
        client = LlmClient(SETTINGS, gemini_client_factory=lambda: gemini, random_source=random.Random(seed))
        generate(client)
        seen.add(json.loads(gemini.calls[0]["contents"])["available_methods"][0])
    assert METHODS == ("story", "quote", "film reference", "photo", "music")
    assert seen <= set(METHODS) and len(seen) > 1


@pytest.mark.parametrize(
    ("method", "answer"),
    [("story", "story_success"), ("quote", "quote_success"), ("film reference", "film_reference_variant_success")],
)
def test_text_methods_use_llm_prompt_without_tools(method, answer):
    # G5
    client, gemini, _ = make_client([RECORDED[answer]], [method])

    assert json.loads(generate(client))["method"] == method

    config = gemini.calls[0]["config"]
    assert config.system_instruction == prompt("llm.txt")
    assert not config.tools


@pytest.mark.parametrize("method", ["photo", "music"])
def test_web_methods_use_the_suggest_prompt_without_tools(method):
    # G6
    client, gemini, _ = make_client([RECORDED[f"{method}_success"]], [method])

    generate(client)

    config = gemini.calls[0]["config"]
    assert config.system_instruction == prompt("llm_suggest.txt")
    assert not config.tools


def test_call_input_holds_word_meaning_method_and_context():
    # G7
    client, gemini, _ = make_client([RECORDED["story_success"]], ["story"])

    generate(client)

    assert json.loads(gemini.calls[0]["contents"]) == {
        "word": WORD,
        "meaning": MEANING,
        "available_methods": ["story"],
        "retrieved_context": {
            "texts": [{"document": "A stranger lent me an umbrella.", "name": "Travel Notes", "path": ""}],
            "images": [],
        },
    }


def test_model_is_the_configured_model():
    # G8
    client, gemini, _ = make_client([RECORDED["retrieval_query"], RECORDED["story_success"]], ["story"])

    client.build_search_queries(WORD, MEANING)
    generate(client)

    assert [call["model"] for call in gemini.calls] == ["gemini-test-model"] * 2


def test_text_method_success_gives_text_content():
    # G9
    client, _, _ = make_client([RECORDED["story_success"]], ["story"])

    content = generate(client)

    assert json.loads(content) == {
        "method": "story",
        "title": "The Umbrella in Paris",
        "content": "In the rain a stranger lent you an umbrella: pure serendipity.",
        "source_reference": "Travel Notes",
    }


def test_returned_method_variant_is_stored_as_the_canonical_name():
    # G9
    client, _, _ = make_client([RECORDED["film_reference_variant_success"]], ["film reference"])

    content = json.loads(generate(client))

    assert content["method"] == "film reference"
    assert content["title"] == "Amélie"


def test_different_returned_method_is_a_failure():
    # G9
    client, gemini, _ = make_client([RECORDED["wrong_method"], RECORDED["insufficient_context"]], ["story", "music"])

    assert generate(client) is None
    assert len(gemini.calls) == 2


def test_photo_success_gives_the_web_image_found_for_the_suggested_phrase():
    # G10
    finder = FakeImageFinder()
    client, _, _ = make_client([RECORDED["photo_success"]], ["photo"], image_finder=finder)

    assert json.loads(generate(client)) == {"method": "photo", "image_url": EXAMPLE_IMAGE_URL}
    assert finder.calls == ["umbrella in the rain"]


def test_a_phrase_with_no_image_found_is_a_failed_method():
    # G10
    client, gemini, _ = make_client(
        [RECORDED["photo_success"], RECORDED["story_success"]], ["photo", "story"], image_finder=FakeImageFinder(url=None)
    )

    assert json.loads(generate(client))["method"] == "story"
    assert len(gemini.calls) == 2


def test_music_success_gives_the_song_spotify_found_and_no_lyrics():
    # G11
    finder = FakeSongFinder()
    client, _, _ = make_client([RECORDED["music_success"]], ["music"], song_finder=finder)

    assert json.loads(generate(client)) == {
        "method": "music",
        "song_title": "Serendipity",
        "artist": "BTS",
        "song_url": "https://open.spotify.com/track/4d8b0ZFHJaGG4H3CSHfSwV",
        "lyrics_excerpt": None,
    }
    assert finder.calls == [("Serendipity", "BTS")]


def test_a_song_spotify_does_not_have_is_a_failed_method():
    # G11
    client, gemini, _ = make_client(
        [RECORDED["music_success"], RECORDED["story_success"]], ["music", "story"], song_finder=FakeSongFinder(song=None)
    )

    assert json.loads(generate(client))["method"] == "story"
    assert len(gemini.calls) == 2


@pytest.mark.parametrize(("method", "answer"), [("photo", "photo_http_url"), ("music", "music_incomplete")])
def test_an_answer_without_what_the_finder_needs_counts_as_insufficient_context(method, answer):
    # G12
    client, gemini, _ = make_client([RECORDED[answer], RECORDED["story_success"]], [method, "story"])

    assert json.loads(generate(client))["method"] == "story"
    assert len(gemini.calls) == 2


@pytest.mark.parametrize("answer", ["insufficient_context", "empty", "retrieval_invalid"])
def test_failed_method_tries_one_other_random_method(answer):
    # G13
    client, gemini, random_source = make_client([RECORDED[answer], RECORDED["quote_success"]], ["story", "quote"])

    content = generate(client)

    assert json.loads(content)["method"] == "quote"
    assert random_source.offered[1] == [method for method in METHODS if method != "story"]
    assert json.loads(gemini.calls[1]["contents"])["available_methods"] == ["quote"]


def test_second_failure_gives_no_content():
    # G14
    client, gemini, _ = make_client(
        [RECORDED["insufficient_context"], RECORDED["empty"]], ["story", "photo"]
    )

    assert generate(client) is None
    assert len(gemini.calls) == 2


def test_a_gemini_error_for_a_web_method_counts_as_failed_method():
    # G15
    refused = errors.ClientError(400, {"error": {"code": 400, "message": "Not supported.", "status": "INVALID_ARGUMENT"}})
    client, gemini, _ = make_client([refused, RECORDED["story_success"]], ["photo", "story"])

    assert json.loads(generate(client))["method"] == "story"
    assert not gemini.calls[1]["config"].tools


def test_missing_gemini_key_gives_no_content_and_names_the_key(caplog):
    # B5
    client = LlmClient(Settings(), random_source=ScriptedRandom(["story", "quote"]))

    assert client.build_search_queries(WORD, MEANING) == [f"{WORD}: {MEANING}"]
    assert generate(client) is None
    assert "RAG_GEMINI_API_KEY" in caplog.text


def test_missing_key_error_is_raised_only_when_the_client_is_used():
    # B5
    client = LlmClient(Settings())

    with pytest.raises(MissingSettingError, match="RAG_GEMINI_API_KEY"):
        client.gemini_client()


def test_each_prompt_file_is_read_once_over_several_calls(monkeypatch, tmp_path):
    # G18
    for name in ("retrieval.txt", "llm.txt", "llm_suggest.txt"):
        (tmp_path / name).write_text(f"prompt {name}", encoding="utf-8")
    reads: list[str] = []
    read_text = Path.read_text

    def counting_read_text(path, *args, **kwargs):
        reads.append(path.name)
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    answers = [RECORDED["retrieval_query"], RECORDED["story_success"]] * 2 + [RECORDED["photo_success"]]
    gemini = FakeGeminiClient(answers)
    client = LlmClient(
        SETTINGS,
        gemini_client_factory=lambda: gemini,
        random_source=ScriptedRandom(["story", "story", "photo"]),
        prompts_dir=tmp_path,
        image_finder=FakeImageFinder(),
    )

    for _ in range(2):
        client.build_search_queries(WORD, MEANING)
        generate(client)
    generate(client)

    assert sorted(reads) == ["llm.txt", "llm_suggest.txt", "retrieval.txt"]
    assert gemini.calls[-1]["config"].system_instruction == "prompt llm_suggest.txt"


def test_missing_web_prompt_does_not_break_text_methods_or_the_search_query(tmp_path):
    # G19
    for name in ("retrieval.txt", "llm.txt"):
        (tmp_path / name).write_text(f"prompt {name}", encoding="utf-8")
    gemini = FakeGeminiClient([RECORDED["retrieval_query"], RECORDED["story_success"]])
    client = LlmClient(
        SETTINGS, gemini_client_factory=lambda: gemini, random_source=ScriptedRandom(["story"]), prompts_dir=tmp_path
    )

    query = client.build_search_queries(WORD, MEANING)
    content = generate(client)

    assert query[0].startswith("unexpected discoveries")
    assert json.loads(content)["method"] == "story"
    assert [call["config"].system_instruction for call in gemini.calls] == ["prompt retrieval.txt", "prompt llm.txt"]


def generate_with_images(client, images=DRIVE_IMAGES):
    return client.generate(WORD, MEANING, TEXT_RESULTS, images)


def test_images_are_sent_by_reference_name_and_path_without_base64():
    # Phase 5b G1 R4
    client, gemini, _ = make_client([RECORDED["photo_success"]], ["photo"])

    generate_with_images(client)

    sent = gemini.calls[0]["contents"]
    assert json.loads(sent)["retrieved_context"]["images"] == [
        {"image_url": "drive:1", "name": "paris_rain.jpg", "path": "Photos"},
        {"image_url": "drive:2", "name": "umbrella.png", "path": "Photos / Paris"},
        {"image_url": "drive:3", "name": "cafe.heic", "path": "Photos / Paris"},
    ]
    assert all(image.document not in sent for image in DRIVE_IMAGES)


def test_drive_reference_gives_the_chosen_images_data_url():
    # Phase 5b G2
    client, _, _ = make_client([RECORDED["photo_drive_success"]], ["photo"])

    content = json.loads(generate_with_images(client))

    assert content == {"method": "photo", "image_url": f"data:image/jpeg;base64,{DRIVE_IMAGES[1].document}"}


def test_https_image_url_is_kept_with_drive_images_present():
    # Phase 5b G3
    client, _, _ = make_client([RECORDED["photo_success"]], ["photo"])

    content = json.loads(generate_with_images(client))

    assert content["image_url"] == EXAMPLE_IMAGE_URL


def test_unknown_drive_reference_counts_as_insufficient_context():
    # Phase 5b G4
    client, gemini, _ = make_client([RECORDED["photo_drive_unknown"], RECORDED["story_success"]], ["photo", "story"])

    assert json.loads(generate_with_images(client))["method"] == "story"
    assert len(gemini.calls) == 2


@pytest.mark.parametrize("answer", ["photo_data_url", "photo_javascript_url", "photo_http_url"])
def test_data_or_other_non_https_url_written_by_gemini_counts_as_insufficient_context(answer):
    # Phase 5b G5
    client, gemini, _ = make_client([RECORDED[answer], RECORDED["story_success"]], ["photo", "story"])

    assert json.loads(generate_with_images(client))["method"] == "story"
    assert len(gemini.calls) == 2


def test_drive_reference_without_image_results_counts_as_insufficient_context():
    # Phase 5b G4 G6
    client, gemini, _ = make_client([RECORDED["photo_drive_success"], RECORDED["story_success"]], ["photo", "story"])

    assert json.loads(generate_with_images(client, images=[]))["method"] == "story"
    assert json.loads(gemini.calls[0]["contents"])["retrieved_context"]["images"] == []


def test_photo_without_image_results_works_as_before():
    # Phase 5b G6
    client, gemini, _ = make_client([RECORDED["photo_success"]], ["photo"])

    content = json.loads(generate_with_images(client, images=[]))

    assert content == {"method": "photo", "image_url": EXAMPLE_IMAGE_URL}
    assert json.loads(gemini.calls[0]["contents"])["retrieved_context"]["images"] == []


def test_stored_drive_photo_holds_a_jpeg_of_at_most_512_px():
    # Phase 5b G7
    large = io.BytesIO()
    Image.new("RGB", (1600, 900), (90, 140, 200)).save(large, format="PNG")
    data = load_fixture("drive_recorded.json")
    umbrella = data["children"]["1dRvFolderParis000000000000000b"]["start"]["files"][0]
    data["children"] = {DRIVE_TEST_FOLDER_ID: {"start": {"files": [umbrella]}}}
    api = FakeDriveApi(data, {"1dRvImgUmbrella00000000000000002": large.getvalue()})
    document = fake_drive_resource(api).read_documents()[0]
    images = [DRIVE_IMAGES[0], RetrievedItem(document.text, document.metadata, 0.4)]
    client, _, _ = make_client([RECORDED["photo_drive_success"]], ["photo"])

    stored = json.loads(generate_with_images(client, images))

    prefix = "data:image/jpeg;base64,"
    assert stored["image_url"].startswith(prefix)
    picture = Image.open(io.BytesIO(base64.b64decode(stored["image_url"][len(prefix):], validate=True)))
    assert picture.format == "JPEG"
    assert max(picture.size) == MAX_PICTURE_SIDE == 512


def test_movie_result_is_sent_as_a_text_context_item_with_its_document_and_name():
    # Phase 5c G2
    movie = RetrievedItem(
        document="The Lantern Keeper (2019)\nDirector: Mara Ellison\nGenres: Drama, Mystery",
        metadata={
            "name": "The Lantern Keeper", "path": "", "director": "Mara Ellison", "musician": "Tobias Rehn",
            "genre": "Drama, Mystery", "timestamp": "2026-01-05", "type": "text",
        },
        similarity=0.66,
    )
    client, gemini, _ = make_client([RECORDED["story_success"]], ["story"])

    client.generate(WORD, MEANING, [*TEXT_RESULTS, movie], [])

    context = json.loads(gemini.calls[0]["contents"])["retrieved_context"]
    assert context["texts"] == [
        {"document": "A stranger lent me an umbrella.", "name": "Travel Notes", "path": ""},
        {"document": movie.document, "name": "The Lantern Keeper", "path": ""},
    ]
    assert context["images"] == []


def unavailable():
    return errors.ServerError(
        503, {"error": {"code": 503, "message": "This model is currently experiencing high demand.", "status": "UNAVAILABLE"}}
    )


def test_search_query_retries_a_503_and_uses_geminis_query():
    client, gemini, _ = make_client([unavailable(), unavailable(), RECORDED["retrieval_query"]])

    assert client.build_search_queries(WORD, MEANING) != [f"{WORD}: {MEANING}"]
    assert len(gemini.calls) == 3


def test_search_query_falls_back_when_503_lasts():
    client, gemini, _ = make_client([unavailable()] * 5)

    assert client.build_search_queries(WORD, MEANING) == [f"{WORD}: {MEANING}"]
    assert len(gemini.calls) == 5


def test_a_closed_gemini_client_is_replaced_and_the_search_query_is_asked_again():
    closed = RuntimeError("Cannot send a request, as the client has been closed.")
    clients = [FakeGeminiClient([closed]), FakeGeminiClient([RECORDED["retrieval_query"]])]
    made = iter(clients)
    client = LlmClient(
        SETTINGS, gemini_client_factory=lambda: next(made), random_source=ScriptedRandom([]), sleep=lambda _: None
    )

    assert client.build_search_queries(WORD, MEANING) != [f"{WORD}: {MEANING}"]
    assert [len(c.calls) for c in clients] == [1, 1]


def test_another_runtime_error_is_not_retried():
    client, gemini, _ = make_client([RuntimeError("something else")])

    assert client.build_search_queries(WORD, MEANING) == [f"{WORD}: {MEANING}"]
    assert len(gemini.calls) == 1


def test_queries_are_distinct_trimmed_and_at_most_four():
    # G1
    answer = json.dumps({"queries": ["  a  ", "a", "", 5, "b", "c", "d", "e"]})
    client, _, _ = make_client([answer])

    assert client.build_search_queries(WORD, MEANING) == ["a", "b", "c", "d"]


def test_a_single_query_text_is_still_accepted():
    # G2
    client, _, _ = make_client(['{"query": "lucky surprises"}'])

    assert client.build_search_queries(WORD, MEANING) == ["lucky surprises"]


def test_queries_for_a_method_send_the_target_method():
    # G1
    client, gemini, _ = make_client([RECORDED["retrieval_query"]])

    client.build_search_queries(WORD, MEANING, "quote")

    assert json.loads(gemini.calls[0]["contents"]) == {"word": WORD, "meaning": MEANING, "target_method": "quote"}


def test_the_retry_sends_the_context_found_for_its_own_method():
    # G20
    other = [RetrievedItem(document="A line from a film.", metadata={"name": "Film Notes", "path": ""}, similarity=0.8)]
    asked = []

    def retrieve_for_method(method):
        asked.append(method)
        return other, []

    client, gemini, _ = make_client([RECORDED["insufficient_context"], RECORDED["quote_success"]], ["story", "quote"])

    content = client.generate(WORD, MEANING, TEXT_RESULTS, [], retrieve_for_method)

    assert asked == ["quote"]
    assert json.loads(content)["method"] == "quote"
    first, second = (json.loads(call["contents"])["retrieved_context"]["texts"] for call in gemini.calls)
    assert [text["name"] for text in first] == ["Travel Notes"]
    assert [text["name"] for text in second] == ["Film Notes"]
