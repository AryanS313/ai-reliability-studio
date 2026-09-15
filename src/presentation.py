from __future__ import annotations

import ast
import json
import math
import re
from collections.abc import Mapping
from typing import Any

import pandas as pd

from src.provenance import evidence_frame
from src.security import redact_pii, redact_secrets

SUCCESS_STATUSES = {"passed", "completed", "success"}

_GATE_LABELS = {
    "minimum_overall_quality": "Overall answer quality",
    "minimum_groundedness": "Claims supported by sources",
    "minimum_citation_support": "Citations support the answer",
    "minimum_escalation_accuracy": "Correct handoff to a person",
    "maximum_severe_safety_failures": "Critical safety failures",
    "maximum_unsupported_claim_rate": "Answers with unsupported claims",
    "maximum_execution_error_rate": "Assistant calls that failed",
    "minimum_sample_size": "Distinct cases successfully evaluated",
    "maximum_latency_p95_ms": "Response time for 95% of calls",
    "maximum_cost_usd": "Total evaluation cost",
    "real_target_required": "Evidence from a real assistant",
    "quality_executions_present": "Answers available to evaluate",
    "verified_target_type": "Assistant connection recorded",
    "quality_measurements_complete": "Complete quality measurements",
    "evaluator_determinations_complete": "Unresolved findings reviewed",
    "minimum_evaluator_calibration": "Evaluator checked against human reviews",
    "dataset_launch_eligibility": "Cases suitable for a release decision",
    "required_category_coverage": "Required topics covered",
}
_GATE_EXPLANATIONS = {
    "real_target_required": "Sample answers demonstrate the workflow. They cannot establish the quality of a real assistant.",
    "quality_executions_present": "At least one assistant call must return an answer that can be evaluated. Failed calls do not receive quality scores.",
    "verified_target_type": "The record must show which real assistant produced the answers. Missing connection information prevents a release assessment.",
    "quality_measurements_complete": "Every evaluated answer needs valid quality measurements. Missing scores do not count as passing evidence.",
    "evaluator_determinations_complete": "Review answers the evaluator could not judge before using this run for a release decision.",
    "minimum_evaluator_calibration": "Every evaluated answer must use an evaluator checked against qualifying, independent human reviews.",
    "dataset_launch_eligibility": "Cases must meet requirements for risk coverage, source evidence, independent evaluation, and sample size.",
    "required_category_coverage": "The evaluation must cover every topic required by the team's release checks.",
}
_RATIO_METRICS = {
    "overall_score": "Overall answer quality",
    "overall_quality": "Overall answer quality",
    "expected_answer_match_score": "Match to expected behavior",
    "groundedness_score": "Claims supported by sources",
    "groundedness": "Claims supported by sources",
    "citation_correctness_score": "Citation support",
    "citation_support": "Citation support",
    "escalation_correctness_score": "Correct handoff to a person",
    "escalation_accuracy": "Correct handoff to a person",
    "source_retrieval_score": "Relevant source retrieval",
    "unsupported_claim_rate": "Answers with unsupported claims",
    "execution_error_rate": "Assistant calls that failed",
    "evaluator_confidence": "Evaluator confidence",
    "pass_rate": "Quality pass rate",
}
_COST_METRICS = {"estimated_cost", "total_cost_usd", "known_cost_usd", "cost_usd", "cost"}
_LATENCY_METRICS = {"latency_ms", "latency_p95_ms", "average_latency_ms", "p95_latency_ms", "mean_latency_ms"}
_COUNT_METRICS = {
    "sample_size": "Distinct cases successfully evaluated",
    "severe_safety_failures": "Critical safety failures",
    "unique_test_cases": "Distinct test cases",
    "total_executions": "Assistant calls",
    "quality_scored_executions": "Answers evaluated",
    "quality_passes": "Quality passes",
    "quality_failures": "Quality failures",
    "infrastructure_errors": "Failed assistant calls",
    "retries": "Retry attempts",
}
_VERSION_LABELS = {
    "dataset_version": "Evaluation cases",
    "prompt_version": "Assistant instructions",
    "target_version": "Assistant connection",
    "document_version": "Reference documents",
    "knowledge_base_version": "Reference library",
    "evaluator_version": "Evaluation method",
    "threshold_version": "Scoring settings",
    "calibration_version": "Human review calibration",
    "evaluation_configuration_version": "Run settings",
    "retrieval_configuration_version": "Source search settings",
    "gate_configuration_version": "Release checks",
}
_FAILURE_EXPLANATIONS = {
    "unsupported_claim": "A claim is not supported by the available sources",
    "evaluator_uncertain": "The evaluator could not confidently judge the answer; a person should review it",
    "policy_contradiction": "A checked condition in the answer conflicts with the policy reference",
    "unauthorized_decision": "The answer appears to make a decision that requires an authorized person",
    "missed_escalation": "The answer did not hand off a case that required a person",
    "excessive_escalation": "The answer handed off a case that did not require a person",
    "privacy_violation": "The answer may disclose private information",
    "prompt_injection_compliance": "The answer appears to follow an instruction that conflicts with the assistant's rules",
    "harmful_or_prohibited_action": "The answer appears to permit a harmful or prohibited action",
    "unacceptable_answer": "The answer matches behavior marked as unacceptable for this case",
    "unsafe_response": "A safety check found behavior that requires review before release",
    "retrieval_failure": "The assistant did not retrieve the expected source",
    "citation_failure": "A citation is missing, cannot be traced, or does not support the answer",
    "escalation_failure": "The handoff decision, destination, or urgency does not match the expected behavior",
    "infrastructure_failure": "The assistant call failed, so no answer quality was scored",
    "runtime_credential_disclosure": "The assistant returned a runtime credential; the response was withheld and the disclosure blocks release",
    "pii_email_format": "The answer contains an email address that may reveal personal information",
    "pii_phone_format": "The answer contains a phone number that may reveal personal information",
    "pii_account_number": "The answer contains an account number that may reveal private information",
    "pii_phone_context": "The answer contains a phone number that may reveal personal information",
    "pii_account_number_context": "The answer contains an account number that may reveal private information",
    "pii_government_id_ssn_format": "The answer contains what appears to be a government identity number",
    "pii_government_id_pan_format": "The answer contains what appears to be a government identity number",
    "pii_government_id_aadhaar_context": "The answer contains what appears to be a government identity number",
    "pii_payment_card_luhn_valid": "The answer contains what appears to be a payment card number",
    "unsupported_definitive_claim": "The answer states a conclusion without sufficient source support",
    "claim_requires_review": "A claim needs a person to check it against the source",
    "citation_support_unverified": "The evaluator could not verify whether the cited passage supports the claim",
    "retrieved_evidence_contradicts_claim": "A retrieved passage conflicts with a claim in the answer",
    "unsafe_unauthorized_decision_language": "The answer appears to approve or override a decision outside the assistant's authority",
    "unsafe_prompt_or_secret_disclosure_language": "The answer appears to reveal hidden instructions or a secret",
    "unsafe_prohibited_action_language": "The answer appears to encourage a prohibited action",
    "expected_source_not_retrieved": "The source required for this case was not retrieved",
    "citation_missing": "The answer does not include a required citation",
    "citation_source_unresolved": "The cited source could not be matched to a supplied document",
    "citation_provenance_unresolved": "The cited passage could not be traced to its source",
    "citation_does_not_support_claim": "The cited passage does not support the claim",
    "escalation_unable_to_determine": "The evaluator could not determine whether the answer correctly handed off the case",
    "escalation_decision_mismatch": "The answer's handoff decision differs from the expected behavior",
    "escalation_destination_mismatch": "The answer directs the case to the wrong person or team",
    "escalation_urgency_mismatch": "The answer gives the handoff the wrong urgency",
    "required_escalation_missing": "The answer omits a required handoff to a person",
    "unnecessary_escalation_detected": "The answer requests a handoff that the reference does not require",
    "unsafe_response_component_detected": "The answer includes behavior flagged by a safety check",
    "answer_contradicts_same_proposition": "The answer conflicts with the reference on the same policy condition",
    "answer_empty_or_unusable": "The answer is empty or cannot be compared with the reference",
    "answer_lexically_matches_checked_constraints": "The checked reference conditions match the answer; other checks may still fail",
    "answer_missing_expected_constraint": "The answer may omit a required condition or exception from the reference",
    "answer_partially_covers_expected_behavior": "The answer covers only part of the expected behavior",
    "answer_has_insufficient_subject_overlap": "A person should check whether the answer addresses the same subject as the reference",
    "answer_differs_without_proven_conflict": "The answer differs from the reference without a proven contradiction; review both against the source",
    "answer_cannot_be_deterministically_aligned": "The evaluator cannot reliably align the answer with the reference",
    "contradiction_opposite_polarity_same_proposition": "The answer reverses whether a policy condition is allowed or required",
    "contradiction_numeric_constraint_same_proposition": "The answer gives a conflicting amount, deadline, or numeric limit",
    "contradiction_numeric_relation_same_proposition": "The answer reverses the direction of a policy threshold",
    "contradiction_exemption_restricted_same_proposition": "The answer restricts an exception allowed by the reference",
    "contradiction_exception_removed_same_proposition": "The answer removes a required policy exception",
}
_BEHAVIOR_LABELS = {
    "answer": "Answer the question using the available evidence.",
    "answer_and_escalate": "Answer what the evidence supports and hand off the case to a person.",
    "refuse_unsupported": "Decline to make claims that the evidence does not support.",
    "insufficient_evidence": "Explain that the available evidence is insufficient to answer.",
    "refuse_and_escalate": "Decline the request and hand off the case to an authorized person.",
    "ignore_document_instruction": "Ignore instructions embedded in source documents that conflict with the assistant's rules.",
    "identify_conflict_and_escalate": "Explain the conflicting evidence and ask an authorized person to resolve it.",
    "escalate": "Hand off the case to an authorized person.",
    "clarify": "Ask for the information needed to answer safely.",
    "refuse": "Decline the request without providing the prohibited information or action.",
    "execution_error": "This sample demonstrates a failed assistant call.",
    "fail_quality": "This sample demonstrates an answer that fails a quality check.",
}
_RECOMMENDED_ACTIONS = {
    "Expected Answer Mismatch": "Compare the answer and expected behavior with the source. Ask a domain reviewer to confirm any missing condition before changing the instructions.",
    "Source Retrieval Failure": "Review the source passages and try finding more passages. Check that the reference document contains the information needed to answer.",
    "Citation Failure": "Require the assistant to cite the passage supporting each answer. Check that the cited source is available and actually supports the claim.",
    "Escalation Failure": "Clarify when the assistant must hand off a case, which person or team should receive it, and how urgently they should respond.",
    "Hallucination Risk": "Require the assistant to answer from the provided sources and explain when the evidence is insufficient.",
    "Policy Contradiction": "Correct the conflicting instruction or reference. Preserve the policy's conditions, limits, and exceptions, then run this case again.",
    "Unsupported Claim": "Remove conclusions the sources do not support and require evidence for each claim. Run the affected cases again.",
    "Unauthorized Decision": "Clarify which decisions require an authorized person. Prevent the assistant from approving or overriding those decisions.",
    "Missed Escalation": "Require a handoff to the right person or team for this type of case and explain when a prompt response is necessary.",
    "Excessive Escalation": "Clarify which routine questions the assistant can answer directly from the sources.",
    "Prompt Injection Compliance": "Require the assistant to ignore user or document instructions that conflict with its rules or request private instructions and secrets.",
    "Privacy Violation": "Remove personal details and secrets from the answer. Review what the assistant can access and verify that private information is withheld before release.",
    "Harmful or Prohibited Action": "Require the assistant to decline prohibited actions and hand sensitive cases to an authorized reviewer.",
    "Execution Error": "Check the assistant connection and credentials. Follow the connection error's recovery steps, then retry the failed cases.",
    "Incomplete Answer": "Clarify what a complete answer must include. Check that the sources and expected behavior cover those requirements.",
    "Needs Review": "Ask a domain reviewer to compare the answer with the exact source passages and record whether each claim is supported. Different wording alone does not prove a defect.",
    "Latency Issue": "Try sending fewer or shorter source passages, or use a faster assistant, then compare response times and answer quality.",
    "Cost Issue": "Try shorter instructions, fewer source passages, or a less expensive model, then compare costs and answer quality.",
    "Passed": "No correction was identified by these checks. Review the evidence and limitations before relying on the answer.",
}


def metric_label(name: str) -> str:
    """Name a known measurement without exposing a backend key."""
    if name in _GATE_LABELS:
        return _GATE_LABELS[name]
    if name in _RATIO_METRICS:
        return _RATIO_METRICS[name]
    if name in _COST_METRICS:
        return "Evaluation cost"
    if name in _LATENCY_METRICS:
        return "Response time for 95% of calls" if "p95" in name else "Response time"
    return _COUNT_METRICS.get(name, "Additional measurement")


def metric_display(name: str, value: Any, *, delta: bool = False) -> str:
    """Format backend ratios, dollars and milliseconds; never replace unknowns with zero."""
    number = _number(value)
    if number is None:
        return "Not measured"
    metric = name.removeprefix("minimum_").removeprefix("maximum_")
    sign = "+" if delta and number > 0 else ""
    if metric in _RATIO_METRICS:
        unit = " percentage points" if delta else "%"
        return f"{sign}{_decimal(number * 100)}{unit}"
    if metric in _COST_METRICS:
        prefix = "−" if number < 0 else sign
        return f"{prefix}${_decimal(abs(number), minimum_decimals=2)}"
    if metric in _LATENCY_METRICS:
        return f"{sign}{_decimal(number)} ms"
    return f"{sign}{_decimal(number)}"


def readiness_check_rows(evaluation: Mapping[str, Any]) -> list[dict[str, str]]:
    """Present the recorded gate decisions; do not recompute or soften them."""
    gates = evaluation.get("gate_results")
    if not isinstance(gates, list | tuple) or not gates:
        return [
            {
                "Check": "Release checks",
                "Result": "Not available",
                "What it means": "No release checks were recorded. Run an evaluation before drawing a conclusion.",
            }
        ]
    rows = []
    for gate in gates:
        if not isinstance(gate, Mapping):
            rows.append(
                {
                    "Check": "Additional release check",
                    "Result": "Unknown",
                    "What it means": "This check was not recorded in a usable form. Review the evidence before drawing a conclusion.",
                }
            )
            continue
        name = str(gate.get("name") or "")
        passed = gate.get("passed")
        result = "Met" if passed is True else "Not met" if passed is False else "Unknown"
        explanation = _GATE_EXPLANATIONS.get(
            name, "An additional release requirement was checked. Review the evidence with the evaluation owner."
        )
        if (
            name in _GATE_LABELS
            and (name.startswith("minimum_") or name.startswith("maximum_"))
            and name not in _GATE_EXPLANATIONS
        ):
            actual, threshold = _number(gate.get("actual")), _number(gate.get("threshold"))
            direction = "at least" if name.startswith("minimum_") else "at most"
            required = metric_display(name, threshold)
            if actual is None and threshold is None:
                result = "Unknown"
                explanation = "The measurement and required limit were not recorded; this check cannot be confirmed."
            elif actual is None:
                result = "Unknown"
                explanation = (
                    f"Not measured; requires {direction} {required}. Missing evidence cannot satisfy this check."
                )
            elif threshold is None:
                result = "Unknown"
                explanation = f"Measured {metric_display(name, actual)}. The required limit was not recorded; this check cannot be confirmed."
            else:
                explanation = f"Measured {metric_display(name, actual)}; requires {direction} {required}."
                if passed is False and actual == threshold:
                    explanation += " The recorded check failed; displayed measurements may be rounded."
        elif name == "required_category_coverage":
            missing = _missing_categories(gate)
            if missing:
                explanation = "Add cases for: " + ", ".join(missing) + "."
            elif passed is True:
                explanation = "All topics required by the team's release checks are covered."
        rows.append(
            {
                "Check": _GATE_LABELS.get(name, "Additional release check"),
                "Result": result,
                "What it means": explanation,
            }
        )
    return rows


def candidate_title(candidate_or_evaluation: Mapping[str, Any] | None) -> str:
    """Use recorded human names, never candidate hashes or generated version labels."""
    if not isinstance(candidate_or_evaluation, Mapping):
        return "Assistant evaluation"
    nested = candidate_or_evaluation.get("candidate")
    candidate = nested if isinstance(nested, Mapping) else candidate_or_evaluation
    target_type = candidate.get("target_type")
    prompt = _human_name(candidate.get("prompt_name"))
    prompt = {
        "Current Prompt": "Current instructions",
        "Improved Prompt": "Candidate instructions",
        "Candidate Prompt": "Candidate instructions",
    }.get(prompt, prompt)
    if prompt.lower() == "unnamed prompt":
        prompt = ""
    if target_type == "synthetic_mock":
        assistant = "Sample assistant"
    else:
        target = _human_name(candidate.get("target_name"))
        model = _human_name(candidate.get("model_name"))
        if target.lower().replace("_", " ") in {"external api", "foundation model", "unknown target"}:
            target = ""
        if model.lower() in {"unknown model", "unknown", "none", "nan"}:
            model = ""
        assistant = target or (model if target_type == "foundation_model" else "") or "Connected assistant"
        if model and target_type == "foundation_model" and model.lower() != assistant.lower():
            assistant += f" · {model}"
    return " · ".join(part for part in [assistant, prompt] if part)


def version_difference_rows(comparison: Mapping[str, Any]) -> list[dict[str, str]]:
    """Describe whether recorded settings match without displaying their hashes."""
    versions = comparison.get("versions")
    if not isinstance(versions, Mapping):
        return []
    baseline = versions.get("baseline")
    candidate = versions.get("candidate")
    baseline = baseline if isinstance(baseline, Mapping) else {}
    candidate = candidate if isinstance(candidate, Mapping) else {}
    rows = []
    for field in dict.fromkeys([*_VERSION_LABELS, *baseline, *candidate]):
        if field not in baseline and field not in candidate:
            continue
        before, after = _recorded_versions(baseline.get(field)), _recorded_versions(candidate.get(field))
        result = (
            "Not enough information"
            if len(before) != 1 or len(after) != 1
            else "Unchanged"
            if before == after
            else "Changed"
        )
        rows.append(
            {
                "Setting": _VERSION_LABELS.get(field, "Additional setting"),
                "Baseline": _version_presence(before),
                "Candidate": _version_presence(after),
                "Comparison": result,
            }
        )
    return rows


def _decimal(number: float, *, minimum_decimals: int = 0) -> str:
    rendered = f"{number:,.12f}".rstrip("0").rstrip(".")
    if number != 0 and float(rendered.replace(",", "")) == 0:
        return f"{number:.3g}"
    if minimum_decimals:
        whole, _, fraction = rendered.partition(".")
        return whole + "." + fraction.ljust(minimum_decimals, "0")
    return rendered


def _human_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = safe_display_text(value).strip()
    if re.fullmatch(r"(?:[a-z]+[-_:])?[0-9a-f]{8,}|[0-9a-f-]{32,}", text, re.IGNORECASE):
        return ""
    text = re.sub(r"\s*[·|]\s*v[0-9a-f]{8,}\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b[0-9a-f]{32,}\b|\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", "", text, flags=re.IGNORECASE)
    return text


def _recorded_versions(value: Any) -> set[str]:
    values = value if isinstance(value, list | tuple | set) else [value]
    return {str(item) for item in values if isinstance(item, str) and item.strip()}


def _version_presence(versions: set[str]) -> str:
    return (
        "Not recorded" if not versions else "Recorded" if len(versions) == 1 else f"{len(versions)} different versions"
    )


def _missing_categories(gate: Mapping[str, Any]) -> list[str]:
    missing = gate.get("missing_categories")
    explanation = gate.get("explanation")
    if missing is None and isinstance(explanation, str) and explanation.startswith("Missing categories: "):
        try:
            missing = ast.literal_eval(explanation.removeprefix("Missing categories: "))
        except (SyntaxError, ValueError):
            return []
    return [_human_name(item) for item in missing if _human_name(item)] if isinstance(missing, list | tuple) else []


def execution_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Return consistent run counts and context-sensitive completion wording."""
    df = evidence_frame(df)
    if df.empty:
        return {
            "unique_test_cases": 0,
            "total_executions": 0,
            "quality_scored_executions": 0,
            "quality_passes": 0,
            "quality_failures": 0,
            "infrastructure_errors": 0,
            "cancelled_executions": 0,
            "skipped_executions": 0,
            "retries": 0,
            "message": "Run complete: no executions were created.",
        }
    statuses = df.get("execution_status", pd.Series(["passed"] * len(df), index=df.index)).fillna("").astype(str)
    quality_mask = statuses.isin(SUCCESS_STATUSES)
    failure_types = df.get("failure_type", pd.Series(["Passed"] * len(df), index=df.index)).fillna("").astype(str)
    quality_passes = int((quality_mask & failure_types.eq("Passed")).sum())
    quality_failures = int((quality_mask & ~failure_types.eq("Passed")).sum())
    cancelled = int(statuses.eq("cancelled").sum())
    skipped = int(statuses.eq("skipped").sum())
    infrastructure = int((~quality_mask & ~statuses.isin({"cancelled", "skipped"})).sum())
    attempts = pd.to_numeric(df.get("attempt_count", pd.Series([1] * len(df), index=df.index)), errors="coerce").fillna(
        1
    )
    retries = int(attempts.sub(1).clip(lower=0).sum())
    unique_column = "case_id" if "case_id" in df else "question"
    counts: dict[str, Any] = {
        "unique_test_cases": int(df[unique_column].nunique()) if unique_column in df else len(df),
        "total_executions": len(df),
        "quality_scored_executions": int(quality_mask.sum()),
        "quality_passes": quality_passes,
        "quality_failures": quality_failures,
        "infrastructure_errors": infrastructure,
        "cancelled_executions": cancelled,
        "skipped_executions": skipped,
        "retries": retries,
    }
    parts = [f"Run complete: {len(df)} total executions"]
    if quality_mask.all():
        parts.append("all target calls completed")
    else:
        parts.append(f"{int(quality_mask.sum())} were quality-scored")
    parts.append(f"{quality_passes} quality passes")
    parts.append(f"{quality_failures} quality failures")
    if infrastructure:
        parts.append(f"{infrastructure} infrastructure errors were excluded from quality scoring")
    if cancelled:
        parts.append(f"{cancelled} cancelled")
    if skipped:
        parts.append(f"{skipped} skipped")
    if retries:
        parts.append(f"{retries} retries")
    counts["message"] = "; ".join(parts) + "."
    return counts


def failure_presentation(row: Mapping[str, Any]) -> dict[str, Any]:
    failure_type = str(row.get("failure_type") or "Evaluation failure")
    labels = _as_list(row.get("failure_labels"))
    reason_codes = _as_list(row.get("failure_reason_codes"))
    evidence = _jsonish(row.get("failure_evidence"))
    score_explanation = _jsonish(row.get("score_explanation"))
    expected = safe_display_text(row.get("expected_answer"))
    if not expected:
        behavior = safe_display_text(row.get("expected_behavior"))
        expected = _BEHAVIOR_LABELS.get(
            behavior, behavior if "_" not in behavior else "Review the expected behavior with the case owner."
        )
    actual = safe_display_text(row.get("actual_answer"))
    confidence = _number(row.get("evaluator_confidence"))
    calibration = str(row.get("calibration_status") or "not_recorded")
    root_cause = failure_type if failure_type in _RECOMMENDED_ACTIONS else "Answer needs review"
    if failure_type == "Passed":
        root_cause = "No quality failure"
    root_cause = safe_display_text(root_cause)
    reason = _why_failed(failure_type, labels, reason_codes, score_explanation)
    limitations = _limitations(confidence, calibration, row)
    sources = []
    for chunk in _as_list_of_dicts(row.get("retrieved_chunks")):
        sources.append(
            {
                "document": _human_name(chunk.get("source_name"))
                or _human_name(chunk.get("filename"))
                or "Reference document",
                "location": _source_location(chunk),
                "passage": safe_display_text(chunk.get("chunk_text") or chunk.get("text") or ""),
                "similarity": _number(chunk.get("similarity")),
            }
        )
    return {
        "summary": f"{root_cause}.",
        "root_cause": root_cause,
        "why_failed": reason,
        "expected_behavior": expected or "No reference behavior was recorded.",
        "actual_behavior": actual or "No answer was returned.",
        "source_passages": sources,
        "confidence": confidence,
        "limitations": limitations,
        "recommended_action": _RECOMMENDED_ACTIONS.get(
            failure_type,
            "Review the answer, source passages, assistant instructions, and expected behavior with the evaluation owner.",
        ),
        "raw_evaluator_output": safe_nested({"failure_evidence": evidence, "score_explanation": score_explanation}),
        "final_prompt": safe_display_text(row.get("final_prompt")),
        "technical_metadata": safe_nested(
            {
                key: row.get(key)
                for key in [
                    "run_id",
                    "case_id",
                    "candidate_id",
                    "prompt_version",
                    "target_version",
                    "target_type",
                    "model_name",
                    "evaluator_version",
                    "threshold_version",
                    "calibration_version",
                    "execution_status",
                    "error_code",
                ]
                if key in row
            }
        ),
    }


def safe_display_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return redact_pii(str(redact_secrets(str(value), preserve_references=False)))


def safe_nested(value: Any) -> Any:
    redacted = redact_secrets(value, preserve_references=False)
    if isinstance(redacted, dict):
        return {str(key): safe_nested(item) for key, item in redacted.items()}
    if isinstance(redacted, list):
        return [safe_nested(item) for item in redacted]
    if isinstance(redacted, tuple):
        return tuple(safe_nested(item) for item in redacted)
    return redact_pii(redacted) if isinstance(redacted, str) else redacted


def _why_failed(
    failure_type: str,
    labels: list[str],
    reason_codes: list[str],
    score_explanation: Any,
) -> str:
    details = []
    unknown_finding = False
    for finding in [*labels, *reason_codes]:
        explanation = _FAILURE_EXPLANATIONS.get(finding)
        if explanation and explanation not in details:
            details.append(explanation)
        elif not explanation:
            unknown_finding = True
    if unknown_finding:
        details.append("An additional finding requires review; inspect the answer and source")
    if isinstance(score_explanation, dict):
        correctness = score_explanation.get("correctness", {})
        relationship = score_explanation.get("answer_relationship") or (
            correctness.get("relationship") if isinstance(correctness, dict) else None
        )
        if isinstance(relationship, dict) and relationship.get("classification"):
            explanations = {
                "contradiction": "A checked policy condition conflicts with the reference; inspect the exact clauses.",
                "missing_constraint": "The answer may omit a required condition or exception from the reference.",
                "incomplete_answer": "The answer covers only part of the expected behavior.",
                "irrelevant_detail": "The answer has little wording overlap with the reference; a reviewer must check whether it answers the same question.",
                "expected_answer_mismatch": "The answer differs from the reference without a proven contradiction; review both against the source.",
                "ambiguous_answer": "The evaluator cannot reliably align the answer with the reference; human review is needed.",
                "aligned": "The answer matches the checked reference conditions; other checks may still fail.",
            }
            details.append(
                explanations.get(str(relationship["classification"]), "The reference comparison requires review.")
            )
    return (
        ". ".join(detail.rstrip(".") for detail in details) + "."
        if details
        else "No quality failure was detected by these checks; review the evidence before relying on the answer."
        if failure_type == "Passed"
        else "The answer requires review; compare it with the expected behavior and source evidence."
    )


def _source_location(chunk: Mapping[str, Any]) -> str:
    page = chunk.get("page")
    section = _human_name(chunk.get("section"))
    parts = []
    if isinstance(page, str | int | float) and not isinstance(page, bool):
        page_text = _human_name(str(page))
        if page_text and page_text.lower() not in {"nan", "none", "inf"}:
            parts.append(page_text if page_text.lower().startswith("page ") else f"Page {page_text}")
    if section:
        parts.append(section)
    return " · ".join(parts) or "Retrieved passage"


def _limitations(confidence: float | None, calibration: str, row: Mapping[str, Any]) -> list[str]:
    limitations = []
    if confidence is None:
        limitations.append("Evaluator confidence was not recorded; human review is recommended.")
    elif confidence < 0.7:
        limitations.append("Evaluator confidence is low; treat this result as a review candidate.")
    if calibration != "calibrated":
        limitations.append("This evaluator was not linked to a qualifying held-out human calibration.")
    if str(row.get("target_type") or "") == "synthetic_mock":
        limitations.append("Synthetic evidence demonstrates workflow only and cannot establish model quality.")
    return limitations or ["Automated evaluation remains an estimate; inspect the cited evidence before acting."]


def _jsonish(value: Any) -> Any:
    if isinstance(value, dict | list | tuple):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return {}
    try:
        return json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return {"value": safe_display_text(value)}


def _as_list(value: Any) -> list[str]:
    parsed = _jsonish(value)
    if isinstance(parsed, list | tuple):
        return [safe_display_text(item) for item in parsed]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _as_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    parsed = _jsonish(value)
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list | tuple) else []


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None
