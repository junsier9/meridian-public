from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime, timedelta
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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import tree_sha256  # noqa: E402
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9y_owner_review_after_p9x import (  # noqa: E402
    APPROVE_P9Y_DECISION,
    build_phase9y,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9z_timer_path_readback_owner_gate import (  # noqa: E402
    APPROVE_P9Z_DECISION,
    build_phase9z,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles import (  # noqa: E402
    APPROVE_P9AA_DECISION,
    build_phase9aa,
)


class Phase9Y9Z9AATimerPathShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p9y-9z-9aa-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.hook = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        self.hook.write_text("# hook\n", encoding="utf-8")
        self.supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        self.supervisor.write_text("def run():\n    return 'baseline supervisor'\n", encoding="utf-8")
        self.config_dir = self.temp_dir / "live_config"
        self.config_dir.mkdir()
        (self.config_dir / "config.yaml").write_text("core_loop:\n  live_delta_enabled: false\n", encoding="utf-8")
        self.project_profile = self.temp_dir / "project_profile.json"
        _write_json(self.project_profile, {"current_stage": "stage_1_research_readiness_only"})
        self.base_config = self.temp_dir / "base_noorder.json"
        _write_json(
            self.base_config,
            {
                "strategy": {"label": "fixture"},
                "binance": {"venue": "usdm_futures"},
                "risk": {"trading_enabled": False},
                "core_loop": {
                    "target_engine": "multiphase_equal_sleeve",
                    "live_delta_enabled": False,
                    "submit_orders": False,
                    "auto_confirm_delta_after_preflight": False,
                    "max_cycles_per_invocation": 1,
                },
                "mainnet_live_supervisor": {
                    "target_engine": "multiphase_equal_sleeve",
                    "allow_live_delta_when_armed": False,
                    "max_cycles_per_invocation": 1,
                },
                "state": {
                    "sqlite_path": str(self.temp_dir / "state.sqlite3"),
                    "artifact_root": str(self.temp_dir / "runs"),
                },
            },
        )

    def test_p9y_p9z_p9aa_ready_with_three_fresh_no_order_cycles(self) -> None:
        p9x = self._write_p9x_summary()
        p9y_summary, p9y_exit = build_phase9y(
            Namespace(
                output_root=str(self.temp_dir / "p9y"),
                project_profile=str(self.project_profile),
                phase9x_summary=str(p9x),
                hook_module=str(self.hook),
                supervisor=str(self.supervisor),
                live_config_dir=str(self.config_dir),
                owner="rulebook_owner",
                owner_decision=APPROVE_P9Y_DECISION,
                owner_decision_source="test",
            ),
            now_fn=_time_at(0),
        )
        self.assertEqual(p9y_exit, 0)
        self.assertTrue(p9y_summary["p9x_sufficient_for_next_owner_gate"])

        p9z_summary, p9z_exit = build_phase9z(
            Namespace(
                output_root=str(self.temp_dir / "p9z"),
                project_profile=str(self.project_profile),
                phase9y_summary=p9y_summary["output_files"]["summary"],
                hook_module=str(self.hook),
                supervisor=str(self.supervisor),
                live_config_dir=str(self.config_dir),
                owner="rulebook_owner",
                owner_decision=APPROVE_P9Z_DECISION,
                owner_decision_source="test",
            ),
            now_fn=_time_at(1),
        )
        self.assertEqual(p9z_exit, 0)
        self.assertTrue(p9z_summary["observe_only_shadow_readback_authorized"])

        calls: list[Namespace] = []
        p9aa_summary, p9aa_exit = build_phase9aa(
            Namespace(
                output_root=str(self.temp_dir / "p9aa"),
                phase9z_summary=p9z_summary["output_files"]["summary"],
                base_config=str(self.base_config),
                shadow_cycles=3,
                interval_seconds=0.0,
                as_of="now",
                symbols="",
                fixture_panel="",
                public_market_data=False,
                target_engine="",
                position_tolerance=1e-9,
                position_reference_source="",
                owner="rulebook_owner",
                owner_decision=APPROVE_P9AA_DECISION,
                owner_decision_source="test",
            ),
            now_fn=_time_at(2),
            supervisor_runner=_fake_supervisor_runner(calls),
            env={},
        )
        self.assertEqual(p9aa_exit, 0)
        self.assertEqual(p9aa_summary["completed_shadow_cycles"], 3)
        self.assertTrue(p9aa_summary["fresh_proof_each_cycle"])
        self.assertEqual(p9aa_summary["orders_submitted"], 0)
        self.assertEqual(p9aa_summary["fill_count"], 0)
        self.assertTrue(p9aa_summary["gates"]["all_executor_baseline_only"])
        self.assertTrue(p9aa_summary["gates"]["all_candidate_artifacts_shadow_only"])
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(call.cycles == 1 for call in calls))

    def test_p9aa_blocks_without_ready_p9z_and_does_not_run_supervisor(self) -> None:
        bad_p9z = self.temp_dir / "bad_p9z.json"
        _write_json(bad_p9z, {"contract_version": "bad", "status": "blocked", "blockers": ["x"]})
        calls: list[Namespace] = []
        summary, exit_code = build_phase9aa(
            Namespace(
                output_root=str(self.temp_dir / "blocked_p9aa"),
                phase9z_summary=str(bad_p9z),
                base_config=str(self.base_config),
                shadow_cycles=3,
                interval_seconds=0.0,
                as_of="now",
                symbols="",
                fixture_panel="",
                public_market_data=False,
                target_engine="",
                position_tolerance=1e-9,
                position_reference_source="",
                owner="rulebook_owner",
                owner_decision=APPROVE_P9AA_DECISION,
                owner_decision_source="test",
            ),
            now_fn=_time_at(3),
            supervisor_runner=_fake_supervisor_runner(calls),
            env={},
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("p9z_owner_gate_ready", summary["blockers"])
        self.assertEqual(calls, [])

    def _write_p9x_summary(self) -> Path:
        hook_sha = _sha(self.hook)
        supervisor_sha = _sha(self.supervisor)
        config_sha = tree_sha256(self.config_dir)
        gates = {
            "project_stage_boundary_preserved": True,
            "p9w_owner_gate_ready": True,
            "p9w_allows_future_p9x_gate_request": True,
            "dry_load_outputs_under_proof_artifacts": True,
            "dry_load_mode_not_live_timer_service": True,
            "default_off_config_loaded": True,
            "disabled_hook_readback_ready": True,
            "disabled_hook_writes_zero_candidate_artifacts": True,
            "baseline_target_plan_byte_for_byte_unchanged": True,
            "executor_input_hash_unchanged": True,
            "executor_input_hash_equals_baseline": True,
            "executor_consumes_baseline_only": True,
            "candidate_shadow_hash_differs_from_executor": True,
            "candidate_plan_not_referenced_by_executor": True,
            "target_plan_not_replaced": True,
            "live_supervisor_source_unchanged": True,
            "live_config_dir_unchanged": True,
            "live_timer_service_not_enabled_or_invoked": True,
            "supervisor_not_run_for_execution": True,
            "no_remote_sync_in_p9x": True,
            "no_live_timer_path_load_in_p9x": True,
            "no_executor_input_mutation_in_p9x": True,
            "no_target_plan_replacement_in_p9x": True,
            "no_live_mutation_in_p9x": True,
            "zero_orders_fills_in_p9x": True,
        }
        p9x = self.temp_dir / "p9x_summary.json"
        _write_json(
            p9x,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9x_default_off_timer_path_dry_load.v1",
                "status": "ready",
                "blockers": [],
                "owner_decision": {
                    "decision": "approve_p9x_execute_default_off_timer_path_dry_load_only",
                    "default_off_timer_path_dry_load_execution_approved": True,
                    "candidate_execution_approved": False,
                    "live_order_submission_approved": False,
                },
                "default_off_timer_path_dry_load_ready": True,
                "default_off_timer_path_dry_load_execution_authorized": True,
                "default_off_timer_path_dry_load_executed": True,
                "dry_load_mode": "default_off_timer_path_dry_load_harness_not_live_timer_service",
                "entered_timer_path_dry_load_harness": True,
                "entered_live_timer_path": False,
                "default_off_hook_enabled": False,
                "candidate_execution_enabled": False,
                "disabled_hook_candidate_artifacts_written_count": 0,
                "executor_consumes_baseline_only": True,
                "executor_input_hash_equals_baseline": True,
                "candidate_plan_referenced_by_executor": False,
                "target_plan_replaced": False,
                "executor_input_changed": False,
                "eligible_for_live_order_submission": False,
                "eligible_for_live_timer_path_load": False,
                "timer_path_load_authorized": False,
                "live_order_submission_authorized": False,
                "live_timer_path_loaded": False,
                "live_timer_service_enabled_or_invoked": False,
                "ran_supervisor": False,
                "remote_execution_performed": False,
                "live_config_changed": False,
                "operator_state_changed": False,
                "timer_state_changed": False,
                "orders_submitted": 0,
                "fill_count": 0,
                "source_evidence": {
                    "hook_module": {"path": str(self.hook), "exists": True, "sha256": hook_sha},
                    "live_supervisor": {"path": str(self.supervisor), "exists": True, "sha256": supervisor_sha},
                    "live_config_dir": {"path": str(self.config_dir), "exists": True, "sha256": config_sha},
                },
                "gates": gates,
            },
        )
        return p9x


def _fake_supervisor_runner(calls: list[Namespace]):
    counter = {"value": 0}

    def run(args: Namespace, **_: object) -> tuple[dict[str, object], int]:
        counter["value"] += 1
        calls.append(args)
        config = _read_json(Path(args.config))
        artifact_root = Path(config["state"]["artifact_root"])
        run_id = f"fake-supervisor-{counter['value']:03d}"
        plan_root = artifact_root / "mainnet_core_loop" / run_id / "plan"
        plan_root.mkdir(parents=True, exist_ok=True)
        _write_json(
            plan_root / "target_portfolio.json",
            {
                "contract_version": "fixture_target_portfolio.v1",
                "run_id": run_id,
                "positions": [{"symbol": "BTCUSDT", "target_weight": 0.1}],
            },
        )
        return (
            {
                "run_id": run_id,
                "status": "mainnet_live_supervisor_completed",
                "blockers": [],
                "artifact_root": str(artifact_root / "mainnet_live_supervisor" / run_id),
                "orders_submitted": 0,
                "fill_count": 0,
                "live_delta_authorized": False,
                "cycles": [
                    {
                        "cycle_index": 1,
                        "execute_live_delta_requested": False,
                        "orders_submitted": 0,
                        "fill_count": 0,
                        "live_delta_authorized": False,
                        "core_loop_summary": {
                            "status": "mainnet_core_loop_completed",
                            "blockers": [],
                            "orders_submitted": 0,
                            "fill_count": 0,
                            "live_delta_authorized": False,
                            "cycles": [
                                {
                                    "status": "cycle_plan_only_ready",
                                    "plan_artifact_root": str(plan_root),
                                    "orders_submitted": 0,
                                    "fill_count": 0,
                                }
                            ],
                        },
                    }
                ],
            },
            0,
        )

    return run


def _time_at(offset: int):
    base = datetime(2026, 6, 7, 0, 0, 0, tzinfo=UTC)
    return lambda: base + timedelta(seconds=offset)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
