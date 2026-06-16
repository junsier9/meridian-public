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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ad_nonflat_no_order_contract import (  # noqa: E402
    APPROVE_P9AD_DECISION,
    P9AE_GATE,
    build_phase9ad,
    p9ac_blocked_on_nonflat_account,
)


class Phase9ADNonflatNoOrderContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p9ad-"))
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

    def test_p9ad_defines_nonflat_contract_without_authorizing_execution(self) -> None:
        p9ab = self._write_p9ab_summary()
        p9ac = self._write_p9ac_summary(open_positions=11)
        summary, exit_code = build_phase9ad(
            self._args(p9ab, p9ac, self.temp_dir / "p9ad-ready"),
            now_fn=_time_at(0),
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9ad_nonflat_no_order_contract_ready"])
        self.assertEqual(summary["allowed_next_gate"], P9AE_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(summary["p9ae_remote_sync_authorized"])
        self.assertFalse(summary["p9ae_remote_execution_authorized"])
        self.assertTrue(summary["p9ae_execution_requires_separate_owner_gate"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["production_timer_service_load_authorized"])
        self.assertFalse(summary["remote_sync_performed"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertTrue(summary["nonflat_contract"]["requires_position_fingerprint_stability"])

    def test_p9ad_rejects_p9ac_that_did_not_block_on_nonflat_account(self) -> None:
        p9ab = self._write_p9ab_summary()
        p9ac = self._write_p9ac_summary(open_positions=0)
        self.assertFalse(p9ac_blocked_on_nonflat_account(_read_json(p9ac)))
        summary, exit_code = build_phase9ad(
            self._args(p9ab, p9ac, self.temp_dir / "p9ad-blocked"),
            now_fn=_time_at(1),
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("p9ac_blocked_on_nonflat_account", summary["blockers"])
        self.assertFalse(summary["p9ad_nonflat_no_order_contract_ready"])
        self.assertFalse(summary["remote_execution_performed"])

    def _args(self, p9ab: Path, p9ac: Path, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(self.project_profile),
            phase9ab_summary=str(p9ab),
            phase9ac_summary=str(p9ac),
            hook_module=str(self.hook),
            supervisor=str(self.supervisor),
            live_config_dir=str(self.config_dir),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9AD_DECISION,
            owner_decision_source="test",
        )

    def _write_p9ab_summary(self) -> Path:
        path = self.temp_dir / "p9ab_summary.json"
        _write_json(
            path,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9ab_remote_p9aa_owner_gate.v1",
                "status": "ready",
                "blockers": [],
                "p9ab_remote_p9aa_owner_gate_ready": True,
                "eligible_for_p9ac_remote_runner_no_order_p9aa": True,
                "candidate_execution_authorized": False,
                "live_order_submission_authorized": False,
                "production_timer_service_load_authorized": False,
            },
        )
        return path

    def _write_p9ac_summary(self, *, open_positions: int) -> Path:
        preflight = self.temp_dir / f"preflight_{open_positions}.json"
        pre_snapshot = self.temp_dir / f"pre_snapshot_{open_positions}.json"
        post_snapshot = self.temp_dir / f"post_snapshot_{open_positions}.json"
        blockers = [f"mainnet_open_positions_exist:{open_positions}"] if open_positions else []
        _write_json(
            preflight,
            {
                "status": "blocked" if open_positions else "passed_read_only_account_probe",
                "blockers": blockers,
                "account_readable": True,
                "can_trade": True,
                "position_mode": "one_way",
                "open_order_count": 0,
                "open_position_count": open_positions,
                "side_effects": {
                    "only_http_get_endpoints": True,
                    "order_test_calls": 0,
                    "orders_canceled": 0,
                    "orders_submitted": 0,
                },
            },
        )
        snapshot = {
            "remote_live_config_sha256": "cfg",
            "live_supervisor_sha256": "sup",
            "operator_state": {"live_delta_armed": {"value": "true"}},
            "systemd_units": {
                "meridian-alpha-mainnet-supervisor-live.timer": {
                    "LoadState": "loaded",
                    "UnitFileState": "enabled",
                    "ActiveState": "active",
                    "SubState": "waiting",
                    "FragmentPath": "/etc/systemd/system/meridian-alpha-mainnet-supervisor-live.timer",
                }
            },
        }
        _write_json(pre_snapshot, snapshot)
        _write_json(post_snapshot, snapshot)
        path = self.temp_dir / f"p9ac_summary_{open_positions}.json"
        _write_json(
            path,
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback.v1",
                "status": "blocked",
                "blockers": ["fresh_remote_account_read_pre_failed"],
                "remote_sync_performed": False,
                "remote_execution_performed": False,
                "completed_shadow_cycles": 0,
                "orders_submitted": 0,
                "fill_count": 0,
                "live_config_changed": False,
                "operator_state_changed": False,
                "timer_state_changed": False,
                "production_timer_service_loaded_or_modified": False,
                "fresh_remote_account_read_pre": {"path": str(preflight)},
                "pre_control_snapshot": {"path": str(pre_snapshot)},
                "post_control_snapshot": {"path": str(post_snapshot)},
            },
        )
        return path


def _time_at(offset: int):
    base = datetime(2026, 6, 7, 1, 10, 0, tzinfo=UTC)
    return lambda: base + timedelta(seconds=offset)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
