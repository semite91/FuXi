"""Spotify resource: the Learner's liked songs, as one text document per song."""

import json
import os
import re
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

from base import (
    METADATA_ALBUM,
    METADATA_MUSICIAN,
    METADATA_NAME,
    METADATA_PATH,
    METADATA_TIMESTAMP,
    METADATA_TYPE,
    NO_PATH,
    SONG_DOCUMENT_TYPE,
    Document,
    Resource,
    ResourceKind,
)
from resources.document_fields import (
    LINE_SEPARATOR,
    SUMMARY_SEPARATOR,
    clean_text,
    join_names,
    json_entries,
    labelled_lines,
    unique_names,
)
from resources.http_retry import (
    NO_ENDPOINT,
    ApiCallError,
    Clock,
    ReadStats,
    basic_header,
    bearer_header,
    call_json,
    create_http_client,
    http_retry_wait,
    json_object_or_none,
    rate_limit_retry_wait,
    timed_read,
)
from settings import SPOTIFY_CLIENT_ID_KEY, SPOTIFY_CLIENT_SECRET_KEY, SPOTIFY_TOKEN_FILE_KEY, Settings

RESOURCE_NAME = "spotify"

TOKEN_URL = "https://accounts.spotify.com/api/token"
TOKEN_ENDPOINT = httpx.URL(TOKEN_URL).path
# Every page of liked songs is asked on this address; a next link that leaves it is not followed.
LIKED_SONGS_URL = "https://api.spotify.com/v1/me/tracks"
LIKED_SONGS_ADDRESS = httpx.URL(LIKED_SONGS_URL)
LIKED_SONGS_ENDPOINT = LIKED_SONGS_ADDRESS.path
PAGE_SIZE = 50
FIRST_PAGE_URL = str(LIKED_SONGS_ADDRESS.copy_with(params={"limit": PAGE_SIZE}))
NO_USERINFO = b""
ITEMS_FIELD = "items"
NEXT_FIELD = "next"
NO_ITEM_LIST_FAILURE = "a page without an item list"
EMPTY_PAGE_WITH_NEXT_FAILURE = "an empty page with a next link"
OFF_ADDRESS_NEXT_FAILURE = "a next link off the liked songs address"
REPEATED_NEXT_FAILURE = "a next link already followed"
BACKWARD_NEXT_FAILURE = "a next link whose offset does not move forward"
OFFSET_PARAM = "offset"
# The first call asks for no offset, which Spotify reads as 0.
FIRST_PAGE_OFFSET = 0
REFRESH_TOKEN_GRANT = "refresh_token"
ACCESS_TOKEN_FIELD = "access_token"
REFRESH_TOKEN_FIELD = "refresh_token"
# Spotify answers a request it refuses with a 400 or a 401; the error code tells what it refused.
REFUSED_STATUSES = frozenset({400, 401})
NO_ACCESS_TOKEN_FAILURE = "an answer without an access token"
SIGN_IN_REFUSED_FORMAT = "Spotify refused the refresh token ({status} on {endpoint}): run spotify_authorize.py again"
CLIENT_REFUSED_FORMAT = (
    "Spotify refused the client ({status} on {endpoint}): "
    f"check {SPOTIFY_CLIENT_ID_KEY} and {SPOTIFY_CLIENT_SECRET_KEY}"
)
REQUEST_REFUSED_FORMAT = "Spotify refused the request ({failure} on {endpoint})"
STATUS_AND_ERROR_CODE_FORMAT = "{status} {error_code}"
# The "error" field of Spotify's OAuth answers, such as invalid_grant or invalid_client.
ERROR_CODE_FIELD = "error"
INVALID_CLIENT_ERROR = "invalid_client"
INVALID_GRANT_ERROR = "invalid_grant"
# An error code is kept only when it is a short plain word, so no other input reaches a message.
PLAIN_ERROR_CODE = re.compile(r"[A-Za-z0-9_]{1,64}")
NO_ERROR_CODE = ""

TOKEN_FILE_ENCODING = "utf-8"
TEMPORARY_FILE_SUFFIX = ".tmp"
# A token folder the helper makes is readable by the Learner only.
PRIVATE_FOLDER_MODE = 0o700
TOKEN_FILE_MISSING_MESSAGE = f"The {SPOTIFY_TOKEN_FILE_KEY} file does not exist: run spotify_authorize.py"
TOKEN_FILE_INVALID_MESSAGE = (
    f"The {SPOTIFY_TOKEN_FILE_KEY} file is not JSON with a refresh token: run spotify_authorize.py again"
)
TOKEN_FILE_UNREADABLE_MESSAGE = (
    f"The {SPOTIFY_TOKEN_FILE_KEY} file cannot be read: check it or run spotify_authorize.py again"
)
TOKEN_FILE_UNWRITABLE_MESSAGE = f"The new refresh token cannot be written to the {SPOTIFY_TOKEN_FILE_KEY} file"

SONG_TRACK_TYPE = "track"
# Only a web link to the song is kept; a local file or any other address is left out.
SONG_LINK_PREFIX = "https://open.spotify.com/"
SONG_LABEL = "Song"
MUSICIAN_LABEL = "Musician"
ALBUM_LABEL = "Album"
LINK_LABEL = "Link"


class Refusal(Enum):
    """What Spotify's token address refused: the client (its id or secret), the sign-in (a code or refresh
    token), another request (any other 400 or 401), or nothing (any other failure)."""

    CLIENT = "client"
    SIGN_IN = "sign-in"
    REQUEST = "request"
    NONE = "none"


class SpotifyError(ApiCallError):
    """A Spotify failure that fails the source. The message never holds a token, the client secret, the query
    string or a song's name. The error code is the OAuth "error" of a failed answer (invalid_client) when it is a
    short plain word; else empty."""

    SERVICE = "Spotify"

    def __init__(
        self, message: str, status: int | None = None, endpoint: str = NO_ENDPOINT, error_code: str = NO_ERROR_CODE
    ) -> None:
        super().__init__(message, status, endpoint)
        self.error_code = error_code

    @classmethod
    def of_http_error(cls, error: httpx.HTTPError | httpx.InvalidURL, endpoint: str) -> "SpotifyError":
        if not isinstance(error, httpx.HTTPStatusError):
            return super().of_http_error(error, endpoint)
        status = error.response.status_code
        return cls(cls.call_failed_message(status, endpoint), status, endpoint, answer_error_code(error.response))

    def refusal(self) -> Refusal:
        """A 400 or 401 is a refused client (invalid_client), a refused sign-in (invalid_grant), or else a refused
        request."""
        if self.status not in REFUSED_STATUSES:
            return Refusal.NONE
        if self.error_code == INVALID_CLIENT_ERROR:
            return Refusal.CLIENT
        return Refusal.SIGN_IN if self.error_code == INVALID_GRANT_ERROR else Refusal.REQUEST

    def request_refused_message(self) -> str:
        """The status, the error code when there is one, and the endpoint of a refused request."""
        failure = (
            STATUS_AND_ERROR_CODE_FORMAT.format(status=self.status, error_code=self.error_code)
            if self.error_code
            else str(self.status)
        )
        return REQUEST_REFUSED_FORMAT.format(failure=failure, endpoint=self.endpoint)

    def refused_error(self) -> "SpotifyError":
        """The error that tells the Learner what to do about a refusal; any other failure is kept as it is."""
        refusal = self.refusal()
        if refusal is Refusal.NONE:
            return self
        if refusal is Refusal.REQUEST:
            return SpotifyError(self.request_refused_message(), self.status, self.endpoint, self.error_code)
        return SpotifySignInError.of_refusal(self)


class SpotifySignInError(SpotifyError):
    """Spotify refused the refresh token (the Learner approves the app again) or the client (the Learner checks
    the client id and secret)."""

    @classmethod
    def of_refusal(cls, error: SpotifyError) -> "SpotifySignInError":
        refused_format = CLIENT_REFUSED_FORMAT if error.refusal() is Refusal.CLIENT else SIGN_IN_REFUSED_FORMAT
        message = refused_format.format(status=error.status, endpoint=error.endpoint)
        return cls(message, error.status, error.endpoint, error.error_code)


class SpotifyTokenFileError(RuntimeError):
    """The token file cannot be used. The message names the setting and the approval helper, never the file's
    path or its content."""


@dataclass(frozen=True)
class SpotifyCredentials:
    """The Spotify app's client id and client secret."""

    client_id: str
    client_secret: str = field(repr=False)

    def authorization_header(self) -> dict[str, str]:
        return basic_header(self.client_id, self.client_secret)


class Skip(Enum):
    """Why a liked item gave no document."""

    NO_TRACK = "no track"
    NOT_A_SONG = "not a song"
    NO_NAME = "no name"


@dataclass(frozen=True)
class Song:
    """A song that was read, with the key that tells two items of the same song."""

    key: str
    document: Document


@dataclass
class ItemCounts:
    """The liked items read so far, by outcome; the songs are the documents read."""

    items: int = 0
    repeated_items: int = 0
    skips: Counter[Skip] = field(default_factory=Counter)


def plain_error_code(value: Any) -> str:
    """The value when it is a short plain word (letters, digits, underscore); else empty text."""
    return value if isinstance(value, str) and PLAIN_ERROR_CODE.fullmatch(value) else NO_ERROR_CODE


def answer_error_code(response: httpx.Response) -> str:
    """The plain "error" field of an answer's JSON object; empty text when the body is not one."""
    answer = json_object_or_none(response)
    return NO_ERROR_CODE if answer is None else plain_error_code(answer.get(ERROR_CODE_FIELD))


def spotify_credentials(settings: Settings) -> SpotifyCredentials:
    """The client id and secret; an empty one raises MissingSettingError naming its key."""
    return SpotifyCredentials(settings.require_spotify_client_id(), settings.require_spotify_client_secret())


def request_tokens(
    client: httpx.Client,
    credentials: SpotifyCredentials,
    form: dict[str, str],
    stats: ReadStats,
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    """The JSON object of a call to Spotify's token address, signed with the client's Basic header. Spotify may
    use a code or refresh token of a call whose answer is lost, so the call is tried again only after a 429; any
    other failure raises SpotifyError at once."""
    return call_json(
        lambda: client.post(TOKEN_URL, data=form, headers=credentials.authorization_header()),
        TOKEN_ENDPOINT,
        SpotifyError,
        rate_limit_retry_wait,
        stats,
        sleep,
    )


def write_token_file(token_file: Path, refresh_token: str) -> None:
    """Writes the refresh token through a temporary file in the same folder, so a failed write never leaves a
    half written token file. A missing folder is made private; the temporary file is always closed, and removed
    when the write fails."""
    _make_private_folder(token_file.parent)
    handle, temporary_name = tempfile.mkstemp(
        dir=token_file.parent, prefix=token_file.name, suffix=TEMPORARY_FILE_SUFFIX
    )
    try:
        try:
            temporary_file = os.fdopen(handle, "w", encoding=TOKEN_FILE_ENCODING)
        except BaseException:
            os.close(handle)
            raise
        with temporary_file:
            json.dump({REFRESH_TOKEN_FIELD: refresh_token}, temporary_file)
        os.replace(temporary_name, token_file)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _make_private_folder(folder: Path) -> None:
    """Makes a missing folder readable by the Learner only; the mode is set again since the umask can mask it.
    An existing folder is left as it is."""
    if folder.is_dir():
        return
    os.makedirs(folder, mode=PRIVATE_FOLDER_MODE, exist_ok=True)
    os.chmod(folder, PRIVATE_FOLDER_MODE)


def read_refresh_token(token_file: Path) -> str:
    try:
        content = json.loads(token_file.read_bytes().decode(TOKEN_FILE_ENCODING))
    except FileNotFoundError:
        # The causes are dropped, so neither the file's path nor its content reaches a log.
        raise SpotifyTokenFileError(TOKEN_FILE_MISSING_MESSAGE) from None
    except OSError:
        raise SpotifyTokenFileError(TOKEN_FILE_UNREADABLE_MESSAGE) from None
    except ValueError:  # not UTF-8 or not JSON
        raise SpotifyTokenFileError(TOKEN_FILE_INVALID_MESSAGE) from None
    refresh_token = content.get(REFRESH_TOKEN_FIELD) if isinstance(content, dict) else None
    if not isinstance(refresh_token, str) or not refresh_token:
        raise SpotifyTokenFileError(TOKEN_FILE_INVALID_MESSAGE)
    return refresh_token


class SpotifyResource(Resource):
    name = RESOURCE_NAME
    kind = ResourceKind.TEXT

    def __init__(
        self,
        credentials_factory: Callable[[], SpotifyCredentials],
        token_file_factory: Callable[[], Path],
        http_client_factory: Callable[[], httpx.Client] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Clock = time.monotonic,
    ) -> None:
        self._credentials_factory = credentials_factory
        self._token_file_factory = token_file_factory
        self._http_client_factory = http_client_factory or create_http_client
        self._sleep = sleep
        self._clock = clock
        self._stats = ReadStats()
        self._counts = ItemCounts()
        # The songs read so far by key, kept also when the read fails, so its summary counts them.
        self._songs: dict[str, Document] = {}

    def read_documents(self) -> list[Document]:
        self._counts = ItemCounts()
        self._songs = {}
        with timed_read(self._clock) as self._stats:
            return self._read_documents()

    def read_summary(self) -> str:
        """The counts hold every item read, also when the read failed."""
        counts = self._counts
        skip_counts = SUMMARY_SEPARATOR.join(f"{counts.skips[skip]} {skip.value}" for skip in Skip)
        return self._stats.summary(
            f"{counts.items} items",
            f"{len(self._songs)} songs",
            f"{counts.skips.total()} skipped items ({skip_counts})",
            f"{counts.repeated_items} repeated items",
        )

    def _read_documents(self) -> list[Document]:
        credentials = self._credentials_factory()
        token_file = self._token_file_factory()
        refresh_token = read_refresh_token(token_file)
        with self._http_client_factory() as client:
            access_token = self._refresh(client, credentials, token_file, refresh_token)
            return self._liked_songs(client, access_token)

    def _refresh(
        self, client: httpx.Client, credentials: SpotifyCredentials, token_file: Path, refresh_token: str
    ) -> str:
        """A new access token; a new refresh token in the answer replaces the one in the token file."""
        form = {"grant_type": REFRESH_TOKEN_GRANT, REFRESH_TOKEN_FIELD: refresh_token}
        try:
            tokens = request_tokens(client, credentials, form, self._stats, self._sleep)
        except SpotifyError as error:
            refused = error.refused_error()
            if refused is error:
                raise
            raise refused from None
        access_token = tokens.get(ACCESS_TOKEN_FIELD)
        if not isinstance(access_token, str) or not access_token:
            raise SpotifyError.of_call(NO_ACCESS_TOKEN_FAILURE, TOKEN_ENDPOINT)
        new_refresh_token = tokens.get(REFRESH_TOKEN_FIELD)
        if isinstance(new_refresh_token, str) and new_refresh_token and new_refresh_token != refresh_token:
            _save_refresh_token(token_file, new_refresh_token)
        return access_token

    def _liked_songs(self, client: httpx.Client, access_token: str) -> list[Document]:
        """Each song once, in Spotify's order (the newest like first)."""
        for item in self._liked_items(client, access_token):
            self._counts.items += 1
            result = _read_song(item)
            if isinstance(result, Skip):
                self._counts.skips[result] += 1
            elif result.key in self._songs:
                self._counts.repeated_items += 1
            else:
                self._songs[result.key] = result.document
        return list(self._songs.values())

    def _liked_items(self, client: httpx.Client, access_token: str) -> Iterator[Any]:
        """The items of every page: the first page, then each page's next link, until a page has no next link.
        A page whose items are missing or not a list, an empty page with a next link, and a next link that leaves
        the liked songs address, was already followed or whose offset does not move forward fail the source."""
        headers = bearer_header(access_token)
        followed: set[str] = set()
        page_url = FIRST_PAGE_URL
        start = FIRST_PAGE_OFFSET
        while True:
            followed.add(page_url)
            page = self._page(client, headers, page_url)
            items = page.get(ITEMS_FIELD)
            if not isinstance(items, list):
                raise SpotifyError.of_call(NO_ITEM_LIST_FAILURE, LIKED_SONGS_ENDPOINT)
            yield from items
            next_link = page.get(NEXT_FIELD)
            if not next_link:
                return
            if not items:
                raise SpotifyError.of_call(EMPTY_PAGE_WITH_NEXT_FAILURE, LIKED_SONGS_ENDPOINT)
            page_url, start = _next_page(next_link, followed, start)

    def _page(self, client: httpx.Client, headers: dict[str, str], page_url: str) -> dict[str, Any]:
        return call_json(
            lambda: client.get(page_url, headers=headers),
            LIKED_SONGS_ENDPOINT,
            SpotifyError,
            http_retry_wait,
            self._stats,
            self._sleep,
        )


def create_spotify_resource(settings: Settings) -> SpotifyResource:
    """The settings are read only when the resource reads, so a missing setting fails only then."""
    return SpotifyResource(
        credentials_factory=lambda: spotify_credentials(settings),
        token_file_factory=settings.require_spotify_token_file,
    )


def liked_songs_url(link: Any) -> str | None:
    """The link, normalized, when it is an https link on the liked songs address (no other host, port, user or
    path); else None."""
    if not isinstance(link, str):
        return None
    try:
        url = httpx.URL(link)
    except httpx.InvalidURL:
        return None
    address = LIKED_SONGS_ADDRESS
    on_address = (url.scheme, url.userinfo, url.host, url.port, url.path) == (
        address.scheme, NO_USERINFO, address.host, address.port, address.path
    )
    return str(url) if on_address else None


def _next_page(next_link: Any, followed: set[str], start: int) -> tuple[str, int]:
    """The next page's address and offset, which must be past start (the page's offset). The error holds the
    endpoint only, never the link."""
    page_url = liked_songs_url(next_link)
    if page_url is None:
        raise SpotifyError.of_call(OFF_ADDRESS_NEXT_FAILURE, LIKED_SONGS_ENDPOINT)
    if page_url in followed:
        raise SpotifyError.of_call(REPEATED_NEXT_FAILURE, LIKED_SONGS_ENDPOINT)
    next_start = page_offset(page_url)
    if next_start is None or next_start <= start:
        raise SpotifyError.of_call(BACKWARD_NEXT_FAILURE, LIKED_SONGS_ENDPOINT)
    return page_url, next_start


def page_offset(page_url: str) -> int | None:
    """The link's one offset when it is a whole number written in digits only; else None."""
    offsets = httpx.URL(page_url).params.get_list(OFFSET_PARAM)
    if len(offsets) != 1:
        return None
    offset = offsets[0]
    return int(offset) if offset.isascii() and offset.isdigit() else None


def _save_refresh_token(token_file: Path, refresh_token: str) -> None:
    try:
        write_token_file(token_file, refresh_token)
    except OSError:
        # The cause is dropped, so the file's path does not reach a log.
        raise SpotifyTokenFileError(TOKEN_FILE_UNWRITABLE_MESSAGE) from None


def _read_song(item: Any) -> Song | Skip:
    track = item.get("track") if isinstance(item, dict) else None
    if not isinstance(track, dict):
        return Skip.NO_TRACK
    if track.get("type") != SONG_TRACK_TYPE:
        return Skip.NOT_A_SONG
    name = clean_text(track.get("name"))
    if not name:
        return Skip.NO_NAME
    document = build_document(track, name, clean_text(item.get("added_at")))
    # A local file has no track id; its uri tells it apart.
    key = clean_text(track.get("id")) or clean_text(track.get("uri")) or document.text
    return Song(key, document)


def build_document(track: dict[str, Any], name: str, liked_at: str) -> Document:
    musicians = join_names(unique_names(json_entries(track.get("artists"))))
    album = track.get("album")
    album_name = clean_text(album.get("name")) if isinstance(album, dict) else ""
    lines = labelled_lines(
        (SONG_LABEL, name),
        (MUSICIAN_LABEL, musicians),
        (ALBUM_LABEL, album_name),
        (LINK_LABEL, _song_link(track)),
    )
    metadata = {
        METADATA_NAME: name,
        METADATA_PATH: NO_PATH,
        METADATA_MUSICIAN: musicians,
        METADATA_ALBUM: album_name,
        METADATA_TYPE: SONG_DOCUMENT_TYPE,
        METADATA_TIMESTAMP: liked_at,
    }
    return Document(LINE_SEPARATOR.join(lines), metadata)


def _song_link(track: dict[str, Any]) -> str:
    links = track.get("external_urls")
    link = clean_text(links.get("spotify")) if isinstance(links, dict) else ""
    return link if link.startswith(SONG_LINK_PREFIX) else ""
