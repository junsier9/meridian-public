from __future__ import annotations

from enhengclaw.core.enums import MarketState, ProcessingState, RiskState
from enhengclaw.core.research_object import ResearchObject


PROCESSING_ORDER = {
    ProcessingState.CANDIDATE: 0,
    ProcessingState.SCREENED: 1,
    ProcessingState.ACTIVE_RESEARCH: 2,
    ProcessingState.EVIDENCE_COMPLETE: 3,
    ProcessingState.PUBLISH_READY: 4,
    ProcessingState.PUBLISHED: 5,
    ProcessingState.MONITORING: 6,
    ProcessingState.ARCHIVED: 7,
    ProcessingState.BLOCKED: 8,
}


ALLOWED_PROCESSING_TRANSITIONS = {
    ProcessingState.CANDIDATE: {ProcessingState.SCREENED, ProcessingState.ARCHIVED, ProcessingState.BLOCKED},
    ProcessingState.SCREENED: {
        ProcessingState.ACTIVE_RESEARCH,
        ProcessingState.MONITORING,
        ProcessingState.ARCHIVED,
        ProcessingState.BLOCKED,
    },
    ProcessingState.ACTIVE_RESEARCH: {
        ProcessingState.EVIDENCE_COMPLETE,
        ProcessingState.MONITORING,
        ProcessingState.BLOCKED,
    },
    ProcessingState.EVIDENCE_COMPLETE: {
        ProcessingState.PUBLISH_READY,
        ProcessingState.MONITORING,
        ProcessingState.BLOCKED,
    },
    ProcessingState.PUBLISH_READY: {
        ProcessingState.PUBLISHED,
        ProcessingState.EVIDENCE_COMPLETE,
        ProcessingState.MONITORING,
        ProcessingState.BLOCKED,
    },
    ProcessingState.PUBLISHED: {ProcessingState.MONITORING, ProcessingState.BLOCKED},
    ProcessingState.MONITORING: {
        ProcessingState.ACTIVE_RESEARCH,
        ProcessingState.ARCHIVED,
        ProcessingState.BLOCKED,
    },
    ProcessingState.ARCHIVED: {ProcessingState.ACTIVE_RESEARCH, ProcessingState.BLOCKED},
    ProcessingState.BLOCKED: set(),
}


class StateMachine:
    def begin_cycle(self, research_object: ResearchObject) -> None:
        research_object.cycle_index += 1
        research_object.processing_transitions_this_cycle = 0

    def transition_processing(self, research_object: ResearchObject, target: ProcessingState) -> None:
        current = research_object.processing_state
        if target == current:
            return
        if target not in ALLOWED_PROCESSING_TRANSITIONS[current]:
            raise ValueError(f"Invalid processing transition: {current} -> {target}")

        if target == ProcessingState.BLOCKED:
            research_object.processing_state = target
            return

        is_forward = PROCESSING_ORDER[target] > PROCESSING_ORDER[current]
        if is_forward and research_object.processing_transitions_this_cycle >= 1:
            raise ValueError(
                f"Only one forward processing transition is allowed per cycle for {research_object.object_id}"
            )

        research_object.processing_state = target
        if is_forward:
            research_object.processing_transitions_this_cycle += 1

    def set_risk_state(self, research_object: ResearchObject, target: RiskState) -> None:
        research_object.risk_state = target

    def set_market_state(self, research_object: ResearchObject, target: MarketState) -> None:
        research_object.market_state = target
