"""Plain-language case editing without exposing or discarding evaluation metadata."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any
from uuid import uuid4

import pandas as pd

from src import config
from src.datasets import parse_list, strict_bool

EDITOR_COLUMNS = ["case_id", "question", "expected_answer", "expected_source", "category", "handoff", "severity"]
FIELD_LABELS = {
    "question": "Question",
    "expected_answer": "Main expected answer",
    "expected_answers": "Expected answers",
    "expected_source": "Main source",
    "expected_sources": "Reference sources",
    "category": "Question group",
    "should_escalate": "Human handoff",
    "severity": "Impact of a wrong answer",
    "case_id": "Question reference",
    "expected_behavior": "Expected response",
    "tags": "Saved question groups",
    "split": "Question set",
    "rubric": "Saved evaluation rules",
    "variables": "Saved request details",
}
RISK_LABELS = {
    "privacy": "Protecting personal data",
    "security": "Preventing unauthorized actions",
    "prompt-injection": "Resisting misleading instructions",
    "unsupported-claim": "Avoiding unsupported answers",
    "conflicting-sources": "Handling conflicting documents",
    "missing-evidence": "Handling missing information",
    "citation": "Referencing the right sources",
    "retrieval": "Finding the right information",
    "escalation": "Handing off to a human",
    "ambiguous": "Clarifying unclear questions",
    "numeric-date": "Getting amounts and dates right",
    "policy-exception": "Recognizing policy exceptions",
    "infrastructure": "Handling service failures",
}


def case_editor_frame(source: pd.DataFrame) -> pd.DataFrame:
    """Show simple scalar fields; case_id stays hidden and read-only in the UI."""
    rows = []
    for original in source.to_dict("records"):
        handoff = strict_bool(original.get("should_escalate"), allow_blank=True)
        rows.append(
            {
                "case_id": _text(original.get("case_id")),
                "question": _text(original.get("question")),
                "expected_answer": _primary(original, "expected_answer", "expected_answers"),
                "expected_source": _primary(original, "expected_source", "expected_sources"),
                "category": _text(original.get("category")),
                "handoff": "Not specified" if handoff is None else "Yes" if handoff else "No",
                "severity": _text(original.get("severity", "medium")).capitalize(),
            }
        )
    return pd.DataFrame(rows, columns=EDITOR_COLUMNS)


def merge_case_edits(
    source: pd.DataFrame,
    edited: pd.DataFrame,
    *,
    new_id: Callable[[], str] | None = None,
) -> pd.DataFrame:
    """Merge by immutable ID, preserving hidden fields and reference alternatives.

    An absent row is deleted. A row without an ID is new. Existing identifiers
    cannot be replaced, duplicated or borrowed from another dataset.
    """
    if edited.empty:
        raise ValueError("Keep at least one question before saving.")
    if len(edited) > config.MAX_DATASET_ROWS:
        raise ValueError(f"This set has too many questions. The limit is {config.MAX_DATASET_ROWS:,}.")
    if not set(EDITOR_COLUMNS).issubset(edited.columns):
        raise ValueError("The editor is missing a question field. Reload the page and try again.")
    originals = {_text(row.get("case_id")): deepcopy(row) for row in source.to_dict("records")}
    if "" in originals or len(originals) != len(source):
        raise ValueError("The saved questions need unique references. Correct the uploaded file before editing.")
    before = {row["case_id"]: row for row in case_editor_frame(source).to_dict("records")}
    generate_id = new_id or (lambda: "case-" + uuid4().hex[:16])
    seen: set[str] = set()
    merged = []
    for position, edited_row in enumerate(edited.to_dict("records"), start=1):
        identity = _text(edited_row.get("case_id"))
        if identity:
            if identity not in originals or identity in seen:
                raise ValueError("A question reference changed or was repeated. Reload the editor before saving.")
            original = deepcopy(originals[identity])
            previous = before[identity]
        else:
            identity = generate_id()
            if not identity or identity in originals or identity in seen:
                raise ValueError("A new question reference could not be created. Try saving again.")
            for field in ("question", "expected_answer", "expected_source", "category", "severity", "handoff"):
                if not _text(edited_row.get(field)):
                    raise ValueError(f"Question {position}: add {FIELD_LABELS.get(field, 'human handoff').lower()}.")
            original = {
                "case_id": identity,
                "expected_behavior": "answer",
                "expected_answers": [],
                "expected_sources": [],
                "tags": [_text(edited_row.get("category")).lower().replace(" ", "-")],
                "split": "development",
                "environment": "development",
                "language": "",
                "locale": "",
            }
            previous = {}
            # Preserve the original file's schema shape for compatibility aliases.
            for field in ("expected_answer", "expected_source"):
                if field in source:
                    original[field] = ""
        seen.add(identity)
        for field in ("question", "category"):
            value = _text(edited_row.get(field))
            if value != previous.get(field):
                original[field] = value
        severity = _text(edited_row.get("severity")).lower()
        if severity != str(previous.get("severity", "")).lower():
            original["severity"] = severity
        handoff_label = _text(edited_row.get("handoff"))
        if handoff_label not in {"Yes", "No", "Not specified"}:
            raise ValueError(f"Question {position}: choose Yes, No or Not specified for human handoff.")
        if handoff_label != previous.get("handoff"):
            original["should_escalate"] = {"Yes": True, "No": False, "Not specified": None}[handoff_label]
        for scalar, plural in (("expected_answer", "expected_answers"), ("expected_source", "expected_sources")):
            value = _text(edited_row.get(scalar))
            old_value = str(previous.get(scalar, ""))
            if value != old_value or not previous:
                references = deepcopy(parse_list(original.get(plural, [])))
                if old_value and old_value in references:
                    offset = references.index(old_value)
                    if value:
                        references[offset] = value
                    else:
                        references.pop(offset)
                elif value and value not in references:
                    references.insert(0, value)
                original[plural] = references
                if scalar in original:
                    original[scalar] = value
        merged.append(original)
    result = pd.DataFrame(merged)
    result.attrs = deepcopy(source.attrs)
    return result


def coverage_findings(coverage: dict[str, Any]) -> list[str]:
    """Translate known quality checks without exposing machine dictionaries or IDs."""
    quality = coverage["quality_report"]
    findings: list[str] = []
    for message in [*quality.get("errors", []), *quality.get("warnings", []), *coverage.get("warnings", [])]:
        message = str(message)
        if "Required risk categories" in message:
            text = "Some risk areas have no questions yet. See the coverage list below."
        elif "critical" in message.lower() and ("No critical" in message or "untested" in message):
            text = "Include questions where a wrong answer could cause the most harm."
        elif "held-out" in message or "heldout" in message:
            text = "Keep a separate set of questions that was not used to improve the assistant."
        elif "Duplicate case IDs" in message:
            text = "Some question references are repeated. Upload a corrected file with a different reference for each question."
        elif "Duplicate evaluation cases" in message:
            text = "Some questions are repeated. Keep distinct questions or make their differences clear."
        elif "Expected sources do not exist" in message:
            text = "Some reference sources are missing. Add the matching documents or correct the source names."
        elif "non-empty" in message:
            field = (
                "impact level"
                if "severity" in message
                else "language and region"
                if "locale" in message
                else "test environment"
            )
            text = f"Some saved questions need a {field} before they can support a release decision."
        elif "tuning" in message:
            text = "Record whether these questions were used while changing the assistant."
        elif "30" in message:
            text = "Use at least 30 questions for a release review. Smaller sets are useful for trying the workflow."
        elif "fewer than 5" in message:
            text = "Add more examples to the smaller question groups."
        elif "No positive escalation" in message:
            text = "Include questions that should be handed to a human."
        elif "No negative escalation" in message:
            text = "Include questions the assistant should answer without a human handoff."
        elif "purpose" in message:
            text = "In your source file, record what each question is meant to test."
        elif "severity rationale" in message:
            text = "In your source file, explain why each question has its chosen impact level."
        elif "source behavior" in message:
            text = "In your source file, describe how each question should use its reference sources."
        else:
            text = "Some saved case details still need review before these questions can support a release decision."
        if text not in findings:
            findings.append(text)
    return findings


def _primary(row: dict[str, Any], scalar: str, plural: str) -> str:
    if _text(row.get(scalar)):
        return _text(row[scalar])
    references = parse_list(row.get(plural, []))
    return _text(references[0]) if references and isinstance(references[0], str) else ""


def _text(value: Any) -> str:
    if value is None or value is pd.NA or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, list | dict | tuple):
        return ""
    return str(value).strip()
