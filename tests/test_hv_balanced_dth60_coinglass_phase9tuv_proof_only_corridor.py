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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    P9T_GATE,
    P9U_GATE,
    P9V_GATE,
    build_corridor,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
    resolve_path,
)


class HvBalancedDth60CoinglassPhase9tuvProofOnlyCorridorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9tuv-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_corridor_runs_p9t_p9u_p9v_without_live_mutation(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_corridor(
            self._args(paths),
            now_fn=lambda: datetime(2026, 6, 8, 3, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["p9t_status"], "ready")
        self.assertEqual(summary["p9u_status"], "ready")
        self.assertEqual(summary["p9v_status"], "ready")
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["live_config_mutation_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        p9t = self._load_json(Path(summary["outputs"]["p9t_summary"]))
        p9u = self._load_json(Path(summary["outputs"]["p9u_summary"]))
        p9v = self._load_json(Path(summary["outputs"]["p9v_summary"]))
        self.assertTrue(p9t["proposal_preparation_authorized"])
        self.assertFalse(p9t["proposal_package_prepared_in_p9t"])
        self.assertEqual(p9t["allowed_next_gate"], P9U_GATE)
        self.assertTrue(p9u["proposal_review_package_ready"])
        self.assertFalse(p9u["execute_proposal_authorized"])
        self.assertEqual(p9u["allowed_next_gate"], P9V_GATE)
        self.assertTrue(p9v["p9v_dry_load_readiness_review_ready"])
        self.assertFalse(p9v["entered_timer_path"])
        self.assertFalse(p9v["dry_load_executed"])
        self.assertFalse(p9v["executor_input_mutated"])
        self.assertFalse(p9v["live_config_mutated"])
        self.assertTrue(p9v["live_config_dir_unchanged"])

        package = self._load_json(Path(p9u["output_files"]["proposal_review_package"]))
        self.assertEqual(package["proposal_mode"], "default_off_observe_only_shadow_hook_load_path")
        self.assertTrue(package["proposal_written_under_proof_artifacts"])
        self.assertFalse(package["proposal_executes_anything"])
        review = self._load_json(Path(p9v["output_files"]["dry_load_readiness_review"]))
        self.assertEqual(review["review_mode"], "local_retained_evidence_readiness_review_not_timer_path")
        self.assertFalse(review["entered_timer_path"])
        self.assertFalse(review["executor_input_mutated"])
        self.assertFalse(review["live_config_mutated"])

    def test_corridor_blocks_when_p9s_authorizes_timer_path(self) -> None:
        paths = self._write_ready_inputs(
            p9s_overrides={
                "timer_path_load_authorized": True,
                "gates": {
                    "no_live_timer_path_load_in_p9s": False,
                },
            },
            matrix_overrides={
                "authorizations": {
                    "live_timer_path_load": True,
                }
            },
        )

        summary, exit_code = build_corridor(
            self._args(paths),
            now_fn=lambda: datetime(2026, 6, 8, 3, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["p9t_status"], "blocked")
        self.assertEqual(summary["p9u_status"], "skipped")
        self.assertIn("p9s_scope_definition_ready", summary["blockers"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_corridor_blocks_when_current_supervisor_loads_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_corridor(
            self._args(paths),
            now_fn=lambda: datetime(2026, 6, 8, 3, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["p9t_status"], "blocked")
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(self, paths: dict[str, Path]) -> Namespace:
        return Namespace(
            project_profile=str(paths["project_profile"]),
            phase9s_summary=str(paths["phase9s"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            output_root=str(self.temp_dir / "corridor" / "summary-root"),
            artifacts_root=str(self.temp_dir / "corridor_artifacts"),
            owner="rulebook_owner",
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9s_overrides: dict | None = None,
        matrix_overrides: dict | None = None,
        scope_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9s = self.temp_dir / "phase9s" / "summary.json"
        scope_path = self.temp_dir / "phase9s" / "proof_artifacts" / "p9s" / "run" / (
            "next_gate_scope_definition.json"
        )
        matrix_path = self.temp_dir / "phase9s" / "proof_artifacts" / "p9s" / "run" / "non_authorization_matrix.json"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        live_config_dir.mkdir(parents=True)
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")
        supervisor_sha = file_sha256(supervisor)
        self._write_json(
            project_profile,
            {
                "current_stage": "stage_1_research_readiness_only",
                "target_stage": "stage_4_automated_execution",
            },
        )
        scope = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9s_next_gate_scope_definition.v1",
            "run_id": "unit-test-p9s",
            "defined_next_gate": (
                "P9T_owner_gate_prepare_default_off_live_supervisor_shadow_hook_load_proposal_only_if_separately_requested"
            ),
            "defined_next_gate_must_be_separately_requested": True,
            "defined_next_gate_executes_in_p9s": False,
            "defined_next_gate_authorized_in_p9s": False,
            "defined_next_gate_required_boundaries": {
                "proof_artifacts_only": True,
                "default_off_only": True,
                "executor_input_must_remain_baseline_only": True,
                "target_plan_must_not_be_replaced": True,
                "candidate_plan_must_not_be_referenced_by_executor": True,
                "candidate_order_authority": "disabled",
                "orders_submitted_must_equal": 0,
                "fill_count_must_equal": 0,
            },
            "defined_next_gate_disallowed_actions": {
                "implement_hook": True,
                "deploy_hook": True,
                "load_live_timer_path": True,
                "run_supervisor": True,
                "invoke_timer_or_service": True,
                "mutate_executor_input": True,
                "replace_target_plan": True,
                "mutate_live_config": True,
                "mutate_operator_state": True,
                "mutate_timer_or_service_state": True,
                "remote_sync": True,
                "stage_governance_change": True,
                "submit_orders": True,
            },
        }
        self._deep_update(scope, scope_overrides or {})
        self._write_json(scope_path, scope)
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9s_non_authorization_matrix.v1",
            "run_id": "unit-test-p9s",
            "authorizations": {
                "define_next_gate_scope": True,
                "execute_defined_next_gate": False,
                "prepare_proposal": False,
                "timer_hook_implementation": False,
                "hook_deployment": False,
                "live_timer_path_load": False,
                "live_order_submission": False,
                "target_plan_replacement": False,
                "executor_input_mutation": False,
                "live_config_mutation": False,
                "operator_state_mutation": False,
                "timer_or_service_mutation": False,
                "remote_sync": False,
                "supervisor_run": False,
                "stage_governance_change": False,
            },
        }
        self._deep_update(matrix, matrix_overrides or {})
        self._write_json(matrix_path, matrix)
        gates = {
            "owner_decision_p9s_define_scope_only": True,
            "project_stage_boundary_preserved": True,
            "p9q_owner_gate_ready": True,
            "p9q_allows_p9s_scope_definition": True,
            "p9q_did_not_define_scope": True,
            "p9q_did_not_execute_next_gate": True,
            "current_live_supervisor_not_loading_hook": True,
            "current_hook_hash_matches_p9q_source": True,
            "current_supervisor_hash_matches_p9q_source": True,
            "next_gate_scope_definition_output_under_proof_artifacts": True,
            "p9s_defines_scope_only": True,
            "p9s_does_not_execute_defined_next_gate": True,
            "p9s_does_not_prepare_proposal": True,
            "p9s_requires_defined_gate_to_be_separately_requested": True,
            "defined_gate_must_be_proof_artifacts_only": True,
            "defined_gate_must_keep_order_authority_disabled": True,
            "defined_gate_must_not_authorize_live_order_submission": True,
            "defined_gate_must_not_load_live_timer_path": True,
            "defined_gate_must_not_mutate_executor_input": True,
            "defined_gate_must_not_replace_target_plan": True,
            "defined_gate_must_not_remote_sync": True,
            "no_timer_hook_implementation_in_p9s": True,
            "no_hook_deployment_in_p9s": True,
            "no_live_timer_path_load_in_p9s": True,
            "no_supervisor_run_in_p9s": True,
            "no_remote_execution_in_p9s": True,
            "no_executor_input_mutation_in_p9s": True,
            "no_target_plan_replacement_in_p9s": True,
            "no_live_mutation_in_p9s": True,
            "zero_orders_fills_in_p9s": True,
        }
        p9s = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9s_define_next_gate_scope.v1",
            "status": "ready",
            "blockers": [],
            "p9s_next_gate_scope_definition_ready": True,
            "next_gate_scope_defined": True,
            "defined_next_gate": P9T_GATE + "_if_separately_requested",
            "defined_next_gate_authorized_in_p9s": False,
            "defined_next_gate_execution_authorized": False,
            "prepare_proposal_authorized": False,
            "defined_next_gate_must_be_separately_requested": True,
            "defined_next_gate_must_be_proof_artifacts_only": True,
            "defined_next_gate_must_keep_order_authority_disabled": True,
            "defined_next_gate_must_not_authorize_live_order_submission": True,
            "defined_next_gate_must_not_load_live_timer_path": True,
            "timer_path_load_authorized": False,
            "live_order_submission_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "remote_sync_authorized": False,
            "supervisor_run_authorized": False,
            "execution_target_source": "baseline_only",
            "candidate_artifact_sink": "proof_artifacts_only",
            "live_supervisor_loads_candidate_hook": False,
            "live_supervisor_source_unchanged": True,
            "live_timer_path_loaded": False,
            "live_timer_service_enabled_or_invoked": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "remote_execution_performed": False,
            "remote_control_plane_touched": False,
            "wrote_live_hook_config": False,
            "implemented_hook": False,
            "deployed_hook": False,
            "loaded_hook": False,
            "target_plan_replaced": False,
            "executor_input_changed": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "owner_decision": {
                "decision": "approve_p9s_define_next_gate_scope_only",
                "define_next_gate_scope_approved": True,
                "execute_defined_next_gate_approved": False,
                "prepare_proposal_approved": False,
                "timer_hook_implementation_approved": False,
                "hook_deployment_approved": False,
                "live_timer_path_load_approved": False,
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
            "gates": gates,
            "output_files": {
                "next_gate_scope_definition": str(scope_path),
                "non_authorization_matrix": str(matrix_path),
            },
        }
        self._deep_update(p9s, p9s_overrides or {})
        self._write_json(phase9s, p9s)
        return {
            "project_profile": project_profile,
            "phase9s": phase9s,
            "hook_module": hook_path,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }

    @staticmethod
    def _deep_update(target: dict, updates: dict) -> None:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                HvBalancedDth60CoinglassPhase9tuvProofOnlyCorridorTests._deep_update(target[key], value)
            else:
                target[key] = value

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _load_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
