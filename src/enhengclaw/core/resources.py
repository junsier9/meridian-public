from __future__ import annotations

from dataclasses import dataclass

from enhengclaw.core.enums import ConflictSeverity, ProcessingState, ResourceTier, RiskState, SlotType
from enhengclaw.core.research_object import ResearchObject


@dataclass(slots=True)
class ResourceAllocation:
    object_id: str
    tier: ResourceTier
    slot_type: SlotType


class ResourceAllocator:
    def __init__(
        self,
        hot_objects_limit: int = 24,
        deep_limit: int = 4,
        conflict_limit: int = 3,
        publish_limit: int = 2,
        monitoring_limit: int = 16,
    ) -> None:
        self.hot_objects_limit = hot_objects_limit
        self.deep_limit = deep_limit
        self.conflict_limit = conflict_limit
        self.publish_limit = publish_limit
        self.monitoring_limit = monitoring_limit

    @staticmethod
    def tier_for_attention(score: int) -> ResourceTier:
        if score >= 80:
            return ResourceTier.A
        if score >= 65:
            return ResourceTier.B
        if score >= 45:
            return ResourceTier.C
        if score >= 30:
            return ResourceTier.D
        return ResourceTier.E

    @staticmethod
    def desired_slot(research_object: ResearchObject, max_conflict: ConflictSeverity) -> SlotType:
        if research_object.processing_state == ProcessingState.BLOCKED or research_object.risk_state == RiskState.BLOCKED:
            return SlotType.NONE
        if research_object.processing_state == ProcessingState.PUBLISH_READY:
            return SlotType.PUBLISH
        if max_conflict.rank >= ConflictSeverity.HIGH.rank:
            return SlotType.CONFLICT
        if (
            research_object.processing_state == ProcessingState.ACTIVE_RESEARCH
            and research_object.attention_score >= 65
            and research_object.risk_state != RiskState.RESTRICTED
        ):
            return SlotType.DEEP
        if research_object.processing_state in {ProcessingState.MONITORING, ProcessingState.SCREENED, ProcessingState.EVIDENCE_COMPLETE, ProcessingState.PUBLISHED}:
            return SlotType.MONITORING
        return SlotType.NONE

    def allocate(
        self,
        objects: list[ResearchObject],
        max_conflicts: dict[str, ConflictSeverity],
    ) -> list[ResourceAllocation]:
        ranked = sorted(
            objects,
            key=lambda obj: (
                obj.processing_state == ProcessingState.PUBLISH_READY,
                obj.risk_state == RiskState.RESTRICTED,
                max_conflicts.get(obj.object_id, ConflictSeverity.CLEAN).rank,
                obj.attention_score,
            ),
            reverse=True,
        )

        allocations: list[ResourceAllocation] = []
        deep_used = conflict_used = publish_used = monitoring_used = 0
        hot_used = 0

        for obj in ranked:
            if hot_used >= self.hot_objects_limit:
                break

            tier = self.tier_for_attention(obj.attention_score)
            slot = self.desired_slot(obj, max_conflicts.get(obj.object_id, ConflictSeverity.CLEAN))

            if slot == SlotType.DEEP and (deep_used >= self.deep_limit or tier not in {ResourceTier.A, ResourceTier.B}):
                slot = SlotType.MONITORING
            if slot == SlotType.CONFLICT and conflict_used >= self.conflict_limit:
                slot = SlotType.MONITORING
            if slot == SlotType.PUBLISH and publish_used >= self.publish_limit:
                slot = SlotType.MONITORING
            if slot == SlotType.MONITORING and monitoring_used >= self.monitoring_limit:
                slot = SlotType.NONE

            if slot == SlotType.NONE and tier == ResourceTier.E:
                continue

            if slot == SlotType.DEEP:
                deep_used += 1
                hot_used += 1
            elif slot == SlotType.CONFLICT:
                conflict_used += 1
                hot_used += 1
            elif slot == SlotType.PUBLISH:
                publish_used += 1
                hot_used += 1
            elif slot == SlotType.MONITORING:
                monitoring_used += 1
                hot_used += 1

            allocations.append(ResourceAllocation(object_id=obj.object_id, tier=tier, slot_type=slot))

        return allocations
