import threading

import httpx
import pytest

from resources import google_drive_resource, http_retry, letterboxd_tmdb_resource, notion_resource
from resources.http_retry import (
    MAX_ATTEMPTS,
    MAX_RETRY_AFTER_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    TRANSIENT_NETWORK_ERRORS,
    ReadStats,
    Wait,
    backoff_seconds,
    call_with_retry,
    create_http_client,
    http_retry_wait,
    retry_after_seconds,
    timed_read,
)


class Retryable(Exception):
    pass


def network_wait(error: Exception, attempt: int) -> Wait | None:
    return Wait(backoff_seconds(attempt), rate_limited=False) if isinstance(error, Retryable) else None


def failing_then(answer, failures: int):
    calls = {"count": 0}

    def call():
        calls["count"] += 1
        if calls["count"] <= failures:
            raise Retryable()
        return answer

    return call


def test_backoff_doubles_from_one_second():
    # Phase 5b DRY C17
    assert [backoff_seconds(attempt) for attempt in range(MAX_ATTEMPTS - 1)] == [1.0, 2.0, 4.0, 8.0]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("3", 3.0), (None, 1.5), ("soon", 1.5), ("-4", 0.0), ("3600", MAX_RETRY_AFTER_SECONDS)],
)
def test_retry_after_is_parsed_and_clamped(raw, expected):
    # Phase 5b DRY C16
    assert retry_after_seconds(raw, default=1.5) == expected


def test_retryable_error_waits_and_the_call_succeeds():
    # Phase 5b DRY C17
    stats, sleeps = ReadStats(), []

    assert call_with_retry(failing_then("ok", 2), network_wait, stats, sleeps.append) == "ok"
    assert sleeps == [1.0, 2.0]
    assert (stats.calls, stats.network_retries, stats.rate_limit_waits) == (3, 2, 0)


def test_last_attempts_error_is_raised():
    # Phase 5b DRY C17
    stats, sleeps = ReadStats(), []

    with pytest.raises(Retryable):
        call_with_retry(failing_then("ok", MAX_ATTEMPTS), network_wait, stats, sleeps.append)

    assert stats.calls == MAX_ATTEMPTS
    assert len(sleeps) == MAX_ATTEMPTS - 1


def test_error_that_is_not_retryable_is_raised_at_once():
    # Phase 5b DRY
    stats = ReadStats()

    def call():
        raise KeyError("x")

    with pytest.raises(KeyError):
        call_with_retry(call, network_wait, stats, lambda _: None)

    assert stats.calls == 1


def test_rate_limit_wait_is_counted_with_its_seconds():
    # Phase 5b DRY C18
    stats = ReadStats()

    stats.count_wait(Wait(3.0, rate_limited=True))

    assert stats.summary("2 images") == "2 images, 0 calls, 1 rate limit waits (3.0 s), 0 network retries, 0.0 s"


def test_counts_from_many_threads_are_not_lost():
    # Phase 5b SPEED C18
    stats = ReadStats()
    threads = [threading.Thread(target=lambda: [stats.count_call() for _ in range(1000)]) for _ in range(8)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert stats.calls == 8000


def status_error(status: int, headers=None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.example/items")
    return httpx.HTTPStatusError("failed", request=request, response=httpx.Response(status, headers=headers or {}))


def test_http_rule_waits_retry_after_on_a_429():
    # Phase 5c D10
    assert http_retry_wait(status_error(429, {"Retry-After": "3"}), 0) == Wait(3.0, rate_limited=True)
    assert http_retry_wait(status_error(429), 2) == Wait(4.0, rate_limited=True)


@pytest.mark.parametrize("error", [
    status_error(500),
    status_error(503),
    httpx.ConnectError("no route"),
    httpx.ReadError("connection reset"),
    httpx.ReadTimeout("timed out"),
])
def test_http_rule_backs_off_on_a_server_error_a_dropped_connection_or_a_timeout(error):
    # Phase 5c D11
    assert [http_retry_wait(error, attempt) for attempt in range(MAX_ATTEMPTS - 1)] == [
        Wait(seconds, rate_limited=False) for seconds in (1.0, 2.0, 4.0, 8.0)
    ]


@pytest.mark.parametrize("error", [status_error(401), status_error(403), status_error(404), ValueError("bad answer")])
def test_http_rule_does_not_retry_other_errors(error):
    # Phase 5c D8 D9
    assert http_retry_wait(error, 0) is None


@pytest.mark.parametrize("error", [
    httpx.ConnectTimeout("timed out"),
    httpx.ReadTimeout("timed out"),
    httpx.WriteTimeout("timed out"),
    httpx.PoolTimeout("timed out"),
    httpx.ConnectError("no route"),
    httpx.ReadError("connection reset"),
    httpx.WriteError("connection reset"),
    httpx.CloseError("not closed"),
    httpx.RemoteProtocolError("the server dropped the connection"),
])
def test_http_rule_backs_off_on_a_transient_network_error(error):
    # Phase 5c D20
    assert [http_retry_wait(error, attempt) for attempt in range(MAX_ATTEMPTS - 1)] == [
        Wait(seconds, rate_limited=False) for seconds in (1.0, 2.0, 4.0, 8.0)
    ]


@pytest.mark.parametrize("error", [
    httpx.LocalProtocolError("a malformed request header"),
    httpx.UnsupportedProtocol("an unsupported protocol"),
    httpx.ProxyError("the proxy refused"),
    httpx.TransportError("another transport error"),
    httpx.DecodingError("an answer that cannot be decoded"),
    httpx.TooManyRedirects("too many redirects"),
])
def test_http_rule_does_not_retry_a_network_error_that_cannot_pass_by_trying_again(error):
    # Phase 5c D20
    assert http_retry_wait(error, 0) is None


def test_transient_network_errors_are_the_timeout_the_network_error_and_the_dropped_connection():
    # Phase 5c D20
    assert TRANSIENT_NETWORK_ERRORS == (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)


def test_error_that_cannot_pass_by_trying_again_is_called_once():
    # Phase 5c D20
    stats, sleeps = ReadStats(), []

    def call():
        raise httpx.LocalProtocolError("a malformed request header")

    with pytest.raises(httpx.LocalProtocolError):
        call_with_retry(call, http_retry_wait, stats, sleeps.append)

    assert (stats.calls, stats.network_retries, sleeps) == (1, 0, [])


def test_shared_http_client_has_the_request_timeout():
    # Phase 5c I8
    with create_http_client() as client:
        assert client.timeout == httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
    assert REQUEST_TIMEOUT_SECONDS == 60.0


def test_timed_read_gives_new_stats_and_keeps_the_seconds_of_the_read():
    # Phase 5c I8
    ticks = iter([100.0, 107.5])

    with timed_read(lambda: next(ticks)) as stats:
        stats.count_call()

    assert (stats.calls, stats.seconds) == (1, 7.5)


def test_timed_read_keeps_the_seconds_when_the_read_fails():
    # Phase 5c I8
    ticks = iter([10.0, 25.0])

    with pytest.raises(KeyError):
        with timed_read(lambda: next(ticks)) as stats:
            raise KeyError("x")

    assert stats.seconds == 15.0


def test_resources_share_the_http_client_and_the_timed_read():
    # Phase 5c I8
    for module in (google_drive_resource, letterboxd_tmdb_resource):
        assert module.create_http_client is http_retry.create_http_client
        assert not hasattr(module, "REQUEST_TIMEOUT_SECONDS") and not hasattr(module, "_create_http_client")
    for module in (google_drive_resource, letterboxd_tmdb_resource, notion_resource):
        assert module.timed_read is http_retry.timed_read
