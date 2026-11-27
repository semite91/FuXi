"""Finders that turn what Gemini suggests into a real thing: a Spotify song and an openly licensed web image.

Gemini only names a song or describes an image; these finders look it up, so every link is one that exists."""

import threading
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from resources.http_retry import (
    Clock,
    ReadStats,
    basic_header,
    bearer_header,
    call_with_retry,
    create_http_client,
    http_retry_wait,
)
from settings import Settings

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SEARCH_URL = "https://api.spotify.com/v1/search"
SPOTIFY_SEARCH_LIMIT = 10
SPOTIFY_QUERY_FORMAT = 'track:"{title}" artist:"{artist}"'
CLIENT_CREDENTIALS_GRANT = "client_credentials"
SONG_LINK_PREFIX = "https://open.spotify.com/"
# The token is asked again this many seconds before it ends.
TOKEN_EXPIRY_MARGIN_SECONDS = 60.0

OPENVERSE_SEARCH_URL = "https://api.openverse.org/v1/images/"
OPENVERSE_PAGE_SIZE = 5
OPENVERSE_USER_AGENT = "fuxi-vocabulary-app"
HTTPS_SCHEME = "https"

HttpClientFactory = Callable[[], httpx.Client]


@dataclass(frozen=True)
class FoundSong:
    title: str
    artist: str
    url: str


def _plain(text: str) -> str:
    """Lower case without accents or punctuation, so "Beyoncé" and "beyonce" are the same."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(character for character in decomposed if character.isalnum() or character == " ").strip()


class SpotifySongFinder:
    """Searches Spotify for the song Gemini named; a song that Spotify does not have is not returned."""

    def __init__(
        self,
        settings: Settings,
        http_client_factory: HttpClientFactory = create_http_client,
        clock: Clock = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._http_client_factory = http_client_factory
        self._clock = clock
        self._sleep = sleep
        self._token: str | None = None
        self._token_ends_at = 0.0
        self._lock = threading.Lock()

    def find_song(self, title: str, artist: str) -> FoundSong | None:
        query = SPOTIFY_QUERY_FORMAT.format(title=title.replace('"', ""), artist=artist.replace('"', ""))
        with self._http_client_factory() as client:
            headers = bearer_header(self._access_token(client))
            answer = self._get(client, SPOTIFY_SEARCH_URL, {"q": query, "type": "track", "limit": SPOTIFY_SEARCH_LIMIT}, headers)
        for item in _items(answer):
            found = _song(item)
            if found is not None and _plain(title) in _plain(found.title) and _plain(artist) in _plain(found.artist):
                return found
        return None

    def _access_token(self, client: httpx.Client) -> str:
        with self._lock:
            if self._token is None or self._clock() >= self._token_ends_at:
                client_id, client_secret = self._settings.require_spotify_client()
                headers = basic_header(client_id, client_secret)
                form = {"grant_type": CLIENT_CREDENTIALS_GRANT}
                response = self._call(lambda: client.post(SPOTIFY_TOKEN_URL, data=form, headers=headers).raise_for_status())
                body = response.json()
                self._token = body["access_token"]
                self._token_ends_at = self._clock() + float(body.get("expires_in", 0)) - TOKEN_EXPIRY_MARGIN_SECONDS
            return self._token

    def _get(self, client: httpx.Client, url: str, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        answer = self._call(lambda: client.get(url, params=params, headers=headers).raise_for_status()).json()
        return answer if isinstance(answer, dict) else {}

    def _call(self, call: Callable[[], httpx.Response]) -> httpx.Response:
        return call_with_retry(call, http_retry_wait, ReadStats(), self._sleep)


def _items(answer: dict[str, Any]) -> list[Any]:
    tracks = answer.get("tracks")
    items = tracks.get("items") if isinstance(tracks, dict) else None
    return items if isinstance(items, list) else []


def _song(item: Any) -> FoundSong | None:
    if not isinstance(item, dict):
        return None
    artists = item.get("artists")
    links = item.get("external_urls")
    name = item.get("name")
    url = links.get("spotify") if isinstance(links, dict) else None
    artist = ", ".join(a["name"] for a in artists if isinstance(a, dict) and isinstance(a.get("name"), str)) if isinstance(artists, list) else ""
    if not (isinstance(name, str) and name and artist and isinstance(url, str) and url.startswith(SONG_LINK_PREFIX)):
        return None
    return FoundSong(name, artist, url)


class OpenverseImageFinder:
    """Searches Openverse, which lists openly licensed images, for the first image that fits a short English phrase."""

    def __init__(
        self,
        http_client_factory: HttpClientFactory = create_http_client,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http_client_factory = http_client_factory
        self._sleep = sleep

    def find_image(self, query: str) -> str | None:
        params = {"q": query, "page_size": OPENVERSE_PAGE_SIZE, "mature": "false", "license_type": "commercial"}
        headers = {"User-Agent": OPENVERSE_USER_AGENT}
        with self._http_client_factory() as client:
            response = call_with_retry(
                lambda: client.get(OPENVERSE_SEARCH_URL, params=params, headers=headers).raise_for_status(),
                http_retry_wait,
                ReadStats(),
                self._sleep,
            )
        results = response.json().get("results")
        for result in results if isinstance(results, list) else []:
            url = result.get("url") if isinstance(result, dict) else None
            if isinstance(url, str) and urlparse(url).scheme == HTTPS_SCHEME and urlparse(url).netloc:
                return url
        return None
