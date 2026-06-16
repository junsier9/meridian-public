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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bn_review_after_p9bm import (  # noqa: E402
    APPROVE_P9BN_DECISION,
    CONTRACT_VERSION as P9BN_CONTRACT,
    P9BO_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bo_prepare_timer_path_shadow_cycles_proposal import (  # noqa: E402
    APPROVE_P9BO_DECISION,
    P9BP_GATE,
    build_p9bo,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9BOPrepareTimerPathShadowCyclesProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bo-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_p9bo_prepares_proposal_review_package_only(self) -> None:
        paths = self._write_ready_p9bn_bundle()

        summary, exit_code = build_p9bo(
            self._args(paths, output_root=self.temp_dir / "p9bo"),
            now_fn=lambda: datetime(2026, 6, 10, 2, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9bo_proposal_review_package_ready"])
        self.assertTrue(summary["proposal_review_package_prepared"])
        self.assertEqual(summary["allowed_next_gate"], P9BP_GATE)
        self.assertEqual(summary["recommended_next_gate"], P9BP_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(summary["continuous_timer_path_shadow_cycles_execution_authorized"])
        self.assertFalse(summary["timer_path_shadow_readback_execution_authorized"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertFalse(summary["remote_sync_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["entered_timer_path"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        package = _load_json(Path(summary["output_files"]["proposal_review_package"]))
        acceptance = _load_json(Path(summary["output_files"]["acceptance_contract"]))
        matrix = _load_json(Path(summary["output_files"]["non_authorization_matrix"]))
        control = _load_json(Path(summary["output_files"]["control_boundary_readback"]))
        self.assertTrue(package["package_prepared"])
        self.assertEqual(package["proposed_future_gate"], P9BP_GATE)
        self.assertEqual(acceptance["minimum_cycle_count"], 3)
        self.assertTrue(acceptance["fresh_proof_each_cycle"])
        self.assertTrue(acceptance["baseline_only_executor_input_each_cycle"])
        self.assertTrue(acceptance["candidate_shadow_only_each_cycle"])
        self.assertTrue(acceptance["candidate_artifacts_under_proof_artifacts_only_each_cycle"])
        self.assertTrue(acceptance["candidate_plan_must_not_be_referenced_by_executor_each_cycle"])
        self.assertTrue(acceptance["zero_order_delta_each_cycle"])
        self.assertTrue(acceptance["zero_cancel_delta_each_cycle"])
        self.assertTrue(acceptance["zero_fill_delta_each_cycle"])
        self.assertFalse(acceptance["live_order_submission_authorized"])
        self.assertTrue(matrix["authorizations"]["proposal_review_package_preparation"])
        self.assertFalse(matrix["authorizations"]["continuous_timer_path_shadow_cycles_execution"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(control["ran_supervisor"])
        self.assertFalse(control["live_timer_path_loaded"])
        self.assertEqual(control["orders_submitted"], 0)
        self.assertIn("proof_artifacts", Path(summary["output_files"]["proposal_review_package"]).parts)

    def test_wrong_owner_decision_blocks_without_authorizing_execution(self) -> None:
        paths = self._write_ready_p9bn_bundle()

        summary, exit_code = build_p9bo(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_continuous_timer_path_cycles_execution",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 2, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9bo_prepare_package_only", summary["blockers"])
        self.assertFalse(summary["p9bo_proposal_review_package_ready"])
        self.assertFalse(summary["continuous_timer_path_shadow_cycles_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_bad_p9bn_allowed_next_gate_blocks(self) -> None:
        paths = self._write_ready_p9bn_bundle(p9bn_overrides={"allowed_next_gate": "P9LIVE_ORDER"})

        summary, exit_code = build_p9bo(
            self._args(paths, output_root=self.temp_dir / "bad-p9bn"),
            now_fn=lambda: datetime(2026, 6, 10, 2, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bn_ready_for_p9bo", summary["blockers"])
        self.assertIn("p9bn_allows_p9bo_only", summary["blockers"])
        self.assertFalse(summary["timer_path_shadow_readback_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_current_supervisor_loading_hook_blocks(self) -> None:
        paths = self._write_ready_p9bn_bundle(
            supervisor_text="from enhengclaw.live_trading.dth60_observe_only_shadow_hook import run\n"
        )

        summary, exit_code = build_p9bo(
            self._args(paths, output_root=self.temp_dir / "supervisor-loads-hook"),
            now_fn=lambda: datetime(2026, 6, 10, 2, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bn_ready_for_p9bo", summary["blockers"])
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BO_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9bn_summary=str(paths["p9bn_summary"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9bn_bundle(
        self,
        *,
        p9bn_overrides: dict[str, object] | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        p9bn_root = self.temp_dir / "p9bn"
        proof_root = p9bn_root / "proof_artifacts" / "p9bn" / "run"
        summary_path = p9bn_root / "summary.json"
        owner_path = p9bn_root / "owner_decision_record.json"
        review_path = proof_root / "owner_review_packet.json"
        checklist_path = proof_root / "sufficiency_checklist.json"
        matrix_path = proof_root / "non_authorization_matrix.json"
        control_path = proof_root / "control_boundary_readback.json"

        live_config_dir.mkdir(parents=True)
        hook_module.write_text("# hook fixture\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        _write_json(project_profile, {"current_stage": "stage_1_research_readiness_only"})

        source = {
            "hook_module": {"path": str(hook_module), "exists": True, "sha256": file_sha256(hook_module)},
            "live_supervisor": {
                "path": str(supervisor),
                "exists": True,
                "sha256": file_sha256(supervisor),
            },
            "live_config_dir": {
                "path": str(live_config_dir),
                "exists": True,
                "sha256": tree_sha256(live_config_dir),
            },
        }
        owner = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bn_owner_decision.v1",
            "decision": APPROVE_P9BN_DECISION,
            "retained_evidence_review_approved": True,
            "p9bm_sufficiency_review_approved": True,
            "future_proposal_review_gate_discussion_approved": True,
            "prepare_proposal_approved": False,
            "proposal_execution_approved": False,
            "next_gate_execution_approved": False,
        }
        review = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bn_owner_review_packet.v1",
            "p9bm_retained_evidence_sufficient": True,
            "sufficient_for_next_proposal_review_gate": True,
            "allowed_next_gate": P9BO_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "proposal_preparation_authorized": False,
            "next_gate_execution_authorized": False,
            "timer_path_shadow_readback_execution_authorized": False,
            "supervisor_invocation_authorized": False,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        checklist = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bn_sufficiency_checklist.v1",
            "checks": {
                "p9bm_status_ready": True,
                "retained_pit_safe_account_fixture": True,
                "pit_safe_position_reference_fixture_ready": True,
                "supervisor_readback_no_order_ready": True,
                "hook_shadow_readback_ready": True,
                "baseline_only_executor": True,
                "candidate_plan_not_referenced_by_executor": True,
                "zero_order_cancel_fill_trade_delta": True,
            },
        }
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bn_non_authorization_matrix.v1",
            "authorizations": {
                "retained_evidence_review": True,
                "future_proposal_review_gate_discussion": True,
            },
        }
        for key in (
            "prepare_proposal",
            "proposal_execution",
            "next_gate_execution",
            "timer_path_shadow_readback_execution",
            "candidate_execution",
            "candidate_live_order_submission",
            "live_order_submission",
            "target_plan_replacement",
            "executor_input_mutation",
            "live_config_mutation",
            "operator_state_mutation",
            "timer_or_service_mutation",
            "remote_sync",
            "remote_execution",
            "supervisor_invocation",
            "supervisor_run",
            "stage_governance_change",
        ):
            matrix["authorizations"][key] = False
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bn_control_boundary_readback.v1",
            "live_supervisor_source_unchanged": True,
            "live_supervisor_loads_candidate_hook": False,
            "live_config_dir_unchanged": True,
            "proposal_preparation_authorized": False,
            "next_gate_execution_authorized": False,
            "timer_path_shadow_readback_execution_authorized": False,
            "supervisor_invocation_authorized": False,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        false_keys = (
            "continuous_timer_path_shadow_cycles_execution_authorized",
            "timer_path_shadow_readback_execution_authorized",
            "timer_path_shadow_readback_authorized",
            "dry_load_readback_execution_authorized",
            "timer_hook_implementation_authorized",
            "hook_deployment_authorized",
            "timer_path_load_authorized",
            "supervisor_invocation_authorized",
            "supervisor_run_authorized",
            "remote_sync_authorized",
            "remote_execution_authorized",
            "candidate_execution_authorized",
            "candidate_live_order_submission_authorized",
            "live_order_submission_authorized",
            "target_plan_replacement_authorized",
            "executor_input_mutation_authorized",
            "live_config_mutation_authorized",
            "operator_state_mutation_authorized",
            "timer_or_service_mutation_authorized",
            "production_timer_service_load_authorized",
            "repo_stage_change_authorized",
            "continuous_timer_path_shadow_cycles_executed",
            "entered_timer_path",
            "live_timer_path_loaded",
            "live_timer_service_enabled_or_invoked",
            "ran_supervisor",
            "timer_path_invoked",
            "remote_execution_performed",
            "remote_control_plane_touched",
            "candidate_execution_performed",
            "applied_to_live",
            "live_config_changed",
            "operator_state_changed",
            "timer_state_changed",
            "wrote_live_hook_config",
            "implemented_hook",
            "deployed_hook",
            "loaded_hook",
            "target_plan_replaced",
            "executor_input_changed",
        )
        for target in (review, control):
            for key in false_keys:
                target[key] = False
        for key in false_keys:
            owner[key.replace("_authorized", "_approved")] = False

        _write_json(owner_path, owner)
        _write_json(review_path, review)
        _write_json(checklist_path, checklist)
        _write_json(matrix_path, matrix)
        _write_json(control_path, control)
        summary = {
            "contract_version": P9BN_CONTRACT,
            "status": "ready",
            "blockers": [],
            "p9bn_owner_gate_ready": True,
            "p9bm_retained_evidence_sufficient": True,
            "sufficient_for_next_proposal_review_gate": True,
            "eligible_for_future_p9bo_proposal_review_gate_request": True,
            "allowed_next_gate": P9BO_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "proposal_preparation_authorized": False,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "shadow_only_not_executor",
            "candidate_artifact_sink": "proof_artifacts_only",
            "executor_consumes_baseline_only": True,
            "candidate_plan_referenced_by_executor": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "source_evidence": source,
            "output_files": {
                "summary": str(summary_path),
                "owner_decision_record": str(owner_path),
                "owner_review_packet": str(review_path),
                "sufficiency_checklist": str(checklist_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        for key in false_keys:
            summary[key] = False
        if p9bn_overrides:
            summary.update(p9bn_overrides)
        _write_json(summary_path, summary)
        return {
            "project_profile": project_profile,
            "p9bn_summary": summary_path,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
