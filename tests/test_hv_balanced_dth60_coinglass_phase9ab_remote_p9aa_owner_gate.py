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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ab_remote_p9aa_owner_gate import (  # noqa: E402
    APPROVE_P9AB_DECISION,
    P9AC_GATE,
    build_phase9ab,
)


class Phase9ABRemoteP9AAOwnerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p9ab-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.project_profile = self.temp_dir / "project_profile.json"
        _write_json(self.project_profile, {"current_stage": "stage_1_research_readiness_only"})
        self.hook = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        self.hook.write_text("# hook\n", encoding="utf-8")
        self.supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        self.supervisor.write_text("def run():\n    return 'baseline supervisor'\n", encoding="utf-8")
        self.config_dir = self.temp_dir / "live_config"
        self.config_dir.mkdir()
        (self.config_dir / "config.yaml").write_text("risk:\n  trading_enabled: false\n", encoding="utf-8")

    def test_p9ab_allows_future_remote_no_order_p9aa_only(self) -> None:
        p9aa = self._write_p9aa_summary(account_blocked=True)
        summary, exit_code = build_phase9ab(
            self._args(p9aa, self.temp_dir / "p9ab-ready"),
            now_fn=_time_at(0),
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9ab_remote_p9aa_owner_gate_ready"])
        self.assertEqual(summary["allowed_next_gate"], P9AC_GATE)
        self.assertTrue(summary["future_p9ac_remote_sync_authorized"])
        self.assertTrue(summary["future_p9ac_remote_execution_authorized"])
        self.assertTrue(summary["future_p9ac_fresh_remote_account_read_proof_required"])
        self.assertTrue(summary["future_p9ac_baseline_only_executor_required"])
        self.assertTrue(summary["future_p9ac_candidate_shadow_only_required"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["production_timer_service_load_authorized"])
        self.assertFalse(summary["remote_sync_performed"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

    def test_p9ab_blocks_if_p9aa_was_not_account_read_fail_closed(self) -> None:
        p9aa = self._write_p9aa_summary(account_blocked=False)
        summary, exit_code = build_phase9ab(
            self._args(p9aa, self.temp_dir / "p9ab-blocked"),
            now_fn=_time_at(1),
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("p9aa_blocked_fail_closed_due_local_account_read", summary["blockers"])
        self.assertFalse(summary["future_p9ac_remote_execution_authorized"])
        self.assertFalse(summary["remote_execution_performed"])

    def _args(self, p9aa: Path, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(self.project_profile),
            phase9aa_summary=str(p9aa),
            hook_module=str(self.hook),
            supervisor=str(self.supervisor),
            live_config_dir=str(self.config_dir),
            remote_host="root@203.0.113.10",
            remote_repo="/root/meridian_alpha_live_runner/repo",
            remote_config="/root/meridian_alpha_live_runner/repo/config/live_trading/remote.yaml",
            expected_egress_ip="203.0.113.10",
            owner="rulebook_owner",
            owner_decision=APPROVE_P9AB_DECISION,
            owner_decision_source="test",
        )

    def _write_p9aa_summary(self, *, account_blocked: bool) -> Path:
        path = self.temp_dir / ("p9aa_account_blocked.json" if account_blocked else "p9aa_other_blocked.json")
        blockers = [
            "all_candidate_artifacts_shadow_only",
            "all_cycles_ready",
            "all_executor_baseline_only",
            "no_executor_input_mutation",
        ]
        account_read_blockers: list[str] = []
        plan_missing: list[int] = []
        if account_blocked:
            blockers.extend(["timer_path_account_read_blocked", "timer_path_plan_artifact_missing"])
            account_read_blockers = [
                "read_only_endpoint_failed:account_config:BinanceUsdmRequestError",
                "account_reconcile_failed:blocked_live_position_monitor",
            ]
            plan_missing = [1, 2, 3]
        _write_json(
            path,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.v1",
                "status": "blocked",
                "timer_path_shadow_cycles_ready": False,
                "blockers": blockers,
                "completed_shadow_cycles": 3,
                "fresh_proof_each_cycle": True,
                "same_risk_no_order_config_each_cycle": True,
                "timer_path_supervisor_entrypoint_invoked": True,
                "systemd_timer_service_invoked": False,
                "production_timer_service_loaded_or_modified": False,
                "remote_execution_performed": False,
                "live_config_changed": False,
                "operator_state_changed_outside_generated_p9aa_state": False,
                "timer_state_changed": False,
                "orders_submitted": 0,
                "fill_count": 0,
                "account_read_blockers": account_read_blockers,
                "plan_artifact_missing_cycles": plan_missing,
            },
        )
        return path


def _time_at(offset: int):
    base = datetime(2026, 6, 7, 0, 30, 0, tzinfo=UTC)
    return lambda: base + timedelta(seconds=offset)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
