from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
import json
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

from enhengclaw.live_trading.mainnet_multiphase_migration_runner import (  # noqa: E402
    run_mainnet_multiphase_migration,
)


class HvBalancedMainnetMultiphaseMigrationRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="hv-balanced-mainnet-multiphase-migration-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_stage_builds_no_order_follow_up_artifacts(self) -> None:
        config_path = self._config_path()
        calls: dict[str, list[Namespace]] = {"target": [], "delta": []}

        def fake_target(args: Namespace, **_kwargs):
            calls["target"].append(args)
            return _target_summary(self.temp_dir / "target-plan", active_stage="reduce_first"), 0

        def fake_delta(args: Namespace, **_kwargs):
            calls["delta"].append(args)
            self.assertFalse(args.execute_mainnet_delta_orders)
            return {
                "status": "mainnet_delta_execution_ready",
                "artifact_root": str(self.temp_dir / "delta-dry-run"),
                "required_confirmation": "LIVE_DELTA_EXECUTION:HV_BALANCED:MAINNET:PLAN_SHA256=abc:CURRENT_POSITION_AWARE:ONE_WAY:CROSS_MAX_LEVERAGE=2:EXECUTION_STAGE=REDUCE_FIRST:DELTA_ONLY:NO_RECURRING:NO_DAILY_PNL_GATE",
                "blockers": [],
            }, 0

        summary, exit_code = run_mainnet_multiphase_migration(
            _args(config_path=config_path, stage="reduce_first"),
            env={"LIVE_KEY": "key", "LIVE_SECRET": "secret"},
            target_plan_runner=fake_target,
            delta_runner=fake_delta,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_multiphase_migration_stage_ready")
        self.assertEqual(summary["active_execution_phase"], "reduce_first")
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertTrue(summary["runner_never_submits_orders"])
        self.assertEqual(len(calls["target"]), 1)
        self.assertEqual(len(calls["delta"]), 1)
        self.assertTrue(summary["operator_next_steps"]["live_delta_command_requires_manual_execution"])
        self.assertIn("--execute-mainnet-delta-orders", summary["operator_next_steps"]["live_delta_command"])
        run_root = Path(summary["artifact_root"])
        self.assertTrue((run_root / "target_plan_summary.json").exists())
        self.assertTrue((run_root / "delta_dry_run_summary.json").exists())
        next_steps = json.loads((run_root / "operator_next_steps.json").read_text(encoding="utf-8"))
        self.assertNotIn("--i-understand-daily-realized-pnl-gate-is-active", next_steps["live_delta_command"])
        self.assertNotIn("--i-understand-daily-loss-budget-is-review-only", next_steps["live_delta_command"])
        self.assertEqual(next_steps["after_successful_execution_run_follow_up_command"][5], "entry_second")

    def test_stage_mismatch_blocks_before_delta_dry_run(self) -> None:
        config_path = self._config_path()
        delta_called = False

        def fake_target(args: Namespace, **_kwargs):
            return _target_summary(self.temp_dir / "target-plan", active_stage="reduce_first"), 0

        def fake_delta(args: Namespace, **_kwargs):
            nonlocal delta_called
            delta_called = True
            return {}, 0

        summary, exit_code = run_mainnet_multiphase_migration(
            _args(config_path=config_path, stage="entry_second"),
            target_plan_runner=fake_target,
            delta_runner=fake_delta,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "mainnet_multiphase_migration_blocked")
        self.assertIn("stage_mismatch:expected=entry_second:actual=reduce_first", summary["blockers"])
        self.assertFalse(delta_called)
        self.assertEqual(summary["operator_next_steps"]["action"], "do_not_submit_orders")

    def test_noop_target_holds_without_delta_dry_run(self) -> None:
        config_path = self._config_path()
        delta_called = False

        def fake_target(args: Namespace, **_kwargs):
            summary = _target_summary(self.temp_dir / "target-plan", active_stage="")
            summary["status"] = "mainnet_current_position_rebalance_dust_noop"
            summary["planned_delta_order_count"] = 0
            return summary, 0

        def fake_delta(args: Namespace, **_kwargs):
            nonlocal delta_called
            delta_called = True
            return {}, 0

        summary, exit_code = run_mainnet_multiphase_migration(
            _args(config_path=config_path),
            target_plan_runner=fake_target,
            delta_runner=fake_delta,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_multiphase_migration_noop")
        self.assertFalse(delta_called)
        self.assertEqual(summary["operator_next_steps"]["action"], "hold_and_monitor")

    def test_completed_slot_hold_target_holds_without_delta_dry_run(self) -> None:
        config_path = self._config_path()
        delta_called = False

        def fake_target(args: Namespace, **_kwargs):
            summary = _target_summary(self.temp_dir / "target-plan", active_stage="noop")
            summary["status"] = "mainnet_current_position_rebalance_hold_until_next_rebalance_slot"
            summary["planned_delta_order_count"] = 0
            return summary, 0

        def fake_delta(args: Namespace, **_kwargs):
            nonlocal delta_called
            delta_called = True
            return {}, 0

        summary, exit_code = run_mainnet_multiphase_migration(
            _args(config_path=config_path),
            target_plan_runner=fake_target,
            delta_runner=fake_delta,
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "mainnet_multiphase_migration_noop")
        self.assertFalse(delta_called)
        self.assertEqual(summary["operator_next_steps"]["action"], "hold_and_monitor")
        self.assertEqual(
            summary["operator_next_steps"]["reason"],
            "mainnet_current_position_rebalance_hold_until_next_rebalance_slot",
        )

    def _config_path(self) -> Path:
        config_path = self.temp_dir / "hv_balanced_multiphase_migration.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "state:",
                    f"  sqlite_path: {(self.temp_dir / 'state.sqlite3').as_posix()}",
                    f"  artifact_root: {(self.temp_dir / 'runs').as_posix()}",
                ]
            ),
            encoding="utf-8",
        )
        return config_path


def _args(*, config_path: Path, stage: str = "auto") -> Namespace:
    return Namespace(
        config=str(config_path),
        as_of="now",
        fixture_panel="",
        symbols="",
        public_market_data=False,
        api_key_env="",
        api_secret_env="",
        stage=stage,
        previous_stage_artifact="",
        ignore_heartbeat_run_id="",
        position_tolerance=1e-9,
    )


def _target_summary(plan_root: Path, *, active_stage: str) -> dict[str, object]:
    plan_root.mkdir(parents=True, exist_ok=True)
    return {
        "run_id": "target-plan-1",
        "status": "mainnet_current_position_rebalance_plan_ready",
        "artifact_root": str(plan_root),
        "blockers": [],
        "active_execution_phase": active_stage,
        "planned_delta_order_count": 2 if active_stage else 0,
        "phase_counts": {active_stage: 2} if active_stage else {},
        "deferred_phase_counts": {"entry_second": 2} if active_stage == "reduce_first" else {},
    }


def _fixed_now() -> datetime:
    return datetime(2026, 5, 23, 6, 0, 0, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
