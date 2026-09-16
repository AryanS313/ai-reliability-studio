"""Private stdin/stdout extraction worker; never invoke it with user arguments."""

from __future__ import annotations

import base64
import contextlib
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any


def _deny_network(*args: Any, **kwargs: Any) -> Any:
    raise OSError("Document parsers cannot open network connections.")


def _set_resource_limits() -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    # RLIMIT_AS is enforced on the deployed Linux host. macOS does not provide
    # equivalent address-space enforcement; wall time/CPU/output bounds remain.
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))


def main() -> None:
    _set_resource_limits()
    socket.socket.connect = _deny_network  # type: ignore[method-assign]
    socket.socket.connect_ex = _deny_network  # type: ignore[method-assign]
    socket.socket.sendto = _deny_network  # type: ignore[method-assign]
    socket.create_connection = _deny_network
    socket.getaddrinfo = _deny_network
    sys.dont_write_bytecode = True
    # -I deliberately excludes caller paths. Add only the trusted application.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raw = sys.stdin.buffer.read(3 * 1024 * 1024 + 1)
    response: dict[str, Any]
    try:
        if len(raw) > 3 * 1024 * 1024:
            raise ValueError("Document input is too large.")
        value = json.loads(raw)
        from src import config
        from src.document_loader import SUPPORTED_EXTENSIONS, _extract_validated_document
        from src.security import validate_upload

        config.MAX_EXTRACTED_CHARACTERS = min(int(value["max_characters"]), 250_000)
        config.MAX_DATASET_ROWS = min(int(value["max_rows"]), 500)
        data = base64.b64decode(value["content"], validate=True)
        filename = validate_upload(
            value["filename"], data, allowed_extensions=SUPPORTED_EXTENSIONS, max_bytes=2 * 1024 * 1024
        )
        # Library chatter must not corrupt the protocol or disclose input in logs.
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink):
            if value.get("operation") == "dataset":
                artifact = _read_dataset(filename, data)
            elif value.get("operation") == "document":
                artifact = _extract_validated_document(filename, filename, data, [], {})
            else:
                raise ValueError("Unsupported document processing operation.")
        response = {"ok": True, "artifact": artifact}
    except ValueError as exc:
        response = {"ok": False, "error": str(exc)[:400]}
    except Exception:
        response = {"ok": False, "error": "This document could not be read. Try a smaller file or export it again."}
    encoded = json.dumps(response).encode("utf-8")
    if len(encoded) > 4 * 1024 * 1024:
        encoded = b'{"ok":false,"error":"Extracted content is too large. Split the document into smaller files."}'
    sys.stdout.buffer.write(encoded)


def _read_dataset(filename: str, data: bytes) -> dict[str, Any]:
    from io import BytesIO

    import pandas as pd

    from src import config
    from src.datasets import normalize_dataset_frame
    from src.document_loader import _validate_zip_container

    suffix = Path(filename).suffix.lower()
    if suffix == ".xlsx":
        _validate_zip_container(data)
    buffer = BytesIO(data)
    if suffix in {".csv", ".tsv"}:
        frame = pd.read_csv(
            buffer,
            sep="\t" if suffix == ".tsv" else ",",
            dtype=str,
            keep_default_na=False,
            nrows=config.MAX_DATASET_ROWS + 1,
        )
    elif suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(buffer, dtype=str, keep_default_na=False, nrows=config.MAX_DATASET_ROWS + 1)
    elif suffix in {".json", ".jsonl"}:
        frame = pd.read_json(buffer, lines=suffix == ".jsonl", dtype=False, convert_dates=False)
    else:
        raise ValueError("Choose a CSV, TSV, Excel, JSON or JSONL question file.")
    if len(frame) > config.MAX_DATASET_ROWS or len(frame.columns) > 100:
        raise ValueError("This question file is too large. Use at most 500 questions and 100 columns.")
    normalized = normalize_dataset_frame(frame, allow_legacy=True)
    return {"records": json.loads(normalized.to_json(orient="records")), "columns": list(normalized.columns)}


if __name__ == "__main__":
    main()
