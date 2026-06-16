from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from enhengclaw.core.enums import ObjectType, ProcessingState
from enhengclaw.core.research_object import ResearchObject


@dataclass(slots=True)
class CadencePlan:
    mode: str
    normal_review_after: timedelta | None
    deep_review_after: timedelta | None


OBJECT_MULTIPLIERS = {
    ObjectType.EVENT: 0.25,
    ObjectType.ASSET: 0.5,
    ObjectType.WALLET_CLUSTER: 0.5,
    ObjectType.NARRATIVE: 1.0,
    ObjectType.PROJECT: 1.5,
    ObjectType.VENUE: 1.0,
}


def cadence_for_object(research_object: ResearchObject) -> CadencePlan:
    multiplier = OBJECT_MULTIPLIERS[research_object.object_type]

    if research_object.processing_state == ProcessingState.BLOCKED:
        return CadencePlan(mode="blocked", normal_review_after=None, deep_review_after=None)

    if research_object.is_restricted_monitoring:
        return CadencePlan(
            mode="restricted_monitoring",
            normal_review_after=timedelta(hours=2 * multiplier),
            deep_review_after=timedelta(hours=24 * multiplier),
        )

    base_hours = {
        ProcessingState.CANDIDATE: (4, 24),
        ProcessingState.SCREENED: (2, 24),
        ProcessingState.ACTIVE_RESEARCH: (0.5, 6),
        ProcessingState.EVIDENCE_COMPLETE: (1, 8),
        ProcessingState.PUBLISH_READY: (10 / 60, 12),
        ProcessingState.PUBLISHED: (1, 12),
        ProcessingState.MONITORING: (6, 72),
        ProcessingState.ARCHIVED: (24 * 7, None),
    }

    normal_hours, deep_hours = base_hours[research_object.processing_state]
    return CadencePlan(
        mode=research_object.processing_state.value,
        normal_review_after=timedelta(hours=normal_hours * multiplier) if normal_hours is not None else None,
        deep_review_after=timedelta(hours=deep_hours * multiplier) if deep_hours is not None else None,
    )
