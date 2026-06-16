from __future__ import annotations

import unittest

from tests.test_helpers import enter_runtime_worker, make_signal

from enhengclaw.core.enums import (
    ClaimType,
    Direction,
    EvidenceLevel,
    ObjectType,
    ProcessingState,
    RiskState,
    SourceFamily,
    TimeHorizon,
)
from enhengclaw.core.publish_gate import PublishDecision, PublishDecisionType
from enhengclaw.core.research_object import ResearchObject
from enhengclaw.core.resources import ResourceAllocator
from enhengclaw.orchestration.runtime_runner import RuntimeOrchestrator, RuntimeRunRequest
from enhengclaw.core.session import InMemoryObjectStore, RuntimeSession


class RuntimeSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        enter_runtime_worker(self, slug="test-runtime-sessions")
        self.store = InMemoryObjectStore()
        self.orchestrator = RuntimeOrchestrator(store=self.store)

    def _strong_bullish_signals(self, prefix: str) -> list:
        return [
            make_signal(
                f"{prefix}-1",
                "AIX",
                "spot_breakout",
                "spot volume expansion",
                ClaimType.MEASUREMENT,
                Direction.BULLISH,
                SourceFamily.CEX,
                EvidenceLevel.E4,
                82,
            ),
            make_signal(
                f"{prefix}-2",
                "AIX",
                "smart_money_accumulation",
                "wallets net buying",
                ClaimType.FLOW,
                Direction.BULLISH,
                SourceFamily.ONCHAIN,
                EvidenceLevel.E4,
                78,
            ),
            make_signal(
                f"{prefix}-3",
                "AIX",
                "structure_support",
                "spot leads perps",
                ClaimType.MARKET_STRUCTURE,
                Direction.BULLISH,
                SourceFamily.ANALYTICS,
                EvidenceLevel.E4,
                75,
            ),
        ]

    def _risk_signal(self, prefix: str):
        return make_signal(
            f"{prefix}-risk",
            "AIX",
            "bridge_risk",
            "unusual bridge activity",
            ClaimType.RISK_FLAG,
            Direction.RISK,
            SourceFamily.SAFETY,
            EvidenceLevel.E4,
            68,
            time_horizon=TimeHorizon.SHORT,
        )

    def test_existing_object_can_resume(self) -> None:
        created = self.orchestrator.run_new(
            object_id="obj-resume",
            object_type=ObjectType.ASSET,
            scope="spot+perp",
            signals=self._strong_bullish_signals("create"),
        )
        resumed = self.orchestrator.continue_existing(
            object_id="obj-resume",
            signals=[self._risk_signal("resume")],
        )

        self.assertEqual(created.research_object.object_id, resumed.research_object.object_id)
        self.assertGreater(len(resumed.claims), len(created.claims))
        self.assertEqual(resumed.steps[0].step, "session_load")
        stored = self.store.load("obj-resume")
        self.assertEqual(len(stored.claims), len(resumed.claims))

    def test_archived_object_without_strong_new_signals_stays_archived(self) -> None:
        archived = RuntimeSession(
            object_id="obj-archived-stay",
            research_object=ResearchObject(
                object_id="obj-archived-stay",
                object_type=ObjectType.ASSET,
                scope="spot",
                time_horizon=TimeHorizon.INTRADAY,
                processing_state=ProcessingState.ARCHIVED,
                risk_state=RiskState.NORMAL,
                attention_score=20,
            ),
            latest_decision=PublishDecision(PublishDecisionType.ARCHIVED, ["previously archived"]),
        )
        self.store.save(archived)

        result = self.orchestrator.continue_existing(
            object_id="obj-archived-stay",
            signals=[
                make_signal(
                    "weak-1",
                    "AIX",
                    "commentary",
                    "weak infoflow",
                    ClaimType.CAUSAL,
                    Direction.NEUTRAL,
                    SourceFamily.INFOFLOW,
                    EvidenceLevel.E3,
                    45,
                )
            ],
        )

        self.assertEqual(result.research_object.processing_state, ProcessingState.ARCHIVED)
        self.assertEqual(result.decision.decision, PublishDecisionType.ARCHIVED)

    def test_archived_object_can_reactivate_with_strong_new_signals(self) -> None:
        archived = RuntimeSession(
            object_id="obj-archived-reactivate",
            research_object=ResearchObject(
                object_id="obj-archived-reactivate",
                object_type=ObjectType.ASSET,
                scope="spot",
                time_horizon=TimeHorizon.INTRADAY,
                processing_state=ProcessingState.ARCHIVED,
                risk_state=RiskState.NORMAL,
                attention_score=20,
            ),
            latest_decision=PublishDecision(PublishDecisionType.ARCHIVED, ["previously archived"]),
        )
        self.store.save(archived)

        result = self.orchestrator.continue_existing(
            object_id="obj-archived-reactivate",
            signals=self._strong_bullish_signals("reactivate"),
        )

        self.assertIn(
            result.research_object.processing_state,
            {ProcessingState.ACTIVE_RESEARCH, ProcessingState.EVIDENCE_COMPLETE, ProcessingState.PUBLISH_READY, ProcessingState.PUBLISHED, ProcessingState.MONITORING},
        )
        self.assertTrue(any(step.step == "archived_reactivation" for step in result.steps))

    def test_monitoring_object_reenters_active_path_with_new_signals(self) -> None:
        monitoring = RuntimeSession(
            object_id="obj-monitoring-resume",
            research_object=ResearchObject(
                object_id="obj-monitoring-resume",
                object_type=ObjectType.ASSET,
                scope="spot+perp",
                time_horizon=TimeHorizon.INTRADAY,
                processing_state=ProcessingState.MONITORING,
                risk_state=RiskState.NORMAL,
                attention_score=42,
            ),
            latest_decision=PublishDecision(PublishDecisionType.MONITORING, ["waiting for new evidence"]),
        )
        self.store.save(monitoring)

        result = self.orchestrator.continue_existing(
            object_id="obj-monitoring-resume",
            signals=self._strong_bullish_signals("monitor"),
        )

        resume_steps = [step for step in result.steps if step.step == "monitoring_resume_decision"]
        self.assertTrue(resume_steps)
        self.assertEqual(resume_steps[0].details["target"], ProcessingState.ACTIVE_RESEARCH.value)

    def test_batch_run_preserves_allocation_ordering(self) -> None:
        constrained = RuntimeOrchestrator(
            store=InMemoryObjectStore(),
            resource_allocator=ResourceAllocator(
                hot_objects_limit=1,
                deep_limit=1,
                conflict_limit=1,
                publish_limit=1,
                monitoring_limit=1,
            ),
        )

        requests = [
            RuntimeRunRequest(
                mode="create",
                object_id="batch-published",
                object_type=ObjectType.ASSET,
                scope="spot+perp",
                signals=self._strong_bullish_signals("batch-pub"),
            ),
            RuntimeRunRequest(
                mode="create",
                object_id="batch-restricted",
                object_type=ObjectType.ASSET,
                scope="bridge",
                signals=[
                    *self._strong_bullish_signals("batch-risk"),
                    self._risk_signal("batch-risk"),
                ],
            ),
            RuntimeRunRequest(
                mode="create",
                object_id="batch-archived",
                object_type=ObjectType.PROJECT,
                scope="global",
                signals=[
                    make_signal(
                        "batch-archived-1",
                        "ZZZ",
                        "rumor",
                        "weak rumor",
                        ClaimType.CAUSAL,
                        Direction.NEUTRAL,
                        SourceFamily.INFOFLOW,
                        EvidenceLevel.E2,
                        30,
                    )
                ],
            ),
        ]

        results = constrained.run_batch(requests, business_request_id="runtime-sessions-batch-allocation")
        by_id = {result.research_object.object_id: result for result in results}

        self.assertIsNotNone(by_id["batch-restricted"].resource_allocation)
        self.assertIsNone(by_id["batch-published"].resource_allocation)
        self.assertIsNone(by_id["batch-archived"].resource_allocation)


if __name__ == "__main__":
    unittest.main()
