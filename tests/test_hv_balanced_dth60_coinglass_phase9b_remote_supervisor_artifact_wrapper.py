from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import hashlib
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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9b_remote_supervisor_artifact_wrapper import (  # noqa: E402
    PLAN_HASH_REQUIRED_FILES,
    build_phase9b_summary,
)


class HvBalancedDth60CoinglassPhase9bRemoteSupervisorArtifactWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9b-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9b_ready_when_executor_manifest_consumes_baseline_plan(self) -> None:
        paths = self._write_remote_artifacts()

        summary, exit_code = build_phase9b_summary(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p9b"),
            now_fn=lambda: datetime(2026, 6, 7, 9, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertTrue(summary["executor_input_plan_hash_equals_baseline"])
        self.assertEqual(summary["executor_input_reference_kind"], "source_plan_manifest")
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        self.assertEqual(summary["candidate_orders_submitted"], 0)
        self.assertTrue(summary["wrapper_output_under_proof_artifacts"])

    def test_phase9b_blocks_when_manifest_hash_does_not_match_plan_hash(self) -> None:
        paths = self._write_remote_artifacts(manifest_hash="wrong-hash")

        summary, exit_code = build_phase9b_summary(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p9b-blocked"),
            now_fn=lambda: datetime(2026, 6, 7, 9, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("executor_input_plan_hash_equals_baseline", summary["blockers"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def test_phase9b_blocks_when_executor_manifest_points_to_candidate_or_proof_artifacts(self) -> None:
        paths = self._write_remote_artifacts(plan_root_override=str(self.temp_dir / "proof_artifacts" / "candidate_plan"))

        summary, exit_code = build_phase9b_summary(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p9b-candidate"),
            now_fn=lambda: datetime(2026, 6, 7, 9, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("executor_input_plan_root_equals_supervisor_plan_root", summary["blockers"])
        self.assertIn("candidate_plan_not_referenced_by_executor", summary["blockers"])

    def test_phase9b_ready_from_latest_supervisor_core_loop_inline_plan(self) -> None:
        paths = self._write_latest_supervisor_inline_artifacts()

        summary, exit_code = build_phase9b_summary(
            self._args(paths, output_root=self.temp_dir / "proof_artifacts" / "p9b-inline"),
            now_fn=lambda: datetime(2026, 6, 7, 9, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["executor_input_reference_kind"], "core_loop_inline_strategy_plan")
        self.assertEqual(summary["cycle"]["executor_cycle_source"], "core_loop_summary.cycles")
        self.assertTrue(summary["inline_strategy_plan_artifacts_present"])
        self.assertTrue(summary["inline_plan_reference_matches_baseline"])
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertTrue(summary["executor_input_plan_hash_equals_baseline"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertEqual(summary["candidate_orders_submitted"], 0)
        self.assertEqual(summary["candidate_fill_count"], 0)
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def _args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            supervisor_summary=str(paths["supervisor_summary"]),
            pre_control_snapshot=str(paths["pre"]),
            post_control_snapshot=str(paths["post"]),
            require_output_under_proof_artifacts=True,
        )

    def _write_remote_artifacts(
        self,
        *,
        manifest_hash: str | None = None,
        plan_root_override: str = "",
    ) -> dict[str, Path]:
        live_root = self.temp_dir / "repo" / "artifacts" / "live_trading" / "hv"
        supervisor_root = live_root / "mainnet_live_supervisor" / "latest-supervisor"
        plan_root = live_root / "mainnet_multiphase_target_plan" / "latest-plan"
        executor_root = live_root / "mainnet_delta_execution" / "latest-delta"
        supervisor_root.mkdir(parents=True)
        plan_root.mkdir(parents=True)
        executor_root.mkdir(parents=True)
        for name in PLAN_HASH_REQUIRED_FILES:
            path = plan_root / name
            if name.endswith(".csv"):
                path.write_text("symbol,value\nBTCUSDT,1\n", encoding="utf-8")
            else:
                path.write_text(json.dumps({"file": name}, sort_keys=True) + "\n", encoding="utf-8")
        plan_hash = self._plan_hash(plan_root)
        manifest_root = plan_root_override or str(plan_root)
        (executor_root / "source_plan_manifest.json").write_text(
            json.dumps(
                {
                    "plan_root": manifest_root,
                    "plan_hash": manifest_hash if manifest_hash is not None else plan_hash,
                    "source_run_id": "plan-run",
                    "execute_requested": False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        cycle = {
            "cycle_index": 1,
            "status": "cycle_plan_only_ready",
            "plan_artifact_root": str(plan_root),
            "plan_status": "mainnet_current_position_rebalance_ready",
            "delta_preflight_artifact_root": str(executor_root),
            "orders_submitted": 0,
            "fill_count": 0,
            "live_delta_authorized": False,
        }
        (supervisor_root / "cycle_001.json").write_text(json.dumps(cycle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        supervisor = {
            "run_id": "latest-supervisor",
            "status": "mainnet_live_supervisor_completed",
            "artifact_root": str(supervisor_root),
            "orders_submitted": 0,
            "fill_count": 0,
            "live_delta_authorized": False,
            "target_engine": "multiphase_equal_sleeve",
            "cycles": [cycle],
        }
        supervisor_summary = supervisor_root / "run_summary.json"
        supervisor_summary.write_text(json.dumps(supervisor, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        pre = self._control_snapshot()
        post = self._control_snapshot()
        pre_path = self.temp_dir / "pre.json"
        post_path = self.temp_dir / "post.json"
        pre_path.write_text(json.dumps(pre), encoding="utf-8")
        post_path.write_text(json.dumps(post), encoding="utf-8")
        return {"supervisor_summary": supervisor_summary, "pre": pre_path, "post": post_path}

    def _write_latest_supervisor_inline_artifacts(self) -> dict[str, Path]:
        live_root = self.temp_dir / "repo" / "artifacts" / "live_trading" / "hv"
        supervisor_root = live_root / "mainnet_live_supervisor" / "latest-supervisor-inline"
        core_loop_root = live_root / "mainnet_core_loop" / "latest-core-loop"
        plan_root = live_root / "mainnet_multiphase_target_plan" / "latest-plan-inline"
        supervisor_root.mkdir(parents=True)
        core_loop_root.mkdir(parents=True)
        plan_root.mkdir(parents=True)
        for name in PLAN_HASH_REQUIRED_FILES:
            path = plan_root / name
            if name.endswith(".csv"):
                path.write_text("symbol,value\nBTCUSDT,1\n", encoding="utf-8")
            else:
                path.write_text(json.dumps({"file": name}, sort_keys=True) + "\n", encoding="utf-8")
        inline_cycle = {
            "cycle_index": 1,
            "status": "cycle_dust_noop",
            "execution_status": "noop_dust_delta",
            "plan_artifact_root": str(plan_root),
            "plan_status": "mainnet_current_position_rebalance_dust_noop",
            "planned_delta_order_count": 0,
            "orders_submitted": 0,
            "fill_count": 0,
            "live_delta_authorized": False,
            "strategy_target": {
                "artifact_root": str(plan_root),
                "orders_submitted": 0,
                "fill_count": 0,
                "planned_delta_order_count": 0,
                "status": "mainnet_current_position_rebalance_dust_noop",
            },
            "strategy_plan_artifacts": {
                "run_summary": {"artifact_root": str(plan_root), "status": "ready"},
                "execution_plan": {"orders": []},
                "risk_gate": {"passed": True},
                "target_portfolio": {"positions": []},
                "current_positions": [],
                "order_sizing_report": [],
            },
        }
        supervisor_cycle = {
            "cycle_index": 1,
            "status": "cycle_live_delta_completed",
            "core_loop_artifact_root": str(core_loop_root),
            "core_loop_status": "mainnet_core_loop_completed",
            "orders_submitted": 0,
            "fill_count": 0,
            "live_delta_authorized": False,
            "core_loop_summary": {
                "artifact_root": str(core_loop_root),
                "status": "mainnet_core_loop_completed",
                "orders_submitted": 0,
                "fill_count": 0,
                "live_delta_authorized": False,
                "cycles": [inline_cycle],
            },
        }
        (supervisor_root / "cycle_001.json").write_text(
            json.dumps(supervisor_cycle, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        supervisor = {
            "run_id": "latest-supervisor-inline",
            "status": "mainnet_live_supervisor_completed",
            "artifact_root": str(supervisor_root),
            "orders_submitted": 0,
            "fill_count": 0,
            "live_delta_authorized": False,
            "target_engine": "multiphase_equal_sleeve",
            "cycles": [supervisor_cycle],
        }
        supervisor_summary = supervisor_root / "run_summary.json"
        supervisor_summary.write_text(json.dumps(supervisor, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        pre = self._control_snapshot()
        post = self._control_snapshot()
        pre_path = self.temp_dir / "pre-inline.json"
        post_path = self.temp_dir / "post-inline.json"
        pre_path.write_text(json.dumps(pre), encoding="utf-8")
        post_path.write_text(json.dumps(post), encoding="utf-8")
        return {"supervisor_summary": supervisor_summary, "pre": pre_path, "post": post_path}

    def _control_snapshot(self) -> dict:
        return {
            "remote_live_config_sha256": "same",
            "systemd": {"timers": {"supervisor.timer": "active"}, "services": {"supervisor.service": "inactive"}},
            "operator_state": [{"key": "live_delta_armed", "value": "true"}],
            "p9b_remote_mutation_observed": False,
        }

    def _plan_hash(self, root: Path) -> str:
        digest = hashlib.sha256()
        for name in sorted(PLAN_HASH_REQUIRED_FILES):
            path = root / name
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()


if __name__ == "__main__":
    unittest.main()
