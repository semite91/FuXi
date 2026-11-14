"""Spotify approval helper, run once by the Learner from /rag with: python spotify_authorize.py

It opens Spotify's approval page in the browser, waits for Spotify's answer on 127.0.0.1:8888, checks the state
value, exchanges the code for tokens and writes the refresh token to the RAG_SPOTIFY_TOKEN_FILE file. It is run
again when Spotify stops accepting the refresh token. Nothing secret is printed.
"""

import html
import secrets
import socket
import sys
import time
import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from resources.http_retry import MIN_SERVER_ERROR_STATUS, ReadStats, create_http_client
from resources.spotify_resource import (
    REFRESH_TOKEN_FIELD,
    Refusal,
    SpotifyCredentials,
    SpotifyError,
    plain_error_code,
    request_tokens,
    spotify_credentials,
    write_token_file,
)
from settings import (
    SPOTIFY_CLIENT_ID_KEY,
    SPOTIFY_CLIENT_SECRET_KEY,
    SPOTIFY_TOKEN_FILE_KEY,
    ConfigurationError,
    Settings,
    load_settings,
)

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
LIBRARY_SCOPE = "user-library-read"
CODE_RESPONSE_TYPE = "code"
AUTHORIZATION_CODE_GRANT = "authorization_code"
REDIRECT_HOST = "127.0.0.1"
REDIRECT_PORT = 8888
CALLBACK_PATH = "/callback"
REDIRECT_URI = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}{CALLBACK_PATH}"
STATE_BYTES = 32
# The state values are compared as bytes, so a value with any letter is compared, not refused with an error.
STATE_ENCODING = "utf-8"
STATE_PARAM = "state"
CODE_PARAM = "code"
ERROR_PARAM = "error"
ACCESS_DENIED_ERROR = "access_denied"
APPROVAL_WAIT_SECONDS = 300.0
# A connection that sends nothing is closed after this many seconds, never later than the approval's time limit.
CONNECTION_TIMEOUT_SECONDS = 5.0
# A connection accepted at the time limit still gets a moment to be read.
MIN_CONNECTION_TIMEOUT_SECONDS = 0.01
# The value that turns a socket option on.
EXCLUSIVE_USE_ON = 1

STATUS_OK = 200
STATUS_NOT_FOUND = 404
PAGE_ENCODING = "utf-8"
PAGE_CONTENT_TYPE = f"text/html; charset={PAGE_ENCODING}"
CONTENT_TYPE_HEADER = "Content-Type"
CONTENT_LENGTH_HEADER = "Content-Length"
PAGE_FORMAT = (
    "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>FuXi Spotify approval</title></head>"
    "<body><h1>FuXi Spotify approval</h1><p>{text}</p></body></html>"
)
SUCCESS_PAGE_TEXT = "The approval worked. You can close this tab."
FAILURE_PAGE_TEXT = "The approval did not work. The terminal says why."

SUCCESS_EXIT_CODE = 0
FAILURE_EXIT_CODE = 1
SAVED_MESSAGE = f"The approval worked: the refresh token is saved in the {SPOTIFY_TOKEN_FILE_KEY} file."
STATE_MISMATCH_MESSAGE = "The answer's state value is not this run's: nothing was saved. Run the helper again."
STRAY_ANSWER_MESSAGE = "An answer that is not this run's was refused: still waiting for Spotify's answer."
ACCESS_DENIED_MESSAGE = "The approval was refused in Spotify: nothing was saved."
SPOTIFY_ERROR_FORMAT = "Spotify answered with the error {error}: nothing was saved."
UNNAMED_ERROR_MESSAGE = "Spotify answered with an error: nothing was saved."
NO_CODE_MESSAGE = "Spotify's answer has no approval code: nothing was saved."
EXCHANGE_REFUSED_FORMAT = (
    "Spotify did not exchange the approval code ({error}): nothing was saved. Run the helper again."
)
EXCHANGE_CLIENT_REFUSED_FORMAT = (
    "Spotify refused the client ({error}): nothing was saved. "
    f"Check {SPOTIFY_CLIENT_ID_KEY} and {SPOTIFY_CLIENT_SECRET_KEY}."
)
EXCHANGE_REQUEST_REFUSED_FORMAT = "{refused}: nothing was saved."
EXCHANGE_UNFINISHED_FORMAT = (
    "The exchange of the approval code did not finish ({error}): nothing was saved. Run the helper again."
)
NO_REFRESH_TOKEN_MESSAGE = "Spotify's answer has no refresh token: nothing was saved."
UNWRITABLE_MESSAGE = f"The {SPOTIFY_TOKEN_FILE_KEY} file cannot be written: nothing was saved."
NO_ANSWER_MESSAGE = "No answer came from Spotify in time: nothing was saved. Run the helper again."
PORT_IN_USE_FORMAT = (
    f"Port {{port}} on {REDIRECT_HOST} is in use or cannot be opened: nothing was saved. "
    "Close the program that uses it and run the helper again."
)
OPENING_MESSAGE = "Opening Spotify's approval page in the browser. If it does not open, visit:\n{url}"


@dataclass(frozen=True)
class Outcome:
    """How an answer was handled; the message never holds the code, a token or the client secret. An answer
    that is not this run's does not end the wait."""

    succeeded: bool
    message: str
    ends_wait: bool = True


def new_state() -> str:
    """A random value that ties Spotify's answer to this run."""
    return secrets.token_urlsafe(STATE_BYTES)


def build_authorize_url(client_id: str, state: str) -> str:
    params = {
        "response_type": CODE_RESPONSE_TYPE,
        "client_id": client_id,
        "scope": LIBRARY_SCOPE,
        "redirect_uri": REDIRECT_URI,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def handle_callback(
    params: Mapping[str, str],
    expected_state: str,
    credentials: SpotifyCredentials,
    token_file: Path,
    client: httpx.Client,
    sleep: Callable[[float], None] = time.sleep,
) -> Outcome:
    """Checks Spotify's answer and, when it holds this run's state and a code, saves the refresh token. The code
    works only once, so its exchange is tried again only after a 429 (see request_tokens)."""
    if not _is_this_runs_state(params.get(STATE_PARAM, ""), expected_state):
        return Outcome(False, STATE_MISMATCH_MESSAGE, ends_wait=False)
    if ERROR_PARAM in params:
        return Outcome(False, _spotify_error_message(params[ERROR_PARAM]))
    code = params.get(CODE_PARAM)
    if not code:
        return Outcome(False, NO_CODE_MESSAGE)
    form = {"grant_type": AUTHORIZATION_CODE_GRANT, "code": code, "redirect_uri": REDIRECT_URI}
    try:
        tokens = request_tokens(client, credentials, form, ReadStats(), sleep)
    except SpotifyError as error:
        return Outcome(False, _exchange_failure_message(error))
    refresh_token = tokens.get(REFRESH_TOKEN_FIELD)
    if not isinstance(refresh_token, str) or not refresh_token:
        return Outcome(False, NO_REFRESH_TOKEN_MESSAGE)
    try:
        write_token_file(token_file, refresh_token)
    except OSError:
        return Outcome(False, UNWRITABLE_MESSAGE)
    return Outcome(True, SAVED_MESSAGE)


def _is_this_runs_state(state: str, expected_state: str) -> bool:
    return secrets.compare_digest(state.encode(STATE_ENCODING), expected_state.encode(STATE_ENCODING))


def _spotify_error_message(error: str) -> str:
    """Names Spotify's error only when it is a short plain word, so no other input is echoed."""
    if error == ACCESS_DENIED_ERROR:
        return ACCESS_DENIED_MESSAGE
    error_code = plain_error_code(error)
    return SPOTIFY_ERROR_FORMAT.format(error=error_code) if error_code else UNNAMED_ERROR_MESSAGE


def _exchange_failure_message(error: SpotifyError) -> str:
    """A refused client, a refused code, another refused request, or an exchange that did not finish (no answer
    or a server error)."""
    if error.status is None or error.status >= MIN_SERVER_ERROR_STATUS:
        return EXCHANGE_UNFINISHED_FORMAT.format(error=error)
    refusal = error.refusal()
    if refusal is Refusal.CLIENT:
        return EXCHANGE_CLIENT_REFUSED_FORMAT.format(error=error)
    if refusal is Refusal.REQUEST:
        return EXCHANGE_REQUEST_REFUSED_FORMAT.format(refused=error.request_refused_message())
    return EXCHANGE_REFUSED_FORMAT.format(error=error)


def answer_page(outcome: Outcome) -> bytes:
    """The browser's page: whether the approval worked, without the reason (the terminal has it)."""
    text = SUCCESS_PAGE_TEXT if outcome.succeeded else FAILURE_PAGE_TEXT
    return PAGE_FORMAT.format(text=html.escape(text)).encode(PAGE_ENCODING)


class _CallbackServer(HTTPServer):
    """Serves until an answer of this run reaches the callback path; other paths (a browser's favicon) answer
    404, and an answer with another state gets the refusal page while the server keeps waiting. The port is the
    helper's only: it is never shared with a program that already listens on it."""

    allow_reuse_address = False

    def __init__(self, port: int, handle: Callable[[dict[str, str]], Outcome], clock: Callable[[], float]) -> None:
        super().__init__((REDIRECT_HOST, port), _CallbackHandler)
        self.handle = handle
        self.clock = clock
        self.deadline = float("inf")
        self.outcome: Outcome | None = None
        self.stray_outcome: Outcome | None = None

    def server_bind(self) -> None:
        """On Windows the port is also claimed for exclusive use, so no other socket can bind it as well."""
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, EXCLUSIVE_USE_ON)
        super().server_bind()

    def connection_timeout(self) -> float:
        """The read timeout of one connection: short, and never past the approval's time limit."""
        remaining = self.deadline - self.clock()
        return max(min(CONNECTION_TIMEOUT_SECONDS, remaining), MIN_CONNECTION_TIMEOUT_SECONDS)

    def keep(self, outcome: Outcome) -> None:
        if outcome.ends_wait:
            self.outcome = outcome
        else:
            self.stray_outcome = outcome
            print(STRAY_ANSWER_MESSAGE)


class _CallbackHandler(BaseHTTPRequestHandler):
    server: _CallbackServer

    def setup(self) -> None:
        self.timeout = self.server.connection_timeout()
        super().setup()

    def do_GET(self) -> None:
        address = urlsplit(self.path)
        if address.path != CALLBACK_PATH:
            self.send_error(STATUS_NOT_FOUND)
            return
        params = {name: values[0] for name, values in parse_qs(address.query).items()}
        outcome = self.server.handle(params)
        self.server.keep(outcome)
        page = answer_page(outcome)
        self.send_response(STATUS_OK)
        self.send_header(CONTENT_TYPE_HEADER, PAGE_CONTENT_TYPE)
        self.send_header(CONTENT_LENGTH_HEADER, str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, format: str, *args: Any) -> None:
        """Nothing is logged: the request line holds the approval code."""


def wait_for_callback(
    handle: Callable[[dict[str, str]], Outcome],
    port: int = REDIRECT_PORT,
    on_listening: Callable[[HTTPServer], None] | None = None,
    timeout_seconds: float = APPROVAL_WAIT_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> Outcome:
    """Listens on 127.0.0.1 only until this run's callback or the time limit, then closes; on_listening runs once
    it listens. A port that cannot be opened ends it at once."""
    try:
        server = _CallbackServer(port, handle, clock)
    except OSError:
        # The cause is dropped: the helper says which port, without a stack trace.
        return Outcome(False, PORT_IN_USE_FORMAT.format(port=port))
    with server:
        if on_listening is not None:
            on_listening(server)
        server.deadline = clock() + timeout_seconds
        while server.outcome is None and (remaining := server.deadline - clock()) > 0:
            server.timeout = remaining
            server.handle_request()
        return server.outcome or server.stray_outcome or Outcome(False, NO_ANSWER_MESSAGE)


def main(
    settings_loader: Callable[[], Settings] = load_settings,
    open_browser: Callable[[str], Any] = webbrowser.open,
    http_client_factory: Callable[[], httpx.Client] = create_http_client,
    port: int = REDIRECT_PORT,
    timeout_seconds: float = APPROVAL_WAIT_SECONDS,
) -> int:
    try:
        settings = settings_loader()
        credentials = spotify_credentials(settings)
        token_file = settings.require_spotify_token_file()
    except ConfigurationError as error:
        # The message names the key; the stack trace is left out.
        print(error)
        return FAILURE_EXIT_CODE
    state = new_state()
    url = build_authorize_url(credentials.client_id, state)

    def show_approval_page(server: HTTPServer) -> None:
        print(OPENING_MESSAGE.format(url=url))
        open_browser(url)

    with http_client_factory() as client:
        outcome = wait_for_callback(
            lambda params: handle_callback(params, state, credentials, token_file, client),
            port,
            on_listening=show_approval_page,
            timeout_seconds=timeout_seconds,
        )
    print(outcome.message)
    return SUCCESS_EXIT_CODE if outcome.succeeded else FAILURE_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
