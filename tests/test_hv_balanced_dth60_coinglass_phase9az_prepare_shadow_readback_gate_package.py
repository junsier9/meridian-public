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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ay_allow_prepare_shadow_readback_gate import (  # noqa: E402
    APPROVE_P9AY_DECISION,
    CONTRACT_VERSION as P9AY_CONTRACT,
    P9AZ_GATE,
    P9AZ_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9az_prepare_shadow_readback_gate_package import (  # noqa: E402
    APPROVE_P9AZ_DECISION,
    FALSE_EXECUTION_KEYS,
    P9BA_GATE,
    P9BA_SCOPE,
    P9AY_FALSE_KEYS,
    build_phase9az,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9AZPrepareShadowReadbackGatePackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9az-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_p9az_ready_prepares_gate_package_only(self) -> None:
        paths = self._write_ready_p9ay_bundle()
        output_root = self.temp_dir / "p9az"

        summary, exit_code = build_phase9az(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 17, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9az_shadow_readback_gate_package_ready"])
        self.assertTrue(summary["shadow_readback_gate_package_prepared"])
        self.assertTrue(summary["shadow_readback_gate_package_under_proof_artifacts"])
        self.assertTrue(summary["prepare_gate_package_authorized"])
        self.assertEqual(summary["allowed_next_gate"], P9BA_GATE)
        self.assertEqual(summary["allowed_next_gate_scope"], P9BA_SCOPE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(summary["proposal_body_write_authorized"])
        self.assertFalse(summary["dry_load_readback_execution_authorized"])
        self.assertFalse(summary["timer_path_shadow_readback_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["candidate_execution_performed"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["execution_target_source"], "baseline_only")
        self.assertEqual(summary["candidate_artifact_sink"], "proof_artifacts_only")
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = output_root / "proof_artifacts" / "p9az" / "20260608T170000Z"
        package = self._load_json(proof_root / "shadow_readback_gate_package.json")
        checklist = self._load_json(proof_root / "package_acceptance_checklist.json")
        matrix = self._load_json(proof_root / "non_authorization_matrix.json")
        control = self._load_json(proof_root / "control_boundary_readback.json")
        self.assertTrue(package["package_prepared"])
        self.assertFalse(package["default_enabled"])
        self.assertTrue(package["observe_only"])
        self.assertEqual(package["order_authority"], "disabled")
        self.assertEqual(package["executor_target_source"], "baseline_only")
        self.assertEqual(package["future_review_gate"], P9BA_GATE)
        self.assertTrue(package["future_review_gate_must_be_separately_requested"])
        self.assertFalse(package["authorizations"]["dry_load_readback_execution"])
        self.assertFalse(package["authorizations"]["live_order_submission"])
        self.assertTrue(checklist["checks"]["p9az_package_preparation_only"])
        self.assertTrue(matrix["authorizations"]["prepare_shadow_readback_gate_package"])
        self.assertFalse(matrix["authorizations"]["execute_p9ba"])
        self.assertFalse(matrix["authorizations"]["timer_path_shadow_readback_execution"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertTrue(control["prepare_gate_package_authorized"])
        self.assertFalse(control["entered_timer_path"])
        self.assertFalse(control["ran_supervisor"])
        self.assertEqual(control["orders_submitted"], 0)

    def test_p9az_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_p9ay_bundle()

        summary, exit_code = build_phase9az(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_submission",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 17, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9az_prepare_package_only", summary["blockers"])
        self.assertFalse(summary["shadow_readback_gate_package_prepared"])
        self.assertFalse(summary["prepare_gate_package_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_p9az_blocks_if_p9ay_does_not_allow_p9az(self) -> None:
        paths = self._write_ready_p9ay_bundle(
            p9ay_overrides={
                "allowed_next_gate": "P9BAD_live_order_gate",
                "recommended_next_gate": "P9BAD_live_order_gate",
            }
        )

        summary, exit_code = build_phase9az(
            self._args(paths, output_root=self.temp_dir / "bad-p9ay"),
            now_fn=lambda: datetime(2026, 6, 8, 17, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9ay_permission_ready_for_p9az", summary["blockers"])
        self.assertIn("p9ay_allows_p9az_only", summary["blockers"])
        self.assertFalse(summary["shadow_readback_gate_package_prepared"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_p9az_blocks_if_current_supervisor_loads_candidate_hook(self) -> None:
        paths = self._write_ready_p9ay_bundle(
            supervisor_text="from dth60_observe_only_shadow_hook import run\n",
        )

        summary, exit_code = build_phase9az(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 17, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9ay_permission_ready_for_p9az", summary["blockers"])
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["shadow_readback_gate_package_prepared"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9AZ_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9ay_summary=str(paths["p9ay_summary"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9ay_bundle(
        self,
        *,
        p9ay_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        p9ay_root = self.temp_dir / "p9ay"
        proof_root = p9ay_root / "proof_artifacts" / "p9ay" / "run"
        p9ay_summary = p9ay_root / "summary.json"
        owner_record_path = p9ay_root / "owner_decision_record.json"
        permission_path = proof_root / "shadow_readback_gate_preparation_permission.json"
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
        owner_record = self._p9ay_owner_record()
        permission = self._p9ay_permission(owner_record, sources)
        matrix = self._p9ay_matrix()
        control = self._p9ay_control(sources)
        self._write_json(owner_record_path, owner_record)
        self._write_json(permission_path, permission)
        self._write_json(matrix_path, matrix)
        self._write_json(control_path, control)

        summary = {
            "contract_version": P9AY_CONTRACT,
            "status": "ready",
            "blockers": [],
            "run_id": "unit-test-p9ay",
            "p9ay_allow_prepare_shadow_readback_gate_ready": True,
            "eligible_for_future_shadow_readback_gate_package_preparation_request": True,
            "future_shadow_readback_gate_package_preparation_request_authorized": True,
            "allowed_next_gate": P9AZ_GATE,
            "recommended_next_gate": P9AZ_GATE,
            "allowed_next_gate_scope": P9AZ_SCOPE,
            "allowed_next_gate_must_be_separately_requested": True,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "shadow_only_not_executor",
            "candidate_artifact_sink": "proof_artifacts_only",
            "executor_consumes_baseline_only": True,
            "candidate_shadow_only": True,
            "candidate_plan_referenced_by_executor": False,
            "live_supervisor_source_unchanged": True,
            "live_config_dir_unchanged": True,
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
                "summary": str(p9ay_summary),
                "owner_decision_record": str(owner_record_path),
                "shadow_readback_gate_preparation_permission": str(permission_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        for key in P9AY_FALSE_KEYS:
            summary[key] = False
        self._deep_update(summary, p9ay_overrides or {})
        self._write_json(p9ay_summary, summary)
        return {
            "project_profile": project_profile,
            "p9ay_summary": p9ay_summary,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }

    @staticmethod
    def _p9ay_owner_record() -> dict:
        record = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ay_owner_decision.v1",
            "owner": "rulebook_owner",
            "decision": APPROVE_P9AY_DECISION,
            "decision_source": "unit_test",
            "recorded_at_utc": "2026-06-08T16:00:00Z",
            "decision_question": "allow_future_shadow_readback_gate_package_preparation_request_only",
            "decision_effect": "allow_future_p9az_gate_package_preparation_request_only",
            "future_shadow_readback_gate_package_preparation_request_approved": True,
            "prepare_shadow_readback_gate_in_p9ay_approved": False,
            "execute_p9az_approved": False,
            "prepare_gate_package_approved": False,
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
    def _p9ay_permission(owner_record: dict, sources: dict) -> dict:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ay_shadow_readback_gate_preparation_permission.v1",
            "run_id": "unit-test-p9ay",
            "source_evidence": sources,
            "owner_decision": owner_record,
            "allowed_next_gate": P9AZ_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "allowed_next_gate_scope": P9AZ_SCOPE,
            "opened_in_p9ay": False,
            "executed_in_p9ay": False,
            "prepared_in_p9ay": False,
            "p9az_required_boundaries": {
                "owner_gated": True,
                "proof_artifacts_only": True,
                "default_off_required": True,
                "observe_only_required": True,
                "executor_input_must_remain_baseline_only": True,
                "candidate_shadow_only": True,
                "candidate_plan_must_not_be_referenced_by_executor": True,
                "candidate_order_authority": "disabled",
                "live_order_submission_authorized": False,
                "orders_submitted_must_equal": 0,
                "fill_count_must_equal": 0,
                "dry_load_readback_execution_authorized": False,
                "timer_path_shadow_readback_execution_authorized": False,
                "timer_path_load_authorized": False,
                "supervisor_invocation_authorized": False,
                "remote_sync_authorized": False,
            },
            "p9az_disallowed_actions": {
                "execute_p9az_inside_p9ay": True,
                "prepare_gate_package_inside_p9ay": True,
                "write_proposal_body_inside_p9ay": True,
                "execute_dry_load_readback": True,
                "execute_timer_path_shadow_readback": True,
                "implement_hook": True,
                "deploy_hook": True,
                "load_live_timer_path": True,
                "run_supervisor": True,
                "invoke_timer_or_service": True,
                "mutate_executor_input": True,
                "replace_target_plan": True,
                "mutate_live_config": True,
                "mutate_operator_state": True,
                "mutate_timer_or_service_state": True,
                "remote_sync": True,
                "remote_execution": True,
                "stage_governance_change": True,
                "submit_orders": True,
            },
        }

    @staticmethod
    def _p9ay_matrix() -> dict:
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ay_non_authorization_matrix.v1",
            "run_id": "unit-test-p9ay",
            "authorizations": {
                "future_shadow_readback_gate_package_preparation_request": True,
                "prepare_shadow_readback_gate_in_p9ay": False,
                "execute_p9az": False,
                "prepare_gate_package": False,
                "write_proposal_body": False,
            },
        }
        for key in (
            "dry_load_readback_execution",
            "timer_path_shadow_readback_execution",
            "candidate_execution",
            "candidate_live_order_submission",
            "timer_hook_implementation",
            "hook_deployment",
            "live_timer_path_load",
            "production_timer_service_load",
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
        return matrix

    @staticmethod
    def _p9ay_control(sources: dict) -> dict:
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ay_control_boundary_readback.v1",
            "run_id": "unit-test-p9ay",
            "live_supervisor": sources["live_supervisor"],
            "live_supervisor_source_unchanged": True,
            "live_supervisor_loads_candidate_hook": False,
            "live_config_dir_unchanged": True,
            "future_shadow_readback_gate_package_preparation_request_authorized": True,
            "prepare_gate_package_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        for key in FALSE_EXECUTION_KEYS:
            control[key] = False
        for key in (
            "proposal_body_write_authorized",
            "dry_load_readback_execution_authorized",
            "timer_path_shadow_readback_authorized",
            "timer_path_load_authorized",
            "supervisor_invocation_authorized",
            "supervisor_run_authorized",
            "remote_sync_authorized",
            "remote_execution_authorized",
            "candidate_execution_authorized",
            "live_order_submission_authorized",
            "executor_input_mutated",
            "target_plan_replaced",
        ):
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
                Phase9AZPrepareShadowReadbackGatePackageTests._deep_update(target[key], value)
            else:
                target[key] = value


if __name__ == "__main__":
    unittest.main()
