from __future__ import annotations

import unittest

from tests.test_helpers import ROOT

import sys

SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.ops.scheduled_task_contracts import (
    evaluate_startup_catchup,
    evaluate_task_readiness,
    evaluate_upstream_dependency_status,
    load_scheduled_task_manifest,
    task_resilience,
    validate_scheduled_task_summary,
)


MANIFEST_PATH = ROOT / "config" / "scheduled_tasks" / "manifest.json"


class ScheduledTaskContractTests(unittest.TestCase):
    def test_validate_scheduled_task_summary_requires_standard_metadata(self) -> None:
        blockers = validate_scheduled_task_summary(
            {
                "task_key": "binance_ohlcv_sync",
                "task_name": "OpenClaw Binance OHLCV Sync",
                "success": True,
            }
        )

        self.assertTrue(any("summary missing required field: exit_status" in blocker for blocker in blockers))
        self.assertTrue(any("summary missing required field: produced_at_utc" in blocker for blocker in blockers))
        self.assertTrue(any("summary missing required field: input_watermarks" in blocker for blocker in blockers))

    def test_quant_research_readiness_fails_when_ohlcv_upstream_is_stale(self) -> None:
        manifest = load_scheduled_task_manifest(MANIFEST_PATH)
        summaries_by_task_key = {
            "binance_ohlcv_sync": self._summary(
                task_key="binance_ohlcv_sync",
                task_name="OpenClaw Binance OHLCV Sync",
                produced_at_utc="2026-04-20T06:00:00Z",
                artifact_family="binance_ohlcv_sync",
            ),
            "quant_derivatives_sync": self._summary(
                task_key="quant_derivatives_sync",
                task_name="OpenClaw Quant Derivatives Sync",
                produced_at_utc="2026-04-20T08:30:00Z",
                artifact_family="quant_derivatives_sync",
            ),
            "quant_universe_freeze": self._summary(
                task_key="quant_universe_freeze",
                task_name="OpenClaw Quant Universe Freeze",
                produced_at_utc="2026-04-20T08:45:00Z",
                artifact_family="quant_universe_freeze",
            ),
            "quant_coinapi_spot_sync": self._summary(
                task_key="quant_coinapi_spot_sync",
                task_name="OpenClaw Quant CoinAPI Spot Sync",
                produced_at_utc="2026-04-20T08:35:00Z",
                artifact_family="quant_coinapi_spot_sync",
            ),
            "quant_research_daily_cycle": self._summary(
                task_key="quant_research_daily_cycle",
                task_name="OpenClaw Quant Monitoring Daily Cycle",
                produced_at_utc="2026-04-20T09:00:00Z",
                artifact_family="quant_research_cycle",
                input_watermarks={
                    "binance_ohlcv_sync_produced_at_utc": "2026-04-20T06:00:00Z",
                    "quant_derivatives_sync_produced_at_utc": "2026-04-20T08:30:00Z",
                    "quant_universe_freeze_produced_at_utc": "2026-04-20T08:45:00Z",
                },
            ),
        }

        result = evaluate_task_readiness(
            task_key="quant_research_daily_cycle",
            manifest=manifest,
            summaries_by_task_key=summaries_by_task_key,
            now_utc="2026-04-20T10:30:00Z",
        )

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("task summary is stale for binance_ohlcv_sync" in blocker for blocker in result["blockers"]))

    def test_manifest_v2_declares_startup_catchup_only_for_key_chain(self) -> None:
        manifest = load_scheduled_task_manifest(MANIFEST_PATH)
        self.assertEqual(manifest["contract_version"], "scheduled_tasks_manifest.v2")
        enabled_startup = {
            str(task["task_key"])
            for task in manifest["tasks"]
            if task_resilience(task)["startup_catchup_enabled"]
        }
        self.assertEqual(
            enabled_startup,
            {
                "binance_ohlcv_sync",
                "quant_coinapi_spot_sync",
                "quant_universe_input_producer",
                "quant_derivatives_sync",
                "quant_universe_freeze",
                "quant_research_daily_cycle",
                "quant_repo_health_guard",
                "quant_strategy_proposal_cycle",
            },
        )

    def test_daily_catchup_skips_before_due_and_after_success(self) -> None:
        manifest = load_scheduled_task_manifest(MANIFEST_PATH)
        task_entry = next(task for task in manifest["tasks"] if task["task_key"] == "quant_research_daily_cycle")

        before_due = evaluate_startup_catchup(
            task_entry=task_entry,
            current_summary=None,
            now_local="2026-04-21T03:30:00+08:00",
        )
        self.assertEqual(before_due, {"should_run": False, "reason": "scheduled_time_not_reached"})

        after_due = evaluate_startup_catchup(
            task_entry=task_entry,
            current_summary=None,
            now_local="2026-04-21T04:00:00+08:00",
        )
        self.assertEqual(after_due, {"should_run": True, "reason": "scheduled_window_missed"})

        after_success = evaluate_startup_catchup(
            task_entry=task_entry,
            current_summary=self._summary(
                task_key="quant_research_daily_cycle",
                task_name="OpenClaw Quant Monitoring Daily Cycle",
                produced_at_utc="2026-04-20T20:15:00Z",
                artifact_family="quant_research_cycle",
            ),
            now_local="2026-04-21T04:30:00+08:00",
        )
        self.assertEqual(after_success, {"should_run": False, "reason": "already_succeeded_today"})

    def test_quant_strategy_discovery_daily_catchup_runs_after_daily_window(self) -> None:
        manifest = load_scheduled_task_manifest(MANIFEST_PATH)
        task_entry = next(task for task in manifest["tasks"] if task["task_key"] == "quant_strategy_proposal_cycle")
        self.assertEqual(task_entry["expected_interval"], "daily")
        self.assertEqual(task_entry["schedule"]["type"], "daily")
        self.assertEqual(task_entry["schedule"]["time"], "05:00")
        self.assertEqual(task_entry["freshness_budget_hours"], 24)
        self.assertEqual(task_entry["upstream_dependencies"], ["quant_repo_health_guard"])

        before_due = evaluate_startup_catchup(
            task_entry=task_entry,
            current_summary=None,
            now_local="2026-04-27T04:30:00+08:00",
        )
        self.assertEqual(before_due, {"should_run": False, "reason": "scheduled_time_not_reached"})

        after_due = evaluate_startup_catchup(
            task_entry=task_entry,
            current_summary=None,
            now_local="2026-04-27T05:30:00+08:00",
        )
        self.assertEqual(after_due, {"should_run": True, "reason": "scheduled_window_missed"})

    def test_upstream_dependency_status_distinguishes_missing_and_stale(self) -> None:
        manifest = load_scheduled_task_manifest(MANIFEST_PATH)
        missing = evaluate_upstream_dependency_status(
            task_key="quant_universe_freeze",
            manifest=manifest,
            summaries_by_task_key={},
            now_utc="2026-04-20T20:00:00Z",
        )
        self.assertEqual(missing["status"], "missing")

        stale = evaluate_upstream_dependency_status(
            task_key="quant_research_daily_cycle",
            manifest=manifest,
            summaries_by_task_key={
                "binance_ohlcv_sync": self._summary(
                    task_key="binance_ohlcv_sync",
                    task_name="OpenClaw Binance OHLCV Sync",
                    produced_at_utc="2026-04-20T06:00:00Z",
                    artifact_family="binance_ohlcv_sync",
                ),
                "quant_derivatives_sync": self._summary(
                    task_key="quant_derivatives_sync",
                    task_name="OpenClaw Quant Derivatives Sync",
                    produced_at_utc="2026-04-20T19:00:00Z",
                    artifact_family="quant_derivatives_sync",
                ),
                "quant_coinapi_spot_sync": self._summary(
                    task_key="quant_coinapi_spot_sync",
                    task_name="OpenClaw Quant CoinAPI Spot Sync",
                    produced_at_utc="2026-04-20T19:05:00Z",
                    artifact_family="quant_coinapi_spot_sync",
                ),
                "quant_universe_input_producer": self._summary(
                    task_key="quant_universe_input_producer",
                    task_name="OpenClaw Quant Universe Input Producer",
                    produced_at_utc="2026-04-20T19:10:00Z",
                    artifact_family="quant_universe_input_producer",
                ),
                "quant_universe_freeze": self._summary(
                    task_key="quant_universe_freeze",
                    task_name="OpenClaw Quant Universe Freeze",
                    produced_at_utc="2026-04-20T19:20:00Z",
                    artifact_family="quant_universe_freeze",
                ),
            },
            now_utc="2026-04-20T20:30:00Z",
        )
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["dependencies"]["binance_ohlcv_sync"], "stale")

    def test_research_intake_readiness_requires_quant_repo_health_guard(self) -> None:
        manifest = load_scheduled_task_manifest(MANIFEST_PATH)
        summaries_by_task_key = {
            "structural_research_scan": self._summary(
                task_key="structural_research_scan",
                task_name="OpenClaw Structural Research Scan",
                produced_at_utc="2026-04-20T19:50:00Z",
                artifact_family="openclaw_structural_research_scan",
            ),
        }

        result = evaluate_task_readiness(
            task_key="research_intake_cycle",
            manifest=manifest,
            summaries_by_task_key=summaries_by_task_key,
            now_utc="2026-04-20T20:00:00Z",
        )

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("upstream dependency summary missing: quant_repo_health_guard" in blocker for blocker in result["blockers"]))

    def _summary(
        self,
        *,
        task_key: str,
        task_name: str,
        produced_at_utc: str,
        artifact_family: str,
        input_watermarks: dict[str, str] | None = None,
    ) -> dict[str, object]:
        return {
            "task_key": task_key,
            "task_name": task_name,
            "exit_status": 0,
            "success": True,
            "produced_at_utc": produced_at_utc,
            "source_commit_sha": "abc123",
            "artifact_family": artifact_family,
            "input_watermarks": input_watermarks or {},
            "upstream_versions": {},
        }


if __name__ == "__main__":
    unittest.main()
