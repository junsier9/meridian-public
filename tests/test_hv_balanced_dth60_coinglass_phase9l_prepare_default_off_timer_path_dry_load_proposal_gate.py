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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9l_prepare_default_off_timer_path_dry_load_proposal_gate import (  # noqa: E402
    APPROVE_P9L_DECISION,
    build_phase9l,
    file_sha256,
    resolve_path,
)


class HvBalancedDth60CoinglassPhase9lPrepareDryLoadProposalGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9l-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9l_ready_allows_only_future_proposal_preparation(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase9l"

        summary, exit_code = build_phase9l(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 7, 20, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["gate_scope"], "owner_gated_prepare_default_off_timer_path_dry_load_proposal_only")
        self.assertEqual(summary["owner_decision"]["decision"], APPROVE_P9L_DECISION)
        self.assertTrue(summary["p9l_prepare_default_off_timer_path_dry_load_proposal_gate_ready"])
        self.assertTrue(summary["eligible_to_prepare_default_off_timer_path_dry_load_proposal"])
        self.assertFalse(summary["prepared_default_off_timer_path_dry_load_proposal"])
        self.assertFalse(summary["eligible_for_timer_hook_implementation"])
        self.assertFalse(summary["eligible_for_hook_deployment"])
        self.assertFalse(summary["eligible_for_timer_path_load"])
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
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        proof_root = output_root / "proof_artifacts" / "p9l" / "20260607T200000Z"
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        self.assertTrue((proof_root / "proposal_preparation_gate.json").exists())
        self.assertTrue((proof_root / "non_authorization_matrix.json").exists())
        self.assertTrue((proof_root / "control_boundary_readback.json").exists())

    def test_phase9l_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9l(
            self._args(paths, output_root=self.temp_dir / "wrong-owner", owner_decision="approve_timer_path_load"),
            now_fn=lambda: datetime(2026, 6, 7, 20, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9l_prepare_proposal_only", summary["blockers"])
        self.assertFalse(summary["eligible_to_prepare_default_off_timer_path_dry_load_proposal"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9l_blocks_when_p9k_authorizes_timer_load(self) -> None:
        paths = self._write_ready_inputs(
            p9k_overrides={
                "eligible_for_timer_path_load": True,
                "timer_path_load_authorized": True,
                "gates": {"no_timer_path_load_in_p9k": False},
            }
        )

        summary, exit_code = build_phase9l(
            self._args(paths, output_root=self.temp_dir / "bad-p9k"),
            now_fn=lambda: datetime(2026, 6, 7, 20, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9k_owner_review_after_dry_load_ready", summary["blockers"])
        self.assertFalse(summary["eligible_to_prepare_default_off_timer_path_dry_load_proposal"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9l_blocks_when_current_supervisor_imports_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9l(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 7, 20, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9L_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9k_summary=str(paths["phase9k"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9k_overrides: dict | None = None,
        supervisor_text: str = "# no candidate hook import\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9k = self.temp_dir / "phase9k.json"
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
        p9k = {
            "status": "ready",
            "blockers": [],
            "review_scope": "owner_gated_review_after_dry_load_readback_only",
            "owner_review_after_dry_load_readback_ready": True,
            "eligible_for_owner_next_step_discussion": True,
            "eligible_for_timer_hook_implementation": False,
            "eligible_for_timer_path_load": False,
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
            "same_timestamp_context_proven": True,
            "same_risk_inputs_proven": True,
            "overlay_only_distance_to_high_60_contribution": True,
            "research_contract_parity_zero_mismatches": True,
            "dry_load_readback_from_proof_artifacts_only": True,
            "executor_input_baseline_only_after_dry_load": True,
            "candidate_plan_referenced_by_executor": False,
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
                "decision": "approve_p9k_owner_review_after_dry_load_readback_only",
                "owner_review_after_dry_load_readback_approved": True,
                "timer_hook_implementation_approved": False,
                "hook_deployment_approved": False,
                "timer_path_load_approved": False,
                "live_order_submission_approved": False,
                "target_plan_replacement_approved": False,
                "executor_input_mutation_approved": False,
                "remote_sync_approved": False,
                "supervisor_run_approved": False,
                "repo_stage_change_approved": False,
            },
            "source_evidence": {
                "hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha},
                "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
            },
            "gates": {
                "owner_decision_p9k_review_only": True,
                "project_stage_boundary_preserved": True,
                "phase4_same_context_ready": True,
                "p9e_timer_adjacent_same_context_ready": True,
                "p9j_dry_load_readback_ready": True,
                "p9r_research_to_live_parity_ready": True,
                "same_timestamp_context_proven": True,
                "same_risk_inputs_proven": True,
                "overlay_only_distance_to_high_60_contribution": True,
                "research_contract_parity_zero_mismatches": True,
                "dry_load_from_proof_artifacts_only": True,
                "executor_input_baseline_only_after_dry_load": True,
                "candidate_plan_not_referenced_by_executor": True,
                "timer_path_not_loaded_or_invoked": True,
                "current_live_supervisor_not_loading_hook": True,
                "review_output_under_proof_artifacts": True,
                "no_timer_hook_implementation_in_p9k": True,
                "no_hook_deployment_in_p9k": True,
                "no_timer_path_load_in_p9k": True,
                "no_supervisor_run_in_p9k": True,
                "no_remote_execution_in_p9k": True,
                "no_executor_input_mutation_in_p9k": True,
                "no_target_plan_replacement_in_p9k": True,
                "no_live_mutation_in_p9k": True,
                "zero_orders_fills_in_p9k": True,
            },
        }
        self._deep_update(p9k, p9k_overrides or {})
        self._write_json(phase9k, p9k)
        return {
            "project_profile": project_profile,
            "phase9k": phase9k,
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
