import threading

import pytest

from resources.http_retry import (
    MAX_ATTEMPTS,
    MAX_RETRY_AFTER_SECONDS,
    ReadStats,
    Wait,
    backoff_seconds,
    call_with_retry,
    retry_after_seconds,
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
