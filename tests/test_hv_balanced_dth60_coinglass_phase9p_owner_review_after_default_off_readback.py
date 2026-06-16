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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9p_owner_review_after_default_off_readback import (  # noqa: E402
    APPROVE_P9P_DECISION,
    build_phase9p,
    file_sha256,
    resolve_path,
)


class HvBalancedDth60CoinglassPhase9pOwnerReviewAfterDefaultOffReadbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9p-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9p_ready_marks_readback_sufficient_without_authorizing_next_action(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase9p"

        summary, exit_code = build_phase9p(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 0, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["review_scope"], "owner_gated_p9o_default_off_readback_sufficiency_review_only")
        self.assertEqual(summary["owner_decision"]["decision"], APPROVE_P9P_DECISION)
        self.assertTrue(summary["p9o_default_off_readback_sufficient_for_next_owner_gate"])
        self.assertTrue(summary["eligible_for_next_owner_gate_discussion"])
        self.assertFalse(summary["next_owner_gate_execution_authorized"])
        self.assertFalse(summary["eligible_for_live_timer_path_load"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertTrue(summary["default_off_readback_executed"])
        self.assertTrue(summary["default_off_readback_proof_files_ready"])
        self.assertTrue(summary["baseline_executor_input_hash_unchanged"])
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["live_timer_path_loaded"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = output_root / "proof_artifacts" / "p9p" / "20260608T000000Z"
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        self.assertTrue((proof_root / "owner_review_packet.json").exists())
        self.assertTrue((proof_root / "review_decision_matrix.json").exists())
        self.assertTrue((proof_root / "control_boundary_readback.json").exists())
        matrix = self._load_json(proof_root / "review_decision_matrix.json")
        self.assertTrue(matrix["authorizations"]["p9p_review_default_off_readback_sufficiency"])
        self.assertTrue(matrix["authorizations"]["enter_separate_next_owner_gate_discussion"])
        self.assertFalse(matrix["authorizations"]["timer_path_load"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])

    def test_phase9p_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9p(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_timer_path_load",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 0, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9p_review_only", summary["blockers"])
        self.assertFalse(summary["p9o_default_off_readback_sufficient_for_next_owner_gate"])
        self.assertFalse(summary["next_owner_gate_execution_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9p_blocks_when_p9o_loaded_timer_path(self) -> None:
        paths = self._write_ready_inputs(
            p9o_overrides={
                "live_timer_path_loaded": True,
                "gates": {
                    "no_live_timer_path_load_in_p9o": False,
                },
            },
            control_overrides={
                "live_timer_path_loaded": True,
            },
        )

        summary, exit_code = build_phase9p(
            self._args(paths, output_root=self.temp_dir / "timer-loaded"),
            now_fn=lambda: datetime(2026, 6, 8, 0, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9o_summary_ready", summary["blockers"])
        self.assertIn("control_boundary_readback_ready", summary["blockers"])
        self.assertIn("live_timer_path_not_loaded", summary["blockers"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9p_blocks_when_executor_input_not_baseline_only(self) -> None:
        paths = self._write_ready_inputs(
            p9o_overrides={
                "executor_input_hash_equals_baseline": False,
                "candidate_plan_referenced_by_executor": True,
                "gates": {
                    "executor_input_hash_equals_baseline": False,
                    "candidate_plan_not_referenced_by_executor": False,
                },
            },
            executor_overrides={
                "executor_input_hash_equals_baseline": False,
                "candidate_plan_referenced_by_executor": True,
            },
        )

        summary, exit_code = build_phase9p(
            self._args(paths, output_root=self.temp_dir / "executor-mutated"),
            now_fn=lambda: datetime(2026, 6, 8, 0, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9o_summary_ready", summary["blockers"])
        self.assertIn("executor_input_readback_ready", summary["blockers"])
        self.assertIn("baseline_executor_input_hash_unchanged", summary["blockers"])
        self.assertIn("candidate_plan_not_referenced_by_executor", summary["blockers"])
        self.assertFalse(summary["next_owner_gate_execution_authorized"])

    def test_phase9p_blocks_when_current_supervisor_loads_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9p(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 0, 20, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9o_summary_ready", summary["blockers"])
        self.assertIn("live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9P_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9o_summary=str(paths["phase9o"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9o_overrides: dict | None = None,
        manifest_overrides: dict | None = None,
        config_overrides: dict | None = None,
        hook_summary_overrides: dict | None = None,
        executor_overrides: dict | None = None,
        control_overrides: dict | None = None,
        supervisor_text: str = "# no candidate hook import\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        p9o = self.temp_dir / "p9o" / "summary.json"
        proof_root = self.temp_dir / "p9o" / "proof_artifacts" / "p9o" / "run"
        plans = proof_root / "input_plans"
        manifest = proof_root / "dry_load_execution_manifest.json"
        config = proof_root / "default_off_config_readback.json"
        hook_summary = proof_root / "disabled_hook_readback_summary.json"
        executor = proof_root / "executor_input_readback.json"
        control = proof_root / "control_boundary_readback.json"
        baseline_plan = plans / "baseline_target_plan.json"
        executor_plan = plans / "executor_input_target_plan.json"
        candidate_plan = plans / "candidate_shadow_plan.json"

        self._write_json(
            project_profile,
            {
                "current_stage": "stage_1_research_readiness_only",
                "target_stage": "stage_4_automated_execution",
            },
        )
        supervisor.write_text(supervisor_text, encoding="utf-8")
        supervisor_sha = file_sha256(supervisor)
        self._write_json(baseline_plan, {"plan": "baseline", "weights": {"BTCUSDT": 0.1}})
        self._write_json(executor_plan, {"plan": "baseline", "weights": {"BTCUSDT": 0.1}})
        self._write_json(candidate_plan, {"plan": "candidate", "weights": {"BTCUSDT": 0.2}})
        baseline_sha = file_sha256(baseline_plan)
        executor_sha = file_sha256(executor_plan)
        candidate_sha = file_sha256(candidate_plan)

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
        manifest_payload = {
            **base_no_order,
            "contract_version": "hv_balanced_dth60_coinglass_phase9o_dry_load_execution_manifest.v1",
            "dry_load_readback_executed": True,
            "dry_load_mode": "default_off_timer_path_readback_not_live_timer_service",
            "live_timer_path_loaded": False,
            "live_timer_service_enabled_or_invoked": False,
            "supervisor_run_invoked": False,
            "remote_sync_performed": False,
            "execution_target_source": "baseline_only",
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
        }
        config_payload = {
            **base_no_order,
            "contract_version": "hv_balanced_dth60_coinglass_phase9o_default_off_config_readback.v1",
            "default_off_required": True,
            "proof_artifacts_only": True,
            "hook_config_enabled": False,
            "mode": "observe_only",
            "artifact_sink": "proof_artifacts_only",
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "candidate_overlay_execution_path": "excluded",
            "execution_target_source": "baseline_only",
            "live_timer_service_enabled_or_invoked": False,
            "supervisor_run_for_execution": False,
            "remote_sync_performed": False,
        }
        hook_summary_payload = {
            **base_no_order,
            **base_no_mutation,
            "contract_version": "hv_balanced_dth60_observe_only_shadow_hook.v1",
            "status": "ready",
            "blockers": [],
            "hook_enabled": False,
            "baseline_target_plan_byte_for_byte_unchanged": True,
            "executor_input_plan_hash_unchanged": True,
            "executor_input_plan_hash_equals_baseline": True,
            "executor_consumes_baseline_only": True,
            "candidate_artifacts_written_count": 0,
            "candidate_plan_referenced_by_executor": False,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "candidate_overlay_execution_path": "excluded",
            "execution_target_source": "baseline_only",
            "artifact_sink": "proof_artifacts_only",
            "deployed_hook": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
        }
        executor_payload = {
            **base_no_order,
            "contract_version": "hv_balanced_dth60_coinglass_phase9o_executor_input_readback.v1",
            "baseline_target_plan": {"exists": True, "path": str(baseline_plan), "sha256": baseline_sha},
            "executor_input_plan": {"exists": True, "path": str(executor_plan), "sha256": executor_sha},
            "candidate_shadow_plan": {"exists": True, "path": str(candidate_plan), "sha256": candidate_sha},
            "executor_input_hash_equals_baseline": True,
            "candidate_shadow_hash_differs_from_executor": True,
            "candidate_plan_referenced_by_executor": False,
            "target_plan_replaced": False,
            "executor_input_changed": False,
        }
        control_payload = {
            **base_no_order,
            "contract_version": "hv_balanced_dth60_coinglass_phase9o_control_boundary_readback.v1",
            "scope": "local_proof_artifacts_default_off_dry_load_readback_only",
            "live_supervisor_source_unchanged": True,
            "live_supervisor_loads_candidate_hook": False,
            "live_timer_path_loaded": False,
            "live_timer_service_enabled_or_invoked": False,
            "ran_supervisor": False,
            "remote_control_plane_touched": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
        }
        self._deep_update(manifest_payload, manifest_overrides or {})
        self._deep_update(config_payload, config_overrides or {})
        self._deep_update(hook_summary_payload, hook_summary_overrides or {})
        self._deep_update(executor_payload, executor_overrides or {})
        self._deep_update(control_payload, control_overrides or {})
        self._write_json(manifest, manifest_payload)
        self._write_json(config, config_payload)
        self._write_json(hook_summary, hook_summary_payload)
        self._write_json(executor, executor_payload)
        self._write_json(control, control_payload)

        gates = {
            "owner_decision_p9o_execute_readback_only": True,
            "project_stage_boundary_preserved": True,
            "p9n_dry_load_readback_owner_gate_ready": True,
            "current_live_supervisor_not_loading_hook": True,
            "current_hook_hash_matches_p9n_source": True,
            "current_supervisor_hash_matches_p9n_source": True,
            "dry_load_outputs_under_proof_artifacts": True,
            "dry_load_mode_not_live_timer_service": True,
            "default_off_config_loaded": True,
            "artifact_sink_proof_artifacts_only": True,
            "candidate_order_authority_disabled": True,
            "candidate_live_order_submission_authorized_false": True,
            "execution_target_source_baseline_only": True,
            "disabled_hook_readback_ready": True,
            "disabled_hook_writes_zero_candidate_artifacts": True,
            "baseline_target_plan_byte_for_byte_unchanged": True,
            "executor_input_hash_unchanged": True,
            "executor_input_hash_equals_baseline": True,
            "executor_consumes_baseline_only": True,
            "candidate_shadow_hash_differs_from_executor": True,
            "candidate_plan_not_referenced_by_executor": True,
            "target_plan_not_replaced": True,
            "live_supervisor_source_unchanged": True,
            "live_timer_service_not_enabled_or_invoked": True,
            "supervisor_not_run_for_execution": True,
            "no_remote_sync_in_p9o": True,
            "no_live_timer_path_load_in_p9o": True,
            "no_executor_input_mutation_in_p9o": True,
            "no_target_plan_replacement_in_p9o": True,
            "no_live_mutation_in_p9o": True,
            "zero_orders_fills_in_p9o": True,
        }
        p9o_payload = {
            **base_no_order,
            **base_no_mutation,
            "contract_version": "hv_balanced_dth60_coinglass_phase9o_default_off_timer_path_dry_load_readback.v1",
            "status": "ready",
            "blockers": [],
            "dry_load_readback_scope": "owner_gated_default_off_timer_path_dry_load_readback_execution_only",
            "default_off_timer_path_dry_load_readback_ready": True,
            "executed_default_off_timer_path_dry_load_readback": True,
            "dry_load_mode": "default_off_timer_path_readback_not_live_timer_service",
            "dry_load_outputs_under_proof_artifacts": True,
            "default_off_config_loaded": True,
            "default_off_hook_enabled": False,
            "disabled_hook_readback_ready": True,
            "disabled_hook_candidate_artifacts_written_count": 0,
            "baseline_target_plan_byte_for_byte_unchanged": True,
            "executor_input_hash_unchanged": True,
            "executor_input_hash_equals_baseline": True,
            "executor_consumes_baseline_only": True,
            "candidate_shadow_hash_differs_from_executor": True,
            "candidate_plan_referenced_by_executor": False,
            "target_plan_replaced": False,
            "executor_input_changed": False,
            "eligible_for_owner_p9p_review": True,
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
            "wrote_live_hook_config": False,
            "implemented_hook": False,
            "deployed_hook": False,
            "loaded_hook": False,
            "owner_decision": {
                "decision": "approve_p9o_execute_default_off_timer_path_dry_load_readback_only",
                "default_off_timer_path_dry_load_readback_execution_approved": True,
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
                "dry_load_execution_manifest": str(manifest),
                "default_off_config_readback": str(config),
                "disabled_hook_readback_summary": str(hook_summary),
                "executor_input_readback": str(executor),
                "control_boundary_readback": str(control),
                "baseline_target_plan": str(baseline_plan),
                "executor_input_plan": str(executor_plan),
                "candidate_shadow_plan": str(candidate_plan),
            },
        }
        self._deep_update(p9o_payload, p9o_overrides or {})
        self._write_json(p9o, p9o_payload)
        return {
            "project_profile": project_profile,
            "phase9o": p9o,
            "hook_module": hook_path,
            "supervisor": supervisor,
        }

    @staticmethod
    def _deep_update(target: dict, updates: dict) -> None:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                HvBalancedDth60CoinglassPhase9pOwnerReviewAfterDefaultOffReadbackTests._deep_update(
                    target[key], value
                )
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
