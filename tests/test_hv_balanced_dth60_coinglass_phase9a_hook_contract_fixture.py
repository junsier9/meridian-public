from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9a_hook_contract_fixture import (  # noqa: E402
    build_phase9a_fixture,
)


class HvBalancedDth60CoinglassPhase9aHookContractFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9a-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9a_proves_disabled_parity_and_enabled_shadow_only(self) -> None:
        paths = self._write_phase4_inputs()

        summary, exit_code = build_phase9a_fixture(
            Namespace(output_root=str(self.temp_dir / "p9a"), phase4_summary=str(paths["summary"])),
            now_fn=lambda: datetime(2026, 6, 7, 8, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["disabled_hook_baseline_output_unchanged"])
        self.assertEqual(summary["disabled_hook_candidate_artifacts_written_count"], 0)
        self.assertTrue(summary["enabled_hook_execution_target_unchanged"])
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertTrue(summary["candidate_artifacts_under_proof_artifacts_only"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        self.assertEqual(summary["candidate_orders_submitted"], 0)
        self.assertEqual(summary["candidate_fill_count"], 0)
        self.assertNotEqual(summary["candidate_shadow_plan_sha256"], summary["executor_input_plan_sha256"])
        self.assertTrue((self.temp_dir / "p9a" / "disabled_hook" / "executor_input" / "target_plan.json").exists())
        self.assertTrue((self.temp_dir / "p9a" / "enabled_hook" / "executor_input" / "target_plan.json").exists())
        candidate_path = Path(summary["output_files"]["candidate_shadow_plan"])
        self.assertIn("proof_artifacts", candidate_path.parts)
        for rel_path in summary["candidate_artifact_paths"]:
            self.assertTrue(rel_path.startswith("proof_artifacts/"))

    def test_phase9a_blocks_when_phase4_had_order_authority(self) -> None:
        paths = self._write_phase4_inputs(orders_submitted=1)

        summary, exit_code = build_phase9a_fixture(
            Namespace(output_root=str(self.temp_dir / "p9a-blocked"), phase4_summary=str(paths["summary"])),
            now_fn=lambda: datetime(2026, 6, 7, 8, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("phase4_zero_orders_fills", summary["blockers"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def test_phase9a_blocks_when_candidate_plan_matches_executor_plan(self) -> None:
        paths = self._write_phase4_inputs(candidate_equals_baseline=True)

        summary, exit_code = build_phase9a_fixture(
            Namespace(output_root=str(self.temp_dir / "p9a-same-plan"), phase4_summary=str(paths["summary"])),
            now_fn=lambda: datetime(2026, 6, 7, 8, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("candidate_shadow_plan_hash_differs_from_executor", summary["blockers"])
        self.assertTrue(summary["enabled_hook_execution_target_unchanged"])

    def _write_phase4_inputs(
        self,
        *,
        orders_submitted: int = 0,
        candidate_equals_baseline: bool = False,
    ) -> dict[str, Path]:
        root = self.temp_dir / "phase4"
        root.mkdir(parents=True)
        baseline = root / "baseline_target_portfolio.json"
        candidate = root / "candidate_target_portfolio.json"
        target_diff = root / "target_plan_diff.csv"
        shared_context = root / "shared_input_context.json"
        summary = root / "summary.json"
        baseline.write_text(
            json.dumps(
                {
                    "portfolio_id": "baseline",
                    "positions": [{"usdm_symbol": "BTCUSDT", "target_weight": 0.1}],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        candidate_payload = (
            {
                "portfolio_id": "baseline",
                "positions": [{"usdm_symbol": "BTCUSDT", "target_weight": 0.1}],
            }
            if candidate_equals_baseline
            else {
                "portfolio_id": "candidate",
                "positions": [{"usdm_symbol": "ETHUSDT", "target_weight": 0.1}],
            }
        )
        candidate.write_text(json.dumps(candidate_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        target_diff.write_text(
            "symbol,baseline_target_weight,candidate_target_weight,changed\nBTCUSDT,0.1,0.0,True\n",
            encoding="utf-8",
        )
        shared_context.write_text(json.dumps({"shared": True}, sort_keys=True) + "\n", encoding="utf-8")
        phase4_payload = {
            "status": "ready",
            "run_id": "phase4-fixture",
            "generated_at_utc": "2026-06-07T07:59:00Z",
            "blockers": [],
            "same_timestamp_context_proven": True,
            "same_risk_inputs_proven": True,
            "same_symbol_set_proven": True,
            "same_portfolio_engine_proven": True,
            "deterministic_target_difference_proven": True,
            "orders_submitted": orders_submitted,
            "fill_count": 0,
            "mainnet_order_submission_authorized": False,
            "exchange_order_submission": "disabled",
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "target_engine": "multiphase_equal_sleeve",
            "portfolio_engine": "enhengclaw.live_trading.portfolio_targets.build_target_portfolio",
            "upper_timestamp_utc": "2026-06-15T00:00:00Z",
            "phase_decision_times_utc": ["2026-06-07T00:00:00Z"],
            "shared_risk_inputs_sha256": "risk-sha",
            "shared_panel_sha256": "panel-sha",
            "shared_phase_context_sha256": "phase-sha",
            "phase2_pit_proof_checks": {
                "no_future_fill_proven": True,
                "no_stale_fill_proven": True,
                "no_zero_fill_proven": True,
            },
            "phase2b_pit_proof_checks": {
                "no_future_fill_proven": True,
                "no_stale_fill_proven": True,
                "no_zero_fill_proven": True,
            },
            "phase3_parity_proof_checks": {
                "overlay_enabled_only_target_contribution_changed": True,
            },
            "output_files": {
                "baseline_target_portfolio": str(baseline),
                "candidate_target_portfolio": str(candidate),
                "target_plan_diff": str(target_diff),
                "shared_input_context": str(shared_context),
            },
        }
        summary.write_text(json.dumps(phase4_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"summary": summary, "baseline": baseline, "candidate": candidate}


if __name__ == "__main__":
    unittest.main()
