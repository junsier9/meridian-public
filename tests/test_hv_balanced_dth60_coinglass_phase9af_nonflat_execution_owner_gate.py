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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9af_nonflat_execution_owner_gate import (  # noqa: E402
    APPROVE_P9AF_DECISION,
    P9AG_GATE,
    build_phase9af,
    p9ae_ready_for_p9af,
)


class Phase9AFNonflatExecutionOwnerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p9af-"))
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

    def test_p9af_discusses_future_p9ag_without_authorizing_execution(self) -> None:
        p9ae = self._write_p9ae_summary(matrix_good=True)
        summary, exit_code = build_phase9af(
            self._args(p9ae, self.temp_dir / "p9af-ready"),
            now_fn=_time_at(0),
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9af_nonflat_execution_owner_gate_ready"])
        self.assertTrue(summary["review_scope_discusses_actual_execution"])
        self.assertEqual(summary["allowed_next_gate"], P9AG_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(summary["nonflat_remote_no_order_readback_execution_authorized"])
        self.assertFalse(summary["p9ag_execution_authorized"])
        self.assertFalse(summary["remote_sync_authorized"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["production_timer_service_load_authorized"])
        self.assertFalse(summary["remote_sync_performed"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertTrue(summary["future_p9ag_requirements"]["must_follow_p9ad_and_p9ae_contracts"])

    def test_p9af_blocks_if_p9ae_matrix_authorized_execution(self) -> None:
        p9ae = self._write_p9ae_summary(matrix_good=False)
        self.assertFalse(p9ae_ready_for_p9af(_read_json(p9ae)))
        summary, exit_code = build_phase9af(
            self._args(p9ae, self.temp_dir / "p9af-blocked"),
            now_fn=_time_at(1),
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("p9ae_owner_gate_ready", summary["blockers"])
        self.assertFalse(summary["p9af_nonflat_execution_owner_gate_ready"])
        self.assertFalse(summary["remote_execution_performed"])

    def _args(self, p9ae: Path, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(self.project_profile),
            phase9ae_summary=str(p9ae),
            hook_module=str(self.hook),
            supervisor=str(self.supervisor),
            live_config_dir=str(self.config_dir),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9AF_DECISION,
            owner_decision_source="test",
        )

    def _write_p9ae_summary(self, *, matrix_good: bool) -> Path:
        matrix = self.temp_dir / ("p9ae_matrix_good.json" if matrix_good else "p9ae_matrix_bad.json")
        _write_json(matrix, _p9ae_matrix(matrix_good=matrix_good))
        path = self.temp_dir / ("p9ae_summary_good.json" if matrix_good else "p9ae_summary_bad.json")
        _write_json(
            path,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9ae_nonflat_readback_owner_gate.v1",
                "status": "ready",
                "blockers": [],
                "p9ae_nonflat_readback_owner_gate_ready": True,
                "review_scope_only_discusses_execution": True,
                "eligible_for_future_p9af_nonflat_readback_execution_gate": True,
                "allowed_next_gate": "P9AF_execute_nonflat_remote_runner_no_order_p9aa_readback_only_if_separately_requested",
                "nonflat_remote_no_order_readback_execution_authorized": False,
                "p9af_execution_authorized": False,
                "remote_sync_authorized": False,
                "remote_execution_authorized": False,
                "candidate_execution_authorized": False,
                "live_order_submission_authorized": False,
                "target_plan_replacement_authorized": False,
                "executor_input_mutation_authorized": False,
                "production_timer_service_load_authorized": False,
                "remote_sync_performed": False,
                "remote_execution_performed": False,
                "orders_submitted": 0,
                "fill_count": 0,
                "gates": {
                    "p9ad_nonflat_contract_ready": True,
                    "p9af_execution_not_authorized_in_p9ae": matrix_good,
                    "remote_sync_not_authorized_in_p9ae": True,
                    "remote_execution_not_authorized_in_p9ae": True,
                },
                "output_files": {"execution_discussion_matrix": str(matrix)},
            },
        )
        return path


def _p9ae_matrix(*, matrix_good: bool) -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ae_execution_discussion_matrix.v1",
        "allowed_next_gate": "P9AF_execute_nonflat_remote_runner_no_order_p9aa_readback_only_if_separately_requested",
        "p9af_must_follow_p9ad_contract": True,
        "p9af_must_reprove_fresh_remote_account_read": True,
        "p9af_must_reprove_position_fingerprint_stability": True,
        "p9af_must_reprove_baseline_only_executor_input": True,
        "p9af_must_reprove_candidate_shadow_only": True,
        "p9af_must_reprove_zero_order_fill_trade_deltas": True,
        "p9af_must_reprove_remote_control_boundary_unchanged": True,
        "current_gate_authorizations": {
            "p9af_execution": not matrix_good,
            "remote_sync": False,
            "remote_execution": False,
            "candidate_execution": False,
            "live_order_submission": False,
        },
    }


def _time_at(offset: int):
    base = datetime(2026, 6, 7, 2, 45, 0, tzinfo=UTC)
    return lambda: base + timedelta(seconds=offset)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
