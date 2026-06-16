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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9n_default_off_timer_path_dry_load_readback_owner_gate import (  # noqa: E402
    APPROVE_P9N_DECISION,
    build_phase9n,
    file_sha256,
    resolve_path,
)


class HvBalancedDth60CoinglassPhase9nDryLoadReadbackOwnerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9n-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9n_ready_allows_only_future_default_off_readback_execution(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase9n"

        summary, exit_code = build_phase9n(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 7, 22, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(
            summary["gate_scope"],
            "owner_gated_default_off_timer_path_dry_load_readback_execution_permission_only",
        )
        self.assertEqual(summary["owner_decision"]["decision"], APPROVE_P9N_DECISION)
        self.assertTrue(summary["p9n_default_off_timer_path_dry_load_readback_owner_gate_ready"])
        self.assertTrue(summary["eligible_to_execute_default_off_timer_path_dry_load_readback"])
        self.assertFalse(summary["executed_default_off_timer_path_dry_load_readback"])
        self.assertEqual(
            summary["allowed_next_gate"],
            "P9O_default_off_timer_path_dry_load_readback_execution_only_if_separately_requested",
        )
        self.assertEqual(summary["future_readback_artifact_sink_required"], "proof_artifacts_only")
        self.assertEqual(summary["future_readback_executor_input_required"], "baseline_only")
        self.assertEqual(summary["future_readback_candidate_order_authority_required"], "disabled")
        self.assertFalse(summary["future_readback_live_order_submission_authorized_required"])
        self.assertFalse(summary["eligible_for_timer_hook_implementation"])
        self.assertFalse(summary["eligible_for_hook_deployment"])
        self.assertFalse(summary["eligible_for_live_timer_path_load"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        self.assertFalse(summary["timer_hook_implementation_authorized"])
        self.assertFalse(summary["hook_deployment_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["remote_sync_authorized"])
        self.assertFalse(summary["supervisor_run_authorized"])
        self.assertFalse(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = output_root / "proof_artifacts" / "p9n" / "20260607T220000Z"
        gate_path = proof_root / "dry_load_readback_execution_gate.json"
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        self.assertTrue(gate_path.exists())
        self.assertTrue((proof_root / "non_authorization_matrix.json").exists())
        self.assertTrue((proof_root / "control_boundary_readback.json").exists())
        gate = self._load_json(gate_path)
        self.assertEqual(gate["allowed_next_action"], "execute_default_off_timer_path_dry_load_readback")
        self.assertFalse(gate["executed_in_p9n"])
        self.assertTrue(gate["allowed_next_action_constraints"]["default_off_required"])
        self.assertTrue(gate["allowed_next_action_constraints"]["proof_artifacts_only"])
        self.assertEqual(gate["allowed_next_action_constraints"]["executor_input_must_remain_baseline_only"], True)
        self.assertEqual(gate["allowed_next_action_constraints"]["orders_submitted_must_equal"], 0)

    def test_phase9n_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9n(
            self._args(paths, output_root=self.temp_dir / "wrong-owner", owner_decision="approve_live_timer_path_load"),
            now_fn=lambda: datetime(2026, 6, 7, 22, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9n_dry_load_readback_gate_only", summary["blockers"])
        self.assertFalse(summary["eligible_to_execute_default_off_timer_path_dry_load_readback"])
        self.assertFalse(summary["executed_default_off_timer_path_dry_load_readback"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9n_blocks_when_p9m_proposal_body_not_default_off(self) -> None:
        paths = self._write_ready_inputs(
            proposal_overrides={
                "proposed_future_dry_load_contract": {
                    "hook_config_enabled_default": True,
                    "orders_submitted_must_equal": 1,
                }
            }
        )

        summary, exit_code = build_phase9n(
            self._args(paths, output_root=self.temp_dir / "bad-proposal"),
            now_fn=lambda: datetime(2026, 6, 7, 22, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9m_proposal_body_ready", summary["blockers"])
        self.assertFalse(summary["eligible_to_execute_default_off_timer_path_dry_load_readback"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9n_blocks_when_current_supervisor_imports_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9n(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 7, 22, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["eligible_to_execute_default_off_timer_path_dry_load_readback"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9N_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9m_summary=str(paths["phase9m"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9m_overrides: dict | None = None,
        proposal_overrides: dict | None = None,
        supervisor_text: str = "# no candidate hook import\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9m = self.temp_dir / "phase9m.json"
        proposal_path = self.temp_dir / "proof_artifacts" / "p9m" / "proposal.json"
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
        proposal = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9m_default_off_timer_path_dry_load_proposal_body.v1",
            "run_id": "unit-test-p9m",
            "proposal_scope": "owner_gated_default_off_timer_path_dry_load_proposal_only",
            "proposal_status": "draft_for_future_owner_review",
            "p9m_authorizes_timer_path_dry_load": False,
            "p9m_authorizes_timer_hook_implementation": False,
            "p9m_authorizes_hook_deployment": False,
            "p9m_authorizes_timer_path_load": False,
            "p9m_authorizes_supervisor_run": False,
            "p9m_authorizes_live_orders": False,
            "future_gate_required": True,
            "proposed_future_gate": "P9N_default_off_timer_path_dry_load_readback_only_if_separately_requested",
            "proposed_future_gate_scope": "default_off_timer_path_dry_load_readback_only",
            "proposed_future_dry_load_contract": {
                "default_off_required": True,
                "hook_config_enabled_default": False,
                "observe_only_mode_required": True,
                "candidate_order_authority": "disabled",
                "candidate_live_order_submission_authorized": False,
                "execution_target_source": "baseline_only",
                "candidate_overlay_execution_path": "excluded",
                "candidate_artifact_sink": "proof_artifacts_only",
                "executor_input_must_remain_baseline_only": True,
                "candidate_plan_must_not_be_referenced_by_executor": True,
                "target_plan_must_not_be_replaced": True,
                "live_timer_service_must_not_be_enabled_or_invoked": True,
                "supervisor_must_not_be_run_for_execution": True,
                "remote_sync_must_not_occur": True,
                "live_config_must_not_change": True,
                "operator_state_must_not_change": True,
                "timer_state_must_not_change": True,
                "orders_submitted_must_equal": 0,
                "fill_count_must_equal": 0,
            },
            "default_off_hook_config_contract": {
                "ObserveOnlyShadowHookConfig.enabled": False,
                "ObserveOnlyShadowHookConfig.mode": "observe_only",
                "ObserveOnlyShadowHookConfig.artifact_sink": "proof_artifacts_only",
                "ObserveOnlyShadowHookConfig.candidate_order_authority": "disabled",
                "ObserveOnlyShadowHookConfig.candidate_live_order_submission_authorized": False,
                "ObserveOnlyShadowHookConfig.execution_target_source": "baseline_only",
                "ObserveOnlyShadowHookConfig.candidate_overlay_execution_path": "excluded",
            },
        }
        self._deep_update(proposal, proposal_overrides or {})
        self._write_json(proposal_path, proposal)
        p9m = {
            "status": "ready",
            "blockers": [],
            "proposal_scope": "owner_gated_default_off_timer_path_dry_load_proposal_only",
            "default_off_timer_path_dry_load_proposal_ready": True,
            "eligible_for_future_default_off_timer_path_dry_load_review": True,
            "prepared_default_off_timer_path_dry_load_proposal": True,
            "wrote_default_off_timer_path_dry_load_proposal_body": True,
            "proposal_body_sink": "proof_artifacts_only",
            "p9m_authorizes_timer_path_dry_load": False,
            "future_dry_load_gate_required": True,
            "proposed_future_gate": "P9N_default_off_timer_path_dry_load_readback_only_if_separately_requested",
            "proposed_dry_load_default_off": True,
            "proposed_dry_load_mode": "proposal_only_not_loaded",
            "proposed_timer_load_mode": "proposal_only_not_loaded",
            "proposed_executor_input_source": "baseline_only",
            "proposed_candidate_artifact_sink": "proof_artifacts_only",
            "proposed_candidate_order_authority": "disabled",
            "proposed_candidate_live_order_submission_authorized": False,
            "eligible_for_timer_path_dry_load_execution": False,
            "eligible_for_timer_hook_implementation": False,
            "eligible_for_hook_deployment": False,
            "eligible_for_timer_path_load": False,
            "eligible_for_live_order_submission": False,
            "eligible_for_stage_governance_change": False,
            "timer_path_dry_load_authorized": False,
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
            "wrote_live_hook_config": False,
            "implemented_hook": False,
            "deployed_hook": False,
            "loaded_hook": False,
            "target_plan_replaced": False,
            "executor_input_changed": False,
            "owner_decision": {
                "decision": "approve_p9m_default_off_timer_path_dry_load_proposal_only",
                "draft_default_off_timer_path_dry_load_proposal_approved": True,
                "write_proposal_artifact_approved": True,
                "timer_path_dry_load_approved": False,
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
                "default_off_timer_path_dry_load_proposal": str(proposal_path),
            },
            "gates": {
                "owner_decision_p9m_proposal_only": True,
                "project_stage_boundary_preserved": True,
                "p9l_proposal_preparation_gate_ready": True,
                "current_live_supervisor_not_loading_hook": True,
                "current_hook_hash_matches_p9l_source": True,
                "current_supervisor_hash_matches_p9l_source": True,
                "proposal_output_under_proof_artifacts": True,
                "proposal_body_output_under_proof_artifacts": True,
                "proposal_default_off_required": True,
                "proposal_artifact_sink_proof_artifacts_only": True,
                "proposal_executor_input_source_baseline_only": True,
                "proposal_candidate_order_authority_disabled": True,
                "proposal_requires_separate_future_dry_load_gate": True,
                "no_timer_path_dry_load_execution_in_p9m": True,
                "no_timer_hook_implementation_in_p9m": True,
                "no_hook_deployment_in_p9m": True,
                "no_timer_path_load_in_p9m": True,
                "no_supervisor_run_in_p9m": True,
                "no_remote_execution_in_p9m": True,
                "no_executor_input_mutation_in_p9m": True,
                "no_target_plan_replacement_in_p9m": True,
                "no_live_mutation_in_p9m": True,
                "zero_orders_fills_in_p9m": True,
            },
        }
        self._deep_update(p9m, p9m_overrides or {})
        self._write_json(phase9m, p9m)
        return {
            "project_profile": project_profile,
            "phase9m": phase9m,
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
