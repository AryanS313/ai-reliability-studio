"""Anonymous target checks are offline; no test connects to a target or resolver."""

from __future__ import annotations

import json
import socket
import ssl
import urllib.request
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from src import config
from src.domain import ExecutionStatus
from src.targets import ExternalHTTPTarget, ExternalTargetConfig, TargetConfigurationError, _secure_urlopen


@pytest.fixture(autouse=True)
def public_environment(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "public-session")
    monkeypatch.setattr(config, "APP_ENV", "public-demo")
    monkeypatch.setattr(config, "ALLOW_PRIVATE_EXTERNAL_TARGETS", True)
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ("assistant.example.test",))
    monkeypatch.setattr(socket, "getaddrinfo", MagicMock(side_effect=AssertionError("DNS must be stubbed explicitly")))


@pytest.mark.parametrize("environment", ["public-demo", "development", "production"])
def test_anonymous_mode_requires_https_and_host_allowlist_in_every_environment(monkeypatch, environment):
    monkeypatch.setattr(config, "APP_ENV", environment)
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ())
    with pytest.raises(TargetConfigurationError, match="HTTPS"):
        ExternalTargetConfig(name="local", endpoint="http://127.0.0.1:8501")
    with pytest.raises(TargetConfigurationError, match="ALLOWED_HOSTS"):
        ExternalTargetConfig(name="unlisted", endpoint="https://assistant.example.test")


@pytest.mark.parametrize("port", ["0", "65536", "not-a-port"])
def test_invalid_ports_are_configuration_errors(port):
    with pytest.raises(TargetConfigurationError, match="valid port"):
        ExternalTargetConfig(name="invalid-port", endpoint=f"https://assistant.example.test:{port}")


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "localhost",
        "[::1]",
        "[::ffff:127.0.0.1]",
        "[fe80::1]",
        "[fc00::1]",
        "169.254.169.254",
        "10.0.0.1",
        "100.64.0.1",
        "224.0.0.1",
        "[ff02::1]",
    ],
)
def test_anonymous_mode_rejects_nonpublic_literals_even_when_private_access_flag_is_set(monkeypatch, host):
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", (host.strip("[]"),))
    with pytest.raises(TargetConfigurationError, match="Private-network"):
        ExternalTargetConfig(name="private", endpoint=f"https://{host}")


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "169.254.169.254", "10.0.0.1", "::1", "::ffff:127.0.0.1", "fc00::1", "ff02::1", "100.64.0.1"],
)
@pytest.mark.parametrize("operation", ["execute", "health_check"])
def test_resolved_private_destinations_never_reach_opener(monkeypatch, address, operation):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
        ],
    )
    opener = MagicMock(side_effect=AssertionError("Private destination must never be contacted"))
    target = ExternalHTTPTarget(
        ExternalTargetConfig(
            name="fixture", endpoint="https://assistant.example.test/chat", health_check_path="health"
        ),
        opener=opener,
    )
    result = target.execute({"question": "Fixture"}) if operation == "execute" else target.health_check()
    assert result.status != ExecutionStatus.PASSED
    opener.assert_not_called()


class Response:
    def __init__(self, final_url, status=200):
        self.final_url = final_url
        self.status = status

    def geturl(self):
        return self.final_url

    def read(self, *_):
        return json.dumps({"answer": "Offline fixture"}).encode()


@pytest.mark.parametrize("operation", ["execute", "health_check"])
def test_allowlisted_public_destination_works_with_stubbed_network(monkeypatch, operation):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    )
    target = ExternalHTTPTarget(
        ExternalTargetConfig(
            name="fixture", endpoint="https://assistant.example.test/chat", health_check_path="health"
        ),
        opener=lambda request, **kwargs: Response(request.full_url),
    )
    result = target.execute({"question": "Fixture"}) if operation == "execute" else target.health_check()
    assert result.status == ExecutionStatus.PASSED


@pytest.mark.parametrize("operation", ["execute", "health_check"])
@pytest.mark.parametrize(
    "destination", ["https://127.0.0.1/secret", "https://[::1]/secret", "https://other.example.test/chat"]
)
def test_redirected_responses_are_rejected_including_private_ipv6(monkeypatch, operation, destination):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    )
    target = ExternalHTTPTarget(
        ExternalTargetConfig(
            name="fixture", endpoint="https://assistant.example.test/chat", health_check_path="health"
        ),
        opener=lambda *a, **k: Response(destination),
    )
    result = target.execute({"question": "Fixture"}) if operation == "execute" else target.health_check()
    assert result.error_code == "external_redirect_blocked"


def test_single_user_development_can_still_use_local_test_servers(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "single-user")
    monkeypatch.setattr(config, "APP_ENV", "development")
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ())
    target = ExternalHTTPTarget(
        ExternalTargetConfig(name="local", endpoint="http://127.0.0.1:9999"),
        opener=lambda request, **kwargs: Response(request.full_url),
    )
    assert target.execute({"question": "Fixture"}).status == ExecutionStatus.PASSED


class OfflineSocket:
    def __init__(self, family, kind, protocol, *, status=200, location=None):
        self.family = family
        self.connected = None
        self.closed = False
        self.sent = b""
        self.timeout = None
        body = b'{"answer":"Offline fixture"}'
        headers = f"HTTP/1.1 {status} Fixture\r\nContent-Length: {len(body)}\r\n"
        if location:
            headers += f"Location: {location}\r\n"
        self.response = headers.encode() + b"\r\n" + body

    def connect(self, sockaddr):
        self.connected = sockaddr

    def settimeout(self, timeout):
        self.timeout = timeout

    def sendall(self, data):
        self.sent += bytes(data)

    def makefile(self, *args, **kwargs):
        return BytesIO(self.response)

    def close(self):
        self.closed = True


def offline_sockets(monkeypatch, *, status=200, location=None, certificate_error=False, connect_error=False):
    sockets = []
    tls_settings = []

    def create(family, kind, protocol):
        sock = OfflineSocket(family, kind, protocol, status=status, location=location)
        if connect_error:

            def fail(address):
                raise TimeoutError("Offline connection timeout")

            sock.connect = fail
        sockets.append(sock)
        return sock

    def tls(context, sock, *, server_hostname):
        tls_settings.append((context.check_hostname, context.verify_mode, server_hostname))
        if certificate_error:
            raise ssl.SSLCertVerificationError("Offline certificate rejection")
        return sock

    monkeypatch.setattr(socket, "socket", create)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", tls)
    return sockets, tls_settings


@pytest.mark.parametrize(
    "family,address",
    [
        (socket.AF_INET, ("8.8.8.8", 443)),
        (socket.AF_INET6, ("2606:4700:4700::1111", 443, 0, 0)),
    ],
)
def test_protected_connection_pins_validated_ip_without_reresolving_and_preserves_tls_host(
    monkeypatch, family, address
):
    resolutions = []

    def resolve(host, port, **kwargs):
        resolutions.append(host)
        # A second lookup would return an internal service (DNS rebinding).
        destination = address if len(resolutions) == 1 else ("127.0.0.1", port)
        return [(family, socket.SOCK_STREAM, 6, "", destination)]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setenv("HTTPS_PROXY", "http://owner-proxy.invalid:8080")
    monkeypatch.setenv("ALL_PROXY", "http://owner-proxy.invalid:8080")
    sockets, tls_settings = offline_sockets(monkeypatch)
    request = urllib.request.Request(
        "https://assistant.example.test/chat",
        headers={
            "Authorization": "Bearer visitor-fixture",
            "Host": "unapproved.invalid",
            "Proxy-Authorization": "Basic owner-fixture",
        },
    )
    response = _secure_urlopen(request, timeout=12)
    try:
        assert json.loads(response.read())["answer"] == "Offline fixture"
    finally:
        response.close()
    assert resolutions == ["assistant.example.test"]
    assert len(sockets) == 1
    assert sockets[0].connected == address
    assert sockets[0].timeout == 12
    assert sockets[0].closed
    assert tls_settings == [(True, ssl.CERT_REQUIRED, "assistant.example.test")]
    assert b"Host: assistant.example.test\r\n" in sockets[0].sent
    assert b"Authorization: Bearer visitor-fixture\r\n" in sockets[0].sent
    assert b"owner-fixture" not in sockets[0].sent
    assert b"unapproved.invalid" not in sockets[0].sent
    assert b"CONNECT " not in sockets[0].sent


@pytest.mark.parametrize("operation", ["execute", "health_check"])
def test_dns_change_to_private_between_preflight_and_connection_is_blocked(monkeypatch, operation):
    attempts = []

    def resolve(*args, **kwargs):
        attempts.append(1)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8" if len(attempts) == 1 else "127.0.0.1", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    sockets, tls_settings = offline_sockets(monkeypatch)
    target = ExternalHTTPTarget(
        ExternalTargetConfig(
            name="fixture",
            endpoint="https://assistant.example.test/chat",
            health_check_path="health",
        )
    )
    result = target.execute({"question": "Fixture"}) if operation == "execute" else target.health_check()
    assert result.status != ExecutionStatus.PASSED
    assert not sockets
    assert not tls_settings


@pytest.mark.parametrize("operation", ["execute", "health_check"])
@pytest.mark.parametrize("failure", [None, "certificate", "timeout", "redirect"])
def test_real_protected_opener_success_and_failures_close_resources(monkeypatch, operation, failure):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    )
    sockets, tls_settings = offline_sockets(
        monkeypatch,
        status=307 if failure == "redirect" else 200,
        location="https://127.0.0.1/private" if failure == "redirect" else None,
        certificate_error=failure == "certificate",
        connect_error=failure == "timeout",
    )
    target = ExternalHTTPTarget(
        ExternalTargetConfig(
            name="fixture",
            endpoint="https://assistant.example.test/chat",
            health_check_path="health",
        )
    )
    result = target.execute({"question": "Fixture"}) if operation == "execute" else target.health_check()
    assert len(sockets) == 1
    assert sockets[0].closed
    if failure is None:
        assert result.status == ExecutionStatus.PASSED
        assert tls_settings == [(True, ssl.CERT_REQUIRED, "assistant.example.test")]
    else:
        assert result.status != ExecutionStatus.PASSED
    if failure == "timeout" and operation == "execute":
        assert result.status == ExecutionStatus.TIMED_OUT


def test_production_authenticated_mode_also_pins_addresses_and_disables_proxy(monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "signed-token")
    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    )
    monkeypatch.setenv("HTTPS_PROXY", "http://owner-proxy.invalid:8080")
    sockets, _ = offline_sockets(monkeypatch)
    target = ExternalHTTPTarget(ExternalTargetConfig(name="fixture", endpoint="https://assistant.example.test/chat"))
    assert target.execute({"question": "Fixture"}).status == ExecutionStatus.PASSED
    assert sockets[0].connected == ("8.8.8.8", 443)
    assert sockets[0].closed
