from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.default_off_scorer_shadow_wrapper import (  # noqa: E402
    DefaultOffScorerShadowConfig,
    frame_sha256,
    run_default_off_scorer_shadow_wrapper,
)
from scripts.live_trading.run_hv_balanced_12factor_p10d_default_off_scorer_wrapper import (  # noqa: E402
    run_p10d_default_off_scorer_wrapper,
)


REQUIRED_FACTORS = [
    "intraday_realized_vol_4h_to_1d_smooth_60",
    "realized_volatility_5",
    "distance_to_high_60",
    "distance_to_high_5",
    "coinglass_top_trader_long_pct_smooth_5",
    "liquidity_stress_qv_iv",
    "momentum_decay_5_20",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "quality_funding_oi",
    "downside_upside_vol_ratio_30",
    "funding_basis_residual_implied_repo_30",
    "settlement_cycle_premium_60d",
]


class HvBalanced12FactorP10dDefaultOffScorerWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p10d-scorer-wrapper-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_disabled_preserves_baseline_and_writes_no_shadow_artifacts(self) -> None:
        baseline = self._baseline_scores()
        baseline_hash = frame_sha256(baseline)

        result = run_default_off_scorer_shadow_wrapper(
            config=DefaultOffScorerShadowConfig(enabled=False),
            baseline_scores=baseline,
            executor_input_scores=baseline.copy(),
            shadow_scorer_scores=self._shadow_scores(),
            run_id="disabled",
            now=datetime(2026, 6, 8, 14, 0, tzinfo=UTC),
        )

        self.assertEqual(result.summary["status"], "ready")
        self.assertFalse(result.summary["hook_enabled"])
        self.assertEqual(frame_sha256(result.executor_scores), baseline_hash)
        self.assertTrue(result.summary["baseline_scores_byte_for_byte_unchanged"])
        self.assertTrue(result.summary["wrapper_output_scores_hash_equals_baseline"])
        self.assertTrue(result.summary["executor_consumes_baseline_only"])
        self.assertEqual(result.summary["shadow_artifacts_written_count"], 0)
        self.assertEqual(result.summary["shadow_artifact_paths"], [])
        self.assertFalse(result.summary["candidate_scorer_loaded_into_executor"])
        self.assertFalse(result.summary["executor_invoked"])
        self.assertEqual(result.summary["orders_submitted"], 0)
        self.assertEqual(result.summary["fill_count"], 0)

    def test_enabled_writes_shadow_artifact_only_and_executor_gets_baseline(self) -> None:
        baseline = self._baseline_scores()
        shadow = self._shadow_scores()
        proof_root = self.temp_dir / "proof_artifacts" / "p10d" / "enabled"

        result = run_default_off_scorer_shadow_wrapper(
            config=DefaultOffScorerShadowConfig(enabled=True, output_root=proof_root),
            baseline_scores=baseline,
            executor_input_scores=baseline.copy(),
            shadow_scorer_scores=shadow,
            scorer_context={"source": "unit-test"},
            run_id="enabled",
            now=datetime(2026, 6, 8, 14, 5, tzinfo=UTC),
        )

        self.assertEqual(result.summary["status"], "ready")
        self.assertTrue(result.summary["hook_enabled"])
        self.assertTrue(result.summary["shadow_artifacts_under_proof_artifacts_only"])
        self.assertGreater(result.summary["shadow_artifacts_written_count"], 0)
        self.assertTrue(result.summary["executor_consumes_baseline_only"])
        self.assertFalse(result.summary["shadow_scorer_referenced_by_executor"])
        self.assertFalse(result.summary["candidate_scorer_loaded_into_executor"])
        self.assertFalse(result.summary["candidate_scorer_loaded_into_timer"])
        self.assertFalse(result.summary["executor_input_mutated"])
        self.assertEqual(frame_sha256(result.executor_scores), frame_sha256(baseline))
        self.assertNotEqual(result.summary["shadow_scorer_scores_sha256"], result.summary["wrapper_output_scores_sha256"])
        self.assertTrue(all("proof_artifacts" in Path(path).parts for path in result.summary["shadow_artifact_paths"]))
        self.assertTrue((proof_root / "shadow_scorer" / "shadow_scorer_scores.csv").exists())
        self.assertEqual(result.summary["orders_submitted"], 0)
        self.assertEqual(result.summary["fill_count"], 0)

    def test_enabled_blocks_when_output_root_is_not_proof_artifacts(self) -> None:
        result = run_default_off_scorer_shadow_wrapper(
            config=DefaultOffScorerShadowConfig(enabled=True, output_root=self.temp_dir / "not_proof"),
            baseline_scores=self._baseline_scores(),
            executor_input_scores=self._baseline_scores(),
            shadow_scorer_scores=self._shadow_scores(),
            run_id="blocked",
            now=datetime(2026, 6, 8, 14, 10, tzinfo=UTC),
        )

        self.assertEqual(result.summary["status"], "blocked")
        self.assertIn("enabled_wrapper_output_root_not_under_proof_artifacts", result.summary["blockers"])
        self.assertEqual(result.summary["shadow_artifacts_written_count"], 0)
        self.assertFalse(result.summary["shadow_artifacts_under_proof_artifacts_only"])
        self.assertTrue(result.summary["executor_consumes_baseline_only"])

    def test_enabled_blocks_when_executor_input_is_not_baseline(self) -> None:
        baseline = self._baseline_scores()
        executor_input = baseline.copy()
        executor_input.loc[0, "score"] = 0.77

        result = run_default_off_scorer_shadow_wrapper(
            config=DefaultOffScorerShadowConfig(
                enabled=True,
                output_root=self.temp_dir / "proof_artifacts" / "p10d" / "drift",
            ),
            baseline_scores=baseline,
            executor_input_scores=executor_input,
            shadow_scorer_scores=self._shadow_scores(),
            run_id="drift",
            now=datetime(2026, 6, 8, 14, 15, tzinfo=UTC),
        )

        self.assertEqual(result.summary["status"], "blocked")
        self.assertIn("executor_input_scores_hash_not_baseline_before_wrapper", result.summary["blockers"])
        self.assertFalse(result.summary["executor_consumes_baseline_only"])
        self.assertEqual(result.summary["shadow_artifacts_written_count"], 0)

    def test_p10d_runner_builds_retained_ready_wrapper_proof_from_p10c_snapshot(self) -> None:
        p10c_summary = self._write_p10c_artifacts()
        output_root = self.temp_dir / "proof_artifacts" / "p10d-runner"

        summary, exit_code = run_p10d_default_off_scorer_wrapper(
            Namespace(p10c_summary=p10c_summary, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 14, 20, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p10c_snapshot_ready"])
        self.assertTrue(summary["disabled_hook_baseline_byte_for_byte_unchanged"])
        self.assertEqual(summary["disabled_hook_shadow_artifacts_written_count"], 0)
        self.assertTrue(summary["enabled_hook_shadow_artifacts_under_proof_artifacts_only"])
        self.assertTrue(summary["enabled_hook_executor_consumes_baseline_only"])
        self.assertFalse(summary["candidate_scorer_loaded_into_executor"])
        self.assertFalse(summary["executor_invoked"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertFalse(summary["supervisor_invoked"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "disabled_wrapper_summary.json").exists())
        self.assertTrue((output_root / "enabled_wrapper_summary.json").exists())

    def _baseline_scores(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "symbol": "BTCUSDT",
                    "subject": "BTC",
                    "decision_time_utc": "2026-06-08T14:00:00Z",
                    "score": 0.11,
                    "score_source": "baseline_fixture",
                },
                {
                    "symbol": "ETHUSDT",
                    "subject": "ETH",
                    "decision_time_utc": "2026-06-08T14:00:00Z",
                    "score": -0.22,
                    "score_source": "baseline_fixture",
                },
            ]
        )

    def _shadow_scores(self) -> pd.DataFrame:
        output = self._baseline_scores()
        output["score"] = [0.31, -0.41]
        output["score_source"] = "shadow_research_contract_scorer"
        return output

    def _write_p10c_artifacts(self) -> Path:
        p10c_root = self.temp_dir / "p10c"
        p10c_root.mkdir(parents=True, exist_ok=True)
        matrix_path = p10c_root / "research_scorer_input_matrix.csv"
        contract_path = p10c_root / "research_scorer_contract.json"
        summary_path = p10c_root / "summary.json"
        rows = []
        for symbol, subject, offset in (("BTCUSDT", "BTC", 0.0), ("ETHUSDT", "ETH", 0.5)):
            row = {"symbol": symbol, "subject": subject}
            for index, factor in enumerate(REQUIRED_FACTORS):
                row[factor] = float(index) + offset
            rows.append(row)
        pd.DataFrame(rows).to_csv(matrix_path, index=False)
        contract = {
            "required_feature_count": len(REQUIRED_FACTORS),
            "required_feature_columns": REQUIRED_FACTORS,
            "active_factor_order_bound": True,
        }
        contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True), encoding="utf-8")
        summary = {
            "status": "ready",
            "p10a_decision_time_utc": "2026-06-08T13:59:00Z",
            "comparison_cell_count": len(REQUIRED_FACTORS) * 2,
            "mismatch_count": 0,
            "max_abs_diff": 0.0,
            "factor_order_matches_research_contract": True,
            "executor_invoked": False,
            "candidate_executed": False,
            "orders_submitted": 0,
            "fills_observed": 0,
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "research_contract": contract | {"contract_path": str(contract_path)},
            "artifacts": {
                "research_scorer_input_matrix": str(matrix_path),
                "research_scorer_contract": str(contract_path),
            },
        }
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        return summary_path


if __name__ == "__main__":
    unittest.main()
