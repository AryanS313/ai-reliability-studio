from __future__ import annotations

import json

import pytest

from src import config
from src.domain import ExecutionStatus
from src.targets import (
    ExternalHTTPTarget,
    ExternalTargetConfig,
    FoundationModelConfig,
    SecretResolver,
    TargetConfigurationError,
    target_configuration_for_storage,
)


@pytest.fixture(autouse=True)
def local_access(monkeypatch):
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "local")


@pytest.mark.parametrize(
    "changes",
    [
        {"endpoint": "https://example.test:bad"},
        {"endpoint": "https://example.test/?token=short-secret"},
        {"endpoint": "https://example.test/#secret"},
        {"headers": {"Authorization": "short-secret"}},
        {"headers": {"X-Api-Key": "short-secret"}},
        {"headers": {"Cookie": "short-secret"}},
        {"headers": {"Host": "another.example"}},
        {"headers": {"Content-Length": "4"}},
        {"headers": {"X-Invalid": "hello\r\nInjected: true"}},
        {"headers": {"Bad Header": "hello"}},
        {"headers": {"X-Invalid": 123}},
        {"headers": []},
        {"request_template": {"api_key": "short-secret"}},
        {"request_template": []},
        {"response_mappings": {"answer": "response.answer"}},
        {"response_mappings": []},
        {"health_check_path": "https://other.example/health"},
        {"health_check_path": "//other.example/health"},
        {"health_check_path": "health?token=raw"},
        {"retry_count": 11},
        {"timeout_seconds": "fast"},
        {"method": 7},
    ],
)
def test_malformed_or_sensitive_target_configuration_is_rejected_before_network(changes):
    with pytest.raises(TargetConfigurationError):
        ExternalTargetConfig(**{"name": "Target", "endpoint": "https://example.test", **changes})


def test_usage_token_fields_do_not_get_mistaken_for_credentials():
    foundation = FoundationModelConfig("openai", "example-model", "secret://KEY", max_tokens=256)
    assert target_configuration_for_storage(foundation)["max_tokens"] == 256
    external = ExternalTargetConfig(
        name="Assistant",
        endpoint="https://example.test/chat",
        request_template={"input": "${question}", "max_tokens": 256},
        response_mappings={"answer": "$.answer", "input_tokens": "$.usage.input", "output_tokens": "$.usage.output"},
    )
    assert target_configuration_for_storage(external)["response_mappings"]["input_tokens"] == "$.usage.input"


def test_secret_reference_cannot_extract_an_arbitrary_server_environment_variable(monkeypatch):
    monkeypatch.setenv("PRIVATE_DATABASE_PASSWORD", "must-not-leave-server")
    with pytest.raises(TargetConfigurationError):
        SecretResolver().resolve("secret://PRIVATE_DATABASE_PASSWORD")
    assert SecretResolver(environment_names=("PRIVATE_DATABASE_PASSWORD",)).resolve(
        "secret://PRIVATE_DATABASE_PASSWORD"
    )
    with pytest.raises(TargetConfigurationError):
        SecretResolver({"BAD-NAME": "value"}).resolve("secret://BAD-NAME")


def test_health_check_does_not_claim_success_without_a_real_check():
    target = ExternalHTTPTarget(ExternalTargetConfig(name="Assistant", endpoint="https://example.test/chat"))
    result = target.health_check()
    assert result.status == ExecutionStatus.PENDING
    assert result.metadata == {"health": "not_checked", "network_checked": False}
    assert result.error_code == "health_check_not_configured"


def test_health_checks_apply_dns_safety_before_sending_credentials(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ("example.test",))
    monkeypatch.setattr("src.targets.socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("10.1.2.3", 443))])
    target = ExternalHTTPTarget(
        ExternalTargetConfig(name="Assistant", endpoint="https://example.test", health_check_path="health"),
        opener=lambda *args, **kwargs: pytest.fail("Private health-check host must not be contacted"),
    )
    assert target.health_check().status == ExecutionStatus.FAILED


def test_real_transport_pins_a_validated_ip_and_keeps_original_hostname(monkeypatch):
    from test_public_target_network import offline_sockets

    dns_calls = []

    def resolve(*args, **kwargs):
        dns_calls.append(args)
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    monkeypatch.setattr("src.targets.socket.getaddrinfo", resolve)
    monkeypatch.setenv("HTTPS_PROXY", "https://malicious.example")
    sockets, tls = offline_sockets(monkeypatch)
    target = ExternalHTTPTarget(ExternalTargetConfig(name="Assistant", endpoint="https://example.test/chat"))
    assert target.execute({"question": "hello"}).status == ExecutionStatus.PASSED
    assert len(dns_calls) == 1
    assert len(sockets) == 1 and sockets[0].connected == ("93.184.216.34", 443)
    assert b"Host: example.test" in sockets[0].sent
    assert tls[0][2] == "example.test"
    assert sockets[0].closed


def test_public_demo_refuses_external_execution_and_health_before_network(monkeypatch):
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOWED_HOSTS", ("example.test",))
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "public-demo")
    monkeypatch.setattr("src.targets.socket.getaddrinfo", lambda *args, **kwargs: pytest.fail("No public-demo DNS"))
    target = ExternalHTTPTarget(
        ExternalTargetConfig(name="Assistant", endpoint="https://example.test", health_check_path="health"),
        opener=lambda *args, **kwargs: pytest.fail("No public-demo external call"),
    )
    assert target.execute({"question": "private"}).error_code == "public_demo_external_disabled"
    assert target.health_check().error_code == "public_demo_external_disabled"


@pytest.mark.parametrize(
    ("path", "expected"), [("/health", "https://example.test/health"), ("health", "https://example.test/api/health")]
)
def test_health_path_has_standard_url_semantics(path, expected):
    from types import SimpleNamespace

    captured = []

    def opener(request, timeout):
        captured.append(request.full_url)
        return SimpleNamespace(status=200)

    target = ExternalHTTPTarget(
        ExternalTargetConfig(name="Assistant", endpoint="https://example.test/api/answer", health_check_path=path),
        opener=opener,
    )
    assert target.health_check().status == ExecutionStatus.PASSED
    assert captured == [expected]


def test_private_dns_is_blocked_in_real_local_transport_before_any_socket(monkeypatch):
    monkeypatch.setattr("src.targets.socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("10.1.2.3", 443))])
    monkeypatch.setattr(
        "src.targets.socket.create_connection", lambda *args, **kwargs: pytest.fail("No private-network socket")
    )
    target = ExternalHTTPTarget(ExternalTargetConfig(name="Assistant", endpoint="https://example.test/chat"))
    assert target.execute({"question": "hello"}).error_code == "external_destination_blocked"


def test_target_echo_of_runtime_credential_is_discarded_before_persistence():
    from types import SimpleNamespace

    secret = "unusual-short-key"
    target = ExternalHTTPTarget(
        ExternalTargetConfig(
            name="Assistant", endpoint="https://example.test", headers={"Authorization": "secret://KEY"}
        ),
        SecretResolver({"KEY": f"Bearer {secret}"}),
        opener=lambda *args, **kwargs: SimpleNamespace(
            status=200, read=lambda size: json.dumps({"answer": f"Your key is {secret}"}).encode()
        ),
    )
    response = target.execute({"question": "hello"})
    assert response.status == ExecutionStatus.INVALID_RESPONSE
    assert response.error_code == "credential_in_target_response"
    assert response.answer == ""
    assert secret not in str(response)
    assert response.metadata["quality_score_eligible"] is False


@pytest.mark.parametrize(
    "endpoint", ["https://10.0.0.1/answer", "https://169.254.169.254/latest", "https://100.64.0.1/answer"]
)
def test_literal_private_destinations_are_rejected_during_configuration(endpoint, monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "development")
    monkeypatch.setattr(config, "ALLOW_PRIVATE_EXTERNAL_TARGETS", False)
    with pytest.raises(TargetConfigurationError, match="operator approval"):
        ExternalTargetConfig(name="Unsafe network", endpoint=endpoint)
    monkeypatch.setattr(config, "ALLOW_PRIVATE_EXTERNAL_TARGETS", True)
    assert ExternalTargetConfig(name="Operator-approved network", endpoint=endpoint).endpoint == endpoint


def test_local_loopback_assistant_remains_available_for_private_development(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "development")
    monkeypatch.setattr(config, "ALLOW_PRIVATE_EXTERNAL_TARGETS", False)
    assert ExternalTargetConfig(name="Local assistant", endpoint="http://127.0.0.1:8877/answer").endpoint
