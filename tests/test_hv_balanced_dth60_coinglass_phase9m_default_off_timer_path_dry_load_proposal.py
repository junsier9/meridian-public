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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9m_default_off_timer_path_dry_load_proposal import (  # noqa: E402
    APPROVE_P9M_DECISION,
    build_phase9m,
    file_sha256,
    resolve_path,
)


class HvBalancedDth60CoinglassPhase9mDefaultOffDryLoadProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9m-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9m_ready_writes_only_default_off_proposal_artifacts(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase9m"

        summary, exit_code = build_phase9m(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 7, 21, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["proposal_scope"], "owner_gated_default_off_timer_path_dry_load_proposal_only")
        self.assertEqual(summary["owner_decision"]["decision"], APPROVE_P9M_DECISION)
        self.assertTrue(summary["default_off_timer_path_dry_load_proposal_ready"])
        self.assertTrue(summary["eligible_for_future_default_off_timer_path_dry_load_review"])
        self.assertTrue(summary["prepared_default_off_timer_path_dry_load_proposal"])
        self.assertTrue(summary["wrote_default_off_timer_path_dry_load_proposal_body"])
        self.assertEqual(summary["proposal_body_sink"], "proof_artifacts_only")
        self.assertTrue(summary["future_dry_load_gate_required"])
        self.assertFalse(summary["p9m_authorizes_timer_path_dry_load"])
        self.assertFalse(summary["eligible_for_timer_path_dry_load_execution"])
        self.assertFalse(summary["eligible_for_timer_hook_implementation"])
        self.assertFalse(summary["eligible_for_hook_deployment"])
        self.assertFalse(summary["eligible_for_timer_path_load"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        self.assertFalse(summary["timer_path_dry_load_authorized"])
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
        self.assertEqual(summary["execution_target_source"], "baseline_only")
        self.assertEqual(summary["candidate_artifact_sink"], "proof_artifacts_only")

        proof_root = output_root / "proof_artifacts" / "p9m" / "20260607T210000Z"
        proposal_path = proof_root / "default_off_timer_path_dry_load_proposal.json"
        self.assertTrue((output_root / "summary.json").exists())
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        self.assertTrue(proposal_path.exists())
        self.assertTrue((proof_root / "default_off_timer_path_dry_load_proposal.md").exists())
        self.assertTrue((proof_root / "proposal_acceptance_checklist.json").exists())
        self.assertTrue((proof_root / "non_authorization_matrix.json").exists())
        self.assertTrue((proof_root / "control_boundary_readback.json").exists())

        proposal = self._load_json(proposal_path)
        self.assertFalse(proposal["p9m_authorizes_timer_path_dry_load"])
        self.assertEqual(
            proposal["proposed_future_gate"],
            "P9N_default_off_timer_path_dry_load_readback_only_if_separately_requested",
        )
        self.assertTrue(proposal["proposed_future_dry_load_contract"]["default_off_required"])
        self.assertFalse(proposal["proposed_future_dry_load_contract"]["hook_config_enabled_default"])
        self.assertEqual(proposal["proposed_future_dry_load_contract"]["execution_target_source"], "baseline_only")
        self.assertEqual(proposal["proposed_future_dry_load_contract"]["candidate_artifact_sink"], "proof_artifacts_only")
        self.assertEqual(proposal["proposed_future_dry_load_contract"]["orders_submitted_must_equal"], 0)

    def test_phase9m_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "wrong-owner"

        summary, exit_code = build_phase9m(
            self._args(paths, output_root=output_root, owner_decision="approve_timer_path_dry_load"),
            now_fn=lambda: datetime(2026, 6, 7, 21, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9m_proposal_only", summary["blockers"])
        self.assertFalse(summary["default_off_timer_path_dry_load_proposal_ready"])
        self.assertFalse(summary["wrote_default_off_timer_path_dry_load_proposal_body"])
        self.assertFalse(summary["timer_path_dry_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        proof_root = output_root / "proof_artifacts" / "p9m" / "20260607T210500Z"
        self.assertFalse((proof_root / "default_off_timer_path_dry_load_proposal.json").exists())
        self.assertTrue((proof_root / "non_authorization_matrix.json").exists())

    def test_phase9m_blocks_when_p9l_no_longer_ready(self) -> None:
        paths = self._write_ready_inputs(
            p9l_overrides={
                "eligible_to_prepare_default_off_timer_path_dry_load_proposal": False,
                "blockers": ["synthetic_p9l_blocker"],
                "gates": {"future_proposal_must_keep_executor_baseline_only": False},
            }
        )

        summary, exit_code = build_phase9m(
            self._args(paths, output_root=self.temp_dir / "bad-p9l"),
            now_fn=lambda: datetime(2026, 6, 7, 21, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9l_proposal_preparation_gate_ready", summary["blockers"])
        self.assertFalse(summary["default_off_timer_path_dry_load_proposal_ready"])
        self.assertFalse(summary["timer_path_dry_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9m_blocks_when_current_supervisor_imports_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9m(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 7, 21, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["timer_path_dry_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9M_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9l_summary=str(paths["phase9l"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9l_overrides: dict | None = None,
        supervisor_text: str = "# no candidate hook import\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9l = self.temp_dir / "phase9l.json"
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
        p9l = {
            "status": "ready",
            "blockers": [],
            "gate_scope": "owner_gated_prepare_default_off_timer_path_dry_load_proposal_only",
            "p9l_prepare_default_off_timer_path_dry_load_proposal_gate_ready": True,
            "eligible_to_prepare_default_off_timer_path_dry_load_proposal": True,
            "prepared_default_off_timer_path_dry_load_proposal": False,
            "wrote_timer_path_dry_load_proposal_body": False,
            "future_proposal_default_off_required": True,
            "future_proposal_artifact_sink_required": "proof_artifacts_only",
            "future_proposal_executor_input_required": "baseline_only",
            "future_proposal_live_order_submission_authorized_required": False,
            "eligible_for_timer_hook_implementation": False,
            "eligible_for_hook_deployment": False,
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
                "decision": "approve_p9l_prepare_default_off_timer_path_dry_load_proposal_only",
                "prepare_default_off_timer_path_dry_load_proposal_approved": True,
                "write_proposal_artifact_approved": True,
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
            "gates": {
                "owner_decision_p9l_prepare_proposal_only": True,
                "project_stage_boundary_preserved": True,
                "p9k_owner_review_after_dry_load_ready": True,
                "current_live_supervisor_not_loading_hook": True,
                "current_hook_hash_matches_p9k_source": True,
                "current_supervisor_hash_matches_p9k_source": True,
                "proposal_preparation_gate_output_under_proof_artifacts": True,
                "future_proposal_must_be_default_off": True,
                "future_proposal_must_be_proof_artifacts_only": True,
                "future_proposal_must_keep_order_authority_disabled": True,
                "future_proposal_must_keep_executor_baseline_only": True,
                "no_proposal_body_written_in_p9l": True,
                "no_timer_hook_implementation_in_p9l": True,
                "no_hook_deployment_in_p9l": True,
                "no_timer_path_load_in_p9l": True,
                "no_supervisor_run_in_p9l": True,
                "no_remote_execution_in_p9l": True,
                "no_executor_input_mutation_in_p9l": True,
                "no_target_plan_replacement_in_p9l": True,
                "no_live_mutation_in_p9l": True,
                "zero_orders_fills_in_p9l": True,
            },
        }
        self._deep_update(p9l, p9l_overrides or {})
        self._write_json(phase9l, p9l)
        return {
            "project_profile": project_profile,
            "phase9l": phase9l,
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
