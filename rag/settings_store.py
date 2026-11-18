"""Reads app-wide values the FuXi API saved in the Settings table. The engine never writes there."""

from collections.abc import Sequence
from dataclasses import dataclass, field

import psycopg

from settings import DatabaseSettings, Settings

NOTION_ACCESS_TOKEN_CODE = "NotionAccessToken"
GOOGLE_DRIVE_REFRESH_TOKEN_CODE = "GoogleDriveRefreshToken"
GOOGLE_DRIVE_FOLDER_ID_CODE = "GoogleDriveFolderId"
LETTERBOXD_LIKED_FILMS_CSV_CODE = "LetterboxdLikedFilmsCsv"
SELECT_SETTINGS = 'SELECT "Code", "Value" FROM "Settings" WHERE "Code" = ANY(%s)'
CONNECT_TIMEOUT_SECONDS = 10
READ_FAILED_MESSAGE = "the Settings table could not be read"


class SettingsStoreError(RuntimeError):
    """The Settings table could not be read. The message never holds a password or a token."""


@dataclass(frozen=True)
class GoogleDriveRows:
    """What the Settings page saved for Google Drive; an empty or missing row is None."""

    refresh_token: str | None = field(repr=False)
    folder_id: str | None


def connect_read_only(database: DatabaseSettings) -> psycopg.Connection:
    """A connection whose every transaction is read-only, so a mistake here can never change the API's data."""
    connection = psycopg.connect(
        host=database.host,
        port=database.port,
        dbname=database.name,
        user=database.user,
        password=database.password,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
    )
    connection.read_only = True
    return connection


def read_settings(settings: Settings, codes: Sequence[str]) -> dict[str, str]:
    """The values of these codes in one SELECT; a missing or empty value is left out.

    They are read at each call, so a new sign-in or folder is used by the next build without a restart.
    """
    try:
        with connect_read_only(settings.require_database()) as connection:
            rows = connection.execute(SELECT_SETTINGS, (list(codes),)).fetchall()
    except psycopg.Error as error:
        # psycopg's message can name the host and the user; only the error type is kept.
        raise SettingsStoreError(f"{READ_FAILED_MESSAGE}: {type(error).__name__}") from None
    return {code: value for code, value in rows if value}


def read_notion_token(settings: Settings) -> str | None:
    """The Notion access token the Learner connected on the Settings page; None when there is none."""
    return read_settings(settings, [NOTION_ACCESS_TOKEN_CODE]).get(NOTION_ACCESS_TOKEN_CODE)


def read_google_drive_rows(settings: Settings) -> GoogleDriveRows:
    """The Google refresh token and the chosen folder the Learner saved on the Settings page."""
    values = read_settings(settings, [GOOGLE_DRIVE_REFRESH_TOKEN_CODE, GOOGLE_DRIVE_FOLDER_ID_CODE])
    return GoogleDriveRows(
        refresh_token=values.get(GOOGLE_DRIVE_REFRESH_TOKEN_CODE),
        folder_id=values.get(GOOGLE_DRIVE_FOLDER_ID_CODE),
    )


def read_liked_films_csv(settings: Settings) -> str | None:
    """The text of the liked movies CSV the Learner uploaded on the Settings page; None when there is none."""
    return read_settings(settings, [LETTERBOXD_LIKED_FILMS_CSV_CODE]).get(LETTERBOXD_LIKED_FILMS_CSV_CODE)
