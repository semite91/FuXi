import copy
import threading
import traceback
from pathlib import Path

import httpx
import pytest

from base import Resource, ResourceKind
from fakes import FIXTURES_DIR, FakeTmdbApi, load_fixture
from resources import http_retry, letterboxd_tmdb_resource
from resources.http_retry import MAX_ATTEMPTS, NETWORK_RETRY_SECONDS
from resources.letterboxd_tmdb_resource import (
    LOOKUP_WORKERS,
    MAX_ACTORS,
    LetterboxdTmdbResource,
    TmdbError,
    TmdbRefusedError,
    WatchedFileError,
    create_letterboxd_tmdb_resource,
)
from settings import MissingSettingError, Settings

WATCHED_FILE = FIXTURES_DIR / "watched.csv"
TMDB_TOKEN = "tmdb-test-read-access-token"
CSV_HEADER = "Date,Name,Year,Letterboxd URI"
LANTERN_ROW = "2026-01-05,The Lantern Keeper,2019,https://boxd.it/aB1c"
HARBOR_ROW = "2026-03-02,Paper Harbor,2015,https://boxd.it/aB3e"
LANTERN_ID = "1001"
LANTERN_SEARCH = "search:The Lantern Keeper"
LANTERN_DETAILS = f"movie:{LANTERN_ID}"
LANTERN_OVERVIEW = (
    "A lighthouse keeper on a remote island finds a stranger's diary washed ashore and follows "
    "its clues to a secret the village has kept for thirty years."
)
LANTERN_TEXT = "\n".join([
    "The Lantern Keeper (2019)",
    "Director: Mara Ellison",
    "Music: Tobias Rehn",
    "Screenplay: Mara Ellison, Jonas Whitfield",
    "Genres: Drama, Mystery",
    "Actors: Iris Calloway, Daniel Ferro, Noor Haddad, Samuel Okoye, Greta Lindqvist, Theo Marsh, "
    "Paloma Reyes, Kenji Arai, Odette Blanc, Ruben Castile",
    f"Summary: {LANTERN_OVERVIEW}",
])
FIXTURE_TITLES = ["The Lantern Keeper", "Winter Sun", "Paper Harbor", "The Lost Stars"]
WAIT_SECONDS = 5.0
PARALLEL_ROWS = 10


def recorded():
    return copy.deepcopy(load_fixture("tmdb_recorded.json"))


def make_api(data=None, failures=None) -> FakeTmdbApi:
    return FakeTmdbApi(data or recorded(), failures)


def make_resource(api, watched_file: Path = WATCHED_FILE, sleeps=None, clock=None, token: str = TMDB_TOKEN):
    sleeps = [] if sleeps is None else sleeps
    return LetterboxdTmdbResource(
        watched_file_factory=lambda: watched_file,
        token_factory=lambda: token,
        http_client_factory=api.client,
        sleep=sleeps.append,
        **({"clock": clock} if clock is not None else {}),
    )


def write_watched(tmp_path: Path, *rows: str, header: str = CSV_HEADER, encoding: str = "utf-8") -> Path:
    watched_file = tmp_path / "watched.csv"
    watched_file.write_text("\n".join([header, *rows]) + "\n", encoding=encoding)
    return watched_file


def names(documents) -> list[str]:
    return [document.metadata["name"] for document in documents]


def answer(status: int, headers=None) -> httpx.Response:
    return httpx.Response(status, headers=headers or {}, json={"success": False})


def recorded_answer(name: str, status: int) -> httpx.Response:
    return httpx.Response(status, json=recorded()[name])


def logged(error: BaseException) -> str:
    """The error as the embedding pipeline writes it to its log."""
    return f"{type(error).__name__}: {error}"


def with_results(query: str, *results: dict) -> dict:
    """The recorded answers with the query's search results replaced; each result starts as a Paper Harbor result."""
    data = recorded()
    base = data["search"]["Paper Harbor"]["results"][0]
    data["search"][query] = {**data["empty_search"], "results": [{**base, **result} for result in results]}
    return data


def searches(api) -> list[tuple[str, str]]:
    return [
        (request.url.params["query"], request.url.params["primary_release_year"])
        for request in api.requests
        if request.url.path == "/3/search/movie"
    ]


def test_each_watched_row_gives_its_name_year_and_watched_date():
    # Phase 5c C1
    api = make_api()

    documents = make_resource(api).read_documents()

    assert sorted(searches(api)) == sorted([
        ("The Lantern Keeper", "2019"), ("Kış Güneşi", "2021"), ("Paper Harbor", "2015"), ("Les Étoiles Perdues", "2008")
    ])
    assert [document.metadata["timestamp"] for document in documents] == [
        "2026-01-05", "2026-02-11", "2026-03-02", "2026-03-20"
    ]


def test_watched_file_with_a_bom_and_non_english_names_is_read_correctly(tmp_path):
    # Phase 5c C2
    watched_file = write_watched(
        tmp_path,
        "2026-02-11,Kış Güneşi,2021,https://boxd.it/aB2d",
        "2026-03-20,Les Étoiles Perdues,2008,https://boxd.it/aB4f",
        encoding="utf-8-sig",
    )
    assert watched_file.read_bytes().startswith(b"\xef\xbb\xbf")
    api = make_api()

    documents = make_resource(api, watched_file).read_documents()

    assert searches(api) and sorted(searches(api)) == sorted([("Kış Güneşi", "2021"), ("Les Étoiles Perdues", "2008")])
    assert [document.metadata["timestamp"] for document in documents] == ["2026-02-11", "2026-03-20"]


def test_missing_watched_file_fails_the_read_and_names_the_setting_without_the_path(tmp_path):
    # Phase 5c C3
    api = make_api()
    resource = make_resource(api, tmp_path / "absent" / "watched.csv")

    with pytest.raises(WatchedFileError, match="RAG_LETTERBOXD_WATCHED_FILE") as raised:
        resource.read_documents()

    assert str(tmp_path) not in str(raised.value)
    assert "watched.csv" not in str(raised.value)
    assert api.requests == []


@pytest.mark.parametrize(("header", "column"), [("Date,Year,Letterboxd URI", "Name"), ("Date,Name,Letterboxd URI", "Year")])
def test_watched_file_without_a_required_column_fails_and_names_the_column(tmp_path, header, column):
    # Phase 5c C4
    api = make_api()
    watched_file = write_watched(tmp_path, "2026-01-05,The Lantern Keeper,https://boxd.it/aB1c", header=header)

    with pytest.raises(WatchedFileError, match=f"RAG_LETTERBOXD_WATCHED_FILE file has no {column} column") as raised:
        make_resource(api, watched_file).read_documents()

    assert str(tmp_path) not in str(raised.value)
    assert api.requests == []


def test_row_with_an_empty_name_or_a_year_that_is_not_a_number_is_skipped_and_counted(tmp_path):
    # Phase 5c C5
    watched_file = write_watched(
        tmp_path,
        "2026-01-01,,2019,https://boxd.it/x1",
        LANTERN_ROW,
        "2026-01-02,Paper Harbor,n/a,https://boxd.it/x2",
        "2026-01-03,Paper Harbor,,https://boxd.it/x3",
        HARBOR_ROW,
    )
    api = make_api()
    resource = make_resource(api, watched_file)

    documents = resource.read_documents()

    assert names(documents) == ["The Lantern Keeper", "Paper Harbor"]
    assert resource.read_summary().startswith(
        "5 rows, 2 movies, 3 skipped rows (3 bad rows, 0 no match, 0 not found, 0 refused), 0 repeated rows,"
    )


def test_same_name_and_year_in_two_rows_asks_tmdb_once_and_makes_one_document(tmp_path):
    # Phase 5c C6
    watched_file = write_watched(tmp_path, LANTERN_ROW, HARBOR_ROW, "2026-04-09,The Lantern Keeper,2019,https://boxd.it/aB1c")
    api = make_api()
    resource = make_resource(api, watched_file)

    documents = resource.read_documents()

    assert names(documents) == ["The Lantern Keeper", "Paper Harbor"]
    assert api.routes.count(LANTERN_SEARCH) == 1
    assert api.routes.count(LANTERN_DETAILS) == 1
    assert documents[0].metadata["timestamp"] == "2026-01-05"  # the first row is the one read
    assert "3 rows, 2 movies, 0 skipped rows (0 bad rows, 0 no match, 0 not found, 0 refused), 1 repeated rows," in resource.read_summary()


def test_two_names_of_the_same_tmdb_movie_make_one_document_of_the_first_row(tmp_path):
    # Phase 5c C9
    data = with_results("Lantern Keeper", {"id": int(LANTERN_ID), "title": "The Lantern Keeper", "release_date": "2019-03-01"})
    # The first row's search is held until the later row's movie is read, so the later row finishes first.
    api = GatedTmdbApi(data, held_route="search:Lantern Keeper", release_route=LANTERN_DETAILS)
    watched_file = write_watched(tmp_path, "2026-04-09,Lantern Keeper,2019,https://boxd.it/aB9z", HARBOR_ROW, LANTERN_ROW)
    resource = make_resource(api, watched_file)

    documents = resource.read_documents()

    assert names(documents) == ["The Lantern Keeper", "Paper Harbor"]
    assert documents[0].metadata["timestamp"] == "2026-04-09"  # the first row in the file's order wins
    assert documents[0].text == LANTERN_TEXT
    assert api.routes.index(LANTERN_DETAILS) < api.routes.index("search:Lantern Keeper")
    assert resource.read_summary().startswith(
        "3 rows, 2 movies, 0 skipped rows (0 bad rows, 0 no match, 0 not found, 0 refused), 1 repeated rows,"
    )


def test_watched_file_with_only_the_header_gives_no_document_and_no_error(tmp_path):
    # Phase 5c C7
    api = make_api()
    resource = make_resource(api, write_watched(tmp_path))

    assert resource.read_documents() == []
    assert api.requests == []
    assert resource.read_summary().startswith("0 rows, 0 movies, 0 skipped rows")


@pytest.mark.parametrize("error_type", [PermissionError, FileNotFoundError])
def test_watched_file_that_cannot_be_opened_fails_and_names_the_setting_without_the_path(tmp_path, monkeypatch, error_type):
    # Phase 5c C8
    watched_file = write_watched(tmp_path, LANTERN_ROW)
    real_open = Path.open

    def refusing_open(path, *args, **kwargs):
        if path == watched_file:
            raise error_type(13, "The file cannot be opened", str(path))
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", refusing_open)
    api = make_api()

    with pytest.raises(WatchedFileError, match="RAG_LETTERBOXD_WATCHED_FILE") as raised:
        make_resource(api, watched_file).read_documents()

    monkeypatch.undo()
    printed = logged(raised.value) + "".join(traceback.format_exception(raised.value))
    assert str(tmp_path) not in printed
    assert "watched.csv" not in printed
    assert raised.value.__cause__ is None
    assert api.requests == []


def test_watched_file_that_fails_while_it_is_read_fails_and_names_the_setting_without_the_path(tmp_path, monkeypatch):
    # Phase 5c C8
    watched_file = write_watched(tmp_path, LANTERN_ROW)

    def failing_rows(reader):
        raise OSError(5, "The file cannot be read", str(watched_file))

    monkeypatch.setattr(letterboxd_tmdb_resource, "_watched_list", failing_rows)
    api = make_api()

    with pytest.raises(WatchedFileError, match="RAG_LETTERBOXD_WATCHED_FILE") as raised:
        make_resource(api, watched_file).read_documents()

    assert str(tmp_path) not in logged(raised.value)
    assert "watched.csv" not in logged(raised.value)
    assert api.requests == []


def test_empty_tmdb_token_fails_before_any_call_and_names_the_setting():
    # Phase 5c D1
    api = make_api()
    resource = LetterboxdTmdbResource(
        watched_file_factory=lambda: WATCHED_FILE,
        token_factory=Settings(tmdb_token="").require_tmdb_token,
        http_client_factory=api.client,
    )

    with pytest.raises(MissingSettingError, match="RAG_TMDB_TOKEN"):
        resource.read_documents()

    assert api.requests == []


def test_unset_settings_fail_only_when_the_movies_are_read():
    # Phase 5c B3
    resource = create_letterboxd_tmdb_resource(Settings())  # creating does not fail

    with pytest.raises(MissingSettingError, match="RAG_TMDB_TOKEN"):
        resource.read_documents()
    with pytest.raises(MissingSettingError, match="RAG_LETTERBOXD_WATCHED_FILE"):
        create_letterboxd_tmdb_resource(Settings(tmdb_token=TMDB_TOKEN)).read_documents()


def test_every_call_sends_the_bearer_token_and_never_puts_it_in_the_url():
    # Phase 5c D2
    api = make_api()

    make_resource(api).read_documents()

    assert len(api.requests) == 8  # a search and a details call per movie
    assert all(request.headers["Authorization"] == f"Bearer {TMDB_TOKEN}" for request in api.requests)
    assert all(TMDB_TOKEN not in str(request.url) for request in api.requests)
    assert all(request.url.host == "api.themoviedb.org" and request.url.scheme == "https" for request in api.requests)


def test_search_is_called_with_the_rows_name_year_and_english(tmp_path):
    # Phase 5c D3
    api = make_api()

    make_resource(api, write_watched(tmp_path, LANTERN_ROW)).read_documents()

    search = api.requests[0]
    assert search.method == "GET"
    assert search.url.path == "/3/search/movie"
    assert dict(search.url.params) == {
        "query": "The Lantern Keeper", "primary_release_year": "2019", "language": "en-US"
    }


def test_first_result_with_the_rows_year_is_taken_not_the_first_result(tmp_path):
    # Phase 5c D4
    api = make_api()
    assert [result["release_date"][:4] for result in api.recorded["search"]["The Lantern Keeper"]["results"]] == [
        "1987", "2019"
    ]

    documents = make_resource(api, write_watched(tmp_path, LANTERN_ROW)).read_documents()

    assert api.routes == [LANTERN_SEARCH, LANTERN_DETAILS]
    assert documents[0].text.startswith("The Lantern Keeper (2019)")


def test_result_with_the_rows_title_is_taken_before_an_earlier_result_of_the_same_year(tmp_path):
    # Phase 5c D4
    api = make_api(with_results(
        "paper harbor",
        {"id": 9010, "title": "Paper Harbor Nights", "original_title": "Paper Harbor Nights"},
        {"id": 1003, "title": " PAPER HARBOR ", "original_title": "Papirhavn"},  # letter case and outer spaces are ignored
    ))
    watched_file = write_watched(tmp_path, "2026-03-02,paper harbor,2015,https://boxd.it/aB3e")

    documents = make_resource(api, watched_file).read_documents()

    assert api.routes == ["search:paper harbor", "movie:1003"]
    assert names(documents) == ["Paper Harbor"]


def test_result_with_the_rows_original_title_is_taken_before_an_earlier_result_of_the_same_year(tmp_path):
    # Phase 5c D4
    api = make_api(with_results(
        "Kış Güneşi",
        {"id": 9011, "title": "Winter Sun Rising", "original_title": "Winter Sun Rising", "release_date": "2021-05-01"},
        {"id": 1002, "title": "Winter Sun", "original_title": "kış GÜNEŞi", "release_date": "2021-01-22"},
    ))
    watched_file = write_watched(tmp_path, "2026-02-11,Kış Güneşi,2021,https://boxd.it/aB2d")

    documents = make_resource(api, watched_file).read_documents()

    assert api.routes == ["search:Kış Güneşi", "movie:1002"]
    assert names(documents) == ["Winter Sun"]


def test_title_of_another_year_is_not_taken_and_the_first_result_of_the_rows_year_is_the_fallback(tmp_path):
    # Phase 5c D4
    api = make_api(with_results(
        "Harbor",
        {"id": 9012, "title": "Harbor", "original_title": "Harbor", "release_date": "1999-01-01"},
        {"id": 1003, "title": "Paper Harbor", "original_title": "Paper Harbor"},
        {"id": 9013, "title": "Harbor Lights", "original_title": "Harbor Lights"},
    ))
    watched_file = write_watched(tmp_path, "2026-03-02,Harbor,2015,https://boxd.it/aB3e")

    documents = make_resource(api, watched_file).read_documents()

    assert api.routes == ["search:Harbor", "movie:1003"]
    assert names(documents) == ["Paper Harbor"]


def routes_for_titles(tmp_path, row_name: str, tmdb_title: str) -> list[str]:
    """The calls made for a row whose search answers another title first, then the given title (movie 1003)."""
    api = make_api(with_results(
        row_name,
        {"id": 9010, "title": "Another Film", "original_title": "Another Film"},
        {"id": 1003, "title": tmdb_title, "original_title": "Papirhavn"},
    ))
    make_resource(api, write_watched(tmp_path, f"2026-03-02,{row_name},2015,https://boxd.it/aB3e")).read_documents()
    return api.routes


@pytest.mark.parametrize(("row_name", "tmdb_title"), [
    ("KIŞ", "Kış"),
    ("KIŞ", "Kis"),
    ("Kış", "Kis"),
    ("Kis", "KIŞ"),
    ("Kış Güneşi", "Kis Gunesi"),
    ("Kis Gunesi", "KIŞ GÜNEŞİ"),
    ("Çöğüş", "cogus"),
    ("COGUS", "ÇÖĞÜŞ"),
])
def test_turkish_letters_match_their_latin_forms_in_both_directions(tmp_path, row_name, tmdb_title):
    # Phase 5c D4
    assert routes_for_titles(tmp_path, row_name, tmdb_title) == [f"search:{row_name}", "movie:1003"]


@pytest.mark.parametrize(("row_name", "tmdb_title"), [
    ("İstanbul", "istanbul"),
    ("istanbul", "İSTANBUL"),
    ("ISTANBUL", "ıstanbul"),
    ("ıstanbul", "Istanbul"),
    ("İstanbul", "ISTANBUL"),
])
def test_dotted_and_dotless_i_in_both_cases_match_the_latin_i(tmp_path, row_name, tmdb_title):
    # Phase 5c D4
    assert routes_for_titles(tmp_path, row_name, tmdb_title) == [f"search:{row_name}", "movie:1003"]


def test_titles_that_differ_only_in_letter_case_match(tmp_path):
    # Phase 5c D4
    assert routes_for_titles(tmp_path, "paper HARBOR", "Paper harbor") == ["search:paper HARBOR", "movie:1003"]


@pytest.mark.parametrize(("row_name", "tmdb_title"), [("Kış", "Kuş"), ("Kis", "Kiss"), ("Étoile", "Etoile")])
def test_different_title_does_not_match_and_the_first_result_of_the_year_is_taken(tmp_path, row_name, tmdb_title):
    # Phase 5c D4
    assert routes_for_titles(tmp_path, row_name, tmdb_title) == [f"search:{row_name}", "movie:9010"]


@pytest.mark.parametrize("row", [
    "2026-05-01,Ghost Reel,2020,https://boxd.it/g1",  # the only result is from 2011
    "2026-05-02,Nowhere Film,2003,https://boxd.it/n1",  # no result at all
])
def test_row_without_a_result_of_its_year_is_skipped_and_counted(tmp_path, row):
    # Phase 5c D5
    api = make_api()
    resource = make_resource(api, write_watched(tmp_path, row, HARBOR_ROW))

    documents = resource.read_documents()

    assert names(documents) == ["Paper Harbor"]
    assert not any(route.startswith("movie:9") for route in api.routes)
    assert "2 rows, 1 movies, 1 skipped rows (0 bad rows, 1 no match, 0 not found, 0 refused)" in resource.read_summary()


def test_result_without_a_release_date_does_not_count_as_the_rows_year(tmp_path):
    # Phase 5c D6
    api = make_api()
    results = api.recorded["search"]["Undated Cut"]["results"]
    assert results[0]["release_date"] == "" and "release_date" not in results[1]
    resource = make_resource(api, write_watched(tmp_path, "2026-05-03,Undated Cut,2017,https://boxd.it/u1"))

    assert resource.read_documents() == []
    assert api.routes == ["search:Undated Cut"]
    assert "1 skipped rows (0 bad rows, 1 no match, 0 not found, 0 refused)" in resource.read_summary()


def test_details_are_asked_once_with_the_credits_in_english(tmp_path):
    # Phase 5c D7
    api = make_api()

    make_resource(api, write_watched(tmp_path, LANTERN_ROW)).read_documents()

    details = [request for request in api.requests if request.url.path != "/3/search/movie"]
    assert [request.url.path for request in details] == [f"/3/movie/{LANTERN_ID}"]
    assert dict(details[0].url.params) == {"append_to_response": "credits", "language": "en-US"}


def test_details_404_skips_the_movie_and_the_others_are_still_read(tmp_path):
    # Phase 5c D8
    api = make_api()
    watched_file = write_watched(tmp_path, LANTERN_ROW, "2026-05-04,Vanished Print,2012,https://boxd.it/v1", HARBOR_ROW)
    sleeps: list[float] = []
    resource = make_resource(api, watched_file, sleeps)

    documents = resource.read_documents()

    assert names(documents) == ["The Lantern Keeper", "Paper Harbor"]
    assert api.routes.count("movie:1404") == 1  # a 404 is not tried again
    assert sleeps == []
    assert "3 rows, 2 movies, 1 skipped rows (0 bad rows, 0 no match, 1 not found, 0 refused)" in resource.read_summary()


@pytest.mark.parametrize("status", [400, 422])
@pytest.mark.parametrize("route", [LANTERN_SEARCH, LANTERN_DETAILS])
def test_400_or_422_on_a_movies_search_or_details_skips_the_movie_and_the_others_are_still_read(tmp_path, route, status):
    # Phase 5c D8
    sleeps: list[float] = []
    api = make_api(failures={route: [answer(status)]})
    resource = make_resource(api, write_watched(tmp_path, LANTERN_ROW, HARBOR_ROW), sleeps)

    documents = resource.read_documents()

    assert names(documents) == ["Paper Harbor"]
    assert api.routes.count(route) == 1  # a refused request is not tried again
    assert sleeps == []
    assert "2 rows, 1 movies, 1 skipped rows (0 bad rows, 0 no match, 0 not found, 1 refused)" in resource.read_summary()


def test_404_on_the_search_call_fails_the_movie_resource(tmp_path):
    # Phase 5c D8
    api = make_api(failures={LANTERN_SEARCH: [answer(404)]})

    with pytest.raises(TmdbError) as raised:
        make_resource(api, write_watched(tmp_path, LANTERN_ROW, HARBOR_ROW)).read_documents()

    assert raised.value.status == 404


@pytest.mark.parametrize("route", [LANTERN_SEARCH, LANTERN_DETAILS])
def test_401_answer_fails_the_movie_resource(route):
    # Phase 5c D9
    sleeps: list[float] = []
    api = make_api(failures={route: [recorded_answer("unauthorized", 401)]})

    with pytest.raises(TmdbError) as raised:
        make_resource(api, sleeps=sleeps).read_documents()

    assert raised.value.status == 401
    assert api.routes.count(route) == 1  # a refused token is not tried again
    assert sleeps == []
    assert TMDB_TOKEN not in str(raised.value)


def test_rate_limit_waits_retry_after_and_tries_again():
    # Phase 5c D10
    sleeps: list[float] = []
    api = make_api(failures={LANTERN_SEARCH: [answer(429, {"Retry-After": "3"})]})

    documents = make_resource(api, sleeps=sleeps).read_documents()

    assert sleeps == [3.0]
    assert names(documents) == FIXTURE_TITLES


def retryable_failures():
    return [answer(500), answer(503), httpx.ConnectError("no route"), httpx.ReadError("reset"), httpx.ReadTimeout("slow")]


@pytest.mark.parametrize("failure", retryable_failures())
def test_server_error_dropped_connection_or_timeout_waits_and_tries_again(failure):
    # Phase 5c D11
    sleeps: list[float] = []
    api = make_api(failures={LANTERN_DETAILS: [failure]})

    documents = make_resource(api, sleeps=sleeps).read_documents()

    assert sleeps == [NETWORK_RETRY_SECONDS] == [1.0]
    assert names(documents) == FIXTURE_TITLES


@pytest.mark.parametrize("failure", retryable_failures())
def test_retries_wait_1_2_4_and_8_seconds_and_fail_the_source_after_5_attempts(tmp_path, failure):
    # Phase 5c D11
    sleeps: list[float] = []
    api = make_api(failures={LANTERN_SEARCH: [failure] * MAX_ATTEMPTS})

    with pytest.raises(TmdbError):
        make_resource(api, write_watched(tmp_path, LANTERN_ROW), sleeps).read_documents()

    assert sleeps == [1.0, 2.0, 4.0, 8.0]
    assert MAX_ATTEMPTS == 5
    assert api.routes.count(LANTERN_SEARCH) == MAX_ATTEMPTS


class GatedTmdbApi(FakeTmdbApi):
    """Holds one route's answer until another route has been answered, which only parallel lookups allow."""

    def __init__(self, recorded_data, held_route: str, release_route: str):
        super().__init__(recorded_data)
        self.held_route = held_route
        self.release_route = release_route
        self.released = threading.Event()

    def __call__(self, request):
        route = self._route(request)
        if route == self.held_route:
            assert self.released.wait(WAIT_SECONDS)
        response = super().__call__(request)
        if route == self.release_route:
            self.released.set()
        return response


def ten_movies(tmp_path) -> tuple[dict, Path, list[str]]:
    """Ten recorded movies and their watched.csv, made from the recorded Paper Harbor answers."""
    data = recorded()
    titles = [f"Parallel Film {number}" for number in range(1, PARALLEL_ROWS + 1)]
    for number, title in enumerate(titles, start=1):
        movie_id = 2000 + number
        search = copy.deepcopy(data["search"]["Paper Harbor"])
        search["results"][0].update(id=movie_id, title=title, original_title=title)
        data["search"][title] = search
        data["movies"][str(movie_id)] = {**copy.deepcopy(data["movies"]["1003"]), "id": movie_id, "title": title}
    rows = [f"2026-06-{number:02d},{title},2015,https://boxd.it/p{number}" for number, title in enumerate(titles, start=1)]
    return data, write_watched(tmp_path, *rows), titles


def test_ten_rows_are_looked_up_in_parallel_and_documents_keep_the_watched_order(tmp_path):
    # Phase 5c D12
    data, watched_file, titles = ten_movies(tmp_path)
    api = GatedTmdbApi(data, held_route=f"search:{titles[0]}", release_route=f"movie:{2000 + PARALLEL_ROWS}")

    documents = make_resource(api, watched_file).read_documents()

    assert LOOKUP_WORKERS == 4
    assert names(documents) == titles
    assert [document.metadata["timestamp"] for document in documents] == [
        f"2026-06-{number:02d}" for number in range(1, PARALLEL_ROWS + 1)
    ]
    assert api.routes.index(f"movie:{2000 + PARALLEL_ROWS}") < api.routes.index(f"search:{titles[0]}")


def test_read_summary_counts_rows_movies_skips_calls_waits_and_time(tmp_path):
    # Phase 5c D13
    watched_file = write_watched(
        tmp_path,
        LANTERN_ROW,
        "2026-01-02,Paper Harbor,n/a,https://boxd.it/x2",
        "2026-05-01,Ghost Reel,2020,https://boxd.it/g1",
        "2026-05-04,Vanished Print,2012,https://boxd.it/v1",
        HARBOR_ROW,
        LANTERN_ROW,
    )
    ticks = iter([100.0, 107.5])
    api = make_api(failures={LANTERN_SEARCH: [answer(429, {"Retry-After": "3"}), httpx.ReadError("connection reset")]})
    resource = make_resource(api, watched_file, clock=lambda: next(ticks))

    resource.read_documents()

    assert resource.read_summary() == (
        "6 rows, 2 movies, 3 skipped rows (1 bad rows, 1 no match, 1 not found, 0 refused), 1 repeated rows, "
        f"{len(api.requests)} calls, 1 rate limit waits (3.0 s), 1 network retries, 7.5 s"
    )
    assert len(api.requests) == 9


def test_read_summary_counts_a_refused_row_apart_from_a_row_that_is_not_found(tmp_path):
    # Phase 5c D13
    watched_file = write_watched(tmp_path, LANTERN_ROW, "2026-05-04,Vanished Print,2012,https://boxd.it/v1", HARBOR_ROW)
    api = make_api(failures={LANTERN_SEARCH: [answer(400)]})
    resource = make_resource(api, watched_file)

    resource.read_documents()

    assert resource.read_summary().startswith(
        "3 rows, 1 movies, 2 skipped rows (0 bad rows, 0 no match, 1 not found, 1 refused), 0 repeated rows, 5 calls,"
    )


def test_read_summary_is_kept_when_the_read_fails(tmp_path):
    # Phase 5c D13
    ticks = iter([10.0, 25.0])
    api = make_api(failures={LANTERN_SEARCH: [httpx.ReadError("reset")] * MAX_ATTEMPTS})
    resource = make_resource(api, write_watched(tmp_path, LANTERN_ROW), clock=lambda: next(ticks))

    with pytest.raises(TmdbError):
        resource.read_documents()

    assert resource.read_summary() == (
        "1 rows, 0 movies, 0 skipped rows (0 bad rows, 0 no match, 0 not found, 0 refused), 0 repeated rows, "
        f"{MAX_ATTEMPTS} calls, 0 rate limit waits (0.0 s), {MAX_ATTEMPTS - 1} network retries, 15.0 s"
    )


SEARCH_ENDPOINT = "/3/search/movie"
DETAILS_ENDPOINT = f"/3/movie/{LANTERN_ID}"


@pytest.mark.parametrize(("route", "failures", "kind", "endpoint"), [
    (LANTERN_SEARCH, [answer(401)], "401", SEARCH_ENDPOINT),
    (LANTERN_DETAILS, [answer(401)], "401", DETAILS_ENDPOINT),
    (LANTERN_SEARCH, [answer(403)], "403", SEARCH_ENDPOINT),
    (LANTERN_DETAILS, [answer(403)], "403", DETAILS_ENDPOINT),
    (LANTERN_SEARCH, [answer(404)], "404", SEARCH_ENDPOINT),
    (LANTERN_DETAILS, [answer(409)], "409", DETAILS_ENDPOINT),
    (LANTERN_SEARCH, [answer(503)] * MAX_ATTEMPTS, "503", SEARCH_ENDPOINT),
    (LANTERN_DETAILS, [answer(500)] * MAX_ATTEMPTS, "500", DETAILS_ENDPOINT),
    (LANTERN_SEARCH, [answer(429)] * MAX_ATTEMPTS, "429", SEARCH_ENDPOINT),
    (LANTERN_SEARCH, [httpx.ConnectError("no route to The Lantern Keeper")] * MAX_ATTEMPTS, "ConnectError", SEARCH_ENDPOINT),
    (LANTERN_DETAILS, [httpx.ReadTimeout("slow")] * MAX_ATTEMPTS, "ReadTimeout", DETAILS_ENDPOINT),
])
def test_tmdb_error_that_fails_the_source_holds_the_status_and_endpoint_not_the_name_or_token(
    tmp_path, route, failures, kind, endpoint
):
    # Phase 5c D16
    api = make_api(failures={route: failures})

    with pytest.raises(TmdbError) as raised:
        make_resource(api, write_watched(tmp_path, LANTERN_ROW)).read_documents()

    line = logged(raised.value)
    assert kind in line and endpoint in line
    assert raised.value.endpoint == endpoint
    for secret in ["Lantern", "Keeper", "query", "?", TMDB_TOKEN, "Bearer"]:
        assert secret not in line
    printed = "".join(traceback.format_exception(raised.value))
    assert "The Lantern Keeper" not in printed and "Lantern%20Keeper" not in printed and "Lantern+Keeper" not in printed
    assert TMDB_TOKEN not in printed
    assert api.routes.count(route) == len(failures)


@pytest.mark.parametrize("error_type", [
    httpx.DecodingError,
    httpx.TooManyRedirects,
    httpx.LocalProtocolError,
    httpx.UnsupportedProtocol,
    httpx.ProxyError,
    httpx.InvalidURL,
])
@pytest.mark.parametrize(("route", "endpoint"), [(LANTERN_SEARCH, SEARCH_ENDPOINT), (LANTERN_DETAILS, DETAILS_ENDPOINT)])
def test_any_other_httpx_error_fails_the_source_with_its_kind_and_endpoint_not_the_name_or_token(
    tmp_path, route, endpoint, error_type
):
    # Phase 5c D16
    sleeps: list[float] = []
    api = make_api(failures={route: [error_type(f"failed for The Lantern Keeper with Bearer {TMDB_TOKEN}")]})

    with pytest.raises(TmdbError) as raised:
        make_resource(api, write_watched(tmp_path, LANTERN_ROW), sleeps).read_documents()

    assert logged(raised.value) == f"TmdbError: TMDB call failed: {error_type.__name__} on {endpoint}"
    assert (raised.value.status, raised.value.endpoint) == (None, endpoint)
    printed = "".join(traceback.format_exception(raised.value))
    assert "Lantern" not in printed and TMDB_TOKEN not in printed
    assert raised.value.__cause__ is None
    assert api.routes.count(route) == 1  # an error that cannot pass by trying again is not tried again
    assert sleeps == []


def test_movie_id_that_makes_no_valid_address_fails_the_source_with_a_tmdb_error(tmp_path):
    # Phase 5c D16
    api = make_api(with_results("The Lantern Keeper", {"id": "The Lantern\nKeeper", "release_date": "2019-03-01"}))

    with pytest.raises(TmdbError) as raised:
        make_resource(api, write_watched(tmp_path, LANTERN_ROW)).read_documents()

    assert logged(raised.value) == "TmdbError: TMDB call failed: InvalidURL on an address that is not valid"
    printed = "".join(traceback.format_exception(raised.value))
    assert "Lantern" not in printed and TMDB_TOKEN not in printed
    assert raised.value.__cause__ is None
    assert api.routes == [LANTERN_SEARCH]


def test_network_error_that_cannot_pass_by_trying_again_is_raised_after_one_attempt(tmp_path):
    # Phase 5c D20
    sleeps: list[float] = []
    api = make_api(failures={LANTERN_SEARCH: [httpx.LocalProtocolError("a malformed request header")]})
    resource = make_resource(api, write_watched(tmp_path, LANTERN_ROW), sleeps)

    with pytest.raises(TmdbError, match="LocalProtocolError on /3/search/movie"):
        resource.read_documents()

    assert api.routes.count(LANTERN_SEARCH) == 1
    assert sleeps == []
    assert "1 calls, 0 rate limit waits (0.0 s), 0 network retries" in resource.read_summary()


@pytest.mark.parametrize("statuses", [(400, 400), (422, 422), (400, 422)])
@pytest.mark.parametrize("routes", [
    (LANTERN_SEARCH, "search:Paper Harbor"),
    (LANTERN_DETAILS, "movie:1003"),
    (LANTERN_SEARCH, "movie:1003"),
])
def test_rows_that_are_all_refused_fail_the_movie_resource_without_a_movie_name(tmp_path, routes, statuses):
    # Phase 5c D19
    sleeps: list[float] = []
    api = make_api(failures={route: [answer(status)] for route, status in zip(routes, statuses)})
    resource = make_resource(api, write_watched(tmp_path, LANTERN_ROW, HARBOR_ROW), sleeps)

    with pytest.raises(TmdbError) as raised:
        resource.read_documents()

    assert isinstance(raised.value, TmdbRefusedError)
    assert logged(raised.value) == "TmdbRefusedError: TMDB refused every movie request (400 or 422)"
    printed = "".join(traceback.format_exception(raised.value))
    for secret in ["Lantern", "Harbor", TMDB_TOKEN, "Bearer"]:
        assert secret not in printed
    assert raised.value.__cause__ is None
    assert all(api.routes.count(route) == 1 for route in routes)  # a refused request is not tried again
    assert sleeps == []
    assert "2 rows, 0 movies, 2 skipped rows (0 bad rows, 0 no match, 0 not found, 2 refused)" in resource.read_summary()


def test_refused_error_has_no_status_and_an_endpoint_that_is_text(tmp_path):
    # Phase 5c D19
    api = make_api(failures={LANTERN_SEARCH: [answer(400)]})

    with pytest.raises(TmdbRefusedError) as raised:
        make_resource(api, write_watched(tmp_path, LANTERN_ROW)).read_documents()

    assert (raised.value.status, raised.value.endpoint) == (None, "")
    assert raised.value.args == ("TMDB refused every movie request (400 or 422)",)


def test_single_refused_row_fails_the_movie_resource(tmp_path):
    # Phase 5c D19
    api = make_api(failures={LANTERN_SEARCH: [answer(400)]})
    watched_file = write_watched(tmp_path, "2026-01-01,,2019,https://boxd.it/x1", LANTERN_ROW)  # the bad row is not looked up

    with pytest.raises(TmdbRefusedError):
        make_resource(api, watched_file).read_documents()


@pytest.mark.parametrize(("other_row", "skip_counts"), [
    ("2026-05-01,Ghost Reel,2020,https://boxd.it/g1", "1 no match, 0 not found, 1 refused"),
    ("2026-05-04,Vanished Print,2012,https://boxd.it/v1", "0 no match, 1 not found, 1 refused"),  # a details 404
])
def test_refused_row_is_skipped_when_another_row_is_not_refused_even_without_a_movie(tmp_path, other_row, skip_counts):
    # Phase 5c D19
    api = make_api(failures={LANTERN_SEARCH: [answer(422)]})
    resource = make_resource(api, write_watched(tmp_path, LANTERN_ROW, other_row))

    assert resource.read_documents() == []
    assert f"2 rows, 0 movies, 2 skipped rows (0 bad rows, {skip_counts})" in resource.read_summary()


def test_rows_that_are_all_bad_give_no_document_and_no_error(tmp_path):
    # Phase 5c D19
    api = make_api()
    resource = make_resource(api, write_watched(tmp_path, "2026-01-01,,2019,https://boxd.it/x1"))

    assert resource.read_documents() == []
    assert api.requests == []


def body(content: str) -> httpx.Response:
    return httpx.Response(200, content=content.encode("utf-8"))


@pytest.mark.parametrize("content", ["<html>The Lantern Keeper</html>", "", "[]", "null", '"The Lantern Keeper"', "7"])
@pytest.mark.parametrize(("route", "endpoint"), [(LANTERN_SEARCH, SEARCH_ENDPOINT), (LANTERN_DETAILS, DETAILS_ENDPOINT)])
def test_200_answer_that_is_not_a_json_object_fails_the_source_with_the_endpoint_not_the_name(
    tmp_path, route, endpoint, content
):
    # Phase 5c D18
    sleeps: list[float] = []
    api = make_api(failures={route: [body(content)]})

    with pytest.raises(TmdbError) as raised:
        make_resource(api, write_watched(tmp_path, LANTERN_ROW), sleeps).read_documents()

    assert raised.value.endpoint == endpoint
    assert raised.value.status is None
    line = logged(raised.value)
    assert endpoint in line
    for secret in ["Lantern", "Keeper", "query", "?", TMDB_TOKEN, "Bearer"]:
        assert secret not in line
    printed = "".join(traceback.format_exception(raised.value))
    assert "The Lantern Keeper" not in printed and TMDB_TOKEN not in printed
    assert raised.value.__cause__ is None
    assert api.routes.count(route) == 1  # a wrongly shaped answer is not tried again
    assert sleeps == []


@pytest.mark.parametrize("results", [None, 7, "The Lantern Keeper", {"id": 1001}, ["The Lantern Keeper", 7, None, [1001]]])
def test_search_results_of_a_wrong_shape_count_as_no_result(tmp_path, results):
    # Phase 5c D18
    data = recorded()
    data["search"]["The Lantern Keeper"] = {**data["empty_search"], "results": results}
    resource = make_resource(make_api(data), write_watched(tmp_path, LANTERN_ROW, HARBOR_ROW))

    assert names(resource.read_documents()) == ["Paper Harbor"]
    assert "2 rows, 1 movies, 1 skipped rows (0 bad rows, 1 no match, 0 not found, 0 refused)" in resource.read_summary()


@pytest.mark.parametrize("credits", [
    ["crew"],
    "crew",
    7,
    {"crew": {"name": "Mara Ellison", "job": "Director"}, "cast": "Iris Calloway"},
    {"crew": ["Mara Ellison", 7, None, ["Director"]], "cast": [None, "Iris Calloway", 7]},
    {"crew": [{"name": 7, "job": ["Director"]}], "cast": [{"name": None}]},
])
def test_details_parts_of_a_wrong_shape_count_as_missing(tmp_path, credits):
    # Phase 5c D18
    def change(movie):
        movie.update(credits=credits, genres={"name": "Drama"}, overview=["A summary"], title=7)

    document = lantern_document(tmp_path, change)

    assert document.text == "The Lantern Keeper (2019)"
    assert document.metadata == {
        "name": "The Lantern Keeper", "path": "", "director": "", "musician": "", "genre": "", "timestamp": "2026-01-05",
        "type": "text",
    }


def test_read_summary_of_a_failed_read_counts_the_movies_and_skips_finished_before_the_failure(tmp_path):
    # Phase 5c D17
    watched_file = write_watched(
        tmp_path,
        LANTERN_ROW,
        "2026-01-02,Paper Harbor,n/a,https://boxd.it/x2",
        "2026-05-01,Ghost Reel,2020,https://boxd.it/g1",
        "2026-05-04,Vanished Print,2012,https://boxd.it/v1",
        HARBOR_ROW,  # the last row fails, so the rows before it have finished when the error is raised
    )
    api = make_api(failures={"search:Paper Harbor": [recorded_answer("unauthorized", 401)]})
    resource = make_resource(api, watched_file)

    with pytest.raises(TmdbError):
        resource.read_documents()

    assert resource.read_summary().startswith(
        "5 rows, 1 movies, 3 skipped rows (1 bad rows, 1 no match, 1 not found, 0 refused), 0 repeated rows, 6 calls,"
    )


def test_second_read_after_a_failed_read_starts_its_counts_again(tmp_path):
    # Phase 5c D17
    watched_file = write_watched(tmp_path, LANTERN_ROW, HARBOR_ROW)
    api = make_api(failures={"search:Paper Harbor": [recorded_answer("unauthorized", 401)]})
    resource = make_resource(api, watched_file)
    with pytest.raises(TmdbError):
        resource.read_documents()

    resource.read_documents()

    assert resource.read_summary().startswith("2 rows, 2 movies, 0 skipped rows (0 bad rows, 0 no match, 0 not found, 0 refused)")


def test_second_read_starts_its_summary_again():
    # Phase 5c D13
    resource = make_resource(make_api())

    resource.read_documents()
    resource.read_documents()

    assert resource.read_summary().startswith("4 rows, 4 movies, 0 skipped rows (0 bad rows, 0 no match, 0 not found, 0 refused), 0 repeated rows, 8 calls,")


def test_movie_resource_implements_the_resource_base_as_a_text_source_with_the_shared_retry_helper():
    # Phase 5c D14
    resource = make_resource(make_api())

    assert isinstance(resource, Resource)
    assert (resource.name, resource.kind) == ("letterboxd_tmdb", ResourceKind.TEXT)
    assert letterboxd_tmdb_resource.call_with_retry is http_retry.call_with_retry
    assert letterboxd_tmdb_resource.http_retry_wait is http_retry.http_retry_wait
    assert letterboxd_tmdb_resource.ReadStats is http_retry.ReadStats


def lantern_document(tmp_path, change=None):
    data = recorded()
    if change:
        change(data["movies"][LANTERN_ID])
    return make_resource(make_api(data), write_watched(tmp_path, LANTERN_ROW)).read_documents()[0]


def test_document_text_has_the_title_year_and_every_line(tmp_path):
    # Phase 5c E1
    assert lantern_document(tmp_path).text == LANTERN_TEXT


def test_director_music_and_screenplay_come_from_the_right_crew_jobs(tmp_path):
    # Phase 5c E2
    lines = lantern_document(tmp_path).text.splitlines()

    assert "Director: Mara Ellison" in lines  # not the Assistant Director
    assert "Music: Tobias Rehn" in lines  # not the Music Supervisor
    assert "Screenplay: Mara Ellison, Jonas Whitfield" in lines  # not the Novel's writer
    assert not any(name in "\n".join(lines) for name in ["Piet Vandermeer", "Lena Okafor", "Ada Brennan", "Sofia Marchetti"])


def test_screenplay_job_outside_the_writing_department_is_not_listed(tmp_path):
    # Phase 5c E2
    def change(movie):
        movie["credits"]["crew"].append({"name": "Hal Brandt", "department": "Production", "job": "Writer"})

    assert "Hal Brandt" not in lantern_document(tmp_path, change).text


def test_first_ten_of_fifteen_actors_are_listed_in_tmdbs_order(tmp_path):
    # Phase 5c E3
    cast = recorded()["movies"][LANTERN_ID]["credits"]["cast"]
    assert len(cast) == 15

    actors_line = lantern_document(tmp_path).text.splitlines()[5]

    assert MAX_ACTORS == 10
    assert actors_line == "Actors: " + ", ".join(actor["name"] for actor in cast[:10])


def test_person_listed_twice_in_a_role_appears_once(tmp_path):
    # Phase 5c E4
    crew = recorded()["movies"][LANTERN_ID]["credits"]["crew"]
    assert [member["job"] for member in crew if member["name"] == "Jonas Whitfield"] == ["Screenplay", "Writer"]

    document = lantern_document(tmp_path)

    assert document.text.count("Jonas Whitfield") == 1


def test_actor_listed_twice_appears_once_and_ten_actors_are_still_listed(tmp_path):
    # Phase 5c E4
    def change(movie):
        cast = movie["credits"]["cast"]
        cast.insert(1, {**cast[0], "character": "Narrator"})

    actors = lantern_document(tmp_path, change).text.splitlines()[5].removeprefix("Actors: ").split(", ")

    assert len(actors) == len(set(actors)) == 10


def test_movie_without_a_composer_or_an_overview_leaves_that_line_out():
    # Phase 5c E5
    documents = {document.metadata["name"]: document for document in make_resource(make_api()).read_documents()}

    assert documents["Winter Sun"].text.splitlines() == [
        "Winter Sun (2021)",
        "Director: Selin Yıldız",
        "Screenplay: Çağan Öztürk",
        "Genres: Drama, Family",
        "Actors: Elif Karaca, Mert Aydın",
        "Summary: Karlı bir kasabada iki kardeş, babalarının eski fırınını yeniden açmaya çalışır.",
    ]
    assert documents["Paper Harbor"].text.splitlines() == [
        "Paper Harbor (2015)",
        "Director: Nell Ashby",
        "Music: Oskar Lund",
        "Genres: Comedy",
        "Actors: Hugh Pemberton",
    ]


def test_movie_without_credits_and_genres_is_still_a_document(tmp_path):
    # Phase 5c E5
    def change(movie):
        movie.update(credits={}, genres=[], overview=None)

    document = lantern_document(tmp_path, change)

    assert document.text == "The Lantern Keeper (2019)"
    assert document.metadata == {
        "name": "The Lantern Keeper", "path": "", "director": "", "musician": "", "genre": "", "timestamp": "2026-01-05",
        "type": "text",
    }


def test_metadata_has_name_empty_path_director_musician_genre_timestamp_and_type_as_strings(tmp_path):
    # Phase 5c E6
    def change(movie):
        movie["credits"]["crew"].append({"name": "Ines Varga", "department": "Directing", "job": "Director"})

    metadata = lantern_document(tmp_path, change).metadata

    assert metadata == {
        "name": "The Lantern Keeper",
        "path": "",
        "director": "Mara Ellison, Ines Varga",
        "musician": "Tobias Rehn",
        "genre": "Drama, Mystery",
        "timestamp": "2026-01-05",
        "type": "text",
    }
    assert all(isinstance(value, str) for value in metadata.values())


@pytest.mark.parametrize(("header", "row"), [
    ("Name,Year", "The Lantern Keeper,2019"),  # no Date column
    (CSV_HEADER, "yesterday,The Lantern Keeper,2019,https://boxd.it/aB1c"),  # not a date
    (CSV_HEADER, ",The Lantern Keeper,2019,https://boxd.it/aB1c"),
])
def test_missing_or_unreadable_watched_date_gives_an_empty_timestamp(tmp_path, header, row):
    # Phase 5c E6
    watched_file = write_watched(tmp_path, row, header=header)

    document = make_resource(make_api(), watched_file).read_documents()[0]

    assert document.metadata["timestamp"] == ""
