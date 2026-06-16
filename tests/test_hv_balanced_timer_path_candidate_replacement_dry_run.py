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
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.live_trading.run_hv_balanced_timer_path_candidate_replacement_dry_run import (  # noqa: E402
    APPROVE_TIMER_PATH_CANDIDATE_REPLACEMENT_DRY_RUN,
    NEXT_GATE,
    run_timer_path_candidate_replacement_dry_run,
)


class HvBalancedTimerPathCandidateReplacementDryRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="timer-path-replacement-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_proves_timer_path_replacement_hash_fallback_kill_switch_and_auto_leverage(self) -> None:
        paths = self._write_inputs()

        summary, exit_code = run_timer_path_candidate_replacement_dry_run(
            self._args(paths, output_root=self.temp_dir / "proof"),
            now_fn=lambda: datetime(2026, 6, 9, 1, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["blockers"], [])
        self.assertTrue(summary["timer_path_candidate_replacement_dry_run_ready"])
        self.assertTrue(summary["entered_timer_path_dry_run_harness"])
        self.assertFalse(summary["entered_live_timer_path"])
        self.assertFalse(summary["production_timer_service_loaded_or_invoked"])
        self.assertFalse(summary["supervisor_invoked"])
        self.assertTrue(summary["candidate_target_plan_replacement_semantics_proven"])
        self.assertTrue(summary["hash_binding_proven"])
        self.assertTrue(summary["baseline_fallback_proven"])
        self.assertTrue(summary["kill_switch_proven"])
        self.assertTrue(summary["auto_leverage_setting_proven"])
        self.assertTrue(summary["auto_truncate_allocated_capital_to_margin_gate_enabled"])
        self.assertTrue(summary["allow_reduce_only_plan_when_margin_below_min_enabled"])
        self.assertNotEqual(summary["baseline_target_plan_sha256"], summary["candidate_target_plan_sha256"])
        self.assertEqual(
            summary["simulated_timer_executor_input_after_replacement_sha256"],
            summary["candidate_target_plan_sha256"],
        )
        self.assertEqual(
            summary["actual_executor_input_after_dry_run_sha256"],
            summary["baseline_target_plan_sha256"],
        )
        self.assertFalse(summary["actual_executor_input_changed"])
        self.assertFalse(summary["actual_target_plan_replaced"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["account_setting_preparation_status"], "prepared")
        self.assertEqual(summary["account_setting_call_count"], 1)
        self.assertEqual(summary["target_max_leverage"], 2)
        self.assertEqual(summary["allowed_next_gate"], NEXT_GATE)

        outputs = summary["output_files"]
        auto_leverage = _load_json(Path(outputs["auto_leverage_setting_dry_run"]))
        fallback = _load_json(Path(outputs["baseline_fallback_readback"]))
        kill_switch = _load_json(Path(outputs["kill_switch_readback"]))
        control = _load_json(Path(outputs["control_boundary_readback"]))
        self.assertEqual(auto_leverage["fake_client_leverage_changes"], [{"symbol": "BTCUSDT", "leverage": 2}])
        self.assertEqual(auto_leverage["actions"][0]["action"], "change_initial_leverage")
        self.assertTrue(fallback["all_fallback_scenarios_return_baseline"])
        self.assertTrue(kill_switch["kill_switch_active_returns_baseline"])
        self.assertEqual(kill_switch["kill_switch_source"], "sqlite_operator_state")
        self.assertFalse(control["entered_live_timer_path"])
        self.assertFalse(control["executor_input_changed"])

    def test_wrong_owner_decision_blocks_without_authorizing_runtime_or_orders(self) -> None:
        paths = self._write_inputs()

        summary, exit_code = run_timer_path_candidate_replacement_dry_run(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_orders_now",
            ),
            now_fn=lambda: datetime(2026, 6, 9, 1, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_recorded", summary["blockers"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_auto_leverage_disabled_blocks_the_requested_proof(self) -> None:
        paths = self._write_inputs(auto_prepare=False)

        summary, exit_code = run_timer_path_candidate_replacement_dry_run(
            self._args(paths, output_root=self.temp_dir / "auto-disabled"),
            now_fn=lambda: datetime(2026, 6, 9, 1, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("timer_profile_readback_ready", summary["blockers"])
        self.assertIn("auto_leverage_setting_proven", summary["blockers"])
        self.assertFalse(summary["auto_leverage_setting_proven"])
        auto_leverage = _load_json(Path(summary["output_files"]["auto_leverage_setting_dry_run"]))
        self.assertFalse(auto_leverage["auto_prepare_planned_symbol_settings_enabled"])
        self.assertEqual(auto_leverage["setting_call_count"], 0)

    def test_stage4_boundary_summary_is_required_but_does_not_authorize_runtime(self) -> None:
        paths = self._write_inputs(stage4_ready=False)

        summary, exit_code = run_timer_path_candidate_replacement_dry_run(
            self._args(paths, output_root=self.temp_dir / "stage4-blocked"),
            now_fn=lambda: datetime(2026, 6, 9, 1, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("stage4_boundary_owner_gate_ready", summary["blockers"])
        self.assertFalse(summary["production_timer_service_load_authorized"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_TIMER_PATH_CANDIDATE_REPLACEMENT_DRY_RUN,
    ) -> Namespace:
        return Namespace(
            output_root=output_root,
            project_profile=paths["project_profile"],
            live_timer_config=paths["live_timer_config"],
            stage4_boundary_summary=paths["stage4_summary"],
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_inputs(self, *, auto_prepare: bool = True, stage4_ready: bool = True) -> dict[str, Path]:
        root = self.temp_dir / "inputs"
        root.mkdir(parents=True, exist_ok=True)
        profile = root / "project_profile.json"
        timer_config = root / "timer.yaml"
        stage4 = root / "stage4_summary.json"
        _write_json(
            profile,
            {
                "contract_version": "project_profile.v1",
                "current_stage": "stage_3_human_approved_execution",
                "target_stage": "stage_4_automated_execution",
            },
        )
        timer_config.write_text(
            "\n".join(
                [
                    "strategy:",
                    "  label: v5_binance_pit_top_mid_h10d_pruned3_hv_balanced_soft_budget",
                    "binance:",
                    "  margin_type: cross",
                    "  max_leverage: 2",
                    f"  auto_prepare_planned_symbol_settings: {str(auto_prepare).lower()}",
                    "capital:",
                    "  allocated_capital_usdt: 1000.0",
                    "  max_symbol_notional_usdt: 600.0",
                    "  max_order_notional_usdt: 600.0",
                    "  auto_truncate_allocated_capital_to_margin_gate: true",
                    "  margin_safe_truncation_tolerance_usdt: 1.0",
                    "risk:",
                    "  trading_enabled: false",
                    "  require_manual_live_confirm: true",
                    "  max_symbol_notional_usdt: 600.0",
                    "  max_order_notional_usdt: 600.0",
                    "  allow_reduce_only_plan_when_margin_below_min: true",
                    "core_loop:",
                    "  mode: account_reconcile_multiphase_dynamic_capital_delta_risk_execution_reconcile",
                    "  max_cycles_per_invocation: 1",
                    "  live_delta_enabled: true",
                    "  submit_orders: true",
                    "  kill_switch_source: sqlite_operator_state",
                    "mainnet_live_supervisor:",
                    "  mode: sqlite_armed_multiphase_dynamic_capital_core_loop_timer",
                    "  max_cycles_per_invocation: 1",
                    "  allow_live_delta_when_armed: true",
                    "mainnet_health_monitor:",
                    "  require_systemd_timer_active: true",
                    "  systemd_timer_name: enhengclaw-mainnet-supervisor-live.timer",
                    "state:",
                    f"  sqlite_path: {(root / 'state.sqlite3').as_posix()}",
                    f"  artifact_root: {(root / 'runs').as_posix()}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        _write_json(
            stage4,
            {
                "contract_version": "project_governance_stage4_automated_execution_boundary_owner_gate.v1",
                "status": "ready" if stage4_ready else "blocked",
                "stage4_automated_execution_boundary_owner_gate_ready": stage4_ready,
                "stage4_automated_execution_authorized_now": False,
                "automated_execution_unlocked_now": False,
            },
        )
        return {
            "project_profile": profile,
            "live_timer_config": timer_config,
            "stage4_summary": stage4,
        }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
