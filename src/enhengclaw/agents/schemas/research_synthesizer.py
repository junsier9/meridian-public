from __future__ import annotations

from dataclasses import dataclass


_ALLOWED_TYPES = {"descriptive", "predictive", "risk", "counter", "none"}
_ALLOWED_CONFLICTS = {"clean", "low", "medium", "high", "critical", "none"}
_ALLOWED_CLAIM_TYPES = {"predictive", "risk_flag"}
_ALLOWED_DIRECTIONS = {"bullish", "bearish", "neutral", "risk"}
_ALLOWED_SOURCE_FAMILIES = {"analytics", "official"}
_ALLOWED_EVIDENCE_LEVELS = {"E2", "E3", "E4"}
_ALLOWED_TIME_HORIZONS = {"short", "medium", "structural"}


@dataclass(frozen=True, slots=True)
class ResearchSynthesisSignalDraft:
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
    time_horizon: str = "medium"

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
            raise ValueError("claim_type must stay within the bounded synthesis signal set")
        if self.direction not in _ALLOWED_DIRECTIONS:
            raise ValueError("direction must stay within the bounded synthesis direction set")
        if self.source_family not in _ALLOWED_SOURCE_FAMILIES:
            raise ValueError("source_family must stay within the bounded synthesis source set")
        if self.evidence_level not in _ALLOWED_EVIDENCE_LEVELS:
            raise ValueError("evidence_level must stay within the bounded synthesis evidence set")
        if self.time_horizon not in _ALLOWED_TIME_HORIZONS:
            raise ValueError("time_horizon must stay within the bounded synthesis time horizons")

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
class ResearchSynthesisDraft:
    object_id: str
    processing_state: str
    stage_permitted: bool
    thesis_count: int
    thesis_ids: tuple[str, ...]
    working_primary_thesis_id: str | None
    working_opposing_thesis_id: str | None
    working_primary_type: str
    working_primary_conflict: str
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.object_id.strip():
            raise ValueError("object_id must be non-empty")
        if not self.processing_state.strip():
            raise ValueError("processing_state must be non-empty")
        if self.thesis_count < 0:
            raise ValueError("thesis_count must be non-negative")
        if self.working_primary_type not in _ALLOWED_TYPES:
            allowed = ", ".join(sorted(_ALLOWED_TYPES))
            raise ValueError(f"working_primary_type must be one of: {allowed}")
        if self.working_primary_conflict not in _ALLOWED_CONFLICTS:
            allowed = ", ".join(sorted(_ALLOWED_CONFLICTS))
            raise ValueError(f"working_primary_conflict must be one of: {allowed}")
