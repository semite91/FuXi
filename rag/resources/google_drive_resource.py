"""Google Drive resource: every image shared with the service account, as Base64 JPEG picture documents."""

import base64
import io
import re
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageOps

from base import (
    METADATA_NAME,
    METADATA_PATH,
    METADATA_TIMESTAMP,
    METADATA_TYPE,
    PICTURE_DOCUMENT_TYPE,
    Document,
    Resource,
    ResourceKind,
)
from embedders import PICTURE_ERRORS, RGB_MODE
from resources.http_retry import (
    Clock,
    ReadStats,
    Wait,
    bearer_header,
    call_with_retry,
    create_http_client,
    http_retry_wait,
    rate_limit_wait,
    timed_read,
)
from resources.parallel import in_parallel
from settings import GOOGLE_SERVICE_ACCOUNT_FILE_KEY, Settings

RESOURCE_NAME = "google_drive"
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
# Images are downloaded and prepared this many at a time.
DOWNLOAD_WORKERS = 4

IMAGE_QUERY = "mimeType contains 'image/' and trashed = false"
PAGE_SIZE = 1000
FILE_FIELDS = "nextPageToken, files(id, name, mimeType, parents, createdTime, thumbnailLink, imageMediaMetadata(time))"
FOLDER_FIELDS = "id, name, parents"
TRUE_PARAM = "true"
MEDIA_PARAMS = {"alt": "media", "supportsAllDrives": TRUE_PARAM}

# Drive's thumbnailLink ends with its size, as "=s220"; the token is sent only to Google's thumbnail host.
THUMBNAIL_SIZE_PATTERN = re.compile(r"=s\d+$")
THUMBNAIL_SIZE_SUFFIX = "=s512"
THUMBNAIL_SCHEME = "https"
THUMBNAIL_HOST_SUFFIX = ".googleusercontent.com"

MAX_PICTURE_SIDE = 512
PICTURE_BOX = (MAX_PICTURE_SIDE, MAX_PICTURE_SIDE)
JPEG_FORMAT = "JPEG"
JPEG_QUALITY = 85
RGBA_MODE = "RGBA"
ALPHA_CHANNEL = "A"
ALPHA_MODES = frozenset({"RGBA", "LA", "PA"})
TRANSPARENCY_INFO = "transparency"
FLATTEN_BACKGROUND = (255, 255, 255)
FIRST_FRAME = 0
BASE64_ENCODING = "ascii"

# The photo's taken time, as Drive gives it from the EXIF data.
TAKEN_TIME_FORMAT = "%Y:%m:%d %H:%M:%S"
PATH_SEPARATOR = " / "

FORBIDDEN_STATUS = 403
# A folder or file answering with one of these is not visible to the service account.
UNREADABLE_STATUSES = frozenset({FORBIDDEN_STATUS, 404})
# A 403 with one of these reasons is Drive's rate limit, compared without case and underscores.
RATE_LIMIT_REASONS = frozenset({"ratelimitexceeded", "userratelimitexceeded"})
REASON_SEPARATOR = "_"

CredentialsLoader = Callable[..., Any]


class DriveSignInError(RuntimeError):
    """The service account key cannot be used. The message never holds the key's content."""


class AccessTokenSource(Protocol):
    def access_token(self) -> str: ...


class ServiceAccountTokens:
    """Signs in with the service account key (read-only Drive scope) and refreshes the token when it expires."""

    def __init__(
        self,
        key_file: Path,
        load_credentials: CredentialsLoader | None = None,
        request_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._key_file = key_file
        self._load_credentials = load_credentials or _service_account_credentials
        self._request_factory = request_factory or _google_auth_request
        self._credentials: Any = None
        self._lock = threading.Lock()

    def access_token(self) -> str:
        with self._lock:
            if self._credentials is None:
                self._credentials = self._load()
            if not self._credentials.valid:
                self._credentials.refresh(self._request_factory())
            return self._credentials.token

    def _load(self) -> Any:
        if not self._key_file.is_file():
            raise DriveSignInError(f"The {GOOGLE_SERVICE_ACCOUNT_FILE_KEY} file does not exist")
        try:
            return self._load_credentials(str(self._key_file), scopes=[DRIVE_READONLY_SCOPE])
        except Exception:
            # The cause is dropped, so no part of the key reaches a log.
            raise DriveSignInError(
                f"The {GOOGLE_SERVICE_ACCOUNT_FILE_KEY} file is not a valid service account key"
            ) from None


class GoogleDriveResource(Resource):
    name = RESOURCE_NAME
    kind = ResourceKind.IMAGE

    def __init__(
        self,
        token_source_factory: Callable[[], AccessTokenSource],
        http_client_factory: Callable[[], httpx.Client] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Clock = time.monotonic,
    ) -> None:
        self._token_source_factory = token_source_factory
        self._http_client_factory = http_client_factory or create_http_client
        self._sleep = sleep
        self._clock = clock
        self._stats = ReadStats()
        self._images = 0
        self._skipped_files = 0

    def read_documents(self) -> list[Document]:
        self._images = 0
        self._skipped_files = 0
        with timed_read(self._clock) as self._stats:
            return self._read_documents()

    def read_summary(self) -> str:
        return self._stats.summary(f"{self._images} images", f"{self._skipped_files} skipped files")

    def _read_documents(self) -> list[Document]:
        tokens = self._token_source_factory()
        with self._http_client_factory() as client:
            drive = _DriveSession(client, tokens, self._stats, self._sleep)
            files = list(_list_images(drive))
            self._images = len(files)
            folders = _FolderCache(drive)
            documents = in_parallel(lambda file: _read_image(drive, file, folders), files, DOWNLOAD_WORKERS)
        self._skipped_files = documents.count(None)
        return [document for document in documents if document is not None]


class _DriveSession:
    """Drive calls of one read, each with the current access token and the shared retry rules."""

    def __init__(
        self, client: httpx.Client, tokens: AccessTokenSource, stats: ReadStats, sleep: Callable[[float], None]
    ) -> None:
        self._client = client
        self._tokens = tokens
        self._stats = stats
        self._sleep = sleep

    def get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """The answer of a successful call; a 4xx or 5xx raises httpx.HTTPStatusError after the retries."""
        return call_with_retry(
            lambda: self._client.get(url, params=params, headers=self._headers()).raise_for_status(),
            _retry_wait,
            self._stats,
            self._sleep,
        )

    def download(self, file: dict[str, Any]) -> bytes:
        """Drive's 512 px thumbnail; the full file when there is no thumbnail on Google's host."""
        thumbnail = _thumbnail_url(file.get("thumbnailLink"))
        if thumbnail:
            return self.get(thumbnail).content
        return self.get(f"{DRIVE_FILES_URL}/{file['id']}", MEDIA_PARAMS).content

    def folder(self, folder_id: str) -> dict[str, Any]:
        return self.get(f"{DRIVE_FILES_URL}/{folder_id}", {"fields": FOLDER_FIELDS, "supportsAllDrives": TRUE_PARAM}).json()

    def _headers(self) -> dict[str, str]:
        return bearer_header(self._tokens.access_token())


class _FolderCache:
    """Each folder is asked from Drive once per read, even by parallel downloads; None marks an unreadable folder."""

    def __init__(self, drive: _DriveSession) -> None:
        self._drive = drive
        self._folders: dict[str, Future] = {}
        self._lock = threading.Lock()

    def get(self, folder_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._folders.get(folder_id)
            is_asker = entry is None
            if is_asker:
                entry = self._folders[folder_id] = Future()
        if is_asker:
            self._ask(folder_id, entry)
        return entry.result()

    def _ask(self, folder_id: str, entry: Future) -> None:
        """403 or 404 gives None; other errors are kept, so every image waiting for the folder raises them."""
        try:
            entry.set_result(self._drive.folder(folder_id))
        except httpx.HTTPStatusError as error:
            if _is_not_visible(error.response):
                entry.set_result(None)
            else:
                entry.set_exception(error)
        except Exception as error:
            entry.set_exception(error)


def create_google_drive_resource(settings: Settings) -> GoogleDriveResource:
    """The key file is read only when the resource reads, so a missing setting fails only then."""
    return GoogleDriveResource(
        token_source_factory=lambda: ServiceAccountTokens(settings.require_google_service_account_file())
    )


def prepare_picture(content: bytes) -> bytes:
    """First frame, upright, RGB (transparency on white), longest side at most 512 px, as JPEG bytes."""
    with Image.open(io.BytesIO(content)) as image:
        _check_pixel_limit(image)
        image.seek(FIRST_FRAME)
        # A JPEG is decoded at a reduced scale near 512 px; other formats ignore the draft.
        image.draft(RGB_MODE, PICTURE_BOX)
        picture = _to_rgb(ImageOps.exif_transpose(image))
    picture.thumbnail(PICTURE_BOX)
    output = io.BytesIO()
    picture.save(output, format=JPEG_FORMAT, quality=JPEG_QUALITY)
    return output.getvalue()


def _check_pixel_limit(image: Image.Image) -> None:
    """Above Pillow's pixel limit Pillow only warns; it is an error here, so the file is skipped before it loads.

    The check reads the size from the header; warnings.catch_warnings is not used because it is not thread safe.
    """
    limit = Image.MAX_IMAGE_PIXELS
    if limit is not None and image.width * image.height > limit:
        raise Image.DecompressionBombError(f"the picture has more than {limit} pixels")


def _list_images(drive: _DriveSession) -> Iterator[dict[str, Any]]:
    params = {
        "q": IMAGE_QUERY,
        "pageSize": PAGE_SIZE,
        "fields": FILE_FIELDS,
        "includeItemsFromAllDrives": TRUE_PARAM,
        "supportsAllDrives": TRUE_PARAM,
    }
    page_token: str | None = None
    while True:
        page_params = {**params, "pageToken": page_token} if page_token else params
        answer = drive.get(DRIVE_FILES_URL, page_params).json()
        yield from answer.get("files", [])
        page_token = answer.get("nextPageToken")
        if not page_token:
            return


def _read_image(drive: _DriveSession, file: dict[str, Any], folders: _FolderCache) -> Document | None:
    """The picture document, or None when the file is not visible (403, 404) or Pillow cannot prepare it."""
    try:
        content = drive.download(file)
    except httpx.HTTPStatusError as error:
        if not _is_not_visible(error.response):
            raise
        return None
    try:
        jpeg = prepare_picture(content)
    except PICTURE_ERRORS:
        return None
    text = base64.b64encode(jpeg).decode(BASE64_ENCODING)
    return Document(text, _build_metadata(file, folders))


def _build_metadata(file: dict[str, Any], folders: _FolderCache) -> dict[str, str]:
    return {
        METADATA_NAME: file.get("name", ""),
        METADATA_PATH: PATH_SEPARATOR.join(_folder_names(file, folders)),
        METADATA_TYPE: PICTURE_DOCUMENT_TYPE,
        METADATA_TIMESTAMP: _timestamp(file),
    }


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode not in ALPHA_MODES and TRANSPARENCY_INFO not in image.info:
        return image.convert(RGB_MODE)
    transparent = image.convert(RGBA_MODE)
    background = Image.new(RGB_MODE, transparent.size, FLATTEN_BACKGROUND)
    background.paste(transparent, mask=transparent.getchannel(ALPHA_CHANNEL))
    return background


def _folder_names(file: dict[str, Any], folders: _FolderCache) -> list[str]:
    """Parent folder names from the top folder down; the path stops at the first folder the account cannot read."""
    names: list[str] = []
    seen: set[str] = set()
    parents = file.get("parents") or []
    while parents and parents[0] not in seen:
        seen.add(parents[0])
        folder = folders.get(parents[0])
        if folder is None:
            break
        names.insert(0, folder.get("name", ""))
        parents = folder.get("parents") or []
    return names


def _timestamp(file: dict[str, Any]) -> str:
    """The photo's taken time (ISO, no time zone is known) when Drive has it, otherwise Drive's created time."""
    taken = (file.get("imageMediaMetadata") or {}).get("time")
    if taken:
        try:
            return datetime.strptime(taken, TAKEN_TIME_FORMAT).isoformat()
        except ValueError:
            pass
    return file.get("createdTime", "")


def _thumbnail_url(link: str | None) -> str | None:
    if not link:
        return None
    parsed = urlparse(link)
    if parsed.scheme != THUMBNAIL_SCHEME or not (parsed.hostname or "").endswith(THUMBNAIL_HOST_SUFFIX):
        return None
    return THUMBNAIL_SIZE_PATTERN.sub("", link) + THUMBNAIL_SIZE_SUFFIX


def _retry_wait(error: Exception, attempt: int) -> Wait | None:
    """Drive's rate limit 403 waits as a 429 does; every other error follows the shared httpx rule."""
    if isinstance(error, httpx.HTTPStatusError) and _is_rate_limit_refusal(error.response):
        return rate_limit_wait(error.response, attempt)
    return http_retry_wait(error, attempt)


def _is_not_visible(response: httpx.Response) -> bool:
    """403 or 404, but never a rate limit 403 that is still refused after the retries."""
    return response.status_code in UNREADABLE_STATUSES and not _is_rate_limit_refusal(response)


def _is_rate_limit_refusal(response: httpx.Response) -> bool:
    """A 403 whose error reasons (errors[] or details[]) name a rate limit."""
    if response.status_code != FORBIDDEN_STATUS:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return False
    entries = [*(error.get("errors") or []), *(error.get("details") or [])]
    reasons = {_normal_reason(entry.get("reason")) for entry in entries if isinstance(entry, dict)}
    return not reasons.isdisjoint(RATE_LIMIT_REASONS)


def _normal_reason(reason: Any) -> str:
    return reason.replace(REASON_SEPARATOR, "").lower() if isinstance(reason, str) else ""


def _service_account_credentials(path: str, scopes: list[str]) -> Any:
    # Imported here so the engine starts without loading google-auth.
    from google.oauth2 import service_account

    return service_account.Credentials.from_service_account_file(path, scopes=scopes)


def _google_auth_request() -> Any:
    from google.auth.transport.requests import Request

    return Request()
