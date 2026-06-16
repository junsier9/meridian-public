from __future__ import annotations

from dataclasses import dataclass


_ALLOWED_RECOMMENDATIONS = {"advance", "monitor", "archive", "hold"}
_ALLOWED_CLAIM_TYPES = {"measurement"}
_ALLOWED_DIRECTIONS = {"neutral"}
_ALLOWED_SOURCE_FAMILIES = {"analytics"}
_ALLOWED_EVIDENCE_LEVELS = {"E2", "E3", "E4"}
_ALLOWED_TIME_HORIZONS = {"short", "medium"}


@dataclass(frozen=True, slots=True)
class AttentionAllocatorSignalDraft:
    input_id: str
    subject: str
    predicate: str
    value: str
    confidence_hint: int
    scope: str = "spot+perp"
    claim_type: str = "measurement"
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
            raise ValueError("claim_type must remain a bounded attention measurement signal")
        if self.direction not in _ALLOWED_DIRECTIONS:
            raise ValueError("direction must remain neutral for attention posture signals")
        if self.source_family not in _ALLOWED_SOURCE_FAMILIES:
            raise ValueError("source_family must stay within the bounded attention source set")
        if self.evidence_level not in _ALLOWED_EVIDENCE_LEVELS:
            raise ValueError("evidence_level must stay within the bounded attention evidence set")
        if self.time_horizon not in _ALLOWED_TIME_HORIZONS:
            raise ValueError("time_horizon must stay within the bounded attention time horizons")

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
class AttentionAllocatorAssessment:
    object_id: str
    processing_state: str
    risk_state: str
    current_attention: int
    recalculated_attention: int
    stage_permitted: bool
    recommendation: str
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.object_id.strip():
            raise ValueError("object_id must be non-empty")
        if not self.processing_state.strip():
            raise ValueError("processing_state must be non-empty")
        if not self.risk_state.strip():
            raise ValueError("risk_state must be non-empty")
        if not 0 <= self.current_attention <= 100:
            raise ValueError("current_attention must be between 0 and 100")
        if not 0 <= self.recalculated_attention <= 100:
            raise ValueError("recalculated_attention must be between 0 and 100")
        if self.recommendation not in _ALLOWED_RECOMMENDATIONS:
            allowed = ", ".join(sorted(_ALLOWED_RECOMMENDATIONS))
            raise ValueError(f"recommendation must be one of: {allowed}")
