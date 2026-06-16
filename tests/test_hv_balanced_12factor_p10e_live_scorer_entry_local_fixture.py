from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_12factor_p10e_live_scorer_entry_local_fixture import (  # noqa: E402
    file_sha256,
    run_p10e_live_scorer_entry_local_fixture,
)


class HvBalanced12FactorP10eLiveScorerEntryLocalFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p10e-scorer-entry-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_p10e_ready_wraps_copied_live_scorer_entry_and_default_off_preserves_baseline(self) -> None:
        p10d_summary = self._write_p10d_artifacts()
        output_root = self.temp_dir / "proof_artifacts" / "p10e"

        summary, exit_code = run_p10e_live_scorer_entry_local_fixture(
            Namespace(p10d_summary=p10d_summary, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["fixture_scope"], "live_scorer_entry_local_fixture_only_outside_timer_supervisor")
        self.assertTrue(summary["live_scorer_entry_wrapped_locally"])
        self.assertFalse(summary["default_off_scorer_wrapper_enabled"])
        self.assertFalse(summary["candidate_scorer_loaded_into_live_scorer_entry"])
        self.assertTrue(summary["p10d_ready"])
        self.assertEqual(summary["baseline_source_sha256_before"], summary["baseline_source_sha256_after"])
        self.assertEqual(summary["baseline_copy_sha256"], summary["baseline_source_sha256_before"])
        self.assertEqual(summary["entry_input_sha256_before_wrapper"], summary["baseline_copy_sha256"])
        self.assertEqual(summary["entry_input_sha256_after_wrapper"], summary["entry_input_sha256_before_wrapper"])
        self.assertTrue(summary["disabled_baseline_scores_byte_for_byte_unchanged"])
        self.assertTrue(summary["disabled_wrapper_output_scores_hash_equals_baseline"])
        self.assertTrue(summary["disabled_executor_consumes_baseline_only"])
        self.assertEqual(summary["disabled_shadow_artifacts_written_count"], 0)
        self.assertTrue(summary["enabled_shadow_artifacts_under_proof_artifacts_only"])
        self.assertTrue(summary["enabled_executor_consumes_baseline_only"])
        self.assertFalse(summary["enabled_shadow_scorer_referenced_by_executor"])
        self.assertFalse(summary["executor_invoked"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertFalse(summary["supervisor_invoked"])
        self.assertFalse(summary["live_config_changed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "ctx.json").exists())
        self.assertTrue((output_root / "disabled.json").exists())
        self.assertTrue((output_root / "enabled.json").exists())

    def test_p10e_blocks_when_p10d_default_off_evidence_is_not_ready(self) -> None:
        p10d_summary = self._write_p10d_artifacts({"disabled_hook_baseline_byte_for_byte_unchanged": False})

        summary, exit_code = run_p10e_live_scorer_entry_local_fixture(
            Namespace(p10d_summary=p10d_summary, output_root=self.temp_dir / "proof_artifacts" / "blocked-p10d"),
            now_fn=lambda: datetime(2026, 6, 8, 15, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p10d_not_ready_for_p10e_live_scorer_entry_fixture", summary["blockers"])
        self.assertIn("p10d_ready", summary["blockers"])
        self.assertFalse(summary["p10d_ready"])
        self.assertFalse(summary["executor_invoked"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_p10e_blocks_when_output_root_is_not_proof_artifacts(self) -> None:
        p10d_summary = self._write_p10d_artifacts()

        summary, exit_code = run_p10e_live_scorer_entry_local_fixture(
            Namespace(p10d_summary=p10d_summary, output_root=self.temp_dir / "not_proof"),
            now_fn=lambda: datetime(2026, 6, 8, 15, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p10e_output_root_not_under_proof_artifacts", summary["blockers"])
        self.assertIn("output_root_under_proof_artifacts", summary["blockers"])
        self.assertEqual(summary["disabled_wrapper_status"], "")
        self.assertFalse(summary["timer_path_invoked"])
        self.assertEqual(summary["orders_submitted"], 0)

    def _write_p10d_artifacts(self, overrides: dict | None = None) -> Path:
        p10d_root = self.temp_dir / "p10d"
        p10d_root.mkdir(parents=True, exist_ok=True)
        baseline_path = p10d_root / "baseline.csv"
        shadow_path = p10d_root / "shadow.csv"
        pd.DataFrame(
            [
                {
                    "symbol": "BTCUSDT",
                    "subject": "BTC",
                    "decision_time_utc": "2026-06-08T14:00:00Z",
                    "score": 0.0,
                    "score_source": "baseline_executor_fixture",
                },
                {
                    "symbol": "ETHUSDT",
                    "subject": "ETH",
                    "decision_time_utc": "2026-06-08T14:00:00Z",
                    "score": 0.0,
                    "score_source": "baseline_executor_fixture",
                },
            ]
        ).to_csv(baseline_path, index=False)
        pd.DataFrame(
            [
                {
                    "symbol": "BTCUSDT",
                    "subject": "BTC",
                    "decision_time_utc": "2026-06-08T14:00:00Z",
                    "shadow_score": 0.25,
                    "score_source": "research_contract_shadow_scorer_fixture",
                },
                {
                    "symbol": "ETHUSDT",
                    "subject": "ETH",
                    "decision_time_utc": "2026-06-08T14:00:00Z",
                    "shadow_score": -0.15,
                    "score_source": "research_contract_shadow_scorer_fixture",
                },
            ]
        ).to_csv(shadow_path, index=False)
        summary = {
            "status": "ready",
            "blockers": [],
            "p10c_snapshot_ready": True,
            "disabled_hook_baseline_byte_for_byte_unchanged": True,
            "disabled_hook_shadow_artifacts_written_count": 0,
            "enabled_hook_executor_consumes_baseline_only": True,
            "enabled_hook_shadow_artifacts_under_proof_artifacts_only": True,
            "enabled_hook_shadow_scorer_referenced_by_executor": False,
            "candidate_scorer_loaded_into_executor": False,
            "candidate_scorer_loaded_into_timer": False,
            "executor_invoked": False,
            "timer_path_invoked": False,
            "supervisor_invoked": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "artifacts": {
                "baseline_executor_scores_fixture": str(baseline_path),
                "shadow_research_contract_scorer_scores_fixture": str(shadow_path),
            },
            "baseline_executor_scores_fixture_sha256": file_sha256(baseline_path),
            "shadow_research_contract_scorer_scores_fixture_sha256": file_sha256(shadow_path),
        }
        summary.update(overrides or {})
        summary_path = p10d_root / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        return summary_path


if __name__ == "__main__":
    unittest.main()
