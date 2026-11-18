"""Google Drive resource: every image in the folder the Learner chose, as Base64 JPEG picture documents."""

import base64
import io
import re
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
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
    ResourceSkipped,
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
from settings import Settings
from settings_store import GoogleDriveRows, read_google_drive_rows

RESOURCE_NAME = "google_drive"
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REFRESH_TOKEN_GRANT = "refresh_token"
# A new access token is asked this long before the old one ends, so no call is sent with an expired token.
TOKEN_EXPIRY_MARGIN_SECONDS = 60
# Google answers 1 hour; used when expires_in is missing, so a build does not ask again at every call.
DEFAULT_TOKEN_LIFETIME_SECONDS = 3600
# Images are downloaded and prepared this many at a time.
DOWNLOAD_WORKERS = 4

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
# One folder's images and subfolders that are not in the trash.
CHILDREN_QUERY = (
    "'{folder_id}' in parents and trashed = false and "
    f"(mimeType contains 'image/' or mimeType = '{FOLDER_MIME_TYPE}')"
)
# Drive IDs are letters, digits, - and _; anything else never reaches the q parameter.
DRIVE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
PAGE_SIZE = 1000
FILE_FIELDS = "nextPageToken, files(id, name, mimeType, createdTime, thumbnailLink, imageMediaMetadata(time))"
FOLDER_FIELDS = "id, name, mimeType, trashed"
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
UNAUTHORIZED_STATUS = 401
# A folder or file answering with one of these is not visible to the connected account.
UNREADABLE_STATUSES = frozenset({FORBIDDEN_STATUS, 404})
# Google's token endpoint answers a refresh token it no longer accepts with one of these and invalid_grant.
TOKEN_REFUSED_STATUSES = frozenset({400, UNAUTHORIZED_STATUS})
INVALID_GRANT = "invalid_grant"
# A 403 with one of these reasons is Drive's rate limit, compared without case and underscores.
RATE_LIMIT_REASONS = frozenset({"ratelimitexceeded", "userratelimitexceeded"})
REASON_SEPARATOR = "_"

NOT_CONNECTED = "not connected"
NO_FOLDER_CHOSEN = "no folder chosen"
TOKEN_REJECTED_MESSAGE = "Google Drive token rejected: connect Google Drive again on the Settings page"
FOLDER_NOT_FOUND_MESSAGE = "Google Drive folder not found: choose the folder again on the Settings page"
TOKEN_REQUEST_FAILED = "Google's token request failed"


class DriveTokenRejected(RuntimeError):
    """Google no longer accepts the saved refresh token, or Drive answered 401."""


class DriveFolderNotFound(RuntimeError):
    """The chosen folder ID is not a folder the connected account can see."""


class DriveSignInError(RuntimeError):
    """Google's token endpoint failed for another reason, such as a wrong client ID or secret, or no network.

    The message holds only the status or the error type, never the client secret or the refresh token.
    """


@dataclass(frozen=True)
class GoogleClient:
    """The Google sign-in client from .env."""

    client_id: str
    client_secret: str = field(repr=False)


@dataclass(frozen=True)
class DriveConnection:
    """What one read needs: the chosen folder and how to get an access token."""

    folder_id: str
    refresh_token: str = field(repr=False)
    client: GoogleClient


class AccessTokenSource(Protocol):
    def access_token(self) -> str: ...


class RefreshTokenSource:
    """Gets an access token from the refresh token and asks again shortly before it ends (Google's last 1 hour).

    The token stays in memory; the Settings table is never written.
    """

    def __init__(
        self,
        client: httpx.Client,
        refresh_token: str,
        google_client: GoogleClient,
        stats: ReadStats,
        sleep: Callable[[float], None],
        clock: Clock,
    ) -> None:
        self._client = client
        self._form = {
            "grant_type": REFRESH_TOKEN_GRANT,
            "refresh_token": refresh_token,
            "client_id": google_client.client_id,
            "client_secret": google_client.client_secret,
        }
        self._stats = stats
        self._sleep = sleep
        self._clock = clock
        self._token: str | None = None
        self._renew_at = 0.0
        self._lock = threading.Lock()

    def access_token(self) -> str:
        with self._lock:
            if self._token is None or self._clock() >= self._renew_at:
                self._refresh()
            return self._token

    def _refresh(self) -> None:
        asked_at = self._clock()
        try:
            answer = call_with_retry(
                lambda: self._client.post(TOKEN_URL, data=self._form).raise_for_status(),
                http_retry_wait,
                self._stats,
                self._sleep,
            ).json()
        except httpx.HTTPStatusError as error:
            if _is_invalid_grant(error.response):
                raise DriveTokenRejected(TOKEN_REJECTED_MESSAGE) from None
            # Not an httpx error, so the Drive call that asked for the token neither takes it for its own answer
            # nor tries it again.
            raise DriveSignInError(f"{TOKEN_REQUEST_FAILED}: status {error.response.status_code}") from None
        except httpx.HTTPError as error:
            raise DriveSignInError(f"{TOKEN_REQUEST_FAILED}: {type(error).__name__}") from None
        token = answer.get("access_token") if isinstance(answer, dict) else None
        if not isinstance(token, str) or not token:
            raise DriveSignInError(f"{TOKEN_REQUEST_FAILED}: no access token in the answer")
        lifetime = answer.get("expires_in")
        if isinstance(lifetime, bool) or not isinstance(lifetime, (int, float)):
            lifetime = DEFAULT_TOKEN_LIFETIME_SECONDS
        self._token = token
        self._renew_at = asked_at + float(lifetime) - TOKEN_EXPIRY_MARGIN_SECONDS


TokenSourceFactory = Callable[[httpx.Client, DriveConnection], AccessTokenSource]


class GoogleDriveResource(Resource):
    name = RESOURCE_NAME
    kind = ResourceKind.IMAGE

    def __init__(
        self,
        connection_factory: Callable[[], DriveConnection],
        http_client_factory: Callable[[], httpx.Client] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Clock = time.monotonic,
        token_source_factory: TokenSourceFactory | None = None,
    ) -> None:
        self._connection_factory = connection_factory
        self._http_client_factory = http_client_factory or create_http_client
        self._sleep = sleep
        self._clock = clock
        self._token_source_factory = token_source_factory or self._refresh_token_source
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
        connection = self._connection_factory()
        with self._http_client_factory() as client:
            drive = _DriveSession(client, self._token_source_factory(client, connection), self._stats, self._sleep)
            images = list(_list_folder_tree(drive, connection.folder_id))
            self._images = len(images)
            documents = in_parallel(lambda image: _read_image(drive, image), images, DOWNLOAD_WORKERS)
        self._skipped_files = documents.count(None)
        return [document for document in documents if document is not None]

    def _refresh_token_source(self, client: httpx.Client, connection: DriveConnection) -> AccessTokenSource:
        return RefreshTokenSource(
            client, connection.refresh_token, connection.client, self._stats, self._sleep, self._clock
        )


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
        """The answer of a successful call; a 4xx or 5xx raises httpx.HTTPStatusError after the retries.

        A 401 means the access token was refused, which a new sign-in fixes.
        """
        try:
            return call_with_retry(
                lambda: self._client.get(url, params=params, headers=self._headers()).raise_for_status(),
                _retry_wait,
                self._stats,
                self._sleep,
            )
        except httpx.HTTPStatusError as error:
            if error.response.status_code == UNAUTHORIZED_STATUS:
                raise DriveTokenRejected(TOKEN_REJECTED_MESSAGE) from None
            raise

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


@dataclass(frozen=True)
class _DriveImage:
    """A listed image and the folder names from the chosen folder down to its own folder."""

    file: dict[str, Any]
    folder_names: tuple[str, ...]


def create_google_drive_resource(
    settings: Settings,
    read_rows: Callable[[Settings], GoogleDriveRows] = read_google_drive_rows,
) -> GoogleDriveResource:
    """The Settings rows are read at each read, so a new sign-in or folder needs no restart.

    Not connected or no folder skips Google Drive; a missing client key or an unreadable table fails it.
    """

    def connection_factory() -> DriveConnection:
        rows = read_rows(settings)
        if not rows.refresh_token:
            raise ResourceSkipped(NOT_CONNECTED)
        if not rows.folder_id:
            raise ResourceSkipped(NO_FOLDER_CHOSEN)
        client_id, client_secret = settings.require_google_client()
        return DriveConnection(rows.folder_id, rows.refresh_token, GoogleClient(client_id, client_secret))

    return GoogleDriveResource(connection_factory=connection_factory)


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


def _chosen_folder(drive: _DriveSession, folder_id: str) -> dict[str, Any]:
    """The chosen folder; a bad ID, a folder the account cannot see, a file or a trashed folder fails the read."""
    if not DRIVE_ID_PATTERN.fullmatch(folder_id):
        raise DriveFolderNotFound(FOLDER_NOT_FOUND_MESSAGE)
    try:
        folder = drive.folder(folder_id)
    except httpx.HTTPStatusError as error:
        if _is_not_visible(error.response):
            raise DriveFolderNotFound(FOLDER_NOT_FOUND_MESSAGE) from None
        raise
    if folder.get("mimeType") != FOLDER_MIME_TYPE or folder.get("trashed"):
        raise DriveFolderNotFound(FOLDER_NOT_FOUND_MESSAGE)
    return folder


def _list_folder_tree(drive: _DriveSession, folder_id: str) -> Iterator[_DriveImage]:
    """Every image in the chosen folder and its subfolders, breadth first; a folder in two places is read once."""
    chosen = _chosen_folder(drive, folder_id)
    pending = deque([(folder_id, (chosen.get("name", ""),))])
    seen = {folder_id}
    while pending:
        current_id, names = pending.popleft()
        for child in _list_children(drive, current_id):
            if child.get("mimeType") != FOLDER_MIME_TYPE:
                yield _DriveImage(child, names)
            elif child["id"] not in seen:
                seen.add(child["id"])
                pending.append((child["id"], (*names, child.get("name", ""))))


def _list_children(drive: _DriveSession, folder_id: str) -> Iterator[dict[str, Any]]:
    params = {
        "q": CHILDREN_QUERY.format(folder_id=folder_id),
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


def _read_image(drive: _DriveSession, image: _DriveImage) -> Document | None:
    """The picture document, or None when the file is not visible (403, 404) or Pillow cannot prepare it."""
    try:
        content = drive.download(image.file)
    except httpx.HTTPStatusError as error:
        if not _is_not_visible(error.response):
            raise
        return None
    try:
        jpeg = prepare_picture(content)
    except PICTURE_ERRORS:
        return None
    text = base64.b64encode(jpeg).decode(BASE64_ENCODING)
    return Document(text, _build_metadata(image))


def _build_metadata(image: _DriveImage) -> dict[str, str]:
    return {
        METADATA_NAME: image.file.get("name", ""),
        METADATA_PATH: PATH_SEPARATOR.join(image.folder_names),
        METADATA_TYPE: PICTURE_DOCUMENT_TYPE,
        METADATA_TIMESTAMP: _timestamp(image.file),
    }


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode not in ALPHA_MODES and TRANSPARENCY_INFO not in image.info:
        return image.convert(RGB_MODE)
    transparent = image.convert(RGBA_MODE)
    background = Image.new(RGB_MODE, transparent.size, FLATTEN_BACKGROUND)
    background.paste(transparent, mask=transparent.getchannel(ALPHA_CHANNEL))
    return background


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


def _is_invalid_grant(response: httpx.Response) -> bool:
    """Google's answer to a refresh token that ended (7 days in Testing) or was revoked."""
    if response.status_code not in TOKEN_REFUSED_STATUSES:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and body.get("error") == INVALID_GRANT
