import base64
import copy
import io
import threading
import warnings

import httpx
import pytest
from PIL import Image, JpegImagePlugin

from base import Resource, ResourceKind
from fakes import FAKE_ACCESS_TOKEN, FakeDriveApi, FakeTokens, load_fixture
from resources.google_drive_resource import (
    DOWNLOAD_WORKERS,
    DRIVE_READONLY_SCOPE,
    MAX_PICTURE_SIDE,
    GoogleDriveResource,
    ServiceAccountTokens,
    create_google_drive_resource,
)
from resources.http_retry import MAX_ATTEMPTS, NETWORK_RETRY_SECONDS
from resources.notion_resource import NotionResource
from settings import MissingSettingError, Settings

PARIS_RAIN = "1dRvImgParisRain0000000000000001"
UMBRELLA = "1dRvImgUmbrella00000000000000002"
CAFE = "1dRvImgCafe000000000000000000003"
SKETCH = "1dRvImgSketch00000000000000000004"
FOLDER_PHOTOS = "1dRvFolderPhotos00000000000000a"
FOLDER_PARIS = "1dRvFolderParis000000000000000b"
IMAGE_NAMES = ["cafe.heic", "paris_rain.jpg", "sketch.gif", "umbrella.png"]
SMALL_SIZE = (64, 48)
WHITE = (255, 255, 255)
KEY_FILE_SECRET = "-----BEGIN PRIVATE KEY-----secret-key-content"


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


def make_resource(api, sleeps=None, tokens=None, clock=None):
    sleeps = [] if sleeps is None else sleeps
    return GoogleDriveResource(
        token_source_factory=lambda: tokens or FakeTokens(),
        http_client_factory=api.client,
        sleep=sleeps.append,
        **({"clock": clock} if clock is not None else {}),
    )


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


WAIT_SECONDS = 5.0


class FakeCredentials:
    def __init__(self):
        self.valid = False
        self.token = None
        self.refreshes = []

    def refresh(self, request):
        self.refreshes.append(request)
        self.token = "signed-in-token"
        self.valid = True


def test_sign_in_asks_google_auth_for_a_drive_readonly_token_only(tmp_path):
    # Phase 5b C1
    key_file = tmp_path / "drive.json"
    key_file.write_text("{}", encoding="utf-8")
    loads = []
    credentials = FakeCredentials()

    def load_credentials(path, scopes):
        loads.append((path, scopes))
        return credentials

    tokens = ServiceAccountTokens(key_file, load_credentials=load_credentials, request_factory=lambda: "request")

    assert tokens.access_token() == "signed-in-token"
    assert tokens.access_token() == "signed-in-token"
    assert loads == [(str(key_file), [DRIVE_READONLY_SCOPE])]
    assert DRIVE_READONLY_SCOPE == "https://www.googleapis.com/auth/drive.readonly"
    assert credentials.refreshes == ["request"]  # a valid token is not refreshed again


def test_expired_token_is_refreshed(tmp_path):
    # Phase 5b C1
    key_file = tmp_path / "drive.json"
    key_file.write_text("{}", encoding="utf-8")
    credentials = FakeCredentials()
    tokens = ServiceAccountTokens(key_file, load_credentials=lambda path, scopes: credentials, request_factory=object)

    tokens.access_token()
    credentials.valid = False
    tokens.access_token()

    assert len(credentials.refreshes) == 2


def test_missing_key_file_fails_the_read_and_names_the_setting(tmp_path):
    # Phase 5b C2
    resource = create_google_drive_resource(Settings(google_service_account_file=str(tmp_path / "absent.json")))

    with pytest.raises(Exception, match="RAG_GOOGLE_SERVICE_ACCOUNT_FILE") as raised:
        resource.read_documents()

    assert "absent.json" not in str(raised.value)


def test_unreadable_key_file_error_hides_the_key_content(tmp_path):
    # Phase 5b C2
    key_file = tmp_path / "drive.json"
    key_file.write_text(KEY_FILE_SECRET, encoding="utf-8")
    resource = create_google_drive_resource(Settings(google_service_account_file=str(key_file)))

    with pytest.raises(Exception, match="RAG_GOOGLE_SERVICE_ACCOUNT_FILE") as raised:
        resource.read_documents()

    assert "secret-key-content" not in str(raised.value)
    assert raised.value.__cause__ is None


def test_unset_key_file_setting_fails_only_when_drive_is_read():
    # Phase 5b B3
    resource = create_google_drive_resource(Settings())

    with pytest.raises(MissingSettingError, match="RAG_GOOGLE_SERVICE_ACCOUNT_FILE"):
        resource.read_documents()


def test_every_image_is_read_once_over_two_result_pages():
    # Phase 5b C3
    api = make_api()

    documents = make_resource(api).read_documents()

    lists = [request for request, route in zip(api.requests, api.routes) if route == "files.list"]
    assert len(lists) == 2
    assert "pageToken" not in lists[0].url.params
    assert lists[1].url.params["pageToken"] == "page-token-2"
    assert sorted(by_name(documents)) == IMAGE_NAMES
    downloads = [route for route in api.routes if route.startswith(("thumbnail:", "media:"))]
    assert sorted(downloads) == sorted(set(downloads)) and len(downloads) == 4


def test_list_asks_only_for_images_not_in_the_trash():
    # Phase 5b C4
    api = make_api()

    make_resource(api).read_documents()

    params = api.requests[0].url.params
    assert api.routes[0] == "files.list"
    assert params["q"] == "mimeType contains 'image/' and trashed = false"
    assert params["pageSize"] == "1000"
    assert params["includeItemsFromAllDrives"] == "true"
    assert params["supportsAllDrives"] == "true"
    assert params["fields"] == (
        "nextPageToken, files(id, name, mimeType, parents, createdTime, thumbnailLink, imageMediaMetadata(time))"
    )


def test_every_call_sends_the_access_token():
    # Phase 5b C1 C5
    api = make_api()

    make_resource(api).read_documents()

    assert {request.headers["Authorization"] for request in api.requests} == {f"Bearer {FAKE_ACCESS_TOKEN}"}


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
    data["files_list"]["start"]["files"][0]["thumbnailLink"] = "https://evil.example/picture=s220"
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
    data["files_list"]["start"]["files"][0]["imageMediaMetadata"]["time"] = "0000:00:00 00:00:00"

    documents = by_name(make_resource(make_api(data)).read_documents())

    assert documents["paris_rain.jpg"].metadata["timestamp"] == "2026-09-20T07:12:31.000Z"


def test_nested_folders_make_the_path_from_the_top_folder_down():
    # Phase 5b C12
    documents = by_name(make_resource(make_api()).read_documents())

    assert documents["umbrella.png"].metadata["path"] == "Photos / Paris"
    assert documents["cafe.heic"].metadata["path"] == "Photos / Paris"
    assert documents["sketch.gif"].metadata["path"] == "Photos"


def test_each_folder_is_asked_from_drive_once():
    # Phase 5b C13
    api = make_api()

    make_resource(api).read_documents()

    folder_calls = [route for route in api.routes if route.startswith("files.get:")]
    assert folder_calls.count(f"files.get:{FOLDER_PARIS}") == 1
    assert folder_calls.count(f"files.get:{FOLDER_PHOTOS}") == 1
    request = api.requests[api.routes.index(f"files.get:{FOLDER_PARIS}")]
    assert request.url.params["fields"] == "id, name, parents"
    assert request.url.params["supportsAllDrives"] == "true"


@pytest.mark.parametrize("status", [403, 404])
def test_unreadable_parent_folder_ends_the_path_and_the_image_is_still_read(status):
    # Phase 5b C14
    api = make_api(failures={f"files.get:{FOLDER_PARIS}": [answer(status)]})

    documents = by_name(make_resource(api).read_documents())

    assert documents["umbrella.png"].metadata["path"] == ""
    assert documents["paris_rain.jpg"].metadata["path"] == "Photos"
    assert sorted(documents) == IMAGE_NAMES


@pytest.mark.parametrize(("status", "count"), [(500, MAX_ATTEMPTS), (401, 1)])
def test_parent_folder_server_error_or_refused_token_fails_the_resource(status, count):
    # Phase 5b C15
    api = make_api(failures={f"files.get:{FOLDER_PHOTOS}": [answer(status)] * count})

    with pytest.raises(httpx.HTTPStatusError) as raised:
        make_resource(api).read_documents()

    assert raised.value.response.status_code == status


def test_rate_limit_waits_retry_after_and_tries_again():
    # Phase 5b C16
    sleeps: list[float] = []
    api = make_api(failures={"files.list": [answer(429, {"Retry-After": "3"})]})

    documents = make_resource(api, sleeps).read_documents()

    assert sleeps == [3.0]
    assert len(documents) == 4


def test_rate_limit_without_retry_after_waits_like_a_network_retry_and_is_bounded():
    # Phase 5b C16
    sleeps: list[float] = []
    api = make_api(failures={"files.list": [answer(429)] * MAX_ATTEMPTS})

    with pytest.raises(httpx.HTTPStatusError):
        make_resource(api, sleeps).read_documents()

    assert sleeps == [NETWORK_RETRY_SECONDS * 2**attempt for attempt in range(MAX_ATTEMPTS - 1)]


def test_long_retry_after_is_clamped():
    # Phase 5b C16
    sleeps: list[float] = []
    api = make_api(failures={"files.list": [answer(429, {"Retry-After": "3600"})]})

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
    api = make_api(failures={"files.list": [httpx.ReadError("connection reset")] * MAX_ATTEMPTS})

    with pytest.raises(httpx.ReadError):
        make_resource(api, sleeps).read_documents()

    assert sleeps == [1.0, 2.0, 4.0, 8.0]
    assert MAX_ATTEMPTS == 5
    assert api.routes.count("files.list") == MAX_ATTEMPTS


@pytest.mark.parametrize("route", ["files.list", f"thumbnail:{PARIS_RAIN}"])
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
    api = make_api(failures={"files.list": [answer(503)]})

    assert len(make_resource(api, sleeps).read_documents()) == 4
    assert sleeps == [1.0]


# Phase 5b C25
def test_read_summary_counts_images_skips_calls_waits_and_time():
    # Phase 5b C18
    ticks = iter([100.0, 107.5])
    api = make_api(
        picture_map=pictures(**{CAFE: b"broken"}),
        failures={"files.list": [answer(429, {"Retry-After": "3"}), httpx.ReadError("connection reset")]},
    )
    resource = make_resource(api, clock=lambda: next(ticks))

    resource.read_documents()

    assert resource.read_summary() == (
        f"4 images, 1 skipped files, {len(api.requests)} calls, 1 rate limit waits (3.0 s), "
        "1 network retries, 7.5 s"
    )


def test_read_summary_is_kept_when_the_read_fails():
    # Phase 5b C18
    resource = make_resource(make_api(failures={"files.list": [httpx.ReadError("reset")] * MAX_ATTEMPTS}))

    with pytest.raises(httpx.ReadError):
        resource.read_documents()

    assert f"{MAX_ATTEMPTS} calls" in resource.read_summary()
    assert f"{MAX_ATTEMPTS - 1} network retries" in resource.read_summary()


def test_no_shared_image_gives_no_document_and_no_error():
    # Phase 5b C19
    data = recorded()
    data["files_list"] = {"start": data["empty_list"]}
    resource = make_resource(make_api(data))

    assert resource.read_documents() == []
    assert resource.read_summary().startswith("0 images, 0 skipped files, 1 calls")


def test_drive_resource_implements_the_resource_base_as_an_image_source():
    # Phase 5b C20
    resource = make_resource(make_api())

    assert isinstance(resource, Resource)
    assert (resource.name, resource.kind) == ("google_drive", ResourceKind.IMAGE)
    assert NotionResource.kind is ResourceKind.TEXT


# Phase 5b C16
@pytest.mark.parametrize("name", ["rate_limited_403", "user_rate_limited_403", "rate_limited_403_details"])
def test_rate_limited_403_on_the_listing_is_retried_like_a_429(name):
    # Phase 5b R2 C16
    sleeps: list[float] = []
    api = make_api(failures={"files.list": [recorded_answer(name)]})
    resource = make_resource(api, sleeps)

    documents = resource.read_documents()

    assert sleeps == [NETWORK_RETRY_SECONDS]
    assert len(documents) == 4
    assert "1 rate limit waits (1.0 s), 0 network retries" in resource.read_summary()


def test_rate_limited_403_honors_retry_after():
    # Phase 5b R2 C16
    sleeps: list[float] = []
    api = make_api(failures={"files.list": [recorded_answer("rate_limited_403", {"Retry-After": "2"})]})

    make_resource(api, sleeps).read_documents()

    assert sleeps == [2.0]


def test_rate_limited_403_retries_are_bounded():
    # Phase 5b R2 C16
    sleeps: list[float] = []
    api = make_api(failures={"files.list": [recorded_answer("rate_limited_403")] * MAX_ATTEMPTS})

    with pytest.raises(httpx.HTTPStatusError) as raised:
        make_resource(api, sleeps).read_documents()

    assert raised.value.response.status_code == 403
    assert sleeps == [1.0, 2.0, 4.0, 8.0]


def test_permission_403_on_the_listing_is_not_retried():
    # Phase 5b R2
    sleeps: list[float] = []
    api = make_api(failures={"files.list": [recorded_answer("forbidden_403")]})

    with pytest.raises(httpx.HTTPStatusError):
        make_resource(api, sleeps).read_documents()

    assert sleeps == []


def test_rate_limited_403_on_a_download_is_retried_and_the_image_is_read():
    # Phase 5b R2 C9
    sleeps: list[float] = []
    api = make_api(failures={f"thumbnail:{CAFE}": [recorded_answer("user_rate_limited_403")]})
    resource = make_resource(api, sleeps)

    documents = by_name(resource.read_documents())

    assert sorted(documents) == IMAGE_NAMES
    assert sleeps == [1.0]
    assert "0 skipped files" in resource.read_summary()


# Phase 5b C22
def test_permission_403_on_a_download_skips_the_image():
    # Phase 5b R2 C9
    resource = make_resource(make_api(failures={f"thumbnail:{CAFE}": [recorded_answer("forbidden_403")]}))

    assert "cafe.heic" not in by_name(resource.read_documents())
    assert "1 skipped files" in resource.read_summary()


def test_rate_limited_403_on_a_folder_is_retried_and_the_path_is_kept():
    # Phase 5b R2 C14
    sleeps: list[float] = []
    api = make_api(failures={f"files.get:{FOLDER_PARIS}": [recorded_answer("rate_limited_403_details")]})

    documents = by_name(make_resource(api, sleeps).read_documents())

    assert documents["umbrella.png"].metadata["path"] == "Photos / Paris"
    assert sleeps == [1.0]


def test_permission_403_on_a_folder_ends_the_path():
    # Phase 5b R2 C14
    api = make_api(failures={f"files.get:{FOLDER_PARIS}": [recorded_answer("forbidden_403")]})

    assert by_name(make_resource(api).read_documents())["umbrella.png"].metadata["path"] == ""


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


# Phase 5b C23
def test_images_are_downloaded_in_parallel_and_documents_keep_the_listing_order():
    # Phase 5b SPEED
    api = GatedDriveApi(recorded(), pictures(), held_route=f"thumbnail:{PARIS_RAIN}", release_route=f"media:{SKETCH}")

    documents = make_resource(api).read_documents()

    assert DOWNLOAD_WORKERS == 4
    assert [document.metadata["name"] for document in documents] == [
        "paris_rain.jpg", "umbrella.png", "cafe.heic", "sketch.gif"
    ]
    assert api.routes.index(f"media:{SKETCH}") < api.routes.index(f"thumbnail:{PARIS_RAIN}")


class SlowFolderDriveApi(FakeDriveApi):
    """Answers folder lookups slowly, so parallel images would ask for the same folder together."""

    def __call__(self, request):
        if self._route(request).startswith("files.get:"):
            threading.Event().wait(0.05)
        return super().__call__(request)


# Phase 5b C24
def test_each_folder_is_asked_once_even_when_images_are_read_in_parallel():
    # Phase 5b SPEED C13
    data = recorded()
    paris_file = data["files_list"]["start"]["files"][1]
    data["files_list"]["start"]["files"] = [
        {**paris_file, "id": f"{UMBRELLA}-{index}", "name": f"umbrella-{index}.png", "thumbnailLink": None}
        for index in range(8)
    ]
    data["files_list"]["page-token-2"]["files"] = []
    api = SlowFolderDriveApi(data, {f"{UMBRELLA}-{index}": picture_bytes() for index in range(8)})

    documents = make_resource(api).read_documents()

    assert {document.metadata["path"] for document in documents} == {"Photos / Paris"}
    assert api.routes.count(f"files.get:{FOLDER_PARIS}") == 1
    assert api.routes.count(f"files.get:{FOLDER_PHOTOS}") == 1


@pytest.mark.parametrize("route", [f"thumbnail:{CAFE}", f"files.get:{FOLDER_PARIS}"])
@pytest.mark.parametrize("name", ["rate_limited_403", "user_rate_limited_403", "rate_limited_403_details"])
def test_rate_limited_403_after_the_last_retry_fails_the_resource(route, name):
    # Phase 5b C26
    sleeps: list[float] = []
    api = make_api(failures={route: [recorded_answer(name)] * MAX_ATTEMPTS})

    with pytest.raises(httpx.HTTPStatusError) as raised:
        make_resource(api, sleeps).read_documents()

    assert raised.value.response.status_code == 403
    assert sleeps == [1.0, 2.0, 4.0, 8.0]


class TokensFailingAfter:
    """Gives tokens for the listing calls, then fails like an unexpected error on the download path."""

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
    listing_calls = 2

    with pytest.raises(OSError, match="token cache"):
        make_resource(make_api(), tokens=TokensFailingAfter(listing_calls)).read_documents()


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
