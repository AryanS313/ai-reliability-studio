from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from src import config
from src.domain import ROLE_RANK, Role


class AuthorizationError(PermissionError):
    pass


class UploadSecurityError(ValueError):
    pass


SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.I),
    re.compile(r"\b(?:api[_-]?key|authorization|token)\s*[:=]\s*[^\s,;]+", re.I),
]
SECRET_REFERENCE_PATTERN = re.compile(r"\bsecret://[A-Za-z0-9_.-]+\b", re.I)
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
PAN_INDIA_PATTERN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
NUMBER_CANDIDATE_PATTERN = re.compile(r"(?<![A-Za-z0-9])\+?(?:\d[\s().-]?){6,19}(?![A-Za-z0-9])")
STRUCTURED_CITATION_PATTERN = re.compile(
    r"\[(?:source|citation)\s*:[^\]]*(?:chunk|passage|id)\s*:[^\]]+\]",
    re.I,
)
UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.I,
)
HASH_PATTERN = re.compile(r"\b[0-9a-f]{24,128}\b", re.I)
TIMESTAMP_PATTERN = re.compile(r"\b(?:1[5-9]|2\d)\d{8}(?:\d{3})?\b")

PHONE_CONTEXT = {"phone", "telephone", "tel", "mobile", "cell", "whatsapp", "call", "contact"}
ACCOUNT_CONTEXT = {
    "account",
    "acct",
    "bank account",
    "account number",
    "routing",
    "iban",
    "beneficiary",
}
AADHAAR_CONTEXT = {"aadhaar", "aadhar", "uid", "uidai", "identity number", "government id"}


def require_role(actual: Role | str, minimum: Role | str) -> None:
    actual_role = actual if isinstance(actual, Role) else Role(str(actual))
    minimum_role = minimum if isinstance(minimum, Role) else Role(str(minimum))
    if ROLE_RANK[actual_role] < ROLE_RANK[minimum_role]:
        raise AuthorizationError(
            f"Role {actual_role.value} cannot perform an operation requiring {minimum_role.value}."
        )


def sanitize_filename(filename: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(filename or ""))
    name = Path(normalized.replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    name = re.sub(r"\s+", " ", name)
    if not name or name in {".", ".."}:
        raise UploadSecurityError("Filename is empty or unsafe.")
    if len(name) > 180:
        stem, suffix = os.path.splitext(name)
        name = stem[: max(1, 180 - len(suffix))] + suffix[:20]
    return name


def validate_upload(
    filename: str,
    data: bytes,
    *,
    allowed_extensions: Iterable[str],
    max_bytes: int | None = None,
) -> str:
    safe_name = sanitize_filename(filename)
    extension = Path(safe_name).suffix.lower()
    if extension not in set(allowed_extensions):
        raise UploadSecurityError(f"Unsupported file type: {extension or 'no extension'}")
    maximum = max_bytes if max_bytes is not None else config.MAX_UPLOAD_BYTES
    if len(data) > maximum:
        raise UploadSecurityError(f"File exceeds the {maximum} byte upload limit.")
    if not data:
        raise UploadSecurityError("Empty files are not accepted.")
    return safe_name


def validate_upload_batch(file_count: int) -> None:
    if file_count > config.MAX_DOCUMENTS_PER_UPLOAD:
        raise UploadSecurityError(
            f"Upload contains {file_count} documents; the limit is {config.MAX_DOCUMENTS_PER_UPLOAD}."
        )


def redact_secrets(value: Any, *, preserve_references: bool = True) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                item
                if preserve_references
                and _secret_key(str(key))
                and isinstance(item, str)
                and item.startswith("secret://")
                else "[REDACTED]"
                if _secret_key(str(key))
                else redact_secrets(item, preserve_references=preserve_references)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item, preserve_references=preserve_references) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item, preserve_references=preserve_references) for item in value)
    if not isinstance(value, str):
        return value
    text = value
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    if not preserve_references:
        text = SECRET_REFERENCE_PATTERN.sub("[REDACTED_SECRET_REFERENCE]", text)
    return text


def detect_pii(text: str) -> list[dict[str, Any]]:
    """Return redacted, structured evidence for high-precision PII findings.

    Findings intentionally omit the matched value. Structured citations, UUIDs,
    hashes, timestamps, and other internal identifiers are excluded before any
    numeric classification. Payment-card candidates must pass Luhn validation;
    phone and account-like numbers require contextual evidence.
    """
    value = text or ""
    excluded = _excluded_identifier_ranges(value)
    findings: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []

    for direct_kind, pattern, direct_reason_code in [
        ("email", EMAIL_PATTERN, "pii_email_format"),
        ("government_id_ssn", SSN_PATTERN, "pii_government_id_ssn_format"),
        ("government_id_pan_india", PAN_INDIA_PATTERN, "pii_government_id_pan_format"),
    ]:
        for match in pattern.finditer(value):
            if _overlaps(match.span(), excluded):
                continue
            findings.append(_pii_evidence(direct_kind, direct_reason_code, match.start(), match.end()))
            occupied.append(match.span())

    for match in NUMBER_CANDIDATE_PATTERN.finditer(value):
        span = match.span()
        if _overlaps(span, excluded) or _overlaps(span, occupied):
            continue
        raw = match.group(0)
        digits = re.sub(r"\D", "", raw)
        if not digits:
            continue
        context_terms = _nearby_context_terms(value, span)
        kind: str | None = None
        reason_code: str | None = None
        attributes: dict[str, Any] = {}
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            kind = "payment_card"
            reason_code = "pii_payment_card_luhn_valid"
            attributes["luhn_valid"] = True
        elif len(digits) == 12 and context_terms & AADHAAR_CONTEXT:
            kind = "government_id_aadhaar"
            reason_code = "pii_government_id_aadhaar_context"
        elif 6 <= len(digits) <= 18 and context_terms & ACCOUNT_CONTEXT:
            kind = "account_number"
            reason_code = "pii_account_number_context"
        elif 8 <= len(digits) <= 15 and (
            context_terms & PHONE_CONTEXT or (raw.strip().startswith("+") and len(digits) >= 10)
        ):
            kind = "phone"
            reason_code = "pii_phone_context"
        if kind and reason_code:
            findings.append(
                _pii_evidence(
                    kind,
                    reason_code,
                    match.start(),
                    match.end(),
                    context_terms=sorted(context_terms),
                    **attributes,
                )
            )
            occupied.append(span)
    return sorted(findings, key=lambda item: (int(item["start"]), str(item["type"])))


def redact_pii(text: str) -> str:
    output = text or ""
    findings = detect_pii(output)
    for finding in reversed(findings):
        start = int(finding["start"])
        end = int(finding["end"])
        replacement = f"[REDACTED_{str(finding['type']).upper()}]"
        output = output[:start] + replacement + output[end:]
    return output


def privacy_notice() -> str:
    return (
        "Documents, prompts, dataset inputs, and target responses are processed by this application and stored in the "
        "selected workspace. Direct-model requests are sent to the selected provider; external-target requests are sent "
        "to the configured endpoint. Do not submit proprietary or personal data until your deployment's access, retention, "
        "redaction, and provider agreements have been reviewed. API keys are resolved at runtime and are never persisted."
    )


def _secret_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z]", "", key.lower())
    return any(
        term in normalized
        for term in ["apikey", "authorization", "password", "secret", "token", "cookie", "credential", "sessionid"]
    )


def _pii_evidence(
    kind: str,
    reason_code: str,
    start: int,
    end: int,
    **attributes: Any,
) -> dict[str, Any]:
    return {
        "type": kind,
        "reason_code": reason_code,
        "start": start,
        "end": end,
        "length": end - start,
        "value": "[REDACTED]",
        **attributes,
    }


def _excluded_identifier_ranges(text: str) -> list[tuple[int, int]]:
    patterns = [STRUCTURED_CITATION_PATTERN, UUID_PATTERN, HASH_PATTERN, TIMESTAMP_PATTERN]
    return [match.span() for pattern in patterns for match in pattern.finditer(text or "")]


def _overlaps(span: tuple[int, int], ranges: list[tuple[int, int]]) -> bool:
    return any(span[0] < stop and span[1] > start for start, stop in ranges)


def _nearby_context_terms(text: str, span: tuple[int, int], radius: int = 64) -> set[str]:
    window = text[max(0, span[0] - radius) : min(len(text), span[1] + radius)].lower()
    candidates = PHONE_CONTEXT | ACCOUNT_CONTEXT | AADHAAR_CONTEXT
    return {term for term in candidates if re.search(rf"\b{re.escape(term)}\b", window)}


def _luhn_valid(digits: str) -> bool:
    if not digits.isdigit() or not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    parity = len(digits) % 2
    for index, character in enumerate(digits):
        number = int(character)
        if index % 2 == parity:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0
