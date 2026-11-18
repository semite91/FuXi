import base64
import copy
import io
import threading
import warnings

import httpx
import pytest
from PIL import Image, JpegImagePlugin

from base import Resource, ResourceKind, ResourceSkipped
from fakes import FAKE_ACCESS_TOKEN, FakeDriveApi, FakeTokens, load_fixture
from resources.google_drive_resource import (
    DOWNLOAD_WORKERS,
    DRIVE_READONLY_SCOPE,
    MAX_PICTURE_SIDE,
    DriveConnection,
    DriveFolderNotFound,
    DriveSignInError,
    DriveTokenRejected,
    GoogleClient,
    GoogleDriveResource,
    RefreshTokenSource,
    TOKEN_REQUEST_FAILED,
    create_google_drive_resource,
)
from resources.http_retry import MAX_ATTEMPTS, NETWORK_RETRY_SECONDS, ReadStats
from resources.notion_resource import NotionResource
from settings import MissingSettingError, Settings
from settings_store import GoogleDriveRows, SettingsStoreError

PARIS_RAIN = "1dRvImgParisRain0000000000000001"
UMBRELLA = "1dRvImgUmbrella00000000000000002"
CAFE = "1dRvImgCafe000000000000000000003"
SKETCH = "1dRvImgSketch00000000000000000004"
FOLDER_PHOTOS = "1dRvFolderPhotos00000000000000a"
FOLDER_PARIS = "1dRvFolderParis000000000000000b"
FOLDER_NIGHT = "1dRvFolderNight000000000000000c"
LIST_PHOTOS = f"files.list:{FOLDER_PHOTOS}"
GET_PHOTOS = f"files.get:{FOLDER_PHOTOS}"
IMAGE_NAMES = ["cafe.heic", "paris_rain.jpg", "sketch.gif", "umbrella.png"]
SMALL_SIZE = (64, 48)
CLIENT_ID = "google-client-id-of-a-test"
CLIENT_SECRET = "google-client-secret-of-a-test"
REFRESH_TOKEN = "1//refresh-token-of-a-test"
GOOGLE_CLIENT = GoogleClient(CLIENT_ID, CLIENT_SECRET)
TOKEN_REJECTED = "Google Drive token rejected: connect Google Drive again on the Settings page"
FOLDER_NOT_FOUND = "Google Drive folder not found: choose the folder again on the Settings page"
FOLDER_MIME = "application/vnd.google-apps.folder"
TOKEN_LIFETIME = 3599


def recorded():
    return copy.deepcopy(load_fixture("drive_recorded.json"))


def picture_bytes(size=SMALL_SIZE, mode="RGB", image_format="PNG", color=(200, 30, 30)) -> bytes:
    output = io.BytesIO()
    Image.new(mode, size, color).save(output, format=image_format)
    return output.getvalue()


def pictures(**overrides: bytes) -> dict[str, bytes]:
    return {PARIS_RAIN: picture_bytes(image_format="JPEG"), UMBRELLA: picture_bytes(),
            CAFE: picture_bytes(image_format="JPEG"), SKETCH: picture_bytes(image_format="GIF"), **overrides}


def make_api(data=None, picture_map=None, failures=None) -> FakeDriveApi:
    return FakeDriveApi(data or recorded(), picture_map or pictures(), failures)


def make_resource(api, sleeps=None, tokens=None, clock=None, folder_id=FOLDER_PHOTOS):
    """The resource with the real refresh token source against the fake token endpoint, unless tokens are given."""
    sleeps = [] if sleeps is None else sleeps
    return GoogleDriveResource(
        connection_factory=lambda: DriveConnection(folder_id, REFRESH_TOKEN, GOOGLE_CLIENT),
        http_client_factory=api.client,
        sleep=sleeps.append,
        **({"token_source_factory": lambda client, connection: tokens} if tokens is not None else {}),
        **({"clock": clock} if clock is not None else {}),
    )


def drive_routes(api):
    return [route for route in api.routes if route != "token"]


def by_name(documents):
    return {document.metadata["name"]: document for document in documents}


def decoded(document) -> Image.Image:
    picture = Image.open(io.BytesIO(base64.b64decode(document.text, validate=True)))
    picture.load()
    return picture


def answer(status: int, headers=None) -> httpx.Response:
    return httpx.Response(status, headers=headers or {}, json={"error": {"code": status}})


def recorded_answer(name: str, headers=None) -> httpx.Response:
    body = recorded()[name]
    return httpx.Response(body["error"]["code"], headers=headers or {}, json=body)


def invalid_grant() -> httpx.Response:
    return httpx.Response(400, json=recorded()["invalid_grant"])


WAIT_SECONDS = 5.0


# Phase 6c D1, D2: a fresh access token from the refresh token, kept in memory only.
def test_build_gets_an_access_token_from_the_refresh_token_and_uses_it_for_every_drive_call():
    # Phase 6c D1
    api = make_api()

    make_resource(api).read_documents()

    assert api.routes[0] == "token"
    token_request = api.requests[0]
    assert token_request.method == "POST"
    assert str(token_request.url) == "https://oauth2.googleapis.com/token"
    assert dict(httpx.QueryParams(token_request.content.decode())) == {
        "grant_type": "refresh_token", "refresh_token": REFRESH_TOKEN,
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
    }
    assert api.routes.count("token") == 1
    drive_requests = [request for request, route in zip(api.requests, api.routes) if route != "token"]
    assert {request.headers["Authorization"] for request in drive_requests} == {f"Bearer {FAKE_ACCESS_TOKEN}"}


def test_access_token_is_refreshed_again_only_when_it_is_about_to_expire():
    # Phase 6c D1 (a long build outlives the 1-hour access token)
    api = make_api()
    now = [1000.0]
    with api.client() as client:
        tokens = RefreshTokenSource(client, REFRESH_TOKEN, GOOGLE_CLIENT, ReadStats(), lambda _: None, lambda: now[0])

        tokens.access_token()
        now[0] += TOKEN_LIFETIME - 120
        tokens.access_token()
        assert api.routes.count("token") == 1
        now[0] += 100
        tokens.access_token()

    assert api.routes.count("token") == 2


@pytest.mark.parametrize("failure", [invalid_grant(), httpx.Response(401, json={"error": "invalid_grant"})])
def test_refused_refresh_token_fails_with_connect_again(failure):
    # Phase 6c D6 (the 7-day end in Testing, or a revoked access)
    api = make_api(failures={"token": [failure]})

    with pytest.raises(DriveTokenRejected, match=TOKEN_REJECTED) as raised:
        make_resource(api).read_documents()

    assert REFRESH_TOKEN not in str(raised.value)
    assert drive_routes(api) == []


def test_other_token_endpoint_error_fails_with_its_status_and_without_the_secret():
    # Phase 6c D6 (a wrong client ID or secret is not a token the Learner can fix by connecting again)
    api = make_api(failures={"token": [httpx.Response(401, json={"error": "invalid_client"})]})

    with pytest.raises(DriveSignInError, match="status 401") as raised:
        make_resource(api).read_documents()

    assert CLIENT_SECRET not in str(raised.value) and REFRESH_TOKEN not in str(raised.value)
    assert raised.value.__cause__ is None
    assert api.routes.count("token") == 1


def test_unreachable_token_endpoint_is_tried_with_the_shared_rules_once():
    # Phase 6c D1 (the Drive call that needs the token does not try the token request again on its own)
    sleeps: list[float] = []
    api = make_api(failures={"token": [httpx.ConnectError("no route")] * MAX_ATTEMPTS})

    with pytest.raises(DriveSignInError, match="ConnectError"):
        make_resource(api, sleeps).read_documents()

    assert api.routes.count("token") == MAX_ATTEMPTS
    assert drive_routes(api) == []


def test_token_endpoint_server_error_is_tried_again():
    # Phase 6c D1 (the shared retry rules)
    sleeps: list[float] = []
    api = make_api(failures={"token": [answer(503)]})

    assert len(make_resource(api, sleeps).read_documents()) == 4
    assert sleeps == [NETWORK_RETRY_SECONDS]


@pytest.mark.parametrize("route", [LIST_PHOTOS, GET_PHOTOS, f"thumbnail:{CAFE}"])
def test_drive_answering_401_fails_with_connect_again(route):
    # Phase 6c D7
    api = make_api(failures={route: [answer(401)]})

    with pytest.raises(DriveTokenRejected, match=TOKEN_REJECTED):
        make_resource(api).read_documents()


# Phase 6c D3, D4, D8, D15: what create_google_drive_resource reads from the Settings table and .env.
def drive_settings(**overrides) -> Settings:
    return Settings(**{"google_client_id": CLIENT_ID, "google_client_secret": CLIENT_SECRET, **overrides})


def rows(refresh_token=REFRESH_TOKEN, folder_id=FOLDER_PHOTOS):
    return lambda settings: GoogleDriveRows(refresh_token=refresh_token, folder_id=folder_id)


@pytest.mark.parametrize("refresh_token", [None, ""])
def test_not_connected_is_skipped(refresh_token):
    # Phase 6c D3
    resource = create_google_drive_resource(drive_settings(), read_rows=rows(refresh_token=refresh_token))

    with pytest.raises(ResourceSkipped, match="^not connected$"):
        resource.read_documents()


@pytest.mark.parametrize("folder_id", [None, ""])
def test_connected_without_a_folder_is_skipped(folder_id):
    # Phase 6c D4
    resource = create_google_drive_resource(drive_settings(), read_rows=rows(folder_id=folder_id))

    with pytest.raises(ResourceSkipped, match="^no folder chosen$"):
        resource.read_documents()


@pytest.mark.parametrize(("overrides", "key"), [
    ({"google_client_id": None}, "GOOGLE_CLIENT_ID"),
    ({"google_client_secret": None}, "GOOGLE_CLIENT_SECRET"),
])
def test_missing_client_key_fails_naming_only_the_key(overrides, key):
    # Phase 6c D8
    resource = create_google_drive_resource(drive_settings(**overrides), read_rows=rows())

    with pytest.raises(MissingSettingError, match=key) as raised:
        resource.read_documents()

    assert REFRESH_TOKEN not in str(raised.value)


def test_unreadable_settings_table_fails_the_resource():
    # Phase 6c D15
    def unreadable(settings):
        raise SettingsStoreError("the Settings table could not be read: OperationalError")

    with pytest.raises(SettingsStoreError):
        create_google_drive_resource(drive_settings(), read_rows=unreadable).read_documents()


def test_rows_are_read_at_each_build():
    # Phase 6c D1 (a new sign-in or folder is used by the next build without a restart)
    reads = []

    def counting(settings):
        reads.append(settings)
        return GoogleDriveRows(refresh_token=None, folder_id=None)

    resource = create_google_drive_resource(drive_settings(), read_rows=counting)
    for _ in range(2):
        with pytest.raises(ResourceSkipped):
            resource.read_documents()

    assert len(reads) == 2


def test_google_drive_rows_hide_the_refresh_token_when_printed():
    # Phase 6c H5
    assert REFRESH_TOKEN not in repr(GoogleDriveRows(refresh_token=REFRESH_TOKEN, folder_id=FOLDER_PHOTOS))
    assert CLIENT_SECRET not in repr(GOOGLE_CLIENT)
    assert REFRESH_TOKEN not in repr(DriveConnection(FOLDER_PHOTOS, REFRESH_TOKEN, GOOGLE_CLIENT))


# Phase 6c D9 to D12: the chosen folder tree.
def test_every_image_in_the_folder_tree_is_read_once():
    # Phase 6c D9
    api = make_api()

    documents = make_resource(api).read_documents()

    assert sorted(by_name(documents)) == IMAGE_NAMES
    assert [route for route in api.routes if route.startswith("files.list:")] == [
        LIST_PHOTOS, LIST_PHOTOS, f"files.list:{FOLDER_PARIS}", f"files.list:{FOLDER_NIGHT}"
    ]
    lists = [request for request, route in zip(api.requests, api.routes) if route == LIST_PHOTOS]
    assert "pageToken" not in lists[0].url.params
    assert lists[1].url.params["pageToken"] == "page-token-2"
    downloads = [route for route in api.routes if route.startswith(("thumbnail:", "media:"))]
    assert sorted(downloads) == sorted(set(downloads)) and len(downloads) == 4


def test_image_outside_the_chosen_folder_is_not_read():
    # Phase 6c D9: choosing Paris leaves out the images of Photos
    api = make_api()

    documents = make_resource(api, folder_id=FOLDER_PARIS).read_documents()

    assert sorted(by_name(documents)) == ["cafe.heic", "umbrella.png"]
    assert LIST_PHOTOS not in api.routes


def test_listing_asks_for_the_folders_images_and_subfolders_not_in_the_trash():
    # Phase 6c D9, D12
    api = make_api()

    make_resource(api).read_documents()

    params = api.requests[api.routes.index(LIST_PHOTOS)].url.params
    assert params["q"] == (
        f"'{FOLDER_PHOTOS}' in parents and trashed = false and "
        "(mimeType contains 'image/' or mimeType = 'application/vnd.google-apps.folder')"
    )
    assert params["pageSize"] == "1000"
    assert params["includeItemsFromAllDrives"] == "true"
    assert params["supportsAllDrives"] == "true"
    assert params["fields"] == (
        "nextPageToken, files(id, name, mimeType, createdTime, thumbnailLink, imageMediaMetadata(time))"
    )


def test_chosen_folder_is_looked_up_once_for_its_name():
    # Phase 6c D10, D11
    api = make_api()

    make_resource(api).read_documents()

    assert drive_routes(api)[0] == GET_PHOTOS
    assert api.routes.count(GET_PHOTOS) == 1
    request = api.requests[api.routes.index(GET_PHOTOS)]
    assert request.url.params["fields"] == "id, name, mimeType, trashed"
    assert request.url.params["supportsAllDrives"] == "true"


def test_path_starts_at_the_chosen_folder_and_goes_down_to_the_images_folder():
    # Phase 6c D10
    documents = by_name(make_resource(make_api()).read_documents())

    assert documents["paris_rain.jpg"].metadata["path"] == "Photos"
    assert documents["sketch.gif"].metadata["path"] == "Photos"
    assert documents["umbrella.png"].metadata["path"] == "Photos / Paris"
    assert documents["cafe.heic"].metadata["path"] == "Photos / Paris / Night"


def test_path_of_a_chosen_subfolder_starts_at_that_subfolder():
    # Phase 6c D10
    documents = by_name(make_resource(make_api(), folder_id=FOLDER_PARIS).read_documents())

    assert documents["cafe.heic"].metadata["path"] == "Paris / Night"


@pytest.mark.parametrize("failure", [answer(404), recorded_answer("forbidden_403")])
def test_chosen_folder_that_cannot_be_seen_fails_with_choose_again(failure):
    # Phase 6c D11
    api = make_api(failures={GET_PHOTOS: [failure]})

    with pytest.raises(DriveFolderNotFound, match=FOLDER_NOT_FOUND):
        make_resource(api).read_documents()

    assert LIST_PHOTOS not in api.routes


@pytest.mark.parametrize("change", [{"mimeType": "image/jpeg"}, {"trashed": True}])
def test_chosen_id_that_is_a_file_or_a_trashed_folder_fails_with_choose_again(change):
    # Phase 6c D11, D12
    data = recorded()
    data["folders"][FOLDER_PHOTOS].update(change)

    with pytest.raises(DriveFolderNotFound, match=FOLDER_NOT_FOUND):
        make_resource(make_api(data)).read_documents()


def test_folder_id_that_is_not_a_drive_id_is_never_sent_in_a_query():
    # Phase 6c D11 (the ID goes into the q parameter, so a quote could change the query)
    api = make_api()

    with pytest.raises(DriveFolderNotFound, match=FOLDER_NOT_FOUND):
        make_resource(api, folder_id="x' or name contains '").read_documents()

    assert drive_routes(api) == []


def test_folder_in_two_places_of_the_tree_is_read_once():
    # Phase 6c D9 (a Drive folder can have two parents)
    data = recorded()
    data["children"][FOLDER_PHOTOS]["page-token-2"]["files"].append(
        {"id": FOLDER_NIGHT, "name": "Night", "mimeType": FOLDER_MIME})
    api = make_api(data)

    documents = make_resource(api).read_documents()

    assert api.routes.count(f"files.list:{FOLDER_NIGHT}") == 1
    assert [document.metadata["name"] for document in documents].count("cafe.heic") == 1


def test_image_with_a_thumbnail_is_downloaded_as_the_512_px_thumbnail():
    # Phase 5b C5
    api = make_api()

    make_resource(api).read_documents()

    request = api.requests[api.routes.index(f"thumbnail:{PARIS_RAIN}")]
    assert str(request.url) == "https://lh3.googleusercontent.com/drive-storage/AJQWtBN1parisrainthumb0001=s512"
    assert request.headers["Authorization"] == f"Bearer {FAKE_ACCESS_TOKEN}"
    assert f"media:{PARIS_RAIN}" not in api.routes


def test_image_without_a_thumbnail_is_downloaded_in_full():
    # Phase 5b C6
    api = make_api()

    make_resource(api).read_documents()

    request = api.requests[api.routes.index(f"media:{SKETCH}")]
    assert request.url.path == f"/drive/v3/files/{SKETCH}"
    assert request.url.params["alt"] == "media"


def test_thumbnail_on_another_host_is_not_fetched_and_the_full_file_is_used():
    # Phase 5b C5 (the token is sent only to Google's thumbnail host)
    data = recorded()
    data["children"][FOLDER_PHOTOS]["start"]["files"][0]["thumbnailLink"] = "https://evil.example/picture=s220"
    api = make_api(data)

    make_resource(api).read_documents()

    assert all(request.url.host != "evil.example" for request in api.requests)
    assert f"media:{PARIS_RAIN}" in api.routes


def test_large_image_is_scaled_to_512_px_keeping_its_shape():
    # Phase 5b C7
    api = make_api(picture_map=pictures(**{UMBRELLA: picture_bytes(size=(1200, 800))}))

    documents = by_name(make_resource(api).read_documents())

    assert decoded(documents["umbrella.png"]).size == (MAX_PICTURE_SIDE, 341)
    assert MAX_PICTURE_SIDE == 512
    assert decoded(documents["paris_rain.jpg"]).size == SMALL_SIZE  # a small image is not enlarged


def test_transparent_png_becomes_an_rgb_jpeg_on_white():
    # Phase 5b C8
    api = make_api(picture_map=pictures(**{UMBRELLA: picture_bytes(mode="RGBA", color=(0, 0, 0, 0))}))

    picture = decoded(by_name(make_resource(api).read_documents())["umbrella.png"])

    assert picture.format == "JPEG"
    assert picture.mode == "RGB"
    assert all(abs(channel - 255) <= 2 for channel in picture.getpixel((10, 10)))


def test_file_pillow_cannot_open_is_skipped_and_counted():
    # Phase 5b C9
    api = make_api(picture_map=pictures(**{CAFE: b"not a picture"}))
    resource = make_resource(api)

    documents = resource.read_documents()

    assert sorted(by_name(documents)) == ["paris_rain.jpg", "sketch.gif", "umbrella.png"]
    assert "1 skipped files" in resource.read_summary()


@pytest.mark.parametrize("status", [403, 404])
def test_download_that_is_refused_or_gone_is_skipped_and_counted(status):
    # Phase 5b C9 (a thumbnail that cannot be fetched skips only that image)
    api = make_api(failures={f"thumbnail:{CAFE}": [answer(status)]})
    resource = make_resource(api)

    documents = resource.read_documents()

    assert "cafe.heic" not in by_name(documents)
    assert len(documents) == 3
    assert "1 skipped files" in resource.read_summary()


def test_document_text_is_base64_jpeg_and_metadata_has_name_path_type_and_timestamp():
    # Phase 5b C10
    documents = by_name(make_resource(make_api()).read_documents())

    paris = documents["paris_rain.jpg"]
    assert decoded(paris).format == "JPEG"
    assert paris.text.isascii()
    assert paris.metadata == {
        "name": "paris_rain.jpg",
        "path": "Photos",
        "type": "picture",
        "timestamp": "2026-09-14T18:42:10",
    }


def test_timestamp_is_the_taken_time_when_known_otherwise_the_created_time():
    # Phase 5b C11
    documents = by_name(make_resource(make_api()).read_documents())

    assert documents["cafe.heic"].metadata["timestamp"] == "2026-09-15T09:01:55"
    assert documents["umbrella.png"].metadata["timestamp"] == "2026-09-21T10:05:00.000Z"
    assert documents["sketch.gif"].metadata["timestamp"] == "2026-10-02T12:00:00.000Z"


def test_unreadable_taken_time_falls_back_to_the_created_time():
    # Phase 5b C11
    data = recorded()
    data["children"][FOLDER_PHOTOS]["start"]["files"][0]["imageMediaMetadata"]["time"] = "0000:00:00 00:00:00"

    documents = by_name(make_resource(make_api(data)).read_documents())

    assert documents["paris_rain.jpg"].metadata["timestamp"] == "2026-09-20T07:12:31.000Z"


def test_rate_limit_waits_retry_after_and_tries_again():
    # Phase 5b C16
    sleeps: list[float] = []
    api = make_api(failures={LIST_PHOTOS: [answer(429, {"Retry-After": "3"})]})

    documents = make_resource(api, sleeps).read_documents()

    assert sleeps == [3.0]
    assert len(documents) == 4


def test_rate_limit_without_retry_after_waits_like_a_network_retry_and_is_bounded():
    # Phase 5b C16
    sleeps: list[float] = []
    api = make_api(failures={LIST_PHOTOS: [answer(429)] * MAX_ATTEMPTS})

    with pytest.raises(httpx.HTTPStatusError):
        make_resource(api, sleeps).read_documents()

    assert sleeps == [NETWORK_RETRY_SECONDS * 2**attempt for attempt in range(MAX_ATTEMPTS - 1)]


def test_long_retry_after_is_clamped():
    # Phase 5b C16
    sleeps: list[float] = []
    api = make_api(failures={LIST_PHOTOS: [answer(429, {"Retry-After": "3600"})]})

    make_resource(api, sleeps).read_documents()

    assert sleeps == [60.0]


@pytest.mark.parametrize("error", [
    httpx.ConnectError("no route"),
    httpx.ReadError("connection reset"),
    httpx.ReadTimeout("timed out"),
])
def test_dropped_connection_or_timeout_waits_and_tries_again(error):
    # Phase 5b C17
    sleeps: list[float] = []
    api = make_api(failures={f"thumbnail:{PARIS_RAIN}": [error]})

    documents = make_resource(api, sleeps).read_documents()

    assert sleeps == [NETWORK_RETRY_SECONDS] == [1.0]
    assert len(documents) == 4


def test_network_retries_wait_1_2_4_and_8_seconds_and_stop_after_5_attempts():
    # Phase 5b C17
    sleeps: list[float] = []
    api = make_api(failures={LIST_PHOTOS: [httpx.ReadError("connection reset")] * MAX_ATTEMPTS})

    with pytest.raises(httpx.ReadError):
        make_resource(api, sleeps).read_documents()

    assert sleeps == [1.0, 2.0, 4.0, 8.0]
    assert MAX_ATTEMPTS == 5
    assert api.routes.count(LIST_PHOTOS) == MAX_ATTEMPTS


@pytest.mark.parametrize("route", [LIST_PHOTOS, f"thumbnail:{PARIS_RAIN}"])
def test_network_error_that_cannot_pass_by_trying_again_is_raised_after_one_attempt(route):
    # Phase 5c D20
    sleeps: list[float] = []
    api = make_api(failures={route: [httpx.LocalProtocolError("a malformed request header")]})

    with pytest.raises(httpx.LocalProtocolError):
        make_resource(api, sleeps).read_documents()

    assert api.routes.count(route) == 1
    assert sleeps == []


def test_server_error_is_tried_again():
    # Phase 5b C15 C17
    sleeps: list[float] = []
    api = make_api(failures={LIST_PHOTOS: [answer(503)]})

    assert len(make_resource(api, sleeps).read_documents()) == 4
    assert sleeps == [1.0]


def test_read_summary_counts_images_skips_calls_waits_and_time():
    # Phase 5b C18
    ticks = iter([100.0, 107.5])
    api = make_api(
        picture_map=pictures(**{CAFE: b"broken"}),
        failures={LIST_PHOTOS: [answer(429, {"Retry-After": "3"}), httpx.ReadError("connection reset")]},
    )
    resource = make_resource(api, tokens=FakeTokens(), clock=lambda: next(ticks))

    resource.read_documents()

    assert resource.read_summary() == (
        f"4 images, 1 skipped files, {len(api.requests)} calls, 1 rate limit waits (3.0 s), "
        "1 network retries, 7.5 s"
    )


def test_read_summary_counts_the_token_call():
    # Phase 6c D1
    api = make_api()
    resource = make_resource(api)

    resource.read_documents()

    assert f"{len(api.requests)} calls" in resource.read_summary()
    assert "token" in api.routes


def test_read_summary_is_kept_when_the_read_fails():
    # Phase 5b C18
    resource = make_resource(make_api(failures={LIST_PHOTOS: [httpx.ReadError("reset")] * MAX_ATTEMPTS}),
                             tokens=FakeTokens())

    with pytest.raises(httpx.ReadError):
        resource.read_documents()

    assert f"{MAX_ATTEMPTS + 1} calls" in resource.read_summary()  # the folder lookup, then the listing attempts
    assert f"{MAX_ATTEMPTS - 1} network retries" in resource.read_summary()


def test_empty_folder_gives_no_document_and_no_error():
    # Phase 5b C19
    data = recorded()
    data["children"][FOLDER_PHOTOS] = {"start": data["empty_list"]}
    resource = make_resource(make_api(data), tokens=FakeTokens())

    assert resource.read_documents() == []
    assert resource.read_summary().startswith("0 images, 0 skipped files, 2 calls")


def test_drive_resource_implements_the_resource_base_as_an_image_source():
    # Phase 5b C20
    resource = make_resource(make_api())

    assert isinstance(resource, Resource)
    assert (resource.name, resource.kind) == ("google_drive", ResourceKind.IMAGE)
    assert NotionResource.kind is ResourceKind.TEXT
    assert DRIVE_READONLY_SCOPE == "https://www.googleapis.com/auth/drive.readonly"


@pytest.mark.parametrize("name", ["rate_limited_403", "user_rate_limited_403", "rate_limited_403_details"])
def test_rate_limited_403_on_the_listing_is_retried_like_a_429(name):
    # Phase 5b R2 C16
    sleeps: list[float] = []
    api = make_api(failures={LIST_PHOTOS: [recorded_answer(name)]})
    resource = make_resource(api, sleeps)

    documents = resource.read_documents()

    assert sleeps == [NETWORK_RETRY_SECONDS]
    assert len(documents) == 4
    assert "1 rate limit waits (1.0 s), 0 network retries" in resource.read_summary()


def test_rate_limited_403_honors_retry_after():
    # Phase 5b R2 C16
    sleeps: list[float] = []
    api = make_api(failures={LIST_PHOTOS: [recorded_answer("rate_limited_403", {"Retry-After": "2"})]})

    make_resource(api, sleeps).read_documents()

    assert sleeps == [2.0]


def test_rate_limited_403_retries_are_bounded():
    # Phase 5b R2 C16
    sleeps: list[float] = []
    api = make_api(failures={LIST_PHOTOS: [recorded_answer("rate_limited_403")] * MAX_ATTEMPTS})

    with pytest.raises(httpx.HTTPStatusError) as raised:
        make_resource(api, sleeps).read_documents()

    assert raised.value.response.status_code == 403
    assert sleeps == [1.0, 2.0, 4.0, 8.0]


def test_permission_403_on_the_listing_is_not_retried():
    # Phase 5b R2
    sleeps: list[float] = []
    api = make_api(failures={LIST_PHOTOS: [recorded_answer("forbidden_403")]})

    with pytest.raises(httpx.HTTPStatusError):
        make_resource(api, sleeps).read_documents()

    assert sleeps == []


def test_rate_limited_403_on_the_folder_lookup_is_retried():
    # Phase 6c D11 (a rate limit is not a folder the account cannot see)
    sleeps: list[float] = []
    api = make_api(failures={GET_PHOTOS: [recorded_answer("rate_limited_403_details")]})

    documents = by_name(make_resource(api, sleeps).read_documents())

    assert documents["umbrella.png"].metadata["path"] == "Photos / Paris"
    assert sleeps == [1.0]


def test_rate_limited_403_on_a_download_is_retried_and_the_image_is_read():
    # Phase 5b R2 C9
    sleeps: list[float] = []
    api = make_api(failures={f"thumbnail:{CAFE}": [recorded_answer("user_rate_limited_403")]})
    resource = make_resource(api, sleeps)

    documents = by_name(resource.read_documents())

    assert sorted(documents) == IMAGE_NAMES
    assert sleeps == [1.0]
    assert "0 skipped files" in resource.read_summary()


def test_permission_403_on_a_download_skips_the_image():
    # Phase 5b R2 C9
    resource = make_resource(make_api(failures={f"thumbnail:{CAFE}": [recorded_answer("forbidden_403")]}))

    assert "cafe.heic" not in by_name(resource.read_documents())
    assert "1 skipped files" in resource.read_summary()


class GatedDriveApi(FakeDriveApi):
    """Holds chosen routes until another route was answered, to force a parallel order."""

    def __init__(self, *args, held_route: str, release_route: str, **kwargs):
        super().__init__(*args, **kwargs)
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


def test_images_are_downloaded_in_parallel_and_documents_keep_the_listing_order():
    # Phase 5b SPEED (the listing order is the folder tree, breadth first)
    api = GatedDriveApi(recorded(), pictures(), held_route=f"thumbnail:{PARIS_RAIN}", release_route=f"media:{SKETCH}")

    documents = make_resource(api).read_documents()

    assert DOWNLOAD_WORKERS == 4
    assert [document.metadata["name"] for document in documents] == [
        "paris_rain.jpg", "sketch.gif", "umbrella.png", "cafe.heic"
    ]
    assert api.routes.index(f"media:{SKETCH}") < api.routes.index(f"thumbnail:{PARIS_RAIN}")


@pytest.mark.parametrize("name", ["rate_limited_403", "user_rate_limited_403", "rate_limited_403_details"])
def test_rate_limited_403_after_the_last_retry_fails_the_resource(name):
    # Phase 5b C26
    sleeps: list[float] = []
    api = make_api(failures={f"thumbnail:{CAFE}": [recorded_answer(name)] * MAX_ATTEMPTS})

    with pytest.raises(httpx.HTTPStatusError) as raised:
        make_resource(api, sleeps).read_documents()

    assert raised.value.response.status_code == 403
    assert sleeps == [1.0, 2.0, 4.0, 8.0]


class TokensFailingAfter:
    """Gives tokens for the folder lookup and listing calls, then fails like an unexpected error on the download path."""

    def __init__(self, good_uses: int):
        self.good_uses = good_uses
        self.lock = threading.Lock()

    def access_token(self) -> str:
        with self.lock:
            self.good_uses -= 1
            if self.good_uses < 0:
                raise OSError("token cache cannot be read")
        return FAKE_ACCESS_TOKEN


def test_unexpected_error_while_downloading_fails_the_resource():
    # Phase 5b C27
    lookup_and_listing_calls = 5

    with pytest.raises(OSError, match="token cache"):
        make_resource(make_api(), tokens=TokensFailingAfter(lookup_and_listing_calls)).read_documents()


def test_large_jpeg_is_decoded_at_reduced_size(monkeypatch):
    # Phase 5b C28
    drafts = []
    original_draft = JpegImagePlugin.JpegImageFile.draft

    def recording_draft(image, mode, size):
        drafts.append((mode, size))
        return original_draft(image, mode, size)

    monkeypatch.setattr(JpegImagePlugin.JpegImageFile, "draft", recording_draft)
    api = make_api(picture_map=pictures(**{PARIS_RAIN: picture_bytes(size=(2400, 1600), image_format="JPEG")}))

    documents = by_name(make_resource(api).read_documents())

    assert ("RGB", (MAX_PICTURE_SIDE, MAX_PICTURE_SIDE)) in drafts
    assert decoded(documents["paris_rain.jpg"]).size == (MAX_PICTURE_SIDE, 341)


@pytest.mark.parametrize("size", [(100, 60), (200, 100)])
def test_picture_over_pillows_pixel_limit_is_a_counted_skip(monkeypatch, size):
    # Phase 5b C28 (100 x 60 is in Pillow's warning range, 200 x 100 in its error range)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 5000)
    filters_before = list(warnings.filters)
    api = make_api(picture_map=pictures(**{UMBRELLA: picture_bytes(size=size)}))
    resource = make_resource(api)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Image.DecompressionBombWarning)
        documents = by_name(resource.read_documents())

    assert "umbrella.png" not in documents
    assert len(documents) == 3
    assert "1 skipped files" in resource.read_summary()
    assert list(warnings.filters) == filters_before


@pytest.mark.parametrize("answer", [{}, {"access_token": ""}, {"access_token": 5}, ["not", "an", "object"]])
def test_token_answer_without_an_access_token_fails_as_a_sign_in_error(answer):
    # Phase 6c review: a 200 answer that is not a token is a sign-in error, not a KeyError
    api = make_api(failures={"token": [httpx.Response(200, json=answer)]})

    with pytest.raises(DriveSignInError, match=TOKEN_REQUEST_FAILED):
        make_resource(api).read_documents()

    assert drive_routes(api) == []


def test_token_answer_without_expires_in_is_kept_for_the_default_hour_not_asked_again_at_every_call():
    # Phase 6c review: a missing expires_in must not make every call hit the token endpoint
    api = make_api(failures={"token": [httpx.Response(200, json={"access_token": FAKE_ACCESS_TOKEN})]})
    now = [1000.0]
    with api.client() as client:
        tokens = RefreshTokenSource(client, REFRESH_TOKEN, GOOGLE_CLIENT, ReadStats(), lambda _: None, lambda: now[0])

        tokens.access_token()
        tokens.access_token()

    assert api.routes.count("token") == 1
