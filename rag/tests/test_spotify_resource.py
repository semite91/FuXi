import base64
import copy
import dataclasses
import inspect
import json
import os
import traceback
from pathlib import Path

import httpx
import pytest

from base import Resource, ResourceKind
from fakes import FakeSpotifyApi, load_fixture
from resources import http_retry, spotify_resource
from resources.http_retry import MAX_ATTEMPTS
from resources.spotify_resource import (
    PAGE_SIZE,
    Refusal,
    SpotifyCredentials,
    SpotifyError,
    SpotifyResource,
    SpotifySignInError,
    SpotifyTokenFileError,
    create_spotify_resource,
    spotify_credentials,
)
from settings import MissingSettingError, Settings

CLIENT_ID = "spotify-test-client-id"
CLIENT_SECRET = "spotify-test-client-secret"
REFRESH_TOKEN = "spotify-test-refresh-token"
ACCESS_TOKEN = "spotify-test-access-token"
ROTATED_REFRESH_TOKEN = "spotify-test-rotated-refresh-token"
BASIC_CREDENTIALS = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode("ascii")).decode("ascii")
SECRETS = [CLIENT_SECRET, REFRESH_TOKEN, ACCESS_TOKEN, ROTATED_REFRESH_TOKEN, BASIC_CREDENTIALS]
SONG_NAMES = ["Glass Harbor Lights", "Paper Moons", "Kitchen Demo", "Saltwater", "Winter Radio"]
TOKEN_ROUTE = "token"
FIRST_PAGE = "tracks:0"
SECOND_PAGE = "tracks:50"
LAST_PAGE = "tracks:100"
TOKEN_ENDPOINT = "/api/token"
TRACKS_ENDPOINT = "/v1/me/tracks"
GLASS_HARBOR_TEXT = "\n".join([
    "Song: Glass Harbor Lights",
    "Musician: Mira Solen",
    "Album: Night Ferries",
    "Link: https://open.spotify.com/track/1aGlassHarborLight0001",
])
FULL_SUMMARY_COUNTS = "9 items, 5 songs, 3 skipped items (1 no track, 1 not a song, 1 no name), 1 repeated items"


def recorded():
    return copy.deepcopy(load_fixture("spotify_recorded.json"))


def make_api(data=None, failures=None) -> FakeSpotifyApi:
    return FakeSpotifyApi(data or recorded(), failures)


@pytest.fixture
def token_file(tmp_path) -> Path:
    path = tmp_path / "secrets" / "spotify_token.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"refresh_token": REFRESH_TOKEN}), encoding="utf-8")
    return path


def make_resource(api, token_file: Path, sleeps=None, clock=None, credentials_factory=None) -> SpotifyResource:
    sleeps = [] if sleeps is None else sleeps
    return SpotifyResource(
        credentials_factory=credentials_factory or (lambda: SpotifyCredentials(CLIENT_ID, CLIENT_SECRET)),
        token_file_factory=lambda: token_file,
        http_client_factory=api.client,
        sleep=sleeps.append,
        **({"clock": clock} if clock is not None else {}),
    )


def answer(status: int, headers=None) -> httpx.Response:
    return httpx.Response(status, headers=headers or {}, json={"error": {"status": status, "message": "failed"}})


def recorded_answer(name: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=recorded()[name])


def body(content: bytes) -> httpx.Response:
    return httpx.Response(200, content=content)


def logged(error: BaseException) -> str:
    """The error as the embedding pipeline writes it to its log."""
    return f"{type(error).__name__}: {error}"


def printed(error: BaseException) -> str:
    return logged(error) + "".join(traceback.format_exception(error))


def names(documents) -> list[str]:
    return [document.metadata["name"] for document in documents]


def song(documents, name: str):
    return next(document for document in documents if document.metadata["name"] == name)


def tracks_requests(api) -> list[httpx.Request]:
    return [request for request in api.requests if request.url.path == TRACKS_ENDPOINT]


def first_track_changed(change) -> dict:
    """The recorded answers with the first liked song (Glass Harbor Lights) changed."""
    data = recorded()
    change(data["tracks"]["0"]["items"][0]["track"])
    return data


def read_first_song(token_file: Path, change):
    documents = make_resource(make_api(first_track_changed(change)), token_file).read_documents()
    return documents[0]


def test_refresh_asks_the_token_address_with_the_refresh_token_and_the_basic_header_before_any_song_call(token_file):
    # Phase 5d D1
    api = make_api()

    make_resource(api, token_file).read_documents()

    assert api.routes[0] == TOKEN_ROUTE and api.routes.count(TOKEN_ROUTE) == 1
    refresh = api.requests[0]
    assert (refresh.method, str(refresh.url)) == ("POST", "https://accounts.spotify.com/api/token")
    assert refresh.headers["Authorization"] == f"Basic {BASIC_CREDENTIALS}"
    assert refresh.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert api.form() == {"grant_type": "refresh_token", "refresh_token": REFRESH_TOKEN}
    assert CLIENT_SECRET not in str(refresh.url) and REFRESH_TOKEN not in str(refresh.url)


def test_song_calls_carry_the_bearer_access_token_and_never_put_it_in_the_url(token_file):
    # Phase 5d D2
    api = make_api()

    make_resource(api, token_file).read_documents()

    calls = tracks_requests(api)
    assert len(calls) == 3
    assert all(request.headers["Authorization"] == f"Bearer {ACCESS_TOKEN}" for request in calls)
    assert all(ACCESS_TOKEN not in str(request.url) for request in calls)
    assert all(request.url.scheme == "https" and request.url.host == "api.spotify.com" for request in calls)


def test_refresh_answer_without_a_refresh_token_leaves_the_token_file_unchanged(token_file):
    # Phase 5d D3
    content = token_file.read_bytes()
    modified = token_file.stat().st_mtime_ns

    make_resource(make_api(), token_file).read_documents()

    assert token_file.read_bytes() == content
    assert token_file.stat().st_mtime_ns == modified


def test_refresh_answer_with_a_new_refresh_token_is_written_to_the_token_file(token_file):
    # Phase 5d D4
    api = make_api(failures={TOKEN_ROUTE: [recorded_answer("token_with_refresh_token")]})

    documents = make_resource(api, token_file).read_documents()

    assert json.loads(token_file.read_text(encoding="utf-8")) == {"refresh_token": ROTATED_REFRESH_TOKEN}
    assert list(token_file.parent.iterdir()) == [token_file]  # the temporary file is gone
    assert names(documents) == SONG_NAMES


def test_new_refresh_token_that_cannot_be_written_fails_and_names_the_setting_without_the_path(token_file, monkeypatch):
    # Phase 5d D4 D9
    def refusing_replace(source, target):
        raise PermissionError(13, "Access is denied", str(target))

    monkeypatch.setattr(os, "replace", refusing_replace)
    api = make_api(failures={TOKEN_ROUTE: [recorded_answer("token_with_refresh_token")]})

    with pytest.raises(SpotifyTokenFileError, match="RAG_SPOTIFY_TOKEN_FILE") as raised:
        make_resource(api, token_file).read_documents()

    monkeypatch.undo()
    assert str(token_file.parent) not in printed(raised.value)
    assert "spotify_token.json" not in printed(raised.value)
    assert all(secret not in printed(raised.value) for secret in SECRETS)
    assert json.loads(token_file.read_text(encoding="utf-8")) == {"refresh_token": REFRESH_TOKEN}
    assert list(token_file.parent.iterdir()) == [token_file]


def test_missing_token_file_fails_before_any_call_and_names_the_setting_and_the_helper_without_the_path(tmp_path):
    # Phase 5d D5
    api = make_api()
    missing = tmp_path / "absent" / "spotify_token.json"

    with pytest.raises(SpotifyTokenFileError) as raised:
        make_resource(api, missing).read_documents()

    message = logged(raised.value)
    assert "RAG_SPOTIFY_TOKEN_FILE" in message and "spotify_authorize.py" in message
    assert str(tmp_path) not in printed(raised.value) and "spotify_token.json" not in printed(raised.value)
    assert raised.value.__cause__ is None
    assert api.requests == []


@pytest.mark.parametrize("content", [
    b"not json",
    b'{"refresh_token": "spotify-test-refresh-token"',  # cut off
    b"[]",
    b"{}",
    b'{"refresh_token": ""}',
    b'{"refresh_token": 7}',
    b'\xff\xfe{"refresh_token": "spotify-test-refresh-token"}',  # not UTF-8
])
def test_token_file_that_is_not_valid_json_or_has_no_refresh_token_fails_before_any_call(token_file, content):
    # Phase 5d D6
    token_file.write_bytes(content)
    api = make_api()

    with pytest.raises(SpotifyTokenFileError) as raised:
        make_resource(api, token_file).read_documents()

    message = logged(raised.value)
    assert "RAG_SPOTIFY_TOKEN_FILE" in message and "spotify_authorize.py" in message
    assert str(token_file.parent) not in printed(raised.value) and REFRESH_TOKEN not in printed(raised.value)
    assert raised.value.__cause__ is None
    assert api.requests == []


def test_token_file_that_cannot_be_read_fails_before_any_call_without_the_path(token_file, monkeypatch):
    # Phase 5d D6
    real_read_bytes = Path.read_bytes

    def refusing_read(path):
        if path == token_file:
            raise PermissionError(13, "Access is denied", str(path))
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", refusing_read)
    api = make_api()

    with pytest.raises(SpotifyTokenFileError, match="RAG_SPOTIFY_TOKEN_FILE") as raised:
        make_resource(api, token_file).read_documents()

    monkeypatch.undo()
    assert "spotify_authorize.py" in logged(raised.value)
    assert str(token_file.parent) not in printed(raised.value)
    assert api.requests == []


@pytest.mark.parametrize("refusal", [
    recorded_answer("invalid_grant", 400),
    recorded_answer("invalid_grant", 401),
])
def test_refused_refresh_token_fails_and_says_to_run_the_approval_helper_again(token_file, refusal):
    # Phase 5d D7
    sleeps: list[float] = []
    api = make_api(failures={TOKEN_ROUTE: [refusal]})

    with pytest.raises(SpotifySignInError) as raised:
        make_resource(api, token_file, sleeps).read_documents()

    assert "run spotify_authorize.py again" in logged(raised.value)
    assert "RAG_SPOTIFY_CLIENT" not in logged(raised.value)
    assert str(refusal.status_code) in logged(raised.value)
    assert api.routes == [TOKEN_ROUTE]  # a refused token is not tried again and no song is asked
    assert sleeps == []


@pytest.mark.parametrize("status", [400, 401])
def test_refused_client_fails_and_says_to_check_the_client_id_and_secret(token_file, status):
    # Phase 5d D7
    sleeps: list[float] = []
    refusal = httpx.Response(status, json={"error": "invalid_client", "error_description": f"Bad {CLIENT_SECRET}"})
    api = make_api(failures={TOKEN_ROUTE: [refusal]})

    with pytest.raises(SpotifySignInError) as raised:
        make_resource(api, token_file, sleeps).read_documents()

    message = logged(raised.value)
    assert "RAG_SPOTIFY_CLIENT_ID" in message and "RAG_SPOTIFY_CLIENT_SECRET" in message
    assert "spotify_authorize.py" not in message
    assert str(status) in message and TOKEN_ENDPOINT in message
    assert "Bad" not in printed(raised.value)
    for secret in SECRETS:
        assert secret not in printed(raised.value)
    assert raised.value.__cause__ is None
    assert api.routes == [TOKEN_ROUTE]
    assert sleeps == []


@pytest.mark.parametrize(("refusal", "message"), [
    (httpx.Response(400, json={"error": "invalid_request", "error_description": f"Bad {REFRESH_TOKEN}"}),
     "Spotify refused the request (400 invalid_request on /api/token)"),
    (httpx.Response(400, json={"error": "unsupported_grant_type"}),
     "Spotify refused the request (400 unsupported_grant_type on /api/token)"),
    (httpx.Response(401, json={"error": "invalid_scope"}), "Spotify refused the request (401 invalid_scope on /api/token)"),
    (httpx.Response(400, content=b"<html>invalid_grant</html>"), "Spotify refused the request (400 on /api/token)"),
    (httpx.Response(400, json=["invalid_grant"]), "Spotify refused the request (400 on /api/token)"),
    (httpx.Response(401, json={"error": {"status": 401, "message": "invalid_grant"}}),
     "Spotify refused the request (401 on /api/token)"),
    (httpx.Response(400, json={"error": "<script>invalid grant</script>"}), "Spotify refused the request (400 on /api/token)"),
    (httpx.Response(400, content=b""), "Spotify refused the request (400 on /api/token)"),
])
def test_other_refusal_names_the_status_and_the_error_and_does_not_ask_for_a_new_approval(token_file, refusal, message):
    # Phase 5d D7
    sleeps: list[float] = []
    api = make_api(failures={TOKEN_ROUTE: [refusal]})

    with pytest.raises(SpotifyError) as raised:
        make_resource(api, token_file, sleeps).read_documents()

    assert not isinstance(raised.value, SpotifySignInError)
    assert logged(raised.value) == f"SpotifyError: {message}"
    assert (raised.value.status, raised.value.endpoint) == (refusal.status_code, TOKEN_ENDPOINT)
    assert "spotify_authorize.py" not in printed(raised.value) and "RAG_SPOTIFY_CLIENT" not in printed(raised.value)
    for secret in SECRETS:
        assert secret not in printed(raised.value)
    assert raised.value.__cause__ is None
    assert api.routes == [TOKEN_ROUTE]
    assert sleeps == []


@pytest.mark.parametrize(("status", "error_code", "refusal"), [
    (400, "invalid_client", Refusal.CLIENT),
    (401, "invalid_client", Refusal.CLIENT),
    (400, "invalid_grant", Refusal.SIGN_IN),
    (401, "invalid_grant", Refusal.SIGN_IN),
    (401, "", Refusal.REQUEST),
    (400, "", Refusal.REQUEST),
    (400, "invalid_request", Refusal.REQUEST),
    (401, "unsupported_grant_type", Refusal.REQUEST),
    (403, "invalid_client", Refusal.NONE),
    (429, "invalid_client", Refusal.NONE),
    (500, "invalid_client", Refusal.NONE),
    (None, "", Refusal.NONE),
])
def test_refusal_tells_a_refused_client_from_a_refused_sign_in(status, error_code, refusal):
    # Phase 5d D7 (one rule for the resource and the approval helper)
    error = SpotifyError("Spotify call failed", status, TOKEN_ENDPOINT, error_code)

    assert error.refusal() is refusal
    assert error.error_code == error_code


def test_error_code_is_given_to_the_constructor_and_passed_through_to_the_sign_in_error():
    # Phase 5d D7
    response = httpx.Response(
        401, json={"error": "invalid_client"}, request=httpx.Request("POST", "https://accounts.spotify.com/api/token")
    )
    status_error = httpx.HTTPStatusError("refused", request=response.request, response=response)

    error = SpotifyError.of_http_error(status_error, TOKEN_ENDPOINT)
    refusal = SpotifySignInError.of_refusal(error)

    assert "error_code" not in vars(SpotifyError)  # no class default used as state
    assert SpotifyError("failed").error_code == ""
    assert (error.status, error.endpoint, error.error_code) == (401, TOKEN_ENDPOINT, "invalid_client")
    assert (refusal.status, refusal.endpoint, refusal.error_code) == (401, TOKEN_ENDPOINT, "invalid_client")


@pytest.mark.parametrize(("client_id", "client_secret", "key"), [
    ("", CLIENT_SECRET, "RAG_SPOTIFY_CLIENT_ID"),
    (None, CLIENT_SECRET, "RAG_SPOTIFY_CLIENT_ID"),
    (CLIENT_ID, "", "RAG_SPOTIFY_CLIENT_SECRET"),
    (CLIENT_ID, None, "RAG_SPOTIFY_CLIENT_SECRET"),
])
def test_empty_client_id_or_client_secret_fails_before_any_call_and_names_the_key(
    token_file, client_id, client_secret, key
):
    # Phase 5d D8
    api = make_api()
    settings = Settings(spotify_client_id=client_id, spotify_client_secret=client_secret)

    with pytest.raises(MissingSettingError, match=key):
        make_resource(api, token_file, credentials_factory=lambda: spotify_credentials(settings)).read_documents()

    assert api.requests == []


def test_unset_spotify_settings_fail_only_when_the_songs_are_read(token_file):
    # Phase 5d B3
    resource = create_spotify_resource(Settings())  # creating does not fail

    with pytest.raises(MissingSettingError, match="RAG_SPOTIFY_CLIENT_ID"):
        resource.read_documents()
    with pytest.raises(MissingSettingError, match="RAG_SPOTIFY_CLIENT_SECRET"):
        create_spotify_resource(Settings(spotify_client_id=CLIENT_ID)).read_documents()
    with pytest.raises(MissingSettingError, match="RAG_SPOTIFY_TOKEN_FILE"):
        create_spotify_resource(
            Settings(spotify_client_id=CLIENT_ID, spotify_client_secret=CLIENT_SECRET)
        ).read_documents()


@pytest.mark.parametrize("failures", [
    [recorded_answer("invalid_grant", 400)],
    [recorded_answer("invalid_client", 401)],
    [answer(403)],
    [answer(500)] * MAX_ATTEMPTS,
    [httpx.ConnectError(f"no route with {REFRESH_TOKEN} and {CLIENT_SECRET}")] * MAX_ATTEMPTS,
    [httpx.LocalProtocolError(f"Basic {BASIC_CREDENTIALS}")],
    [body(f"<html>{ACCESS_TOKEN} {REFRESH_TOKEN}</html>".encode("utf-8"))],
    [body(json.dumps([ACCESS_TOKEN]).encode("utf-8"))],
    [httpx.Response(200, json={"token_type": "Bearer", "refresh_token": ROTATED_REFRESH_TOKEN})],
    [httpx.Response(200, json={"access_token": 7})],
])
def test_sign_in_failure_holds_no_token_and_no_client_secret(token_file, failures):
    # Phase 5d D9
    api = make_api(failures={TOKEN_ROUTE: failures})

    with pytest.raises(SpotifyError) as raised:
        make_resource(api, token_file).read_documents()

    for secret in SECRETS:
        assert secret not in printed(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.endpoint == TOKEN_ENDPOINT
    assert TRACKS_ENDPOINT not in [request.url.path for request in api.requests]
    assert json.loads(token_file.read_text(encoding="utf-8")) == {"refresh_token": REFRESH_TOKEN}


def test_liked_songs_are_asked_with_limit_50_first_then_each_next_link_is_followed_and_each_song_read_once(token_file):
    # Phase 5d E1
    api = make_api()

    documents = make_resource(api, token_file).read_documents()

    calls = tracks_requests(api)
    assert PAGE_SIZE == 50
    assert str(calls[0].url) == "https://api.spotify.com/v1/me/tracks?limit=50"
    assert [str(request.url) for request in calls[1:]] == [
        recorded()["tracks"]["0"]["next"], recorded()["tracks"]["50"]["next"]
    ]
    assert all(request.method == "GET" for request in calls)
    assert names(documents) == SONG_NAMES


def test_next_link_is_followed_as_given_not_computed(token_file):
    # Phase 5d E1
    data = recorded()
    data["tracks"]["0"]["next"] = "https://api.spotify.com/v1/me/tracks?offset=100&limit=50"
    api = make_api(data)

    make_resource(api, token_file).read_documents()

    assert api.routes == [TOKEN_ROUTE, FIRST_PAGE, LAST_PAGE]


def test_last_page_without_a_next_page_asks_no_further_page(token_file):
    # Phase 5d E2
    api = make_api()

    make_resource(api, token_file).read_documents()

    assert api.routes == [TOKEN_ROUTE, FIRST_PAGE, SECOND_PAGE, LAST_PAGE]


def test_first_page_without_a_next_page_is_the_only_page_asked(token_file):
    # Phase 5d E2
    data = recorded()
    data["tracks"]["0"]["next"] = None
    api = make_api(data)

    documents = make_resource(api, token_file).read_documents()

    assert api.routes == [TOKEN_ROUTE, FIRST_PAGE]
    assert names(documents) == ["Glass Harbor Lights", "Paper Moons"]


@pytest.mark.parametrize("offset", ["0", "50"])
def test_page_with_an_empty_item_list_but_a_next_link_fails_the_source_with_the_endpoint(token_file, offset):
    # Phase 5d E2 E14 (only an empty page without a next link ends the read)
    data = recorded()
    data["tracks"][offset]["items"] = []
    api = make_api(data)

    with pytest.raises(SpotifyError) as raised:
        make_resource(api, token_file).read_documents()

    assert (raised.value.status, raised.value.endpoint) == (None, TRACKS_ENDPOINT)
    assert "offset" not in printed(raised.value) and "https://" not in printed(raised.value)
    assert api.routes[-1] == f"tracks:{offset}"


BAD_NEXT_LINKS = [
    "http://api.spotify.com/v1/me/tracks?offset=50&limit=50",
    "https://evil.example/v1/me/tracks?offset=50&limit=50",
    "https://api.spotify.com.evil.example/v1/me/tracks?offset=50&limit=50",
    "https://api.spotify.com@evil.example/v1/me/tracks?offset=50&limit=50",
    "https://user:password@api.spotify.com/v1/me/tracks?offset=50&limit=50",
    "https://api.spotify.com:8443/v1/me/tracks?offset=50&limit=50",
    "https://api.spotify.com/v1/me/tracksx?offset=50&limit=50",
    "https://api.spotify.com/v1/me/tracks/extra?offset=50&limit=50",
    "https://api.spotify.com/v1/me/tracks/../playlists?offset=50&limit=50",
    "https://api.spotify.com/v1/me/albums?offset=50&limit=50",
    "https://api.spotify.com/evil/v1/me/tracks?offset=50&limit=50",
    "/v1/me/tracks?offset=50&limit=50",
    "api.spotify.com/v1/me/tracks?offset=50&limit=50",
    "https://[api.spotify.com/v1/me/tracks?offset=50",
    7,
    ["https://api.spotify.com/v1/me/tracks?offset=50&limit=50"],
    {"href": "https://api.spotify.com/v1/me/tracks?offset=50&limit=50"},
]


@pytest.mark.parametrize("link", BAD_NEXT_LINKS)
def test_next_link_off_the_liked_songs_address_fails_the_source_with_the_endpoint_not_the_link(token_file, link):
    # Phase 5d E15
    data = recorded()
    data["tracks"]["0"]["next"] = link
    api = make_api(data)

    with pytest.raises(SpotifyError) as raised:
        make_resource(api, token_file).read_documents()

    assert (raised.value.status, raised.value.endpoint) == (None, TRACKS_ENDPOINT)
    assert logged(raised.value) == (
        "SpotifyError: Spotify call failed: a next link off the liked songs address on /v1/me/tracks"
    )
    assert "evil.example" not in printed(raised.value) and "password" not in printed(raised.value)
    assert raised.value.__cause__ is None
    assert len(tracks_requests(api)) == 1  # the link is not followed


@pytest.mark.parametrize("link", [
    "https://api.spotify.com/v1/me/tracks?offset=50&limit=50",  # the second page's own link
    "https://api.spotify.com/v1/me/tracks?limit=50",  # the first call
])
def test_next_link_already_followed_fails_the_source_with_the_endpoint_not_the_link(token_file, link):
    # Phase 5d E15
    data = recorded()
    data["tracks"]["50"]["next"] = link
    api = make_api(data)

    with pytest.raises(SpotifyError) as raised:
        make_resource(api, token_file).read_documents()

    assert (raised.value.status, raised.value.endpoint) == (None, TRACKS_ENDPOINT)
    assert logged(raised.value) == "SpotifyError: Spotify call failed: a next link already followed on /v1/me/tracks"
    assert "offset" not in printed(raised.value) and "https://" not in printed(raised.value)
    assert api.routes == [TOKEN_ROUTE, FIRST_PAGE, SECOND_PAGE]


@pytest.mark.parametrize(("offset", "link"), [
    ("0", "https://api.spotify.com/v1/me/tracks?offset=0&limit=50"),  # the first call's offset counts as 0
    ("0", "https://api.spotify.com/v1/me/tracks?limit=50&offset=0&market=from_token"),
    ("50", "https://api.spotify.com/v1/me/tracks?offset=20&limit=50"),  # back
    ("50", "https://api.spotify.com/v1/me/tracks?limit=50&offset=50"),  # the same offset, reordered
    ("50", "https://api.spotify.com/v1/me/tracks?offset=50&limit=50&market=from_token"),
    ("50", "https://api.spotify.com/v1/me/tracks?offset=-100&limit=50"),
    ("0", "https://api.spotify.com/v1/me/tracks?limit=50&market=from_token"),  # no offset
    ("0", "https://api.spotify.com/v1/me/tracks?offset=&limit=50"),
    ("0", "https://api.spotify.com/v1/me/tracks?offset=fifty&limit=50"),
    ("0", "https://api.spotify.com/v1/me/tracks?offset=50.5&limit=50"),
    ("0", "https://api.spotify.com/v1/me/tracks?offset=+50&limit=50"),
    ("0", "https://api.spotify.com/v1/me/tracks?offset=50&offset=0&limit=50"),  # two offsets
])
def test_next_link_whose_offset_does_not_move_forward_fails_the_source_with_the_endpoint_not_the_link(
    token_file, offset, link
):
    # Phase 5d E15
    data = recorded()
    data["tracks"][offset]["next"] = link
    api = make_api(data)

    with pytest.raises(SpotifyError) as raised:
        make_resource(api, token_file).read_documents()

    assert (raised.value.status, raised.value.endpoint) == (None, TRACKS_ENDPOINT)
    assert logged(raised.value) == (
        "SpotifyError: Spotify call failed: a next link whose offset does not move forward on /v1/me/tracks"
    )
    assert "https://" not in printed(raised.value) and "fifty" not in printed(raised.value)
    assert raised.value.__cause__ is None
    assert api.routes[-1] == f"tracks:{offset}"  # the link is not followed


def test_next_link_with_reordered_or_extra_parameters_and_a_forward_offset_is_followed(token_file):
    # Phase 5d E15
    data = recorded()
    data["tracks"]["0"]["next"] = "https://api.spotify.com/v1/me/tracks?limit=50&market=from_token&offset=50"
    data["tracks"]["50"]["next"] = "https://api.spotify.com/v1/me/tracks?limit=50&offset=100"
    api = make_api(data)

    documents = make_resource(api, token_file).read_documents()

    assert api.routes == [TOKEN_ROUTE, FIRST_PAGE, SECOND_PAGE, LAST_PAGE]
    assert names(documents) == SONG_NAMES


def test_no_liked_song_gives_no_document_and_no_error(token_file):
    # Phase 5d E3
    data = recorded()
    data["tracks"] = {}
    api = make_api(data)
    resource = make_resource(api, token_file)

    assert resource.read_documents() == []
    assert api.routes == [TOKEN_ROUTE, FIRST_PAGE]
    assert resource.read_summary().startswith(
        "0 items, 0 songs, 0 skipped items (0 no track, 0 not a song, 0 no name), 0 repeated items, 2 calls,"
    )


def test_item_without_a_track_a_podcast_episode_or_a_song_without_a_name_is_skipped_and_counted(token_file):
    # Phase 5d E4
    resource = make_resource(make_api(), token_file)

    documents = resource.read_documents()

    assert "Morning Talk, Episode 12" not in names(documents)
    assert "" not in names(documents) and len(documents) == 5
    assert names(documents) == SONG_NAMES
    assert resource.read_summary().startswith(FULL_SUMMARY_COUNTS + ",")


@pytest.mark.parametrize("track", [None, 7, "Glass Harbor Lights", []])
def test_item_whose_track_is_not_an_object_counts_as_an_item_without_a_track(token_file, track):
    # Phase 5d E4
    data = recorded()
    data["tracks"]["0"]["items"][0]["track"] = track
    resource = make_resource(make_api(data), token_file)

    documents = resource.read_documents()

    assert sorted(names(documents)) == sorted(SONG_NAMES)  # the same song comes again on the last page
    assert resource.read_summary().startswith(
        "9 items, 5 songs, 4 skipped items (2 no track, 1 not a song, 1 no name), 0 repeated items,"
    )


MISSING = object()


@pytest.mark.parametrize("items", [MISSING, None, 7, "items", {"track": {}}])
@pytest.mark.parametrize("offset", ["0", "50"])
def test_page_whose_items_are_missing_null_or_not_a_list_fails_the_source_with_the_endpoint(token_file, offset, items):
    # Phase 5d E14
    data = recorded()
    if items is MISSING:
        del data["tracks"][offset]["items"]
    else:
        data["tracks"][offset]["items"] = items
    api = make_api(data)

    with pytest.raises(SpotifyError) as raised:
        make_resource(api, token_file).read_documents()

    assert (raised.value.status, raised.value.endpoint) == (None, TRACKS_ENDPOINT)
    for secret in [*SECRETS, *SONG_NAMES]:
        assert secret not in printed(raised.value)
    assert raised.value.__cause__ is None
    assert api.routes[-1] == f"tracks:{offset}"


def test_last_page_with_an_empty_item_list_and_no_next_page_ends_the_read(token_file):
    # Phase 5d E14
    data = recorded()
    data["tracks"]["100"]["items"] = []
    data["tracks"]["100"]["next"] = None
    api = make_api(data)

    documents = make_resource(api, token_file).read_documents()

    assert api.routes == [TOKEN_ROUTE, FIRST_PAGE, SECOND_PAGE, LAST_PAGE]
    assert "Glass Harbor Lights" in names(documents)


def test_same_track_id_in_two_items_makes_one_document_and_counts_the_second_as_repeated(token_file):
    # Phase 5d E5
    resource = make_resource(make_api(), token_file)

    documents = resource.read_documents()

    assert names(documents).count("Glass Harbor Lights") == 1
    assert song(documents, "Glass Harbor Lights").metadata["timestamp"] == "2026-10-02T18:20:11Z"  # the newest like
    assert ", 1 repeated items," in resource.read_summary()


def test_two_local_files_without_a_track_id_are_both_read(token_file):
    # Phase 5d E5
    data = recorded()
    local = data["tracks"]["50"]["items"][0]
    other = copy.deepcopy(local)
    other["track"].update(name="Garden Demo", uri="spotify:local:Ada+North:Home+Recordings:Garden+Demo:160")
    data["tracks"]["50"]["items"].append(other)

    documents = make_resource(make_api(data), token_file).read_documents()

    assert {"Kitchen Demo", "Garden Demo"} <= set(names(documents))


@pytest.mark.parametrize(("route", "name", "status"), [
    (FIRST_PAGE, "unauthorized", 401),
    (SECOND_PAGE, "unauthorized", 401),
    (FIRST_PAGE, "forbidden", 403),
    (LAST_PAGE, "forbidden", 403),
])
def test_401_or_403_on_a_song_call_fails_the_spotify_resource(token_file, route, name, status):
    # Phase 5d E6
    sleeps: list[float] = []
    api = make_api(failures={route: [recorded_answer(name, status)]})

    with pytest.raises(SpotifyError) as raised:
        make_resource(api, token_file, sleeps).read_documents()

    assert not isinstance(raised.value, SpotifySignInError)
    assert (raised.value.status, raised.value.endpoint) == (status, TRACKS_ENDPOINT)
    assert api.routes.count(route) == 1
    assert sleeps == []


@pytest.mark.parametrize("route", [TOKEN_ROUTE, SECOND_PAGE])
def test_rate_limit_waits_retry_after_and_tries_again(token_file, route):
    # Phase 5d E7 D11 (a 429 on the refresh call is still waited for)
    sleeps: list[float] = []
    api = make_api(failures={route: [answer(429, {"Retry-After": "3"})]})

    documents = make_resource(api, token_file, sleeps).read_documents()

    assert sleeps == [3.0]
    assert api.routes.count(route) == 2
    assert names(documents) == SONG_NAMES


def retryable_failures():
    return [answer(500), answer(503), httpx.ConnectError("no route"), httpx.ReadError("reset"), httpx.ReadTimeout("slow")]


@pytest.mark.parametrize("failure", retryable_failures())
def test_server_error_dropped_connection_or_timeout_waits_and_tries_again(token_file, failure):
    # Phase 5d E8 D11 (only a song call is tried again)
    sleeps: list[float] = []
    api = make_api(failures={SECOND_PAGE: [failure]})

    documents = make_resource(api, token_file, sleeps).read_documents()

    assert sleeps == [1.0]
    assert names(documents) == SONG_NAMES


@pytest.mark.parametrize("failure", retryable_failures())
def test_retries_wait_1_2_4_and_8_seconds_and_fail_the_source_after_5_attempts(token_file, failure):
    # Phase 5d E8 D11 (only a song call is tried again)
    sleeps: list[float] = []
    api = make_api(failures={SECOND_PAGE: [failure] * MAX_ATTEMPTS})

    with pytest.raises(SpotifyError):
        make_resource(api, token_file, sleeps).read_documents()

    assert sleeps == [1.0, 2.0, 4.0, 8.0]
    assert api.routes.count(SECOND_PAGE) == MAX_ATTEMPTS == 5


@pytest.mark.parametrize(("failure", "kind"), [
    (answer(500), "500"),
    (answer(503), "503"),
    (httpx.ConnectError("no route"), "ConnectError"),
    (httpx.ReadError("reset"), "ReadError"),
    (httpx.ReadTimeout("slow"), "ReadTimeout"),
    (httpx.RemoteProtocolError("dropped"), "RemoteProtocolError"),
])
def test_refresh_call_that_times_out_drops_or_gets_a_5xx_is_not_tried_again_and_fails_the_source(
    token_file, failure, kind
):
    # Phase 5d D11
    sleeps: list[float] = []
    api = make_api(failures={TOKEN_ROUTE: [failure]})

    with pytest.raises(SpotifyError) as raised:
        make_resource(api, token_file, sleeps).read_documents()

    assert not isinstance(raised.value, SpotifySignInError)
    assert logged(raised.value) == f"SpotifyError: Spotify call failed: {kind} on {TOKEN_ENDPOINT}"
    assert raised.value.__cause__ is None
    assert api.routes == [TOKEN_ROUTE]  # Spotify may have used the refresh token
    assert sleeps == []
    assert json.loads(token_file.read_text(encoding="utf-8")) == {"refresh_token": REFRESH_TOKEN}


@pytest.mark.parametrize("content", [b"<html>Glass Harbor Lights</html>", b"", b"[]", b"null", b'"Paper Moons"', b"7"])
@pytest.mark.parametrize("route", [FIRST_PAGE, SECOND_PAGE])
def test_200_answer_that_is_not_a_json_object_fails_the_source_with_the_endpoint(token_file, route, content):
    # Phase 5d E9
    sleeps: list[float] = []
    api = make_api(failures={route: [body(content)]})

    with pytest.raises(SpotifyError) as raised:
        make_resource(api, token_file, sleeps).read_documents()

    assert (raised.value.status, raised.value.endpoint) == (None, TRACKS_ENDPOINT)
    assert logged(raised.value) == (
        "SpotifyError: Spotify call failed: an answer that is not a JSON object on /v1/me/tracks"
    )
    assert "Glass Harbor" not in printed(raised.value) and "Paper Moons" not in printed(raised.value)
    assert api.routes.count(route) == 1
    assert sleeps == []


@pytest.mark.parametrize(("route", "failures", "kind"), [
    (FIRST_PAGE, [answer(401)], "401"),
    (SECOND_PAGE, [answer(403)], "403"),
    (SECOND_PAGE, [answer(404)], "404"),
    (LAST_PAGE, [answer(400)], "400"),
    (SECOND_PAGE, [answer(503)] * MAX_ATTEMPTS, "503"),
    (SECOND_PAGE, [answer(429)] * MAX_ATTEMPTS, "429"),
    (SECOND_PAGE, [httpx.ConnectError(f"no route for Glass Harbor Lights with Bearer {ACCESS_TOKEN}")] * MAX_ATTEMPTS,
     "ConnectError"),
    (LAST_PAGE, [httpx.ReadTimeout("slow")] * MAX_ATTEMPTS, "ReadTimeout"),
])
def test_song_call_error_holds_the_status_and_the_endpoint_not_a_token_or_a_song_name(token_file, route, failures, kind):
    # Phase 5d E10
    api = make_api(failures={route: failures})

    with pytest.raises(SpotifyError) as raised:
        make_resource(api, token_file).read_documents()

    assert logged(raised.value) == f"SpotifyError: Spotify call failed: {kind} on {TRACKS_ENDPOINT}"
    for secret in [*SECRETS, *SONG_NAMES, "Bearer", "offset", "?"]:
        assert secret not in logged(raised.value)
    for secret in [*SECRETS, "Glass Harbor Lights", "Paper Moons"]:
        assert secret not in printed(raised.value)
    assert raised.value.__cause__ is None
    assert api.routes.count(route) == len(failures)


@pytest.mark.parametrize("error_type", [
    httpx.DecodingError,
    httpx.TooManyRedirects,
    httpx.LocalProtocolError,
    httpx.UnsupportedProtocol,
    httpx.ProxyError,
    httpx.InvalidURL,
])
@pytest.mark.parametrize(("route", "endpoint"), [(TOKEN_ROUTE, TOKEN_ENDPOINT), (SECOND_PAGE, TRACKS_ENDPOINT)])
def test_any_other_httpx_error_fails_the_source_at_once_with_its_kind_and_endpoint(token_file, route, endpoint, error_type):
    # Phase 5d E10
    sleeps: list[float] = []
    api = make_api(failures={route: [error_type(f"failed for Glass Harbor Lights with Bearer {ACCESS_TOKEN}")]})

    with pytest.raises(SpotifyError) as raised:
        make_resource(api, token_file, sleeps).read_documents()

    assert logged(raised.value) == f"SpotifyError: Spotify call failed: {error_type.__name__} on {endpoint}"
    assert "Glass Harbor" not in printed(raised.value) and ACCESS_TOKEN not in printed(raised.value)
    assert raised.value.__cause__ is None
    assert api.routes.count(route) == 1
    assert sleeps == []


def test_read_summary_counts_items_songs_skips_repeats_calls_waits_and_time(token_file):
    # Phase 5d E11
    ticks = iter([100.0, 107.5])
    api = make_api(failures={SECOND_PAGE: [answer(429, {"Retry-After": "3"}), httpx.ReadError("connection reset")]})
    resource = make_resource(api, token_file, clock=lambda: next(ticks))

    resource.read_documents()

    assert resource.read_summary() == (
        f"{FULL_SUMMARY_COUNTS}, 6 calls, 1 rate limit waits (3.0 s), 1 network retries, 7.5 s"
    )
    assert len(api.requests) == 6


def test_read_summary_is_kept_when_the_read_fails(token_file):
    # Phase 5d E11
    ticks = iter([10.0, 25.0])
    api = make_api(failures={SECOND_PAGE: [recorded_answer("unauthorized", 401)]})
    resource = make_resource(api, token_file, clock=lambda: next(ticks))

    with pytest.raises(SpotifyError):
        resource.read_documents()

    assert resource.read_summary() == (
        "3 items, 2 songs, 1 skipped items (0 no track, 1 not a song, 0 no name), 0 repeated items, "
        "3 calls, 0 rate limit waits (0.0 s), 0 network retries, 15.0 s"
    )


def test_read_summary_of_a_sign_in_failure_counts_its_calls(token_file):
    # Phase 5d E11
    resource = make_resource(make_api(failures={TOKEN_ROUTE: [recorded_answer("invalid_grant", 400)]}), token_file)

    with pytest.raises(SpotifySignInError):
        resource.read_documents()

    assert resource.read_summary().startswith(
        "0 items, 0 songs, 0 skipped items (0 no track, 0 not a song, 0 no name), 0 repeated items, 1 calls,"
    )


def test_second_read_starts_its_summary_again(token_file):
    # Phase 5d E11
    resource = make_resource(make_api(), token_file)

    resource.read_documents()
    resource.read_documents()

    assert resource.read_summary().startswith(f"{FULL_SUMMARY_COUNTS}, 4 calls,")


def test_spotify_resource_implements_the_resource_base_as_a_text_source_with_the_shared_http_helpers(token_file):
    # Phase 5d E12
    resource = make_resource(make_api(), token_file)

    assert isinstance(resource, Resource)
    assert (resource.name, resource.kind) == ("spotify", ResourceKind.TEXT)
    assert issubclass(SpotifyError, http_retry.ApiCallError)
    for helper in (
        "call_json", "http_retry_wait", "rate_limit_retry_wait", "ReadStats", "create_http_client", "timed_read", "bearer_header",
        "basic_header", "json_object_or_none",
    ):
        assert getattr(spotify_resource, helper) is getattr(http_retry, helper)
    assert not hasattr(spotify_resource, "REQUEST_TIMEOUT_SECONDS") and not hasattr(spotify_resource, "MAX_ATTEMPTS")


def test_song_document_text_has_the_song_musician_album_and_link_lines(token_file):
    # Phase 5d F1
    documents = make_resource(make_api(), token_file).read_documents()

    assert song(documents, "Glass Harbor Lights").text == GLASS_HARBOR_TEXT


def test_song_with_3_artists_joins_their_names_in_the_musician_line_and_metadata(token_file):
    # Phase 5d F2
    paper_moons = song(make_resource(make_api(), token_file).read_documents(), "Paper Moons")

    assert paper_moons.text.splitlines()[1] == "Musician: Leo Varga, Ines Duval, The Quiet Rooms"
    assert paper_moons.metadata["musician"] == "Leo Varga, Ines Duval, The Quiet Rooms"


def test_artist_listed_twice_appears_once(token_file):
    # Phase 5d F2
    def change(track):
        track["artists"] = [*track["artists"], {"name": " Mira Solen "}, {"name": ""}, "Mira", 7]

    assert read_first_song(token_file, change).metadata["musician"] == "Mira Solen"


def test_song_without_an_album_name_leaves_the_album_line_out(token_file):
    # Phase 5d F3
    saltwater = song(make_resource(make_api(), token_file).read_documents(), "Saltwater")

    assert saltwater.text == "\n".join([
        "Song: Saltwater", "Musician: Noor Haddad", "Link: https://open.spotify.com/track/3cSaltwaterTrack00003"
    ])
    assert saltwater.metadata["album"] == ""


@pytest.mark.parametrize("album", [None, {}, "Night Ferries", ["Night Ferries"], {"name": 7}])
def test_album_of_a_wrong_shape_counts_as_missing(token_file, album):
    # Phase 5d F3
    def change(track):
        track["album"] = album

    document = read_first_song(token_file, change)

    assert "Album:" not in document.text
    assert document.metadata["name"] == "Glass Harbor Lights" and document.metadata["album"] == ""


def test_song_without_artists_leaves_the_musician_line_out(token_file):
    # Phase 5d F3
    def change(track):
        track["artists"] = []

    document = read_first_song(token_file, change)

    assert document.text.splitlines()[:2] == ["Song: Glass Harbor Lights", "Album: Night Ferries"]
    assert document.metadata["musician"] == ""


def test_local_file_leaves_the_link_line_out(token_file):
    # Phase 5d F4
    kitchen_demo = song(make_resource(make_api(), token_file).read_documents(), "Kitchen Demo")

    assert kitchen_demo.text == "Song: Kitchen Demo\nMusician: Ada North\nAlbum: Home Recordings"


@pytest.mark.parametrize("external_urls", [
    {"spotify": "http://open.spotify.com/track/1aGlassHarborLight0001"},
    {"spotify": "https://open.spotify.com.example.com/track/1aGlassHarborLight0001"},
    {"spotify": "https://example.com/open.spotify.com/track/1aGlassHarborLight0001"},
    {"spotify": "javascript:alert(1)"},
    {"spotify": "spotify:track:1aGlassHarborLight0001"},
    {"spotify": 7},
    {},
    None,
    "https://open.spotify.com/track/1aGlassHarborLight0001",
])
def test_link_that_does_not_start_with_the_spotify_web_address_is_left_out(token_file, external_urls):
    # Phase 5d F4
    def change(track):
        track["external_urls"] = external_urls

    document = read_first_song(token_file, change)

    assert document.text == "Song: Glass Harbor Lights\nMusician: Mira Solen\nAlbum: Night Ferries"


def test_song_metadata_has_name_empty_path_musician_album_type_song_and_the_liked_time_as_strings(token_file):
    # Phase 5d F5
    metadata = song(make_resource(make_api(), token_file).read_documents(), "Glass Harbor Lights").metadata

    assert metadata == {
        "name": "Glass Harbor Lights",
        "path": "",
        "musician": "Mira Solen",
        "album": "Night Ferries",
        "type": "song",
        "timestamp": "2026-10-02T18:20:11Z",
    }
    assert all(isinstance(value, str) for value in metadata.values())


@pytest.mark.parametrize("added_at", [None, 7, ""])
def test_missing_liked_time_gives_an_empty_timestamp(token_file, added_at):
    # Phase 5d F5
    data = recorded()
    data["tracks"]["0"]["items"][0]["added_at"] = added_at

    documents = make_resource(make_api(data), token_file).read_documents()

    assert song(documents, "Glass Harbor Lights").metadata["timestamp"] == ""


PRIVATE_FOLDER_MODE = 0o700


def test_token_file_in_a_missing_folder_makes_the_folder_readable_by_the_learner_only(tmp_path, monkeypatch):
    # Phase 5d D12 (the mode is set again after makedirs, since the umask can mask it; POSIX bits are checked on POSIX)
    folder = tmp_path / "secrets"
    made: list[tuple[str, int]] = []
    changed: list[tuple[str, int]] = []
    real_makedirs, real_chmod = os.makedirs, os.chmod

    def recording_makedirs(name, mode=0o777, exist_ok=False):
        made.append((str(name), mode))
        real_makedirs(name, mode=mode, exist_ok=exist_ok)

    def recording_chmod(path, mode, **kwargs):
        changed.append((str(path), mode))
        real_chmod(path, mode, **kwargs)

    monkeypatch.setattr(os, "makedirs", recording_makedirs)
    monkeypatch.setattr(os, "chmod", recording_chmod)

    spotify_resource.write_token_file(folder / "spotify_token.json", REFRESH_TOKEN)

    monkeypatch.undo()
    assert made == [(str(folder), PRIVATE_FOLDER_MODE)]
    assert changed == [(str(folder), PRIVATE_FOLDER_MODE)]
    assert json.loads((folder / "spotify_token.json").read_text(encoding="utf-8")) == {"refresh_token": REFRESH_TOKEN}
    if os.name == "posix":
        assert folder.stat().st_mode & 0o777 == PRIVATE_FOLDER_MODE


def test_token_file_in_an_existing_folder_leaves_the_folder_as_it_is(token_file, monkeypatch):
    # Phase 5d D12
    changed: list[str] = []
    monkeypatch.setattr(os, "chmod", lambda path, mode, **kwargs: changed.append(str(path)))

    spotify_resource.write_token_file(token_file, ROTATED_REFRESH_TOKEN)

    monkeypatch.undo()
    assert changed == []
    assert json.loads(token_file.read_text(encoding="utf-8")) == {"refresh_token": ROTATED_REFRESH_TOKEN}


def record_temporary_handles(monkeypatch) -> list[int]:
    handles: list[int] = []
    real_mkstemp = spotify_resource.tempfile.mkstemp

    def recording_mkstemp(**kwargs):
        handle, name = real_mkstemp(**kwargs)
        handles.append(handle)
        return handle, name

    monkeypatch.setattr(spotify_resource.tempfile, "mkstemp", recording_mkstemp)
    return handles


def is_closed(handle: int) -> bool:
    try:
        os.fstat(handle)
    except OSError:
        return True
    return False


def test_temporary_file_is_closed_and_removed_when_it_cannot_be_opened(token_file, monkeypatch):
    # Phase 5d D12
    handles = record_temporary_handles(monkeypatch)

    def refusing_fdopen(handle, *args, **kwargs):
        raise OSError("cannot open the temporary file")

    monkeypatch.setattr(os, "fdopen", refusing_fdopen)

    with pytest.raises(OSError):
        spotify_resource.write_token_file(token_file, ROTATED_REFRESH_TOKEN)

    monkeypatch.undo()
    assert is_closed(handles[0])
    assert list(token_file.parent.iterdir()) == [token_file]
    assert json.loads(token_file.read_text(encoding="utf-8")) == {"refresh_token": REFRESH_TOKEN}


def test_temporary_file_is_closed_and_removed_when_the_write_fails(token_file, monkeypatch):
    # Phase 5d D12
    handles = record_temporary_handles(monkeypatch)

    def failing_dump(content, file):
        raise OSError("disk full")

    monkeypatch.setattr(spotify_resource.json, "dump", failing_dump)

    with pytest.raises(OSError):
        spotify_resource.write_token_file(token_file, ROTATED_REFRESH_TOKEN)

    monkeypatch.undo()
    assert is_closed(handles[0])
    assert list(token_file.parent.iterdir()) == [token_file]
    assert json.loads(token_file.read_text(encoding="utf-8")) == {"refresh_token": REFRESH_TOKEN}


def test_error_code_reuses_the_shared_json_parsing_and_the_song_count_is_the_documents_count():
    # Phase 5d H3
    assert ".json()" not in inspect.getsource(spotify_resource.answer_error_code)
    assert "songs" not in {item.name for item in dataclasses.fields(spotify_resource.ItemCounts)}
