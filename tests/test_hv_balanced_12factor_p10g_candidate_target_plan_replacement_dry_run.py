from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
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

from scripts.live_trading.run_hv_balanced_12factor_p10g_candidate_target_plan_replacement_dry_run import (  # noqa: E402
    APPROVE_P10G_DECISION,
    P10H_GATE,
    run_p10g_candidate_target_plan_replacement_dry_run,
)


class HvBalanced12FactorP10gCandidateReplacementDryRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p10g-replacement-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_proves_replacement_hash_binding_fallback_and_kill_switch(self) -> None:
        paths = self._write_ready_p10f_bundle()

        summary, exit_code = run_p10g_candidate_target_plan_replacement_dry_run(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p10g"),
            now_fn=lambda: datetime(2026, 6, 8, 18, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["p10g_candidate_target_plan_replacement_dry_run_ready"])
        self.assertTrue(summary["candidate_target_plan_replacement_semantics_proven"])
        self.assertTrue(summary["hash_binding_proven"])
        self.assertTrue(summary["baseline_fallback_proven"])
        self.assertTrue(summary["kill_switch_proven"])
        self.assertNotEqual(summary["baseline_target_plan_sha256"], summary["candidate_target_plan_sha256"])
        self.assertEqual(
            summary["simulated_executor_input_after_replacement_sha256"],
            summary["candidate_target_plan_sha256"],
        )
        self.assertEqual(
            summary["actual_executor_input_after_dry_run_sha256"],
            summary["baseline_target_plan_sha256"],
        )
        self.assertFalse(summary["actual_executor_input_changed"])
        self.assertFalse(summary["actual_target_plan_replaced"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["allowed_next_gate"], P10H_GATE)

        outputs = summary["output_files"]
        binding = _load_json(Path(outputs["hash_binding"]))
        fallback = _load_json(Path(outputs["baseline_fallback_readback"]))
        kill_switch = _load_json(Path(outputs["kill_switch_readback"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))
        candidate = _load_json(Path(outputs["candidate_target_plan"]))
        self.assertEqual(binding["candidate_plan_binds_baseline_target_plan_sha256"], summary["baseline_target_plan_sha256"])
        self.assertTrue(binding["shadow_scores"]["exists"])
        self.assertTrue(fallback["all_fallback_scenarios_return_baseline"])
        self.assertTrue(
            all(row["selected_executor_input_sha256"] == summary["baseline_target_plan_sha256"] for row in fallback["scenarios"])
        )
        self.assertTrue(kill_switch["kill_switch_active_returns_baseline"])
        self.assertEqual(
            kill_switch["selected_executor_input_when_kill_switch_active_sha256"],
            summary["baseline_target_plan_sha256"],
        )
        self.assertFalse(control["executor_input_changed"])
        self.assertFalse(control["target_plan_replaced"])
        self.assertEqual(len(candidate["positions"]), summary["candidate_symbol_count"])

    def test_blocks_when_p10f_summary_is_not_ready(self) -> None:
        paths = self._write_ready_p10f_bundle(p10f_overrides={"status": "blocked"})

        summary, exit_code = run_p10g_candidate_target_plan_replacement_dry_run(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "blocked"),
            now_fn=lambda: datetime(2026, 6, 8, 18, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p10f_summary_ready", summary["blockers"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_wrong_owner_decision_blocks_without_authorizing_execution(self) -> None:
        paths = self._write_ready_p10f_bundle()

        summary, exit_code = run_p10g_candidate_target_plan_replacement_dry_run(
            self._args(
                paths,
                output_root=self.temp_dir / "proof_artifacts" / "wrong-owner",
                owner_decision="approve_live_order_now",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 18, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p10g_recorded", summary["blockers"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P10G_DECISION,
    ) -> Namespace:
        return Namespace(
            p10f_summary=paths["p10f_summary"],
            output_root=output_root,
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
            max_symbols=4,
        )

    def _write_ready_p10f_bundle(self, p10f_overrides: dict[str, object] | None = None) -> dict[str, Path]:
        root = self.temp_dir / "bundle"
        ctx_dir = root / "ctx"
        plan_dir = root / "plan"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        plan_dir.mkdir(parents=True, exist_ok=True)
        baseline_scores = ctx_dir / "baseline_scores.csv"
        shadow_scores = ctx_dir / "shadow_scores.csv"
        ctx = ctx_dir / "ctx.json"
        target_portfolio = plan_dir / "target_portfolio.json"
        retained_fixture = root / "retained_account_plan_fixture_summary.json"
        p10f_summary = root / "summary.json"

        pd.DataFrame(
            [
                {"symbol": "BTCUSDT", "subject": "BTC", "decision_time_utc": "2026-06-08T10:49:01Z", "score": 0.0},
                {"symbol": "ETHUSDT", "subject": "ETH", "decision_time_utc": "2026-06-08T10:49:01Z", "score": 0.0},
                {"symbol": "SOLUSDT", "subject": "SOL", "decision_time_utc": "2026-06-08T10:49:01Z", "score": 0.0},
                {"symbol": "XRPUSDT", "subject": "XRP", "decision_time_utc": "2026-06-08T10:49:01Z", "score": 0.0},
            ]
        ).to_csv(baseline_scores, index=False)
        pd.DataFrame(
            [
                {"symbol": "BTCUSDT", "subject": "BTC", "decision_time_utc": "2026-06-08T10:49:01Z", "shadow_score": 5.5},
                {"symbol": "ETHUSDT", "subject": "ETH", "decision_time_utc": "2026-06-08T10:49:01Z", "shadow_score": 2.0},
                {"symbol": "SOLUSDT", "subject": "SOL", "decision_time_utc": "2026-06-08T10:49:01Z", "shadow_score": -1.0},
                {"symbol": "XRPUSDT", "subject": "XRP", "decision_time_utc": "2026-06-08T10:49:01Z", "shadow_score": 4.0},
            ]
        ).to_csv(shadow_scores, index=False)
        _write_json(
            ctx,
            {
                "baseline_scores_copy": {"path": str(baseline_scores), "exists": True},
                "shadow_scores_copy": {"path": str(shadow_scores), "exists": True},
            },
        )
        _write_json(
            target_portfolio,
            {
                "allocated_capital_usdt": 1000.0,
                "target_gross_weight": 1.0,
                "target_net_weight": 0.0,
                "portfolio_drawdown_multiplier": 1.0,
                "decision_id": "unit_test_baseline",
            },
        )
        target_positions = [
            {"usdm_symbol": "BTCUSDT", "subject": "BTC", "target_weight": 0.25, "target_notional_usdt": 250.0, "score": 0.1, "side": "long"},
            {"usdm_symbol": "ETHUSDT", "subject": "ETH", "target_weight": -0.25, "target_notional_usdt": 250.0, "score": -0.1, "side": "short"},
            {"usdm_symbol": "SOLUSDT", "subject": "SOL", "target_weight": 0.25, "target_notional_usdt": 250.0, "score": 0.2, "side": "long"},
            {"usdm_symbol": "XRPUSDT", "subject": "XRP", "target_weight": -0.25, "target_notional_usdt": 250.0, "score": -0.2, "side": "short"},
        ]
        _write_json(
            retained_fixture,
            {
                "status": "ready",
                "read_only": True,
                "proof_artifacts_only": True,
                "orders_submitted": 0,
                "fill_count": 0,
                "output_files": {"target_portfolio": str(target_portfolio)},
                "core_loop_summary": {
                    "status": "mainnet_core_loop_completed",
                    "cycles": [{"strategy_plan_artifacts": {"target_positions": target_positions}}],
                },
            },
        )
        summary = {
            "status": "ready",
            "p10f_timer_path_no_order_shadow_cycles_ready": True,
            "baseline_only_executor": True,
            "candidate_shadow_only": True,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "completed_shadow_cycles": 3,
            "zero_order_cancel_fill_trade_delta": True,
            "orders_submitted": 0,
            "fill_count": 0,
            "target_plan_replaced": False,
            "executor_input_changed": False,
            "generated_at_utc": "2026-06-08T11:30:17Z",
            "p10e_context": {"path": str(ctx), "exists": True},
            "retained_account_plan_fixture": {"path": str(retained_fixture), "exists": True},
        }
        summary.update(p10f_overrides or {})
        _write_json(p10f_summary, summary)
        return {"p10f_summary": p10f_summary}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
