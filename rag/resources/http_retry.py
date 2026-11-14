"""Retry rules, read statistics, the HTTP client, the Authorization headers and the call errors shared by the resources
that call a web API."""

import base64
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, ClassVar, TypeVar

import httpx

MAX_ATTEMPTS = 5
# A retried call waits 1, 2, 4 and 8 seconds.
NETWORK_RETRY_SECONDS = 1.0
NETWORK_RETRY_GROWTH = 2
MIN_RETRY_AFTER_SECONDS = 0.0
MAX_RETRY_AFTER_SECONDS = 60.0
RATE_LIMITED_STATUS = 429
MIN_SERVER_ERROR_STATUS = 500
RETRY_AFTER_HEADER = "retry-after"
REQUEST_TIMEOUT_SECONDS = 60.0
# Network errors that can pass by trying again: a timeout, a failed connection, a read, write or close error,
# and a connection that the server dropped.
TRANSIENT_NETWORK_ERRORS = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)
AUTHORIZATION_HEADER = "Authorization"
BEARER_FORMAT = "Bearer {token}"
BASIC_FORMAT = "Basic {credentials}"
BASIC_CREDENTIALS_FORMAT = "{user}:{password}"
BASIC_CREDENTIALS_ENCODING = "utf-8"
CALL_FAILED_FORMAT = "{service} call failed: {failure} on {endpoint}"
NOT_A_JSON_OBJECT_FAILURE = "an answer that is not a JSON object"
# The endpoint of an error that is not of one call.
NO_ENDPOINT = ""

T = TypeVar("T")
# Seconds that only move forward; differences between two readings are measured.
Clock = Callable[[], float]


@dataclass(frozen=True)
class Wait:
    """How long to wait before the next attempt, and whether the API asked for it (rate limit)."""

    seconds: float
    rate_limited: bool


# Decides from the error and the attempt (0-based) whether to wait and try again; None raises the error.
RetryRule = Callable[[Exception, int], Wait | None]


@dataclass
class ReadStats:
    """What one read cost: calls, waits and time. Counting is safe from many threads."""

    calls: int = 0
    rate_limit_waits: int = 0
    rate_limit_seconds: float = 0.0
    network_retries: int = 0
    seconds: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def count_call(self) -> None:
        with self._lock:
            self.calls += 1

    def count_wait(self, wait: Wait) -> None:
        with self._lock:
            if wait.rate_limited:
                self.rate_limit_waits += 1
                self.rate_limit_seconds += wait.seconds
            else:
                self.network_retries += 1

    def summary(self, *counts: str) -> str:
        """The resource's own counts first, then the calls, waits and time."""
        return ", ".join([
            *counts,
            f"{self.calls} calls",
            f"{self.rate_limit_waits} rate limit waits ({self.rate_limit_seconds:.1f} s)",
            f"{self.network_retries} network retries",
            f"{self.seconds:.1f} s",
        ])


@contextmanager
def timed_read(clock: Clock) -> Iterator[ReadStats]:
    """New statistics for one read; its seconds are kept also when the read fails."""
    stats = ReadStats()
    started = clock()
    try:
        yield stats
    finally:
        stats.seconds = clock() - started


def create_http_client() -> httpx.Client:
    """The httpx client of one read, with the shared request timeout."""
    return httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)


def call_with_retry(call: Callable[[], T], retry_rule: RetryRule, stats: ReadStats, sleep: Callable[[float], None]) -> T:
    """At most MAX_ATTEMPTS calls; the last attempt's error is raised."""
    for attempt in range(MAX_ATTEMPTS - 1):
        stats.count_call()
        try:
            return call()
        except Exception as error:
            wait = retry_rule(error, attempt)
            if wait is None:
                raise
        stats.count_wait(wait)
        sleep(wait.seconds)
    stats.count_call()
    return call()


def bearer_header(token: str) -> dict[str, str]:
    """The Authorization header of a call signed with a Bearer token."""
    return {AUTHORIZATION_HEADER: BEARER_FORMAT.format(token=token)}


def basic_header(user: str, password: str) -> dict[str, str]:
    """The Authorization header of a call signed with HTTP Basic credentials."""
    credentials = BASIC_CREDENTIALS_FORMAT.format(user=user, password=password).encode(BASIC_CREDENTIALS_ENCODING)
    return {AUTHORIZATION_HEADER: BASIC_FORMAT.format(credentials=base64.b64encode(credentials).decode("ascii"))}


class ApiCallError(RuntimeError):
    """A web API failure that fails the source. The message holds the status (or the kind of failure) and the
    endpoint's path only: never the query string, an answer's body or a token. Subclasses name the service."""

    SERVICE: ClassVar[str] = "API"

    def __init__(self, message: str, status: int | None = None, endpoint: str = NO_ENDPOINT) -> None:
        super().__init__(message)
        self.status = status
        self.endpoint = endpoint

    @classmethod
    def of_call(cls, failure: int | str, endpoint: str) -> "ApiCallError":
        """A call that failed after the retries, or whose answer is not a JSON object."""
        status = failure if isinstance(failure, int) else None
        return cls(cls.call_failed_message(failure, endpoint), status, endpoint)

    @classmethod
    def call_failed_message(cls, failure: int | str, endpoint: str) -> str:
        return CALL_FAILED_FORMAT.format(service=cls.SERVICE, failure=failure, endpoint=endpoint)

    @classmethod
    def of_http_error(cls, error: httpx.HTTPError | httpx.InvalidURL, endpoint: str) -> "ApiCallError":
        """The status of a failed answer, else the kind of the httpx error. The caller drops the cause: its
        message holds the full address."""
        if isinstance(error, httpx.HTTPStatusError):
            return cls.of_call(error.response.status_code, endpoint)
        return cls.of_call(type(error).__name__, endpoint)


def json_object_or_none(response: httpx.Response) -> dict[str, Any] | None:
    """The answer's JSON object; None when the body is not UTF-8, not JSON or not an object."""
    try:
        answer = response.json()
    except ValueError:
        return None
    return answer if isinstance(answer, dict) else None


def json_object(response: httpx.Response, endpoint: str, error_type: type[ApiCallError]) -> dict[str, Any]:
    """The answer's JSON object; anything else raises error_type without the answer's body."""
    answer = json_object_or_none(response)
    if answer is None:
        raise error_type.of_call(NOT_A_JSON_OBJECT_FAILURE, endpoint)
    return answer


def call_json(
    call: Callable[[], httpx.Response],
    endpoint: str,
    error_type: type[ApiCallError],
    retry_rule: RetryRule,
    stats: ReadStats,
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    """The JSON object of a successful call, tried again as retry_rule says. A failed answer or any other httpx
    error raises error_type with the status or the error's kind and the endpoint; so does an answer that is not
    a JSON object."""
    try:
        response = call_with_retry(lambda: call().raise_for_status(), retry_rule, stats, sleep)
    except (httpx.HTTPError, httpx.InvalidURL) as error:
        # The cause is dropped: an httpx error can hold the full address and the request with its token.
        raise error_type.of_http_error(error, endpoint) from None
    return json_object(response, endpoint, error_type)


def backoff_seconds(attempt: int) -> float:
    return NETWORK_RETRY_SECONDS * NETWORK_RETRY_GROWTH**attempt


def http_retry_wait(error: Exception, attempt: int) -> Wait | None:
    """The httpx rule: a 429 waits Retry-After (or backs off); a 5xx or a transient network error backs off."""
    if isinstance(error, TRANSIENT_NETWORK_ERRORS):
        return Wait(backoff_seconds(attempt), rate_limited=False)
    if not isinstance(error, httpx.HTTPStatusError):
        return None
    response = error.response
    if response.status_code == RATE_LIMITED_STATUS:
        return rate_limit_wait(response, attempt)
    if response.status_code >= MIN_SERVER_ERROR_STATUS:
        return Wait(backoff_seconds(attempt), rate_limited=False)
    return None


def rate_limit_retry_wait(error: Exception, attempt: int) -> Wait | None:
    """The rule of a call that must not reach the server twice (a single-use code): only a 429, which the server
    refused before it used the call, waits Retry-After (or backs off); any other error is raised at once."""
    if isinstance(error, httpx.HTTPStatusError) and error.response.status_code == RATE_LIMITED_STATUS:
        return rate_limit_wait(error.response, attempt)
    return None


def rate_limit_wait(response: httpx.Response, attempt: int) -> Wait:
    """The wait a rate limited answer asks for: its Retry-After, or the backoff when it has none."""
    raw = response.headers.get(RETRY_AFTER_HEADER)
    return Wait(retry_after_seconds(raw, backoff_seconds(attempt)), rate_limited=True)


def retry_after_seconds(raw: str | None, default: float) -> float:
    """The Retry-After header in seconds, kept between 0 and 60; the default when it is missing or not a number."""
    try:
        seconds = float(raw) if raw is not None else default
    except (TypeError, ValueError):
        seconds = default
    return min(max(seconds, MIN_RETRY_AFTER_SECONDS), MAX_RETRY_AFTER_SECONDS)
