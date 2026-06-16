from __future__ import annotations

import unittest

from tests.test_helpers import ROOT

from enhengclaw.quant_research.postmortem import (
    _resolve_experiment_root,
    build_sharpe_anomaly_postmortem_evidence,
)


ANOMALY_ALPHA_ID = "2026-04-20-baseline-eth-balanced-logistic-regression-single-asset"
HASHED_ALPHA_ID = "2026-04-22-baseline-sui-conservative-logistic-regression-single-asset"


class QuantResearchPostmortemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = build_sharpe_anomaly_postmortem_evidence(
            alpha_id=ANOMALY_ALPHA_ID,
            artifacts_root=ROOT / "artifacts" / "quant_research",
            repo_root=ROOT,
            now_utc="2026-04-21T00:00:00Z",
        )

    def test_single_asset_label_horizon_is_inferred_as_24h(self) -> None:
        self.assertEqual(self.evidence["label_horizon_bars"], 6)
        self.assertEqual(self.evidence["label_horizon_hours"], 24.0)
        self.assertEqual(self.evidence["bar_interval_hours"], 4.0)

    def test_split_boundary_contamination_is_detected(self) -> None:
        contamination = self.evidence["boundary_contamination_counts"]
        self.assertEqual(contamination["train_to_validation"]["contaminated_row_count"], 6)
        self.assertEqual(contamination["validation_to_test"]["contaminated_row_count"], 6)
        self.assertEqual(len(self.evidence["walk_forward_windows"]), 4)
        for window in self.evidence["walk_forward_windows"]:
            self.assertEqual(window["train_to_validation_contaminated_row_count"], 6)
            self.assertEqual(window["validation_to_test_contaminated_row_count"], 6)

    def test_overlap_is_primary_root_cause(self) -> None:
        self.assertEqual(self.evidence["primary_root_cause"], "overlap")
        self.assertEqual(self.evidence["secondary_root_causes"], [])
        self.assertTrue(self.evidence["backtest_horizon_mismatch"]["detected"])
        candidate_map = {item["name"]: item for item in self.evidence["candidate_root_causes"]}
        self.assertTrue(candidate_map["overlap"]["supported"])
        self.assertFalse(candidate_map["look_ahead_bias"]["supported"])

    def test_resolve_experiment_root_supports_shortened_hashed_directory_names(self) -> None:
        experiment_root = _resolve_experiment_root(
            artifacts_root=ROOT / "artifacts" / "quant_research",
            alpha_id=HASHED_ALPHA_ID,
        )
        self.assertTrue(experiment_root.exists())
        self.assertEqual(experiment_root.name, "2026-04-22-baseline-sui-conservative-log-4b6ee4be7cb2")


if __name__ == "__main__":
    unittest.main()
