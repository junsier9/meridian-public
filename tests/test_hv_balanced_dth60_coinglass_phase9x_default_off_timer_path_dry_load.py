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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
    resolve_path,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9w_default_off_timer_path_dry_load_owner_gate import (  # noqa: E402
    P9X_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9x_default_off_timer_path_dry_load import (  # noqa: E402
    APPROVE_P9X_DECISION,
    build_phase9x,
)


class HvBalancedDth60CoinglassPhase9xDefaultOffTimerPathDryLoadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9x-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9x_ready_executes_default_off_dry_load_only(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9x(
            self._args(paths, output_root=self.temp_dir / "p9x"),
            now_fn=lambda: datetime(2026, 6, 8, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["owner_decision"]["decision"], APPROVE_P9X_DECISION)
        self.assertTrue(summary["owner_decision"]["default_off_timer_path_dry_load_execution_approved"])
        self.assertTrue(summary["default_off_timer_path_dry_load_ready"])
        self.assertTrue(summary["default_off_timer_path_dry_load_executed"])
        self.assertTrue(summary["entered_timer_path_dry_load_harness"])
        self.assertFalse(summary["entered_live_timer_path"])
        self.assertFalse(summary["candidate_execution_enabled"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_timer_path_loaded"])
        self.assertFalse(summary["live_timer_service_enabled_or_invoked"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertTrue(summary["default_off_config_loaded"])
        self.assertFalse(summary["default_off_hook_enabled"])
        self.assertTrue(summary["disabled_hook_readback_ready"])
        self.assertEqual(summary["disabled_hook_candidate_artifacts_written_count"], 0)
        self.assertTrue(summary["baseline_target_plan_byte_for_byte_unchanged"])
        self.assertTrue(summary["executor_input_hash_unchanged"])
        self.assertTrue(summary["executor_input_hash_equals_baseline"])
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertTrue(summary["candidate_shadow_hash_differs_from_executor"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = self.temp_dir / "p9x" / "proof_artifacts" / "p9x" / "20260608T050000Z"
        for name in (
            "dry_load_execution_manifest.json",
            "default_off_config_readback.json",
            "disabled_hook_readback_summary.json",
            "executor_input_readback.json",
            "control_boundary_readback.json",
            "input_plans/baseline_target_plan.json",
            "input_plans/executor_input_target_plan.json",
            "input_plans/candidate_shadow_plan.json",
        ):
            self.assertTrue((proof_root / name).exists(), name)
        manifest = self._load_json(proof_root / "dry_load_execution_manifest.json")
        self.assertTrue(manifest["default_off_timer_path_dry_load_executed"])
        self.assertTrue(manifest["entered_timer_path_dry_load_harness"])
        self.assertFalse(manifest["entered_live_timer_path"])
        config = self._load_json(proof_root / "default_off_config_readback.json")
        self.assertFalse(config["hook_config_enabled"])
        self.assertFalse(config["candidate_execution_enabled"])
        self.assertEqual(config["execution_target_source"], "baseline_only")
        executor = self._load_json(proof_root / "executor_input_readback.json")
        self.assertTrue(executor["executor_input_hash_equals_baseline"])
        self.assertFalse(executor["candidate_plan_referenced_by_executor"])

    def test_phase9x_blocks_wrong_owner_without_dry_load(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9x(
            self._args(paths, output_root=self.temp_dir / "wrong-owner", owner_decision="approve_candidate_execution"),
            now_fn=lambda: datetime(2026, 6, 8, 5, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9x_execute_default_off_dry_load_only", summary["blockers"])
        self.assertFalse(summary["default_off_timer_path_dry_load_executed"])
        self.assertFalse(summary["entered_timer_path_dry_load_harness"])
        self.assertFalse(summary["candidate_execution_enabled"])
        self.assertFalse(summary["live_order_submission_authorized"])
        proof_root = self.temp_dir / "wrong-owner" / "proof_artifacts" / "p9x" / "20260608T050500Z"
        self.assertFalse((proof_root / "input_plans" / "baseline_target_plan.json").exists())
        self.assertTrue((proof_root / "control_boundary_readback.json").exists())

    def test_phase9x_blocks_when_p9w_does_not_allow_future_p9x(self) -> None:
        paths = self._write_ready_inputs(
            p9w_summary_overrides={
                "eligible_for_future_p9x_execution_gate": False,
                "allowed_next_gate": "P9Y_not_p9x",
            },
            p9w_gate_overrides={
                "eligible_for_future_p9x_execution_gate": False,
                "allowed_next_gate": "P9Y_not_p9x",
            },
            p9w_matrix_overrides={
                "authorizations": {
                    "future_p9x_execution_gate_request": False,
                    "candidate_execution": True,
                }
            },
        )

        summary, exit_code = build_phase9x(
            self._args(paths, output_root=self.temp_dir / "bad-p9w"),
            now_fn=lambda: datetime(2026, 6, 8, 5, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9w_owner_gate_ready", summary["blockers"])
        self.assertIn("p9w_allows_future_p9x_gate_request", summary["blockers"])
        self.assertFalse(summary["default_off_timer_path_dry_load_executed"])
        self.assertFalse(summary["candidate_execution_enabled"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9x_blocks_when_current_supervisor_loads_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9x(
            self._args(paths, output_root=self.temp_dir / "supervisor-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 5, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["source_evidence"]["live_supervisor"]["exists"])
        self.assertFalse(summary["default_off_timer_path_dry_load_executed"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9X_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9w_summary=str(paths["phase9w"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9w_summary_overrides: dict | None = None,
        p9w_gate_overrides: dict | None = None,
        p9w_matrix_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9w = self.temp_dir / "phase9w" / "summary.json"
        proof_root = self.temp_dir / "phase9w" / "proof_artifacts" / "p9w" / "run"
        gate_path = proof_root / "dry_load_execution_owner_gate.json"
        matrix_path = proof_root / "non_authorization_matrix.json"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        live_config_dir.mkdir(parents=True)
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")
        supervisor_sha = file_sha256(supervisor)
        live_config_sha = tree_sha256(live_config_dir)
        self._write_json(
            project_profile,
            {
                "current_stage": "stage_1_research_readiness_only",
                "target_stage": "stage_4_automated_execution",
            },
        )
        source_evidence = {
            "hook_module": {"exists": True, "path": str(hook_path), "sha256": hook_sha},
            "live_supervisor": {"exists": True, "path": str(supervisor), "sha256": supervisor_sha},
            "live_config_dir": {"exists": True, "path": str(live_config_dir), "sha256": live_config_sha},
        }
        p9w_summary = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9w_default_off_timer_path_dry_load_owner_gate.v1",
            "status": "ready",
            "blockers": [],
            "p9w_owner_gate_ready": True,
            "eligible_for_future_p9x_execution_gate": True,
            "allowed_next_gate": P9X_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "default_off_timer_path_dry_load_execution_authorized": False,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
            "timer_path_load_authorized": False,
            "executor_input_mutation_authorized": False,
            "target_plan_replacement_authorized": False,
            "live_config_mutation_authorized": False,
            "remote_sync_authorized": False,
            "supervisor_run_authorized": False,
            "entered_timer_path": False,
            "dry_load_executed": False,
            "candidate_execution_enabled": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "source_evidence": source_evidence,
            "output_files": {
                "dry_load_execution_owner_gate": str(gate_path),
                "non_authorization_matrix": str(matrix_path),
            },
        }
        p9w_gate = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9w_execution_discussion_owner_gate.v1",
            "gate_status": "ready",
            "eligible_for_future_p9x_execution_gate": True,
            "allowed_next_gate": P9X_GATE,
            "default_off_timer_path_dry_load_execution_authorized_in_p9w": False,
            "candidate_execution_authorized_in_p9w": False,
            "live_order_submission_authorized_in_p9w": False,
            "required_future_boundaries": {
                "default_off_required": True,
                "proof_artifacts_only": True,
                "baseline_only_executor_input": True,
                "candidate_execution_forbidden": True,
                "live_order_submission_forbidden": True,
                "target_plan_replacement_forbidden": True,
                "executor_input_mutation_forbidden": True,
                "live_config_mutation_forbidden": True,
                "remote_sync_forbidden": True,
                "supervisor_execution_forbidden": True,
                "timer_service_enable_or_invoke_forbidden": True,
                "orders_submitted_must_equal": 0,
                "fill_count_must_equal": 0,
            },
        }
        p9w_matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9w_non_authorization_matrix.v1",
            "authorizations": {
                "future_p9x_execution_gate_request": True,
                "execute_default_off_timer_path_dry_load_in_p9w": False,
                "candidate_execution": False,
                "live_order_submission": False,
                "live_timer_path_load": False,
                "executor_input_mutation": False,
                "live_config_mutation": False,
                "remote_sync": False,
                "supervisor_run": False,
            },
        }
        self._deep_update(p9w_summary, p9w_summary_overrides or {})
        self._deep_update(p9w_gate, p9w_gate_overrides or {})
        self._deep_update(p9w_matrix, p9w_matrix_overrides or {})
        self._write_json(phase9w, p9w_summary)
        self._write_json(gate_path, p9w_gate)
        self._write_json(matrix_path, p9w_matrix)
        return {
            "project_profile": project_profile,
            "phase9w": phase9w,
            "hook_module": hook_path,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }

    def _deep_update(self, base: dict, override: dict) -> None:
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _load_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
