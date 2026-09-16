"""Bound native hosted parsing without sharing deployment credentials with parsers.

This is resource containment, not an operating-system security sandbox or malware
scanner. The scanner policy is enforced by document_loader before this function.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from src import config

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_RESULT_BYTES = 4 * 1024 * 1024
EXTRACTION_TIMEOUT_SECONDS = 20
_slots = threading.BoundedSemaphore(1)


def extract_hosted_document(filename: str, data: bytes) -> dict[str, Any]:
    artifact = _run_extraction(filename, data, "document")
    if not isinstance(artifact.get("text"), str):
        raise ValueError("The document did not produce usable text.")
    return artifact


def read_hosted_dataset(filename: str, data: bytes):
    import pandas as pd

    if config.REQUIRE_MALWARE_SCAN:
        raise ValueError("Question-file ingestion requires a configured malware scanner before files can be accepted.")
    artifact = _run_extraction(filename, data, "dataset")
    return pd.DataFrame(artifact["records"], columns=artifact["columns"])


def _run_extraction(filename: str, data: bytes, operation: str) -> dict[str, Any]:
    if len(data) > min(config.MAX_UPLOAD_BYTES, MAX_FILE_BYTES):
        raise ValueError("This document is too large. Upload a file smaller than 2 MB.")
    if not _slots.acquire(blocking=False):
        raise ValueError("Document processing is busy. Your current work is safe; try this upload again shortly.")
    try:
        payload = json.dumps(
            {
                "filename": filename,
                "operation": operation,
                "content": base64.b64encode(data).decode("ascii"),
                "max_characters": min(config.MAX_EXTRACTED_CHARACTERS, 250_000),
                "max_rows": min(config.MAX_DATASET_ROWS, 500),
            }
        ).encode("utf-8")
        worker = Path(__file__).with_name("hosted_document_worker.py")
        # No user text in command arguments, shell, filenames on disk, or logs.
        # Do not inherit owner keys, proxies, Python startup hooks, or dotenv.
        result = subprocess.run(
            [sys.executable, "-I", str(worker)],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=EXTRACTION_TIMEOUT_SECONDS,
            check=False,
            close_fds=True,
            env={
                "STUDIO_EXTRACTION_WORKER": "1",
                "APP_ACCESS_MODE": "hosted-session",
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "LANG": "C.UTF-8",
            },
        )
        if result.returncode != 0:
            raise ValueError("This document could not be processed within the limits. Try a smaller or simpler file.")
        if len(result.stdout) > MAX_RESULT_BYTES:
            raise ValueError("This document produces too much extracted content. Split it into smaller files.")
        try:
            response = json.loads(result.stdout)
        except (ValueError, UnicodeError) as exc:
            raise ValueError(
                "The document could not be read. Try exporting it again from its original application."
            ) from exc
        if not isinstance(response, dict) or response.get("ok") is not True:
            detail = response.get("error") if isinstance(response, dict) else None
            raise ValueError(detail if isinstance(detail, str) else "The document could not be read.")
        artifact = response.get("artifact")
        if not isinstance(artifact, dict):
            raise ValueError("The document did not produce usable text.")
        return artifact
    except subprocess.TimeoutExpired as exc:
        raise ValueError("This document took too long to read. Split it into smaller files and try again.") from exc
    except OSError as exc:
        raise ValueError("Document processing is temporarily unavailable. Try again shortly.") from exc
    finally:
        _slots.release()
