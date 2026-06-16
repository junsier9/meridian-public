from __future__ import annotations

import unittest

from tests.test_helpers import make_claim, make_research_object, make_thesis

from enhengclaw.core.enums import (
    ClaimType,
    Direction,
    EvidenceLevel,
    RiskState,
    SourceFamily,
    ThesisType,
)
from enhengclaw.core.thesis import select_working_theses


class ThesisPriorityTests(unittest.TestCase):
    def _claim_index(self) -> dict[str, object]:
        return {
            "bull1": make_claim(
                "bull1",
                claim_type=ClaimType.MEASUREMENT,
                predicate="spot_breakout",
                value="yes",
                direction=Direction.BULLISH,
                source_family=SourceFamily.CEX,
                evidence_level=EvidenceLevel.E4,
                confidence=82,
            ),
            "bull2": make_claim(
                "bull2",
                claim_type=ClaimType.FLOW,
                predicate="smart_money_buy",
                value="yes",
                direction=Direction.BULLISH,
                source_family=SourceFamily.ONCHAIN,
                evidence_level=EvidenceLevel.E4,
                confidence=78,
            ),
            "risk1": make_claim(
                "risk1",
                claim_type=ClaimType.RISK_FLAG,
                predicate="bridge_risk",
                value="possible",
                direction=Direction.RISK,
                source_family=SourceFamily.SAFETY,
                evidence_level=EvidenceLevel.E4,
                confidence=74,
            ),
        }

    def test_primary_and_opposing_thesis_are_selected(self) -> None:
        claim_index = self._claim_index()
        research_object = make_research_object(risk_state=RiskState.CAUTION)
        primary = make_thesis(
            "t-primary",
            anchor_claim_ids=["bull1", "bull2"],
            thesis_type=ThesisType.PREDICTIVE,
        )
        risk = make_thesis(
            "t-risk",
            thesis_type=ThesisType.RISK,
            direction=Direction.RISK,
            anchor_claim_ids=["risk1"],
            confidence=70,
        )

        working_primary, working_opposing = select_working_theses(research_object, [primary, risk], claim_index)
        self.assertEqual(working_primary.thesis_id, "t-primary")
        self.assertEqual(working_opposing.thesis_id, "t-risk")

    def test_risk_thesis_preempts_when_restricted(self) -> None:
        claim_index = self._claim_index()
        research_object = make_research_object(risk_state=RiskState.RESTRICTED)
        primary = make_thesis(
            "t-primary",
            anchor_claim_ids=["bull1", "bull2"],
            thesis_type=ThesisType.PREDICTIVE,
        )
        risk = make_thesis(
            "t-risk",
            thesis_type=ThesisType.RISK,
            direction=Direction.RISK,
            anchor_claim_ids=["risk1"],
            confidence=76,
        )

        working_primary, working_opposing = select_working_theses(research_object, [primary, risk], claim_index)
        self.assertEqual(working_primary.thesis_id, "t-risk")
        self.assertEqual(working_opposing.thesis_id, "t-primary")

    def test_working_primary_streak_continues_and_interrupts(self) -> None:
        claim_index = self._claim_index()
        research_object = make_research_object(risk_state=RiskState.CAUTION)
        primary = make_thesis(
            "t-primary",
            anchor_claim_ids=["bull1", "bull2"],
            thesis_type=ThesisType.PREDICTIVE,
        )
        risk = make_thesis(
            "t-risk",
            thesis_type=ThesisType.RISK,
            direction=Direction.RISK,
            anchor_claim_ids=["risk1"],
            confidence=70,
        )

        working_primary, _ = select_working_theses(research_object, [primary, risk], claim_index)
        self.assertEqual(working_primary.working_primary_streak, 1)

        working_primary, _ = select_working_theses(research_object, [primary, risk], claim_index)
        self.assertEqual(working_primary.working_primary_streak, 2)

        research_object.risk_state = RiskState.RESTRICTED
        working_primary, _ = select_working_theses(research_object, [primary, risk], claim_index)
        self.assertEqual(working_primary.thesis_id, "t-risk")
        self.assertEqual(working_primary.working_primary_streak, 1)

        research_object.risk_state = RiskState.CAUTION
        new_primary = make_thesis(
            "t-primary-new",
            anchor_claim_ids=["bull1", "bull2"],
            thesis_type=ThesisType.PREDICTIVE,
        )
        working_primary, _ = select_working_theses(research_object, [new_primary, risk], claim_index)
        self.assertEqual(working_primary.thesis_id, "t-primary-new")
        self.assertEqual(working_primary.working_primary_streak, 1)


if __name__ == "__main__":
    unittest.main()
