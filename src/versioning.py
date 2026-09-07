from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

APPLICATION_VERSION = "1.0.0"


def canonical_json(value: Any) -> str:
    if is_dataclass(value):
        value = asdict(value)  # type: ignore[arg-type]
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def version_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def runtime_metadata() -> dict[str, Any]:
    runtime: dict[str, Any] = {"python": platform.python_version(), "platform": platform.platform()}
    if sys.platform == "emscripten":
        from importlib.metadata import PackageNotFoundError, version

        packages = {}
        for name in (
            "numpy",
            "pandas",
            "scipy",
            "scikit-learn",
            "pydantic",
            "httpx",
            "openai",
            "anthropic",
            "google-genai",
        ):
            try:
                packages[name] = version(name)
            except PackageNotFoundError:
                packages[name] = None
        runtime.update(
            {
                "execution": "browser-sequential-v1",
                "browser_adapter": "browser-runtime-v1",
                "pyodide": "0.26.4",
                "stlite": "0.76.0",
                "packages": packages,
                "source_snapshot_sha256": os.getenv("STUDIO_BROWSER_SOURCE_SHA256"),
                "provider_transport": "direct-browser-fetch-v1",
            }
        )
    return runtime


def git_commit(root: str | Path | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root) if root else None,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def build_run_manifest(
    *,
    prompt: dict[str, Any],
    dataset: dict[str, Any],
    documents: list[dict[str, Any]],
    retrieval: dict[str, Any],
    target: dict[str, Any],
    evaluators: list[dict[str, Any]],
    model: dict[str, Any],
    user_id: int,
    workspace_id: int,
    environment: str | None = None,
) -> dict[str, Any]:
    manifest = {
        "application_version": APPLICATION_VERSION,
        "git_commit": git_commit(Path(__file__).resolve().parents[1]),
        "created_at": datetime.now(UTC).isoformat(),
        "environment": environment or os.getenv("APP_ENV", "development"),
        "runtime": runtime_metadata(),
        "user_id": user_id,
        "workspace_id": workspace_id,
        "prompt": {**prompt, "content_hash": prompt.get("content_hash") or version_hash(prompt)},
        "dataset": {**dataset, "content_hash": dataset.get("content_hash") or version_hash(dataset)},
        "documents": [
            {**document, "content_hash": document.get("content_hash") or version_hash(document)}
            for document in documents
        ],
        "retrieval": retrieval,
        "target": target,
        "evaluators": evaluators,
        "model": model,
    }
    manifest["manifest_hash"] = version_hash(manifest)
    return manifest
