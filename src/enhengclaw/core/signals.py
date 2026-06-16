from __future__ import annotations

from dataclasses import dataclass

from enhengclaw.core.enums import ClaimType, Direction, EvidenceLevel, ObjectType, SourceFamily, TimeHorizon


@dataclass(slots=True)
class Signal:
    signal_id: str
    object_type: ObjectType
    subject: str
    predicate: str
    value: str
    claim_type: ClaimType
    direction: Direction
    source_family: SourceFamily
    evidence_level: EvidenceLevel
    confidence_hint: int
    scope: str = "global"
    time_horizon: TimeHorizon = TimeHorizon.INTRADAY
    fresh: bool = True
