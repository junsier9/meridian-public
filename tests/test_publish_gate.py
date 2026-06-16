from __future__ import annotations

import unittest

from tests.test_helpers import make_claim, make_research_object, make_thesis

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
)
from enhengclaw.core.publish_gate import PublishDecisionType, PublishGate


class PublishGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gate = PublishGate()
        self.claim_index = {
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
                predicate="smart_money_buy",
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
                confidence=72,
            ),
        }

    def test_predictive_publish_allowed_when_conditions_met(self) -> None:
        research_object = make_research_object(
            processing_state=ProcessingState.PUBLISH_READY,
            risk_state=RiskState.CAUTION,
            attention_score=70,
        )
        thesis = make_thesis(
            "t-primary",
            thesis_type=ThesisType.PREDICTIVE,
            status=ThesisStatus.PUBLISHABLE,
            anchor_claim_ids=["a1", "a2"],
            supporting_claim_ids=["a3"],
            working_primary_streak=2,
        )

        decision = self.gate.evaluate(research_object, thesis, None, self.claim_index)
        self.assertEqual(decision.decision, PublishDecisionType.PUBLISH)

    def test_missing_one_predictive_condition_only_monitors(self) -> None:
        research_object = make_research_object(
            processing_state=ProcessingState.PUBLISH_READY,
            risk_state=RiskState.CAUTION,
            attention_score=70,
        )
        thesis = make_thesis(
            "t-primary",
            thesis_type=ThesisType.PREDICTIVE,
            status=ThesisStatus.PUBLISHABLE,
            anchor_claim_ids=["a1", "a2"],
            supporting_claim_ids=["a3"],
            working_primary_streak=1,
        )

        decision = self.gate.evaluate(research_object, thesis, None, self.claim_index)
        self.assertEqual(decision.decision, PublishDecisionType.MONITORING)
        self.assertIn("predictive thesis has not stayed primary for two consecutive evaluations", decision.reasons)

    def test_restricted_risk_state_prevents_publish(self) -> None:
        research_object = make_research_object(
            processing_state=ProcessingState.PUBLISH_READY,
            risk_state=RiskState.RESTRICTED,
            attention_score=75,
        )
        thesis = make_thesis(
            "t-primary",
            thesis_type=ThesisType.PREDICTIVE,
            status=ThesisStatus.PUBLISHABLE,
            anchor_claim_ids=["a1", "a2"],
            supporting_claim_ids=["a3"],
            working_primary_streak=2,
        )

        decision = self.gate.evaluate(research_object, thesis, None, self.claim_index)
        self.assertEqual(decision.decision, PublishDecisionType.MONITORING)
        self.assertIn("risk_state is restricted", decision.reasons)

    def test_unresolved_medium_conflict_prevents_publish(self) -> None:
        research_object = make_research_object(
            processing_state=ProcessingState.PUBLISH_READY,
            risk_state=RiskState.CAUTION,
            attention_score=75,
        )
        primary = make_thesis(
            "t-primary",
            thesis_type=ThesisType.PREDICTIVE,
            status=ThesisStatus.PUBLISHABLE,
            anchor_claim_ids=["a1", "a2"],
            supporting_claim_ids=["a3"],
            working_primary_streak=2,
        )
        primary.conflict_severity = ConflictSeverity.MEDIUM
        opposing = make_thesis(
            "t-risk",
            thesis_type=ThesisType.RISK,
            direction=Direction.RISK,
            anchor_claim_ids=["r1"],
        )
        opposing.conflict_severity = ConflictSeverity.MEDIUM

        decision = self.gate.evaluate(research_object, primary, opposing, self.claim_index)
        self.assertEqual(decision.decision, PublishDecisionType.MONITORING)
        self.assertIn("thesis conflict is medium or higher", decision.reasons)


if __name__ == "__main__":
    unittest.main()
