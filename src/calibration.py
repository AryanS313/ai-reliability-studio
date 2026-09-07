from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from src import config
from src.scoring import EVALUATOR_VERSION, LABEL_SEMANTICS_VERSION
from src.security import validate_upload
from src.versioning import version_hash


@dataclass(frozen=True)
class EvaluatorThresholdConfiguration:
    name: str = "production-defaults"
    thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "claim_support_overlap": 0.42,
            "claim_contradiction_overlap": 0.30,
            "claim_candidate_overlap": 0.12,
            "answer_incomplete_coverage": 0.40,
            "answer_aligned_coverage": 0.72,
        }
    )

    def __post_init__(self) -> None:
        for key, value in self.thresholds.items():
            if not 0 <= float(value) <= 1:
                raise ValueError(f"Evaluator threshold {key!r} must be between 0 and 1.")

    @property
    def version(self) -> str:
        return version_hash(asdict(self))


@dataclass(frozen=True)
class CalibrationRequirements:
    minimum_reviewed_cases: int = 30
    minimum_positive_cases: int = 5
    minimum_negative_cases: int = 5
    minimum_precision: float = 0.90
    minimum_recall: float = 0.80
    maximum_false_positive_rate: float = 0.05


DEFAULT_CALIBRATION_LABELS = (
    "privacy_violation",
    "policy_contradiction",
    "unsafe_response",
    "unsupported_claim",
    "citation_failure",
    "retrieval_failure",
    "escalation_failure",
)
CALIBRATION_UPLOAD_EXTENSIONS = {".csv", ".json", ".jsonl"}


def read_calibration_dataset(filename: str, data: bytes) -> pd.DataFrame:
    safe_name = validate_upload(
        filename,
        data,
        allowed_extensions=CALIBRATION_UPLOAD_EXTENSIONS,
        max_bytes=config.MAX_UPLOAD_BYTES,
    )
    suffix = Path(safe_name).suffix.lower()
    try:
        if suffix == ".csv":
            frame = pd.read_csv(BytesIO(data))
        elif suffix == ".jsonl":
            records = [json.loads(line) for line in data.decode("utf-8-sig").splitlines() if line.strip()]
            frame = pd.DataFrame(records)
        else:
            value = json.loads(data.decode("utf-8-sig"))
            frame = pd.DataFrame(value if isinstance(value, list) else value.get("reviews", []))
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("Calibration upload could not be parsed safely.") from exc
    if len(frame) > config.MAX_DATASET_ROWS:
        raise ValueError(f"Calibration upload exceeds the {config.MAX_DATASET_ROWS} row limit.")
    return frame


def calibrate_evaluators(
    reviewed: pd.DataFrame,
    *,
    labels: tuple[str, ...] | list[str] | None = None,
    requirements: CalibrationRequirements | None = None,
    thresholds: EvaluatorThresholdConfiguration | None = None,
    evaluator_version: str | None = None,
    label_semantics_version: str | None = None,
) -> dict[str, Any]:
    """Compare automatic and human labels on a held-out labelled dataset.

    Metrics are descriptive observations only. This function never changes
    thresholds and never mutates historical runs.
    """
    requirements = requirements or CalibrationRequirements()
    thresholds = thresholds or EvaluatorThresholdConfiguration()
    required_columns = {"case_id", "split", "human_labels", "automatic_labels"}
    missing = sorted(required_columns - set(reviewed.columns))
    if missing:
        raise ValueError(f"Calibration dataset is missing columns: {missing}")
    if reviewed.empty:
        raise ValueError("Calibration dataset contains no reviews.")
    blank_case_ids = reviewed["case_id"].isna() | reviewed["case_id"].astype(str).str.strip().eq("")
    if bool(blank_case_ids.any()):
        raise ValueError("Calibration case IDs must be non-blank.")
    duplicate_ids = reviewed["case_id"].astype(str).duplicated(keep=False)
    if bool(duplicate_ids.any()):
        duplicates = sorted(reviewed.loc[duplicate_ids, "case_id"].astype(str).unique())
        raise ValueError(f"Calibration case IDs must be unique; duplicates: {duplicates[:10]}")
    held_out = reviewed[reviewed["split"].astype(str).str.lower().isin({"calibration", "holdout", "test"})].copy()
    if held_out.empty:
        raise ValueError("Calibration requires at least one calibration, holdout, or test split row.")
    selected_labels = tuple(labels or DEFAULT_CALIBRATION_LABELS)
    metrics: dict[str, dict[str, Any]] = {}
    limitations: list[str] = []
    for label in selected_labels:
        automatic = held_out["automatic_labels"].apply(lambda value, current=label: current in _labels(value))
        human = held_out["human_labels"].apply(lambda value, current=label: current in _labels(value))
        tp = int((automatic & human).sum())
        fp = int((automatic & ~human).sum())
        tn = int((~automatic & ~human).sum())
        fn = int((~automatic & human).sum())
        precision = _ratio(tp, tp + fp)
        recall = _ratio(tp, tp + fn)
        false_positive_rate = _ratio(fp, fp + tn)
        false_negative_rate = _ratio(fn, fn + tp)
        f1 = (
            _ratio(2 * precision * recall, precision + recall)
            if precision is not None and recall is not None and precision + recall
            else None
        )
        positive_cases = tp + fn
        negative_cases = tn + fp
        sample_sufficient = (
            len(held_out) >= requirements.minimum_reviewed_cases
            and positive_cases >= requirements.minimum_positive_cases
            and negative_cases >= requirements.minimum_negative_cases
        )
        thresholds_met = bool(
            sample_sufficient
            and precision is not None
            and recall is not None
            and false_positive_rate is not None
            and precision >= requirements.minimum_precision
            and recall >= requirements.minimum_recall
            and false_positive_rate <= requirements.maximum_false_positive_rate
        )
        if not sample_sufficient:
            limitations.append(
                f"{label}: sample is too small for calibration "
                f"({len(held_out)} reviewed, {positive_cases} positive, {negative_cases} negative)."
            )
        metrics[label] = {
            "confusion_matrix": {"true_positive": tp, "false_positive": fp, "true_negative": tn, "false_negative": fn},
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "false_positive_rate": false_positive_rate,
            "false_negative_rate": false_negative_rate,
            "reviewed_cases": len(held_out),
            "positive_cases": positive_cases,
            "negative_cases": negative_cases,
            "sample_sufficient": sample_sufficient,
            "requirements_met": thresholds_met,
        }
    version_bound = bool(evaluator_version and label_semantics_version)
    if not version_bound:
        limitations.append("Automatic labels lack an explicitly declared evaluator and label-semantics version.")
    status = (
        "calibrated"
        if version_bound and metrics and all(item["requirements_met"] for item in metrics.values())
        else "insufficiently_calibrated"
    )
    payload: dict[str, Any] = {
        "status": status,
        "reviewed_cases": len(held_out),
        "excluded_non_holdout_cases": len(reviewed) - len(held_out),
        "held_out_splits": sorted(set(held_out["split"].astype(str).str.lower())),
        "threshold_version": thresholds.version,
        "evaluator_version": evaluator_version,
        "label_semantics_version": label_semantics_version,
        "reviewed_dataset_hash": version_hash(held_out.to_dict(orient="records")),
        "threshold_configuration": asdict(thresholds),
        "requirements": asdict(requirements),
        "evaluators": metrics,
        "limitations": sorted(set(limitations)),
        "statistical_claim": "Descriptive observed metrics only; no confidence claim is made without a separate power analysis.",
    }
    payload["calibration_version"] = version_hash(payload)
    return payload


def uncalibrated_status(thresholds: EvaluatorThresholdConfiguration | None = None) -> dict[str, Any]:
    thresholds = thresholds or EvaluatorThresholdConfiguration()
    payload = {
        "status": "insufficiently_calibrated",
        "reviewed_cases": 0,
        "threshold_version": thresholds.version,
        "evaluator_version": EVALUATOR_VERSION,
        "label_semantics_version": LABEL_SEMANTICS_VERSION,
        "limitations": ["No held-out human-labelled calibration result was attached to this run."],
        "statistical_claim": "No statistical confidence claim is available.",
    }
    payload["calibration_version"] = version_hash(payload)
    return payload


def validate_calibration_for_run(
    result: dict[str, Any],
    thresholds: EvaluatorThresholdConfiguration,
    *,
    evaluator_version: str,
    label_semantics_version: str,
) -> None:
    """Reject stale or changed qualifying evidence before executing a target.

    The content hash binds the result, including its evaluator and label versions.
    It is an integrity check, not authentication of the reviewer or their labels.
    """
    if result.get("threshold_version") != thresholds.version:
        raise ValueError("Calibration result threshold version does not match this run's threshold configuration.")
    if result.get("status") != "calibrated":
        return
    if result.get("evaluator_version") != evaluator_version:
        raise ValueError("Calibration result evaluator version is missing or does not match this run's evaluator.")
    if result.get("label_semantics_version") != label_semantics_version:
        raise ValueError("Calibration result label-semantics version is missing or does not match this run.")
    content = {key: value for key, value in result.items() if key not in {"calibration_version", "calibration_id"}}
    if not result.get("calibration_version") or version_hash(content) != result["calibration_version"]:
        raise ValueError("Calibration result content hash is missing or does not match its version-bound evidence.")


def run_calibration_workflow(
    repository: Any,
    context: Any,
    reviewed: pd.DataFrame,
    *,
    evaluator_version: str,
    label_semantics_version: str = LABEL_SEMANTICS_VERSION,
    labels: tuple[str, ...] | list[str] | None = None,
    requirements: CalibrationRequirements | None = None,
    thresholds: EvaluatorThresholdConfiguration | None = None,
    dataset_version_id: int | None = None,
) -> dict[str, Any]:
    """Persist human reviews and their immutable calibration result."""
    thresholds = thresholds or EvaluatorThresholdConfiguration()
    result = calibrate_evaluators(
        reviewed,
        labels=labels,
        requirements=requirements,
        thresholds=thresholds,
        evaluator_version=evaluator_version,
        label_semantics_version=label_semantics_version,
    )
    records = reviewed.where(pd.notna(reviewed), None).to_dict(orient="records")
    for record in records:
        record["human_labels"] = sorted(_labels(record.get("human_labels")))
        record["automatic_labels"] = sorted(_labels(record.get("automatic_labels")))
    repository.save_calibration_reviews(context, records)
    calibration_id = repository.save_calibration_result(
        context,
        result,
        evaluator_version=evaluator_version,
        dataset_version_id=dataset_version_id,
    )
    return {**result, "calibration_id": calibration_id}


def _labels(value: Any) -> set[str]:
    if isinstance(value, list | tuple | set):
        return {str(item) for item in value}
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return set()
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {item.strip() for item in str(value).split(",") if item.strip()}
    return {str(item) for item in parsed} if isinstance(parsed, list) else set()


def _ratio(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 4) if denominator else None
