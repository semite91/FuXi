"""Reads app-wide values the FuXi API saved in the Settings table. The engine never writes there."""

import psycopg

from settings import DatabaseSettings, Settings

NOTION_ACCESS_TOKEN_CODE = "NotionAccessToken"
SELECT_SETTING = 'SELECT "Value" FROM "Settings" WHERE "Code" = %s'
CONNECT_TIMEOUT_SECONDS = 10
READ_FAILED_MESSAGE = "the Settings table could not be read"


class SettingsStoreError(RuntimeError):
    """The Settings table could not be read. The message never holds a password or a token."""


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


def read_notion_token(settings: Settings) -> str | None:
    """The Notion access token the Learner connected on the Settings page; None when there is none.

    It is read at each call, so a new sign-in is used by the next build without a restart.
    """
    try:
        with connect_read_only(settings.require_database()) as connection:
            row = connection.execute(SELECT_SETTING, (NOTION_ACCESS_TOKEN_CODE,)).fetchone()
    except psycopg.Error as error:
        # psycopg's message can name the host and the user; only the error type is kept.
        raise SettingsStoreError(f"{READ_FAILED_MESSAGE}: {type(error).__name__}") from None
    return row[0] if row and row[0] else None
