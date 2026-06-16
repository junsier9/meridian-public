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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9e_owner_gated_timer_adjacent_fixture import (  # noqa: E402
    APPROVE_P9E_DECISION,
    build_phase9e,
    file_sha256,
    resolve_path,
)


class HvBalancedDth60CoinglassPhase9eOwnerGatedTimerAdjacentFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9e-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9e_ready_runs_hook_only_against_copied_timer_context(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase9e"

        summary, exit_code = build_phase9e(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 7, 13, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["fixture_scope"], "owner_gated_timer_adjacent_local_fixture_only")
        self.assertTrue(summary["hook_enabled_inside_fixture"])
        self.assertFalse(summary["default_live_hook_enabled"])
        self.assertFalse(summary["hook_deployment_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertEqual(
            summary["executor_input_plan_sha256_after_hook"],
            summary["baseline_target_plan_sha256"],
        )
        self.assertNotEqual(
            summary["candidate_shadow_plan_sha256"],
            summary["executor_input_plan_sha256_after_hook"],
        )
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertTrue(summary["candidate_artifacts_under_proof_artifacts_only"])
        self.assertFalse(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertFalse(summary["eligible_for_timer_path_load"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        self.assertEqual(summary["copied_timer_context_snapshot"]["context_kind"], "copied_timer_adjacent_fixture_context")
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        self.assertTrue((output_root / "copied_timer_context_snapshot.json").exists())
        self.assertTrue((output_root / "timer_adjacent_hook_summary.json").exists())
        self.assertTrue((output_root / "summary.json").exists())

    def test_phase9e_blocks_when_owner_decision_is_not_p9e_fixture_only(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9e(
            self._args(paths, output_root=self.temp_dir / "wrong-decision", owner_decision="approve_timer_load"),
            now_fn=lambda: datetime(2026, 6, 7, 13, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_not_p9e_timer_adjacent_fixture_only", summary["blockers"])
        self.assertIn("owner_decision_p9e_fixture_only", summary["blockers"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def test_phase9e_blocks_when_p9d_hash_or_boundary_is_stale(self) -> None:
        paths = self._write_ready_inputs(
            p9d_overrides={
                "default_off_hook_enabled": True,
                "hook_module": {"path": "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py", "sha256": "bad"},
            }
        )

        summary, exit_code = build_phase9e(
            self._args(paths, output_root=self.temp_dir / "bad-p9d"),
            now_fn=lambda: datetime(2026, 6, 7, 13, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("phase9d_not_ready_for_p9e", summary["blockers"])
        self.assertIn("phase9d_ready", summary["blockers"])
        self.assertIn("hook_module_hash_matches_p9d", summary["blockers"])
        self.assertFalse(summary["eligible_for_timer_path_load"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9E_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            phase9d_summary=str(paths["phase9d"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(self, *, p9d_overrides: dict | None = None) -> dict[str, Path]:
        source_root = self.temp_dir / "source"
        source_root.mkdir()
        baseline = source_root / "baseline_target_plan.json"
        candidate = source_root / "candidate_target_plan.json"
        target_plan_diff = source_root / "target_plan_diff.csv"
        shared_context = source_root / "shared_input_context.json"
        self._write_json(baseline, {"positions": [{"symbol": "BTCUSDT", "target_weight": 0.1}], "kind": "baseline"})
        self._write_json(candidate, {"positions": [{"symbol": "ETHUSDT", "target_weight": 0.1}], "kind": "candidate"})
        target_plan_diff.write_text("symbol,baseline,candidate\nBTCUSDT,0.1,0\n", encoding="utf-8")
        self._write_json(shared_context, {"as_of": "2026-06-07T00:00:00Z"})
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        p9d = {
            "status": "ready",
            "blockers": [],
            "implementation_scope": "default_off_observe_only_hook_contract_only",
            "p9c_owner_decision_approved": True,
            "default_off_hook_enabled": False,
            "hook_deployment_authorized": False,
            "timer_path_load_authorized": False,
            "live_order_submission_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "disabled_hook_baseline_output_unchanged": True,
            "disabled_hook_candidate_artifacts_written_count": 0,
            "enabled_fixture_execution_target_unchanged": True,
            "enabled_fixture_candidate_artifacts_under_proof_artifacts_only": True,
            "candidate_plan_referenced_by_executor": False,
            "live_supervisor_loads_candidate_hook": False,
            "eligible_for_timer_path_load": False,
            "eligible_for_live_order_submission": False,
            "deployed_hook": False,
            "hook_module": {
                "path": str(hook_path),
                "exists": True,
                "sha256": file_sha256(hook_path),
            },
            "source_evidence": {
                "baseline_source": {"path": str(baseline), "exists": True, "sha256": file_sha256(baseline)},
                "candidate_source": {"path": str(candidate), "exists": True, "sha256": file_sha256(candidate)},
                "target_plan_diff": {
                    "path": str(target_plan_diff),
                    "exists": True,
                    "sha256": file_sha256(target_plan_diff),
                },
                "shared_input_context": {
                    "path": str(shared_context),
                    "exists": True,
                    "sha256": file_sha256(shared_context),
                },
            },
        }
        p9d.update(p9d_overrides or {})
        p9d_path = self.temp_dir / "p9d_summary.json"
        self._write_json(p9d_path, p9d)
        return {"phase9d": p9d_path}

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
