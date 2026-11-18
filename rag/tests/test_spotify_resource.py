"""Phase 6e (test_scenarios_2026_11_18_18_30) sections D, E and F: the Spotify resource reads the chosen playlist."""

import copy
from collections.abc import Callable
from urllib.parse import parse_qs

import httpx
import pytest

from base import Resource, ResourceKind, ResourceSkipped
from fakes import load_fixture
from resources.http_retry import MAX_ATTEMPTS, NETWORK_RETRY_SECONDS
from resources.spotify_resource import (
    SpotifyClient,
    SpotifyConnection,
    SpotifyError,
    SpotifyPlaylistNotFound,
    SpotifyResource,
    SpotifySignInError,
    SpotifyTokenRejected,
    create_spotify_resource,
)
from settings import MissingSettingError, Settings
from settings_store import SettingsStoreError, SpotifyRows

CLIENT_ID = "spotify-client-id-of-a-test"
CLIENT_SECRET = "spotify-client-secret-of-a-test"
REFRESH_TOKEN = "AQD-refresh-token-of-a-test"
ACCESS_TOKEN = "spotify-test-access-token"
PLAYLIST_ID = "37i9dQZF1DXcBWIGoYBM5M"
TOKEN_HOST = "accounts.spotify.com"
ITEMS_PATH = f"/v1/playlists/{PLAYLIST_ID}/items"
ITEMS_URL = f"https://api.spotify.com{ITEMS_PATH}"
TOKEN_REJECTED = "Spotify token rejected: connect Spotify again on the Settings page"
PLAYLIST_NOT_FOUND = "Spotify playlist not found: choose the playlist again on the Settings page"
SONG_NAMES = ["Glass Harbor Lights", "Paper Moons", "Saltwater", "Winter Radio"]
SECRETS = [CLIENT_SECRET, REFRESH_TOKEN, ACCESS_TOKEN]


def recorded():
    return copy.deepcopy(load_fixture("spotify_recorded.json"))


class FakeSpotify:
    """Answers Spotify's token address and the playlist items address from the recorded JSON."""

    def __init__(self) -> None:
        self.data = recorded()
        self.requests: list[httpx.Request] = []
        self.token: Callable[[], httpx.Response] = lambda: httpx.Response(200, json=self.data["token"])
        self.pages: dict[int, Callable[[], httpx.Response]] = {}
        self.page_override: Callable[[httpx.Request], httpx.Response] | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == TOKEN_HOST:
            return self.token()
        if self.page_override is not None:
            return self.page_override(request)
        offset = int(request.url.params.get("offset", "0"))
        if offset in self.pages:
            return self.pages[offset]()
        return httpx.Response(200, json=self.data["items_pages"][str(offset)])

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))

    @property
    def token_requests(self) -> list[httpx.Request]:
        return [request for request in self.requests if request.url.host == TOKEN_HOST]

    @property
    def page_requests(self) -> list[httpx.Request]:
        return [request for request in self.requests if request.url.host != TOKEN_HOST]


def make_resource(
    api: FakeSpotify, sleeps: list[float] | None = None, save_refresh_token=lambda _token: None, **connection
) -> SpotifyResource:
    values = {"playlist_id": PLAYLIST_ID, "refresh_token": REFRESH_TOKEN, "client": SpotifyClient(CLIENT_ID, CLIENT_SECRET)}
    values.update(connection)
    clock_ticks = iter(range(0, 1000, 2))
    return SpotifyResource(
        connection_factory=lambda: SpotifyConnection(**values),
        http_client_factory=api.client,
        sleep=(sleeps if sleeps is not None else []).append,
        clock=lambda: float(next(clock_ticks)),
        save_refresh_token=save_refresh_token,
    )


def read(api: FakeSpotify, **connection):
    return make_resource(api, **connection).read_documents()


def errors_of(api: FakeSpotify, error_type=SpotifyError) -> str:
    with pytest.raises(error_type) as caught:
        read(api)
    return str(caught.value)


def assert_no_secret(message: str) -> None:
    for secret in SECRETS:
        assert secret not in message


# ---------------------------------------------------------------- D: the sign-in and the settings


def test_d1_refresh_token_is_posted_with_the_basic_header_before_any_playlist_call():
    api = FakeSpotify()

    read(api)

    first = api.requests[0]
    assert first.method == "POST" and str(first.url) == "https://accounts.spotify.com/api/token"
    assert parse_qs(first.content.decode()) == {"grant_type": ["refresh_token"], "refresh_token": [REFRESH_TOKEN]}
    assert first.headers["Authorization"] == "Basic c3BvdGlmeS1jbGllbnQtaWQtb2YtYS10ZXN0OnNwb3RpZnktY2xpZW50LXNlY3JldC1vZi1hLXRlc3Q="
    assert all(request.url.host == "api.spotify.com" for request in api.requests[1:])


def test_d2_playlist_calls_carry_the_bearer_token_and_it_is_not_in_the_url():
    api = FakeSpotify()

    read(api)

    for request in api.page_requests:
        assert request.headers["Authorization"] == f"Bearer {ACCESS_TOKEN}"
        assert ACCESS_TOKEN not in str(request.url)


def test_d3_a_new_refresh_token_is_saved_and_the_read_goes_on():
    api = FakeSpotify()
    api.token = lambda: httpx.Response(200, json=api.data["token_with_refresh_token"])
    saved: list[str] = []

    documents = make_resource(api, save_refresh_token=saved.append).read_documents()

    assert saved == ["spotify-test-rotated-refresh-token"]
    assert len(documents) == 4


def test_d3_the_same_or_no_refresh_token_is_not_saved():
    api = FakeSpotify()
    saved: list[str] = []
    api.token = lambda: httpx.Response(200, json={**api.data["token_with_refresh_token"], "refresh_token": REFRESH_TOKEN})
    make_resource(api, save_refresh_token=saved.append).read_documents()
    api.token = lambda: httpx.Response(200, json={"access_token": ACCESS_TOKEN})
    make_resource(api, save_refresh_token=saved.append).read_documents()

    assert saved == []


def test_d3_a_failed_save_of_the_new_refresh_token_does_not_fail_the_read():
    api = FakeSpotify()
    api.token = lambda: httpx.Response(200, json=api.data["token_with_refresh_token"])

    def failing_save(_token: str) -> None:
        raise SettingsStoreError("the Settings table could not be written: OperationalError")

    assert len(make_resource(api, save_refresh_token=failing_save).read_documents()) == 4


def test_d4_not_connected_is_skipped():
    for rows in (SpotifyRows(refresh_token=None, playlist_id=None), SpotifyRows(refresh_token=None, playlist_id=PLAYLIST_ID)):
        resource = create_spotify_resource(settings(), read_rows=lambda _settings, rows=rows: rows)
        with pytest.raises(ResourceSkipped, match="^not connected$"):
            resource.read_documents()


def test_d5_connected_without_a_playlist_is_skipped():
    resource = create_spotify_resource(settings(), read_rows=lambda _settings: SpotifyRows(REFRESH_TOKEN, None))

    with pytest.raises(ResourceSkipped, match="^no playlist chosen$"):
        resource.read_documents()


def test_d6_a_skipped_resource_makes_no_call():
    api = FakeSpotify()
    resource = create_spotify_resource(
        settings(), read_rows=lambda _settings: SpotifyRows(None, None), http_client_factory=api.client
    )

    with pytest.raises(ResourceSkipped):
        resource.read_documents()

    assert api.requests == []


def test_d7_invalid_grant_asks_for_a_new_sign_in():
    api = FakeSpotify()
    api.token = lambda: httpx.Response(400, json=api.data["invalid_grant"])

    message = errors_of(api, SpotifyTokenRejected)

    assert message == TOKEN_REJECTED
    assert len(api.page_requests) == 0


@pytest.mark.parametrize("status", [400, 401])
def test_d7_invalid_client_asks_to_check_the_client_keys(status):
    api = FakeSpotify()
    api.token = lambda: httpx.Response(status, json=api.data["invalid_client"])

    message = errors_of(api, SpotifySignInError)

    assert "SPOTIFY_CLIENT_ID" in message and "SPOTIFY_CLIENT_SECRET" in message
    assert_no_secret(message)


@pytest.mark.parametrize("body", [{"error": "invalid_request"}, {}, "not json"])
def test_d7_another_refusal_names_the_status_and_error_without_asking_for_a_new_sign_in(body):
    api = FakeSpotify()
    api.token = lambda: httpx.Response(400, json=body) if body != "not json" else httpx.Response(400, text="<html>")

    with pytest.raises(SpotifySignInError) as caught:
        read(api)

    assert not isinstance(caught.value, SpotifyTokenRejected)
    assert "400" in str(caught.value) and "again" not in str(caught.value)
    assert_no_secret(str(caught.value))


def test_d8_a_401_on_a_playlist_call_asks_for_a_new_sign_in():
    api = FakeSpotify()
    api.pages[0] = lambda: httpx.Response(401, json=api.data["unauthorized"])

    assert errors_of(api, SpotifyTokenRejected) == TOKEN_REJECTED


@pytest.mark.parametrize("missing", ["client_id", "client_secret"])
def test_d9_an_empty_client_key_fails_naming_only_that_key(missing):
    resource = create_spotify_resource(
        settings(**{f"spotify_{missing}": None}), read_rows=lambda _settings: SpotifyRows(REFRESH_TOKEN, PLAYLIST_ID)
    )

    with pytest.raises(MissingSettingError) as caught:
        resource.read_documents()

    assert str(caught.value) == f"SPOTIFY_{missing.upper()} is not set"


@pytest.mark.parametrize("status", [403, 404])
def test_d10_a_playlist_that_is_not_visible_fails_with_the_choose_again_message(status):
    api = FakeSpotify()
    api.pages[0] = lambda: httpx.Response(status, json=api.data["forbidden"])

    assert errors_of(api, SpotifyPlaylistNotFound) == PLAYLIST_NOT_FOUND


def test_d11_an_unreadable_settings_table_fails_the_resource():
    def unreadable(_settings):
        raise SettingsStoreError("the Settings table could not be read: OperationalError")

    resource = create_spotify_resource(settings(), read_rows=unreadable)

    with pytest.raises(SettingsStoreError, match="OperationalError"):
        resource.read_documents()


@pytest.mark.parametrize(
    "answer",
    [
        lambda: httpx.Response(500, json={}),
        lambda: (_ for _ in ()).throw(httpx.ReadTimeout("timed out")),
        lambda: (_ for _ in ()).throw(httpx.RemoteProtocolError("dropped")),
    ],
)
def test_d12_a_refresh_call_that_fails_is_not_tried_again(answer):
    api = FakeSpotify()
    api.token = answer
    sleeps: list[float] = []

    with pytest.raises(SpotifyError):
        make_resource(api, sleeps).read_documents()

    assert len(api.token_requests) == 1 and sleeps == []


def test_d12_a_429_on_the_refresh_call_is_waited_for_and_tried_again():
    api = FakeSpotify()
    answers = iter([httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200, json=api.data["token"])])
    api.token = lambda: next(answers)
    sleeps: list[float] = []

    make_resource(api, sleeps).read_documents()

    assert len(api.token_requests) == 2 and sleeps == [3.0]


def test_d13_a_failed_sign_in_message_holds_no_token_and_no_secret():
    api = FakeSpotify()
    api.token = lambda: httpx.Response(500, json={"error": CLIENT_SECRET + REFRESH_TOKEN})

    with pytest.raises(SpotifyError) as caught:
        read(api)

    assert_no_secret(str(caught.value))
    assert "/api/token" in str(caught.value)


# ---------------------------------------------------------------- E: the playlist songs


def test_e1_three_pages_are_read_by_following_next_and_every_song_once():
    api = FakeSpotify()

    documents = read(api)

    assert [document.metadata["name"] for document in documents] == SONG_NAMES
    pages = api.page_requests
    assert [request.url.path for request in pages] == [ITEMS_PATH] * 3
    assert [request.url.params.get("offset") for request in pages] == [None, "50", "100"]
    assert pages[0].url.params["limit"] == "50"


def test_e2_a_last_page_without_next_asks_no_more_pages():
    api = FakeSpotify()

    read(api)

    assert len(api.page_requests) == 3


@pytest.mark.parametrize(
    "next_link",
    [
        "https://evil.example/v1/playlists/" + PLAYLIST_ID + "/items?offset=50",
        "http://api.spotify.com" + ITEMS_PATH + "?offset=50",
        "https://api.spotify.com/v1/me/tracks?offset=50",
        "https://api.spotify.com/v1/playlists/other/items?offset=50",
        "https://user@api.spotify.com" + ITEMS_PATH + "?offset=50",
        ITEMS_URL + "?offset=0",
        ITEMS_URL,
        ITEMS_URL + "?offset=abc",
        42,
    ],
)
def test_e3_a_next_link_that_cannot_be_followed_fails_with_the_endpoint_and_not_the_link(next_link):
    api = FakeSpotify()
    first = api.data["items_pages"]["0"]
    first["next"] = next_link
    api.pages[0] = lambda: httpx.Response(200, json=first)

    message = errors_of(api)

    assert ITEMS_PATH in message and "evil" not in message and "?" not in message


def test_e3_a_next_link_already_followed_fails():
    api = FakeSpotify()
    page = api.data["items_pages"]["50"]
    page["next"] = ITEMS_URL + "?offset=50&limit=50"
    api.pages[50] = lambda: httpx.Response(200, json=page)

    assert "followed" in errors_of(api)


def test_e4_an_empty_playlist_gives_no_document_and_no_error():
    api = FakeSpotify()
    api.pages[0] = lambda: httpx.Response(200, json=api.data["empty_items"])

    assert read(api) == []


def test_e5_items_that_are_not_songs_are_skipped_and_counted():
    api = FakeSpotify()
    resource = make_resource(api)

    documents = resource.read_documents()

    assert len(documents) == 4
    summary = resource.read_summary()
    assert "9 items" in summary and "4 songs" in summary and "4 skipped items" in summary
    assert "1 not a song" in summary and "1 no track" in summary and "1 no name" in summary and "1 local file" in summary


def test_e6_the_same_track_twice_makes_one_document_and_counts_the_repeat():
    api = FakeSpotify()
    resource = make_resource(api)

    documents = resource.read_documents()

    assert [d.metadata["name"] for d in documents].count("Glass Harbor Lights") == 1
    assert "1 repeated items" in resource.read_summary()


def test_e6_the_first_item_of_a_repeated_track_is_kept():
    api = FakeSpotify()

    documents = read(api)

    assert documents[0].metadata["timestamp"] == "2026-10-02T18:20:11Z"


def test_e7_a_429_with_retry_after_waits_and_tries_again():
    api = FakeSpotify()
    answers = iter([httpx.Response(429, headers={"Retry-After": "7"})])
    api.pages[0] = lambda: next(answers, None) or httpx.Response(200, json=api.data["items_pages"]["0"])
    sleeps: list[float] = []

    documents = make_resource(api, sleeps).read_documents()

    assert sleeps == [7.0] and len(documents) == 4


@pytest.mark.parametrize(
    "answer",
    [
        lambda: httpx.Response(503, json={}),
        lambda: (_ for _ in ()).throw(httpx.ReadTimeout("timed out")),
        lambda: (_ for _ in ()).throw(httpx.RemoteProtocolError("dropped")),
    ],
)
def test_e8_a_server_error_or_network_failure_backs_off_then_fails_after_five_attempts(answer):
    api = FakeSpotify()
    api.pages[0] = answer
    sleeps: list[float] = []

    with pytest.raises(SpotifyError):
        make_resource(api, sleeps).read_documents()

    assert sleeps == [NETWORK_RETRY_SECONDS * 2**attempt for attempt in range(MAX_ATTEMPTS - 1)]
    assert len(api.page_requests) == MAX_ATTEMPTS


@pytest.mark.parametrize("body", [[1, 2], "text", None])
def test_e9_an_answer_that_is_not_a_json_object_fails_with_the_endpoint(body):
    api = FakeSpotify()
    api.pages[0] = lambda: httpx.Response(200, json=body)

    assert ITEMS_PATH in errors_of(api)


@pytest.mark.parametrize("page", [{}, {"items": None}, {"items": "x"}, {"items": {"a": 1}}, {"item": []}])
def test_e9_a_page_without_an_item_list_fails_with_the_endpoint(page):
    api = FakeSpotify()
    api.pages[0] = lambda: httpx.Response(200, json=page)

    assert ITEMS_PATH in errors_of(api)


def test_e9_an_empty_page_with_a_next_link_fails():
    api = FakeSpotify()
    page = {"items": [], "next": ITEMS_URL + "?offset=50"}
    api.pages[0] = lambda: httpx.Response(200, json=page)

    assert ITEMS_PATH in errors_of(api)


def test_e10_a_failure_holds_the_status_and_the_endpoint_but_no_token_and_no_song_name():
    api = FakeSpotify()
    api.pages[50] = lambda: httpx.Response(418, json={"error": {"message": "Saltwater " + ACCESS_TOKEN}})

    message = errors_of(api)

    assert "418" in message and ITEMS_PATH in message
    assert_no_secret(message)
    assert "Saltwater" not in message and "?" not in message


def test_e11_the_summary_holds_the_counts_calls_waits_and_seconds():
    api = FakeSpotify()
    resource = make_resource(api)

    resource.read_documents()

    summary = resource.read_summary()
    assert "9 items" in summary and "4 songs" in summary and "1 repeated items" in summary
    assert "4 calls" in summary and "0 rate limit waits" in summary and "0 network retries" in summary
    assert summary.endswith(" s")


def test_e11_the_summary_counts_the_songs_read_before_a_failure():
    api = FakeSpotify()
    api.pages[100] = lambda: httpx.Response(500, json={})
    resource = make_resource(api)

    with pytest.raises(SpotifyError):
        resource.read_documents()

    assert "3 songs" in resource.read_summary()


def test_e12_the_resource_is_a_text_resource_named_spotify():
    resource = make_resource(FakeSpotify())

    assert isinstance(resource, Resource)
    assert resource.kind is ResourceKind.TEXT and resource.name == "spotify"


def test_e12_the_item_is_read_under_item_and_under_the_older_track_name():
    api = FakeSpotify()
    older = api.data["items_pages"]["100"]
    for entry in older["items"]:
        entry["track"] = entry.pop("item")
    api.pages[100] = lambda: httpx.Response(200, json=older)

    assert "Winter Radio" in [d.metadata["name"] for d in read(api)]


def test_e12_a_null_item_does_not_hide_a_usable_track():
    api = FakeSpotify()
    older = api.data["items_pages"]["100"]
    for entry in older["items"]:
        entry["track"] = entry["item"]
        entry["item"] = None
    api.pages[100] = lambda: httpx.Response(200, json=older)

    assert "Winter Radio" in [d.metadata["name"] for d in read(api)]


# ---------------------------------------------------------------- F: the song document


def test_f1_the_text_has_the_song_musician_album_and_link_lines():
    documents = read(FakeSpotify())

    assert documents[0].text == (
        "Song: Glass Harbor Lights\nMusician: Mira Solen\nAlbum: Night Ferries\n"
        "Link: https://open.spotify.com/track/1aGlassHarborLight0001"
    )


def test_f2_three_artists_are_joined_in_the_text_and_the_metadata():
    document = read(FakeSpotify())[1]

    assert "Musician: Leo Varga, Ines Duval, The Quiet Rooms" in document.text
    assert document.metadata["musician"] == "Leo Varga, Ines Duval, The Quiet Rooms"


def test_f3_a_song_without_an_album_name_has_no_album_line_and_is_still_made():
    document = next(d for d in read(FakeSpotify()) if d.metadata["name"] == "Saltwater")

    assert "Album" not in document.text and document.metadata["album"] == ""


@pytest.mark.parametrize("link", ["https://example.com/track/1", "spotify:track:1", "", None, 5])
def test_f4_a_link_that_is_not_an_open_spotify_link_is_left_out(link):
    api = FakeSpotify()
    page = api.data["items_pages"]["0"]
    page["items"][0]["item"]["external_urls"] = {"spotify": link}
    api.pages[0] = lambda: httpx.Response(200, json=page)

    first = read(api)[0]

    assert "Link" not in first.text and first.metadata["name"] == "Glass Harbor Lights"


def test_f5_the_metadata_has_every_key_with_string_values_and_the_added_time():
    document = read(FakeSpotify())[0]

    assert document.metadata == {
        "name": "Glass Harbor Lights",
        "path": "",
        "musician": "Mira Solen",
        "album": "Night Ferries",
        "type": "song",
        "timestamp": "2026-10-02T18:20:11Z",
    }
    assert all(isinstance(value, str) for value in document.metadata.values())


def settings(**overrides) -> Settings:
    return Settings(**{"spotify_client_id": CLIENT_ID, "spotify_client_secret": CLIENT_SECRET, **overrides})
