import base64
import copy
import json
import socket
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from fakes import FakeSpotifyApi, load_fixture
from settings import Settings, load_settings
import spotify_authorize
from spotify_authorize import (
    REDIRECT_HOST,
    REDIRECT_URI,
    Outcome,
    answer_page,
    build_authorize_url,
    handle_callback,
    main,
    new_state,
    wait_for_callback,
)
from resources.spotify_resource import SpotifyCredentials

CLIENT_ID = "spotify-test-client-id"
CLIENT_SECRET = "spotify-test-client-secret"
CODE = "spotify-test-approval-code"
STATE = "spotify-test-state"
APPROVED_REFRESH_TOKEN = "spotify-test-approved-refresh-token"
FIRST_ACCESS_TOKEN = "spotify-test-first-access-token"
OLD_REFRESH_TOKEN = "spotify-test-old-refresh-token"
BASIC_CREDENTIALS = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode("ascii")).decode("ascii")
SECRETS = [CODE, CLIENT_SECRET, APPROVED_REFRESH_TOKEN, FIRST_ACCESS_TOKEN, BASIC_CREDENTIALS]
CREDENTIALS = SpotifyCredentials(CLIENT_ID, CLIENT_SECRET)
WAIT_SECONDS = 10.0
SHORT_WAIT_SECONDS = 0.5


def recorded():
    return copy.deepcopy(load_fixture("spotify_recorded.json"))


def make_api(*token_answers: httpx.Response | Exception) -> FakeSpotifyApi:
    data = recorded()
    data["token"] = data["authorization_code_token"]
    return FakeSpotifyApi(data, {"token": list(token_answers)})


def callback(api, token_file: Path, params: dict[str, str]) -> Outcome:
    with api.client() as client:
        return handle_callback(params, STATE, CREDENTIALS, token_file, client, sleep=lambda _: None)


def unprinted(text: str) -> bool:
    return not any(secret in text for secret in SECRETS)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((REDIRECT_HOST, 0))
        return probe.getsockname()[1]


def query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


def test_approval_address_is_spotifys_authorize_address_with_the_code_flow_the_library_scope_and_the_state():
    # Phase 5d C1
    url = build_authorize_url(CLIENT_ID, STATE)

    parts = urlsplit(url)
    assert (parts.scheme, parts.netloc, parts.path) == ("https", "accounts.spotify.com", "/authorize")
    assert query(url) == {
        "response_type": ["code"],
        "client_id": [CLIENT_ID],
        "scope": ["user-library-read"],
        "redirect_uri": ["http://127.0.0.1:8888/callback"],
        "state": [STATE],
    }
    assert REDIRECT_URI == "http://127.0.0.1:8888/callback"


def test_two_runs_have_different_random_states():
    # Phase 5d C2
    states = {new_state() for _ in range(5)}

    assert len(states) == 5
    assert all(len(state) >= 32 for state in states)


def test_callback_with_the_right_state_exchanges_the_code_with_the_redirect_address_and_the_basic_header(tmp_path):
    # Phase 5d C3
    api = make_api()

    callback(api, tmp_path / "spotify_token.json", {"code": CODE, "state": STATE})

    exchange = api.requests[0]
    assert len(api.requests) == 1
    assert (exchange.method, str(exchange.url)) == ("POST", "https://accounts.spotify.com/api/token")
    assert exchange.headers["Authorization"] == f"Basic {BASIC_CREDENTIALS}"
    assert api.form() == {"grant_type": "authorization_code", "code": CODE, "redirect_uri": REDIRECT_URI}
    assert CODE not in str(exchange.url) and CLIENT_SECRET not in str(exchange.url)


def test_successful_exchange_writes_the_refresh_token_and_prints_no_token(tmp_path, capsys):
    # Phase 5d C4
    token_file = tmp_path / "secrets" / "spotify_token.json"  # the folder is made

    outcome = callback(make_api(), token_file, {"code": CODE, "state": STATE})

    assert outcome.succeeded is True
    assert json.loads(token_file.read_text(encoding="utf-8")) == {"refresh_token": APPROVED_REFRESH_TOKEN}
    assert list(token_file.parent.iterdir()) == [token_file]
    captured = capsys.readouterr()
    assert unprinted(captured.out + captured.err + outcome.message)


@pytest.mark.parametrize("params", [
    {"code": CODE, "state": "another-state"},
    {"code": CODE},
    {"code": CODE, "state": ""},
    {"error": "access_denied", "state": "another-state"},
])
def test_callback_with_another_state_exchanges_nothing_and_writes_no_file(tmp_path, params):
    # Phase 5d C5
    api = make_api()
    token_file = tmp_path / "spotify_token.json"

    outcome = callback(api, token_file, params)

    assert outcome.succeeded is False
    assert "state" in outcome.message
    assert api.requests == []
    assert not token_file.exists()
    assert unprinted(outcome.message)


def test_callback_with_access_denied_writes_no_file_and_says_the_approval_was_refused(tmp_path):
    # Phase 5d C6
    api = make_api()
    token_file = tmp_path / "spotify_token.json"

    outcome = callback(api, token_file, {"error": "access_denied", "state": STATE})

    assert outcome.succeeded is False
    assert "refused" in outcome.message
    assert api.requests == []
    assert not token_file.exists()


@pytest.mark.parametrize("params", [{"state": STATE}, {"state": STATE, "code": ""}, {"state": STATE, "error": "server_error"}])
def test_callback_without_a_code_writes_no_file(tmp_path, params):
    # Phase 5d C6
    api = make_api()
    token_file = tmp_path / "spotify_token.json"

    outcome = callback(api, token_file, params)

    assert outcome.succeeded is False
    assert api.requests == []
    assert not token_file.exists()


@pytest.mark.parametrize(("answer", "status"), [
    (httpx.Response(400, json={"error": "invalid_grant", "error_description": f"Invalid authorization code {CODE}"}), "400"),
    (httpx.Response(401, json={"error": "invalid_client", "error_description": "Invalid client secret"}), "401"),
])
def test_exchange_that_spotify_refuses_writes_no_file_and_the_message_holds_the_status_only(tmp_path, capsys, answer, status):
    # Phase 5d C7
    token_file = tmp_path / "spotify_token.json"

    outcome = callback(make_api(answer), token_file, {"code": CODE, "state": STATE})

    assert outcome.succeeded is False
    assert status in outcome.message
    assert not token_file.exists()
    captured = capsys.readouterr()
    assert unprinted(captured.out + captured.err + outcome.message)


@pytest.mark.parametrize("answer", [
    httpx.Response(200, json={"access_token": FIRST_ACCESS_TOKEN, "token_type": "Bearer"}),
    httpx.Response(200, content=f"<html>{FIRST_ACCESS_TOKEN}</html>".encode("utf-8")),
])
def test_exchange_answer_without_a_refresh_token_writes_no_file(tmp_path, answer):
    # Phase 5d C7
    token_file = tmp_path / "spotify_token.json"

    outcome = callback(make_api(answer), token_file, {"code": CODE, "state": STATE})

    assert outcome.succeeded is False
    assert not token_file.exists()
    assert unprinted(outcome.message)


@pytest.mark.parametrize(("settings", "key"), [
    (Settings(spotify_client_secret=CLIENT_SECRET, spotify_token_file="rag/secrets/spotify_token.json"), "RAG_SPOTIFY_CLIENT_ID"),
    (Settings(spotify_client_id=CLIENT_ID, spotify_token_file="rag/secrets/spotify_token.json"), "RAG_SPOTIFY_CLIENT_SECRET"),
    (Settings(spotify_client_id=CLIENT_ID, spotify_client_secret=CLIENT_SECRET), "RAG_SPOTIFY_TOKEN_FILE"),
])
def test_missing_setting_stops_the_helper_before_the_browser_opens_and_names_the_key(capsys, settings, key):
    # Phase 5d C8
    opened: list[str] = []

    exit_code = main(settings_loader=lambda: settings, open_browser=opened.append, port=free_port())

    assert exit_code != 0
    assert opened == []
    captured = capsys.readouterr()
    assert key in captured.out + captured.err
    assert CLIENT_SECRET not in captured.out + captured.err


def test_new_approval_replaces_an_existing_token_file(tmp_path):
    # Phase 5d C9
    token_file = tmp_path / "spotify_token.json"
    token_file.write_text(json.dumps({"refresh_token": OLD_REFRESH_TOKEN}), encoding="utf-8")

    outcome = callback(make_api(), token_file, {"code": CODE, "state": STATE})

    assert outcome.succeeded is True
    assert json.loads(token_file.read_text(encoding="utf-8")) == {"refresh_token": APPROVED_REFRESH_TOKEN}
    assert list(tmp_path.iterdir()) == [token_file]


def send_from_a_browser(port: int, *paths: str) -> tuple[threading.Thread, list[httpx.Response]]:
    """Sends each request in order from another thread, as a browser would, while the server waits."""
    answers: list[httpx.Response] = []

    def browse():
        for path in paths:
            answers.append(httpx.get(f"http://{REDIRECT_HOST}:{port}{path}", timeout=WAIT_SECONDS))

    browser = threading.Thread(target=browse)
    browser.start()
    return browser, answers


def test_callback_server_listens_on_127_0_0_1_only_and_stops_after_one_answer(capsys):
    # Phase 5d C10
    received: list[dict[str, str]] = []
    servers: list = []
    browsers: list = []

    def on_listening(server):
        servers.append(server)
        browsers.append(send_from_a_browser(server.server_address[1], "/favicon.ico", f"/callback?code={CODE}&state={STATE}"))

    def handle(params):
        received.append(params)
        return Outcome(True, "The approval worked.")

    outcome = wait_for_callback(handle, port=0, on_listening=on_listening)

    browser, answers = browsers[0]
    browser.join(WAIT_SECONDS)
    assert REDIRECT_HOST == "127.0.0.1" and servers[0].server_address[0] == "127.0.0.1"
    assert outcome.succeeded is True
    assert received == [{"code": CODE, "state": STATE}]  # only the callback is handled
    assert [answer.status_code for answer in answers] == [404, 200]
    assert servers[0].socket.fileno() == -1  # the server is closed after its one answer
    captured = capsys.readouterr()
    assert CODE not in captured.out + captured.err  # the request line is not logged


def test_callback_server_gives_up_after_its_wait():
    # Phase 5d C10
    outcome = wait_for_callback(lambda params: Outcome(True, "unused"), port=0, timeout_seconds=0.05)

    assert outcome.succeeded is False
    assert "No answer" in outcome.message


@pytest.mark.parametrize(("outcome", "words"), [
    (Outcome(True, "saved"), "approval worked"),
    (Outcome(False, f"Spotify call failed: 400 on /api/token"), "approval did not work"),
])
def test_answer_page_says_whether_the_approval_worked_and_holds_no_code_or_token(outcome, words):
    # Phase 5d C11
    page = answer_page(outcome).decode("utf-8")

    assert words in page
    assert page.lstrip().lower().startswith("<!doctype html>")
    assert unprinted(page)


def test_whole_approval_opens_the_browser_saves_the_refresh_token_and_answers_the_browser(tmp_path, capsys):
    # Phase 5d C4 C10 C11
    port = free_port()
    token_file = tmp_path / "secrets" / "spotify_token.json"
    settings = Settings(
        spotify_client_id=CLIENT_ID, spotify_client_secret=CLIENT_SECRET, spotify_token_file=str(token_file)
    )
    api = make_api()
    opened: list[str] = []
    browsers: list = []

    def open_browser(url):
        opened.append(url)
        state = query(url)["state"][0]
        browsers.append(send_from_a_browser(port, f"/callback?code={CODE}&state={state}"))

    exit_code = main(settings_loader=lambda: settings, open_browser=open_browser, http_client_factory=api.client, port=port)

    browser, answers = browsers[0]
    browser.join(WAIT_SECONDS)
    assert exit_code == 0
    assert query(opened[0])["client_id"] == [CLIENT_ID]
    assert json.loads(token_file.read_text(encoding="utf-8")) == {"refresh_token": APPROVED_REFRESH_TOKEN}
    assert "approval worked" in answers[0].text and unprinted(answers[0].text)
    captured = capsys.readouterr()
    assert unprinted(captured.out + captured.err)


def test_whole_approval_that_fails_exits_with_an_error_code(tmp_path, capsys):
    # Phase 5d C5 C11
    port = free_port()
    token_file = tmp_path / "spotify_token.json"
    settings = Settings(
        spotify_client_id=CLIENT_ID, spotify_client_secret=CLIENT_SECRET, spotify_token_file=str(token_file)
    )
    browsers: list = []

    def open_browser(url):
        browsers.append(send_from_a_browser(port, f"/callback?code={CODE}&state=forged"))

    exit_code = main(
        settings_loader=lambda: settings,
        open_browser=open_browser,
        http_client_factory=make_api().client,
        port=port,
        timeout_seconds=SHORT_WAIT_SECONDS,
    )

    browser, answers = browsers[0]
    browser.join(WAIT_SECONDS)
    assert exit_code != 0
    assert not token_file.exists()
    assert "approval did not work" in answers[0].text
    assert "state" in capsys.readouterr().out



@pytest.mark.parametrize("state", ["\u015ftate", f"{STATE}\u00e9", "\U0001f3b5", "\u0131"])
def test_callback_whose_state_has_non_ascii_letters_is_a_state_mismatch_not_a_crash(tmp_path, state):
    # Phase 5d C12
    api = make_api()
    token_file = tmp_path / "spotify_token.json"

    outcome = callback(api, token_file, {"code": CODE, "state": state})

    assert outcome.succeeded is False
    assert "state" in outcome.message
    assert api.requests == []
    assert not token_file.exists()


def serve_callbacks(api, token_file: Path, *paths: str, timeout_seconds: float = WAIT_SECONDS):
    """Runs the callback server with the real handler while a browser sends the paths in order."""
    browsers: list = []

    def on_listening(server):
        browsers.append(send_from_a_browser(server.server_address[1], *paths))

    with api.client() as client:
        outcome = wait_for_callback(
            lambda params: handle_callback(params, STATE, CREDENTIALS, token_file, client, sleep=lambda _: None),
            port=0,
            on_listening=on_listening,
            timeout_seconds=timeout_seconds,
        )
    browser, answers = browsers[0]
    browser.join(WAIT_SECONDS)
    return outcome, answers


def test_stray_callbacks_get_the_refusal_page_and_the_helper_keeps_waiting_for_the_right_answer(tmp_path):
    # Phase 5d C12
    api = make_api()
    token_file = tmp_path / "spotify_token.json"

    outcome, answers = serve_callbacks(
        api,
        token_file,
        f"/callback?code={CODE}&state=%C5%9Ftate",  # a non-ASCII state
        f"/callback?code={CODE}",  # no state
        "/callback?error=access_denied&state=forged",
        f"/callback?code={CODE}&state={STATE}",
    )

    assert outcome.succeeded is True
    assert [answer.status_code for answer in answers] == [200, 200, 200, 200]
    assert ["approval did not work" in answer.text for answer in answers] == [True, True, True, False]
    assert "approval worked" in answers[3].text
    assert api.routes == ["token"]  # only the right answer is exchanged
    assert json.loads(token_file.read_text(encoding="utf-8")) == {"refresh_token": APPROVED_REFRESH_TOKEN}


def test_stray_callback_alone_ends_at_the_time_limit_with_the_state_message(tmp_path):
    # Phase 5d C12
    api = make_api()
    started = time.monotonic()

    outcome, answers = serve_callbacks(
        api, tmp_path / "spotify_token.json", f"/callback?code={CODE}&state=forged", timeout_seconds=SHORT_WAIT_SECONDS
    )

    assert time.monotonic() - started >= SHORT_WAIT_SECONDS
    assert outcome.succeeded is False and "state" in outcome.message
    assert "approval did not work" in answers[0].text
    assert api.requests == []


def test_error_answer_with_the_right_state_ends_the_wait(tmp_path):
    # Phase 5d C12 C14
    started = time.monotonic()

    outcome, answers = serve_callbacks(make_api(), tmp_path / "spotify_token.json", f"/callback?error=access_denied&state={STATE}")

    assert outcome.succeeded is False and "refused" in outcome.message
    assert "approval did not work" in answers[0].text
    assert time.monotonic() - started < WAIT_SECONDS / 2


def hold_idle_connection(port: int, seconds: float) -> threading.Thread:
    """Connects and sends nothing for the given seconds, as a stuck browser tab would."""
    def idle():
        with socket.create_connection((REDIRECT_HOST, port)):
            time.sleep(seconds)

    holder = threading.Thread(target=idle, daemon=True)
    holder.start()
    return holder


def test_connection_read_timeout_is_short():
    # Phase 5d C13
    assert 0 < spotify_authorize.CONNECTION_TIMEOUT_SECONDS <= 10.0


def test_idle_connection_is_closed_after_the_read_timeout_and_the_right_answer_is_still_served(monkeypatch):
    # Phase 5d C13
    monkeypatch.setattr(spotify_authorize, "CONNECTION_TIMEOUT_SECONDS", 0.2)
    browsers: list = []

    def on_listening(server):
        port = server.server_address[1]
        hold_idle_connection(port, 5.0)
        time.sleep(0.1)  # the idle connection is accepted first
        browsers.append(send_from_a_browser(port, f"/callback?code={CODE}&state={STATE}"))

    started = time.monotonic()
    outcome = wait_for_callback(lambda params: Outcome(True, "The approval worked."), port=0, on_listening=on_listening)

    browser, answers = browsers[0]
    browser.join(WAIT_SECONDS)
    assert outcome.succeeded is True
    assert answers[0].status_code == 200
    assert time.monotonic() - started < 3.0


def test_idle_connection_does_not_hold_the_helper_past_its_time_limit():
    # Phase 5d C13
    def on_listening(server):
        hold_idle_connection(server.server_address[1], 5.0)

    started = time.monotonic()
    outcome = wait_for_callback(
        lambda params: Outcome(True, "unused"), port=0, on_listening=on_listening, timeout_seconds=SHORT_WAIT_SECONDS
    )

    assert outcome.succeeded is False and "No answer" in outcome.message
    assert time.monotonic() - started < 3.0


@pytest.mark.parametrize("error", ["invalid_client", "invalid_scope", "server_error", "temporarily_unavailable"])
def test_callback_with_another_spotify_error_writes_no_file_and_names_that_error(tmp_path, error):
    # Phase 5d C14
    api = make_api()
    token_file = tmp_path / "spotify_token.json"

    outcome = callback(api, token_file, {"error": error, "state": STATE, "code": CODE})

    assert outcome.succeeded is False
    assert f"Spotify answered with the error {error}" in outcome.message
    assert api.requests == []
    assert not token_file.exists()


@pytest.mark.parametrize("error", ["<script>alert(1)</script>", "invalid scope", "a" * 65, "ge\u00e7ersiz", "x\ny"])
def test_callback_error_that_is_not_a_plain_word_is_not_echoed(tmp_path, error):
    # Phase 5d C14
    api = make_api()
    token_file = tmp_path / "spotify_token.json"

    outcome = callback(api, token_file, {"error": error, "state": STATE})

    assert outcome.succeeded is False
    assert "Spotify answered with an error" in outcome.message
    assert error not in outcome.message
    assert api.requests == []
    assert not token_file.exists()


def test_occupied_port_exits_with_code_1_and_says_the_port_is_in_use_without_a_stack_trace(capsys):
    # Phase 5d C15
    settings = Settings(
        spotify_client_id=CLIENT_ID, spotify_client_secret=CLIENT_SECRET, spotify_token_file="rag/secrets/spotify_token.json"
    )
    opened: list[str] = []
    with socket.socket() as other_program:
        other_program.bind((REDIRECT_HOST, 0))
        other_program.listen()
        port = other_program.getsockname()[1]

        exit_code = main(settings_loader=lambda: settings, open_browser=opened.append, port=port)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert f"Port {port}" in captured.out and "in use" in captured.out
    assert "Traceback" not in captured.out + captured.err
    assert opened == []


def test_callback_server_opens_its_port_for_the_helper_only():
    # Phase 5d C15 (Windows 11 already refuses a second bind on a listened port, so the options are checked too)
    options: list[tuple[int, int | None]] = []

    def on_listening(server):
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        options.append((
            server.socket.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR),
            None if exclusive is None else server.socket.getsockopt(socket.SOL_SOCKET, exclusive),
        ))

    wait_for_callback(lambda params: Outcome(True, "unused"), port=0, on_listening=on_listening, timeout_seconds=0.05)

    reuse_address, exclusive_use = options[0]
    assert spotify_authorize._CallbackServer.allow_reuse_address is False
    assert reuse_address == 0
    assert exclusive_use is None or exclusive_use != 0


@pytest.mark.parametrize("failure", [
    httpx.ConnectError("no route"),
    httpx.ReadTimeout("slow"),
    httpx.RemoteProtocolError("dropped"),
    httpx.Response(503, json={"error": "server_error"}),
])
def test_code_exchange_that_does_not_finish_is_not_tried_again_and_says_to_run_the_helper_again(tmp_path, failure):
    # Phase 5d D10
    api = make_api(failure)
    token_file = tmp_path / "spotify_token.json"
    sleeps: list[float] = []

    with api.client() as client:
        outcome = handle_callback({"code": CODE, "state": STATE}, STATE, CREDENTIALS, token_file, client, sleeps.append)

    assert outcome.succeeded is False
    assert "did not finish" in outcome.message and "Run the helper again" in outcome.message
    assert api.routes == ["token"]  # the code works only once
    assert sleeps == []
    assert not token_file.exists()
    assert unprinted(outcome.message)


def test_rate_limited_code_exchange_waits_retry_after_and_tries_again(tmp_path):
    # Phase 5d D10
    api = make_api(httpx.Response(429, headers={"Retry-After": "3"}))
    token_file = tmp_path / "spotify_token.json"
    sleeps: list[float] = []

    with api.client() as client:
        outcome = handle_callback({"code": CODE, "state": STATE}, STATE, CREDENTIALS, token_file, client, sleeps.append)

    assert outcome.succeeded is True
    assert sleeps == [3.0]
    assert api.routes == ["token", "token"]


@pytest.mark.parametrize("status", [400, 401])
def test_exchange_refused_for_the_client_says_to_check_the_client_id_and_secret(tmp_path, status):
    # Phase 5d D7
    answer = httpx.Response(status, json={"error": "invalid_client", "error_description": f"Bad {CLIENT_SECRET}"})

    outcome = callback(make_api(answer), tmp_path / "spotify_token.json", {"code": CODE, "state": STATE})

    assert outcome.succeeded is False
    assert "RAG_SPOTIFY_CLIENT_ID" in outcome.message and "RAG_SPOTIFY_CLIENT_SECRET" in outcome.message
    assert str(status) in outcome.message
    assert "Run the helper again" not in outcome.message
    assert unprinted(outcome.message) and "Bad" not in outcome.message


def test_exchange_failure_uses_the_resources_refusal_rule_and_its_own_client_message_name():
    # Phase 5d D7
    assert not hasattr(spotify_authorize, "REFUSED_SIGN_IN_STATUSES")
    assert not hasattr(spotify_authorize, "CLIENT_REFUSED_FORMAT")
    assert "RAG_SPOTIFY_CLIENT_ID" in spotify_authorize.EXCHANGE_CLIENT_REFUSED_FORMAT


@pytest.mark.parametrize("status", [400, 401])
def test_exchange_refused_for_the_code_says_to_run_the_helper_again(tmp_path, status):
    # Phase 5d D7
    answer = httpx.Response(status, json={"error": "invalid_grant", "error_description": f"Invalid code {CODE}"})

    outcome = callback(make_api(answer), tmp_path / "spotify_token.json", {"code": CODE, "state": STATE})

    assert outcome.succeeded is False
    assert str(status) in outcome.message and "Run the helper again" in outcome.message
    assert "RAG_SPOTIFY_CLIENT" not in outcome.message
    assert unprinted(outcome.message)


@pytest.mark.parametrize(("answer", "refused"), [
    (httpx.Response(400, json={"error": "invalid_request", "error_description": f"Bad {CODE}"}),
     "Spotify refused the request (400 invalid_request on /api/token)"),
    (httpx.Response(401, json={"error": "unsupported_grant_type"}),
     "Spotify refused the request (401 unsupported_grant_type on /api/token)"),
    (httpx.Response(400, content=b"<html>invalid_client</html>"), "Spotify refused the request (400 on /api/token)"),
    (httpx.Response(400, content=b""), "Spotify refused the request (400 on /api/token)"),
])
def test_exchange_with_another_refusal_names_the_status_and_the_error_and_does_not_ask_for_a_new_approval(
    tmp_path, answer, refused
):
    # Phase 5d D7
    token_file = tmp_path / "spotify_token.json"

    outcome = callback(make_api(answer), token_file, {"code": CODE, "state": STATE})

    assert outcome.succeeded is False
    assert outcome.message == f"{refused}: nothing was saved."
    assert not token_file.exists()
    assert unprinted(outcome.message)


def read_until_the_server_closes(port: int, path: str) -> tuple[threading.Thread, list[bytes]]:
    """Sends one request and reads until the server closes first, so the server's side of the connection is
    the one left in TIME_WAIT on its port."""
    answers: list[bytes] = []

    def browse():
        with socket.create_connection((REDIRECT_HOST, port), timeout=WAIT_SECONDS) as connection:
            connection.sendall(f"GET {path} HTTP/1.1\r\nHost: {REDIRECT_HOST}:{port}\r\n\r\n".encode("ascii"))
            answer = b""
            while chunk := connection.recv(4096):
                answer += chunk
            answers.append(answer)

    browser = threading.Thread(target=browse)
    browser.start()
    return browser, answers


def test_helper_run_again_at_once_can_open_the_same_port_after_answering_a_browser():
    # Phase 5d C16 (the server closed the answered connection, which waits in TIME_WAIT on its port)
    port = free_port()
    browsers: list = []

    def on_listening(server):
        browsers.append(read_until_the_server_closes(port, f"/callback?code={CODE}&state={STATE}"))

    outcome = wait_for_callback(lambda params: Outcome(True, "The approval worked."), port=port, on_listening=on_listening)
    browser, answers = browsers[0]
    browser.join(WAIT_SECONDS)

    again = spotify_authorize._CallbackServer(port, lambda params: Outcome(True, "unused"), time.monotonic)
    again.server_close()
    assert outcome.succeeded is True and answers[0].startswith(b"HTTP/1.0 200")


@pytest.mark.parametrize(("env", "key"), [
    ("RAG_BATCH_SIZE=many", "RAG_BATCH_SIZE"),
    ("RAG_TEXT_THRESHOLD=high", "RAG_TEXT_THRESHOLD"),
    ("RAG_REBUILD_COOLDOWN_MINUTES=-1", "RAG_REBUILD_COOLDOWN_MINUTES"),
])
def test_invalid_setting_stops_the_helper_with_code_1_and_a_clear_message_without_a_stack_trace(tmp_path, capsys, env, key):
    # Phase 5d C17
    env_file = tmp_path / ".env"
    lines = [
        f"RAG_SPOTIFY_CLIENT_ID={CLIENT_ID}",
        f"RAG_SPOTIFY_CLIENT_SECRET={CLIENT_SECRET}",
        f"RAG_SPOTIFY_TOKEN_FILE={tmp_path / 'spotify_token.json'}",
        env,
    ]
    env_file.write_text("\n".join(lines), encoding="utf-8")
    opened: list[str] = []

    exit_code = main(settings_loader=lambda: load_settings(env_file, environ={}), open_browser=opened.append, port=free_port())

    captured = capsys.readouterr()
    assert exit_code == 1
    assert key in captured.out
    assert "Traceback" not in captured.out + captured.err
    assert CLIENT_SECRET not in captured.out + captured.err
    assert opened == []


def test_programming_error_while_loading_the_settings_is_not_hidden():
    # Phase 5d C17 (only the settings errors are turned into a message)
    def broken_loader():
        raise TypeError("a programming error")

    with pytest.raises(TypeError):
        main(settings_loader=broken_loader, open_browser=lambda url: None, port=free_port())
