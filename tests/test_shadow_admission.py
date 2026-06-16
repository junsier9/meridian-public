from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.governance.shadow_admission import ShadowAdmissionRunner
from tests.test_helpers import enter_runtime_worker_class


class ShadowAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        enter_runtime_worker_class(cls, slug="test-shadow-admission")
        cls.report = ShadowAdmissionRunner().compare_with_filter()

    def test_filter_does_not_change_baseline_runtime(self) -> None:
        for scenario in self.report.scenarios:
            self.assertEqual(scenario.original.baseline.decision, scenario.filtered.baseline.decision)
            self.assertEqual(scenario.original.baseline.risk_state, scenario.filtered.baseline.risk_state)
            self.assertEqual(scenario.original.baseline.processing_state, scenario.filtered.baseline.processing_state)
            self.assertEqual(scenario.original.baseline.attention_score, scenario.filtered.baseline.attention_score)

    def test_filter_lowers_structural_noise(self) -> None:
        self.assertGreater(self.report.before.metrics.material_change_rate, self.report.after.metrics.material_change_rate)
        self.assertGreater(self.report.before.metrics.no_op_structural_change_rate, self.report.after.metrics.no_op_structural_change_rate)
        self.assertLess(self.report.before.metrics.no_op_consistency_rate, self.report.after.metrics.no_op_consistency_rate)
        self.assertEqual(self.report.after.metrics.material_change_rate, 0.0)
        self.assertEqual(self.report.after.metrics.no_op_consistency_rate, 1.0)

    def test_filter_does_not_let_known_bad_candidate_through(self) -> None:
        known_bad = [scenario for scenario in self.report.scenarios if scenario.category == "known_bad"]
        self.assertEqual(len(known_bad), 2)
        for scenario in known_bad:
            self.assertEqual(scenario.original.candidate_status, "rejected")
            self.assertEqual(scenario.filtered.candidate_status, "rejected")
            self.assertEqual(len(scenario.admission.accepted_signals), 0)

    def test_filter_improves_metrics_but_keeps_recommendation_cautious(self) -> None:
        self.assertEqual(self.report.before.recommendation.recommendation, "stay_shadow_only")
        self.assertEqual(self.report.after.recommendation.recommendation, "stay_shadow_only")
        self.assertEqual(self.report.after.classification.classification, "noise")
        self.assertEqual(self.report.after.metrics.decision_change_rate, 0.0)
        self.assertEqual(self.report.after.metrics.known_bad_rejection_rate, 1.0)

    def test_filter_rejects_structural_noise_signals_in_normal_paths(self) -> None:
        normal_bull = next(
            scenario for scenario in self.report.scenarios if scenario.category == "normal" and scenario.scenario == "bullish_publish"
        )
        self.assertEqual(len(normal_bull.admission.accepted_signals), 0)
        self.assertEqual(len(normal_bull.admission.rejected_signals), 1)
        self.assertIn("single_source_onchain_flow_without_cross_support", normal_bull.admission.rejection_reasons)
        self.assertIn("known_good_structural_change_without_stable_edge", normal_bull.admission.rejection_reasons)


if __name__ == "__main__":
    unittest.main()
