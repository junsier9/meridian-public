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
    APPROVE_P9Q_DECISION,
    build_phase9q,
    file_sha256,
    resolve_path,
)


class HvBalancedDth60CoinglassPhase9qDefineNextGateScopeOwnerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9q-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9q_ready_allows_only_future_scope_definition(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase9q"

        summary, exit_code = build_phase9q(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 1, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["gate_scope"], "owner_gated_allow_future_next_gate_scope_definition_only")
        self.assertEqual(summary["owner_decision"]["decision"], APPROVE_P9Q_DECISION)
        self.assertTrue(summary["p9q_define_next_gate_scope_owner_gate_ready"])
        self.assertTrue(summary["eligible_to_define_next_gate_scope"])
        self.assertFalse(summary["defined_next_gate_scope"])
        self.assertFalse(summary["next_gate_scope_definition_in_p9q_authorized"])
        self.assertFalse(summary["next_gate_execution_authorized"])
        self.assertEqual(summary["allowed_next_gate"], "P9S_define_next_gate_scope_only_if_separately_requested")
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = output_root / "proof_artifacts" / "p9q" / "20260608T010000Z"
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        self.assertTrue((proof_root / "next_gate_scope_definition_gate.json").exists())
        self.assertTrue((proof_root / "non_authorization_matrix.json").exists())
        self.assertTrue((proof_root / "control_boundary_readback.json").exists())
        gate = self._load_json(proof_root / "next_gate_scope_definition_gate.json")
        self.assertEqual(gate["allowed_next_gate"], "P9S_define_next_gate_scope_only_if_separately_requested")
        self.assertFalse(gate["defined_in_p9q"])
        self.assertFalse(gate["executed_in_p9q"])
        matrix = self._load_json(proof_root / "non_authorization_matrix.json")
        self.assertTrue(matrix["authorizations"]["future_next_gate_scope_definition"])
        self.assertFalse(matrix["authorizations"]["define_next_gate_scope_in_p9q"])
        self.assertFalse(matrix["authorizations"]["execute_next_gate"])
        self.assertFalse(matrix["authorizations"]["live_timer_path_load"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])

    def test_phase9q_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9q(
            self._args(paths, output_root=self.temp_dir / "wrong-owner", owner_decision="approve_timer_path_load"),
            now_fn=lambda: datetime(2026, 6, 8, 1, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9q_define_scope_only", summary["blockers"])
        self.assertFalse(summary["eligible_to_define_next_gate_scope"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9q_blocks_when_p9p_authorizes_next_gate_execution(self) -> None:
        paths = self._write_ready_inputs(
            p9p_overrides={
                "next_owner_gate_execution_authorized": True,
                "gates": {
                    "no_timer_path_load_in_p9p": False,
                },
            },
            matrix_overrides={
                "authorizations": {
                    "execute_next_owner_gate": True,
                    "timer_path_load": True,
                }
            },
        )

        summary, exit_code = build_phase9q(
            self._args(paths, output_root=self.temp_dir / "bad-p9p"),
            now_fn=lambda: datetime(2026, 6, 8, 1, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9p_owner_review_ready", summary["blockers"])
        self.assertIn("p9p_next_gate_execution_not_authorized", summary["blockers"])
        self.assertFalse(summary["eligible_to_define_next_gate_scope"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9q_blocks_when_current_supervisor_loads_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9q(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 1, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9p_owner_review_ready", summary["blockers"])
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9Q_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9p_summary=str(paths["phase9p"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9p_overrides: dict | None = None,
        matrix_overrides: dict | None = None,
        supervisor_text: str = "# no candidate hook import\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9p = self.temp_dir / "phase9p" / "summary.json"
        matrix_path = self.temp_dir / "phase9p" / "proof_artifacts" / "p9p" / "run" / "review_decision_matrix.json"
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
        base_no_order = {
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        base_no_mutation = {
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
        }
        gates = {
            "owner_decision_p9p_review_only": True,
            "stage_boundary_preserved": True,
            "p9o_summary_ready": True,
            "p9o_default_off_readback_executed": True,
            "p9o_readback_default_off": True,
            "p9o_readback_not_live_timer_service": True,
            "proof_files_exist": True,
            "proof_files_under_proof_artifacts": True,
            "dry_load_manifest_ready": True,
            "default_off_config_readback_ready": True,
            "disabled_hook_readback_summary_ready": True,
            "executor_input_readback_ready": True,
            "control_boundary_readback_ready": True,
            "baseline_executor_input_hash_unchanged": True,
            "executor_consumes_baseline_only": True,
            "candidate_plan_not_referenced_by_executor": True,
            "target_plan_not_replaced": True,
            "live_supervisor_not_loading_hook": True,
            "live_timer_path_not_loaded": True,
            "supervisor_not_run": True,
            "remote_not_touched": True,
            "zero_orders_fills": True,
            "no_live_mutation": True,
            "review_output_under_proof_artifacts": True,
            "no_timer_hook_implementation_in_p9p": True,
            "no_hook_deployment_in_p9p": True,
            "no_timer_path_load_in_p9p": True,
            "no_supervisor_run_in_p9p": True,
            "no_remote_execution_in_p9p": True,
            "no_executor_input_mutation_in_p9p": True,
            "no_target_plan_replacement_in_p9p": True,
            "no_live_mutation_in_p9p": True,
            "zero_orders_fills_in_p9p": True,
        }
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9p_review_decision_matrix.v1",
            "run_id": "unit-test-p9p",
            "authorizations": {
                "p9p_review_default_off_readback_sufficiency": True,
                "enter_separate_next_owner_gate_discussion": True,
                "execute_next_owner_gate": False,
                "timer_hook_implementation": False,
                "hook_deployment": False,
                "timer_path_load": False,
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
        p9p = {
            **base_no_order,
            **base_no_mutation,
            "contract_version": "hv_balanced_dth60_coinglass_phase9p_owner_review_after_default_off_readback.v1",
            "status": "ready",
            "blockers": [],
            "review_scope": "owner_gated_p9o_default_off_readback_sufficiency_review_only",
            "p9o_default_off_readback_sufficient_for_next_owner_gate": True,
            "eligible_for_next_owner_gate_discussion": True,
            "next_owner_gate_execution_authorized": False,
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
            "default_off_readback_executed": True,
            "default_off_readback_proof_files_ready": True,
            "default_off_readback_not_live_timer_service": True,
            "baseline_executor_input_hash_unchanged": True,
            "executor_consumes_baseline_only": True,
            "candidate_plan_referenced_by_executor": False,
            "target_plan_replaced": False,
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
            "executor_input_changed": False,
            "owner_decision": {
                "decision": "approve_p9p_review_default_off_readback_sufficiency_only",
                "review_default_off_readback_sufficiency_approved": True,
                "next_owner_gate_execution_approved": False,
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
                "review_decision_matrix": str(matrix_path),
            },
        }
        self._deep_update(p9p, p9p_overrides or {})
        self._write_json(phase9p, p9p)
        return {
            "project_profile": project_profile,
            "phase9p": phase9p,
            "hook_module": hook_path,
            "supervisor": supervisor,
        }

    @staticmethod
    def _deep_update(target: dict, updates: dict) -> None:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                HvBalancedDth60CoinglassPhase9qDefineNextGateScopeOwnerGateTests._deep_update(target[key], value)
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
