from __future__ import annotations

import unittest
from datetime import timedelta

from tests.test_helpers import make_research_object

from enhengclaw.core.cadence import cadence_for_object
from enhengclaw.core.enums import ConflictSeverity, ProcessingState, RiskState, SlotType
from enhengclaw.core.resources import ResourceAllocator


class CadenceResourceTests(unittest.TestCase):
    def test_cadence_differs_by_operating_mode(self) -> None:
        published = make_research_object(processing_state=ProcessingState.PUBLISHED)
        monitoring = make_research_object(processing_state=ProcessingState.MONITORING)
        blocked = make_research_object(processing_state=ProcessingState.BLOCKED)
        restricted_monitoring = make_research_object(
            processing_state=ProcessingState.MONITORING,
            risk_state=RiskState.RESTRICTED,
        )

        published_plan = cadence_for_object(published)
        monitoring_plan = cadence_for_object(monitoring)
        blocked_plan = cadence_for_object(blocked)
        restricted_plan = cadence_for_object(restricted_monitoring)

        self.assertEqual(published_plan.normal_review_after, timedelta(minutes=30))
        self.assertEqual(monitoring_plan.normal_review_after, timedelta(hours=3))
        self.assertIsNone(blocked_plan.normal_review_after)
        self.assertEqual(restricted_plan.normal_review_after, timedelta(hours=1))
        self.assertEqual(restricted_plan.deep_review_after, timedelta(hours=12))

    def test_allocator_selects_expected_slots(self) -> None:
        allocator = ResourceAllocator()
        publish_ready = make_research_object(
            object_id="ro-publish",
            processing_state=ProcessingState.PUBLISH_READY,
            attention_score=78,
        )
        active = make_research_object(
            object_id="ro-deep",
            processing_state=ProcessingState.ACTIVE_RESEARCH,
            attention_score=75,
        )
        conflict_obj = make_research_object(
            object_id="ro-conflict",
            processing_state=ProcessingState.ACTIVE_RESEARCH,
            attention_score=72,
        )
        monitoring = make_research_object(
            object_id="ro-monitoring",
            processing_state=ProcessingState.MONITORING,
            attention_score=52,
        )

        allocations = allocator.allocate(
            [publish_ready, active, conflict_obj, monitoring],
            {
                publish_ready.object_id: ConflictSeverity.CLEAN,
                active.object_id: ConflictSeverity.CLEAN,
                conflict_obj.object_id: ConflictSeverity.HIGH,
                monitoring.object_id: ConflictSeverity.CLEAN,
            },
        )
        by_object = {allocation.object_id: allocation for allocation in allocations}

        self.assertEqual(by_object[publish_ready.object_id].slot_type, SlotType.PUBLISH)
        self.assertEqual(by_object[active.object_id].slot_type, SlotType.DEEP)
        self.assertEqual(by_object[conflict_obj.object_id].slot_type, SlotType.CONFLICT)
        self.assertEqual(by_object[monitoring.object_id].slot_type, SlotType.MONITORING)

    def test_restricted_monitoring_never_uses_deep_slot(self) -> None:
        allocator = ResourceAllocator()
        restricted_monitoring = make_research_object(
            processing_state=ProcessingState.MONITORING,
            risk_state=RiskState.RESTRICTED,
            attention_score=95,
        )

        allocations = allocator.allocate(
            [restricted_monitoring],
            {restricted_monitoring.object_id: ConflictSeverity.CLEAN},
        )

        self.assertEqual(allocations[0].slot_type, SlotType.MONITORING)


if __name__ == "__main__":
    unittest.main()
