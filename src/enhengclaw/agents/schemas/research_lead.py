from __future__ import annotations

from dataclasses import dataclass


_ALLOWED_CLAIM_TYPES = {"causal", "predictive"}
_ALLOWED_DIRECTIONS = {"neutral", "risk"}
_ALLOWED_SOURCE_FAMILIES = {"analytics", "official"}
_ALLOWED_EVIDENCE_LEVELS = {"E2", "E3", "E4"}
_ALLOWED_TIME_HORIZONS = {"short", "medium"}


@dataclass(frozen=True, slots=True)
class ResearchLeadSignalDraft:
    input_id: str
    subject: str
    predicate: str
    value: str
    confidence_hint: int
    scope: str = "spot+perp"
    claim_type: str = "predictive"
    direction: str = "neutral"
    source_family: str = "analytics"
    evidence_level: str = "E3"
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
        if self.claim_type not in _ALLOWED_CLAIM_TYPES:
            raise ValueError("claim_type must stay within the bounded research-lead signal set")
        if self.direction not in _ALLOWED_DIRECTIONS:
            raise ValueError("direction must stay within the bounded research-lead direction set")
        if self.source_family not in _ALLOWED_SOURCE_FAMILIES:
            raise ValueError("source_family must stay within the bounded research-lead source set")
        if self.evidence_level not in _ALLOWED_EVIDENCE_LEVELS:
            raise ValueError("evidence_level must stay within the bounded research-lead evidence set")
        if self.time_horizon not in _ALLOWED_TIME_HORIZONS:
            raise ValueError("time_horizon must stay within the bounded research-lead time horizons")

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
class ResearchLeadDirective:
    object_id: str
    processing_state: str
    risk_state: str
    next_legal_stage: str
    allowed_actions: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    cadence_mode: str
    resource_slot: str

    def __post_init__(self) -> None:
        if not self.object_id.strip():
            raise ValueError("object_id must be non-empty")
        if not self.processing_state.strip():
            raise ValueError("processing_state must be non-empty")
        if not self.risk_state.strip():
            raise ValueError("risk_state must be non-empty")
        if not self.next_legal_stage.strip():
            raise ValueError("next_legal_stage must be non-empty")
        if not self.allowed_actions:
            raise ValueError("allowed_actions must be non-empty")
