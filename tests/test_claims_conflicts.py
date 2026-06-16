from __future__ import annotations

import unittest

from tests.test_helpers import make_claim, make_signal

from enhengclaw.core.claims import EvidenceRef, claim_from_signal
from enhengclaw.core.conflicts import group_claim_conflicts
from enhengclaw.core.enums import (
    ClaimStatus,
    ClaimType,
    ConflictResolution,
    ConflictSeverity,
    Direction,
    EvidenceLevel,
    SourceFamily,
)


class ClaimConflictTests(unittest.TestCase):
    def test_claim_basic_status_progression(self) -> None:
        signal = make_signal(
            "s1",
            "AIX",
            "news",
            "rumor",
            ClaimType.CAUSAL,
            Direction.NEUTRAL,
            SourceFamily.INFOFLOW,
            EvidenceLevel.E2,
            72,
        )
        claim = claim_from_signal(signal, "ro-test", "c1")
        self.assertEqual(claim.status, ClaimStatus.PROPOSED)

        claim.add_evidence(EvidenceRef("e2", EvidenceLevel.E3, SourceFamily.OFFICIAL, True))
        claim.advance_basic_status()
        self.assertEqual(claim.status, ClaimStatus.SUPPORTED)

    def test_claim_level_conflict_grouping_builds_group(self) -> None:
        left = make_claim(
            "c1",
            predicate="liquidity_state",
            value="strong",
            direction=Direction.BULLISH,
            evidence_level=EvidenceLevel.E3,
            confidence=65,
        )
        right = make_claim(
            "c2",
            predicate="liquidity_state",
            value="weak",
            direction=Direction.BEARISH,
            source_family=SourceFamily.ONCHAIN,
            evidence_level=EvidenceLevel.E3,
            confidence=66,
        )

        groups = group_claim_conflicts([left, right])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].severity, ConflictSeverity.MEDIUM)
        self.assertEqual(groups[0].resolution, ConflictResolution.UNRESOLVED)
        self.assertEqual(left.status, ClaimStatus.CONTESTED)
        self.assertEqual(right.status, ClaimStatus.CONTESTED)

    def test_medium_unresolved_conflict_blocks_anchor_use(self) -> None:
        left = make_claim(
            "c1",
            predicate="trend_strength",
            value="up",
            direction=Direction.BULLISH,
            evidence_level=EvidenceLevel.E3,
            confidence=64,
        )
        right = make_claim(
            "c2",
            predicate="trend_strength",
            value="down",
            direction=Direction.BEARISH,
            source_family=SourceFamily.ONCHAIN,
            evidence_level=EvidenceLevel.E3,
            confidence=63,
        )
        groups = group_claim_conflicts([left, right])

        self.assertEqual(groups[0].severity, ConflictSeverity.MEDIUM)
        self.assertFalse(left.can_anchor(groups[0].severity))
        self.assertFalse(right.can_anchor(groups[0].severity))

    def test_high_unresolved_conflict_blocks_anchor_use(self) -> None:
        left = make_claim(
            "c1",
            predicate="spot_lead",
            value="yes",
            direction=Direction.BULLISH,
            evidence_level=EvidenceLevel.E4,
            confidence=72,
        )
        right = make_claim(
            "c2",
            predicate="spot_lead",
            value="no",
            direction=Direction.BEARISH,
            source_family=SourceFamily.ONCHAIN,
            evidence_level=EvidenceLevel.E4,
            confidence=71,
        )
        groups = group_claim_conflicts([left, right])

        self.assertEqual(groups[0].severity, ConflictSeverity.HIGH)
        self.assertFalse(left.can_anchor(groups[0].severity))
        self.assertFalse(right.can_anchor(groups[0].severity))


if __name__ == "__main__":
    unittest.main()
