import json
import random
from pathlib import Path

import pytest
from google.genai import errors

from base import RetrievedItem
from fakes import FakeGeminiClient, ScriptedRandom, load_fixture
from llm_client import METHODS, PROMPTS_DIR, LlmClient
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


def prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def make_client(answers, choices=None, settings=SETTINGS):
    gemini = FakeGeminiClient(answers)
    random_source = ScriptedRandom(choices or [])
    client = LlmClient(settings, gemini_client_factory=lambda: gemini, random_source=random_source)
    return client, gemini, random_source


def generate(client):
    return client.generate(WORD, MEANING, TEXT_RESULTS, [])


def grounded(config) -> bool:
    return bool(config.tools) and config.tools[0].google_search is not None


def test_search_query_sends_retrieval_prompt_with_word_and_meaning():
    # G1
    client, gemini, _ = make_client([RECORDED["retrieval_query"]])

    client.build_search_query(WORD, MEANING)

    call = gemini.calls[0]
    assert call["config"].system_instruction == prompt("retrieval.txt")
    assert json.loads(call["contents"]) == {"word": WORD, "meaning": MEANING}


def test_search_query_uses_geminis_query():
    # G2
    client, _, _ = make_client([RECORDED["retrieval_query"]])

    assert client.build_search_query(WORD, MEANING).startswith("unexpected discoveries")


@pytest.mark.parametrize("answer", [RECORDED["retrieval_invalid"], "", '{"query": ""}', errors.ServerError(503, {})])
def test_invalid_search_answer_falls_back_to_word_and_meaning(answer):
    # G3
    client, _, _ = make_client([answer])

    assert client.build_search_query(WORD, MEANING) == f"{WORD}: {MEANING}"


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
def test_web_methods_use_web_prompt_with_google_search(method):
    # G6
    client, gemini, _ = make_client([RECORDED[f"{method}_success"]], [method])

    generate(client)

    config = gemini.calls[0]["config"]
    assert config.system_instruction == prompt("llm_web.txt")
    assert grounded(config)


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

    client.build_search_query(WORD, MEANING)
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


def test_photo_success_gives_image_url_content():
    # G10
    client, _, _ = make_client([RECORDED["photo_success"]], ["photo"])

    assert json.loads(generate(client)) == {
        "method": "photo",
        "image_url": "https://upload.wikimedia.org/wikipedia/commons/a/a9/Example.jpg",
    }


def test_music_success_gives_song_content():
    # G11
    client, _, _ = make_client([RECORDED["music_success"]], ["music"])

    assert json.loads(generate(client)) == {
        "method": "music",
        "song_title": "Serendipity",
        "artist": "BTS",
        "song_url": "https://open.spotify.com/track/4d8b0ZFHJaGG4H3CSHfSwV",
        "lyrics_excerpt": "All of this is serendipity",
    }


@pytest.mark.parametrize(("method", "answer"), [("photo", "photo_http_url"), ("music", "music_bad_url")])
def test_non_https_url_counts_as_insufficient_context(method, answer):
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


def test_refused_google_search_counts_as_failed_method():
    # G15
    refused = errors.ClientError(
        400, {"error": {"code": 400, "message": "Search Grounding is not supported.", "status": "INVALID_ARGUMENT"}}
    )
    client, gemini, _ = make_client([refused, RECORDED["story_success"]], ["photo", "story"])

    assert json.loads(generate(client))["method"] == "story"
    assert not gemini.calls[1]["config"].tools


def test_missing_gemini_key_gives_no_content_and_names_the_key(caplog):
    # B5
    client = LlmClient(Settings(), random_source=ScriptedRandom(["story", "quote"]))

    assert client.build_search_query(WORD, MEANING) == f"{WORD}: {MEANING}"
    assert generate(client) is None
    assert "RAG_GEMINI_API_KEY" in caplog.text


def test_missing_key_error_is_raised_only_when_the_client_is_used():
    # B5
    client = LlmClient(Settings())

    with pytest.raises(MissingSettingError, match="RAG_GEMINI_API_KEY"):
        client.gemini_client()


def test_each_prompt_file_is_read_once_over_several_calls(monkeypatch, tmp_path):
    # G18
    for name in ("retrieval.txt", "llm.txt", "llm_web.txt"):
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
    )

    for _ in range(2):
        client.build_search_query(WORD, MEANING)
        generate(client)
    generate(client)

    assert sorted(reads) == ["llm.txt", "llm_web.txt", "retrieval.txt"]
    assert gemini.calls[-1]["config"].system_instruction == "prompt llm_web.txt"


def test_missing_web_prompt_does_not_break_text_methods_or_the_search_query(tmp_path):
    # G19
    for name in ("retrieval.txt", "llm.txt"):
        (tmp_path / name).write_text(f"prompt {name}", encoding="utf-8")
    gemini = FakeGeminiClient([RECORDED["retrieval_query"], RECORDED["story_success"]])
    client = LlmClient(
        SETTINGS, gemini_client_factory=lambda: gemini, random_source=ScriptedRandom(["story"]), prompts_dir=tmp_path
    )

    query = client.build_search_query(WORD, MEANING)
    content = generate(client)

    assert query.startswith("unexpected discoveries")
    assert json.loads(content)["method"] == "story"
    assert [call["config"].system_instruction for call in gemini.calls] == ["prompt retrieval.txt", "prompt llm.txt"]
