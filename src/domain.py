from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class TargetType(str, Enum):
    SYNTHETIC = "synthetic_mock"
    FOUNDATION_MODEL = "foundation_model"
    EXTERNAL_API = "external_api"
    SAVED_RESPONSES = "saved_responses"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    RATE_LIMITED = "rate_limited"
    CANCELLED = "cancelled"
    INVALID_RESPONSE = "invalid_response"


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    UNVERIFIABLE = "unverifiable"


class DeterminationState(str, Enum):
    DETERMINED = "determined"
    UNABLE_TO_DETERMINE = "unable_to_determine"


class EscalationDecision(str, Enum):
    ESCALATE = "escalate"
    DO_NOT_ESCALATE = "do_not_escalate"
    UNABLE_TO_DETERMINE = "unable_to_determine"


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


ROLE_RANK = {
    Role.VIEWER: 10,
    Role.REVIEWER: 20,
    Role.EDITOR: 30,
    Role.ADMIN: 40,
    Role.OWNER: 50,
}


@dataclass(frozen=True)
class WorkspaceContext:
    user_id: int
    workspace_id: int
    role: Role = Role.OWNER


@dataclass(frozen=True)
class SourcePassage:
    document_id: str
    document_version: str
    chunk_id: str
    source_name: str
    text: str
    page: int | None = None
    section: str | None = None
    text_start: int | None = None
    text_end: int | None = None
    similarity: float | None = None


@dataclass(frozen=True)
class ClaimAssessment:
    claim: str
    status: ClaimStatus
    confidence: float
    passages: tuple[SourcePassage, ...] = ()
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return value


@dataclass(frozen=True)
class CitationAssessment:
    present: bool
    source_valid: bool
    supports_claim: bool
    completeness: float
    citations: tuple[dict[str, Any], ...] = ()
    # False supports_claim means no verified credit; support_state distinguishes
    # an established defect from semantic support that still requires review.
    support_state: str = "unverified"


@dataclass(frozen=True)
class EscalationAssessment:
    decision: EscalationDecision
    decision_correct: bool | None
    destination: str | None
    destination_correct: bool | None
    reason: str | None
    reason_correct: bool | None
    urgency: str | None
    urgency_correct: bool | None
    confidence: float


@dataclass(frozen=True)
class TargetResponse:
    status: ExecutionStatus
    answer: str = ""
    citations: tuple[dict[str, Any], ...] = ()
    tool_calls: tuple[dict[str, Any], ...] = ()
    escalation: dict[str, Any] | None = None
    latency_ms: float = 0.0
    http_status: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    safe_error: str | None = None
    provider: str | None = None
    model: str | None = None
    final_prompt: str = ""


@dataclass(frozen=True)
class EvaluationCandidate:
    prompt_version: str
    model: str
    target_version: str

    @property
    def key(self) -> str:
        return f"{self.prompt_version}:{self.model}:{self.target_version}"


SYNTHETIC_EVIDENCE_NOTICE = "Synthetic demonstration — not model-quality evidence."
