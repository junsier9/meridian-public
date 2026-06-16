from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.live_trading.run_hv_balanced_timer_path_live_delta_canary import (
    APPROVE_DECISION,
    CommandResult,
    parse_args,
    remote_summary_ready,
    run_canary,
)


def _ready_remote_summary() -> dict[str, object]:
    return {
        "status": "ready",
        "blockers": [],
        "orders_submitted": 1,
        "fill_count": 1,
        "timer_path_invoked": True,
        "supervisor_invoked": True,
        "core_loop_invoked": True,
        "systemd_timer_service_invoked": False,
        "production_timer_service_loaded_or_modified": False,
        "production_config_modified": False,
        "production_state_mutated": False,
        "continuous_automation_enabled": False,
        "configured_cycle_count": 1,
        "completed_cycle_count": 1,
        "final_operator_state": {"live_delta_armed": False},
    }


class TimerPathLiveDeltaCanaryTests(unittest.TestCase):
    def test_ready_remote_summary_acceptance_requires_single_order_disarmed_timer_path(self) -> None:
        summary = _ready_remote_summary()

        self.assertTrue(remote_summary_ready(summary))

        summary["orders_submitted"] = 2
        self.assertFalse(remote_summary_ready(summary))

    def test_fast_follow_disabled_skipped_is_acceptable(self) -> None:
        summary = _ready_remote_summary()
        summary["status"] = "blocked"
        summary["blockers"] = ["fast_follow_schedule_unexpected:skipped"]
        summary["supervisor_summary"] = {
            "fast_follow_entry_second_schedule": {
                "status": "skipped",
                "reason": "fast_follow_entry_second_disabled",
            }
        }

        self.assertTrue(remote_summary_ready(summary))

    def test_run_canary_records_ready_single_cycle_without_continuous_automation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            calls: list[list[str]] = []

            def fake_runner(args: list[str]) -> CommandResult:
                calls.append(list(args))
                return CommandResult(args=list(args), returncode=0, stdout=json.dumps(_ready_remote_summary()), stderr="")

            args = parse_args(
                [
                    "--output-root",
                    tmp,
                    "--owner-decision",
                    APPROVE_DECISION,
                    "--quantity",
                    "0.001",
                    "--max-notional-usdt",
                    "150",
                ]
            )
            summary, exit_code = run_canary(args, command_runner=fake_runner)

            self.assertEqual(exit_code, 0)
            self.assertEqual(summary["status"], "ready")
            self.assertTrue(summary["timer_path_live_delta_canary_ready"])
            self.assertEqual(summary["orders_submitted"], 1)
            self.assertEqual(summary["fill_count"], 1)
            self.assertTrue(summary["timer_path_invoked"])
            self.assertTrue(summary["supervisor_invoked"])
            self.assertFalse(summary["systemd_timer_service_invoked"])
            self.assertFalse(summary["production_timer_service_loaded_or_modified"])
            self.assertFalse(summary["production_config_modified"])
            self.assertFalse(summary["production_state_mutated"])
            self.assertFalse(summary["continuous_automation_enabled"])
            self.assertFalse(summary["operator_live_delta_armed_after_canary"])
            self.assertEqual(len(calls), 1)
            self.assertIn("run_mainnet_live_supervisor", calls[0][-1])
            self.assertTrue((Path(tmp) / "summary.json").exists())

    def test_run_canary_blocks_if_remote_state_remains_armed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:

            def fake_runner(args: list[str]) -> CommandResult:
                remote = _ready_remote_summary()
                remote["final_operator_state"] = {"live_delta_armed": True}
                return CommandResult(args=list(args), returncode=0, stdout=json.dumps(remote), stderr="")

            args = parse_args(["--output-root", tmp, "--owner-decision", APPROVE_DECISION])
            summary, exit_code = run_canary(args, command_runner=fake_runner)

            self.assertEqual(exit_code, 2)
            self.assertEqual(summary["status"], "blocked")
            self.assertIn("remote_timer_path_canary_summary_not_ready", summary["blockers"])
            self.assertTrue(summary["operator_live_delta_armed_after_canary"])

    def test_owner_not_approved_does_not_invoke_remote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            called = False

            def fake_runner(args: list[str]) -> CommandResult:
                nonlocal called
                called = True
                return CommandResult(args=list(args), returncode=0, stdout="{}", stderr="")

            args = parse_args(["--output-root", tmp, "--owner-decision", "decline"])
            summary, exit_code = run_canary(args, command_runner=fake_runner)

            self.assertEqual(exit_code, 2)
            self.assertFalse(called)
            self.assertIn("owner_decision_not_approved_for_timer_path_live_delta_canary", summary["blockers"])


if __name__ == "__main__":
    unittest.main()
