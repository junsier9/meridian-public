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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ar_open_proposal_preparation_gate import (  # noqa: E402
    APPROVE_P9AR_DECISION,
    P9AS_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9as_p9au_proof_only_corridor import (  # noqa: E402
    APPROVE_CORRIDOR_DECISION,
    P9AT_GATE,
    P9AU_GATE,
    P9AV_GATE,
    build_corridor,
    p9ar_ready_for_p9as,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
    resolve_path,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9ASP9AUProofOnlyCorridorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9as-p9au-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_corridor_ready_generates_package_review_and_owner_gate_without_readback(self) -> None:
        paths = self._write_ready_p9ar_inputs()

        summary, exit_code = build_corridor(
            self._args(paths),
            now_fn=lambda: datetime(2026, 6, 8, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["p9as_status"], "ready")
        self.assertEqual(summary["p9at_status"], "ready")
        self.assertEqual(summary["p9au_status"], "ready")
        self.assertFalse(summary["dry_load_readback_execution_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["supervisor_run_authorized"])
        self.assertFalse(summary["remote_sync_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        p9as = self._load_json(Path(summary["outputs"]["p9as_summary"]))
        p9at = self._load_json(Path(summary["outputs"]["p9at_summary"]))
        p9au = self._load_json(Path(summary["outputs"]["p9au_summary"]))
        self.assertTrue(p9as["p9as_proposal_package_ready"])
        self.assertEqual(p9as["allowed_next_gate"], P9AT_GATE)
        self.assertTrue(p9as["prepare_proposal_authorized"])
        self.assertTrue(p9as["proposal_package_generation_authorized"])
        self.assertFalse(p9as["dry_load_readback_execution_authorized"])
        self.assertFalse(p9as["live_order_submission_authorized"])
        package = self._load_json(Path(p9as["output_files"]["proposal_review_package"]))
        self.assertTrue(package["proposal_written_under_proof_artifacts"])
        self.assertFalse(package["proposal_executes_anything"])
        self.assertFalse(package["dry_load_readback_executed"])
        self.assertFalse(package["timer_path_loaded"])
        self.assertFalse(package["supervisor_invoked"])
        self.assertFalse(package["remote_sync_performed"])
        self.assertTrue(package["required_boundaries"]["proof_artifacts_only"])
        self.assertEqual(package["required_boundaries"]["candidate_order_authority"], "disabled")
        self.assertFalse(package["authorizations"]["dry_load_readback_execution"])
        self.assertFalse(package["authorizations"]["live_order_submission"])

        self.assertTrue(p9at["p9at_retained_readiness_review_ready"])
        self.assertEqual(p9at["allowed_next_gate"], P9AU_GATE)
        self.assertFalse(p9at["dry_load_readback_execution_authorized"])
        review = self._load_json(Path(p9at["output_files"]["readiness_review"]))
        self.assertTrue(review["reviewed_only_retained_evidence"])
        self.assertFalse(review["entered_timer_path"])
        self.assertFalse(review["dry_load_executed"])
        self.assertFalse(review["supervisor_run"])
        self.assertFalse(review["executor_input_mutated"])
        self.assertTrue(review["verdict"]["future_gate_required_before_any_dry_load_readback"])

        self.assertTrue(p9au["p9au_allow_future_dry_load_readback_gate_ready"])
        self.assertTrue(p9au["eligible_for_future_dry_load_readback_execution_gate_request"])
        self.assertEqual(p9au["allowed_next_gate"], P9AV_GATE)
        self.assertTrue(p9au["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(p9au["dry_load_readback_execution_gate_opened"])
        self.assertFalse(p9au["dry_load_readback_execution_authorized_in_p9au"])
        self.assertFalse(p9au["dry_load_readback_execution_authorized"])
        self.assertFalse(p9au["timer_path_load_authorized"])
        self.assertFalse(p9au["live_order_submission_authorized"])
        permission = self._load_json(Path(p9au["output_files"]["dry_load_readback_gate_permission"]))
        self.assertEqual(permission["allowed_next_gate"], P9AV_GATE)
        self.assertFalse(permission["dry_load_readback_executed_in_p9au"])
        self.assertFalse(permission["timer_path_loaded_in_p9au"])
        self.assertFalse(permission["supervisor_invoked_in_p9au"])

    def test_corridor_blocks_wrong_owner_decision_before_package_generation(self) -> None:
        paths = self._write_ready_p9ar_inputs()

        summary, exit_code = build_corridor(
            self._args(paths, owner_decision="approve_live_orders"),
            now_fn=lambda: datetime(2026, 6, 8, 12, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertEqual(summary["p9as_status"], "blocked")
        self.assertEqual(summary["p9at_status"], "skipped")
        self.assertEqual(summary["p9au_status"], "skipped")
        self.assertIn("owner_decision_p9as_p9au_corridor", summary["blockers"])
        self.assertFalse(summary["dry_load_readback_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_corridor_blocks_when_p9ar_already_authorized_package_or_readback(self) -> None:
        paths = self._write_ready_p9ar_inputs(
            p9ar_overrides={
                "proposal_package_generation_authorized": True,
                "dry_load_readback_execution_authorized": True,
                "gates": {
                    "p9ar_does_not_generate_proposal_package": False,
                    "p9ar_does_not_execute_dry_load_readback": False,
                },
            },
            matrix_overrides={
                "authorizations": {
                    "proposal_package_generation": True,
                    "dry_load_readback_execution": True,
                }
            },
        )
        p9ar = self._load_json(paths["phase9ar"])
        opening = self._load_json(paths["opening"])
        matrix = self._load_json(paths["matrix"])
        self.assertFalse(
            p9ar_ready_for_p9as(
                p9ar,
                opening,
                matrix,
                current_hook_sha256=file_sha256(paths["hook_module"]),
                current_supervisor_sha256=file_sha256(paths["supervisor"]),
                current_live_config_sha256=tree_sha256(paths["live_config_dir"]),
                current_supervisor_loads_candidate_hook=False,
            )
        )

        summary, exit_code = build_corridor(
            self._args(paths),
            now_fn=lambda: datetime(2026, 6, 8, 12, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["p9as_status"], "blocked")
        p9as = self._load_json(Path(summary["outputs"]["p9as_summary"]))
        self.assertIn("p9ar_gate_opening_ready", p9as["blockers"])
        self.assertFalse(p9as["dry_load_readback_execution_authorized"])
        self.assertFalse(p9as["live_order_submission_authorized"])

    def test_corridor_blocks_when_current_supervisor_loads_hook(self) -> None:
        paths = self._write_ready_p9ar_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_corridor(
            self._args(paths),
            now_fn=lambda: datetime(2026, 6, 8, 12, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["p9as_status"], "blocked")
        p9as = self._load_json(Path(summary["outputs"]["p9as_summary"]))
        self.assertIn("p9ar_gate_opening_ready", p9as["blockers"])
        self.assertIn("current_live_supervisor_not_loading_hook", p9as["blockers"])
        self.assertTrue(p9as["live_supervisor_loads_candidate_hook"])
        self.assertFalse(p9as["timer_path_load_authorized"])
        self.assertFalse(p9as["live_order_submission_authorized"])

    def _args(self, paths: dict[str, Path], *, owner_decision: str = APPROVE_CORRIDOR_DECISION) -> Namespace:
        return Namespace(
            project_profile=str(paths["project_profile"]),
            phase9ar_summary=str(paths["phase9ar"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            output_root=str(self.temp_dir / "corridor"),
            artifacts_root=str(self.temp_dir / "artifacts"),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9ar_inputs(
        self,
        *,
        p9ar_overrides: dict | None = None,
        opening_overrides: dict | None = None,
        matrix_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9ar = self.temp_dir / "p9ar" / "summary.json"
        proof_root = self.temp_dir / "p9ar" / "proof_artifacts" / "p9ar" / "run"
        opening_path = proof_root / "proposal_preparation_gate_opening.json"
        matrix_path = proof_root / "non_authorization_matrix.json"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        live_config_dir.mkdir(parents=True)
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")
        supervisor_sha = file_sha256(supervisor)
        live_config_sha = tree_sha256(live_config_dir)
        self._write_json(project_profile, {"current_stage": "stage_1_research_readiness_only"})
        opening = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ar_gate_opening.v1",
            "run_id": "unit-test-p9ar",
            "proposal_preparation_gate_opened": True,
            "allowed_next_gate": P9AS_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "prepare_proposal_in_p9ar": False,
            "proposal_package_generated_in_p9ar": False,
            "proposal_body_written_in_p9ar": False,
            "dry_load_readback_executed_in_p9ar": False,
            "required_boundaries_for_next_gate": {
                "proof_artifacts_only": True,
                "default_off_only": True,
                "observe_only_shadow_artifacts_only": True,
                "executor_input_must_remain_baseline_only": True,
                "candidate_order_authority": "disabled",
                "live_order_submission_authorized": False,
                "orders_submitted_must_equal": 0,
                "fill_count_must_equal": 0,
            },
        }
        self._deep_update(opening, opening_overrides or {})
        self._write_json(opening_path, opening)
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ar_non_authorization_matrix.v1",
            "run_id": "unit-test-p9ar",
            "authorizations": {
                "open_proposal_preparation_gate": True,
                "future_proposal_package_preparation_request": True,
                "prepare_proposal": False,
                "proposal_package_generation": False,
                "proposal_body_write": False,
                "dry_load_readback_execution": False,
                "candidate_execution": False,
                "candidate_live_order_submission": False,
                "timer_hook_implementation": False,
                "hook_deployment": False,
                "live_timer_path_load": False,
                "production_timer_service_load": False,
                "live_order_submission": False,
                "target_plan_replacement": False,
                "executor_input_mutation": False,
                "live_config_mutation": False,
                "operator_state_mutation": False,
                "timer_or_service_mutation": False,
                "remote_sync": False,
                "remote_execution": False,
                "supervisor_invocation": False,
                "supervisor_run": False,
                "stage_governance_change": False,
            },
        }
        self._deep_update(matrix, matrix_overrides or {})
        self._write_json(matrix_path, matrix)
        gates = {
            "owner_decision_p9ar_open_gate_only": True,
            "project_stage_boundary_preserved": True,
            "p9aq_permission_gate_ready": True,
            "p9aq_allowed_p9ar_only": True,
            "p9aq_did_not_open_gate": True,
            "p9aq_did_not_prepare_proposal": True,
            "p9aq_did_not_write_proposal_body": True,
            "p9aq_did_not_execute_readback": True,
            "current_live_supervisor_not_loading_hook": True,
            "current_hook_hash_matches_p9aq_source": True,
            "current_supervisor_hash_matches_p9aq_source": True,
            "current_live_config_hash_matches_p9aq_source": True,
            "gate_opening_output_under_proof_artifacts": True,
            "p9ar_opens_gate_only": True,
            "p9ar_does_not_prepare_proposal": True,
            "p9ar_does_not_generate_proposal_package": True,
            "p9ar_does_not_write_proposal_body": True,
            "p9ar_does_not_execute_dry_load_readback": True,
            "p9as_must_be_separately_requested": True,
            "p9as_must_be_proof_artifacts_only": True,
            "p9as_must_keep_default_off": True,
            "p9as_must_keep_observe_only": True,
            "p9as_must_keep_order_authority_disabled": True,
            "no_timer_hook_implementation_in_p9ar": True,
            "no_hook_deployment_in_p9ar": True,
            "no_live_timer_path_load_in_p9ar": True,
            "no_production_timer_service_load_in_p9ar": True,
            "no_supervisor_run_in_p9ar": True,
            "no_remote_execution_in_p9ar": True,
            "no_candidate_execution_in_p9ar": True,
            "no_executor_input_mutation_in_p9ar": True,
            "no_target_plan_replacement_in_p9ar": True,
            "no_live_mutation_in_p9ar": True,
            "zero_orders_fills_in_p9ar": True,
        }
        p9ar = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ar_open_proposal_preparation_gate.v1",
            "status": "ready",
            "blockers": [],
            "p9ar_open_proposal_preparation_gate_ready": True,
            "proposal_preparation_gate_opened": True,
            "eligible_for_future_proposal_package_preparation_request": True,
            "allowed_next_gate": P9AS_GATE,
            "recommended_next_gate": P9AS_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "open_proposal_preparation_gate_authorized": True,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifact_sink": "proof_artifacts_only",
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
            "owner_decision": {
                "decision": APPROVE_P9AR_DECISION,
                "proposal_preparation_gate_open_approved": True,
                "future_proposal_package_preparation_request_approved": True,
                "prepare_proposal_approved": False,
                "proposal_package_generation_approved": False,
                "proposal_body_write_approved": False,
                "dry_load_readback_execution_approved": False,
            },
            "source_evidence": {
                "hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha},
                "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
                "live_config_dir": {"path": str(live_config_dir), "exists": True, "sha256": live_config_sha},
            },
            "gates": gates,
            "output_files": {
                "summary": str(phase9ar),
                "proposal_preparation_gate_opening": str(opening_path),
                "non_authorization_matrix": str(matrix_path),
            },
        }
        for key in (
            "proposal_preparation_action_authorized",
            "prepare_proposal_authorized",
            "proposal_package_generation_authorized",
            "proposal_body_write_authorized",
            "dry_load_readback_execution_authorized",
            "timer_hook_implementation_authorized",
            "hook_deployment_authorized",
            "timer_path_load_authorized",
            "supervisor_invocation_authorized",
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
            "live_supervisor_loads_candidate_hook",
            "live_timer_path_loaded",
            "live_timer_service_enabled_or_invoked",
            "ran_supervisor",
            "timer_path_invoked",
            "remote_execution_performed",
            "remote_control_plane_touched",
            "candidate_execution_performed",
            "wrote_live_hook_config",
            "implemented_hook",
            "deployed_hook",
            "loaded_hook",
            "target_plan_replaced",
            "executor_input_changed",
        ):
            p9ar[key] = False
        self._deep_update(p9ar, p9ar_overrides or {})
        self._write_json(phase9ar, p9ar)
        return {
            "project_profile": project_profile,
            "phase9ar": phase9ar,
            "opening": opening_path,
            "matrix": matrix_path,
            "hook_module": hook_path,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }

    @staticmethod
    def _deep_update(target: dict, updates: dict) -> None:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                Phase9ASP9AUProofOnlyCorridorTests._deep_update(target[key], value)
            else:
                target[key] = value

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _load_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
