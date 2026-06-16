from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.delta_post_trade_reconcile_backfill import (  # noqa: E402
    run_delta_post_trade_reconcile_backfill,
)
from enhengclaw.live_trading.state_store import LiveTradingStateStore  # noqa: E402


class DeltaPostTradeReconcileBackfillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="delta-post-trade-backfill-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_apply_binds_passed_position_monitor_to_direct_delta_run(self) -> None:
        config_path = self._config_path()
        delta_root = self._delta_run()
        monitor_root = self._position_monitor(delta_root)
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.initialize()
        delta_summary = json.loads((delta_root / "run_summary.json").read_text(encoding="utf-8"))
        store.write_json_row("run_summaries", "run_id", delta_summary["run_id"], delta_summary)

        summary, exit_code = run_delta_post_trade_reconcile_backfill(
            Namespace(
                config=str(config_path),
                delta_run=str(delta_root),
                position_monitor_run=str(monitor_root),
                expected_position_monitor_sha256="",
                apply=True,
            ),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "delta_post_trade_reconcile_backfill_applied")
        updated_file = json.loads((delta_root / "run_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(updated_file["post_trade_reconcile_status"], "passed_live_position_monitor")
        self.assertTrue(updated_file["post_trade_reconcile"]["accepted_by_prior_live_submission_gate"])
        latest = store.latest_live_order_submission()
        self.assertEqual(latest["run_id"], "direct-delta-run")
        self.assertEqual(latest["post_trade_reconcile_status"], "passed_live_position_monitor")
        with sqlite3.connect(self.temp_dir / "state.sqlite3") as conn:
            row = conn.execute(
                "SELECT artifact_type FROM live_artifacts WHERE artifact_type = ?",
                ("post_trade_reconcile_backfill",),
            ).fetchone()
        self.assertIsNotNone(row)

    def test_monitor_mismatch_blocks_without_updating_sqlite(self) -> None:
        config_path = self._config_path()
        delta_root = self._delta_run()
        monitor_root = self._position_monitor(delta_root, status="blocked_live_position_monitor")
        store = LiveTradingStateStore(self.temp_dir / "state.sqlite3")
        store.initialize()
        delta_summary = json.loads((delta_root / "run_summary.json").read_text(encoding="utf-8"))
        store.write_json_row("run_summaries", "run_id", delta_summary["run_id"], delta_summary)

        summary, exit_code = run_delta_post_trade_reconcile_backfill(
            Namespace(
                config=str(config_path),
                delta_run=str(delta_root),
                position_monitor_run=str(monitor_root),
                expected_position_monitor_sha256="",
                apply=True,
            ),
            now_fn=_fixed_now,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "delta_post_trade_reconcile_backfill_blocked")
        self.assertIn("position_monitor_not_passed:blocked_live_position_monitor", summary["blockers"])
        latest = store.latest_live_order_submission()
        self.assertEqual(latest["post_trade_reconcile_status"], "direct_delta_reconciled")

    def _config_path(self) -> Path:
        config_path = self.temp_dir / "live.yaml"
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

    def _delta_run(self) -> Path:
        root = self.temp_dir / "mainnet_delta_execution" / "direct-delta-run"
        root.mkdir(parents=True, exist_ok=True)
        summary = {
            "run_id": "direct-delta-run",
            "status": "mainnet_delta_orders_submitted",
            "execution_stage": "entry_second",
            "submitted_order_count": 2,
            "fill_count": 2,
            "reconciliation_status": "reconciled",
            "started_at_utc": "2026-06-15T02:07:22Z",
            "finished_at_utc": "2026-06-15T02:07:23Z",
            "post_trade_reconcile": {"status": "direct_delta_reconciled"},
        }
        (root / "run_summary.json").write_text(json.dumps(summary), encoding="utf-8")
        (root / "reconciliation.json").write_text(
            json.dumps(
                {
                    "status": "reconciled",
                    "submitted_order_count": 2,
                    "fill_count": 2,
                    "open_order_count": 0,
                    "expected_positions": {"BCHUSDT": -1.413, "ETHUSDT": 0.152},
                }
            ),
            encoding="utf-8",
        )
        return root

    def _position_monitor(self, delta_root: Path, *, status: str = "passed_live_position_monitor") -> Path:
        root = self.temp_dir / "position_monitor" / "position-monitor-run"
        root.mkdir(parents=True, exist_ok=True)
        summary = {
            "run_id": "position-monitor-run",
            "status": status,
            "blockers": [] if status == "passed_live_position_monitor" else ["position_drift"],
            "started_at_utc": "2026-06-15T02:07:57Z",
            "finished_at_utc": "2026-06-15T02:07:58Z",
            "artifact_root": str(root),
            "reference_run": str(delta_root),
            "open_order_count": 0,
            "open_position_count": 9,
        }
        (root / "run_summary.json").write_text(json.dumps(summary), encoding="utf-8")
        (root / "monitor_report.json").write_text(
            json.dumps(
                {
                    "status": status,
                    "read_only": True,
                    "side_effects": {
                        "orders_submitted": 0,
                        "orders_canceled": 0,
                        "order_test_calls": 0,
                        "account_settings_changed": 0,
                        "only_http_get_endpoints": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        return root


def _fixed_now() -> datetime:
    return datetime(2026, 6, 16, 8, 0, 0, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
