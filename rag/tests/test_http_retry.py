import ast
import inspect
import threading
import traceback

import httpx
import pytest

import base
from resources import (
    document_fields,
    google_drive_resource,
    http_retry,
    letterboxd_tmdb_resource,
    notion_resource,
    spotify_resource,
)
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


def test_basic_header_holds_the_base64_of_the_user_and_password():
    # Phase 5d C3 D1
    assert http_retry.basic_header("client-id", "client-secret") == {
        "Authorization": "Basic Y2xpZW50LWlkOmNsaWVudC1zZWNyZXQ="
    }


class ExampleError(http_retry.ApiCallError):
    SERVICE = "Example"


def failed_answer(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.example.com/v1/items?query=secret-name")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError("failed for secret-name", request=request, response=response)


def test_call_error_of_a_status_holds_the_status_and_the_endpoint_only():
    # Phase 5d E10
    error = ExampleError.of_http_error(failed_answer(503), "/v1/items")

    assert str(error) == "Example call failed: 503 on /v1/items"
    assert (error.status, error.endpoint) == (503, "/v1/items")


def test_call_error_of_a_network_error_holds_its_kind_and_the_endpoint_only():
    # Phase 5d E10
    error = ExampleError.of_http_error(httpx.ConnectError("no route to secret-name"), "/v1/items")

    assert str(error) == "Example call failed: ConnectError on /v1/items"
    assert (error.status, error.endpoint) == (None, "/v1/items")


@pytest.mark.parametrize("content", ["<html>secret-name</html>", "", "[]", "null", '"secret-name"', "7"])
def test_answer_that_is_not_a_json_object_raises_the_call_error_without_its_body(content):
    # Phase 5d E9
    with pytest.raises(ExampleError) as raised:
        http_retry.json_object(httpx.Response(200, content=content.encode("utf-8")), "/v1/items", ExampleError)

    assert str(raised.value) == "Example call failed: an answer that is not a JSON object on /v1/items"
    assert raised.value.__cause__ is None
    assert "secret-name" not in "".join(traceback.format_exception(raised.value))


def test_json_object_answer_is_given_as_a_dict():
    # Phase 5d E9
    assert http_retry.json_object(httpx.Response(200, json={"items": []}), "/v1/items", ExampleError) == {"items": []}


@pytest.mark.parametrize("content", [b"<html>secret-name</html>", b"", b"[]", b"null", b'"secret-name"', b"7", b"\xff\xfe{}"])
def test_answer_that_is_not_a_json_object_is_none_for_a_caller_that_does_not_fail(content):
    # Phase 5d H3 (one JSON parsing for json_object and the Spotify error code)
    assert http_retry.json_object_or_none(httpx.Response(400, content=content)) is None


def test_json_object_answer_is_given_as_a_dict_also_to_a_caller_that_does_not_fail():
    # Phase 5d H3
    assert http_retry.json_object_or_none(httpx.Response(400, json={"error": "invalid_grant"})) == {"error": "invalid_grant"}


def ok_answer(json_body) -> httpx.Response:
    return httpx.Response(200, json=json_body, request=httpx.Request("GET", "https://api.example.com/v1/items"))


def test_call_json_gives_the_json_object_of_a_successful_call():
    # Phase 5d H3
    stats = ReadStats()

    answer = http_retry.call_json(
        lambda: ok_answer({"items": []}), "/v1/items", ExampleError, http_retry_wait, stats, lambda _: None
    )

    assert answer == {"items": []}
    assert stats.calls == 1


def test_call_json_retries_with_the_given_rule_and_raises_the_given_error_without_the_cause():
    # Phase 5d H3
    stats, sleeps = ReadStats(), []
    answers = iter([httpx.ConnectError("no route to secret-name")] * MAX_ATTEMPTS)

    def call():
        raise next(answers)

    with pytest.raises(ExampleError) as raised:
        http_retry.call_json(call, "/v1/items", ExampleError, http_retry_wait, stats, sleeps.append)

    assert str(raised.value) == "Example call failed: ConnectError on /v1/items"
    assert raised.value.__cause__ is None
    assert "secret-name" not in "".join(traceback.format_exception(raised.value))
    assert sleeps == [1.0, 2.0, 4.0, 8.0]


def test_call_json_checks_the_status_and_the_json_object():
    # Phase 5d H3
    request = httpx.Request("GET", "https://api.example.com/v1/items?query=secret-name")

    with pytest.raises(ExampleError) as refused:
        http_retry.call_json(
            lambda: httpx.Response(404, request=request), "/v1/items", ExampleError, http_retry_wait, ReadStats(),
            lambda _: None,
        )
    with pytest.raises(ExampleError) as not_json:
        http_retry.call_json(
            lambda: ok_answer(["secret-name"]), "/v1/items", ExampleError, http_retry_wait, ReadStats(), lambda _: None
        )

    assert (refused.value.status, refused.value.endpoint) == (404, "/v1/items")
    assert str(not_json.value) == "Example call failed: an answer that is not a JSON object on /v1/items"


def module_constants(module) -> set[str]:
    """The names a module assigns at its top level (imported names are left out)."""
    tree = ast.parse(inspect.getsource(module))
    return {
        target.id
        for node in tree.body if isinstance(node, ast.Assign)
        for target in node.targets if isinstance(target, ast.Name)
    }


def test_web_api_resources_share_the_call_and_check_code_the_separators_and_the_metadata_keys():
    # Phase 5d H3
    for module in (letterboxd_tmdb_resource, spotify_resource):
        assert module.call_json is http_retry.call_json
        assert not hasattr(module, "call_with_retry") and not hasattr(module, "json_object")
        assert module.LINE_SEPARATOR is document_fields.LINE_SEPARATOR
        assert module.SUMMARY_SEPARATOR is document_fields.SUMMARY_SEPARATOR
        assert not {"LINE_SEPARATOR", "SUMMARY_SEPARATOR", "METADATA_ALBUM"} & module_constants(module)
    assert (document_fields.LINE_SEPARATOR, document_fields.SUMMARY_SEPARATOR) == ("\n", ", ")
    assert base.METADATA_ALBUM == "album"
    assert spotify_resource.METADATA_ALBUM is base.METADATA_ALBUM


@pytest.mark.parametrize("error", [
    httpx.ConnectError("no route"),
    httpx.ReadTimeout("slow"),
    httpx.RemoteProtocolError("dropped"),
    failed_answer(503),
    failed_answer(500),
    failed_answer(400),
    ValueError("other"),
])
def test_rate_limit_rule_does_not_try_again_a_call_the_server_may_have_used(error):
    # Phase 5d D10
    assert http_retry.rate_limit_retry_wait(error, 0) is None


def test_rate_limit_rule_waits_the_retry_after_of_a_429():
    # Phase 5d D10
    request = httpx.Request("POST", "https://accounts.example.com/api/token")
    response = httpx.Response(429, headers={"Retry-After": "3"}, request=request)
    error = httpx.HTTPStatusError("rate limited", request=request, response=response)

    assert http_retry.rate_limit_retry_wait(error, 0) == Wait(3.0, rate_limited=True)
