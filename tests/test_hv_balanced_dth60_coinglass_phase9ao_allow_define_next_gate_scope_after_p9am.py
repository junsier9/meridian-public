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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ao_allow_define_next_gate_scope_after_p9am import (  # noqa: E402
    APPROVE_P9AO_DECISION,
    P9AP_GATE,
    build_phase9ao,
    p9an_ready_for_p9ao,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
    resolve_path,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9AOAllowDefineNextGateScopeAfterP9AMTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9ao-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9ao_ready_allows_only_future_scope_definition(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "p9ao-ready"

        summary, exit_code = build_phase9ao(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 8, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(
            summary["gate_scope"],
            "owner_gated_allow_future_next_gate_scope_definition_after_p9am_readback_only",
        )
        self.assertEqual(summary["owner_decision"]["decision"], APPROVE_P9AO_DECISION)
        self.assertTrue(summary["p9ao_allow_define_next_gate_scope_after_p9am_ready"])
        self.assertTrue(summary["eligible_to_define_next_gate_scope_after_p9am"])
        self.assertFalse(summary["defined_next_gate_scope"])
        self.assertFalse(summary["next_gate_scope_definition_in_p9ao_authorized"])
        self.assertFalse(summary["next_gate_execution_authorized"])
        self.assertEqual(summary["allowed_next_gate"], P9AP_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
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

        proof_root = output_root / "proof_artifacts" / "p9ao" / "20260608T080000Z"
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        self.assertTrue((proof_root / "next_gate_scope_permission_gate.json").exists())
        self.assertTrue((proof_root / "non_authorization_matrix.json").exists())
        self.assertTrue((proof_root / "control_boundary_readback.json").exists())
        permission = self._load_json(proof_root / "next_gate_scope_permission_gate.json")
        self.assertEqual(permission["allowed_next_gate"], P9AP_GATE)
        self.assertFalse(permission["defined_in_p9ao"])
        self.assertFalse(permission["executed_in_p9ao"])
        self.assertTrue(permission["allowed_next_action_constraints"]["scope_definition_only"])
        self.assertTrue(permission["allowed_next_action_constraints"]["must_not_execute_next_gate"])
        matrix = self._load_json(proof_root / "non_authorization_matrix.json")
        self.assertTrue(matrix["authorizations"]["future_next_gate_scope_definition_after_p9am"])
        self.assertFalse(matrix["authorizations"]["define_next_gate_scope_in_p9ao"])
        self.assertFalse(matrix["authorizations"]["execute_next_gate"])
        self.assertFalse(matrix["authorizations"]["live_timer_path_load"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])

    def test_phase9ao_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9ao(
            self._args(paths, output_root=self.temp_dir / "wrong-owner", owner_decision="approve_live_orders"),
            now_fn=lambda: datetime(2026, 6, 8, 8, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9ao_allow_define_scope_only", summary["blockers"])
        self.assertFalse(summary["eligible_to_define_next_gate_scope_after_p9am"])
        self.assertFalse(summary["next_gate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9ao_blocks_when_p9an_authorized_next_gate_execution(self) -> None:
        paths = self._write_ready_inputs(
            p9an_overrides={
                "next_owner_gate_execution_authorized": True,
                "gates": {"no_define_next_gate_scope_in_p9an": False},
            },
            matrix_overrides={
                "authorizations": {
                    "execute_next_owner_gate": True,
                    "timer_path_load": True,
                }
            },
            packet_overrides={
                "review_result": {
                    "next_owner_gate_execution_authorized": True,
                }
            },
        )
        p9an = self._load_json(paths["phase9an"])
        matrix = self._load_json(paths["matrix"])
        packet = self._load_json(paths["packet"])
        self.assertFalse(
            p9an_ready_for_p9ao(
                p9an,
                matrix,
                packet,
                current_hook_sha256=file_sha256(paths["hook_module"]),
                current_supervisor_sha256=file_sha256(paths["supervisor"]),
                current_live_config_sha256=tree_sha256(paths["live_config_dir"]),
                current_supervisor_loads_candidate_hook=False,
            )
        )

        summary, exit_code = build_phase9ao(
            self._args(paths, output_root=self.temp_dir / "bad-p9an"),
            now_fn=lambda: datetime(2026, 6, 8, 8, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9an_review_ready", summary["blockers"])
        self.assertIn("p9an_next_gate_execution_not_authorized", summary["blockers"])
        self.assertFalse(summary["eligible_to_define_next_gate_scope_after_p9am"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9ao_blocks_when_current_supervisor_loads_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9ao(
            self._args(paths, output_root=self.temp_dir / "supervisor-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 8, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9an_review_ready", summary["blockers"])
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9AO_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9an_summary=str(paths["phase9an"]),
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
        p9an_overrides: dict | None = None,
        matrix_overrides: dict | None = None,
        packet_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9an = self.temp_dir / "p9an" / "summary.json"
        proof_root = self.temp_dir / "p9an" / "proof_artifacts" / "p9an" / "run"
        matrix_path = proof_root / "review_decision_matrix.json"
        packet_path = proof_root / "owner_review_packet.json"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        live_config_dir.mkdir(parents=True)
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")
        supervisor_sha = file_sha256(supervisor)
        live_config_sha = tree_sha256(live_config_dir)

        self._write_json(project_profile, {"current_stage": "stage_1_research_readiness_only"})
        minimum_proof = {
            "stage_boundary_preserved": True,
            "p9am_summary_ready": True,
            "p9am_default_off_observe_only_readback_executed": True,
            "p9am_readback_default_off": True,
            "p9am_readback_observe_only_shadow_writer": True,
            "p9am_readback_not_live_timer_service": True,
            "proof_files_exist": True,
            "proof_files_under_proof_artifacts": True,
            "dry_load_manifest_ready": True,
            "default_off_config_readback_ready": True,
            "observe_only_shadow_readback_summary_ready": True,
            "executor_input_readback_ready": True,
            "control_boundary_readback_ready": True,
            "candidate_shadow_artifacts_written": True,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "baseline_executor_input_hash_unchanged": True,
            "executor_consumes_baseline_only": True,
            "candidate_shadow_hash_differs_from_executor": True,
            "candidate_plan_not_referenced_by_executor": True,
            "target_plan_not_replaced": True,
            "live_supervisor_not_loading_hook": True,
            "live_config_dir_unchanged": True,
            "live_timer_path_not_loaded": True,
            "supervisor_not_run": True,
            "remote_not_touched": True,
            "candidate_execution_not_performed": True,
            "zero_orders_fills": True,
            "no_live_mutation": True,
        }
        gates = {
            "owner_decision_p9an_review_only": True,
            **minimum_proof,
            "review_output_under_proof_artifacts": True,
            "no_define_next_gate_scope_in_p9an": True,
            "no_timer_hook_implementation_in_p9an": True,
            "no_hook_deployment_in_p9an": True,
            "no_timer_path_load_in_p9an": True,
            "no_production_timer_service_load_in_p9an": True,
            "no_supervisor_run_in_p9an": True,
            "no_remote_execution_in_p9an": True,
            "no_candidate_execution_in_p9an": True,
            "no_executor_input_mutation_in_p9an": True,
            "no_target_plan_replacement_in_p9an": True,
            "no_live_mutation_in_p9an": True,
            "zero_orders_fills_in_p9an": True,
        }
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9an_review_decision_matrix.v1",
            "run_id": "unit-test-p9an",
            "review_question": "is_p9am_default_off_observe_only_readback_sufficient_to_enter_separate_next_owner_gate",
            "minimum_proof": minimum_proof,
            "authorizations": {
                "p9an_review_default_off_observe_only_readback_sufficiency": True,
                "enter_separate_next_owner_gate_discussion": True,
                "define_next_gate_scope_in_p9an": False,
                "execute_next_owner_gate": False,
                "candidate_execution": False,
                "candidate_live_order_submission": False,
                "timer_hook_implementation": False,
                "hook_deployment": False,
                "timer_path_load": False,
                "production_timer_service_load": False,
                "live_order_submission": False,
                "target_plan_replacement": False,
                "executor_input_mutation": False,
                "live_config_mutation": False,
                "operator_state_mutation": False,
                "timer_or_service_mutation": False,
                "remote_sync": False,
                "supervisor_invocation": False,
                "supervisor_run": False,
                "stage_governance_change": False,
            },
        }
        packet = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9an_owner_review_packet.v1",
            "run_id": "unit-test-p9an",
            "review_scope": "owner_gated_p9am_default_off_observe_only_readback_sufficiency_review_only",
            "minimum_proof": minimum_proof,
            "review_result": {
                "p9am_default_off_observe_only_readback_sufficient_for_next_owner_gate": True,
                "next_owner_gate_execution_authorized": False,
                "define_next_gate_scope_in_p9an_authorized": False,
                "timer_path_load_authorized": False,
                "live_order_submission_authorized": False,
            },
        }
        self._deep_update(matrix, matrix_overrides or {})
        self._deep_update(packet, packet_overrides or {})
        self._write_json(matrix_path, matrix)
        self._write_json(packet_path, packet)
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
        p9an_payload = {
            **no_order,
            **no_live,
            "contract_version": "hv_balanced_dth60_coinglass_phase9an_review_after_default_off_observe_only_readback.v1",
            "status": "ready",
            "blockers": [],
            "review_scope": "owner_gated_p9am_default_off_observe_only_readback_sufficiency_review_only",
            "p9am_default_off_observe_only_readback_sufficient_for_next_owner_gate": True,
            "eligible_for_next_owner_gate_discussion": True,
            "allowed_next_gate": "P9AO_allow_define_next_gate_scope_after_p9am_only_if_separately_requested",
            "allowed_next_gate_must_be_separately_requested": True,
            "default_off_observe_only_readback_executed": True,
            "default_off_observe_only_readback_proof_files_ready": True,
            "default_off_readback_not_live_timer_service": True,
            "observe_only_shadow_readback_ready": True,
            "candidate_shadow_artifacts_written_count": 4,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "baseline_executor_input_hash_unchanged": True,
            "executor_consumes_baseline_only": True,
            "candidate_shadow_hash_differs_from_executor": True,
            "candidate_plan_referenced_by_executor": False,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifact_sink": "proof_artifacts_only",
            "live_supervisor_source_unchanged": True,
            "live_config_dir_unchanged": True,
            "owner_decision": {
                "decision": "approve_p9an_review_default_off_observe_only_readback_sufficiency_only",
                "review_default_off_observe_only_readback_sufficiency_approved": True,
                "enter_separate_next_owner_gate_discussion_approved": True,
                "define_next_gate_scope_in_p9an_approved": False,
                "execute_next_owner_gate_approved": False,
                "live_order_submission_approved": False,
            },
            "source_evidence": {
                "hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha},
                "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
                "live_config_dir": {"path": str(live_config_dir), "exists": True, "sha256": live_config_sha},
            },
            "gates": gates,
            "output_files": {
                "review_decision_matrix": str(matrix_path),
                "owner_review_packet": str(packet_path),
            },
        }
        for key in (
            "next_owner_gate_execution_authorized",
            "define_next_gate_scope_in_p9an_authorized",
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
            "candidate_execution_authorized",
            "live_order_submission_authorized",
            "target_plan_replacement_authorized",
            "executor_input_mutation_authorized",
            "live_config_mutation_authorized",
            "operator_state_mutation_authorized",
            "timer_or_service_mutation_authorized",
            "candidate_live_order_submission_authorized",
            "live_supervisor_loads_candidate_hook",
            "live_timer_path_loaded",
            "live_timer_service_enabled_or_invoked",
            "ran_supervisor",
            "timer_path_invoked",
            "remote_execution_performed",
            "remote_control_plane_touched",
            "candidate_execution_performed",
            "target_plan_replaced",
            "wrote_live_hook_config",
            "implemented_hook",
            "deployed_hook",
            "loaded_hook",
            "executor_input_changed",
        ):
            p9an_payload[key] = False
        self._deep_update(p9an_payload, p9an_overrides or {})
        self._write_json(phase9an, p9an_payload)
        return {
            "project_profile": project_profile,
            "phase9an": phase9an,
            "matrix": matrix_path,
            "packet": packet_path,
            "hook_module": hook_path,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }

    @staticmethod
    def _deep_update(target: dict, updates: dict) -> None:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                Phase9AOAllowDefineNextGateScopeAfterP9AMTests._deep_update(target[key], value)
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
