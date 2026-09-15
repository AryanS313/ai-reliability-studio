import json

import pandas as pd
import pytest

from src.connection_settings import parse_connection_settings
from src.ui_display import readable_frame, review_labels


def test_readable_table_retains_unknown_measurements_and_does_not_change_evidence():
    frame = pd.DataFrame(
        [
            {
                "groundedness_score": 0.75,
                "estimated_cost": float("nan"),
                "execution_status": "timed_out",
                "prompt_name": "Improved Prompt",
            }
        ]
    )
    saved = frame.copy(deep=True)
    shown = readable_frame(frame)
    assert shown.iloc[0].to_dict() == {
        "Answer supported by sources": "75%",
        "Recorded cost": "Not recorded",
        "Call outcome": "Timed out",
        "Instructions": "Candidate instructions",
    }
    pd.testing.assert_frame_equal(saved, frame)


@pytest.mark.parametrize("value", [["unsupported_claim"], '["unsupported_claim"]', "unsupported_claim", None])
def test_review_labels_show_native_choices_without_serialized_array_text(value):
    expected = [] if value is None else ["unsupported_claim"]
    assert review_labels(value) == expected


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"{",
        b"[]",
        b"null",
        b'{"endpoint":"http://169.254.169.254/metadata","name":"Unsafe"}',
        b'{"endpoint":"https://example.com","name":"Unsafe","headers":{"Authorization":"raw-secret"}}',
    ],
)
def test_imported_connection_rejects_invalid_unsafe_or_secret_content(content):
    with pytest.raises(ValueError):
        parse_connection_settings(content)


def test_imported_connection_preserves_custom_request_and_has_no_network(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: pytest.fail("Import must not access network"))
    content = {
        "name": "Support",
        "endpoint": "https://example.com/answer",
        "request_template": {"message": {"query": "${question}"}, "limit": 3},
        "headers": {"Authorization": "secret://SESSION_EXTERNAL_AUTH"},
        "retry_count": 0,
    }
    result = parse_connection_settings(json.dumps(content).encode())
    assert result["request_template"] == content["request_template"]
    assert result["retry_count"] == 0
    assert result["headers"] == content["headers"]
    assert parse_connection_settings(json.dumps(result).encode()) == result
