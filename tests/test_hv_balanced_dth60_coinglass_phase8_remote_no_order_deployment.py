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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase6_owner_review_pack import TARGET_CONTRIBUTION  # noqa: E402
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase8_remote_no_order_deployment import (  # noqa: E402
    build_phase8_summary,
)


class HvBalancedDth60CoinglassPhase8RemoteNoOrderDeploymentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase8-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_build_phase8_summary_ready_when_remote_no_order_and_control_unchanged(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase8_summary(
            self._args(paths, output_root=self.temp_dir / "p8"),
            now_fn=lambda: datetime(2026, 6, 6, 17, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["eligible_for_remote_no_order_shadow_observation"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        self.assertFalse(summary["applied_to_live"])
        self.assertFalse(summary["live_config_changed"])
        self.assertFalse(summary["operator_state_changed"])
        self.assertFalse(summary["timer_state_changed"])
        self.assertTrue(summary["control_plane"]["unchanged"])

    def test_build_phase8_summary_blocks_when_control_plane_changes(self) -> None:
        paths = self._write_ready_inputs(post_config_hash="changed")

        summary, exit_code = build_phase8_summary(
            self._args(paths, output_root=self.temp_dir / "p8-blocked"),
            now_fn=lambda: datetime(2026, 6, 6, 17, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("remote_control_plane_unchanged", summary["blockers"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def _args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            p7_summary=str(paths["p7"]),
            phase2_summary=str(paths["phase2"]),
            phase2b_summary=str(paths["phase2b"]),
            remote_phase3_summary=str(paths["phase3"]),
            remote_phase4_summary=str(paths["phase4"]),
            pre_control_snapshot=str(paths["pre"]),
            post_control_snapshot=str(paths["post"]),
        )

    def _write_ready_inputs(self, *, post_config_hash: str = "same-hash") -> dict[str, Path]:
        paths = {
            "p7": self.temp_dir / "p7.json",
            "phase2": self.temp_dir / "phase2.json",
            "phase2b": self.temp_dir / "phase2b.json",
            "phase3": self.temp_dir / "remote_phase3.json",
            "phase4": self.temp_dir / "remote_phase4.json",
            "pre": self.temp_dir / "pre.json",
            "post": self.temp_dir / "post.json",
        }
        no_mutation = {
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "exchange_order_submission": "disabled",
        }
        self._write_json(paths["p7"], {"status": "ready", "applied_to_live": False, "eligible_for_live_order_submission": False})
        self._write_json(
            paths["phase2"],
            {"status": "ready", "no_future_fill_proven": True, "no_stale_fill_proven": True, "no_zero_fill_proven": True},
        )
        self._write_json(
            paths["phase2b"],
            {"status": "ready", "no_future_fill_proven": True, "no_stale_fill_proven": True, "no_zero_fill_proven": True},
        )
        self._write_json(
            paths["phase3"],
            {
                **no_mutation,
                "status": "ready",
                "run_id": "remote-p3",
                "generated_at_utc": "2026-06-06T17:01:00Z",
                "combined_candidate_trigger_proven": True,
                "changed_contribution_columns": [TARGET_CONTRIBUTION],
                "changed_non_target_contribution_columns": [],
                "non_target_contribution_max_abs_diff_enabled_vs_disabled": 0.0,
            },
        )
        self._write_json(
            paths["phase4"],
            {
                **no_mutation,
                "status": "ready",
                "run_id": "remote-p4",
                "generated_at_utc": "2026-06-06T17:02:00Z",
                "same_timestamp_context_proven": True,
                "same_risk_inputs_proven": True,
                "same_symbol_set_proven": True,
                "same_portfolio_engine_proven": True,
                "baseline_plan_only_risk_gate_status": "passed",
                "candidate_plan_only_risk_gate_status": "passed",
                "orders_submitted": 0,
                "fill_count": 0,
                "mainnet_order_submission_authorized": False,
                "target_weight_delta_symbol_count": 12,
                "absolute_target_weight_delta_sum": 0.2,
            },
        )
        pre = self._control_snapshot(config_hash="same-hash")
        post = self._control_snapshot(config_hash=post_config_hash)
        self._write_json(paths["pre"], pre)
        self._write_json(paths["post"], post)
        return paths

    def _control_snapshot(self, *, config_hash: str) -> dict:
        return {
            "remote_live_config_sha256": config_hash,
            "systemd": {
                "timers": {
                    "supervisor.timer": {"enabled": "enabled", "active": "active"},
                    "health.timer": {"enabled": "enabled", "active": "active"},
                },
                "services": {
                    "supervisor.service": {"active": "inactive"},
                    "health.service": {"active": "inactive"},
                },
            },
            "operator_state": [
                {"key": "live_delta_armed", "value": "true"},
                {"key": "paused", "value": "false"},
            ],
            "p8_remote_mutation_observed": False,
        }

    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
