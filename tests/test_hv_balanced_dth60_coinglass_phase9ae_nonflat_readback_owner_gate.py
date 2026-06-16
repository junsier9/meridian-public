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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ae_nonflat_readback_owner_gate import (  # noqa: E402
    APPROVE_P9AE_DECISION,
    P9AF_GATE,
    build_phase9ae,
    p9ad_ready_for_p9ae,
)


class Phase9AENonflatReadbackOwnerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p9ae-"))
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

    def test_p9ae_discusses_future_p9af_without_authorizing_execution(self) -> None:
        p9ad = self._write_p9ad_summary(contract_good=True)
        summary, exit_code = build_phase9ae(
            self._args(p9ad, self.temp_dir / "p9ae-ready"),
            now_fn=_time_at(0),
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9ae_nonflat_readback_owner_gate_ready"])
        self.assertTrue(summary["review_scope_only_discusses_execution"])
        self.assertEqual(summary["allowed_next_gate"], P9AF_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(summary["nonflat_remote_no_order_readback_execution_authorized"])
        self.assertFalse(summary["p9af_execution_authorized"])
        self.assertFalse(summary["remote_sync_authorized"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["production_timer_service_load_authorized"])
        self.assertFalse(summary["remote_sync_performed"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertTrue(summary["future_p9af_requirements"]["must_follow_p9ad_contract"])

    def test_p9ae_blocks_if_p9ad_contract_does_not_require_position_stability(self) -> None:
        p9ad = self._write_p9ad_summary(contract_good=False)
        self.assertFalse(p9ad_ready_for_p9ae(_read_json(p9ad)))
        summary, exit_code = build_phase9ae(
            self._args(p9ad, self.temp_dir / "p9ae-blocked"),
            now_fn=_time_at(1),
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("p9ad_nonflat_contract_ready", summary["blockers"])
        self.assertFalse(summary["p9ae_nonflat_readback_owner_gate_ready"])
        self.assertFalse(summary["remote_execution_performed"])

    def _args(self, p9ad: Path, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(self.project_profile),
            phase9ad_summary=str(p9ad),
            hook_module=str(self.hook),
            supervisor=str(self.supervisor),
            live_config_dir=str(self.config_dir),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9AE_DECISION,
            owner_decision_source="test",
        )

    def _write_p9ad_summary(self, *, contract_good: bool) -> Path:
        contract = self.temp_dir / ("p9ad_contract_good.json" if contract_good else "p9ad_contract_bad.json")
        _write_json(contract, _p9ad_contract(contract_good=contract_good))
        path = self.temp_dir / ("p9ad_summary_good.json" if contract_good else "p9ad_summary_bad.json")
        _write_json(
            path,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9ad_nonflat_no_order_readback_contract.v1",
                "status": "ready",
                "blockers": [],
                "p9ad_nonflat_no_order_contract_ready": True,
                "eligible_for_p9ae_nonflat_remote_no_order_readback_gate": True,
                "allowed_next_gate": "P9AE_nonflat_remote_runner_no_order_p9aa_readback_only_if_separately_requested",
                "p9ae_remote_sync_authorized": False,
                "p9ae_remote_execution_authorized": False,
                "p9ae_execution_requires_separate_owner_gate": True,
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
                    "p9ac_blocked_on_nonflat_account": True,
                    "nonflat_contract_requires_position_fingerprint_stability": contract_good,
                },
                "output_files": {"nonflat_no_order_readback_contract": str(contract)},
            },
        )
        return path


def _p9ad_contract(*, contract_good: bool) -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ad_nonflat_no_order_contract_body.v1",
        "admission": {
            "fresh_remote_account_read_same_run": True,
            "open_order_count_required": 0,
            "open_position_count_may_be_nonzero": True,
        },
        "position_safety_contract": {
            "position_fingerprint_required_before_each_cycle": True,
            "position_fingerprint_required_after_each_cycle": True,
            "position_symbols_and_quantities_must_remain_unchanged": contract_good,
            "no_position_size_change": contract_good,
        },
        "cycle_contract": {
            "consecutive_shadow_cycles_required": 3,
            "baseline_only_executor_input": True,
            "candidate_shadow_artifact_only": True,
            "candidate_execution": False,
            "live_order_submission": False,
        },
        "post_cycle_contract": {
            "orders_submitted_delta_required": 0,
            "fills_delta_required": 0,
            "account_trade_delta_required": 0,
            "position_fingerprint_must_match_pre_cycle_baseline": True,
        },
        "non_authorizations": {
            "p9ae_execution": False,
            "remote_sync": False,
            "remote_execution": False,
            "candidate_execution": False,
            "live_order_submission": False,
        },
    }


def _time_at(offset: int):
    base = datetime(2026, 6, 7, 1, 30, 0, tzinfo=UTC)
    return lambda: base + timedelta(seconds=offset)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
