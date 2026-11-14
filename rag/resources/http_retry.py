"""Retry rules, read statistics, the HTTP client and the Bearer header shared by the resources that call a web API."""

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TypeVar

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
