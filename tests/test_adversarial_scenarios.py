from __future__ import annotations

import unittest

from tests.test_helpers import make_claim, make_research_object, make_thesis

from enhengclaw.core.conflicts import group_claim_conflicts
from enhengclaw.core.enums import (
    ClaimStatus,
    ClaimType,
    ConflictSeverity,
    Direction,
    EvidenceLevel,
    ProcessingState,
    RiskState,
    SourceFamily,
    ThesisStatus,
    ThesisType,
    TimeHorizon,
)
from enhengclaw.core.publish_gate import PublishDecisionType, PublishGate
from enhengclaw.core.state_machine import StateMachine
from enhengclaw.core.thesis import build_theses_for_object, select_working_theses


class AdversarialScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gate = PublishGate()
        self.machine = StateMachine()
        self.base_claim_index = {
            "a1": make_claim(
                "a1",
                claim_type=ClaimType.MEASUREMENT,
                predicate="spot_breakout",
                source_family=SourceFamily.CEX,
                evidence_level=EvidenceLevel.E4,
                status=ClaimStatus.PROMOTED,
            ),
            "a2": make_claim(
                "a2",
                claim_type=ClaimType.FLOW,
                predicate="wallet_buy",
                source_family=SourceFamily.ONCHAIN,
                evidence_level=EvidenceLevel.E4,
                status=ClaimStatus.PROMOTED,
            ),
            "a3": make_claim(
                "a3",
                claim_type=ClaimType.MARKET_STRUCTURE,
                predicate="spot_leads_perps",
                source_family=SourceFamily.ANALYTICS,
                evidence_level=EvidenceLevel.E4,
                status=ClaimStatus.PROMOTED,
            ),
            "r1": make_claim(
                "r1",
                claim_type=ClaimType.RISK_FLAG,
                predicate="bridge_risk",
                direction=Direction.RISK,
                source_family=SourceFamily.SAFETY,
                evidence_level=EvidenceLevel.E4,
                confidence=85,
                status=ClaimStatus.PROMOTED,
                time_horizon=TimeHorizon.SHORT,
            ),
        }

    def _publishable_predictive(self, streak: int = 2):
        return make_thesis(
            "t-primary",
            thesis_type=ThesisType.PREDICTIVE,
            status=ThesisStatus.PUBLISHABLE,
            anchor_claim_ids=["a1", "a2"],
            supporting_claim_ids=["a3"],
            working_primary_streak=streak,
        )

    def _risk_thesis(self, confidence: int = 90):
        return make_thesis(
            "t-risk",
            thesis_type=ThesisType.RISK,
            direction=Direction.RISK,
            time_horizon=TimeHorizon.SHORT,
            anchor_claim_ids=["r1"],
            confidence=confidence,
        )

    def test_predictive_ready_but_restricted_risk_only_monitors(self) -> None:
        research_object = make_research_object(
            processing_state=ProcessingState.PUBLISH_READY,
            risk_state=RiskState.RESTRICTED,
            attention_score=80,
        )
        predictive = self._publishable_predictive(streak=2)

        decision = self.gate.evaluate(research_object, predictive, None, self.base_claim_index)

        self.assertEqual(decision.decision, PublishDecisionType.MONITORING)
        self.assertIn("risk_state is restricted", decision.reasons)

    def test_predictive_ready_but_medium_conflict_only_monitors(self) -> None:
        research_object = make_research_object(
            processing_state=ProcessingState.PUBLISH_READY,
            risk_state=RiskState.NORMAL,
            attention_score=80,
        )
        predictive = self._publishable_predictive(streak=2)
        predictive.conflict_severity = ConflictSeverity.MEDIUM

        decision = self.gate.evaluate(research_object, predictive, None, self.base_claim_index)

        self.assertEqual(decision.decision, PublishDecisionType.MONITORING)
        self.assertIn("thesis conflict is medium or higher", decision.reasons)

    def test_higher_confidence_risk_thesis_preempts_when_risk_is_restricted(self) -> None:
        research_object = make_research_object(
            processing_state=ProcessingState.EVIDENCE_COMPLETE,
            risk_state=RiskState.RESTRICTED,
            attention_score=78,
        )
        predictive = self._publishable_predictive(streak=2)
        risk = self._risk_thesis(confidence=92)

        working_primary, working_opposing = select_working_theses(
            research_object,
            [predictive, risk],
            self.base_claim_index,
        )

        self.assertEqual(working_primary.thesis_id, "t-risk")
        self.assertEqual(working_opposing.thesis_id, "t-primary")

    def test_conflict_graph_does_not_collapse_to_clean_and_anchor_rules_hold(self) -> None:
        claim_a = make_claim(
            "A",
            predicate="trend_state",
            value="strong",
            direction=Direction.BULLISH,
            source_family=SourceFamily.CEX,
            evidence_level=EvidenceLevel.E4,
            confidence=90,
        )
        claim_b = make_claim(
            "B",
            predicate="trend_state",
            value="weak",
            direction=Direction.BEARISH,
            source_family=SourceFamily.ONCHAIN,
            evidence_level=EvidenceLevel.E3,
            confidence=60,
        )
        claim_c = make_claim(
            "C",
            predicate="trend_state",
            value="sideways",
            direction=Direction.BULLISH,
            source_family=SourceFamily.INFOFLOW,
            evidence_level=EvidenceLevel.E2,
            confidence=55,
        )

        groups = group_claim_conflicts([claim_a, claim_b, claim_c])
        by_pair = {frozenset(group.claim_ids): group for group in groups}

        self.assertEqual(len(groups), 3)
        self.assertEqual(by_pair[frozenset({"A", "B"})].resolution.value, "resolved")
        self.assertEqual(by_pair[frozenset({"B", "C"})].resolution.value, "unresolved")
        self.assertEqual(by_pair[frozenset({"C", "A"})].severity, ConflictSeverity.LOW)
        self.assertTrue(any(group.severity != ConflictSeverity.CLEAN for group in groups))

        self.assertFalse(claim_a.can_anchor(ConflictSeverity.MEDIUM))
        self.assertFalse(claim_b.can_anchor(ConflictSeverity.MEDIUM))
        self.assertFalse(claim_c.can_anchor(ConflictSeverity.LOW))

        research_object = make_research_object(processing_state=ProcessingState.ACTIVE_RESEARCH)
        theses = build_theses_for_object(research_object, [claim_a, claim_b, claim_c], groups)
        self.assertEqual(theses, [])

    def test_publish_gate_wrong_state_does_not_create_illegal_state(self) -> None:
        research_object = make_research_object(
            processing_state=ProcessingState.ACTIVE_RESEARCH,
            risk_state=RiskState.CAUTION,
            attention_score=80,
        )
        predictive = self._publishable_predictive(streak=2)
        decision = self.gate.evaluate(research_object, predictive, None, self.base_claim_index)

        self.assertEqual(decision.decision, PublishDecisionType.PUBLISH)

        self.machine.begin_cycle(research_object)
        with self.assertRaises(ValueError):
            self.machine.transition_processing(research_object, ProcessingState.PUBLISHED)
        self.assertEqual(research_object.processing_state, ProcessingState.ACTIVE_RESEARCH)

    def test_thesis_generation_before_active_research_does_not_pollute_state(self) -> None:
        research_object = make_research_object(
            processing_state=ProcessingState.SCREENED,
            risk_state=RiskState.NORMAL,
            attention_score=75,
        )
        claims = [
            self.base_claim_index["a1"],
            self.base_claim_index["a2"],
            self.base_claim_index["a3"],
        ]
        theses = build_theses_for_object(research_object, claims, [])

        self.assertTrue(any(thesis.thesis_type == ThesisType.PREDICTIVE for thesis in theses))
        self.assertEqual(research_object.processing_state, ProcessingState.SCREENED)

        self.machine.begin_cycle(research_object)
        with self.assertRaises(ValueError):
            self.machine.transition_processing(research_object, ProcessingState.EVIDENCE_COMPLETE)
        self.assertEqual(research_object.processing_state, ProcessingState.SCREENED)

    def test_three_cycle_loop_stability(self) -> None:
        research_object = make_research_object(
            processing_state=ProcessingState.PUBLISH_READY,
            risk_state=RiskState.CAUTION,
            attention_score=74,
        )
        cycle1_bull = self._publishable_predictive(streak=1)

        working_primary, _ = select_working_theses(research_object, [cycle1_bull], self.base_claim_index)
        self.assertEqual(working_primary.thesis_id, "t-primary")
        self.assertEqual(working_primary.working_primary_streak, 2)

        cycle1_decision = self.gate.evaluate(research_object, cycle1_bull, None, self.base_claim_index)
        self.assertEqual(cycle1_decision.decision, PublishDecisionType.PUBLISH)

        self.machine.begin_cycle(research_object)
        self.machine.transition_processing(research_object, ProcessingState.MONITORING)
        research_object.risk_state = RiskState.RESTRICTED

        cycle2_risk = self._risk_thesis(confidence=92)
        working_primary, working_opposing = select_working_theses(
            research_object,
            [cycle1_bull, cycle2_risk],
            self.base_claim_index,
        )
        self.assertEqual(working_primary.thesis_id, "t-risk")
        self.assertEqual(working_opposing.thesis_id, "t-primary")

        cycle2_decision = self.gate.evaluate(research_object, working_primary, working_opposing, self.base_claim_index)
        self.assertEqual(cycle2_decision.decision, PublishDecisionType.MONITORING)

        self.machine.begin_cycle(research_object)
        self.machine.transition_processing(research_object, ProcessingState.ACTIVE_RESEARCH)
        research_object.risk_state = RiskState.CAUTION

        cycle3_bull = make_thesis(
            "t-primary-v2",
            thesis_type=ThesisType.PREDICTIVE,
            status=ThesisStatus.ACTIVE,
            anchor_claim_ids=["a1", "a2"],
            supporting_claim_ids=["a3"],
            working_primary_streak=0,
        )
        working_primary, _ = select_working_theses(research_object, [cycle3_bull], self.base_claim_index)

        self.assertEqual(research_object.processing_state, ProcessingState.ACTIVE_RESEARCH)
        self.assertEqual(working_primary.thesis_id, "t-primary-v2")
        self.assertEqual(working_primary.working_primary_streak, 1)


if __name__ == "__main__":
    unittest.main()
