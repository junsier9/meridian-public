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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9i_default_off_local_implementation_diff_fixture import (  # noqa: E402
    APPROVE_P9I_DECISION,
    build_phase9i,
    file_sha256,
    resolve_path,
)


class HvBalancedDth60CoinglassPhase9iDefaultOffLocalImplementationDiffFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9i-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9i_ready_builds_local_diff_fixture_without_authorizing_load_or_orders(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase9i"

        summary, exit_code = build_phase9i(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 7, 17, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["fixture_scope"], "owner_gated_default_off_local_implementation_diff_fixture_only")
        self.assertEqual(summary["owner_decision"]["decision"], APPROVE_P9I_DECISION)
        self.assertTrue(summary["implementation_diff_fixture_ready"])
        self.assertTrue(summary["eligible_for_owner_p9j_dry_load_review"])
        self.assertFalse(summary["eligible_for_timer_hook_implementation"])
        self.assertFalse(summary["timer_hook_implementation_authorized"])
        self.assertFalse(summary["hook_deployment_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["remote_sync_authorized"])
        self.assertFalse(summary["supervisor_run_authorized"])
        self.assertTrue(summary["implemented_hook_in_fixture"])
        self.assertFalse(summary["implemented_hook_in_live_supervisor"])
        self.assertFalse(summary["implementation_diff_fixture_applied_to_live_supervisor"])
        self.assertEqual(summary["supervisor_sha256_before_fixture"], summary["supervisor_sha256_after_fixture"])
        self.assertTrue(summary["disabled_hook_baseline_byte_for_byte_unchanged"])
        self.assertEqual(summary["disabled_hook_candidate_artifacts_written_count"], 0)
        self.assertTrue(summary["enabled_hook_writes_shadow_artifact_only"])
        self.assertTrue(summary["executor_input_hash_equals_baseline_target_hash"])
        self.assertTrue(summary["candidate_artifacts_under_proof_artifacts_only"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertFalse(summary["eligible_for_timer_path_load"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        proof_root = output_root / "proof_artifacts" / "p9i" / "20260607T170000Z"
        self.assertTrue((proof_root / "implementation_diff_fixture.json").exists())
        self.assertTrue((proof_root / "proposed_supervisor_hook_diff.patch").exists())
        self.assertTrue((proof_root / "disabled_hook_summary.json").exists())
        self.assertTrue((proof_root / "enabled_hook_summary.json").exists())
        self.assertTrue((output_root / "summary.json").exists())

    def test_phase9i_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9i(
            self._args(paths, output_root=self.temp_dir / "wrong-owner", owner_decision="approve_timer_load"),
            now_fn=lambda: datetime(2026, 6, 7, 17, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9i_fixture_only", summary["blockers"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def test_phase9i_blocks_when_p9h_authorizes_implementation_or_load(self) -> None:
        paths = self._write_ready_inputs(
            p9h_overrides={
                "eligible_for_timer_hook_implementation": True,
                "timer_path_load_authorized": True,
                "gates": {
                    "owner_decision_p9h_proposal_only": True,
                    "project_stage_boundary_preserved": True,
                    "p9g_timer_hook_review_pack_ready": True,
                    "current_live_supervisor_not_loading_hook": True,
                    "current_hook_hash_matches_p9g_source": True,
                    "proposal_output_under_proof_artifacts": True,
                    "proposal_default_off_required": True,
                    "proposal_timer_load_mode_is_not_live_timer_path": True,
                    "proposal_executor_input_source_baseline_only": True,
                    "proposal_candidate_order_authority_disabled": True,
                    "proposal_artifact_sink_proof_artifacts_only": True,
                    "future_implementation_gate_separate": True,
                    "future_timer_load_gate_separate": True,
                    "future_live_order_gate_separate": True,
                    "no_hook_implementation_in_p9h": False,
                    "no_hook_deployment_in_p9h": True,
                    "no_timer_path_load_in_p9h": False,
                    "no_supervisor_run_in_p9h": True,
                    "no_remote_execution_in_p9h": True,
                    "no_executor_input_mutation_in_p9h": True,
                    "no_target_plan_replacement_in_p9h": True,
                    "no_live_mutation_in_p9h": True,
                    "zero_orders_fills_in_p9h": True,
                },
            }
        )

        summary, exit_code = build_phase9i(
            self._args(paths, output_root=self.temp_dir / "bad-p9h"),
            now_fn=lambda: datetime(2026, 6, 7, 17, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9h_proposal_ready", summary["blockers"])
        self.assertFalse(summary["timer_hook_implementation_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def test_phase9i_blocks_when_current_supervisor_imports_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9i(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 7, 17, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9I_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9h_summary=str(paths["phase9h"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9h_overrides: dict | None = None,
        supervisor_text: str = "# no candidate hook import\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9h = self.temp_dir / "phase9h.json"
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
        p9h = {
            "status": "ready",
            "blockers": [],
            "proposal_scope": "owner_gated_timer_hook_implementation_load_proposal_only",
            "implementation_load_proposal_ready": True,
            "eligible_for_owner_implementation_load_review": True,
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
            "proposed_timer_load_mode": "proposal_only_not_loaded",
            "live_supervisor_loads_candidate_hook": False,
            "implemented_hook": False,
            "deployed_hook": False,
            "loaded_hook": False,
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
                "decision": "approve_p9h_timer_hook_implementation_load_proposal_only",
                "implementation_load_proposal_approved": True,
                "timer_hook_implementation_approved": False,
                "hook_deployment_approved": False,
                "timer_path_load_approved": False,
                "live_order_submission_approved": False,
            },
            "source_evidence": {
                "hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha},
                "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
            },
            "gates": {
                "owner_decision_p9h_proposal_only": True,
                "project_stage_boundary_preserved": True,
                "p9g_timer_hook_review_pack_ready": True,
                "current_live_supervisor_not_loading_hook": True,
                "current_hook_hash_matches_p9g_source": True,
                "proposal_output_under_proof_artifacts": True,
                "proposal_default_off_required": True,
                "proposal_timer_load_mode_is_not_live_timer_path": True,
                "proposal_executor_input_source_baseline_only": True,
                "proposal_candidate_order_authority_disabled": True,
                "proposal_artifact_sink_proof_artifacts_only": True,
                "future_implementation_gate_separate": True,
                "future_timer_load_gate_separate": True,
                "future_live_order_gate_separate": True,
                "no_hook_implementation_in_p9h": True,
                "no_hook_deployment_in_p9h": True,
                "no_timer_path_load_in_p9h": True,
                "no_supervisor_run_in_p9h": True,
                "no_remote_execution_in_p9h": True,
                "no_executor_input_mutation_in_p9h": True,
                "no_target_plan_replacement_in_p9h": True,
                "no_live_mutation_in_p9h": True,
                "zero_orders_fills_in_p9h": True,
            },
        }
        p9h.update(p9h_overrides or {})
        self._write_json(phase9h, p9h)
        return {
            "project_profile": project_profile,
            "phase9h": phase9h,
            "hook_module": hook_path,
            "supervisor": supervisor,
        }

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
