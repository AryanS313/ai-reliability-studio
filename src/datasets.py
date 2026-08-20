from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.versioning import version_hash

REQUIRED_FIELDS = {"case_id", "question", "category", "expected_behavior", "severity", "tags"}
LEGACY_REQUIRED_FIELDS = {"question", "expected_answer", "expected_source", "category", "should_escalate"}
OPTIONAL_FIELDS = {
    "expected_answers",
    "unacceptable_answers",
    "expected_sources",
    "expected_passages",
    "should_escalate",
    "escalation_destination",
    "escalation_urgency",
    "expected_tool_calls",
    "conversation_history",
    "variables",
    "user_segment",
    "language",
    "locale",
    "environment",
    "purpose",
    "severity_rationale",
    "source_expectation",
    "tuning_disclosure",
    "infrastructure_simulation",
    "rubric",
    "notes",
    "mock_scenario",
    "split",
}
REQUIRED_LAUNCH_CATEGORIES = {
    "privacy",
    "security",
    "prompt-injection",
    "unsupported-claim",
    "conflicting-sources",
    "missing-evidence",
    "citation",
    "retrieval",
    "escalation",
    "ambiguous",
    "numeric-date",
    "policy-exception",
    "infrastructure",
}
SEVERITIES = {"low", "medium", "high", "critical"}
SPLITS = {"calibration", "development", "holdout", "train", "test"}
TRUE_VALUES = {True, "1", "true", "yes", "y"}
FALSE_VALUES = {False, "0", "false", "no", "n"}


@dataclass(frozen=True)
class DatasetValidationError:
    row: int | None
    field: str
    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"row": self.row, "field": self.field, "code": self.code, "message": self.message}


class DatasetValidationException(ValueError):
    def __init__(self, errors: list[DatasetValidationError]):
        self.errors = errors
        summary = "; ".join(
            f"row {error.row}: {error.field} {error.message}" if error.row is not None else error.message
            for error in errors[:20]
        )
        if len(errors) > 20:
            summary += f"; plus {len(errors) - 20} more errors"
        super().__init__(summary)


def strict_bool(value: Any, *, allow_blank: bool = False) -> bool | None:
    if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == "":
        if allow_blank:
            return None
        raise ValueError("must be a non-blank boolean")
    normalized = value if isinstance(value, bool | int) else str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"has invalid boolean value {value!r}; use true/false, yes/no, or 1/0")


def validate_dataset_frame(df: pd.DataFrame, *, allow_legacy: bool = True) -> list[DatasetValidationError]:
    errors: list[DatasetValidationError] = []
    columns = set(df.columns)
    legacy = LEGACY_REQUIRED_FIELDS.issubset(columns)
    missing = (LEGACY_REQUIRED_FIELDS if legacy and allow_legacy else REQUIRED_FIELDS) - columns
    for field in sorted(missing):
        errors.append(DatasetValidationError(None, field, "missing_column", f"missing required column: {field}"))
    if missing:
        return errors

    seen: dict[str, int] = {}
    for index, row in df.iterrows():
        row_number = int(index) + 2 if isinstance(index, int) else None
        required = ["question", "category"]
        if legacy and allow_legacy:
            required.extend(["expected_answer", "expected_source", "should_escalate"])
        else:
            required.extend(["case_id", "expected_behavior", "severity", "tags"])
        for field in required:
            if _blank(row.get(field)):
                errors.append(DatasetValidationError(row_number, field, "blank", "must not be blank"))

        case_id = str(row.get("case_id", "")).strip()
        if case_id:
            if case_id in seen:
                errors.append(
                    DatasetValidationError(
                        row_number,
                        "case_id",
                        "duplicate",
                        f"duplicates row {seen[case_id]}",
                    )
                )
            seen[case_id] = row_number or 0
            if not re.fullmatch(r"[A-Za-z0-9_.:-]+", case_id):
                errors.append(
                    DatasetValidationError(
                        row_number, "case_id", "invalid_format", "may contain letters, digits, _ . : -"
                    )
                )

        severity = str(row.get("severity", "medium")).strip().lower()
        if severity not in SEVERITIES:
            errors.append(
                DatasetValidationError(row_number, "severity", "invalid_enum", f"must be one of {sorted(SEVERITIES)}")
            )
        split = str(row.get("split", "")).strip().lower()
        if split and split not in SPLITS:
            errors.append(
                DatasetValidationError(row_number, "split", "invalid_enum", f"must be one of {sorted(SPLITS)}")
            )
        if "should_escalate" in columns and not _blank(row.get("should_escalate")):
            try:
                strict_bool(row.get("should_escalate"))
            except ValueError as exc:
                errors.append(DatasetValidationError(row_number, "should_escalate", "invalid_boolean", str(exc)))
        for field in ["expected_answers", "unacceptable_answers", "expected_sources", "expected_passages", "tags"]:
            if field in columns and not _blank(row.get(field)):
                try:
                    parsed = parse_list(row.get(field))
                    if field == "tags" and not parsed:
                        raise ValueError("must contain at least one tag")
                except ValueError as exc:
                    errors.append(DatasetValidationError(row_number, field, "invalid_list", str(exc)))
        for field in ["variables", "rubric"]:
            if field in columns and not _blank(row.get(field)):
                try:
                    parse_object(row.get(field))
                except ValueError as exc:
                    errors.append(DatasetValidationError(row_number, field, "invalid_object", str(exc)))
    return errors


def normalize_dataset_frame(df: pd.DataFrame, *, allow_legacy: bool = True) -> pd.DataFrame:
    source_quality = dataset_quality_report(df)
    errors = validate_dataset_frame(df, allow_legacy=allow_legacy)
    if errors:
        raise DatasetValidationException(errors)
    out = df.copy()
    legacy = LEGACY_REQUIRED_FIELDS.issubset(out.columns)
    if "case_id" not in out:
        out["case_id"] = [f"case-{index + 1:04d}" for index in range(len(out))]
    if "expected_behavior" not in out:
        out["expected_behavior"] = out["expected_answer"] if legacy else "answer"
    if "severity" not in out:
        out["severity"] = "medium"
    if "tags" not in out:
        out["tags"] = out["category"].apply(lambda value: [str(value).strip().lower().replace(" ", "-")])
    else:
        out["tags"] = out["tags"].apply(parse_list)
    if "expected_answers" not in out:
        out["expected_answers"] = out.get("expected_answer", pd.Series([""] * len(out))).apply(
            lambda value: [str(value)] if not _blank(value) else []
        )
    else:
        out["expected_answers"] = out["expected_answers"].apply(parse_list)
    if "expected_sources" not in out:
        out["expected_sources"] = out.get("expected_source", pd.Series([""] * len(out))).apply(
            lambda value: [str(value)] if not _blank(value) else []
        )
    else:
        out["expected_sources"] = out["expected_sources"].apply(parse_list)
    if "should_escalate" in out:
        out["should_escalate"] = out["should_escalate"].apply(lambda value: strict_bool(value, allow_blank=True))
    else:
        out["should_escalate"] = None
    for field in ["unacceptable_answers", "expected_passages", "expected_tool_calls", "conversation_history"]:
        if field not in out:
            out[field] = [[] for _ in range(len(out))]
        else:
            out[field] = out[field].apply(parse_list)
    for field in ["variables", "rubric"]:
        if field not in out:
            out[field] = [{} for _ in range(len(out))]
        else:
            out[field] = out[field].apply(parse_object)
    defaults = {
        "escalation_destination": "",
        "escalation_urgency": "",
        "user_segment": "",
        "language": "en",
        "locale": "en-US",
        "environment": "development",
        "purpose": "",
        "severity_rationale": "",
        "source_expectation": "",
        "tuning_disclosure": "",
        "infrastructure_simulation": "",
        "notes": "",
        "mock_scenario": "correct_grounded_answer",
        "split": "development",
    }
    for field, default in defaults.items():
        if field not in out:
            out[field] = default
    out["severity"] = out["severity"].astype(str).str.strip().str.lower()
    out["split"] = out["split"].astype(str).str.strip().str.lower()
    out.attrs["source_quality_report"] = source_quality
    return out


def dataset_snapshot(df: pd.DataFrame, *, name: str, version: int) -> dict[str, Any]:
    normalized = normalize_dataset_frame(df)
    records = normalized.to_dict(orient="records")
    return {
        "name": name,
        "version": version,
        "case_count": len(records),
        "records": records,
        "content_hash": version_hash(records),
    }


def coverage_analysis(df: pd.DataFrame) -> dict[str, Any]:
    normalized = normalize_dataset_frame(df)
    quality = dict(df.attrs.get("source_quality_report") or dataset_quality_report(df))
    return {
        "cases": len(normalized),
        "categories": normalized["category"].value_counts().to_dict(),
        "severities": normalized["severity"].value_counts().to_dict(),
        "languages": normalized["language"].value_counts().to_dict(),
        "splits": normalized["split"].value_counts().to_dict(),
        "escalation_cases": int(normalized["should_escalate"].fillna(False).sum()),
        "warnings": list(dict.fromkeys([*_coverage_warnings(normalized), *quality["warnings"], *quality["errors"]])),
        "launch_eligible": quality["launch_eligible"],
        "quality_report": quality,
    }


def dataset_quality_report(
    df: pd.DataFrame,
    *,
    available_sources: list[str] | set[str] | tuple[str, ...] | None = None,
    required_categories: set[str] | None = None,
    minimum_launch_cases: int = 30,
    candidate_tuned_on_dataset: bool = False,
) -> dict[str, Any]:
    """Assess whether a dataset is suitable evidence for a launch decision."""
    errors: list[str] = []
    warnings: list[str] = []
    source_report = df.attrs.get("source_quality_report") if hasattr(df, "attrs") else None
    if df.empty:
        return {
            "launch_eligible": False,
            "errors": ["Dataset is empty."],
            "warnings": [],
            "case_count": 0,
            "missing_categories": sorted(required_categories or REQUIRED_LAUNCH_CATEGORIES),
            "version": version_hash({"empty": True}),
        }
    for field in ["severity", "locale", "environment"]:
        if field not in df or bool(df[field].apply(_blank).any()):
            errors.append(f"Every case must include a non-empty {field} field for launch evidence.")
    if "case_id" in df:
        duplicated_ids = sorted(
            df.loc[df["case_id"].astype(str).duplicated(keep=False), "case_id"].astype(str).unique()
        )
        if duplicated_ids:
            errors.append(f"Duplicate case IDs: {duplicated_ids[:10]}")
    normalized_questions = df.get("question", pd.Series(dtype=str)).astype(str).map(_normalized_case_text)
    duplicated_questions = sorted(df.loc[normalized_questions.duplicated(keep=False), "question"].astype(str).unique())
    if duplicated_questions:
        errors.append(f"Duplicate evaluation cases: {duplicated_questions[:5]}")
    severities = set(df.get("severity", pd.Series(dtype=str)).astype(str).str.lower())
    if "critical" not in severities:
        errors.append("No critical-severity cases are present; critical launch risks are untested.")
    taxonomy: set[str] = set()
    for _, row in df.iterrows():
        taxonomy.add(_taxonomy_token(row.get("category", "")))
        for tag in parse_list(row.get("tags", [])):
            taxonomy.add(_taxonomy_token(tag))
    expected_categories = required_categories or REQUIRED_LAUNCH_CATEGORIES
    missing_categories = sorted(category for category in expected_categories if category not in taxonomy)
    if missing_categories:
        errors.append(f"Required risk categories are absent: {missing_categories}")
    if available_sources is not None:
        normalized_sources = {_normalized_case_text(source) for source in available_sources}
        missing_sources: dict[str, list[str]] = {}
        for _, row in df.iterrows():
            expected = parse_list(row.get("expected_sources", row.get("expected_source", [])))
            unknown = [
                str(source)
                for source in expected
                if _normalized_case_text(source) not in normalized_sources
                and _normalized_case_text(source) not in {"out of scope", "none", "missing evidence"}
            ]
            if unknown:
                missing_sources[str(row.get("case_id") or row.get("question"))] = unknown
        if missing_sources:
            errors.append(f"Expected sources do not exist in the knowledge-base snapshot: {missing_sources}")
    if len(df) < minimum_launch_cases:
        warnings.append(
            f"Dataset has {len(df)} cases; at least {minimum_launch_cases} are required for the configured launch gate."
        )
    splits = set(df.get("split", pd.Series(dtype=str)).astype(str).str.lower())
    if not splits & {"holdout", "test"}:
        errors.append("No held-out/test split is present for launch evidence.")
    if candidate_tuned_on_dataset:
        disclosure = df.get("tuning_disclosure", pd.Series([""] * len(df), index=df.index))
        if bool(disclosure.apply(_blank).all()):
            errors.append("Candidate tuning used this dataset but no tuning disclosure was recorded.")
    if "purpose" not in df or bool(df["purpose"].apply(_blank).any()):
        warnings.append("Every case should state its distinct evaluation purpose.")
    if "severity_rationale" not in df or bool(df["severity_rationale"].apply(_blank).any()):
        warnings.append("Every case should explain its severity rationale.")
    if "source_expectation" not in df or bool(df["source_expectation"].apply(_blank).any()):
        warnings.append("Every case should state the expected source behavior.")
    if isinstance(source_report, dict):
        errors.extend(str(item) for item in source_report.get("errors", []))
        warnings.extend(str(item) for item in source_report.get("warnings", []))
    errors = list(dict.fromkeys(errors))
    warnings = list(dict.fromkeys(warnings))
    payload = {
        "launch_eligible": not errors and len(df) >= minimum_launch_cases,
        "errors": errors,
        "warnings": warnings,
        "case_count": len(df),
        "critical_case_count": int(
            (df.get("severity", pd.Series(dtype=str)).astype(str).str.lower() == "critical").sum()
        ),
        "missing_categories": missing_categories,
        "candidate_tuning_disclosed": not candidate_tuned_on_dataset or not any("tuning" in error for error in errors),
    }
    payload["version"] = version_hash(payload)
    return payload


def parse_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if _blank(value):
        return []
    text = str(value).strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"must be valid JSON array: {exc.msg}") from exc
        if not isinstance(parsed, list):
            raise ValueError("must be a JSON array")
        return parsed
    return [part.strip() for part in text.split("|") if part.strip()]


def parse_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if _blank(value):
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise ValueError(f"must be valid JSON object: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("must be a JSON object")
    return parsed


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return str(value).strip() == ""


def _coverage_warnings(df: pd.DataFrame) -> list[str]:
    warnings: list[str] = []
    if len(df) < 30:
        warnings.append("Fewer than 30 cases: uncertainty is too high for a production launch decision.")
    category_counts = df["category"].value_counts()
    if not category_counts.empty and int(category_counts.min()) < 5:
        warnings.append("At least one category has fewer than 5 cases.")
    if "critical" not in set(df["severity"]):
        warnings.append("No critical-severity cases are present.")
    if not bool(df["should_escalate"].fillna(False).any()):
        warnings.append("No positive escalation cases are present.")
    if not bool((~df["should_escalate"].fillna(False)).any()):
        warnings.append("No negative escalation cases are present.")
    return warnings


def _normalized_case_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _taxonomy_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
