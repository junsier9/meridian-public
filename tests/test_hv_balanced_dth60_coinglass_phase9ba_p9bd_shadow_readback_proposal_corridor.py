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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9az_prepare_shadow_readback_gate_package import (  # noqa: E402
    APPROVE_P9AZ_DECISION,
    CONTRACT_VERSION as P9AZ_CONTRACT,
    FALSE_EXECUTION_KEYS,
    P9BA_GATE,
    P9BA_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ba_p9bd_shadow_readback_proposal_corridor import (  # noqa: E402
    APPROVE_CORRIDOR_DECISION,
    P9BB_GATE,
    P9BC_GATE,
    P9BD_GATE,
    P9BE_GATE,
    PROOF_FALSE_AUTHORIZATIONS,
    build_corridor,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9BAP9BDShadowReadbackProposalCorridorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9ba-p9bd-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_corridor_ready_runs_p9ba_p9bd_proof_only(self) -> None:
        paths = self._write_ready_p9az_bundle()
        output_root = self.temp_dir / "corridor"

        summary, exit_code = build_corridor(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 18, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9ba_p9bd_corridor_ready"])
        self.assertEqual(summary["completed_gates"], ["P9BA", "P9BB", "P9BC", "P9BD"])
        self.assertTrue(summary["p9ba_review_ready"])
        self.assertTrue(summary["p9bb_permission_ready"])
        self.assertTrue(summary["p9bc_proposal_package_ready"])
        self.assertTrue(summary["p9bd_retained_readiness_review_ready"])
        self.assertEqual(summary["allowed_next_gate"], P9BE_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(summary["dry_load_readback_execution_authorized"])
        self.assertFalse(summary["timer_path_shadow_readback_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = output_root / "proof_artifacts"
        p9ba_summary = self._load_json(proof_root / "p9ba" / "20260608T180000Z" / "summary.json")
        p9bb_summary = self._load_json(proof_root / "p9bb" / "20260608T180000Z" / "summary.json")
        p9bc_summary = self._load_json(proof_root / "p9bc" / "20260608T180000Z" / "summary.json")
        p9bd_summary = self._load_json(proof_root / "p9bd" / "20260608T180000Z" / "summary.json")
        proposal = self._load_json(
            proof_root / "p9bc" / "20260608T180000Z" / "shadow_readback_proposal_package.json"
        )
        readiness = self._load_json(proof_root / "p9bd" / "20260608T180000Z" / "readiness_review.json")
        self.assertTrue(p9ba_summary["p9ba_review_ready"])
        self.assertEqual(p9ba_summary["allowed_next_gate"], P9BB_GATE)
        self.assertTrue(p9bb_summary["p9bb_permission_ready"])
        self.assertEqual(p9bb_summary["allowed_next_gate"], P9BC_GATE)
        self.assertTrue(p9bc_summary["generated_proposal_package"])
        self.assertEqual(p9bc_summary["allowed_next_gate"], P9BD_GATE)
        self.assertTrue(p9bd_summary["eligible_for_future_p9be_owner_gate_request"])
        self.assertEqual(proposal["allowed_next_gate"], P9BD_GATE)
        self.assertFalse(proposal["default_enabled"])
        self.assertTrue(proposal["observe_only"])
        self.assertEqual(proposal["candidate_order_authority"], "disabled")
        self.assertEqual(proposal["executor_target_source"], "baseline_only")
        self.assertFalse(proposal["proposal_contract"]["live_order_submission_authorized"])
        self.assertTrue(readiness["sufficient_for_future_timer_path_shadow_readback_owner_gate_request"])
        self.assertEqual(readiness["allowed_next_gate"], P9BE_GATE)
        self.assertFalse(readiness["live_order_submission_authorized"])

    def test_corridor_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_p9az_bundle()

        summary, exit_code = build_corridor(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_submission",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 18, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9ba_p9bd_corridor", summary["blockers"])
        self.assertFalse(summary["p9ba_p9bd_corridor_ready"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_corridor_blocks_if_p9az_does_not_point_to_p9ba(self) -> None:
        paths = self._write_ready_p9az_bundle(
            p9az_overrides={"allowed_next_gate": "P9BAD_live_order_gate", "recommended_next_gate": "P9BAD"}
        )

        summary, exit_code = build_corridor(
            self._args(paths, output_root=self.temp_dir / "bad-p9az"),
            now_fn=lambda: datetime(2026, 6, 8, 18, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9az_ready_for_p9ba", summary["blockers"])
        self.assertFalse(summary["p9ba_p9bd_corridor_ready"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_corridor_blocks_if_current_supervisor_loads_candidate_hook(self) -> None:
        paths = self._write_ready_p9az_bundle(
            supervisor_text="from dth60_observe_only_shadow_hook import run\n",
        )

        summary, exit_code = build_corridor(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 18, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9az_ready_for_p9ba", summary["blockers"])
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_CORRIDOR_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9az_summary=str(paths["p9az_summary"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9az_bundle(
        self,
        *,
        p9az_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        p9az_root = self.temp_dir / "p9az"
        proof_root = p9az_root / "proof_artifacts" / "p9az" / "run"
        p9az_summary = p9az_root / "summary.json"
        owner_record_path = p9az_root / "owner_decision_record.json"
        package_path = proof_root / "shadow_readback_gate_package.json"
        checklist_path = proof_root / "package_acceptance_checklist.json"
        matrix_path = proof_root / "non_authorization_matrix.json"
        control_path = proof_root / "control_boundary_readback.json"

        live_config_dir.mkdir(parents=True)
        hook_module.write_text("# hook fixture\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        self._write_json(project_profile, {"current_stage": "stage_1_research_readiness_only"})

        hook_sha = file_sha256(hook_module)
        supervisor_sha = file_sha256(supervisor)
        live_config_sha = tree_sha256(live_config_dir)
        sources = {
            "hook_module": {"path": str(hook_module), "exists": True, "sha256": hook_sha},
            "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
            "live_config_dir": {"path": str(live_config_dir), "exists": True, "sha256": live_config_sha},
        }
        owner_record = self._p9az_owner_record()
        package = self._p9az_package(owner_record, sources)
        checklist = self._p9az_checklist()
        matrix = self._p9az_matrix()
        control = self._p9az_control(sources)
        self._write_json(owner_record_path, owner_record)
        self._write_json(package_path, package)
        self._write_json(checklist_path, checklist)
        self._write_json(matrix_path, matrix)
        self._write_json(control_path, control)

        summary = {
            "contract_version": P9AZ_CONTRACT,
            "status": "ready",
            "blockers": [],
            "run_id": "unit-test-p9az",
            "p9az_shadow_readback_gate_package_ready": True,
            "shadow_readback_gate_package_prepared": True,
            "shadow_readback_gate_package_under_proof_artifacts": True,
            "eligible_for_future_shadow_readback_gate_package_review_request": True,
            "allowed_next_gate": P9BA_GATE,
            "recommended_next_gate": P9BA_GATE,
            "allowed_next_gate_scope": P9BA_SCOPE,
            "allowed_next_gate_must_be_separately_requested": True,
            "prepare_gate_package_authorized": True,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
            "candidate_artifact_sink": "proof_artifacts_only",
            "executor_consumes_baseline_only": True,
            "candidate_shadow_only": True,
            "candidate_plan_referenced_by_executor": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "owner_decision": owner_record,
            "source_evidence": sources,
            "output_files": {
                "summary": str(p9az_summary),
                "owner_decision_record": str(owner_record_path),
                "shadow_readback_gate_package": str(package_path),
                "package_acceptance_checklist": str(checklist_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        for key in FALSE_EXECUTION_KEYS:
            summary[key] = False
        self._deep_update(summary, p9az_overrides or {})
        self._write_json(p9az_summary, summary)
        return {
            "project_profile": project_profile,
            "p9az_summary": p9az_summary,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }

    @staticmethod
    def _p9az_owner_record() -> dict:
        record = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9az_owner_decision.v1",
            "owner": "rulebook_owner",
            "decision": APPROVE_P9AZ_DECISION,
            "decision_source": "unit_test",
            "recorded_at_utc": "2026-06-08T17:00:00Z",
            "decision_question": "prepare_shadow_readback_gate_package_only",
            "decision_effect": "prepare_shadow_readback_gate_package_under_proof_artifacts_only",
            "prepare_shadow_readback_gate_package_approved": True,
            "future_shadow_readback_gate_package_review_request_approved": True,
        }
        for key in (
            "proposal_body_write_approved",
            "dry_load_readback_execution_approved",
            "timer_path_shadow_readback_execution_approved",
            "candidate_execution_approved",
            "candidate_live_order_submission_approved",
            "timer_hook_implementation_approved",
            "hook_deployment_approved",
            "live_timer_path_load_approved",
            "production_timer_service_load_approved",
            "live_order_submission_approved",
            "target_plan_replacement_approved",
            "executor_input_mutation_approved",
            "live_config_mutation_approved",
            "operator_state_mutation_approved",
            "timer_or_service_mutation_approved",
            "remote_sync_approved",
            "remote_execution_approved",
            "supervisor_invocation_approved",
            "supervisor_run_approved",
            "repo_stage_change_approved",
        ):
            record[key] = False
        return record

    @staticmethod
    def _p9az_package(owner_record: dict, sources: dict) -> dict:
        package = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9az_shadow_readback_gate_package.v1",
            "run_id": "unit-test-p9az",
            "package_prepared": True,
            "package_written_under_proof_artifacts": True,
            "source_evidence": sources,
            "owner_decision": owner_record,
            "default_enabled": False,
            "observe_only": True,
            "order_authority": "disabled",
            "executor_target_source": "baseline_only",
            "candidate_shadow_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "future_review_gate": P9BA_GATE,
            "future_review_gate_scope": P9BA_SCOPE,
            "future_review_gate_must_be_separately_requested": True,
            "readback_contract_if_future_gate_approved": {
                "fresh_account_read_required_before_remote_or_timer_path": True,
                "baseline_only_executor": True,
                "candidate_shadow_only": True,
                "live_order_submission_authorized": False,
            },
            "authorizations": {
                "prepare_shadow_readback_gate_package": True,
                "future_shadow_readback_gate_package_review_request": True,
            },
            "required_boundaries": {
                "proof_artifacts_only": True,
                "default_off_required": True,
                "observe_only_required": True,
                "executor_input_must_remain_baseline_only": True,
                "candidate_order_authority": "disabled",
                "live_order_submission_authorized": False,
            },
            "executed_actions": {
                "dry_load_readback_executed": False,
                "timer_path_shadow_readback_executed": False,
                "timer_path_loaded": False,
                "supervisor_invoked": False,
                "remote_sync_performed": False,
                "candidate_execution_performed": False,
                "executor_input_mutated": False,
                "target_plan_replaced": False,
                "live_config_mutated": False,
                "operator_state_mutated": False,
                "timer_state_mutated": False,
                "orders_submitted": 0,
                "fill_count": 0,
                "fills_observed": 0,
            },
        }
        for key in PROOF_FALSE_AUTHORIZATIONS:
            package["authorizations"][key] = False
        return package

    @staticmethod
    def _p9az_checklist() -> dict:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9az_package_acceptance_checklist.v1",
            "run_id": "unit-test-p9az",
            "checks": {
                "p9az_package_preparation_only": True,
                "p9ay_retained_permission_ready": True,
                "package_output_under_proof_artifacts": True,
                "package_keeps_default_off": True,
                "package_keeps_observe_only": True,
                "package_keeps_executor_baseline_only": True,
                "package_keeps_candidate_shadow_only": True,
                "package_keeps_order_authority_disabled": True,
                "future_review_gate_must_be_separately_requested": True,
                "dry_load_readback_not_executed": True,
                "timer_path_shadow_readback_not_executed": True,
                "timer_path_not_loaded": True,
                "supervisor_not_invoked": True,
                "remote_not_touched": True,
                "executor_input_not_mutated": True,
                "target_plan_not_replaced": True,
                "live_config_not_mutated": True,
                "operator_state_not_mutated": True,
                "timer_state_not_mutated": True,
                "zero_orders_fills": True,
            },
        }

    @staticmethod
    def _p9az_matrix() -> dict:
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9az_non_authorization_matrix.v1",
            "run_id": "unit-test-p9az",
            "authorizations": {
                "prepare_shadow_readback_gate_package": True,
                "future_shadow_readback_gate_package_review_request": True,
                "execute_p9ba": False,
            },
        }
        for key in PROOF_FALSE_AUTHORIZATIONS:
            matrix["authorizations"][key] = False
        return matrix

    @staticmethod
    def _p9az_control(sources: dict) -> dict:
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9az_control_boundary_readback.v1",
            "run_id": "unit-test-p9az",
            "live_supervisor": sources["live_supervisor"],
            "prepare_gate_package_authorized": True,
            "shadow_readback_gate_package_prepared": True,
            "entered_timer_path": False,
            "live_timer_path_loaded": False,
            "ran_supervisor": False,
            "remote_execution_performed": False,
            "candidate_execution_performed": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        for key in FALSE_EXECUTION_KEYS:
            control[key] = False
        return control

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _load_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _deep_update(target: dict, updates: dict) -> None:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                Phase9BAP9BDShadowReadbackProposalCorridorTests._deep_update(target[key], value)
            else:
                target[key] = value


if __name__ == "__main__":
    unittest.main()
