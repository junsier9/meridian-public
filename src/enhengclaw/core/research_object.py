from __future__ import annotations

from dataclasses import dataclass, field

from enhengclaw.core.enums import MarketState, ObjectType, ProcessingState, RiskState, TimeHorizon


@dataclass(slots=True)
class ResearchObject:
    object_id: str
    object_type: ObjectType
    scope: str
    time_horizon: TimeHorizon
    processing_state: ProcessingState = ProcessingState.CANDIDATE
    risk_state: RiskState = RiskState.NORMAL
    market_state: MarketState = MarketState.PRE_EMERGENCE
    attention_score: int = 0
    claim_ids: list[str] = field(default_factory=list)
    thesis_ids: list[str] = field(default_factory=list)
    working_primary_thesis_id: str | None = None
    working_opposing_thesis_id: str | None = None
    cycle_index: int = 0
    processing_transitions_this_cycle: int = 0

    @property
    def is_restricted_monitoring(self) -> bool:
        return (
            self.processing_state == ProcessingState.MONITORING
            and self.risk_state == RiskState.RESTRICTED
        )
