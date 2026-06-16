from __future__ import annotations

import unittest

from tests.test_helpers import enter_runtime_worker, make_claim, make_research_object, make_signal, make_thesis

from enhengclaw.core.enums import (
    ClaimStatus,
    ClaimType,
    Direction,
    EvidenceLevel,
    ObjectType,
    ProcessingState,
    RiskState,
    SourceFamily,
    ThesisStatus,
    ThesisType,
    TimeHorizon,
)
from enhengclaw.core.publish_gate import PublishDecision, PublishDecisionType
from enhengclaw.orchestration.runtime_runner import RuntimeBoundaryError, RuntimeOrchestrator, RuntimeRunRequest
from enhengclaw.core.session import InMemoryObjectStore, RuntimeSession


class RuntimeBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        enter_runtime_worker(self, slug="test-runtime-boundaries")
        self.store = InMemoryObjectStore()
        self.orchestrator = RuntimeOrchestrator(store=self.store)
        self.claim_index = {
            "a1": make_claim(
                "a1",
                claim_type=ClaimType.MEASUREMENT,
                predicate="spot_breakout",
                direction=Direction.BULLISH,
                source_family=SourceFamily.CEX,
                evidence_level=EvidenceLevel.E4,
                status=ClaimStatus.PROMOTED,
                confidence=84,
            ),
            "a2": make_claim(
                "a2",
                claim_type=ClaimType.FLOW,
                predicate="wallet_buy",
                direction=Direction.BULLISH,
                source_family=SourceFamily.ONCHAIN,
                evidence_level=EvidenceLevel.E4,
                status=ClaimStatus.PROMOTED,
                confidence=80,
            ),
            "a3": make_claim(
                "a3",
                claim_type=ClaimType.MARKET_STRUCTURE,
                predicate="spot_leads_perps",
                direction=Direction.BULLISH,
                source_family=SourceFamily.ANALYTICS,
                evidence_level=EvidenceLevel.E4,
                status=ClaimStatus.PROMOTED,
                confidence=76,
            ),
        }

    def _predictive_thesis(self):
        return make_thesis(
            "t-primary",
            thesis_type=ThesisType.PREDICTIVE,
            status=ThesisStatus.PUBLISHABLE,
            anchor_claim_ids=["a1", "a2"],
            supporting_claim_ids=["a3"],
            working_primary_streak=2,
            confidence=82,
        )

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
                "wallet_buy",
                "smart money buying",
                ClaimType.FLOW,
                Direction.BULLISH,
                SourceFamily.ONCHAIN,
                EvidenceLevel.E4,
                78,
            ),
            make_signal(
                f"{prefix}-3",
                "AIX",
                "spot_leads_perps",
                "market structure support",
                ClaimType.MARKET_STRUCTURE,
                Direction.BULLISH,
                SourceFamily.ANALYTICS,
                EvidenceLevel.E4,
                75,
            ),
        ]

    def _weak_screened_signal(self, signal_id: str):
        return make_signal(
            signal_id,
            "AIX",
            "commentary",
            "single-source commentary",
            ClaimType.CAUSAL,
            Direction.NEUTRAL,
            SourceFamily.INFOFLOW,
            EvidenceLevel.E3,
            45,
        )

    def test_thesis_building_rejects_in_screened_monitoring_and_archived(self) -> None:
        claims = [self.claim_index["a1"], self.claim_index["a2"]]

        for state in (ProcessingState.SCREENED, ProcessingState.MONITORING, ProcessingState.ARCHIVED):
            with self.subTest(state=state.value):
                research_object = make_research_object(processing_state=state)
                with self.assertRaisesRegex(
                    RuntimeBoundaryError,
                    rf"thesis_building cannot run in {state.value}",
                ):
                    self.orchestrator.build_theses(research_object, claims, [])
                self.assertEqual(research_object.processing_state, state)

    def test_thesis_selection_rejects_in_screened_monitoring_and_archived(self) -> None:
        theses = [self._predictive_thesis()]

        for state in (ProcessingState.SCREENED, ProcessingState.MONITORING, ProcessingState.ARCHIVED):
            with self.subTest(state=state.value):
                research_object = make_research_object(processing_state=state)
                with self.assertRaisesRegex(
                    RuntimeBoundaryError,
                    rf"thesis_selection cannot run in {state.value}",
                ):
                    self.orchestrator.select_working_theses(research_object, theses, self.claim_index)
                self.assertIsNone(research_object.working_primary_thesis_id)
                self.assertIsNone(research_object.working_opposing_thesis_id)

    def test_publish_gate_rejects_in_non_publish_ready_states(self) -> None:
        predictive = self._predictive_thesis()

        for state in (
            ProcessingState.CANDIDATE,
            ProcessingState.SCREENED,
            ProcessingState.ACTIVE_RESEARCH,
            ProcessingState.EVIDENCE_COMPLETE,
            ProcessingState.MONITORING,
        ):
            with self.subTest(state=state.value):
                research_object = make_research_object(
                    processing_state=state,
                    risk_state=RiskState.CAUTION,
                    attention_score=75,
                )
                with self.assertRaisesRegex(
                    RuntimeBoundaryError,
                    rf"publish_gate cannot run in {state.value}",
                ):
                    self.orchestrator.evaluate_publish_gate(
                        research_object,
                        predictive,
                        None,
                        self.claim_index,
                    )
                self.assertEqual(research_object.processing_state, state)

    def test_claim_promotion_rejects_outside_evidence_complete(self) -> None:
        predictive = make_thesis(
            "t-supported",
            thesis_type=ThesisType.PREDICTIVE,
            status=ThesisStatus.ACTIVE,
            anchor_claim_ids=["a1", "a2"],
            supporting_claim_ids=["a3"],
            working_primary_streak=1,
            confidence=80,
        )
        supported_index = {
            claim_id: make_claim(
                claim_id,
                claim_type=claim.claim_type,
                predicate=claim.predicate,
                direction=claim.direction,
                source_family=claim.source_family,
                evidence_level=claim.highest_evidence_level(),
                status=ClaimStatus.SUPPORTED,
                confidence=claim.confidence,
            )
            for claim_id, claim in self.claim_index.items()
        }

        for state in (
            ProcessingState.CANDIDATE,
            ProcessingState.SCREENED,
            ProcessingState.ACTIVE_RESEARCH,
            ProcessingState.PUBLISH_READY,
            ProcessingState.MONITORING,
            ProcessingState.ARCHIVED,
            ProcessingState.BLOCKED,
            ProcessingState.PUBLISHED,
        ):
            with self.subTest(state=state.value):
                research_object = make_research_object(processing_state=state)
                with self.assertRaisesRegex(
                    RuntimeBoundaryError,
                    rf"claim_promotion cannot run in {state.value}",
                ):
                    self.orchestrator.promote_publishable_claims(
                        research_object,
                        predictive,
                        supported_index,
                    )

    def test_continue_existing_blocked_normal_resume_returns_rejected_step(self) -> None:
        blocked_session = RuntimeSession(
            object_id="blocked-object",
            research_object=make_research_object(
                object_id="blocked-object",
                processing_state=ProcessingState.BLOCKED,
                risk_state=RiskState.BLOCKED,
            ),
            latest_decision=PublishDecision(PublishDecisionType.BLOCKED, ["previous block"]),
        )
        self.store.save(blocked_session)

        result = self.orchestrator.continue_existing(
            object_id="blocked-object",
            signals=self._strong_bullish_signals("blocked-resume"),
        )

        self.assertEqual(result.decision.decision, PublishDecisionType.BLOCKED)
        rejected_steps = [step for step in result.steps if step.status == "rejected"]
        self.assertTrue(rejected_steps)
        self.assertEqual(rejected_steps[0].step, "session_resume")
        self.assertIn("blocked objects require forced review", rejected_steps[0].details["reason"])
        self.assertEqual(result.research_object.processing_state, ProcessingState.BLOCKED)

    def test_continue_existing_rejects_illegal_resume_states(self) -> None:
        illegal_states = (
            ProcessingState.CANDIDATE,
            ProcessingState.SCREENED,
            ProcessingState.ACTIVE_RESEARCH,
            ProcessingState.EVIDENCE_COMPLETE,
            ProcessingState.PUBLISH_READY,
        )

        for state in illegal_states:
            with self.subTest(state=state.value):
                object_id = f"illegal-{state.value}"
                session = RuntimeSession(
                    object_id=object_id,
                    research_object=make_research_object(
                        object_id=object_id,
                        processing_state=state,
                    ),
                    latest_decision=PublishDecision(PublishDecisionType.MONITORING, ["seed"]),
                )
                self.store.save(session)

                with self.assertRaisesRegex(
                    RuntimeBoundaryError,
                    r"continue_existing cannot resume from .*allowed states: monitoring, archived, published",
                ):
                    self.orchestrator.continue_existing(
                        object_id=object_id,
                        signals=self._strong_bullish_signals(f"resume-{state.value}"),
                    )

                stored = self.store.load(object_id)
                self.assertEqual(stored.research_object.processing_state, state)
                self.assertEqual(len(stored.claims), 0)

    def test_batch_run_illegal_request_does_not_contaminate_other_sessions(self) -> None:
        illegal_session = RuntimeSession(
            object_id="illegal-screened",
            research_object=make_research_object(
                object_id="illegal-screened",
                processing_state=ProcessingState.SCREENED,
                attention_score=60,
            ),
            latest_decision=PublishDecision(PublishDecisionType.MONITORING, ["seed illegal session"]),
        )
        self.store.save(illegal_session)

        requests = [
            RuntimeRunRequest(
                mode="create",
                object_id="valid-create",
                object_type=ObjectType.ASSET,
                scope="spot+perp",
                signals=self._strong_bullish_signals("valid"),
            ),
            RuntimeRunRequest(
                mode="continue",
                object_id="illegal-screened",
                signals=self._strong_bullish_signals("illegal"),
            ),
        ]

        with self.assertRaises(RuntimeBoundaryError):
            self.orchestrator.run_batch(requests, business_request_id="runtime-boundaries-batch-illegal")

        self.assertTrue(self.store.exists("valid-create"))
        valid_session = self.store.load("valid-create")
        self.assertIn(
            valid_session.research_object.processing_state,
            {
                ProcessingState.PUBLISHED,
                ProcessingState.MONITORING,
                ProcessingState.ARCHIVED,
                ProcessingState.BLOCKED,
            },
        )
        self.assertIsNotNone(valid_session.latest_decision)

        illegal_after = self.store.load("illegal-screened")
        self.assertEqual(illegal_after.research_object.processing_state, ProcessingState.SCREENED)
        self.assertEqual(len(illegal_after.claims), 0)

    def test_rejected_paths_emit_explicit_step_logs_or_raise_boundary_errors(self) -> None:
        result = self.orchestrator.run_new(
            object_id="screened-monitoring",
            object_type=ObjectType.ASSET,
            scope="spot",
            signals=[self._weak_screened_signal("weak-1")],
        )

        publish_gate_steps = [step for step in result.steps if step.step == "publish_gate"]
        self.assertEqual(len(publish_gate_steps), 1)
        self.assertEqual(publish_gate_steps[0].status, "rejected")
        self.assertEqual(
            publish_gate_steps[0].details["reason"],
            "processing_state is not publish_ready",
        )
        self.assertEqual(result.decision.decision, PublishDecisionType.MONITORING)

        with self.assertRaisesRegex(RuntimeBoundaryError, r"thesis_building cannot run in screened"):
            self.orchestrator.build_theses(
                make_research_object(processing_state=ProcessingState.SCREENED),
                [self.claim_index["a1"], self.claim_index["a2"]],
                [],
            )


if __name__ == "__main__":
    unittest.main()
