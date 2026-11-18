"""Phase 6b section D (test_scenarios_2026_11_17_11_48): reading the Notion token from the Settings table.

These tests use the PostgreSQL database of .env.test and are skipped when the file or its FUXI_DB_* keys are
missing or the database cannot be reached. Each test works in a
schema of its own, so the API's tables in that database are never touched.
"""

import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql

from settings import TEST_ENV_PATH, DatabaseSettings, MissingSettingError, Settings, SettingsError, load_settings
from settings_store import (
    GoogleDriveRows,
    SettingsStoreError,
    connect_read_only,
    read_google_drive_rows,
    read_notion_token,
)

ACCESS_TOKEN = "secret_store-test-token"
OTHER_ACCESS_TOKEN = "secret_other-store-test-token"
UNREACHABLE_PORT = 1
CREATE_SETTINGS_TABLE = 'CREATE TABLE "Settings" ("Id" uuid PRIMARY KEY, "Code" text NOT NULL UNIQUE, "Value" text NOT NULL)'
INSERT_SETTING = 'INSERT INTO "Settings" ("Id", "Code", "Value") VALUES (gen_random_uuid(), %s, %s)'
UPDATE_SETTING = 'UPDATE "Settings" SET "Value" = %s WHERE "Code" = %s'
NOTION_ACCESS_TOKEN_CODE = "NotionAccessToken"
GOOGLE_DRIVE_REFRESH_TOKEN_CODE = "GoogleDriveRefreshToken"
GOOGLE_DRIVE_FOLDER_ID_CODE = "GoogleDriveFolderId"
GOOGLE_REFRESH_TOKEN = "1//refresh-token-of-a-store-test"
FOLDER_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz-_0123"


def _test_settings() -> Settings:
    if not TEST_ENV_PATH.is_file():
        pytest.skip(f"{TEST_ENV_PATH.name} is missing")
    return load_settings(TEST_ENV_PATH, environ={})


def _connect(database: DatabaseSettings) -> psycopg.Connection:
    return psycopg.connect(
        host=database.host, port=database.port, dbname=database.name,
        user=database.user, password=database.password, autocommit=True,
    )


def _connect_or_skip(settings: Settings) -> psycopg.Connection:
    """A connection to the .env.test database; the test is skipped when its keys are empty or it is down."""
    try:
        database = settings.require_database()
    except (MissingSettingError, SettingsError) as error:
        pytest.skip(f"the {TEST_ENV_PATH.name} database is not set: {error}")
    try:
        return _connect(database)
    except psycopg.OperationalError as error:
        # The type only: the message can name the host and user.
        pytest.skip(f"the {TEST_ENV_PATH.name} database cannot be reached ({type(error).__name__})")


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    """The .env.test settings, with every new connection pointed at an empty schema of this test."""
    test_settings = _test_settings()
    schema = f"rag_test_{uuid.uuid4().hex}"
    with _connect_or_skip(test_settings) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        monkeypatch.setenv("PGOPTIONS", f"-c search_path={schema}")
        try:
            yield test_settings
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def table(settings: Settings) -> psycopg.Connection:
    """A writable connection to an empty Settings table in the test schema."""
    connection = _connect(settings.require_database())
    connection.execute(CREATE_SETTINGS_TABLE)
    yield connection
    connection.close()


def test_saved_token_is_read(settings, table):
    # D2
    table.execute(INSERT_SETTING, (NOTION_ACCESS_TOKEN_CODE, ACCESS_TOKEN))

    assert read_notion_token(settings) == ACCESS_TOKEN


@pytest.mark.parametrize("rows", [[], [(NOTION_ACCESS_TOKEN_CODE, "")], [("NotionWorkspaceName", "Workspace")]])
def test_missing_or_empty_token_reads_as_none(settings, table, rows):
    # D5
    for row in rows:
        table.execute(INSERT_SETTING, row)

    assert read_notion_token(settings) is None


def test_changed_token_is_read_on_the_next_call(settings, table):
    # D4
    table.execute(INSERT_SETTING, (NOTION_ACCESS_TOKEN_CODE, ACCESS_TOKEN))
    read_notion_token(settings)
    table.execute(UPDATE_SETTING, (OTHER_ACCESS_TOKEN, NOTION_ACCESS_TOKEN_CODE))

    assert read_notion_token(settings) == OTHER_ACCESS_TOKEN


def test_store_connection_cannot_write(settings, table):
    # D3
    with connect_read_only(settings.require_database()) as connection:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            connection.execute(INSERT_SETTING, (NOTION_ACCESS_TOKEN_CODE, ACCESS_TOKEN))


def test_google_drive_rows_are_read_together(settings, table):
    # Phase 6c D1
    table.execute(INSERT_SETTING, (GOOGLE_DRIVE_REFRESH_TOKEN_CODE, GOOGLE_REFRESH_TOKEN))
    table.execute(INSERT_SETTING, (GOOGLE_DRIVE_FOLDER_ID_CODE, FOLDER_ID))
    table.execute(INSERT_SETTING, ("GoogleDriveEmail", "learner@example.com"))

    assert read_google_drive_rows(settings) == GoogleDriveRows(refresh_token=GOOGLE_REFRESH_TOKEN, folder_id=FOLDER_ID)


@pytest.mark.parametrize("rows", [[], [(GOOGLE_DRIVE_REFRESH_TOKEN_CODE, ""), (GOOGLE_DRIVE_FOLDER_ID_CODE, "")]])
def test_missing_or_empty_google_drive_rows_read_as_none(settings, table, rows):
    # Phase 6c D3, D4
    for row in rows:
        table.execute(INSERT_SETTING, row)

    assert read_google_drive_rows(settings) == GoogleDriveRows(refresh_token=None, folder_id=None)


def test_unreachable_database_fails_google_drive_without_secrets(settings):
    # Phase 6c D15
    database = settings.require_database()
    unreachable = Settings(database_values={
        "FUXI_DB_HOST": "127.0.0.1", "FUXI_DB_PORT": str(UNREACHABLE_PORT), "FUXI_DB_NAME": database.name,
        "FUXI_DB_USER": database.user, "FUXI_DB_PASSWORD": database.password,
    })

    with pytest.raises(SettingsStoreError) as raised:
        read_google_drive_rows(unreachable)

    assert database.password not in str(raised.value)


def test_unreachable_database_fails_without_secrets(settings):
    # D8
    database = settings.require_database()
    unreachable = Settings(database_values={
        "FUXI_DB_HOST": "127.0.0.1", "FUXI_DB_PORT": str(UNREACHABLE_PORT), "FUXI_DB_NAME": database.name,
        "FUXI_DB_USER": database.user, "FUXI_DB_PASSWORD": database.password,
    })

    with pytest.raises(SettingsStoreError) as raised:
        read_notion_token(unreachable)

    assert database.password not in str(raised.value)
    assert database.password not in repr(raised.value)
