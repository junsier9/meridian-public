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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9k_owner_review_after_dry_load_readback import (  # noqa: E402
    APPROVE_P9K_DECISION,
    build_phase9k,
    file_sha256,
    resolve_path,
)


class HvBalancedDth60CoinglassPhase9kOwnerReviewAfterDryLoadReadbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9k-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9k_ready_builds_review_packet_without_authorizing_load_or_orders(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase9k"

        summary, exit_code = build_phase9k(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 7, 19, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["review_scope"], "owner_gated_review_after_dry_load_readback_only")
        self.assertEqual(summary["owner_decision"]["decision"], APPROVE_P9K_DECISION)
        self.assertTrue(summary["owner_review_after_dry_load_readback_ready"])
        self.assertTrue(summary["eligible_for_owner_next_step_discussion"])
        self.assertFalse(summary["eligible_for_timer_hook_implementation"])
        self.assertFalse(summary["eligible_for_timer_path_load"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        self.assertFalse(summary["timer_hook_implementation_authorized"])
        self.assertFalse(summary["hook_deployment_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertTrue(summary["same_timestamp_context_proven"])
        self.assertTrue(summary["same_risk_inputs_proven"])
        self.assertTrue(summary["overlay_only_distance_to_high_60_contribution"])
        self.assertTrue(summary["research_contract_parity_zero_mismatches"])
        self.assertTrue(summary["dry_load_readback_from_proof_artifacts_only"])
        self.assertTrue(summary["executor_input_baseline_only_after_dry_load"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        proof_root = output_root / "proof_artifacts" / "p9k" / "20260607T190000Z"
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        self.assertTrue((proof_root / "owner_review_packet.json").exists())
        self.assertTrue((proof_root / "review_decision_matrix.json").exists())
        self.assertTrue((proof_root / "control_boundary_readback.json").exists())

    def test_phase9k_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9k(
            self._args(paths, output_root=self.temp_dir / "wrong-owner", owner_decision="approve_timer_path_load"),
            now_fn=lambda: datetime(2026, 6, 7, 19, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9k_review_only", summary["blockers"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def test_phase9k_blocks_when_p9j_indicates_timer_path_load(self) -> None:
        paths = self._write_ready_inputs(
            p9j_overrides={
                "live_timer_path_loaded": True,
                "gates": {"no_timer_path_load_in_p9j": False},
            }
        )

        summary, exit_code = build_phase9k(
            self._args(paths, output_root=self.temp_dir / "p9j-load"),
            now_fn=lambda: datetime(2026, 6, 7, 19, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9j_dry_load_readback_ready", summary["blockers"])
        self.assertIn("dry_load_from_proof_artifacts_only", summary["blockers"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["eligible_for_timer_path_load"])

    def test_phase9k_blocks_when_p9r_parity_is_not_zero(self) -> None:
        paths = self._write_ready_inputs(
            p9r_overrides={
                "row_parity": {"trigger_mismatch_count": 1},
                "candidate_scorer_loaded_into_timer": True,
            }
        )

        summary, exit_code = build_phase9k(
            self._args(paths, output_root=self.temp_dir / "p9r-bad"),
            now_fn=lambda: datetime(2026, 6, 7, 19, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9r_research_to_live_parity_ready", summary["blockers"])
        self.assertIn("overlay_only_distance_to_high_60_contribution", summary["blockers"])
        self.assertIn("research_contract_parity_zero_mismatches", summary["blockers"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9K_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase4_summary=str(paths["phase4"]),
            phase9e_summary=str(paths["phase9e"]),
            phase9j_summary=str(paths["phase9j"]),
            phase9r_summary=str(paths["phase9r"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        phase4_overrides: dict | None = None,
        p9e_overrides: dict | None = None,
        p9j_overrides: dict | None = None,
        p9r_overrides: dict | None = None,
        supervisor_text: str = "# no candidate hook import\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase4_path = self.temp_dir / "phase4.json"
        phase9e_path = self.temp_dir / "phase9e.json"
        phase9j_path = self.temp_dir / "phase9j.json"
        phase9r_path = self.temp_dir / "phase9r.json"
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
        phase4 = {
            **base_no_order,
            **base_no_mutation,
            "status": "ready",
            "blockers": [],
            "contract_version": "hv_balanced_dth60_coinglass_phase4_paired_target_plan_shadow.v1",
            "plan_only": True,
            "same_timestamp_context_proven": True,
            "same_risk_inputs_proven": True,
            "same_portfolio_engine_proven": True,
            "same_symbol_set_proven": True,
            "deterministic_target_difference_proven": True,
            "combined_candidate_trigger_proven": True,
            "target_factor": "distance_to_high_60",
            "mainnet_order_submission_authorized": False,
            "phase3_parity_proof_checks": {
                "disabled_wrapper_score_matches_core": True,
                "overlay_enabled_only_target_contribution_changed": True,
                "combined_candidate_trigger_proven": True,
            },
            "phase2_pit_proof_checks": {
                "no_future_fill_proven": True,
                "no_stale_fill_proven": True,
            },
            "phase2b_pit_proof_checks": {
                "no_future_fill_proven": True,
                "no_stale_fill_proven": True,
                "train_excludes_decision_row": True,
            },
            "combined_candidate_trigger_proof": {"proven": True},
        }
        p9e = {
            **base_no_order,
            **base_no_mutation,
            "status": "ready",
            "blockers": [],
            "fixture_scope": "owner_gated_timer_adjacent_local_fixture_only",
            "owner_decision": {
                "decision": "approve_p9e_timer_adjacent_local_fixture_only",
                "hook_deployment_approved": False,
                "timer_path_load_approved": False,
                "live_order_submission_approved": False,
                "target_plan_replacement_approved": False,
                "executor_input_mutation_approved": False,
            },
            "hook_enabled_inside_fixture": True,
            "default_live_hook_enabled": False,
            "executor_consumes_baseline_only": True,
            "candidate_plan_referenced_by_executor": False,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "live_supervisor_loads_candidate_hook": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "deployed_hook": False,
            "eligible_for_timer_path_load": False,
            "eligible_for_live_order_submission": False,
            "source_evidence": {
                "hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha},
                "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
            },
            "copied_timer_context_snapshot": {
                "source_shared_input_context": {"exists": True, "path": "shared_input_context.json"},
                "source_target_plan_diff": {"exists": True, "path": "target_plan_diff.csv"},
                "executor_input_plan_copy": {"sha256": "baseline-sha"},
                "baseline_target_plan_copy": {"sha256": "baseline-sha"},
            },
        }
        p9j = {
            **base_no_order,
            **base_no_mutation,
            "status": "ready",
            "blockers": [],
            "dry_load_readback_scope": "owner_gated_proof_artifacts_dry_load_readback_only",
            "proof_artifacts_dry_load_readback_ready": True,
            "eligible_for_owner_p9k_review": True,
            "eligible_for_timer_hook_implementation": False,
            "timer_hook_implementation_authorized": False,
            "hook_deployment_authorized": False,
            "timer_path_load_authorized": False,
            "live_order_submission_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "remote_sync_authorized": False,
            "supervisor_run_authorized": False,
            "dry_load_mode": "proof_artifacts_readback_only_not_timer_path",
            "dry_loaded_from_proof_artifacts_only": True,
            "live_timer_path_loaded": False,
            "live_timer_service_enabled_or_invoked": False,
            "live_supervisor_loads_candidate_hook": False,
            "live_supervisor_source_unchanged": True,
            "executor_input_hash_equals_baseline": True,
            "executor_consumes_baseline_only": True,
            "candidate_shadow_hash_differs_from_executor": True,
            "candidate_plan_referenced_by_executor": False,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
            "candidate_artifact_sink": "proof_artifacts_only",
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "remote_execution_performed": False,
            "owner_decision": {
                "decision": "approve_p9j_proof_artifacts_dry_load_readback_only",
                "proof_artifacts_dry_load_readback_approved": True,
                "timer_hook_implementation_approved": False,
                "hook_deployment_approved": False,
                "timer_path_load_approved": False,
                "live_order_submission_approved": False,
            },
            "source_evidence": {
                "hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha},
                "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
            },
            "supervisor_sha256_before_readback": supervisor_sha,
            "supervisor_sha256_after_readback": supervisor_sha,
            "gates": {
                "owner_decision_p9j_dry_load_readback_only": True,
                "project_stage_boundary_preserved": True,
                "p9i_diff_fixture_ready": True,
                "current_live_supervisor_not_loading_hook": True,
                "current_hook_hash_matches_p9i_source": True,
                "current_supervisor_hash_matches_p9i_source": True,
                "dry_load_source_files_exist": True,
                "dry_load_source_files_under_p9i_proof_artifacts": True,
                "dry_load_output_under_proof_artifacts": True,
                "dry_load_mode_not_live_timer_path": True,
                "dry_load_default_off": True,
                "dry_load_order_authority_disabled": True,
                "dry_load_executor_source_baseline_only": True,
                "live_timer_service_not_enabled_or_invoked": True,
                "supervisor_not_run_from_timer": True,
                "executor_input_hash_equals_baseline": True,
                "executor_consumes_baseline_only": True,
                "candidate_shadow_hash_differs_from_executor": True,
                "candidate_plan_not_referenced_by_executor": True,
                "candidate_artifacts_under_proof_artifacts_only": True,
                "live_supervisor_source_unchanged": True,
                "no_timer_path_load_in_p9j": True,
                "no_supervisor_run_in_p9j": True,
                "no_remote_execution_in_p9j": True,
                "no_executor_input_mutation_in_p9j": True,
                "no_target_plan_replacement_in_p9j": True,
                "no_live_mutation_in_p9j": True,
                "zero_orders_fills_in_p9j": True,
            },
        }
        p9r = {
            **base_no_order,
            **base_no_mutation,
            "status": "ready",
            "blockers": [],
            "scope": "research_to_live_parity_harness_only",
            "candidate_scorer_mode": "research_h10d_contract",
            "candidate_scorer_mode_scope": "proof_harness_only",
            "candidate_scorer_loaded_into_live_wrapper": False,
            "candidate_scorer_loaded_into_timer": False,
            "candidate_scorer_loaded_into_executor": False,
            "target_factor": "distance_to_high_60",
            "target_overlay_semantics": (
                "only distance_to_high_60 contribution is multiplied by 0.0 on candidate trigger rows"
            ),
            "row_parity": {
                "trigger_mismatch_count": 0,
                "multiplier_mismatch_count": 0,
                "target_contribution_mismatch_count": 0,
                "score_mismatch_count": 0,
            },
            "target_weight_parity": {"mismatch_count": 0},
            "slice_metric_parity": {"mismatch_count": 0},
            "retained_forward_artifact_compare": {"status": "ready"},
            "live_supervisor_timer_loaded_candidate_overlay": False,
        }
        self._deep_update(phase4, phase4_overrides or {})
        self._deep_update(p9e, p9e_overrides or {})
        self._deep_update(p9j, p9j_overrides or {})
        self._deep_update(p9r, p9r_overrides or {})
        self._write_json(phase4_path, phase4)
        self._write_json(phase9e_path, p9e)
        self._write_json(phase9j_path, p9j)
        self._write_json(phase9r_path, p9r)
        return {
            "project_profile": project_profile,
            "phase4": phase4_path,
            "phase9e": phase9e_path,
            "phase9j": phase9j_path,
            "phase9r": phase9r_path,
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


if __name__ == "__main__":
    unittest.main()
