import httpx
import pytest

from settings import MissingSettingError, Settings
from web_finders import FoundSong, OpenverseImageFinder, SpotifySongFinder

SETTINGS = Settings(spotify_client_id="id", spotify_client_secret="secret")
SUN_URL = "https://open.spotify.com/track/6dGnYIeXmHdcikdzNNDMm2"


def track(name, artist, url=SUN_URL):
    return {"name": name, "artists": [{"name": artist}], "external_urls": {"spotify": url}}


def spotify_handler(tracks, calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "accounts.spotify.com":
            return httpx.Response(200, json={"access_token": "token-1", "expires_in": 3600})
        return httpx.Response(200, json={"tracks": {"items": tracks}})

    return handler


def song_finder(tracks, calls, settings=SETTINGS, clock=lambda: 0.0):
    transport = httpx.MockTransport(spotify_handler(tracks, calls))
    return SpotifySongFinder(
        settings, http_client_factory=lambda: httpx.Client(transport=transport), clock=clock, sleep=lambda _: None
    )


def test_the_song_gemini_named_is_found_with_spotifys_own_title_artist_and_link():
    # L1
    calls = []
    finder = song_finder([track("Here Comes The Sun - Remastered 2009", "The Beatles")], calls)

    found = finder.find_song("Here Comes the Sun", "The Beatles")

    assert found == FoundSong("Here Comes The Sun - Remastered 2009", "The Beatles", SUN_URL)
    search = calls[-1]
    assert search.url.params["type"] == "track"
    assert search.url.params["q"] == 'track:"Here Comes the Sun" artist:"The Beatles"'
    assert search.headers["authorization"] == "Bearer token-1"


def test_a_result_for_another_song_or_artist_is_not_returned():
    # L2
    finder = song_finder([track("Sunrise", "The Beatles"), track("Here Comes the Sun", "Cover Band X")], [])

    assert finder.find_song("Here Comes the Sun", "The Beatles") is None


def test_accents_and_case_do_not_matter_when_the_song_is_matched():
    # L2
    finder = song_finder([track("Halo", "Beyoncé")], [])

    assert finder.find_song("HALO", "beyonce") == FoundSong("Halo", "Beyoncé", SUN_URL)


def test_a_result_without_a_spotify_web_link_is_not_returned():
    # L2
    finder = song_finder([track("Halo", "Beyoncé", url="javascript:alert(1)")], [])

    assert finder.find_song("Halo", "Beyoncé") is None


def test_the_access_token_is_asked_once_while_it_lasts():
    # L3
    calls = []
    finder = song_finder([track("Halo", "Beyoncé")], calls)

    finder.find_song("Halo", "Beyoncé")
    finder.find_song("Halo", "Beyoncé")

    assert [call.url.host for call in calls] == ["accounts.spotify.com", "api.spotify.com", "api.spotify.com"]


def test_a_missing_spotify_client_is_named_by_its_key():
    # L4
    finder = song_finder([], [], settings=Settings())

    with pytest.raises(MissingSettingError, match="SPOTIFY_CLIENT_ID"):
        finder.find_song("Halo", "Beyoncé")


def image_finder(body, calls, status=200):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json=body)

    transport = httpx.MockTransport(handler)
    return OpenverseImageFinder(http_client_factory=lambda: httpx.Client(transport=transport), sleep=lambda _: None)


def test_the_first_https_image_of_the_phrase_is_returned():
    # L5
    calls = []
    results = [{"url": "http://example.com/a.jpg"}, {"url": "https://example.com/b.jpg"}, {"url": "https://example.com/c.jpg"}]

    assert image_finder({"results": results}, calls).find_image("umbrella in the rain") == "https://example.com/b.jpg"
    assert calls[0].url.params["q"] == "umbrella in the rain"
    assert calls[0].url.params["mature"] == "false"


@pytest.mark.parametrize("body", [{"results": []}, {}, {"results": [{"title": "no url"}, {"url": "ftp://x/y.jpg"}]}])
def test_no_usable_image_gives_none(body):
    # L6
    assert image_finder(body, []).find_image("anything") is None
