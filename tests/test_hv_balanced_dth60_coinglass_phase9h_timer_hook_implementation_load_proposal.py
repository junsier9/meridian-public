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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9h_timer_hook_implementation_load_proposal import (  # noqa: E402
    APPROVE_P9H_DECISION,
    build_phase9h,
    file_sha256,
    resolve_path,
)


class HvBalancedDth60CoinglassPhase9hTimerHookImplementationLoadProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9h-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9h_ready_builds_proposal_without_authorizing_implementation_load_or_orders(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase9h"

        summary, exit_code = build_phase9h(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 7, 16, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["proposal_scope"], "owner_gated_timer_hook_implementation_load_proposal_only")
        self.assertEqual(summary["owner_decision"]["decision"], APPROVE_P9H_DECISION)
        self.assertTrue(summary["implementation_load_proposal_ready"])
        self.assertTrue(summary["eligible_for_owner_implementation_load_review"])
        self.assertFalse(summary["eligible_for_timer_hook_implementation"])
        self.assertFalse(summary["timer_hook_implementation_authorized"])
        self.assertFalse(summary["hook_deployment_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["remote_sync_authorized"])
        self.assertFalse(summary["supervisor_run_authorized"])
        self.assertEqual(summary["candidate_order_authority"], "disabled")
        self.assertEqual(summary["execution_target_source"], "baseline_only")
        self.assertEqual(summary["candidate_artifact_sink"], "proof_artifacts_only")
        self.assertEqual(summary["proposed_timer_load_mode"], "proposal_only_not_loaded")
        self.assertFalse(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["implemented_hook"])
        self.assertFalse(summary["loaded_hook"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertFalse(summary["eligible_for_timer_path_load"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        proof_root = output_root / "proof_artifacts" / "p9h" / "20260607T160000Z"
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        self.assertTrue((proof_root / "implementation_load_proposal.json").exists())
        self.assertTrue((proof_root / "future_gate_checklist.json").exists())

    def test_phase9h_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9h(
            self._args(paths, output_root=self.temp_dir / "wrong-owner", owner_decision="approve_timer_path_load"),
            now_fn=lambda: datetime(2026, 6, 7, 16, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9h_proposal_only", summary["blockers"])
        self.assertFalse(summary["timer_hook_implementation_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def test_phase9h_blocks_when_p9g_authorizes_implementation_or_load(self) -> None:
        paths = self._write_ready_inputs(
            p9g_overrides={
                "eligible_for_timer_hook_implementation": True,
                "timer_path_load_authorized": True,
                "gates": {
                    "owner_decision_p9g_review_pack_only": True,
                    "project_stage_boundary_preserved": True,
                    "p9r_research_to_live_parity_ready": True,
                    "p9d_default_off_hook_ready": True,
                    "p9e_timer_adjacent_fixture_ready": True,
                    "p9f_remote_proof_wrapper_ready": True,
                    "current_live_supervisor_not_loading_hook": True,
                    "hook_module_hash_consistent": True,
                    "default_live_hook_disabled": True,
                    "executor_baseline_only_all_proofs": True,
                    "candidate_plan_not_referenced_all_proofs": True,
                    "candidate_artifacts_proof_only_all_proofs": True,
                    "no_timer_path_load_all_proofs": False,
                    "no_live_mutation_all_proofs": True,
                    "zero_orders_fills_all_proofs": True,
                },
            }
        )

        summary, exit_code = build_phase9h(
            self._args(paths, output_root=self.temp_dir / "p9g-load-authorized"),
            now_fn=lambda: datetime(2026, 6, 7, 16, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9g_timer_hook_review_pack_ready", summary["blockers"])
        self.assertFalse(summary["timer_hook_implementation_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def test_phase9h_blocks_when_current_supervisor_imports_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9h(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 7, 16, 15, tzinfo=UTC),
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
        owner_decision: str = APPROVE_P9H_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9g_summary=str(paths["phase9g"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9g_overrides: dict | None = None,
        supervisor_text: str = "# no candidate hook import\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9g = self.temp_dir / "phase9g.json"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        self._write_json(
            project_profile,
            {
                "current_stage": "stage_1_research_readiness_only",
                "target_stage": "stage_4_automated_execution",
            },
        )
        supervisor.write_text(supervisor_text, encoding="utf-8")
        p9g = {
            "status": "ready",
            "blockers": [],
            "review_pack_scope": "owner_gated_timer_hook_review_pack_only",
            "timer_hook_review_pack_ready": True,
            "eligible_for_owner_timer_hook_review": True,
            "eligible_for_timer_hook_implementation": False,
            "timer_hook_implementation_authorized": False,
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
            "default_live_hook_enabled": False,
            "live_supervisor_loads_candidate_hook": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "remote_execution_performed": False,
            "deployed_hook": False,
            "eligible_for_timer_path_load": False,
            "eligible_for_live_order_submission": False,
            "eligible_for_stage_governance_change": False,
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "owner_decision": {
                "decision": "approve_p9g_timer_hook_review_pack_only",
                "timer_hook_review_pack_approved": True,
                "timer_hook_implementation_approved": False,
                "hook_deployment_approved": False,
                "timer_path_load_approved": False,
                "live_order_submission_approved": False,
            },
            "source_evidence": {
                "hook_module": {
                    "path": str(hook_path),
                    "exists": True,
                    "sha256": hook_sha,
                }
            },
            "gates": {
                "owner_decision_p9g_review_pack_only": True,
                "project_stage_boundary_preserved": True,
                "p9r_research_to_live_parity_ready": True,
                "p9d_default_off_hook_ready": True,
                "p9e_timer_adjacent_fixture_ready": True,
                "p9f_remote_proof_wrapper_ready": True,
                "current_live_supervisor_not_loading_hook": True,
                "hook_module_hash_consistent": True,
                "default_live_hook_disabled": True,
                "executor_baseline_only_all_proofs": True,
                "candidate_plan_not_referenced_all_proofs": True,
                "candidate_artifacts_proof_only_all_proofs": True,
                "no_timer_path_load_all_proofs": True,
                "no_live_mutation_all_proofs": True,
                "zero_orders_fills_all_proofs": True,
            },
        }
        p9g.update(p9g_overrides or {})
        self._write_json(phase9g, p9g)
        return {
            "project_profile": project_profile,
            "phase9g": phase9g,
            "hook_module": hook_path,
            "supervisor": supervisor,
        }

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
