from __future__ import annotations

import json
import sqlite3

import pandas as pd
import pytest

from src.aggregation import LaunchGateConfig, evaluate_candidate
from src.domain import Role, WorkspaceContext
from src.product_analytics import record_event
from src.project_workspace import MAX_WORKSPACE_BYTES, export_project_workspace, restore_project_workspace
from src.security import AuthorizationError
from src.storage import EphemeralSQLiteRepository, SQLiteRepository
from src.versioning import text_hash, version_hash


@pytest.fixture(params=["disk", "memory"])
def project(tmp_path, request):
    repo = SQLiteRepository(tmp_path / "project.sqlite3") if request.param == "disk" else EphemeralSQLiteRepository()
    owner = repo.local_context()
    project_id = repo.create_project(owner, {"name": "Support release", "notes": "Private original material"})
    for index, text in enumerate(["Refund within 14 days.", "Refund within 30 days."]):
        repo.save_documents_and_chunks(
            owner,
            [{"filename": "policy.md", "text": text, "warnings": ["Review original layout."]}],
            [
                {
                    "filename": "policy.md",
                    "source_name": "policy.md",
                    "chunk_text": text,
                    "chunk_index": 0,
                    "chunk_id": f"passage-{index}",
                    "text_start": 0,
                    "text_end": len(text),
                }
            ],
            project_id,
        )
        repo.save_prompt(owner, project_id, "Current instructions", f"Use policy revision {index}.", "current")
        dataset_id = repo.create_dataset_version(
            owner,
            project_id,
            "Release cases",
            [
                {
                    "case_id": "refund",
                    "question": "Refund window?",
                    "expected_answer": text,
                    "expected_source": "policy.md",
                    "category": "policy",
                    "should_escalate": False,
                }
            ],
        )
    repo.create_target_version(
        owner,
        project_id,
        "Support API",
        "external_api",
        {
            "name": "Support API",
            "endpoint": "https://assistant.example.test/answer",
            "headers": {"X-Custom-Auth": "secret://ASSISTANT_TOKEN"},
            "request_template": {"question": "${question}"},
            "response_mappings": {"answer": "$.answer"},
        },
    )
    manifest = {
        "dataset": {"content_hash": version_hash([{"question": "Refund window?"}])},
        "target": {"type": "external_api"},
        "model": {"name": "observed-model"},
    }
    manifest["manifest_hash"] = version_hash(manifest)
    run_id = repo.create_run(
        owner,
        project_id=project_id,
        run_name="Baseline",
        model_name="observed-model",
        mode="batch",
        unique_case_count=1,
        total_executions=1,
        dataset_version_id=dataset_id,
        target_type="external_api",
        manifest=manifest,
        calibration_status="calibrated",
    )
    repo.save_result(
        owner,
        run_id,
        {
            "case_id": "refund",
            "question": "Refund window?",
            "expected_answer": "30 days.",
            "actual_answer": "30 days.",
            "execution_status": "passed",
            "target_type": "external_api",
            "prompt_name": "Current instructions",
            "model_name": "observed-model",
            "overall_score": 1.0,
            "calibration_status": "calibrated",
            "calibration_version": "declared-holdout",
            "prompt_version": text_hash("Use policy revision 1."),
            "target_version": "recorded-target",
            "metadata": {"execution": {"attempt_count": 1, "cache_hit": False}},
            "retrieved_chunks": [{"chunk_text": "Refund within 30 days.", "filename": "policy.md"}],
        },
    )
    record_event(repo, owner, "decision_recorded", "1" * 32, run_id=run_id, decision="hold", next_action="add_cases")
    yield repo, owner, project_id, manifest
    if isinstance(repo, EphemeralSQLiteRepository):
        repo.close()


def _change(raw, mutate):
    archive = json.loads(raw)
    mutate(archive["payload"])
    archive["payload_sha256"] = version_hash(archive["payload"])
    return json.dumps(archive).encode()


def test_full_project_roundtrip_preserves_versions_history_and_current_inputs(project):
    repo, context, project_id, manifest = project
    raw = export_project_workspace(repo, context, project_id)
    archive = json.loads(raw)
    assert len(archive["payload"]["documents"]) == 2
    assert len(archive["payload"]["prompts"]) == 2
    assert len(archive["payload"]["datasets"]) == 2
    assert "secret://" not in raw.decode()
    restored = restore_project_workspace(repo, context, raw)
    assert restored != project_id
    assert len(repo.list_projects(context)) == 2
    assert repo.load_chunks(context, restored)[0]["chunk_text"] == "Refund within 30 days."
    config = repo.load_project_configuration(context, restored)
    assert config["dataset_records"][0]["expected_answer"] == "Refund within 30 days."
    assert config["external_target_config"]["request_template"] == {"question": "${question}"}
    assert not config["external_target_config"].get("headers")
    restored_run = next(run for run in repo.list_runs(context) if run["project_id"] == restored)
    assert restored_run["mode"] == "imported_history"
    assert restored_run["calibration_status"] == "insufficiently_calibrated"
    assert restored_run["calibration_version"] is None
    stored_manifest = json.loads(restored_run["manifest_json"])
    assert stored_manifest["recorded_manifest"] == manifest
    assert stored_manifest["execution_verified"] is False
    results = repo.list_results(context, restored_run["id"])
    assert results[0]["actual_answer"] == "30 days."
    assert results[0]["metadata"]["imported_evidence"]["recorded_calibration_status"] == "calibrated"
    verdict = evaluate_candidate(pd.DataFrame(results), LaunchGateConfig(require_calibration=False))
    assert verdict["launch_blocked"] is True
    assert verdict["verdict"] == "Offline response review — no launch verdict"
    assert repo.latest_calibration(context) is None
    with repo.connection() as conn:
        decisions = conn.execute(
            "SELECT metadata_json FROM audit_logs WHERE action='project.imported_decision'"
        ).fetchall()
    assert len(decisions) == 1
    assert json.loads(decisions[0][0])["verified"] is False
    # A second export/restore retains the original recorded manifest and decision;
    # it does not recursively wrap provenance or claim another observed decision.
    second_raw = export_project_workspace(repo, context, restored)
    assert json.loads(second_raw)["payload"]["runs"][0]["recorded_manifest"] == manifest
    assert len(json.loads(second_raw)["payload"]["decisions"]) == 1
    second = restore_project_workspace(repo, context, second_raw)
    assert second not in {project_id, restored}


def test_imported_synthetic_history_stays_synthetic(project):
    repo, context, project_id, _ = project
    raw = _change(
        export_project_workspace(repo, context, project_id),
        lambda payload: payload["runs"][0].update(
            recorded_target_type="synthetic_mock",
            results=[{**payload["runs"][0]["results"][0], "target_type": "synthetic_mock"}],
        ),
    )
    restored = restore_project_workspace(repo, context, raw)
    run = next(run for run in repo.list_runs(context) if run["project_id"] == restored)
    result = pd.DataFrame(repo.list_results(context, run["id"]))
    assert evaluate_candidate(result)["verdict"] == "Synthetic demonstration — no launch verdict"


def test_export_cannot_read_another_workspace_and_viewer_cannot_restore(project):
    repo, context, project_id, _ = project
    raw = export_project_workspace(repo, context, project_id)
    foreign = repo.create_workspace("separate@example.test", "Separate")
    with pytest.raises(AuthorizationError):
        export_project_workspace(repo, foreign, project_id)
    viewer_id = repo.add_member(context, "viewer@example.test", Role.VIEWER)
    viewer = WorkspaceContext(viewer_id, context.workspace_id, Role.VIEWER)
    assert export_project_workspace(repo, viewer, project_id)
    with pytest.raises(AuthorizationError):
        restore_project_workspace(repo, viewer, raw)


def test_storage_failure_rolls_back_every_created_asset_and_audit(project, monkeypatch):
    repo, context, project_id, _ = project
    raw = export_project_workspace(repo, context, project_id)
    with repo.connection() as conn:
        previous = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in [
                "projects",
                "documents",
                "prompt_versions",
                "dataset_versions",
                "targets",
                "eval_runs",
                "audit_logs",
            ]
        }

    def fail(*args, **kwargs):
        raise RuntimeError("injected storage failure")

    monkeypatch.setattr(repo, "save_result", fail)
    with pytest.raises(RuntimeError, match="injected"):
        restore_project_workspace(repo, context, raw)
    with repo.connection() as conn:
        after = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in previous}
    assert after == previous
    assert repo.load_chunks(context, project_id)[0]["chunk_text"] == "Refund within 30 days."


@pytest.mark.parametrize(
    "invalid",
    [
        b"",
        b"not json",
        b"[]",
        b"null",
        b"SQLite format 3\0",
        b'{"schema":1,"schema":2}',
        b'{"a":NaN}',
        b'{"a":Infinity}',
    ],
)
def test_invalid_format_never_changes_project(project, invalid):
    repo, context, _, _ = project
    with pytest.raises(ValueError):
        restore_project_workspace(repo, context, invalid)
    assert len(repo.list_projects(context)) == 1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["prompts"][0].update(content="tampered"),
        lambda p: p["datasets"][0]["records"][0].update(question="tampered"),
        lambda p: p["documents"][0]["chunks"][0].update(chunk_text="tampered"),
        lambda p: p["documents"][0].update(filename="../escape.md"),
        lambda p: p["runs"][0].update(dataset_source_id=99999),
        lambda p: p["runs"][0].update(total_executions=-1),
        lambda p: p["runs"][0]["results"][0].update(actual_answer={"malformed": "value"}),
        lambda p: p["targets"][0]["configuration"].update(headers={"X-Custom": "opaque credential"}),
        lambda p: p["targets"][0]["configuration"].update(endpoint="https://user:pass@example.test/answer?key=opaque"),
        lambda p: p["targets"][0]["configuration"].update(api_key="short-key"),
        lambda p: p["targets"][0]["configuration"].update(extra="env://PRIVATE_KEY"),
        lambda p: p.update(unsupported=True),
    ],
)
def test_corrupt_or_credential_bearing_content_fails_before_mutation(project, mutate):
    repo, context, project_id, _ = project
    raw = _change(export_project_workspace(repo, context, project_id), mutate)
    with pytest.raises(ValueError):
        restore_project_workspace(repo, context, raw)
    assert len(repo.list_projects(context)) == 1


def test_envelope_checksum_and_size_limits(project):
    repo, context, project_id, _ = project
    archive = json.loads(export_project_workspace(repo, context, project_id))
    archive["payload"]["project"]["name"] = "Changed without checksum"
    with pytest.raises(ValueError, match="checksum"):
        restore_project_workspace(repo, context, json.dumps(archive).encode())
    with pytest.raises(ValueError, match="20 MiB"):
        restore_project_workspace(repo, context, b" " * (MAX_WORKSPACE_BYTES + 1))
    assert len(repo.list_projects(context)) == 1


def test_empty_project_roundtrip_and_no_network(project, monkeypatch):
    import socket

    repo, context, _, _ = project

    def forbid(*args, **kwargs):
        raise AssertionError("No network is permitted during restore")

    monkeypatch.setattr(socket, "getaddrinfo", forbid)
    empty = repo.create_project(context, {"name": "Empty"})
    restored = restore_project_workspace(repo, context, export_project_workspace(repo, context, empty))
    assert repo.load_chunks(context, restored) == []
    assert repo.load_project_configuration(context, restored)["dataset_records"] == []


def test_export_scrubs_unusual_credentials_from_nested_manifest_and_target(project):
    repo, context, project_id, _ = project
    # Direct fixture insertion represents legacy storage that predates safeguards.
    poisoned = {
        "endpoint": "https://user:opaque-password@example.test/a?private=opaque-query#opaque-fragment",
        "headers": {"X-Unusual": "opaque-header"},
        "environment_names": ["UNIQUE_ENV_NAME"],
        "secret_ref": "UNIQUE_REF",
        "request_template": {"question": "${question}", "api_key": "opaque-short-key"},
    }
    with repo.connection() as conn:
        conn.execute("UPDATE target_versions SET configuration_json=?", (json.dumps(poisoned),))
        conn.execute("UPDATE eval_runs SET manifest_json=?", (json.dumps({"target": poisoned}),))
    raw = export_project_workspace(repo, context, project_id)
    for secret in [
        "opaque-password",
        "opaque-query",
        "opaque-fragment",
        "opaque-header",
        "UNIQUE_ENV_NAME",
        "UNIQUE_REF",
        "opaque-short-key",
    ]:
        assert secret not in raw.decode()
    assert restore_project_workspace(repo, context, raw)


def test_repository_transaction_rollback_also_rolls_back_nested_calls(project):
    repo, context, _, _ = project
    with pytest.raises(sqlite3.IntegrityError):
        with repo.transaction():
            repo.create_project(context, {"name": "Must not survive"})
            with repo.connection() as conn:
                conn.execute(
                    "INSERT INTO memberships (user_id, workspace_id, role, created_at) VALUES (99999,99999,?,?)",
                    ("owner", "now"),
                )
    assert [row["name"] for row in repo.list_projects(context)] == ["Support release"]


@pytest.mark.parametrize(
    "kind",
    [
        "empty_case",
        "request_list",
        "response_list",
        "endpoint_http",
        "endpoint_private",
        "endpoint_userinfo",
        "bad_unicode",
    ],
)
def test_restore_rejects_cases_and_connection_settings_that_would_break_hosted_ui(project, monkeypatch, kind):
    from src import config

    repo, context, project_id, _ = project
    raw = export_project_workspace(repo, context, project_id)
    archive = json.loads(raw)
    payload = archive["payload"]
    if kind == "empty_case":
        payload["datasets"][0]["records"] = [{}]
        payload["datasets"][0]["content_hash"] = version_hash([{}])
    elif kind == "request_list":
        payload["targets"][0]["configuration"]["request_template"] = ["not a mapping"]
    elif kind == "response_list":
        payload["targets"][0]["configuration"]["response_mappings"] = ["not a mapping"]
    elif kind == "endpoint_http":
        payload["targets"][0]["configuration"]["endpoint"] = "http://127.0.0.1/answer"
    elif kind == "endpoint_private":
        payload["targets"][0]["configuration"]["endpoint"] = "https://192.168.1.1/answer"
    elif kind == "endpoint_userinfo":
        payload["targets"][0]["configuration"]["endpoint"] = "https://user:pass@example.test/answer"
    elif kind == "bad_unicode":
        # ASCII JSON can encode a lone surrogate that is not valid UTF-8 text.
        payload["project"]["notes"] = "\ud800"
        archive["payload_sha256"] = "untrusted"
        raw = json.dumps(archive, ensure_ascii=True).encode()
    if kind != "bad_unicode":
        archive["payload_sha256"] = version_hash(payload)
        raw = json.dumps(archive).encode()
    monkeypatch.setattr(config, "APP_ACCESS_MODE", "hosted-session")
    monkeypatch.setattr(config, "EXTERNAL_TARGET_ALLOW_PRIVATE", False, raising=False)
    with pytest.raises(ValueError):
        restore_project_workspace(repo, context, raw)
    assert len(repo.list_projects(context)) == 1


def test_complete_32_case_sample_can_be_exported_and_resumed(tmp_path):
    from src import database
    from src.evaluator import run_evaluation
    from src.sample_data import default_prompts, load_sample_documents, load_sample_eval_dataset

    repo = SQLiteRepository(tmp_path / "sample.sqlite3")
    context = repo.local_context()
    project_id = repo.create_project(context, {"name": "Fictional sample"})
    documents, chunks = load_sample_documents()
    repo.save_documents_and_chunks(context, documents, chunks, project_id)
    with database.request_scope(repo, context):
        result = run_evaluation(
            load_sample_eval_dataset(),
            repo.load_chunks(context, project_id),
            {"Current Prompt": default_prompts()["Current Prompt"]},
            "mock-model",
            3,
            0.05,
            3500,
            0.03,
            "sample",
            project_id=project_id,
            max_concurrency=1,
        )
    assert len(result) == 32
    restored_id = restore_project_workspace(repo, context, export_project_workspace(repo, context, project_id))
    restored_run = next(run for run in repo.list_runs(context) if run["project_id"] == restored_id)
    restored = pd.DataFrame(repo.list_results(context, restored_run["id"]))
    assert len(restored) == 32
    assert evaluate_candidate(restored)["verdict"] == "Synthetic demonstration — no launch verdict"
    assert len(repo.load_chunks(context, restored_id)) == len(chunks)
    assert (restored["execution_status"] != "passed").sum() == 3
    assert (restored["attempt_count"] == 0).all()


@pytest.mark.parametrize("usage_path", ["$.usage.input_tokens", ""])
def test_portable_target_preserves_valid_usage_mapping_paths(project, usage_path):
    repo, context, project_id, _ = project
    configuration = repo.load_project_configuration(context, project_id)["external_target_config"]
    configuration["response_mappings"].update(input_tokens=usage_path, output_tokens="$.usage.output_tokens")
    repo.create_target_version(context, project_id, "Support API", "external_api", configuration)
    raw = export_project_workspace(repo, context, project_id)
    restored = restore_project_workspace(repo, context, raw)
    mappings = repo.load_project_configuration(context, restored)["external_target_config"]["response_mappings"]
    assert mappings["input_tokens"] == usage_path
    assert mappings["output_tokens"] == "$.usage.output_tokens"


def test_source_identity_changes_if_export_removes_credential_like_text(project):
    repo, context, project_id, _ = project
    source = "Example api_key=sk-never-export-this-example-secret"
    original_hash = text_hash(source)
    repo.save_documents_and_chunks(
        context,
        [{"filename": "credential-note.md", "text": source}],
        [
            {
                "filename": "credential-note.md",
                "source_name": "credential-note.md",
                "chunk_text": source,
                "chunk_index": 0,
            }
        ],
        project_id,
    )
    raw = export_project_workspace(repo, context, project_id)
    document = next(doc for doc in json.loads(raw)["payload"]["documents"] if doc["filename"] == "credential-note.md")
    assert "sk-never-export-this-example-secret" not in raw.decode()
    assert document["content_hash"] != original_hash
    assert "source identity" in document["warnings"][-1]
    assert document["chunks"][0]["content_hash"] == text_hash(document["chunks"][0]["chunk_text"])
    assert restore_project_workspace(repo, context, raw)


def test_parallel_restore_is_rejected_before_decode_and_leaves_workspace_intact(project, monkeypatch):
    from src import project_workspace

    repo, context, project_id, _ = project
    raw = export_project_workspace(repo, context, project_id)
    with project_workspace._RESTORE_LOCK:

        def forbid_decode(*args, **kwargs):
            raise AssertionError("Busy restore must not allocate a decoded copy")

        with monkeypatch.context() as patch:
            patch.setattr(project_workspace.json, "loads", forbid_decode)
            with pytest.raises(ValueError, match="Another project"):
                restore_project_workspace(repo, context, raw)
    assert len(repo.list_projects(context)) == 1
    # A malformed file must release admission for the next valid restore too.
    with pytest.raises(ValueError):
        restore_project_workspace(repo, context, b"bad")
    assert restore_project_workspace(repo, context, raw) != project_id
