from __future__ import annotations

import json
import uuid

import pytest

from src.domain import Role, WorkspaceContext
from src.product_analytics import record_event, validate_event
from src.security import AuthorizationError
from src.storage import SQLiteRepository


def _events(repository):
    with repository.connection() as connection:
        return [
            dict(row)
            for row in connection.execute("SELECT * FROM audit_logs WHERE action LIKE 'product.%' ORDER BY id")
        ]


@pytest.mark.parametrize(
    "properties",
    [
        {"prompt": "sensitive prompt"},
        {"answer": "sensitive answer"},
        {"document_text": "private source"},
        {"filename": "private-document.txt"},
        {"api_key": "sk-fixture-secret"},
        {"endpoint": "https://private.example.test"},
        {"email": "person@example.test"},
        {"user_id": 123},
        {"project_name": "Customer project"},
        {"error": "secret provider response"},
        {"mode": "person@example.test"},
        {"mode": {"local": "private content"}},
        {"case_count": "32"},
        {"case_count": True},
        {"case_count": -1},
        {"case_count": 10_000_001},
        {"synthetic": "true"},
        {"synthetic": 1},
        {"duration_ms": float("nan")},
        {"duration_ms": float("inf")},
        {"duration_ms": -1},
        {"duration_ms": 86_400_001},
        {"duration_ms": True},
        {"target_type": "external_http"},
        {"schema_version": 2},
    ],
)
def test_analytics_rejects_payloads_unknown_fields_and_invalid_numeric_values(tmp_path, properties):
    repository = SQLiteRepository(tmp_path / "analytics.sqlite3")
    context = repository.local_context()
    with pytest.raises(ValueError):
        record_event(repository, context, "run_completed", uuid.uuid4().hex, **properties)
    assert _events(repository) == []


@pytest.mark.parametrize("session_id", ["", "person@example.test", "a" * 31, "A" * 32, "0" * 33])
def test_analytics_requires_random_session_identifier_shape(session_id):
    with pytest.raises(ValueError):
        validate_event("session_started", session_id, {"mode": "local"})


def test_hosted_session_start_uses_only_allowlisted_operational_mode():
    payload = validate_event("session_started", uuid.uuid4().hex, {"mode": "hosted-session"})
    assert payload["mode"] == "hosted-session"


def test_analytics_stores_only_approved_operational_fields_with_authorization_scope(tmp_path):
    repository = SQLiteRepository(tmp_path / "analytics.sqlite3")
    first = repository.create_workspace("first@example.test", "First private workspace")
    second = repository.create_workspace("second@example.test", "Second private workspace")
    session_id = uuid.uuid4().hex
    record_event(
        repository,
        first,
        "run_completed",
        session_id,
        target_type="external_api",
        outcome="partial",
        synthetic=False,
        execution_count=32,
        scored_count=30,
        error_count=2,
        duration_ms=1500.25,
    )
    record_event(repository, second, "session_started", uuid.uuid4().hex, mode="local")
    rows = _events(repository)
    assert [row["workspace_id"] for row in rows] == [first.workspace_id, second.workspace_id]
    payload = json.loads(rows[0]["metadata_json"])
    assert payload == {
        "schema_version": 1,
        "journey_id": session_id,
        "target_type": "external_api",
        "outcome": "partial",
        "synthetic": False,
        "execution_count": 32,
        "scored_count": 30,
        "error_count": 2,
        "duration_ms": 1500.25,
    }
    assert "first@example.test" not in json.dumps(payload)
    assert "First private workspace" not in json.dumps(payload)
    forged = WorkspaceContext(first.user_id, second.workspace_id, Role.OWNER)
    with pytest.raises(AuthorizationError):
        record_event(repository, forged, "session_started", uuid.uuid4().hex, mode="local")
    assert len(_events(repository)) == 2


def test_analytics_rejects_unregistered_events():
    with pytest.raises(ValueError):
        validate_event("answer_logged", uuid.uuid4().hex, {})


def test_analytics_identifier_cannot_be_overridden_through_properties():
    with pytest.raises(ValueError):
        validate_event("session_started", uuid.uuid4().hex, {"session_id": "0" * 32})
    with pytest.raises(ValueError):
        validate_event("session_started", uuid.uuid4().hex, {"journey_id": "0" * 32})
