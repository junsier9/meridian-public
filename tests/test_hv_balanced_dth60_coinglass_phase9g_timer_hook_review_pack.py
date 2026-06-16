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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9g_timer_hook_review_pack import (  # noqa: E402
    APPROVE_P9G_DECISION,
    build_phase9g,
    file_sha256,
    resolve_path,
)


class HvBalancedDth60CoinglassPhase9gTimerHookReviewPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9g-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9g_ready_builds_review_pack_without_authorizing_timer_or_orders(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase9g"

        summary, exit_code = build_phase9g(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 7, 15, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["review_pack_scope"], "owner_gated_timer_hook_review_pack_only")
        self.assertEqual(summary["owner_decision"]["decision"], APPROVE_P9G_DECISION)
        self.assertTrue(summary["timer_hook_review_pack_ready"])
        self.assertTrue(summary["eligible_for_owner_timer_hook_review"])
        self.assertFalse(summary["eligible_for_timer_hook_implementation"])
        self.assertFalse(summary["timer_hook_implementation_authorized"])
        self.assertFalse(summary["hook_deployment_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertEqual(summary["candidate_order_authority"], "disabled")
        self.assertEqual(summary["execution_target_source"], "baseline_only")
        self.assertFalse(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertFalse(summary["eligible_for_timer_path_load"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        proof_root = output_root / "proof_artifacts" / "p9g" / "20260607T150000Z"
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        self.assertTrue((proof_root / "timer_hook_review_packet.json").exists())

    def test_phase9g_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9g(
            self._args(paths, output_root=self.temp_dir / "wrong-owner", owner_decision="approve_timer_path_load"),
            now_fn=lambda: datetime(2026, 6, 7, 15, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9g_review_pack_only", summary["blockers"])
        self.assertFalse(summary["timer_hook_implementation_authorized"])
        self.assertFalse(summary["eligible_for_timer_path_load"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def test_phase9g_blocks_when_p9f_says_timer_path_load_or_invocation_happened(self) -> None:
        paths = self._write_ready_inputs(
            p9f_overrides={
                "timer_path_invoked": True,
                "eligible_for_timer_path_load": True,
                "gates": {"p9b_timer_path_not_invoked": False},
            }
        )

        summary, exit_code = build_phase9g(
            self._args(paths, output_root=self.temp_dir / "p9f-timer-load"),
            now_fn=lambda: datetime(2026, 6, 7, 15, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9f_remote_proof_wrapper_ready", summary["blockers"])
        self.assertIn("no_timer_path_load_all_proofs", summary["blockers"])
        self.assertTrue(summary["timer_path_invoked"] is False)
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def test_phase9g_blocks_when_current_supervisor_imports_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9g(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 7, 15, 15, tzinfo=UTC),
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
        owner_decision: str = APPROVE_P9G_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9d_summary=str(paths["phase9d"]),
            phase9e_summary=str(paths["phase9e"]),
            phase9f_summary=str(paths["phase9f"]),
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
        p9d_overrides: dict | None = None,
        p9e_overrides: dict | None = None,
        p9f_overrides: dict | None = None,
        p9r_overrides: dict | None = None,
        supervisor_text: str = "# no candidate hook import\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9d = self.temp_dir / "phase9d.json"
        phase9e = self.temp_dir / "phase9e.json"
        phase9f = self.temp_dir / "phase9f.json"
        phase9r = self.temp_dir / "phase9r.json"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        self._write_json(
            project_profile,
            {
                "current_stage": "stage_1_research_readiness_only",
                "target_stage": "stage_4_automated_execution",
            },
        )
        supervisor.write_text(supervisor_text, encoding="utf-8")

        base_no_order = {
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "mainnet_order_submission_authorized": False,
            "exchange_order_submission": "disabled",
        }
        base_no_mutation = {
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
        }
        p9d = {
            **base_no_order,
            **base_no_mutation,
            "status": "ready",
            "blockers": [],
            "implementation_scope": "default_off_observe_only_hook_contract_only",
            "p9c_owner_decision_approved": True,
            "default_off_hook_enabled": False,
            "hook_deployment_authorized": False,
            "timer_path_load_authorized": False,
            "live_order_submission_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifact_sink": "proof_artifacts_only",
            "disabled_hook_baseline_output_unchanged": True,
            "disabled_hook_candidate_artifacts_written_count": 0,
            "enabled_fixture_execution_target_unchanged": True,
            "enabled_fixture_candidate_artifacts_under_proof_artifacts_only": True,
            "candidate_plan_referenced_by_executor": False,
            "live_supervisor_loads_candidate_hook": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "deployed_hook": False,
            "eligible_for_timer_path_load": False,
            "eligible_for_live_order_submission": False,
            "hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha},
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
            "source_evidence": {"hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha}},
        }
        p9f = {
            **base_no_order,
            **base_no_mutation,
            "status": "ready",
            "blockers": [],
            "wrapper_scope": "owner_gated_remote_proof_artifacts_wrapper_only",
            "owner_decision": {
                "decision": "approve_p9f_remote_proof_artifacts_wrapper_only",
                "remote_proof_artifacts_wrapper_approved": True,
                "remote_execution_approved": False,
                "hook_deployment_approved": False,
                "timer_path_load_approved": False,
                "live_order_submission_approved": False,
            },
            "p9e_ready": True,
            "p9b_remote_wrapper_ready": True,
            "remote_execution_performed": False,
            "remote_proof_artifacts_semantics": True,
            "uses_retained_remote_supervisor_artifacts": True,
            "wrapper_output_under_proof_artifacts": True,
            "executor_consumes_baseline_only": True,
            "executor_input_plan_hash_equals_baseline": True,
            "candidate_plan_referenced_by_executor": False,
            "candidate_shadow_plan_generated": False,
            "live_supervisor_loads_candidate_hook": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "remote_control_plane_unchanged": True,
            "candidate_artifact_sink": "proof_artifacts_only",
            "deployed_hook": False,
            "eligible_for_timer_path_load": False,
            "eligible_for_live_order_submission": False,
            "source_evidence": {"hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha}},
        }
        p9r = {
            "status": "ready",
            "blockers": [],
            "candidate_scorer_mode": "research_h10d_contract",
            "candidate_scorer_mode_scope": "proof_harness_only",
            "candidate_scorer_loaded_into_live_wrapper": False,
            "candidate_scorer_loaded_into_timer": False,
            "candidate_scorer_loaded_into_executor": False,
            "row_parity": {
                "trigger_mismatch_count": 0,
                "multiplier_mismatch_count": 0,
                "target_contribution_mismatch_count": 0,
                "score_mismatch_count": 0,
            },
            "target_weight_parity": {"mismatch_count": 0},
            "slice_metric_parity": {"mismatch_count": 0},
            "retained_forward_artifact_compare": {"status": "ready"},
            "orders_submitted": 0,
            "fills_observed": 0,
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "live_supervisor_timer_loaded_candidate_overlay": False,
        }
        p9d.update(p9d_overrides or {})
        p9e.update(p9e_overrides or {})
        p9f.update(p9f_overrides or {})
        p9r.update(p9r_overrides or {})
        self._write_json(phase9d, p9d)
        self._write_json(phase9e, p9e)
        self._write_json(phase9f, p9f)
        self._write_json(phase9r, p9r)
        return {
            "project_profile": project_profile,
            "phase9d": phase9d,
            "phase9e": phase9e,
            "phase9f": phase9f,
            "phase9r": phase9r,
            "hook_module": hook_path,
            "supervisor": supervisor,
        }

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
