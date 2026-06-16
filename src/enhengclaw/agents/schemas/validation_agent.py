from __future__ import annotations

from dataclasses import dataclass


_ALLOWED_VALIDATION_CLAIM_TYPES = {"risk_flag", "invalidation"}
_ALLOWED_VALIDATION_DIRECTIONS = {"risk", "invalidating"}
_ALLOWED_VALIDATION_SOURCE_FAMILIES = {"analytics", "official", "safety"}
_ALLOWED_VALIDATION_EVIDENCE_LEVELS = {"E2", "E3", "E4", "E5"}
_ALLOWED_VALIDATION_TIME_HORIZONS = {"short", "medium", "structural"}
_ALLOWED_DECISIONS = {"publish", "monitoring", "blocked", "archived"}


@dataclass(frozen=True, slots=True)
class ValidationBlockerSignalDraft:
    input_id: str
    subject: str
    predicate: str
    value: str
    confidence_hint: int
    scope: str = "spot+perp"
    claim_type: str = "invalidation"
    direction: str = "invalidating"
    source_family: str = "analytics"
    evidence_level: str = "E4"
    time_horizon: str = "short"

    def __post_init__(self) -> None:
        if not self.input_id.strip():
            raise ValueError("input_id must be non-empty")
        if not self.subject.strip():
            raise ValueError("subject must be non-empty")
        if not self.predicate.strip():
            raise ValueError("predicate must be non-empty")
        if not self.value.strip():
            raise ValueError("value must be non-empty")
        if not 0 <= self.confidence_hint <= 100:
            raise ValueError("confidence_hint must be between 0 and 100")
        if self.claim_type not in _ALLOWED_VALIDATION_CLAIM_TYPES:
            raise ValueError("claim_type must stay within the bounded validation blocker set")
        if self.direction not in _ALLOWED_VALIDATION_DIRECTIONS:
            raise ValueError("direction must remain risk-oriented or invalidating")
        if self.source_family not in _ALLOWED_VALIDATION_SOURCE_FAMILIES:
            raise ValueError("source_family must stay within the bounded validation source set")
        if self.evidence_level not in _ALLOWED_VALIDATION_EVIDENCE_LEVELS:
            raise ValueError("evidence_level must stay within the bounded validation evidence set")
        if self.time_horizon not in _ALLOWED_VALIDATION_TIME_HORIZONS:
            raise ValueError("time_horizon must stay within the bounded validation time horizons")

    def to_agent_payload(self) -> dict[str, object]:
        return {
            "input_id": self.input_id,
            "subject": self.subject,
            "predicate": self.predicate,
            "value": self.value,
            "claim_type": self.claim_type,
            "direction": self.direction,
            "source_family": self.source_family,
            "evidence_level": self.evidence_level,
            "confidence_hint": self.confidence_hint,
            "scope": self.scope,
            "time_horizon": self.time_horizon,
        }


@dataclass(frozen=True, slots=True)
class ValidationReviewDraft:
    object_id: str
    processing_state: str
    publish_gate_checked: bool
    working_primary_thesis_id: str | None
    working_opposing_thesis_id: str | None
    decision: str
    review_name: str = "validation_review"
    gate_status: str = "pass"
    spec_version: int = 0
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.object_id.strip():
            raise ValueError("object_id must be non-empty")
        if not self.processing_state.strip():
            raise ValueError("processing_state must be non-empty")
        if self.decision not in _ALLOWED_DECISIONS:
            allowed = ", ".join(sorted(_ALLOWED_DECISIONS))
            raise ValueError(f"decision must be one of: {allowed}")
        if self.review_name != "validation_review":
            raise ValueError("review_name must be 'validation_review'")
        if self.gate_status not in {"pass", "block"}:
            raise ValueError("gate_status must be either 'pass' or 'block'")
