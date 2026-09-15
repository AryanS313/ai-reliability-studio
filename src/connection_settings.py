"""Import optional engineer-supplied connections without showing raw configuration."""

from __future__ import annotations

import json
from typing import Any

from src import config
from src.targets import ExternalTargetConfig, target_configuration_for_storage


def parse_connection_settings(content: bytes) -> dict[str, Any]:
    if not content or len(content) > min(config.MAX_UPLOAD_BYTES, config.MAX_EXTERNAL_REQUEST_BYTES):
        raise ValueError("The settings file is empty or too large. Ask your engineer for a smaller connection file.")
    try:
        values = json.loads(content.decode("utf-8-sig"))
        if not isinstance(values, dict):
            raise ValueError("Expected connection settings")
        values.pop("version_hash", None)
        configuration = ExternalTargetConfig(**values)
        return target_configuration_for_storage(configuration)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError(
            "These connection settings could not be validated. Ask your engineer to check the endpoint, request fields and secret references. No settings were changed."
        ) from exc
