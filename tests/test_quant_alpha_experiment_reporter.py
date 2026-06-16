from __future__ import annotations

import unittest

from enhengclaw.quant_research.alpha_experiment_reporter import build_alpha_experiment_card
from enhengclaw.quant_research.promotion import h10d_promotion_evidence_blockers


class AlphaExperimentReporterTests(unittest.TestCase):
    def test_build_alpha_experiment_card_requires_full_gate_fields(self) -> None:
        card = build_alpha_experiment_card(
            experiment_id="demo-exp",
            strategy_id="candidate",
            fixed_set_comparison={
                "status": "computed",
                "candidate_label": "candidate",
                "artifact_paths": {"comparison_json_path": "x"},
                "pairwise_results": [
                    {
                        "candidate_a": "candidate",
                        "candidate_b": "v5_rw_bridge_no_overlay_h10d",
                        "observed_cumulative_return_diff": 0.12,
                        "observed_sharpe_diff": 0.3,
                        "bootstrap": {},
                    },
                    {
                        "candidate_a": "candidate",
                        "candidate_b": "v6_h10d",
                        "observed_cumulative_return_diff": 0.05,
                        "observed_sharpe_diff": 0.1,
                        "bootstrap": {},
                    },
                ],
                "promotion_gate": {"passed": True, "blocker_codes": []},
            },
            statistical_falsification={
                "status": "cleared",
                "tests": {
                    "symbol_holdout": {"passed": True},
                    "delayed_execution": {"passed": True},
                    "cost_stress": {"passed": True},
                    "liquidity_bucket_consistency": {"passed": True},
                },
            },
            overlay_ablation={"status": "present"},
        )

        self.assertTrue(card["go_no_go"])
        self.assertTrue(card["promotion_gate_fields_complete"])
        self.assertFalse(card["legacy_only_effective"])

    def test_build_alpha_experiment_card_does_not_require_overlay_for_no_overlay_candidate(self) -> None:
        card = build_alpha_experiment_card(
            experiment_id="demo-exp",
            strategy_id="candidate_no_overlay_h10d",
            fixed_set_comparison={
                "status": "computed",
                "candidate_label": "candidate_no_overlay_h10d",
                "artifact_paths": {"comparison_json_path": "x"},
                "pairwise_results": [
                    {
                        "candidate_a": "candidate_no_overlay_h10d",
                        "candidate_b": "v5_rw_bridge_no_overlay_h10d",
                        "observed_cumulative_return_diff": 0.12,
                        "observed_sharpe_diff": 0.3,
                        "bootstrap": {},
                    }
                ],
                "promotion_gate": {"passed": True, "blocker_codes": []},
            },
            statistical_falsification={
                "status": "cleared",
                "tests": {
                    "symbol_holdout": {"passed": True},
                    "delayed_execution": {"passed": True},
                    "cost_stress": {"passed": True},
                    "liquidity_bucket_consistency": {"passed": True},
                },
            },
        )

        self.assertTrue(card["go_no_go"])
        self.assertFalse(card["overlay_ablation_required"])
        self.assertTrue(card["promotion_gate_fields_complete"])

    def test_build_alpha_experiment_card_keeps_missing_tests_separate_from_measured_failures(self) -> None:
        card = build_alpha_experiment_card(
            experiment_id="demo-exp",
            strategy_id="candidate_no_overlay_h10d",
            fixed_set_comparison={
                "status": "computed",
                "candidate_label": "candidate_no_overlay_h10d",
                "artifact_paths": {"comparison_json_path": "x"},
                "pairwise_results": [],
                "promotion_gate": {"passed": True, "blocker_codes": []},
            },
            statistical_falsification={
                "status": "skipped",
                "applicable": False,
                "reason": "unsupported_experiment",
                "tests": {},
            },
        )

        self.assertFalse(card["go_no_go"])
        self.assertIn("cost_stress_not_measured_fail_closed", card["blocker_codes"])
        self.assertIn("delayed_execution_not_measured_fail_closed", card["blocker_codes"])
        self.assertNotIn("cost_stress_failed", card["blocker_codes"])
        self.assertNotIn("delay_stress_failed", card["blocker_codes"])
        self.assertEqual(
            card["statistical_falsification_test_states"]["cost_stress"]["status"],
            "not_measured_fail_closed",
        )

    def test_h10d_promotion_guard_surfaces_blocker_attribution_codes(self) -> None:
        alpha_card = {
            "shape": "cross_sectional",
            "bar_interval_ms": 86_400_000,
            "label_horizon_bars": 10,
            "label_contract_id": "forward_return_execution_aligned.v1",
            "research_lane": "hypothesis_factor",
            "fixed_set_comparison": {
                "status": "computed",
                "promotion_gate": {
                    "passed": True,
                    "blocker_codes": [],
                    "candidate_summary": {
                        "full_oos_period_count": 64,
                        "full_oos_max_trade_participation_rate": 0.001,
                    },
                },
            },
            "overlay_ablation": {
                "status": "computed",
                "promotion_gate": {"passed": True, "blocker_codes": []},
            },
            "blocker_attribution_gate": {
                "status": "completed_symbol_bucket_strict_gate",
                "passed": False,
                "blocker_codes": ["top_bucket_only", "symbol_holdout_dependency"],
                "missing_statistical_falsification_policy": "not_measured_fail_closed",
            },
        }

        blockers = h10d_promotion_evidence_blockers(alpha_card=alpha_card, require_applicable=True)

        self.assertIn("h10d_promotion.blocker_attribution.strict_gate_not_passed", blockers)
        self.assertIn("blocker_attribution.blocker_code=top_bucket_only", blockers)
        self.assertIn("blocker_attribution.blocker_code=symbol_holdout_dependency", blockers)


if __name__ == "__main__":
    unittest.main()
