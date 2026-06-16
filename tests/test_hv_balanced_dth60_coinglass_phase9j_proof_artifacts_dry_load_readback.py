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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9j_proof_artifacts_dry_load_readback import (  # noqa: E402
    APPROVE_P9J_DECISION,
    build_phase9j,
    file_sha256,
    resolve_path,
)


class HvBalancedDth60CoinglassPhase9jProofArtifactsDryLoadReadbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9j-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9j_ready_reads_p9i_proof_artifacts_without_timer_load_or_orders(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase9j"

        summary, exit_code = build_phase9j(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 7, 18, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["dry_load_readback_scope"], "owner_gated_proof_artifacts_dry_load_readback_only")
        self.assertEqual(summary["owner_decision"]["decision"], APPROVE_P9J_DECISION)
        self.assertTrue(summary["proof_artifacts_dry_load_readback_ready"])
        self.assertTrue(summary["eligible_for_owner_p9k_review"])
        self.assertFalse(summary["eligible_for_timer_hook_implementation"])
        self.assertFalse(summary["timer_hook_implementation_authorized"])
        self.assertFalse(summary["hook_deployment_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["remote_sync_authorized"])
        self.assertFalse(summary["supervisor_run_authorized"])
        self.assertEqual(summary["dry_load_mode"], "proof_artifacts_readback_only_not_timer_path")
        self.assertTrue(summary["dry_loaded_from_proof_artifacts_only"])
        self.assertFalse(summary["live_timer_path_loaded"])
        self.assertFalse(summary["live_timer_service_enabled_or_invoked"])
        self.assertTrue(summary["live_supervisor_source_unchanged"])
        self.assertTrue(summary["executor_input_hash_equals_baseline"])
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertTrue(summary["candidate_shadow_hash_differs_from_executor"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertFalse(summary["eligible_for_timer_path_load"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        proof_root = output_root / "proof_artifacts" / "p9j" / "20260607T180000Z"
        self.assertTrue((proof_root / "dry_load_manifest.json").exists())
        self.assertTrue((proof_root / "dry_load_readback.json").exists())
        self.assertTrue((proof_root / "control_plane_readback.json").exists())
        self.assertTrue((output_root / "summary.json").exists())

    def test_phase9j_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9j(
            self._args(paths, output_root=self.temp_dir / "wrong-owner", owner_decision="approve_timer_path_load"),
            now_fn=lambda: datetime(2026, 6, 7, 18, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9j_dry_load_readback_only", summary["blockers"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def test_phase9j_blocks_when_p9i_authorizes_implementation_or_load(self) -> None:
        paths = self._write_ready_inputs(
            p9i_overrides={
                "eligible_for_timer_hook_implementation": True,
                "timer_path_load_authorized": True,
                "gates": {
                    "owner_decision_p9i_fixture_only": True,
                    "project_stage_boundary_preserved": True,
                    "p9h_proposal_ready": True,
                    "current_live_supervisor_not_loading_hook": True,
                    "current_hook_hash_matches_p9h_source": True,
                    "current_supervisor_hash_matches_p9h_source": True,
                    "implementation_diff_fixture_written": True,
                    "proposed_diff_patch_written": True,
                    "implementation_diff_fixture_not_applied_to_live_supervisor": True,
                    "diff_fixture_default_off": True,
                    "diff_fixture_order_authority_disabled": True,
                    "diff_fixture_executor_source_baseline_only": True,
                    "disabled_hook_ready": True,
                    "disabled_hook_baseline_byte_for_byte_unchanged": True,
                    "disabled_hook_writes_zero_candidate_artifacts": True,
                    "enabled_hook_ready": True,
                    "enabled_hook_writes_shadow_artifact_only": True,
                    "executor_input_hash_equals_baseline_target_hash": True,
                    "candidate_artifacts_under_output_proof_root": True,
                    "candidate_order_authority_disabled": True,
                    "candidate_live_order_submission_authorized_false": True,
                    "no_timer_path_load_in_p9i": False,
                    "no_supervisor_run_in_p9i": True,
                    "no_remote_execution_in_p9i": True,
                    "no_executor_input_mutation_in_p9i": True,
                    "no_target_plan_replacement_in_p9i": True,
                    "no_live_mutation_in_p9i": True,
                    "zero_orders_fills_in_p9i": True,
                },
            }
        )

        summary, exit_code = build_phase9j(
            self._args(paths, output_root=self.temp_dir / "bad-p9i"),
            now_fn=lambda: datetime(2026, 6, 7, 18, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9i_diff_fixture_ready", summary["blockers"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def test_phase9j_blocks_when_dry_load_source_is_not_under_proof_artifacts(self) -> None:
        paths = self._write_ready_inputs(source_outside_proof_artifacts=True)

        summary, exit_code = build_phase9j(
            self._args(paths, output_root=self.temp_dir / "bad-source-path"),
            now_fn=lambda: datetime(2026, 6, 7, 18, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("dry_load_source_files_under_p9i_proof_artifacts", summary["blockers"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9J_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9i_summary=str(paths["phase9i"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9i_overrides: dict | None = None,
        source_outside_proof_artifacts: bool = False,
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9i = self.temp_dir / "phase9i.json"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        self._write_json(
            project_profile,
            {
                "current_stage": "stage_1_research_readiness_only",
                "target_stage": "stage_4_automated_execution",
            },
        )
        supervisor.write_text("# no candidate hook import\n", encoding="utf-8")
        supervisor_sha = file_sha256(supervisor)

        artifact_root = self.temp_dir / "p9i_artifact"
        proof_root = artifact_root / "proof_artifacts" / "p9i" / "20260607T170000Z"
        shadow_root = proof_root / "shadow_hook"
        outside_root = artifact_root / "outside_bundle"
        source_root = outside_root if source_outside_proof_artifacts else proof_root
        source_root.mkdir(parents=True, exist_ok=True)
        shadow_root.mkdir(parents=True, exist_ok=True)

        baseline_plan = artifact_root / "fixture_workspace" / "baseline_target_plan.json"
        executor_plan = artifact_root / "fixture_workspace" / "executor_input" / "target_plan.json"
        candidate_plan = shadow_root / "candidate_shadow_plan.json"
        self._write_json(baseline_plan, {"kind": "baseline", "positions": [{"symbol": "BTCUSDT", "weight": 0.1}]})
        self._write_json(executor_plan, {"kind": "baseline", "positions": [{"symbol": "BTCUSDT", "weight": 0.1}]})
        self._write_json(candidate_plan, {"kind": "candidate", "positions": [{"symbol": "ETHUSDT", "weight": 0.1}]})
        baseline_sha = file_sha256(baseline_plan)
        executor_sha = file_sha256(executor_plan)
        candidate_sha = file_sha256(candidate_plan)

        implementation_diff_fixture = source_root / "implementation_diff_fixture.json"
        proposed_patch = source_root / "proposed_supervisor_hook_diff.patch"
        disabled_summary_path = source_root / "disabled_hook_summary.json"
        enabled_summary_path = source_root / "enabled_hook_summary.json"
        self._write_json(
            implementation_diff_fixture,
            {
                "default_live_hook_enabled": False,
                "candidate_order_authority": "disabled",
                "execution_target_source": "baseline_only",
                "diff_applied_to_live_supervisor": False,
            },
        )
        proposed_patch.write_text("# fixture diff only\n+enabled: false\n", encoding="utf-8")
        executor_readback = shadow_root / "executor_input_readback.json"
        manifest = shadow_root / "manifest.json"
        self._write_json(
            executor_readback,
            {
                "contract_version": "hv_balanced_dth60_observe_only_shadow_hook.v1",
                "run_id": "20260607T170000Z-enabled",
                "execution_target_source": "baseline_only",
                "executor_input_plan": {"path": str(executor_plan), "exists": True, "sha256": executor_sha},
                "baseline_target_plan": {"path": str(baseline_plan), "exists": True, "sha256": baseline_sha},
                "candidate_shadow_plan": {"path": str(candidate_plan), "exists": True, "sha256": candidate_sha},
                "candidate_plan_referenced_by_executor": False,
            },
        )
        self._write_json(
            manifest,
            {
                "execution_target_source": "baseline_only",
                "candidate_order_authority": "disabled",
                "candidate_live_order_submission_authorized": False,
                "orders_submitted": 0,
                "fill_count": 0,
            },
        )
        disabled_hook = {
            "status": "ready",
            "blockers": [],
            "hook_enabled": False,
            "candidate_artifacts_written_count": 0,
            "baseline_target_plan_byte_for_byte_unchanged": True,
            "executor_input_plan_hash_unchanged": True,
            "executor_consumes_baseline_only": True,
            "orders_submitted": 0,
            "fill_count": 0,
            "exchange_order_submission": "disabled",
        }
        enabled_hook = {
            "status": "ready",
            "blockers": [],
            "hook_enabled": True,
            "proof_root": str(shadow_root),
            "candidate_artifacts_written_count": 4,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "candidate_plan_referenced_by_executor": False,
            "executor_consumes_baseline_only": True,
            "executor_input_plan_hash_unchanged": True,
            "baseline_target_plan_byte_for_byte_unchanged": True,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "exchange_order_submission": "disabled",
        }
        self._write_json(disabled_summary_path, disabled_hook)
        self._write_json(enabled_summary_path, enabled_hook)

        p9i = {
            "status": "ready",
            "blockers": [],
            "fixture_scope": "owner_gated_default_off_local_implementation_diff_fixture_only",
            "implementation_diff_fixture_ready": True,
            "eligible_for_owner_p9j_dry_load_review": True,
            "eligible_for_timer_hook_implementation": False,
            "timer_hook_implementation_authorized": False,
            "hook_deployment_authorized": False,
            "timer_path_load_authorized": False,
            "live_order_submission_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "remote_sync_authorized": False,
            "supervisor_run_authorized": False,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
            "candidate_artifact_sink": "proof_artifacts_only",
            "live_supervisor_loads_candidate_hook": False,
            "implemented_hook_in_live_supervisor": False,
            "implementation_diff_fixture_applied_to_live_supervisor": False,
            "supervisor_sha256_before_fixture": supervisor_sha,
            "supervisor_sha256_after_fixture": supervisor_sha,
            "disabled_hook_baseline_byte_for_byte_unchanged": True,
            "disabled_hook_candidate_artifacts_written_count": 0,
            "enabled_hook_writes_shadow_artifact_only": True,
            "executor_input_hash_equals_baseline_target_hash": True,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "candidate_plan_referenced_by_executor": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "remote_execution_performed": False,
            "eligible_for_timer_path_load": False,
            "eligible_for_live_order_submission": False,
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "owner_decision": {
                "decision": "approve_p9i_default_off_local_implementation_diff_fixture_only",
                "local_implementation_diff_fixture_approved": True,
                "timer_hook_implementation_approved": False,
                "hook_deployment_approved": False,
                "timer_path_load_approved": False,
                "live_order_submission_approved": False,
            },
            "source_evidence": {
                "hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha},
                "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
            },
            "output_files": {
                "implementation_diff_fixture": str(implementation_diff_fixture),
                "proposed_supervisor_hook_diff": str(proposed_patch),
                "disabled_hook_summary": str(disabled_summary_path),
                "enabled_hook_summary": str(enabled_summary_path),
            },
            "gates": {
                "owner_decision_p9i_fixture_only": True,
                "project_stage_boundary_preserved": True,
                "p9h_proposal_ready": True,
                "current_live_supervisor_not_loading_hook": True,
                "current_hook_hash_matches_p9h_source": True,
                "current_supervisor_hash_matches_p9h_source": True,
                "implementation_diff_fixture_written": True,
                "proposed_diff_patch_written": True,
                "implementation_diff_fixture_not_applied_to_live_supervisor": True,
                "diff_fixture_default_off": True,
                "diff_fixture_order_authority_disabled": True,
                "diff_fixture_executor_source_baseline_only": True,
                "disabled_hook_ready": True,
                "disabled_hook_baseline_byte_for_byte_unchanged": True,
                "disabled_hook_writes_zero_candidate_artifacts": True,
                "enabled_hook_ready": True,
                "enabled_hook_writes_shadow_artifact_only": True,
                "executor_input_hash_equals_baseline_target_hash": True,
                "candidate_artifacts_under_output_proof_root": True,
                "candidate_order_authority_disabled": True,
                "candidate_live_order_submission_authorized_false": True,
                "no_timer_path_load_in_p9i": True,
                "no_supervisor_run_in_p9i": True,
                "no_remote_execution_in_p9i": True,
                "no_executor_input_mutation_in_p9i": True,
                "no_target_plan_replacement_in_p9i": True,
                "no_live_mutation_in_p9i": True,
                "zero_orders_fills_in_p9i": True,
            },
        }
        p9i.update(p9i_overrides or {})
        self._write_json(phase9i, p9i)
        return {
            "project_profile": project_profile,
            "phase9i": phase9i,
            "hook_module": hook_path,
            "supervisor": supervisor,
        }

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
