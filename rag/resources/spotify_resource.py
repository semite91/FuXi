"""Spotify resource: the songs of the playlist the Learner chose, as one text document per song."""

import re
import time
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
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
    ResourceSkipped,
)
from resources.http_retry import (
    Clock,
    ReadStats,
    basic_header,
    bearer_header,
    call_with_retry,
    create_http_client,
    http_retry_wait,
    rate_limit_retry_wait,
    timed_read,
)
from settings import SPOTIFY_CLIENT_ID_KEY, SPOTIFY_CLIENT_SECRET_KEY, Settings
from settings_store import SettingsStoreError, SpotifyRows, read_spotify_rows, save_spotify_refresh_token

RESOURCE_NAME = "spotify"

TOKEN_URL = "https://accounts.spotify.com/api/token"
TOKEN_ENDPOINT = httpx.URL(TOKEN_URL).path
# The items of one playlist; a next link that leaves this address is not followed.
ITEMS_URL_FORMAT = "https://api.spotify.com/v1/playlists/{playlist_id}/items"
PAGE_SIZE = 50
OFFSET_PARAM = "offset"
LIMIT_PARAM = "limit"
# The first call asks for no offset, which Spotify reads as 0.
FIRST_PAGE_OFFSET = 0
NO_USERINFO = b""
REFRESH_TOKEN_GRANT = "refresh_token"
REFRESH_TOKEN_FIELD = "refresh_token"
ACCESS_TOKEN_FIELD = "access_token"
ITEMS_FIELD = "items"
NEXT_FIELD = "next"
# Since February 2026 an entry holds its song under "item"; "track" is the older name.
SONG_FIELDS = ("item", "track")
ERROR_CODE_FIELD = "error"
INVALID_CLIENT_ERROR = "invalid_client"
INVALID_GRANT_ERROR = "invalid_grant"
# An error code is kept only when it is a short plain word, so no other input reaches a message.
PLAIN_ERROR_CODE = re.compile(r"[A-Za-z0-9_]{1,64}")
NO_ERROR_CODE = ""
# Spotify answers a token request it refuses with a 400 or a 401; the error code tells what it refused.
REFUSED_STATUSES = frozenset({400, 401})
UNAUTHORIZED_STATUS = 401
# A playlist answering with one of these is not one the connected account can read.
UNREADABLE_STATUSES = frozenset({403, 404})

NOT_CONNECTED = "not connected"
NO_PLAYLIST_CHOSEN = "no playlist chosen"
TOKEN_REJECTED_MESSAGE = "Spotify token rejected: connect Spotify again on the Settings page"
PLAYLIST_NOT_FOUND_MESSAGE = "Spotify playlist not found: choose the playlist again on the Settings page"
CLIENT_REFUSED_FORMAT = (
    f"Spotify refused the client ({{failure}} on {{endpoint}}): check {SPOTIFY_CLIENT_ID_KEY} and {SPOTIFY_CLIENT_SECRET_KEY}"
)
TOKEN_REFUSED_FORMAT = "Spotify refused the token request ({failure} on {endpoint})"
CALL_FAILED_FORMAT = "Spotify call failed: {failure} on {endpoint}"
STATUS_AND_ERROR_FORMAT = "{status} {error_code}"
NOT_A_JSON_OBJECT_FAILURE = "an answer that is not a JSON object"
NO_ACCESS_TOKEN_FAILURE = "an answer without an access token"
NO_ITEM_LIST_FAILURE = "a page without an item list"
EMPTY_PAGE_WITH_NEXT_FAILURE = "an empty page with a next link"
OFF_ADDRESS_NEXT_FAILURE = "a next link off the playlist address"
REPEATED_NEXT_FAILURE = "a next link already followed"
BACKWARD_NEXT_FAILURE = "a next link that does not move forward"

SONG_TRACK_TYPE = "track"
# Only a web link to the song is kept; any other address is left out.
SONG_LINK_PREFIX = "https://open.spotify.com/"
SONG_LABEL = "Song"
MUSICIAN_LABEL = "Musician"
ALBUM_LABEL = "Album"
LINK_LABEL = "Link"
LINE_FORMAT = "{label}: {value}"
LINE_SEPARATOR = "\n"
NAME_SEPARATOR = ", "
SUMMARY_SEPARATOR = ", "


class SpotifyError(RuntimeError):
    """A Spotify failure that fails the source. The message holds the status (or the kind of failure) and the
    endpoint's path only: never the query string, an answer's body, a token, the client secret or a song's name."""

    def __init__(self, message: str, status: int | None = None, endpoint: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.endpoint = endpoint

    @classmethod
    def of_call(cls, failure: int | str, endpoint: str) -> "SpotifyError":
        status = failure if isinstance(failure, int) else None
        return cls(CALL_FAILED_FORMAT.format(failure=failure, endpoint=endpoint), status, endpoint)

    @classmethod
    def of_http_error(cls, error: httpx.HTTPError | httpx.InvalidURL, endpoint: str) -> "SpotifyError":
        """The status of a failed answer, else the kind of the httpx error; its cause is dropped, since it can hold
        the full address and the request with its token."""
        if isinstance(error, httpx.HTTPStatusError):
            return cls.of_call(error.response.status_code, endpoint)
        return cls.of_call(type(error).__name__, endpoint)


class SpotifyTokenRejected(SpotifyError):
    """Spotify no longer accepts the saved refresh token, or answered 401: the Learner connects Spotify again."""


class SpotifySignInError(SpotifyError):
    """Spotify's token address refused the client or the request for another reason than an ended token."""


class SpotifyPlaylistNotFound(SpotifyError):
    """The chosen playlist is not one the connected account can read."""


@dataclass(frozen=True)
class SpotifyClient:
    """The Spotify app's client id and client secret, from .env."""

    client_id: str
    client_secret: str = field(repr=False)


@dataclass(frozen=True)
class SpotifyConnection:
    """What one read needs: the chosen playlist and how to get an access token."""

    playlist_id: str
    refresh_token: str = field(repr=False)
    client: SpotifyClient


class Skip(Enum):
    """Why a playlist item gave no document."""

    NO_TRACK = "no track"
    NOT_A_SONG = "not a song"
    LOCAL_FILE = "local file"
    NO_NAME = "no name"


@dataclass(frozen=True)
class Song:
    """A song that was read, with the key that tells two items of the same song."""

    key: str
    document: Document


@dataclass
class ItemCounts:
    """The playlist items read so far, by outcome; the songs are the documents read."""

    items: int = 0
    repeated_items: int = 0
    skips: Counter[Skip] = field(default_factory=Counter)


class SpotifyResource(Resource):
    name = RESOURCE_NAME
    kind = ResourceKind.TEXT

    def __init__(
        self,
        connection_factory: Callable[[], SpotifyConnection],
        http_client_factory: Callable[[], httpx.Client] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Clock = time.monotonic,
        save_refresh_token: Callable[[str], None] = lambda _token: None,
    ) -> None:
        self._connection_factory = connection_factory
        self._save_refresh_token = save_refresh_token
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
        connection = self._connection_factory()
        with self._http_client_factory() as client:
            access_token = self._access_token(client, connection)
            return self._playlist_songs(client, connection.playlist_id, access_token)

    def _access_token(self, client: httpx.Client, connection: SpotifyConnection) -> str:
        """A new access token from the refresh token; it stays in memory. A different refresh token in the answer
        replaces the saved one, because Spotify may end the old one; a failed save does not fail the read.

        Spotify may have used the refresh token of a call whose answer is lost, so the call is tried again only
        after a 429; any other failure raises at once."""
        form = {"grant_type": REFRESH_TOKEN_GRANT, REFRESH_TOKEN_FIELD: connection.refresh_token}
        headers = basic_header(connection.client.client_id, connection.client.client_secret)
        try:
            response = call_with_retry(
                lambda: client.post(TOKEN_URL, data=form, headers=headers).raise_for_status(),
                rate_limit_retry_wait,
                self._stats,
                self._sleep,
            )
        except httpx.HTTPStatusError as error:
            raise _token_refusal(error.response) from None
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            raise SpotifyError.of_http_error(error, TOKEN_ENDPOINT) from None
        answer = _json_object(response, TOKEN_ENDPOINT)
        access_token = answer.get(ACCESS_TOKEN_FIELD)
        if not isinstance(access_token, str) or not access_token:
            raise SpotifyError.of_call(NO_ACCESS_TOKEN_FAILURE, TOKEN_ENDPOINT)
        self._keep_rotated_token(answer, connection.refresh_token)
        return access_token

    def _keep_rotated_token(self, answer: dict[str, Any], used_token: str) -> None:
        new_token = answer.get(REFRESH_TOKEN_FIELD)
        if isinstance(new_token, str) and new_token and new_token != used_token:
            try:
                self._save_refresh_token(new_token)
            except SettingsStoreError:
                pass  # the used token still works until Spotify ends it; the next refresh returns the new one again

    def _playlist_songs(self, client: httpx.Client, playlist_id: str, access_token: str) -> list[Document]:
        """Each song once, in the playlist's order."""
        for item in self._playlist_items(client, playlist_id, access_token):
            self._counts.items += 1
            result = _read_song(item)
            if isinstance(result, Skip):
                self._counts.skips[result] += 1
            elif result.key in self._songs:
                self._counts.repeated_items += 1
            else:
                self._songs[result.key] = result.document
        return list(self._songs.values())

    def _playlist_items(self, client: httpx.Client, playlist_id: str, access_token: str) -> Iterator[Any]:
        """The items of every page: the first page, then each page's next link, until a page has no next link.
        A page whose items are missing or not a list, an empty page with a next link, and a next link that leaves
        the playlist address, was already followed or does not move forward fail the source."""
        address = httpx.URL(ITEMS_URL_FORMAT.format(playlist_id=playlist_id))
        headers = bearer_header(access_token)
        followed: set[str] = set()
        page_url = str(address.copy_with(params={LIMIT_PARAM: PAGE_SIZE}))
        start = FIRST_PAGE_OFFSET
        while True:
            followed.add(page_url)
            page = self._page(client, headers, page_url, address.path)
            items = page.get(ITEMS_FIELD)
            if not isinstance(items, list):
                raise SpotifyError.of_call(NO_ITEM_LIST_FAILURE, address.path)
            yield from items
            next_link = page.get(NEXT_FIELD)
            if not next_link:
                return
            if not items:
                raise SpotifyError.of_call(EMPTY_PAGE_WITH_NEXT_FAILURE, address.path)
            page_url, start = _next_page(next_link, address, followed, start)

    def _page(self, client: httpx.Client, headers: dict[str, str], page_url: str, endpoint: str) -> dict[str, Any]:
        try:
            response = call_with_retry(
                lambda: client.get(page_url, headers=headers).raise_for_status(),
                http_retry_wait,
                self._stats,
                self._sleep,
            )
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if status == UNAUTHORIZED_STATUS:
                raise SpotifyTokenRejected(TOKEN_REJECTED_MESSAGE, status, endpoint) from None
            if status in UNREADABLE_STATUSES:
                raise SpotifyPlaylistNotFound(PLAYLIST_NOT_FOUND_MESSAGE, status, endpoint) from None
            raise SpotifyError.of_http_error(error, endpoint) from None
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            raise SpotifyError.of_http_error(error, endpoint) from None
        return _json_object(response, endpoint)


def create_spotify_resource(
    settings: Settings,
    read_rows: Callable[[Settings], SpotifyRows] = read_spotify_rows,
    http_client_factory: Callable[[], httpx.Client] | None = None,
    save_token: Callable[[Settings, str], None] = save_spotify_refresh_token,
) -> SpotifyResource:
    """The Settings rows are read at each read, so a new sign-in or playlist needs no restart.

    Not connected or no playlist skips Spotify; a missing client key or an unreadable table fails it.
    """

    def connection_factory() -> SpotifyConnection:
        rows = read_rows(settings)
        if not rows.refresh_token:
            raise ResourceSkipped(NOT_CONNECTED)
        if not rows.playlist_id:
            raise ResourceSkipped(NO_PLAYLIST_CHOSEN)
        client_id, client_secret = settings.require_spotify_client()
        return SpotifyConnection(rows.playlist_id, rows.refresh_token, SpotifyClient(client_id, client_secret))

    return SpotifyResource(
        connection_factory=connection_factory,
        http_client_factory=http_client_factory,
        save_refresh_token=lambda token: save_token(settings, token),
    )


def _json_object(response: httpx.Response, endpoint: str) -> dict[str, Any]:
    """The answer's JSON object; anything else raises without the answer's body."""
    try:
        answer = response.json()
    except ValueError:
        answer = None
    if not isinstance(answer, dict):
        raise SpotifyError.of_call(NOT_A_JSON_OBJECT_FAILURE, endpoint)
    return answer


def _token_refusal(response: httpx.Response) -> SpotifyError:
    """What the Learner does about a failed token request: connect again (an ended or withdrawn refresh token),
    check the client keys (a refused client), or nothing known (another failure, named by its status)."""
    status = response.status_code
    error_code = _error_code(response)
    failure = STATUS_AND_ERROR_FORMAT.format(status=status, error_code=error_code) if error_code else str(status)
    if status not in REFUSED_STATUSES:
        return SpotifyError.of_call(status, TOKEN_ENDPOINT)
    if error_code == INVALID_GRANT_ERROR:
        return SpotifyTokenRejected(TOKEN_REJECTED_MESSAGE, status, TOKEN_ENDPOINT)
    refused_format = CLIENT_REFUSED_FORMAT if error_code == INVALID_CLIENT_ERROR else TOKEN_REFUSED_FORMAT
    return SpotifySignInError(refused_format.format(failure=failure, endpoint=TOKEN_ENDPOINT), status, TOKEN_ENDPOINT)


def _error_code(response: httpx.Response) -> str:
    """The plain "error" field of an answer's JSON object; empty text when the body is not one."""
    try:
        answer = response.json()
    except ValueError:
        return NO_ERROR_CODE
    code = answer.get(ERROR_CODE_FIELD) if isinstance(answer, dict) else None
    return code if isinstance(code, str) and PLAIN_ERROR_CODE.fullmatch(code) else NO_ERROR_CODE


def _playlist_url(link: Any, address: httpx.URL) -> str | None:
    """The link, normalized, when it is an https link on the playlist's items address (no other host, port, user or
    path); else None."""
    if not isinstance(link, str):
        return None
    try:
        url = httpx.URL(link)
    except httpx.InvalidURL:
        return None
    on_address = (url.scheme, url.userinfo, url.host, url.port, url.path) == (
        address.scheme, NO_USERINFO, address.host, address.port, address.path
    )
    return str(url) if on_address else None


def _next_page(next_link: Any, address: httpx.URL, followed: set[str], start: int) -> tuple[str, int]:
    """The next page's address and offset, which must be past start (the page's offset). The error holds the
    endpoint only, never the link."""
    page_url = _playlist_url(next_link, address)
    if page_url is None:
        raise SpotifyError.of_call(OFF_ADDRESS_NEXT_FAILURE, address.path)
    if page_url in followed:
        raise SpotifyError.of_call(REPEATED_NEXT_FAILURE, address.path)
    next_start = _page_offset(page_url)
    if next_start is None or next_start <= start:
        raise SpotifyError.of_call(BACKWARD_NEXT_FAILURE, address.path)
    return page_url, next_start


def _page_offset(page_url: str) -> int | None:
    """The link's one offset when it is a whole number written in digits only; else None."""
    offsets = httpx.URL(page_url).params.get_list(OFFSET_PARAM)
    if len(offsets) != 1:
        return None
    offset = offsets[0]
    return int(offset) if offset.isascii() and offset.isdigit() else None


def _read_song(entry: Any) -> Song | Skip:
    # The first of item and track that holds an object; a null or odd item does not hide a usable track.
    track = next(
        (entry[name] for name in SONG_FIELDS if isinstance(entry, dict) and isinstance(entry.get(name), dict)), None
    )
    if track is None:
        return Skip.NO_TRACK
    if track.get("type") != SONG_TRACK_TYPE:
        return Skip.NOT_A_SONG
    if track.get("is_local") is True:
        return Skip.LOCAL_FILE
    name = _clean_text(track.get("name"))
    if not name:
        return Skip.NO_NAME
    document = _build_document(track, name, _clean_text(entry.get("added_at")))
    key = _clean_text(track.get("id")) or _clean_text(track.get("uri")) or document.text
    return Song(key, document)


def _build_document(track: dict[str, Any], name: str, added_at: str) -> Document:
    artists = track.get("artists")
    names = [_clean_text(artist.get("name")) for artist in artists if isinstance(artist, dict)] if isinstance(artists, list) else []
    musicians = NAME_SEPARATOR.join(dict.fromkeys(name_ for name_ in names if name_))
    album = track.get("album")
    album_name = _clean_text(album.get("name")) if isinstance(album, dict) else ""
    labelled = ((SONG_LABEL, name), (MUSICIAN_LABEL, musicians), (ALBUM_LABEL, album_name), (LINK_LABEL, _song_link(track)))
    lines = [LINE_FORMAT.format(label=label, value=value) for label, value in labelled if value]
    metadata = {
        METADATA_NAME: name,
        METADATA_PATH: NO_PATH,
        METADATA_MUSICIAN: musicians,
        METADATA_ALBUM: album_name,
        METADATA_TYPE: SONG_DOCUMENT_TYPE,
        METADATA_TIMESTAMP: added_at,
    }
    return Document(LINE_SEPARATOR.join(lines), metadata)


def _song_link(track: dict[str, Any]) -> str:
    links = track.get("external_urls")
    link = _clean_text(links.get("spotify")) if isinstance(links, dict) else ""
    return link if link.startswith(SONG_LINK_PREFIX) else ""


def _clean_text(value: Any) -> str:
    """A text value without its outer spaces; anything else is empty text."""
    return value.strip() if isinstance(value, str) else ""
