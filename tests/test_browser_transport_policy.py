"""Native offline validation of the production transport's first boundary."""

import httpx
import pytest

from browser_runtime import browser_transport as bridge

URL = "https://api.openai.com/v1/chat/completions"


def request(url=URL, **kwargs):
    return httpx.Request("POST", url, headers={"authorization": "Bearer fixture-key"}, **kwargs)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1/messages",
        "https://api.anthropic.com/v1/chat/completions",
        "https://api.openai.com:444/v1/chat/completions",
        "http://api.openai.com/v1/chat/completions",
        "https://api.openai.com.evil.test/v1/chat/completions",
        "https://user@api.openai.com/v1/chat/completions",
        URL + "?api_key=fixture",
        URL + "#fragment",
        "https://127.0.0.1/v1/chat/completions",
        "https://[::1]/v1/chat/completions",
        "https://generativelanguage.googleapis.com/v1beta/models/unknown:generateContent",
    ],
)
def test_no_cross_provider_routes_ports_credentials_queries_or_private_endpoints(url):
    with pytest.raises(httpx.UnsupportedProtocol, match="endpoint is not allowed"):
        bridge._validated_request(request(url, json={"model": "gpt-4o-mini"}))


@pytest.mark.parametrize(
    "payload",
    [
        {"model": "gpt-4o-mini", "stream": True},
        {"model": "gpt-4o-mini", "stream": 0},
        {"model": "unknown"},
        [],
        None,
    ],
)
def test_streaming_and_unapproved_models_are_rejected(payload):
    with pytest.raises(httpx.TransportError):
        bridge._validated_request(request(content=__import__("json").dumps(payload)))


def test_request_limit_stops_reading_stream_before_excess_allocation():
    seen = []

    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            for index in range(4):
                seen.append(index)
                yield b"x" * (bridge.MAX_BYTES // 2)

    with pytest.raises(httpx.TransportError, match="size limit"):
        bridge._validated_request(request(stream=Stream()))
    assert seen == [0, 1, 2]


def test_headers_are_provider_specific_and_unrelated_credentials_are_dropped():
    req = httpx.Request(
        "POST",
        "https://api.anthropic.com/v1/messages",
        json={"model": "claude-sonnet-5"},
        headers={
            "x-api-key": "fixture-key",
            "authorization": "Bearer unrelated",
            "cookie": "unrelated",
            "openai-project": "unrelated",
            "anthropic-version": "untrusted-version",
            "x-secret-extra": "unrelated",
        },
    )
    _, _, headers = bridge._validated_request(req)
    assert headers == {
        "x-api-key": "fixture-key",
        "content-type": "application/json",
        "accept": "application/json",
        "anthropic-version": "2023-06-01",
        "anthropic-dangerous-direct-browser-access": "true",
    }


@pytest.mark.parametrize("timeout, expected", [(None, 30000), (90, 30000), (0.1, 100), (0.0001, 1)])
def test_timeout_never_exceeds_thirty_seconds(timeout, expected):
    req = request(json={"model": "gpt-4o-mini"})
    req.extensions["timeout"] = {"read": timeout}
    assert bridge._timeout_ms(req) == expected


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True, "30"])
def test_invalid_timeout_does_not_fall_back_to_unbounded_wait(timeout):
    req = request(json={"model": "gpt-4o-mini"})
    req.extensions["timeout"] = {"read": timeout}
    with pytest.raises(httpx.ReadTimeout):
        bridge._timeout_ms(req)


def test_no_custom_transport_or_provider_fixture_origin_option():
    with pytest.raises(ValueError, match="Custom transports are not allowed"):
        bridge.browser_http_client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    with pytest.raises(TypeError):
        bridge.BrowserFetchTransport(fixture_origin="http://127.0.0.1")


def test_uninitialized_transport_fails_closed_and_closes():
    assert not bridge.runtime_ready()
    transport = bridge.BrowserFetchTransport()
    with pytest.raises(httpx.TransportError, match="runtime is not ready"):
        with httpx.Client(transport=transport, trust_env=False) as client:
            client.post(URL)
    assert transport.closed
