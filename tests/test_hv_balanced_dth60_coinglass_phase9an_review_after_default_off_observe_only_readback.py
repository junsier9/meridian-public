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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9am_default_off_readback_execution import (  # noqa: E402
    P9AN_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9an_review_after_default_off_observe_only_readback import (  # noqa: E402
    APPROVE_P9AN_DECISION,
    P9AO_GATE,
    build_phase9an,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
    resolve_path,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9ANReviewAfterDefaultOffObserveOnlyReadbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9an-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9an_ready_reviews_p9am_without_authorizing_next_action(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "p9an-ready"

        summary, exit_code = build_phase9an(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 7, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(
            summary["review_scope"],
            "owner_gated_p9am_default_off_observe_only_readback_sufficiency_review_only",
        )
        self.assertTrue(summary["p9am_default_off_observe_only_readback_sufficient_for_next_owner_gate"])
        self.assertTrue(summary["eligible_for_next_owner_gate_discussion"])
        self.assertEqual(summary["allowed_next_gate"], P9AO_GATE)
        self.assertFalse(summary["next_owner_gate_execution_authorized"])
        self.assertFalse(summary["define_next_gate_scope_in_p9an_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertTrue(summary["default_off_observe_only_readback_executed"])
        self.assertTrue(summary["default_off_observe_only_readback_proof_files_ready"])
        self.assertTrue(summary["observe_only_shadow_readback_ready"])
        self.assertEqual(summary["candidate_shadow_artifacts_written_count"], 4)
        self.assertTrue(summary["candidate_artifacts_under_proof_artifacts_only"])
        self.assertTrue(summary["baseline_executor_input_hash_unchanged"])
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertTrue(summary["candidate_shadow_hash_differs_from_executor"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["live_timer_path_loaded"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = output_root / "proof_artifacts" / "p9an" / "20260608T070000Z"
        self.assertTrue((proof_root / "owner_review_packet.json").exists())
        self.assertTrue((proof_root / "review_decision_matrix.json").exists())
        self.assertTrue((proof_root / "control_boundary_readback.json").exists())
        matrix = self._load_json(proof_root / "review_decision_matrix.json")
        self.assertTrue(matrix["authorizations"]["p9an_review_default_off_observe_only_readback_sufficiency"])
        self.assertTrue(matrix["authorizations"]["enter_separate_next_owner_gate_discussion"])
        self.assertFalse(matrix["authorizations"]["define_next_gate_scope_in_p9an"])
        self.assertFalse(matrix["authorizations"]["execute_next_owner_gate"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])

    def test_phase9an_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9an(
            self._args(paths, output_root=self.temp_dir / "wrong-owner", owner_decision="approve_live_orders"),
            now_fn=lambda: datetime(2026, 6, 8, 7, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9an_review_only", summary["blockers"])
        self.assertFalse(summary["p9am_default_off_observe_only_readback_sufficient_for_next_owner_gate"])
        self.assertFalse(summary["next_owner_gate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9an_blocks_when_candidate_shadow_artifacts_missing(self) -> None:
        paths = self._write_ready_inputs(
            p9am_overrides={
                "candidate_shadow_artifacts_written_count": 0,
                "candidate_artifacts_under_proof_artifacts_only": False,
                "gates": {
                    "candidate_shadow_artifacts_written": False,
                    "candidate_artifacts_under_proof_artifacts_only": False,
                },
            },
            shadow_overrides={
                "candidate_artifacts_written_count": 0,
                "candidate_artifacts_under_proof_artifacts_only": False,
                "candidate_artifact_paths": [],
                "gates": {"candidate_shadow_artifact_written": False},
            },
            executor_overrides={
                "candidate_shadow_artifacts_written_count": 0,
                "candidate_shadow_artifact_paths": [],
            },
        )

        summary, exit_code = build_phase9an(
            self._args(paths, output_root=self.temp_dir / "missing-shadow"),
            now_fn=lambda: datetime(2026, 6, 8, 7, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9am_summary_ready", summary["blockers"])
        self.assertIn("observe_only_shadow_readback_summary_ready", summary["blockers"])
        self.assertIn("executor_input_readback_ready", summary["blockers"])
        self.assertIn("candidate_shadow_artifacts_written", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9an_blocks_when_executor_references_candidate(self) -> None:
        paths = self._write_ready_inputs(
            p9am_overrides={
                "executor_input_hash_equals_baseline": False,
                "executor_consumes_baseline_only": False,
                "candidate_plan_referenced_by_executor": True,
                "gates": {
                    "executor_input_hash_equals_baseline": False,
                    "executor_consumes_baseline_only": False,
                    "candidate_plan_not_referenced_by_executor": False,
                },
            },
            shadow_overrides={
                "executor_input_plan_hash_equals_baseline": False,
                "executor_consumes_baseline_only": False,
                "candidate_plan_referenced_by_executor": True,
            },
            executor_overrides={
                "executor_input_hash_equals_baseline": False,
                "candidate_plan_referenced_by_executor": True,
            },
        )

        summary, exit_code = build_phase9an(
            self._args(paths, output_root=self.temp_dir / "executor-candidate"),
            now_fn=lambda: datetime(2026, 6, 8, 7, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9am_summary_ready", summary["blockers"])
        self.assertIn("observe_only_shadow_readback_summary_ready", summary["blockers"])
        self.assertIn("executor_input_readback_ready", summary["blockers"])
        self.assertIn("baseline_executor_input_hash_unchanged", summary["blockers"])
        self.assertIn("candidate_plan_not_referenced_by_executor", summary["blockers"])
        self.assertFalse(summary["next_owner_gate_execution_authorized"])

    def test_phase9an_blocks_when_current_supervisor_loads_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9an(
            self._args(paths, output_root=self.temp_dir / "supervisor-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 7, 20, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9am_summary_ready", summary["blockers"])
        self.assertIn("live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9AN_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9am_summary=str(paths["phase9am"]),
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
        p9am_overrides: dict | None = None,
        manifest_overrides: dict | None = None,
        config_overrides: dict | None = None,
        shadow_overrides: dict | None = None,
        executor_overrides: dict | None = None,
        control_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9am = self.temp_dir / "p9am" / "summary.json"
        proof_root = self.temp_dir / "p9am" / "proof_artifacts" / "p9am" / "run"
        plans = proof_root / "input_plans"
        shadow_root = proof_root / "observe_only_shadow_output" / "shadow_hook"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        live_config_dir.mkdir(parents=True)
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")

        baseline_plan = plans / "baseline_target_plan.json"
        executor_plan = plans / "executor_input_target_plan.json"
        candidate_plan = plans / "candidate_shadow_plan.json"
        manifest = proof_root / "dry_load_execution_manifest.json"
        config = proof_root / "default_off_config_readback.json"
        shadow = proof_root / "observe_only_shadow_readback_summary.json"
        executor = proof_root / "executor_input_readback.json"
        control = proof_root / "control_boundary_readback.json"
        shadow_candidate = shadow_root / "candidate_shadow_plan.json"
        shadow_context = shadow_root / "supervisor_context_snapshot.json"
        shadow_executor = shadow_root / "executor_input_readback.json"
        shadow_manifest = shadow_root / "manifest.json"

        self._write_json(project_profile, {"current_stage": "stage_1_research_readiness_only"})
        self._write_json(baseline_plan, {"plan": "baseline", "weights": {"BTCUSDT": 0.1}})
        self._write_json(executor_plan, {"plan": "baseline", "weights": {"BTCUSDT": 0.1}})
        self._write_json(candidate_plan, {"plan": "candidate", "weights": {"BTCUSDT": 0.07}})
        for path in (shadow_candidate, shadow_context, shadow_executor, shadow_manifest):
            self._write_json(path, {"artifact": path.stem})

        baseline_sha = file_sha256(baseline_plan)
        executor_sha = file_sha256(executor_plan)
        candidate_sha = file_sha256(candidate_plan)
        supervisor_sha = file_sha256(supervisor)
        live_config_sha = tree_sha256(live_config_dir)
        candidate_artifact_paths = [str(path) for path in (shadow_candidate, shadow_context, shadow_executor, shadow_manifest)]
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
        manifest_payload = {
            **no_order,
            "contract_version": "hv_balanced_dth60_coinglass_phase9am_dry_load_execution_manifest.v1",
            "executed_default_off_observe_only_readback": True,
            "dry_load_readback_executed": True,
            "dry_load_mode": "default_off_observe_only_timer_path_readback_harness_not_live_timer_service",
            "default_off_hook_enabled_in_live_config": False,
            "observe_only_shadow_writer_enabled_in_proof_harness": True,
            "entered_timer_path_dry_load_harness": True,
            "entered_live_timer_path": False,
            "live_timer_path_loaded": False,
            "live_timer_service_enabled_or_invoked": False,
            "supervisor_run_invoked": False,
            "remote_sync_performed": False,
            "candidate_execution_authorized": False,
            "candidate_execution_performed": False,
            "execution_target_source": "baseline_only",
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
        }
        config_payload = {
            **no_order,
            "contract_version": "hv_balanced_dth60_coinglass_phase9am_default_off_config_readback.v1",
            "default_off_required": True,
            "hook_config_enabled_default": False,
            "observe_only_shadow_writer_enabled_in_proof_harness": True,
            "mode": "observe_only",
            "artifact_sink": "proof_artifacts_only",
            "candidate_execution_authorized": False,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "candidate_overlay_execution_path": "excluded",
            "execution_target_source": "baseline_only",
            "proof_artifacts_only": True,
            "entered_timer_path_dry_load_harness": True,
            "entered_live_timer_path": False,
            "live_timer_service_enabled_or_invoked": False,
            "supervisor_run_for_execution": False,
            "remote_sync_performed": False,
        }
        shadow_payload = {
            **no_order,
            **no_live,
            "contract_version": "hv_balanced_dth60_observe_only_shadow_hook.v1",
            "status": "ready",
            "blockers": [],
            "hook_enabled": True,
            "artifact_sink": "proof_artifacts_only",
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "candidate_overlay_execution_path": "excluded",
            "execution_target_source": "baseline_only",
            "candidate_artifact_paths": candidate_artifact_paths,
            "candidate_artifacts_written_count": 4,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "baseline_target_plan_byte_for_byte_unchanged": True,
            "executor_input_plan_hash_unchanged": True,
            "executor_input_plan_hash_equals_baseline": True,
            "executor_consumes_baseline_only": True,
            "candidate_plan_referenced_by_executor": False,
            "candidate_shadow_plan_sha256": candidate_sha,
            "executor_input_plan_sha256_after_hook": executor_sha,
            "deployed_hook": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
        }
        executor_payload = {
            **no_order,
            "contract_version": "hv_balanced_dth60_coinglass_phase9am_executor_input_readback.v1",
            "baseline_target_plan": {"exists": True, "path": str(baseline_plan), "sha256": baseline_sha},
            "executor_input_plan": {"exists": True, "path": str(executor_plan), "sha256": executor_sha},
            "candidate_shadow_source_plan": {"exists": True, "path": str(candidate_plan), "sha256": candidate_sha},
            "candidate_shadow_artifact_paths": candidate_artifact_paths,
            "candidate_shadow_artifacts_written_count": 4,
            "executor_input_hash_equals_baseline": True,
            "candidate_shadow_hash_differs_from_executor": True,
            "candidate_plan_referenced_by_executor": False,
            "target_plan_replaced": False,
            "executor_input_changed": False,
            "execution_target_source": "baseline_only",
        }
        control_payload = {
            **no_order,
            **no_live,
            "contract_version": "hv_balanced_dth60_coinglass_phase9am_control_boundary_readback.v1",
            "scope": "local_proof_artifacts_default_off_observe_only_readback_only",
            "live_supervisor_source_unchanged": True,
            "live_supervisor_loads_candidate_hook": False,
            "live_config_dir_unchanged": True,
            "entered_timer_path_dry_load_harness": True,
            "entered_live_timer_path": False,
            "live_timer_path_loaded": False,
            "live_timer_service_enabled_or_invoked": False,
            "ran_supervisor": False,
            "remote_control_plane_touched": False,
            "candidate_execution_authorized": False,
            "candidate_execution_performed": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
        }
        self._deep_update(manifest_payload, manifest_overrides or {})
        self._deep_update(config_payload, config_overrides or {})
        self._deep_update(shadow_payload, shadow_overrides or {})
        self._deep_update(executor_payload, executor_overrides or {})
        self._deep_update(control_payload, control_overrides or {})
        self._write_json(manifest, manifest_payload)
        self._write_json(config, config_payload)
        self._write_json(shadow, shadow_payload)
        self._write_json(executor, executor_payload)
        self._write_json(control, control_payload)

        gates = {
            "owner_decision_p9am_execute_readback_only": True,
            "project_stage_boundary_preserved": True,
            "p9al_readback_owner_gate_ready": True,
            "p9al_allows_p9am_only": True,
            "p9al_did_not_execute_readback": True,
            "current_live_supervisor_not_loading_hook": True,
            "current_hook_hash_matches_p9al_source": True,
            "current_supervisor_hash_matches_p9al_source": True,
            "current_live_config_hash_matches_p9al_source": True,
            "dry_load_output_root_under_proof_artifacts": True,
            "dry_load_outputs_under_proof_artifacts": True,
            "dry_load_mode_not_live_timer_service": True,
            "default_off_config_loaded": True,
            "observe_only_shadow_writer_enabled_in_proof_harness": True,
            "entered_timer_path_dry_load_harness": True,
            "entered_live_timer_path_false": True,
            "candidate_execution_not_authorized": True,
            "artifact_sink_proof_artifacts_only": True,
            "candidate_order_authority_disabled": True,
            "candidate_live_order_submission_authorized_false": True,
            "execution_target_source_baseline_only": True,
            "observe_only_shadow_readback_ready": True,
            "candidate_shadow_artifacts_written": True,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "baseline_target_plan_byte_for_byte_unchanged": True,
            "executor_input_hash_unchanged": True,
            "executor_input_hash_equals_baseline": True,
            "executor_consumes_baseline_only": True,
            "candidate_shadow_hash_differs_from_executor": True,
            "candidate_plan_not_referenced_by_executor": True,
            "target_plan_not_replaced": True,
            "live_supervisor_source_unchanged": True,
            "live_config_dir_unchanged": True,
            "live_timer_service_not_enabled_or_invoked": True,
            "supervisor_not_run_for_execution": True,
            "no_remote_sync_in_p9am": True,
            "no_live_timer_path_load_in_p9am": True,
            "no_candidate_execution_in_p9am": True,
            "no_executor_input_mutation_in_p9am": True,
            "no_target_plan_replacement_in_p9am": True,
            "no_live_mutation_in_p9am": True,
            "zero_orders_fills_in_p9am": True,
        }
        p9am_payload = {
            **no_order,
            **no_live,
            "contract_version": "hv_balanced_dth60_coinglass_phase9am_default_off_readback_execution.v1",
            "status": "ready",
            "blockers": [],
            "dry_load_readback_scope": "owner_gated_default_off_observe_only_timer_path_dry_load_readback_execution_only",
            "p9am_default_off_observe_only_readback_ready": True,
            "default_off_observe_only_readback_execution_authorized": True,
            "executed_default_off_observe_only_readback": True,
            "dry_load_readback_executed": True,
            "dry_load_mode": "default_off_observe_only_timer_path_readback_harness_not_live_timer_service",
            "dry_load_outputs_under_proof_artifacts": True,
            "default_off_config_loaded": True,
            "default_off_hook_enabled": False,
            "observe_only_shadow_writer_enabled_in_proof_harness": True,
            "observe_only_shadow_readback_ready": True,
            "candidate_shadow_artifacts_written_count": 4,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "baseline_target_plan_byte_for_byte_unchanged": True,
            "executor_input_hash_unchanged": True,
            "executor_input_hash_equals_baseline": True,
            "executor_consumes_baseline_only": True,
            "candidate_shadow_hash_differs_from_executor": True,
            "candidate_plan_referenced_by_executor": False,
            "target_plan_replaced": False,
            "executor_input_changed": False,
            "eligible_for_owner_p9an_review": True,
            "recommended_next_gate": P9AN_GATE,
            "eligible_for_timer_hook_implementation": False,
            "eligible_for_hook_deployment": False,
            "eligible_for_live_timer_path_load": False,
            "eligible_for_supervisor_invocation": False,
            "eligible_for_remote_sync": False,
            "eligible_for_live_order_submission": False,
            "eligible_for_stage_governance_change": False,
            "timer_hook_implementation_authorized": False,
            "hook_deployment_authorized": False,
            "timer_path_load_authorized": False,
            "supervisor_invocation_authorized": False,
            "remote_sync_authorized": False,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "live_config_mutation_authorized": False,
            "operator_state_mutation_authorized": False,
            "timer_or_service_mutation_authorized": False,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifact_sink": "proof_artifacts_only",
            "live_supervisor_loads_candidate_hook": False,
            "live_supervisor_source_unchanged": True,
            "live_config_dir_unchanged": True,
            "live_timer_path_loaded": False,
            "live_timer_service_enabled_or_invoked": False,
            "entered_timer_path_dry_load_harness": True,
            "entered_live_timer_path": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "remote_execution_performed": False,
            "remote_control_plane_touched": False,
            "candidate_execution_performed": False,
            "wrote_live_hook_config": False,
            "implemented_hook": False,
            "deployed_hook": False,
            "loaded_hook": False,
            "owner_decision": {
                "decision": "approve_p9am_execute_default_off_observe_only_timer_path_dry_load_readback_only",
                "default_off_observe_only_readback_execution_approved": True,
                "candidate_shadow_artifact_write_approved_under_proof_artifacts": True,
                "candidate_execution_approved": False,
                "candidate_live_order_submission_approved": False,
                "timer_hook_implementation_approved": False,
                "hook_deployment_approved": False,
                "live_timer_path_load_approved": False,
                "production_timer_service_load_approved": False,
                "live_order_submission_approved": False,
                "target_plan_replacement_approved": False,
                "executor_input_mutation_approved": False,
                "live_config_mutation_approved": False,
                "operator_state_mutation_approved": False,
                "timer_or_service_mutation_approved": False,
                "remote_sync_approved": False,
                "supervisor_invocation_approved": False,
                "supervisor_run_approved": False,
                "repo_stage_change_approved": False,
            },
            "source_evidence": {
                "hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha},
                "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
                "live_config_dir": {"path": str(live_config_dir), "exists": True, "sha256": live_config_sha},
            },
            "gates": gates,
            "output_files": {
                "dry_load_execution_manifest": str(manifest),
                "default_off_config_readback": str(config),
                "observe_only_shadow_readback_summary": str(shadow),
                "executor_input_readback": str(executor),
                "control_boundary_readback": str(control),
                "baseline_target_plan": str(baseline_plan),
                "executor_input_plan": str(executor_plan),
                "candidate_shadow_plan": str(candidate_plan),
            },
        }
        self._deep_update(p9am_payload, p9am_overrides or {})
        self._write_json(phase9am, p9am_payload)
        return {
            "project_profile": project_profile,
            "phase9am": phase9am,
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
