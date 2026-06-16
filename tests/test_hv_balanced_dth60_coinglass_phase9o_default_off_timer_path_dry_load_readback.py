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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9o_default_off_timer_path_dry_load_readback import (  # noqa: E402
    APPROVE_P9O_DECISION,
    build_phase9o,
    file_sha256,
    resolve_path,
)


class HvBalancedDth60CoinglassPhase9oDefaultOffDryLoadReadbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9o-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9o_ready_executes_default_off_readback_only(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase9o"

        summary, exit_code = build_phase9o(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 7, 23, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["default_off_timer_path_dry_load_readback_ready"])
        self.assertTrue(summary["executed_default_off_timer_path_dry_load_readback"])
        self.assertEqual(summary["dry_load_mode"], "default_off_timer_path_readback_not_live_timer_service")
        self.assertTrue(summary["dry_load_outputs_under_proof_artifacts"])
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
        self.assertFalse(summary["eligible_for_live_timer_path_load"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["live_timer_path_loaded"])
        self.assertFalse(summary["live_timer_service_enabled_or_invoked"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = output_root / "proof_artifacts" / "p9o" / "20260607T230000Z"
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
        config = self._load_json(proof_root / "default_off_config_readback.json")
        self.assertFalse(config["hook_config_enabled"])
        self.assertEqual(config["execution_target_source"], "baseline_only")
        self.assertEqual(config["candidate_order_authority"], "disabled")
        self.assertFalse(config["candidate_live_order_submission_authorized"])
        executor = self._load_json(proof_root / "executor_input_readback.json")
        self.assertTrue(executor["executor_input_hash_equals_baseline"])
        self.assertFalse(executor["candidate_plan_referenced_by_executor"])

    def test_phase9o_blocks_wrong_owner_without_executing_readback(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "wrong-owner"

        summary, exit_code = build_phase9o(
            self._args(paths, output_root=output_root, owner_decision="approve_live_timer_path_load"),
            now_fn=lambda: datetime(2026, 6, 7, 23, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9o_execute_readback_only", summary["blockers"])
        self.assertFalse(summary["executed_default_off_timer_path_dry_load_readback"])
        self.assertFalse(summary["default_off_timer_path_dry_load_readback_ready"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        proof_root = output_root / "proof_artifacts" / "p9o" / "20260607T230500Z"
        self.assertFalse((proof_root / "input_plans" / "baseline_target_plan.json").exists())
        self.assertFalse((proof_root / "disabled_hook_readback_summary.json").exists())
        self.assertTrue((proof_root / "control_boundary_readback.json").exists())

    def test_phase9o_blocks_when_p9n_gate_allows_orders(self) -> None:
        paths = self._write_ready_inputs(
            p9n_gate_overrides={
                "allowed_next_action_constraints": {
                    "candidate_live_order_submission_authorized": True,
                    "orders_submitted_must_equal": 1,
                }
            }
        )

        summary, exit_code = build_phase9o(
            self._args(paths, output_root=self.temp_dir / "bad-p9n"),
            now_fn=lambda: datetime(2026, 6, 7, 23, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9n_dry_load_readback_owner_gate_ready", summary["blockers"])
        self.assertFalse(summary["executed_default_off_timer_path_dry_load_readback"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9o_blocks_when_current_supervisor_imports_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9o(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 7, 23, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["executed_default_off_timer_path_dry_load_readback"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9O_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9n_summary=str(paths["phase9n"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9n_overrides: dict | None = None,
        p9n_gate_overrides: dict | None = None,
        supervisor_text: str = "# no candidate hook import\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9n = self.temp_dir / "phase9n.json"
        gate_path = self.temp_dir / "proof_artifacts" / "p9n" / "gate.json"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        self._write_json(
            project_profile,
            {
                "current_stage": "stage_1_research_readiness_only",
                "target_stage": "stage_4_automated_execution",
            },
        )
        supervisor.write_text(supervisor_text, encoding="utf-8")
        supervisor_sha = file_sha256(supervisor)
        gate = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9n_dry_load_readback_execution_gate.v1",
            "run_id": "unit-test-p9n",
            "gate_scope": "owner_gated_default_off_timer_path_dry_load_readback_execution_permission_only",
            "allowed_next_action": "execute_default_off_timer_path_dry_load_readback",
            "allowed_next_gate": "P9O_default_off_timer_path_dry_load_readback_execution_only_if_separately_requested",
            "executed_in_p9n": False,
            "allowed_next_action_constraints": {
                "default_off_required": True,
                "proof_artifacts_only": True,
                "candidate_order_authority": "disabled",
                "candidate_live_order_submission_authorized": False,
                "executor_input_must_remain_baseline_only": True,
                "candidate_plan_must_not_be_referenced_by_executor": True,
                "target_plan_must_not_be_replaced": True,
                "must_not_modify_mainnet_live_supervisor": True,
                "must_not_modify_live_config": True,
                "must_not_modify_operator_state": True,
                "must_not_modify_timer_or_service_state": True,
                "must_not_enable_or_invoke_live_timer_service": True,
                "must_not_run_supervisor_for_execution": True,
                "must_not_remote_sync": True,
                "orders_submitted_must_equal": 0,
                "fill_count_must_equal": 0,
            },
            "owner_decision": {
                "decision": "approve_p9n_execute_default_off_timer_path_dry_load_readback_only",
                "future_default_off_timer_path_dry_load_readback_execution_approved": True,
                "execute_readback_in_p9n_approved": False,
                "timer_hook_implementation_approved": False,
                "hook_deployment_approved": False,
                "timer_path_load_approved": False,
                "live_order_submission_approved": False,
                "target_plan_replacement_approved": False,
                "executor_input_mutation_approved": False,
                "live_config_mutation_approved": False,
                "operator_state_mutation_approved": False,
                "timer_or_service_mutation_approved": False,
                "remote_sync_approved": False,
                "supervisor_run_approved": False,
                "repo_stage_change_approved": False,
            },
        }
        self._deep_update(gate, p9n_gate_overrides or {})
        self._write_json(gate_path, gate)
        p9n = {
            "status": "ready",
            "blockers": [],
            "gate_scope": "owner_gated_default_off_timer_path_dry_load_readback_execution_permission_only",
            "p9n_default_off_timer_path_dry_load_readback_owner_gate_ready": True,
            "eligible_to_execute_default_off_timer_path_dry_load_readback": True,
            "executed_default_off_timer_path_dry_load_readback": False,
            "allowed_next_gate": "P9O_default_off_timer_path_dry_load_readback_execution_only_if_separately_requested",
            "future_readback_default_off_required": True,
            "future_readback_artifact_sink_required": "proof_artifacts_only",
            "future_readback_executor_input_required": "baseline_only",
            "future_readback_candidate_order_authority_required": "disabled",
            "future_readback_live_order_submission_authorized_required": False,
            "future_readback_must_not_enable_live_timer_service": True,
            "future_readback_must_not_run_supervisor_for_execution": True,
            "eligible_for_timer_hook_implementation": False,
            "eligible_for_hook_deployment": False,
            "eligible_for_live_timer_path_load": False,
            "eligible_for_live_order_submission": False,
            "eligible_for_stage_governance_change": False,
            "timer_hook_implementation_authorized": False,
            "hook_deployment_authorized": False,
            "timer_path_load_authorized": False,
            "live_order_submission_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "remote_sync_authorized": False,
            "supervisor_run_authorized": False,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifact_sink": "proof_artifacts_only",
            "live_supervisor_loads_candidate_hook": False,
            "live_supervisor_source_unchanged": True,
            "live_timer_path_loaded": False,
            "live_timer_service_enabled_or_invoked": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "remote_execution_performed": False,
            "remote_control_plane_touched": False,
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "owner_decision": {
                "decision": "approve_p9n_execute_default_off_timer_path_dry_load_readback_only",
                "future_default_off_timer_path_dry_load_readback_execution_approved": True,
                "execute_readback_in_p9n_approved": False,
                "timer_hook_implementation_approved": False,
                "hook_deployment_approved": False,
                "timer_path_load_approved": False,
                "live_order_submission_approved": False,
                "target_plan_replacement_approved": False,
                "executor_input_mutation_approved": False,
                "live_config_mutation_approved": False,
                "operator_state_mutation_approved": False,
                "timer_or_service_mutation_approved": False,
                "remote_sync_approved": False,
                "supervisor_run_approved": False,
                "repo_stage_change_approved": False,
            },
            "source_evidence": {
                "hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha},
                "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
            },
            "output_files": {
                "dry_load_readback_execution_gate": str(gate_path),
            },
            "gates": {
                "owner_decision_p9n_dry_load_readback_gate_only": True,
                "project_stage_boundary_preserved": True,
                "p9m_default_off_timer_path_dry_load_proposal_ready": True,
                "p9m_proposal_body_ready": True,
                "current_live_supervisor_not_loading_hook": True,
                "current_hook_hash_matches_p9m_source": True,
                "current_supervisor_hash_matches_p9m_source": True,
                "dry_load_readback_gate_output_under_proof_artifacts": True,
                "future_readback_must_be_default_off": True,
                "future_readback_must_be_proof_artifacts_only": True,
                "future_readback_must_keep_order_authority_disabled": True,
                "future_readback_must_keep_executor_baseline_only": True,
                "future_readback_must_not_reference_candidate_plan_by_executor": True,
                "future_readback_must_not_replace_target_plan": True,
                "future_readback_must_not_enable_live_timer_service": True,
                "future_readback_must_not_run_supervisor_for_execution": True,
                "no_readback_execution_in_p9n": True,
                "no_timer_hook_implementation_in_p9n": True,
                "no_hook_deployment_in_p9n": True,
                "no_live_timer_path_load_in_p9n": True,
                "no_supervisor_run_in_p9n": True,
                "no_remote_execution_in_p9n": True,
                "no_executor_input_mutation_in_p9n": True,
                "no_target_plan_replacement_in_p9n": True,
                "no_live_mutation_in_p9n": True,
                "zero_orders_fills_in_p9n": True,
            },
        }
        self._deep_update(p9n, p9n_overrides or {})
        self._write_json(phase9n, p9n)
        return {
            "project_profile": project_profile,
            "phase9n": phase9n,
            "hook_module": hook_path,
            "supervisor": supervisor,
        }

    def _deep_update(self, target: dict, patch: dict) -> None:
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                self._deep_update(target[key], value)
            else:
                target[key] = value

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _load_json(self, path: Path) -> dict:
        with path.open(encoding="utf-8") as handle:
            return dict(json.load(handle))


if __name__ == "__main__":
    unittest.main()
