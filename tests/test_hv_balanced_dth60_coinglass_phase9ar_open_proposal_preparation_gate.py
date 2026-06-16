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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9aq_allow_open_proposal_preparation_gate import (  # noqa: E402
    APPROVE_P9AQ_DECISION,
    P9AR_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ar_open_proposal_preparation_gate import (  # noqa: E402
    APPROVE_P9AR_DECISION,
    P9AS_GATE,
    build_phase9ar,
    p9aq_ready_for_p9ar,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
    resolve_path,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9AROpenProposalPreparationGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9ar-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9ar_ready_opens_only_future_proposal_package_request_gate(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "p9ar-ready"

        summary, exit_code = build_phase9ar(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 11, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9ar_open_proposal_preparation_gate_ready"])
        self.assertTrue(summary["proposal_preparation_gate_opened"])
        self.assertTrue(summary["eligible_for_future_proposal_package_preparation_request"])
        self.assertEqual(summary["allowed_next_gate"], P9AS_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertTrue(summary["open_proposal_preparation_gate_authorized"])
        self.assertFalse(summary["proposal_preparation_action_authorized"])
        self.assertFalse(summary["prepare_proposal_authorized"])
        self.assertFalse(summary["proposal_package_generation_authorized"])
        self.assertFalse(summary["proposal_body_write_authorized"])
        self.assertFalse(summary["dry_load_readback_execution_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = output_root / "proof_artifacts" / "p9ar" / "20260608T110000Z"
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        self.assertTrue((proof_root / "proposal_preparation_gate_opening.json").exists())
        self.assertTrue((proof_root / "non_authorization_matrix.json").exists())
        self.assertTrue((proof_root / "control_boundary_readback.json").exists())
        opening = self._load_json(proof_root / "proposal_preparation_gate_opening.json")
        self.assertTrue(opening["proposal_preparation_gate_opened"])
        self.assertEqual(opening["allowed_next_gate"], P9AS_GATE)
        self.assertFalse(opening["prepare_proposal_in_p9ar"])
        self.assertFalse(opening["proposal_package_generated_in_p9ar"])
        self.assertFalse(opening["proposal_body_written_in_p9ar"])
        self.assertFalse(opening["dry_load_readback_executed_in_p9ar"])
        matrix = self._load_json(proof_root / "non_authorization_matrix.json")
        self.assertTrue(matrix["authorizations"]["open_proposal_preparation_gate"])
        self.assertTrue(matrix["authorizations"]["future_proposal_package_preparation_request"])
        self.assertFalse(matrix["authorizations"]["prepare_proposal"])
        self.assertFalse(matrix["authorizations"]["proposal_package_generation"])
        self.assertFalse(matrix["authorizations"]["proposal_body_write"])
        self.assertFalse(matrix["authorizations"]["dry_load_readback_execution"])
        self.assertFalse(matrix["authorizations"]["live_timer_path_load"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])

    def test_phase9ar_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9ar(
            self._args(paths, output_root=self.temp_dir / "wrong-owner", owner_decision="approve_live_orders"),
            now_fn=lambda: datetime(2026, 6, 8, 11, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9ar_open_gate_only", summary["blockers"])
        self.assertFalse(summary["proposal_preparation_gate_opened"])
        self.assertFalse(summary["eligible_for_future_proposal_package_preparation_request"])
        self.assertFalse(summary["prepare_proposal_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9ar_blocks_when_p9aq_already_opened_or_authorized_preparation(self) -> None:
        paths = self._write_ready_inputs(
            p9aq_overrides={
                "opened_proposal_preparation_gate": True,
                "prepare_proposal_authorized": True,
                "gates": {
                    "p9aq_does_not_open_p9ar": False,
                    "p9aq_does_not_prepare_proposal": False,
                },
            },
            permission_overrides={"opened_in_p9aq": True},
            matrix_overrides={
                "authorizations": {
                    "open_proposal_preparation_gate_in_p9aq": True,
                    "prepare_proposal": True,
                }
            },
        )
        p9aq = self._load_json(paths["phase9aq"])
        permission = self._load_json(paths["permission"])
        matrix = self._load_json(paths["matrix"])
        self.assertFalse(
            p9aq_ready_for_p9ar(
                p9aq,
                permission,
                matrix,
                current_hook_sha256=file_sha256(paths["hook_module"]),
                current_supervisor_sha256=file_sha256(paths["supervisor"]),
                current_live_config_sha256=tree_sha256(paths["live_config_dir"]),
                current_supervisor_loads_candidate_hook=False,
            )
        )

        summary, exit_code = build_phase9ar(
            self._args(paths, output_root=self.temp_dir / "bad-p9aq"),
            now_fn=lambda: datetime(2026, 6, 8, 11, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9aq_permission_gate_ready", summary["blockers"])
        self.assertIn("p9aq_did_not_open_gate", summary["blockers"])
        self.assertIn("p9aq_did_not_prepare_proposal", summary["blockers"])
        self.assertFalse(summary["proposal_preparation_gate_opened"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9ar_blocks_when_current_supervisor_loads_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9ar(
            self._args(paths, output_root=self.temp_dir / "supervisor-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 11, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9aq_permission_gate_ready", summary["blockers"])
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9AR_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9aq_summary=str(paths["phase9aq"]),
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
        p9aq_overrides: dict | None = None,
        permission_overrides: dict | None = None,
        matrix_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9aq = self.temp_dir / "p9aq" / "summary.json"
        proof_root = self.temp_dir / "p9aq" / "proof_artifacts" / "p9aq" / "run"
        permission_path = proof_root / "proposal_preparation_gate_permission.json"
        matrix_path = proof_root / "non_authorization_matrix.json"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        live_config_dir.mkdir(parents=True)
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")
        supervisor_sha = file_sha256(supervisor)
        live_config_sha = tree_sha256(live_config_dir)

        self._write_json(project_profile, {"current_stage": "stage_1_research_readiness_only"})
        permission = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9aq_proposal_preparation_gate_permission.v1",
            "run_id": "unit-test-p9aq",
            "owner_decision": {"decision": APPROVE_P9AQ_DECISION},
            "allowed_next_gate": P9AR_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "opened_in_p9aq": False,
            "executed_in_p9aq": False,
            "p9ar_required_boundaries": {
                "owner_gated": True,
                "proof_artifacts_only": True,
                "default_off_only": True,
                "observe_only_shadow_artifacts_only": True,
                "executor_input_must_remain_baseline_only": True,
                "candidate_order_authority": "disabled",
                "live_order_submission_authorized": False,
                "orders_submitted_must_equal": 0,
                "fill_count_must_equal": 0,
            },
            "p9ar_disallowed_actions": {
                "execute_p9ar_inside_p9aq": True,
                "prepare_proposal_inside_p9aq": True,
                "write_proposal_body_inside_p9aq": True,
                "execute_dry_load_readback": True,
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
                "remote_execution": True,
                "stage_governance_change": True,
                "submit_orders": True,
            },
        }
        self._deep_update(permission, permission_overrides or {})
        self._write_json(permission_path, permission)
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9aq_non_authorization_matrix.v1",
            "run_id": "unit-test-p9aq",
            "authorizations": {
                "future_proposal_preparation_gate_request": True,
                "open_proposal_preparation_gate_in_p9aq": False,
                "execute_p9ar": False,
                "prepare_proposal": False,
                "proposal_body_write": False,
                "dry_load_readback_execution": False,
                "candidate_execution": False,
                "candidate_live_order_submission": False,
                "timer_hook_implementation": False,
                "hook_deployment": False,
                "live_timer_path_load": False,
                "production_timer_service_load": False,
                "live_order_submission": False,
                "target_plan_replacement": False,
                "executor_input_mutation": False,
                "live_config_mutation": False,
                "operator_state_mutation": False,
                "timer_or_service_mutation": False,
                "remote_sync": False,
                "remote_execution": False,
                "supervisor_invocation": False,
                "supervisor_run": False,
                "stage_governance_change": False,
            },
        }
        self._deep_update(matrix, matrix_overrides or {})
        self._write_json(matrix_path, matrix)
        gates = {
            "owner_decision_p9aq_allow_open_proposal_preparation_gate_only": True,
            "project_stage_boundary_preserved": True,
            "p9ap_scope_definition_ready": True,
            "p9ap_defined_p9aq_only": True,
            "p9ap_did_not_authorize_p9aq_execution": True,
            "p9ap_did_not_prepare_proposal": True,
            "p9ap_did_not_write_proposal_body": True,
            "p9ap_did_not_execute_readback": True,
            "current_live_supervisor_not_loading_hook": True,
            "current_hook_hash_matches_p9ap_source": True,
            "current_supervisor_hash_matches_p9ap_source": True,
            "current_live_config_hash_matches_p9ap_source": True,
            "permission_gate_output_under_proof_artifacts": True,
            "p9aq_discusses_opening_only": True,
            "p9aq_does_not_open_p9ar": True,
            "p9aq_does_not_execute_p9ar": True,
            "p9aq_does_not_prepare_proposal": True,
            "p9aq_does_not_write_proposal_body": True,
            "p9aq_does_not_execute_dry_load_readback": True,
            "p9ar_must_be_separately_requested": True,
            "p9ar_must_be_proof_artifacts_only": True,
            "p9ar_must_keep_default_off": True,
            "p9ar_must_keep_observe_only": True,
            "p9ar_must_keep_order_authority_disabled": True,
            "no_timer_hook_implementation_in_p9aq": True,
            "no_hook_deployment_in_p9aq": True,
            "no_live_timer_path_load_in_p9aq": True,
            "no_production_timer_service_load_in_p9aq": True,
            "no_supervisor_run_in_p9aq": True,
            "no_remote_execution_in_p9aq": True,
            "no_candidate_execution_in_p9aq": True,
            "no_executor_input_mutation_in_p9aq": True,
            "no_target_plan_replacement_in_p9aq": True,
            "no_live_mutation_in_p9aq": True,
            "zero_orders_fills_in_p9aq": True,
        }
        no_order = {
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        no_live = {
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
        }
        p9aq = {
            **no_order,
            **no_live,
            "contract_version": "hv_balanced_dth60_coinglass_phase9aq_allow_open_proposal_preparation_gate.v1",
            "status": "ready",
            "blockers": [],
            "p9aq_allow_open_proposal_preparation_gate_ready": True,
            "eligible_for_future_proposal_preparation_gate_request": True,
            "allowed_next_gate": P9AR_GATE,
            "recommended_next_gate": P9AR_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifact_sink": "proof_artifacts_only",
            "live_supervisor_source_unchanged": True,
            "live_config_dir_unchanged": True,
            "owner_decision": {
                "decision": APPROVE_P9AQ_DECISION,
                "future_proposal_preparation_gate_request_approved": True,
                "open_proposal_preparation_gate_in_p9aq_approved": False,
                "execute_p9ar_approved": False,
                "prepare_proposal_approved": False,
                "proposal_body_write_approved": False,
                "dry_load_readback_execution_approved": False,
            },
            "source_evidence": {
                "hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha},
                "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
                "live_config_dir": {"path": str(live_config_dir), "exists": True, "sha256": live_config_sha},
            },
            "gates": gates,
            "output_files": {
                "proposal_preparation_gate_permission": str(permission_path),
                "non_authorization_matrix": str(matrix_path),
            },
        }
        for key in (
            "opened_proposal_preparation_gate",
            "open_proposal_preparation_gate_in_p9aq_authorized",
            "proposal_preparation_gate_execution_authorized",
            "prepare_proposal_authorized",
            "proposal_body_write_authorized",
            "dry_load_readback_execution_authorized",
            "eligible_for_timer_hook_implementation",
            "eligible_for_hook_deployment",
            "eligible_for_live_timer_path_load",
            "eligible_for_supervisor_invocation",
            "eligible_for_remote_sync",
            "eligible_for_live_order_submission",
            "eligible_for_stage_governance_change",
            "timer_hook_implementation_authorized",
            "hook_deployment_authorized",
            "timer_path_load_authorized",
            "supervisor_invocation_authorized",
            "remote_sync_authorized",
            "remote_execution_authorized",
            "candidate_execution_authorized",
            "candidate_live_order_submission_authorized",
            "live_order_submission_authorized",
            "target_plan_replacement_authorized",
            "executor_input_mutation_authorized",
            "live_config_mutation_authorized",
            "operator_state_mutation_authorized",
            "timer_or_service_mutation_authorized",
            "production_timer_service_load_authorized",
            "repo_stage_change_authorized",
            "live_supervisor_loads_candidate_hook",
            "live_timer_path_loaded",
            "live_timer_service_enabled_or_invoked",
            "ran_supervisor",
            "timer_path_invoked",
            "remote_execution_performed",
            "remote_control_plane_touched",
            "candidate_execution_performed",
            "wrote_live_hook_config",
            "implemented_hook",
            "deployed_hook",
            "loaded_hook",
            "target_plan_replaced",
            "executor_input_changed",
        ):
            p9aq[key] = False
        self._deep_update(p9aq, p9aq_overrides or {})
        self._write_json(phase9aq, p9aq)
        return {
            "project_profile": project_profile,
            "phase9aq": phase9aq,
            "permission": permission_path,
            "matrix": matrix_path,
            "hook_module": hook_path,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }

    @staticmethod
    def _deep_update(target: dict, updates: dict) -> None:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                Phase9AROpenProposalPreparationGateTests._deep_update(target[key], value)
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
