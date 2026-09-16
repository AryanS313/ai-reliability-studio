"""Private project downloads with unverified history and omitted credential fields.

Checksums detect corruption, not authorship. Restored runs cannot establish live
execution or qualifying calibration. This is JSON, never an uploaded database.
"""

from __future__ import annotations

import json
import math
import re
import threading
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pandas as pd

from src.datasets import normalize_dataset_frame
from src.domain import Role, WorkspaceContext
from src.security import AuthorizationError, redact_secrets, sanitize_filename
from src.storage import PostgresRepository, Repository, SQLiteRepository
from src.targets import ExternalTargetConfig
from src.versioning import canonical_json, text_hash, version_hash

SCHEMA = "project-workspace-v1"
MAX_WORKSPACE_BYTES = 20 * 1024 * 1024
MAX_ITEMS = 20_000
_RESTORE_LOCK = threading.Lock()
IMPORT_NOTICE = (
    "Imported history — execution not independently verified. Recorded results are retained for review, "
    "not a new live run or qualifying calibration. Re-enter credentials and authorize each new run."
)
_SECTIONS = {"project", "documents", "prompts", "datasets", "targets", "runs", "decisions"}
_ID_FIELDS = {"workspace_id", "user_id", "created_by", "auth_subject"}
_SECRET_FIELD = re.compile(r"secret|credential|password|authorization|api.?key|environment.?ref", re.I)
_REFERENCE = re.compile(r"(?:secret|env|environment)://[A-Za-z0-9_.-]+|\$\{[A-Z][A-Z0-9_]*\}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_RESULT_JSON = {
    "retrieved_sources",
    "retrieved_chunks",
    "citation_details",
    "claim_assessments",
    "failure_labels",
    "failure_reason_codes",
    "failure_evidence",
    "score_explanation",
    "tags",
}


def _repository(repository: Repository) -> SQLiteRepository | PostgresRepository:
    if not isinstance(repository, SQLiteRepository | PostgresRepository):
        raise ValueError("This repository does not support portable project files.")
    return repository


def _rows(repository: Any, context: WorkspaceContext, query: str, *params: Any) -> list[dict[str, Any]]:
    with repository.connection() as connection:
        if isinstance(repository, PostgresRepository):
            repository._scope(connection, context)
            query = query.replace("?", "%s")
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def _json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        mappings = value.get("response_mappings")
        safe_mappings = isinstance(mappings, dict) and all(
            isinstance(path, str) and (not path or re.fullmatch(r"\$(?:\.[A-Za-z0-9_-]+(?:\[\d+\])?)*", path))
            for path in mappings.values()
        )
        for key, item in value.items():
            if (
                key in _ID_FIELDS
                or _SECRET_FIELD.search(key)
                or key.lower() in {"headers", "cookies", "environment_names"}
            ):
                continue
            if key.lower() in {"url", "endpoint", "base_url", "endpoint_url"} and isinstance(item, str):
                item = _portable_url(item)
            if key == "response_mappings" and isinstance(mappings, dict) and safe_mappings:
                # A validated $.usage.input_tokens path (or a disabled optional
                # path) is an extraction instruction, never a credential value.
                cleaned[key] = dict(mappings)
                continue
            item = _json(item) if key.endswith("_json") else item
            probe = None if isinstance(item, dict | list) else item
            redacted = redact_secrets({key: probe}, preserve_references=False)[key]
            cleaned[key] = _safe(redacted if redacted != probe else item)
        return cleaned
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, str):
        return _REFERENCE.sub("[REMOVED_CREDENTIAL_REFERENCE]", redact_secrets(value, preserve_references=False))
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _portable_url(value: str) -> str:
    endpoint = urlsplit(value)
    if endpoint.scheme not in {"http", "https"} or not endpoint.hostname:
        raise ValueError("Project contains an invalid assistant address.")
    hostname = f"[{endpoint.hostname}]" if ":" in endpoint.hostname else endpoint.hostname
    netloc = hostname + (f":{endpoint.port}" if endpoint.port else "")
    return urlunsplit((endpoint.scheme, netloc, endpoint.path, "", ""))


def _target_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    # Opaque custom headers can be credentials. Always re-enter them on restore.
    safe = _safe(configuration)
    safe.pop("version_hash", None)
    if isinstance(safe.get("endpoint"), str):
        safe["endpoint"] = _portable_url(safe["endpoint"])
    return safe


def _bounded(value: Any, depth: int = 0, budget: list[int] | None = None) -> None:
    if budget is None:
        budget = [200_000]
    budget[0] -= 1
    if budget[0] < 0 or depth > 24:
        raise ValueError("Project file is too complex.")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 512:
                raise ValueError("Project contains an invalid field name.")
            _bounded(item, depth + 1, budget)
    elif isinstance(value, list):
        if len(value) > MAX_ITEMS:
            raise ValueError("Project contains too many records.")
        for item in value:
            _bounded(item, depth + 1, budget)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Project contains an invalid number.")
    elif isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Project contains invalid Unicode text.") from exc
    elif value is not None and not isinstance(value, str | int | float | bool):
        raise ValueError("Project contains unsupported data.")


def _object(value: Any, fields: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or (fields is not None and set(value) != fields):
        raise ValueError("Project contains missing or unsupported fields.")
    return value


def _text(value: Any, *, nonempty: bool = False) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ValueError("Project contains an invalid text field.")
    return value


def _integer(value: Any, *, minimum: int = 0, maximum: int = MAX_ITEMS) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Project contains an invalid record count or identifier.")
    return value


def _validate(payload: dict[str, Any]) -> None:
    _object(payload, _SECTIONS)
    project = _object(payload["project"], {"name", "use_case", "industry", "notes"})
    for field, value in project.items():
        _text(value, nonempty=field == "name")
    for section in _SECTIONS - {"project"}:
        if not isinstance(payload[section], list) or len(payload[section]) > MAX_ITEMS:
            raise ValueError("Project contains an invalid record collection.")
    for document in payload["documents"]:
        _object(document, {"filename", "version", "content_hash", "text_preview", "warnings", "chunks"})
        filename = _text(document["filename"], nonempty=True)
        if filename != sanitize_filename(filename):
            raise ValueError("Project contains an unsafe source filename.")
        _integer(document["version"], minimum=1)
        if not isinstance(document["content_hash"], str) or not _DIGEST.fullmatch(document["content_hash"]):
            raise ValueError("Project contains an invalid content checksum.")
        _text(document["text_preview"])
        if not isinstance(document["warnings"], list) or not isinstance(document["chunks"], list):
            raise ValueError("Project contains invalid source records.")
        for chunk in document["chunks"]:
            _object(
                chunk,
                {
                    "source_name",
                    "chunk_text",
                    "chunk_index",
                    "chunk_id",
                    "page",
                    "section",
                    "text_start",
                    "text_end",
                    "content_hash",
                },
            )
            for name in ("source_name", "chunk_text", "chunk_id"):
                _text(chunk[name])
            _integer(chunk["chunk_index"])
            if chunk["content_hash"] != text_hash(chunk["chunk_text"]):
                raise ValueError("Source passage checksum does not match its content.")
            for name in ("page", "text_start", "text_end"):
                if chunk[name] is not None:
                    _integer(chunk[name], maximum=MAX_WORKSPACE_BYTES)
            if chunk["section"] is not None:
                _text(chunk["section"])
    for prompt in payload["prompts"]:
        _object(prompt, {"name", "type", "version", "content", "content_hash", "explanation", "motivated_by_failures"})
        for name in ("name", "type", "content", "explanation"):
            _text(prompt[name])
        _integer(prompt["version"], minimum=1)
        if prompt["content_hash"] != text_hash(prompt["content"]):
            raise ValueError("Instruction checksum does not match its content.")
        if not isinstance(prompt["motivated_by_failures"], list) or any(
            not isinstance(item, str) for item in prompt["motivated_by_failures"]
        ):
            raise ValueError("Project contains invalid instruction notes.")
    dataset_ids = set()
    for dataset in payload["datasets"]:
        _object(dataset, {"source_id", "name", "version", "records", "content_hash"})
        _integer(dataset["source_id"], minimum=1, maximum=2**53)
        if dataset["source_id"] in dataset_ids:
            raise ValueError("Project repeats a dataset identifier.")
        dataset_ids.add(dataset["source_id"])
        _integer(dataset["version"], minimum=1)
        _text(dataset["name"], nonempty=True)
        if not isinstance(dataset["records"], list) or any(not isinstance(row, dict) for row in dataset["records"]):
            raise ValueError("Project contains invalid evaluation cases.")
        if dataset["content_hash"] != version_hash(dataset["records"]):
            raise ValueError("Case checksum does not match its content.")
        try:
            normalize_dataset_frame(pd.DataFrame.from_records(dataset["records"]))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ValueError("Project cases do not satisfy the evaluation dataset format.") from exc
    for target in payload["targets"]:
        _object(target, {"name", "target_type", "version", "configuration"})
        _text(target["name"], nonempty=True)
        _integer(target["version"], minimum=1)
        if not isinstance(target["target_type"], str) or target["target_type"] not in {
            "synthetic_mock",
            "foundation_model",
            "external_api",
        }:
            raise ValueError("Project contains an unsupported assistant type.")
        configuration = _object(target["configuration"])
        if _target_configuration(configuration) != configuration:
            raise ValueError("Assistant configuration must omit credentials, headers and URL parameters.")
        if target["target_type"] == "external_api":
            try:
                ExternalTargetConfig(**{**configuration, "name": target["name"]})
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError("Project assistant settings do not satisfy the current connection policy.") from exc
    run_ids = set()
    for run in payload["runs"]:
        _object(
            run,
            {
                "source_id",
                "name",
                "model",
                "mode",
                "recorded_target_type",
                "timestamp",
                "dataset_source_id",
                "unique_case_count",
                "total_executions",
                "recorded_manifest",
                "results",
            },
        )
        _integer(run["source_id"], minimum=1, maximum=2**53)
        if run["source_id"] in run_ids:
            raise ValueError("Project repeats an evaluation identifier.")
        run_ids.add(run["source_id"])
        for name in ("name", "model", "mode", "timestamp"):
            _text(run[name])
        if not isinstance(run["recorded_target_type"], str) or run["recorded_target_type"] not in {
            "synthetic_mock",
            "foundation_model",
            "external_api",
            "saved_responses",
        }:
            raise ValueError("Project contains an invalid recorded assistant type.")
        for name in ("unique_case_count", "total_executions"):
            _integer(run[name])
        if run["dataset_source_id"] is not None:
            _integer(run["dataset_source_id"], minimum=1, maximum=2**53)
            if run["dataset_source_id"] not in dataset_ids:
                raise ValueError("Evaluation refers to missing cases.")
        _object(run["recorded_manifest"])
        if not isinstance(run["results"], list) or len(run["results"]) > run["total_executions"]:
            raise ValueError("Project contains an invalid evaluation result collection.")
        for result in run["results"]:
            _object(result)
            _text(result.get("question"))
            for name in ("expected_answer", "actual_answer", "case_id", "prompt_name", "model_name"):
                if result.get(name) is not None:
                    _text(result[name])
            structured = {
                "metadata",
                "retrieved_sources",
                "retrieved_chunks",
                "citation_details",
                "claim_assessments",
                "failure_labels",
                "failure_reason_codes",
                "failure_evidence",
                "score_explanation",
                "tags",
                "retrieval_metrics",
            }
            for name, value in result.items():
                if isinstance(value, dict | list) and name not in structured and not name.endswith("_json"):
                    raise ValueError("Project contains an invalid result field.")
            if result.get("metadata") is not None:
                _object(result["metadata"])
    for decision in payload["decisions"]:
        _object(decision, {"run_source_id", "decision", "next_action", "recorded_at"})
        _integer(decision["run_source_id"], minimum=1, maximum=2**53)
        if decision["run_source_id"] not in run_ids:
            raise ValueError("Decision refers to a missing evaluation.")
        if not isinstance(decision["decision"], str) or decision["decision"] not in {
            "hold",
            "investigate",
            "internal_test",
            "controlled_beta",
        }:
            raise ValueError("Project contains an invalid decision.")
        if not isinstance(decision["next_action"], str) or decision["next_action"] not in {
            "fix_prompt",
            "fix_sources",
            "fix_target",
            "add_cases",
            "human_review",
            "rerun",
        }:
            raise ValueError("Project contains an invalid next action.")
        _text(decision["recorded_at"])


def export_project_workspace(repository: Repository, context: WorkspaceContext, project_id: int) -> bytes:
    repo = _repository(repository)
    repo.authorize(context, Role.VIEWER)
    with repo.transaction():
        projects = [row for row in repo.list_projects(context) if row["id"] == project_id]
        if not projects:
            raise AuthorizationError("Project is not in this workspace.")
        payload: dict[str, Any] = {
            "project": {key: str(projects[0].get(key) or "") for key in ("name", "use_case", "industry", "notes")},
            "documents": [],
            "prompts": [],
            "datasets": [],
            "targets": [],
            "runs": [],
            "decisions": [],
        }
        for row in _rows(
            repo,
            context,
            "SELECT dv.*, d.safe_filename FROM document_versions dv JOIN documents d ON d.id=dv.document_id WHERE dv.workspace_id=? AND d.workspace_id=? AND d.project_id=? ORDER BY dv.id",
            context.workspace_id,
            context.workspace_id,
            project_id,
        ):
            chunks = _rows(
                repo,
                context,
                "SELECT source_name, chunk_text, chunk_index, chunk_id, page, section, text_start, text_end, content_hash FROM chunks WHERE workspace_id=? AND document_version_id=? ORDER BY id",
                context.workspace_id,
                row["id"],
            )
            payload["documents"].append(
                {
                    "filename": row["safe_filename"],
                    "version": row["version"],
                    "content_hash": row["content_hash"],
                    "text_preview": row["text_preview"] or "",
                    "warnings": _json(row["extraction_warnings"]),
                    "chunks": chunks,
                }
            )
        for row in _rows(
            repo,
            context,
            "SELECT pv.*, p.prompt_name, p.prompt_type FROM prompt_versions pv JOIN prompts p ON p.id=pv.prompt_id WHERE pv.workspace_id=? AND p.workspace_id=? AND p.project_id=? ORDER BY pv.id",
            context.workspace_id,
            context.workspace_id,
            project_id,
        ):
            payload["prompts"].append(
                {
                    "name": row["prompt_name"],
                    "type": row["prompt_type"],
                    "version": row["version"],
                    "content": row["content"],
                    "content_hash": row["content_hash"],
                    "explanation": row["change_explanation"] or "",
                    "motivated_by_failures": _json(row["motivated_by_failures"]),
                }
            )
        for row in _rows(
            repo,
            context,
            "SELECT dv.*, d.name FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id WHERE dv.workspace_id=? AND d.workspace_id=? AND d.project_id=? ORDER BY dv.id",
            context.workspace_id,
            context.workspace_id,
            project_id,
        ):
            payload["datasets"].append(
                {
                    "source_id": row["id"],
                    "name": row["name"],
                    "version": row["version"],
                    "records": _json(row["rows_json"]),
                    "content_hash": row["content_hash"],
                }
            )
        for row in _rows(
            repo,
            context,
            "SELECT tv.*, t.name, t.target_type FROM target_versions tv JOIN targets t ON t.id=tv.target_id WHERE tv.workspace_id=? AND t.workspace_id=? AND t.project_id=? ORDER BY tv.id",
            context.workspace_id,
            context.workspace_id,
            project_id,
        ):
            payload["targets"].append(
                {
                    "name": row["name"],
                    "target_type": row["target_type"],
                    "version": row["version"],
                    "configuration": _target_configuration(_json(row["configuration_json"])),
                }
            )
        for run in reversed(repo.list_runs(context)):
            if run["project_id"] != project_id:
                continue
            results = []
            for result in reversed(repo.list_results(context, run["id"])):
                results.append(
                    {
                        key: _json(value) if key.endswith("_json") or key in _RESULT_JSON else value
                        for key, value in result.items()
                        if key
                        not in {
                            "id",
                            "run_id",
                            "manifest",
                            "manifest_hash",
                            "run_name",
                            "timestamp",
                            "mode",
                            "run_status",
                        }
                    }
                )
            recorded_manifest = _json(run["manifest_json"]) or {}
            recorded_at = str(run["timestamp"])
            if run["mode"] == "imported_history" and isinstance(recorded_manifest, dict):
                recorded_at = recorded_manifest.get("recorded_at", recorded_at)
                recorded_manifest = recorded_manifest.get("recorded_manifest", {})
            payload["runs"].append(
                {
                    "source_id": run["id"],
                    "name": run["run_name"],
                    "model": run["model_name"],
                    "mode": run["mode"],
                    "recorded_target_type": run["target_type"],
                    "timestamp": recorded_at,
                    "dataset_source_id": run["dataset_version_id"],
                    "unique_case_count": run["unique_case_count"],
                    "total_executions": run["total_executions"],
                    "recorded_manifest": recorded_manifest,
                    "results": results,
                }
            )
        run_ids = {run["source_id"] for run in payload["runs"]}
        for row in _rows(
            repo,
            context,
            "SELECT action, entity_id, metadata_json, created_at FROM audit_logs WHERE workspace_id=? AND action IN ('product.decision_recorded', 'project.imported_decision') ORDER BY id",
            context.workspace_id,
        ):
            metadata = _json(row["metadata_json"])
            if isinstance(metadata, dict) and row["action"] == "project.imported_decision":
                metadata["run_id"] = int(row["entity_id"])
            if isinstance(metadata, dict) and metadata.get("run_id") in run_ids:
                payload["decisions"].append(
                    {
                        "run_source_id": metadata["run_id"],
                        "decision": metadata.get("decision"),
                        "next_action": metadata.get("next_action"),
                        "recorded_at": str(metadata.get("recorded_at") or row["created_at"]),
                    }
                )
    original_payload = payload
    payload = _safe(payload)
    for original, document in zip(original_payload["documents"], payload["documents"], strict=True):
        changed = original["text_preview"] != document["text_preview"] or any(
            previous["chunk_text"] != current["chunk_text"]
            for previous, current in zip(original["chunks"], document["chunks"], strict=True)
        )
        for chunk in document["chunks"]:
            chunk["content_hash"] = text_hash(chunk["chunk_text"])
        if changed:
            document["content_hash"] = version_hash(
                {"text_preview": document["text_preview"], "chunks": document["chunks"]}
            )
            document["warnings"].append(
                "Credential-like text was removed during project export; the source identity now describes the exported passages."
            )
    for prompt in payload["prompts"]:
        prompt["content_hash"] = text_hash(prompt["content"])
    for dataset in payload["datasets"]:
        dataset["content_hash"] = version_hash(dataset["records"])
    _bounded(payload)
    _validate(payload)
    raw = canonical_json({"schema": SCHEMA, "payload": payload, "payload_sha256": version_hash(payload)}).encode(
        "utf-8"
    )
    if len(raw) > MAX_WORKSPACE_BYTES:
        raise ValueError("Project exceeds the 20 MiB portable workspace limit.")
    return raw


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Project contains duplicate field names.")
        result[key] = value
    return result


def restore_project_workspace(repository: Repository, context: WorkspaceContext, raw: bytes) -> int:
    """Admit one bounded JSON decode/restore per process without queueing uploads."""
    if not _RESTORE_LOCK.acquire(blocking=False):
        raise ValueError("Another project is being restored. Try again once it finishes.")
    try:
        return _restore_project_workspace(repository, context, raw)
    finally:
        _RESTORE_LOCK.release()


def _restore_project_workspace(repository: Repository, context: WorkspaceContext, raw: bytes) -> int:
    repo = _repository(repository)
    repo.authorize(context, Role.EDITOR)
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_WORKSPACE_BYTES:
        raise ValueError("Choose a project file no larger than 20 MiB.")
    try:
        archive = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ValueError("Project file is not valid workspace JSON.") from exc
    _bounded(archive)
    _object(archive, {"schema", "payload", "payload_sha256"})
    if archive["schema"] != SCHEMA:
        raise ValueError("This project file version is not supported.")
    payload = _object(archive["payload"])
    if archive["payload_sha256"] != version_hash(payload):
        raise ValueError("Project checksum does not match its content.")
    if _safe(payload) != payload:
        raise ValueError("Project contains credential fields or references. Export it again without secrets.")
    _validate(payload)
    with repo.transaction():
        project_id = repo.create_project(context, payload["project"])
        for document in payload["documents"]:
            repo.save_documents_and_chunks(
                context,
                [
                    {
                        "filename": document["filename"],
                        "text": document["text_preview"],
                        "content_hash": document["content_hash"],
                        "warnings": document["warnings"],
                    }
                ],
                [{**chunk, "filename": document["filename"]} for chunk in document["chunks"]],
                project_id,
            )
        for prompt in payload["prompts"]:
            repo.save_prompt(
                context,
                project_id,
                prompt["name"],
                prompt["content"],
                prompt["type"],
                explanation=prompt["explanation"],
                motivated_by_failures=prompt["motivated_by_failures"],
            )
        dataset_ids = {
            dataset["source_id"]: repo.create_dataset_version(
                context, project_id, dataset["name"], dataset["records"], immutable=False
            )
            for dataset in payload["datasets"]
        }
        for target in payload["targets"]:
            repo.create_target_version(
                context, project_id, target["name"], target["target_type"], target["configuration"]
            )
        run_ids = {}
        for run in payload["runs"]:
            imported_type = "synthetic_mock" if run["recorded_target_type"] == "synthetic_mock" else "saved_responses"
            manifest = {
                "imported_evidence": True,
                "execution_verified": False,
                "notice": IMPORT_NOTICE,
                "archive_sha256": archive["payload_sha256"],
                "recorded_at": run["timestamp"],
                "recorded_manifest": run["recorded_manifest"],
            }
            manifest["manifest_hash"] = version_hash(manifest)
            run_id = repo.create_run(
                context,
                run_name=run["name"],
                model_name=run["model"],
                mode="imported_history",
                unique_case_count=run["unique_case_count"],
                total_executions=run["total_executions"],
                project_id=project_id,
                notes=IMPORT_NOTICE,
                target_type=imported_type,
                dataset_version_id=dataset_ids.get(run["dataset_source_id"]),
                manifest=manifest,
                calibration_status="insufficiently_calibrated",
            )
            run_ids[run["source_id"]] = run_id
            for result in run["results"]:
                result = {key: _json(value) if key in _RESULT_JSON else value for key, value in result.items()}
                metadata = _json(result.get("metadata_json", {}))
                metadata = dict(metadata) if isinstance(metadata, dict) else {}
                metadata.update(result.get("metadata") or {})
                prior_import = metadata.get("imported_evidence")
                prior_import = prior_import if isinstance(prior_import, dict) else {}
                metadata["imported_evidence"] = {
                    "execution_verified": False,
                    "archive_sha256": archive["payload_sha256"],
                    "recorded_target_type": prior_import.get("recorded_target_type", result.get("target_type")),
                    "recorded_calibration_status": prior_import.get(
                        "recorded_calibration_status", result.get("calibration_status")
                    ),
                    "recorded_at": run["timestamp"],
                    "notice": IMPORT_NOTICE,
                    "recorded_execution": prior_import.get("recorded_execution", metadata.get("execution", {})),
                }
                metadata["execution"] = {"attempt_count": 0, "cache_hit": False, "execution_key": None}
                explanation = result.get("score_explanation")
                explanation = explanation if isinstance(explanation, dict) else {}
                restored = {
                    **result,
                    "evaluator_version": result.get("evaluator_version") or "unknown_imported_evaluator",
                    "determination_state": result.get("determination_state") or "unable_to_determine",
                    "score_explanation": explanation,
                    "target_type": "synthetic_mock" if result.get("target_type") == "synthetic_mock" else imported_type,
                    "calibration_status": "insufficiently_calibrated",
                    "calibration_version": None,
                    "metadata": metadata,
                    "metadata_json": json.dumps(metadata),
                }
                repo.save_result(context, run_id, restored)
        for decision in payload["decisions"]:
            repo.audit(
                context,
                "project.imported_decision",
                "run",
                str(run_ids[decision["run_source_id"]]),
                {
                    "decision": decision["decision"],
                    "next_action": decision["next_action"],
                    "recorded_at": decision["recorded_at"],
                    "verified": False,
                },
            )
        repo.audit(
            context,
            "project.import",
            "project",
            str(project_id),
            {"archive_sha256": archive["payload_sha256"], "run_count": len(run_ids), "calibration_restored": False},
        )
    return project_id
