from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.governance.shadow_admission import ShadowAdmissionRunner
from enhengclaw.governance.shadow_contribution import (
    ContributionLedger,
    HEALTH_CANDIDATE_FOR_REEVALUATION,
    HEALTH_KEEP_SHADOW_ONLY,
    HEALTH_PROBATION,
)
from tests.test_helpers import enter_runtime_worker_class


class ShadowContributionLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        enter_runtime_worker_class(cls, slug="test-shadow-contribution")
        cls.before = ShadowAdmissionRunner().compare_with_filter()
        cls.ledger = ContributionLedger().build_from_report(cls.before)
        cls.after = ShadowAdmissionRunner().compare_with_filter()

    def test_ledger_does_not_change_runtime_behavior(self) -> None:
        self.assertEqual(self.ledger.summary.classification_snapshot, self.before.after.classification.classification)
        self.assertEqual(self.before.after.metrics.decision_change_rate, self.after.after.metrics.decision_change_rate)
        self.assertEqual(self.before.after.metrics.material_change_rate, self.after.after.metrics.material_change_rate)
        self.assertEqual(
            [scenario.filtered.candidate_if_enabled.decision for scenario in self.before.scenarios if scenario.filtered.candidate_if_enabled is not None],
            [scenario.filtered.candidate_if_enabled.decision for scenario in self.after.scenarios if scenario.filtered.candidate_if_enabled is not None],
        )

    def test_ledger_statistics_are_consistent_with_shadow_reports(self) -> None:
        self.assertEqual(self.ledger.summary.classification_snapshot, self.before.after.classification.classification)
        self.assertEqual(self.ledger.summary.recommendation_snapshot, self.before.after.recommendation.recommendation)
        self.assertEqual(self.ledger.summary.decision_relevance_rate, self.before.after.metrics.decision_change_rate)
        self.assertEqual(self.ledger.summary.structural_noise_rate, self.before.before.metrics.no_op_structural_change_rate)
        self.assertEqual(self.ledger.summary.signal_attempt_count, self.ledger.summary.shadow_signal_count)
        self.assertGreaterEqual(self.ledger.summary.schema_conformance_rate, 0.0)
        self.assertGreaterEqual(self.ledger.summary.data_validity_rate, 0.0)
        self.assertEqual(self.ledger.summary.accepted_signal_count, 0)
        self.assertEqual(self.ledger.summary.acceptance_rate, 0.0)
        self.assertTrue(all(entry.classification_snapshot == self.before.after.classification.classification for entry in self.ledger.entries))
        self.assertTrue(all(entry.recommendation_snapshot == self.before.after.recommendation.recommendation for entry in self.ledger.entries))

    def test_known_bad_and_rejected_scenarios_record_no_net_contribution(self) -> None:
        known_bad_entries = [entry for entry in self.ledger.entries if entry.category == "known_bad"]

        self.assertEqual(len(known_bad_entries), 2)
        for entry in known_bad_entries:
            self.assertEqual(entry.candidate_status, "rejected")
            self.assertEqual(entry.shadow_signal_count, 0)
            self.assertEqual(entry.accepted_signal_count, 0)
            self.assertEqual(entry.decision_changed, False)
            self.assertEqual(entry.risk_state_changed, False)
            self.assertEqual(entry.thesis_changed, False)
            self.assertEqual(entry.allocation_changed, False)
            self.assertIn("candidate_batch_rejected", entry.rejection_reasons)

    def test_zero_accepted_provider_is_not_marked_for_promotion(self) -> None:
        self.assertEqual(self.ledger.summary.accepted_signal_count, 0)
        self.assertNotEqual(self.ledger.health.status, HEALTH_CANDIDATE_FOR_REEVALUATION)
        self.assertIn(self.ledger.health.status, {HEALTH_KEEP_SHADOW_ONLY, HEALTH_PROBATION})
        self.assertNotIn("retire", self.ledger.health.status)
        self.assertTrue(any("shadow" in reason or "observation" in reason for reason in self.ledger.health.reasons))


if __name__ == "__main__":
    unittest.main()
