"""Letterboxd and TMDB resource: every movie of the Letterboxd watched.csv, as one TMDB text document per movie."""

import csv
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

from base import (
    METADATA_NAME,
    METADATA_PATH,
    METADATA_TIMESTAMP,
    METADATA_TYPE,
    TEXT_DOCUMENT_TYPE,
    Document,
    Resource,
    ResourceKind,
)
from resources.http_retry import (
    Clock,
    ReadStats,
    bearer_header,
    call_with_retry,
    create_http_client,
    http_retry_wait,
    timed_read,
)
from resources.parallel import in_parallel
from settings import LETTERBOXD_WATCHED_FILE_KEY, Settings

RESOURCE_NAME = "letterboxd_tmdb"

# Letterboxd's data export; a UTF-8 BOM is allowed.
WATCHED_FILE_ENCODING = "utf-8-sig"
CSV_NEWLINE = ""
NAME_COLUMN = "Name"
YEAR_COLUMN = "Year"
DATE_COLUMN = "Date"
REQUIRED_COLUMNS = (NAME_COLUMN, YEAR_COLUMN)

TMDB_API_URL = "https://api.themoviedb.org/3"
SEARCH_MOVIE_URL = f"{TMDB_API_URL}/search/movie"
MOVIE_URL_FORMAT = f"{TMDB_API_URL}/movie/{{movie_id}}"
TMDB_LANGUAGE = "en-US"
DETAILS_PARAMS = {"append_to_response": "credits", "language": TMDB_LANGUAGE}
BAD_REQUEST_STATUS = 400
NOT_FOUND_STATUS = 404
UNPROCESSABLE_STATUS = 422
# TMDB refuses this one movie's request; the other movies can still be read.
REFUSED_REQUEST_STATUSES = frozenset({BAD_REQUEST_STATUS, UNPROCESSABLE_STATUS})
# A movie that the search found can be gone when its details are asked.
SKIPPED_DETAILS_STATUSES = REFUSED_REQUEST_STATUSES | {NOT_FOUND_STATUS}
TMDB_ERROR_FORMAT = "TMDB call failed: {failure} on {endpoint}"
NOT_A_JSON_OBJECT_FAILURE = "an answer that is not a JSON object"
INVALID_ADDRESS = "an address that is not valid"
EVERY_REQUEST_REFUSED_MESSAGE = "TMDB refused every movie request (400 or 422)"
# The endpoint of an error that is not of one call.
NO_ENDPOINT = ""
# A movie has no folder path.
NO_PATH = ""
# Movies are looked up this many at a time.
LOOKUP_WORKERS = 4

# TMDB's release_date is "yyyy-mm-dd"; its first part is the release year.
RELEASE_DATE_SEPARATOR = "-"
TITLE_KEYS = ("title", "original_title")
# Titles are compared with the Turkish letters turned into their Latin equivalents.
LATIN_LETTERS = str.maketrans("ıİöÖüÜşŞğĞçÇ", "iioouussggcc")
DIRECTOR_JOB = "Director"
COMPOSER_JOB = "Original Music Composer"
WRITING_DEPARTMENT = "Writing"
SCREENPLAY_JOBS = frozenset({"Screenplay", "Writer"})
MAX_ACTORS = 10

TITLE_FORMAT = "{title} ({year})"
LINE_FORMAT = "{label}: {value}"
DIRECTOR_LABEL = "Director"
MUSIC_LABEL = "Music"
SCREENPLAY_LABEL = "Screenplay"
GENRES_LABEL = "Genres"
ACTORS_LABEL = "Actors"
SUMMARY_LABEL = "Summary"
NAME_SEPARATOR = ", "
SUMMARY_SEPARATOR = ", "
LINE_SEPARATOR = "\n"

METADATA_DIRECTOR = "director"
METADATA_MUSICIAN = "musician"
METADATA_GENRE = "genre"


class WatchedFileError(RuntimeError):
    """The watched.csv cannot be used. The message names the setting, never the file's path."""


class TmdbError(RuntimeError):
    """A TMDB failure that fails the source. The message never holds the query string, so never the movie's
    name, and never the token."""

    def __init__(self, message: str, status: int | None = None, endpoint: str = NO_ENDPOINT) -> None:
        super().__init__(message)
        self.status = status
        self.endpoint = endpoint

    @classmethod
    def of_call(cls, failure: int | str, endpoint: str) -> "TmdbError":
        """A call that failed after the retries, or whose answer is not a JSON object: the message holds the
        status (or the kind of failure) and the endpoint's path."""
        status = failure if isinstance(failure, int) else None
        return cls(TMDB_ERROR_FORMAT.format(failure=failure, endpoint=endpoint), status, endpoint)


class TmdbRefusedError(TmdbError):
    """TMDB refused (400 or 422) the request of every movie that was looked up, so the fault is not in one
    movie. The message holds no movie name; the error has no status and no endpoint."""

    def __init__(self) -> None:
        super().__init__(EVERY_REQUEST_REFUSED_MESSAGE)


class Skip(Enum):
    """Why a watched row gave no document."""

    NO_MATCH = "no match"
    NOT_FOUND = "not found"
    REFUSED = "refused"


@dataclass(frozen=True)
class Movie:
    """A movie that was read, with the TMDB id that tells two rows of the same movie."""

    movie_id: str
    document: Document


@dataclass
class LookupCounts:
    """The lookups finished so far, by outcome; a movie that an earlier lookup also read is a repeated row.
    Counting is safe from many threads."""

    movies: int = 0
    repeated_rows: int = 0
    skips: Counter[Skip] = field(default_factory=Counter)
    _movie_ids: set[str] = field(default_factory=set, repr=False, compare=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def count(self, result: Movie | Skip) -> None:
        with self._lock:
            if isinstance(result, Skip):
                self.skips[result] += 1
            elif result.movie_id in self._movie_ids:
                self.repeated_rows += 1
            else:
                self._movie_ids.add(result.movie_id)
                self.movies += 1


@dataclass(frozen=True)
class WatchedRow:
    name: str
    year: int
    watched_date: str


@dataclass(frozen=True)
class WatchedList:
    """The rows to look up, and what was left out of the file's rows."""

    rows: list[WatchedRow]
    row_count: int = 0
    bad_rows: int = 0
    repeated_rows: int = 0


class LetterboxdTmdbResource(Resource):
    name = RESOURCE_NAME
    kind = ResourceKind.TEXT

    def __init__(
        self,
        watched_file_factory: Callable[[], Path],
        token_factory: Callable[[], str],
        http_client_factory: Callable[[], httpx.Client] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Clock = time.monotonic,
    ) -> None:
        self._watched_file_factory = watched_file_factory
        self._token_factory = token_factory
        self._http_client_factory = http_client_factory or create_http_client
        self._sleep = sleep
        self._clock = clock
        self._stats = ReadStats()
        self._watched = WatchedList([])
        self._counts = LookupCounts()

    def read_documents(self) -> list[Document]:
        self._watched = WatchedList([])
        self._counts = LookupCounts()
        with timed_read(self._clock) as self._stats:
            return self._read_documents()

    def read_summary(self) -> str:
        """The movies and skips count every lookup that finished, also when the read failed."""
        skips = self._counts.skips
        bad_rows = self._watched.bad_rows
        skip_counts = [f"{bad_rows} bad rows", *(f"{skips[skip]} {skip.value}" for skip in Skip)]
        return self._stats.summary(
            f"{self._watched.row_count} rows",
            f"{self._counts.movies} movies",
            f"{bad_rows + skips.total()} skipped rows ({SUMMARY_SEPARATOR.join(skip_counts)})",
            f"{self._watched.repeated_rows + self._counts.repeated_rows} repeated rows",
        )

    def _read_documents(self) -> list[Document]:
        token = self._token_factory()
        self._watched = read_watched_list(self._watched_file_factory())
        with self._http_client_factory() as client:
            tmdb = _TmdbSession(client, token, self._stats, self._sleep)
            results = in_parallel(lambda row: self._look_up(tmdb, row), self._watched.rows, LOOKUP_WORKERS)
        if results and all(result is Skip.REFUSED for result in results):
            raise TmdbRefusedError()
        return _documents_of_different_movies(results)

    def _look_up(self, tmdb: "_TmdbSession", row: WatchedRow) -> Movie | Skip:
        result = _read_movie(tmdb, row)
        self._counts.count(result)
        return result


class _TmdbSession:
    """TMDB calls of one read, each with the Bearer token and the shared retry rules."""

    def __init__(self, client: httpx.Client, token: str, stats: ReadStats, sleep: Callable[[float], None]) -> None:
        self._client = client
        self._headers = bearer_header(token)
        self._stats = stats
        self._sleep = sleep

    def get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        """The JSON object of a successful call. A 4xx, a 5xx or any other httpx error raises TmdbError after
        the retries; an answer that is not a JSON object raises it at once."""
        endpoint = _endpoint(url)
        try:
            response = call_with_retry(
                lambda: self._client.get(url, params=params, headers=self._headers).raise_for_status(),
                http_retry_wait,
                self._stats,
                self._sleep,
            )
        except httpx.HTTPStatusError as error:
            # The cause is dropped: its message holds the URL with the movie's name.
            raise TmdbError.of_call(error.response.status_code, endpoint) from None
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            raise TmdbError.of_call(type(error).__name__, endpoint) from None
        return _json_object(response, endpoint)

    def search(self, row: WatchedRow) -> list[dict[str, Any]]:
        params = {"query": row.name, "primary_release_year": row.year, "language": TMDB_LANGUAGE}
        return _entries(self.get(SEARCH_MOVIE_URL, params).get("results"))

    def details(self, movie_id: int) -> dict[str, Any]:
        return self.get(MOVIE_URL_FORMAT.format(movie_id=movie_id), DETAILS_PARAMS)


def _endpoint(url: str) -> str:
    """The path of a TMDB address; a movie id that makes no valid address raises TmdbError."""
    try:
        return httpx.URL(url).path
    except httpx.InvalidURL as error:
        # The cause is dropped: its message can hold a part of the address.
        raise TmdbError.of_call(type(error).__name__, INVALID_ADDRESS) from None


def _json_object(response: httpx.Response, endpoint: str) -> dict[str, Any]:
    try:
        answer = response.json()
    except ValueError:
        # The cause is dropped: it holds the answer's body.
        raise TmdbError.of_call(NOT_A_JSON_OBJECT_FAILURE, endpoint) from None
    if not isinstance(answer, dict):
        raise TmdbError.of_call(NOT_A_JSON_OBJECT_FAILURE, endpoint)
    return answer


def create_letterboxd_tmdb_resource(settings: Settings) -> LetterboxdTmdbResource:
    """The token and the file path are read only when the resource reads, so a missing setting fails only then."""
    return LetterboxdTmdbResource(
        watched_file_factory=settings.require_letterboxd_watched_file,
        token_factory=settings.require_tmdb_token,
    )


def read_watched_list(watched_file: Path) -> WatchedList:
    """Each name and year once, in the file's order; a row with an empty name or a year that is not a number is left out."""
    try:
        if not watched_file.is_file():
            raise WatchedFileError(f"The {LETTERBOXD_WATCHED_FILE_KEY} file does not exist")
        with watched_file.open(encoding=WATCHED_FILE_ENCODING, newline=CSV_NEWLINE) as csv_file:
            reader = csv.DictReader(csv_file)
            _check_columns(reader.fieldnames or [])
            return _watched_list(reader)
    except (UnicodeDecodeError, csv.Error):
        # The cause is dropped, so no part of the file reaches a log.
        raise WatchedFileError(f"The {LETTERBOXD_WATCHED_FILE_KEY} file is not a UTF-8 CSV file") from None
    except OSError:
        # The cause is dropped, so the file's path does not reach a log.
        raise WatchedFileError(f"The {LETTERBOXD_WATCHED_FILE_KEY} file cannot be opened or read") from None


def _check_columns(columns: Iterable[str]) -> None:
    for column in REQUIRED_COLUMNS:
        if column not in columns:
            raise WatchedFileError(f"The {LETTERBOXD_WATCHED_FILE_KEY} file has no {column} column")


def _watched_list(csv_rows: Iterable[dict[str, Any]]) -> WatchedList:
    rows: dict[tuple[str, int], WatchedRow] = {}
    row_count = bad_rows = repeated_rows = 0
    for csv_row in csv_rows:
        row_count += 1
        row = _watched_row(csv_row)
        if row is None:
            bad_rows += 1
        elif (row.name, row.year) in rows:
            repeated_rows += 1
        else:
            rows[(row.name, row.year)] = row
    return WatchedList(list(rows.values()), row_count, bad_rows, repeated_rows)


def _watched_row(csv_row: dict[str, Any]) -> WatchedRow | None:
    name = _text(csv_row.get(NAME_COLUMN))
    year = _text(csv_row.get(YEAR_COLUMN))
    if not name or not year.isdecimal():
        return None
    return WatchedRow(name, int(year), _iso_date(_text(csv_row.get(DATE_COLUMN))))


def _iso_date(text: str) -> str:
    """The watched date as an ISO date; empty text when the row has no readable date."""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return ""


def _documents_of_different_movies(results: Iterable[Movie | Skip]) -> list[Document]:
    """The document of each movie once, in the rows' order: of two rows that name the same TMDB movie, the
    first row's document is kept."""
    movies = [result for result in results if isinstance(result, Movie)]
    first_movies: dict[str, Movie] = {}
    for movie in movies:
        first_movies.setdefault(movie.movie_id, movie)
    return [movie.document for movie in first_movies.values()]


def _read_movie(tmdb: _TmdbSession, row: WatchedRow) -> Movie | Skip:
    """The movie with its document, or why the row is skipped: no result of its year, a search that TMDB refuses
    (400 or 422), or details that TMDB refuses or does not have (400, 422 or 404)."""
    try:
        results = tmdb.search(row)
    except TmdbError as error:
        return _skip_or_raise(error, REFUSED_REQUEST_STATUSES)
    movie_id = _matching_movie_id(results, row)
    if movie_id is None:
        return Skip.NO_MATCH
    try:
        details = tmdb.details(movie_id)
    except TmdbError as error:
        return _skip_or_raise(error, SKIPPED_DETAILS_STATUSES)
    return Movie(str(movie_id), build_document(details, row))


def _skip_or_raise(error: TmdbError, skipped_statuses: frozenset[int]) -> Skip:
    """The skip of a movie whose call got one of the statuses (refused on a 400 or 422, else not found); any
    other failure fails the source."""
    if error.status not in skipped_statuses:
        raise error
    return Skip.REFUSED if error.status in REFUSED_REQUEST_STATUSES else Skip.NOT_FOUND


def _matching_movie_id(results: list[dict[str, Any]], row: WatchedRow) -> int | None:
    """Among the results released in the row's year, the first with the row's name as its title or original
    title, else the first; a result without a release date never matches."""
    same_year = [
        result for result in results if _release_year(result) == str(row.year) and result.get("id") is not None
    ]
    name = _title_key(row.name)
    same_title = (result for result in same_year if name in _title_keys(result))
    match = next(same_title, same_year[0] if same_year else None)
    return match["id"] if match else None


def _title_keys(result: dict[str, Any]) -> set[str]:
    return {_title_key(_text(result.get(key))) for key in TITLE_KEYS}


def _title_key(title: str) -> str:
    """A title as it is compared: without outer spaces, Turkish letters as their Latin equivalents, in lowercase."""
    return title.strip().translate(LATIN_LETTERS).lower()


def _release_year(result: dict[str, Any]) -> str:
    release_date = result.get("release_date")
    return release_date.split(RELEASE_DATE_SEPARATOR)[0] if isinstance(release_date, str) else ""


def build_document(details: dict[str, Any], row: WatchedRow) -> Document:
    title = _text(details.get("title")) or row.name
    credits = details.get("credits")
    credits = credits if isinstance(credits, dict) else {}
    crew = _entries(credits.get("crew"))
    directors = _join(_names(member for member in crew if member.get("job") == DIRECTOR_JOB))
    musicians = _join(_names(member for member in crew if member.get("job") == COMPOSER_JOB))
    writers = _join(_names(member for member in crew if _is_screenplay(member)))
    genres = _join(_names(_entries(details.get("genres"))))
    actors = _join(_names(_entries(credits.get("cast")))[:MAX_ACTORS])
    lines = [
        TITLE_FORMAT.format(title=title, year=row.year),
        *_lines(
            (DIRECTOR_LABEL, directors),
            (MUSIC_LABEL, musicians),
            (SCREENPLAY_LABEL, writers),
            (GENRES_LABEL, genres),
            (ACTORS_LABEL, actors),
            (SUMMARY_LABEL, _text(details.get("overview"))),
        ),
    ]
    metadata = {
        METADATA_NAME: title,
        METADATA_PATH: NO_PATH,
        METADATA_DIRECTOR: directors,
        METADATA_MUSICIAN: musicians,
        METADATA_GENRE: genres,
        METADATA_TIMESTAMP: row.watched_date,
        METADATA_TYPE: TEXT_DOCUMENT_TYPE,
    }
    return Document(LINE_SEPARATOR.join(lines), metadata)


def _is_screenplay(member: dict[str, Any]) -> bool:
    return member.get("department") == WRITING_DEPARTMENT and member.get("job") in SCREENPLAY_JOBS


def _entries(entries: Any) -> list[dict[str, Any]]:
    """The objects of a TMDB list (search results, crew, cast or genres); anything else is an empty list."""
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []


def _names(entries: Iterable[dict[str, Any]]) -> list[str]:
    """Each name once, in TMDB's order."""
    return list(dict.fromkeys(name for name in (_text(entry.get("name")) for entry in entries) if name))


def _join(names: list[str]) -> str:
    return NAME_SEPARATOR.join(names)


def _lines(*labelled_values: tuple[str, str]) -> list[str]:
    """One line per value; a line without a value is left out."""
    return [LINE_FORMAT.format(label=label, value=value) for label, value in labelled_values if value]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
