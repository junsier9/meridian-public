from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.governance.shadow_promotion import (
    CLASSIFY_NOISE,
    PromotionMetrics,
    PromotionPolicy,
    RECOMMEND_LIMITED_PARTICIPATE,
    RECOMMEND_REJECT_PROVIDER,
    RECOMMEND_STAY_SHADOW_ONLY,
    ShadowPromotionCorpus,
    ShadowPromotionRunner,
)
from tests.test_helpers import enter_runtime_worker_class


class ShadowPromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        enter_runtime_worker_class(cls, slug="test-shadow-promotion")

    def test_corpus_loads_expected_entries(self) -> None:
        corpus = ShadowPromotionCorpus(ROOT / "fixtures" / "shadow_promotion_corpus")
        entries = corpus.iter_entries()
        self.assertEqual(len(entries), 5)
        self.assertEqual([entry.category for entry in entries].count("normal"), 2)
        self.assertEqual([entry.category for entry in entries].count("edge"), 1)
        self.assertEqual([entry.category for entry in entries].count("known_bad"), 2)

    def test_runner_produces_structured_diff_for_normal_scenario(self) -> None:
        runner = ShadowPromotionRunner(ShadowPromotionCorpus(ROOT / "fixtures" / "shadow_promotion_corpus"))
        entry = next(entry for entry in runner.corpus.iter_entries() if entry.category == "normal" and entry.scenario == "bullish_publish")
        comparison = runner.compare_entry(entry)
        self.assertEqual(comparison.candidate_status, "ok")
        self.assertTrue(comparison.official_shadow_decision_unchanged)
        self.assertEqual(comparison.baseline.decision, "monitoring")
        self.assertIsNotNone(comparison.shadow_preview)
        self.assertEqual(comparison.shadow_preview.signal_count, 1)
        self.assertIsNotNone(comparison.diff)
        self.assertEqual(comparison.diff.attention_delta, 11)
        self.assertEqual(comparison.diff.allocation_delta, "tier_c:monitoring->tier_b:monitoring")
        self.assertFalse(comparison.diff.decision_changed)

    def test_known_bad_candidate_is_rejected_and_baseline_is_preserved(self) -> None:
        runner = ShadowPromotionRunner(ShadowPromotionCorpus(ROOT / "fixtures" / "shadow_promotion_corpus"))
        entry = next(entry for entry in runner.corpus.iter_entries() if entry.category == "known_bad" and entry.scenario == "missing_field")
        comparison = runner.compare_entry(entry)
        self.assertEqual(comparison.baseline.decision, "monitoring")
        self.assertEqual(comparison.candidate_status, "rejected")
        self.assertIn("missing required field", comparison.candidate_error or "")
        self.assertIsNone(comparison.candidate_if_enabled)
        self.assertIsNone(comparison.diff)

    def test_actual_corpus_recommends_stay_shadow_only(self) -> None:
        report = ShadowPromotionRunner(ShadowPromotionCorpus(ROOT / "fixtures" / "shadow_promotion_corpus")).compare_all()
        self.assertEqual(report.scenario_count, 5)
        self.assertEqual(report.metrics.comparable_scenarios, 3)
        self.assertEqual(report.metrics.candidate_rejected_count, 2)
        self.assertEqual(report.metrics.decision_change_rate, 0.0)
        self.assertEqual(report.metrics.material_change_rate, 1.0)
        self.assertEqual(report.metrics.known_bad_rejection_rate, 1.0)
        self.assertEqual(report.metrics.risk_bias_rate, 0.0)
        self.assertEqual(report.metrics.bullish_bias_rate, 0.3333)
        self.assertEqual(report.metrics.thesis_flip_rate, 0.3333)
        self.assertEqual(report.metrics.no_op_structural_change_rate, 1.0)
        self.assertEqual(report.classification.classification, CLASSIFY_NOISE)
        self.assertEqual(len(report.sensitivity), 2)
        self.assertEqual(report.sensitivity[0].setting_name, "relaxed_attention_threshold")
        self.assertEqual(report.sensitivity[0].decision_change_rate, 0.6667)
        self.assertTrue(report.sensitivity[0].sudden_rise)
        self.assertEqual(report.recommendation.recommendation, RECOMMEND_STAY_SHADOW_ONLY)

    def test_policy_rejects_dangerous_good_publish_demotions(self) -> None:
        runner = ShadowPromotionRunner(policy=PromotionPolicy())
        metrics = PromotionMetrics(
            total_scenarios=4,
            comparable_scenarios=4,
            candidate_rejected_count=0,
            decision_change_rate=0.25,
            material_change_rate=0.25,
            publish_to_monitoring_count=1,
            monitoring_to_blocked_count=0,
            publish_to_blocked_count=0,
            risk_state_uplift_frequency=0.25,
            thesis_replacement_frequency=0.25,
            no_op_consistency_rate=0.75,
            known_bad_rejection_rate=1.0,
            known_bad_accepted_count=0,
            positive_edge_risk_uplift_count=1,
            risk_bias_rate=0.25,
            bullish_bias_rate=0.25,
            thesis_flip_rate=0.25,
            no_op_structural_change_rate=0.25,
        )
        recommendation = runner.evaluate_promotion(metrics)
        self.assertEqual(recommendation.recommendation, RECOMMEND_REJECT_PROVIDER)

    def test_policy_can_mark_limited_participation_for_safe_positive_metrics(self) -> None:
        runner = ShadowPromotionRunner(policy=PromotionPolicy())
        metrics = PromotionMetrics(
            total_scenarios=6,
            comparable_scenarios=4,
            candidate_rejected_count=2,
            decision_change_rate=0.0,
            material_change_rate=0.25,
            publish_to_monitoring_count=0,
            monitoring_to_blocked_count=0,
            publish_to_blocked_count=0,
            risk_state_uplift_frequency=0.25,
            thesis_replacement_frequency=0.25,
            no_op_consistency_rate=0.75,
            known_bad_rejection_rate=1.0,
            known_bad_accepted_count=0,
            positive_edge_risk_uplift_count=1,
            risk_bias_rate=0.0,
            bullish_bias_rate=0.75,
            thesis_flip_rate=0.25,
            no_op_structural_change_rate=0.25,
        )
        recommendation = runner.evaluate_promotion(metrics)
        self.assertEqual(recommendation.recommendation, RECOMMEND_LIMITED_PARTICIPATE)


if __name__ == "__main__":
    unittest.main()
