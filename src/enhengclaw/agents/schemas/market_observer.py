from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MarketObserverSignalDraft:
    input_id: str
    subject: str
    predicate: str
    value: str
    confidence_hint: int
    scope: str = "spot+perp"
    claim_type: str = "measurement"
    direction: str = "bullish"
    source_family: str = "analytics"
    evidence_level: str = "E4"
    time_horizon: str = "intraday"

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
