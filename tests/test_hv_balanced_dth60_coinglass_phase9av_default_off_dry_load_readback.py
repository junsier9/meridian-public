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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9as_p9au_proof_only_corridor import (  # noqa: E402
    P9AU_GATE,
    P9AV_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9av_default_off_dry_load_readback import (  # noqa: E402
    APPROVE_P9AV_DECISION,
    P9AW_GATE,
    build_p9av,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9AVDefaultOffDryLoadReadbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9av-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_p9av_ready_executes_local_proof_only_readback(self) -> None:
        paths = self._write_ready_p9au_inputs()

        summary, exit_code = build_p9av(
            self._args(paths),
            now_fn=lambda: datetime(2026, 6, 8, 13, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9av_default_off_observe_only_dry_load_readback_ready"])
        self.assertEqual(summary["allowed_next_gate"], P9AW_GATE)
        self.assertTrue(summary["dry_load_readback_executed"])
        self.assertEqual(summary["dry_load_readback_mode"], "local_proof_artifacts_only_not_timer_path")
        self.assertTrue(summary["dry_load_manifest_under_proof_artifacts"])
        self.assertTrue(summary["dry_load_readback_under_proof_artifacts"])
        self.assertTrue(summary["candidate_shadow_artifact_under_proof_artifacts"])
        self.assertTrue(summary["executor_input_guard_under_proof_artifacts"])
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertTrue(summary["candidate_shadow_only"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["entered_timer_path"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["candidate_execution_performed"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        manifest = self._load_json(Path(summary["output_files"]["dry_load_manifest"]))
        readback = self._load_json(Path(summary["output_files"]["dry_load_readback"]))
        guard = self._load_json(Path(summary["output_files"]["executor_input_guard"]))
        matrix = self._load_json(Path(summary["output_files"]["non_authorization_matrix"]))
        control = self._load_json(Path(summary["output_files"]["control_boundary_readback"]))
        self.assertEqual(manifest["dry_load_mode"], "default_off_observe_only_local_proof_artifacts_only_not_timer_path")
        self.assertFalse(manifest["timer_path_loaded"])
        self.assertFalse(manifest["supervisor_invoked"])
        self.assertFalse(manifest["remote_sync_performed"])
        self.assertTrue(readback["dry_load_readback_ok"])
        self.assertTrue(readback["baseline_executor_input_hash_unchanged"])
        self.assertTrue(guard["candidate_shadow_hash_differs_from_executor_input"])
        self.assertTrue(matrix["authorizations"]["proof_artifacts_dry_load_readback_execution"])
        self.assertFalse(matrix["authorizations"]["dry_load_readback_execution_in_timer_path"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertTrue(control["dry_load_readback_executed"])
        self.assertFalse(control["entered_timer_path"])
        self.assertFalse(control["ran_supervisor"])
        self.assertFalse(control["remote_sync_performed"])
        self.assertEqual(control["orders_submitted"], 0)
        self.assertEqual(control["fill_count"], 0)

    def test_p9av_blocks_wrong_owner_decision_without_readback(self) -> None:
        paths = self._write_ready_p9au_inputs()

        summary, exit_code = build_p9av(
            self._args(paths, owner_decision="approve_live_orders"),
            now_fn=lambda: datetime(2026, 6, 8, 13, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9av_dry_load_readback_only", summary["blockers"])
        self.assertFalse(summary["dry_load_readback_executed"])
        self.assertFalse(summary["dry_load_readback_execution_authorized"])
        self.assertFalse(summary["candidate_shadow_artifact_written"])
        self.assertEqual(summary["output_files"]["dry_load_readback"], "")
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_p9av_blocks_if_p9au_permission_was_already_used_or_polluted(self) -> None:
        paths = self._write_ready_p9au_inputs(
            permission_overrides={"dry_load_readback_executed_in_p9au": True},
        )

        summary, exit_code = build_p9av(
            self._args(paths),
            now_fn=lambda: datetime(2026, 6, 8, 13, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9au_permission_ready_for_p9av", summary["blockers"])
        self.assertFalse(summary["dry_load_readback_executed"])
        self.assertFalse(summary["entered_timer_path"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_p9av_blocks_when_current_supervisor_loads_candidate_hook(self) -> None:
        paths = self._write_ready_p9au_inputs(
            supervisor_text="from dth60_observe_only_shadow_hook import run\n",
        )

        summary, exit_code = build_p9av(
            self._args(paths),
            now_fn=lambda: datetime(2026, 6, 8, 13, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["dry_load_readback_executed"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(self, paths: dict[str, Path], *, owner_decision: str = APPROVE_P9AV_DECISION) -> Namespace:
        return Namespace(
            project_profile=str(paths["project_profile"]),
            phase9au_summary=str(paths["phase9au_summary"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            output_root=str(self.temp_dir / "p9av"),
            artifacts_root="",
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9au_inputs(
        self,
        *,
        permission_overrides: dict | None = None,
        p9au_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        p9as_summary_path = self.temp_dir / "p9as" / "summary.json"
        p9as_package_path = self.temp_dir / "p9as" / "proof_artifacts" / "p9as" / "run" / "proposal_review_package.json"
        p9at_summary_path = self.temp_dir / "p9at" / "summary.json"
        p9at_review_path = self.temp_dir / "p9at" / "proof_artifacts" / "p9at" / "run" / "readiness_review.json"
        p9at_checklist_path = self.temp_dir / "p9at" / "proof_artifacts" / "p9at" / "run" / "readiness_checklist.json"
        p9au_summary_path = self.temp_dir / "p9au" / "summary.json"
        p9au_proof_root = self.temp_dir / "p9au" / "proof_artifacts" / "p9au" / "run"
        permission_path = p9au_proof_root / "dry_load_readback_gate_permission.json"
        p9au_matrix_path = p9au_proof_root / "non_authorization_matrix.json"
        p9au_control_path = p9au_proof_root / "control_boundary_readback.json"

        live_config_dir.mkdir(parents=True)
        hook_module.write_text("# hook module fixture\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        self._write_json(project_profile, {"current_stage": "stage_1_research_readiness_only"})
        hook_sha = file_sha256(hook_module)
        supervisor_sha = file_sha256(supervisor)
        live_config_sha = tree_sha256(live_config_dir)
        common_sources = {
            "project_profile": self._evidence(project_profile),
            "hook_module": self._evidence(hook_module),
            "live_supervisor": self._evidence(supervisor),
            "live_config_dir": {"path": str(live_config_dir), "exists": True, "sha256": live_config_sha},
        }
        p9as_package = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9as_proposal_package_body.v1",
            "run_id": "fixture",
            "proposal_mode": "default_off_observe_only_live_supervisor_timer_path_shadow_readback_proposal",
            "proposed_future_gate": P9AV_GATE,
            "required_intermediate_owner_gate": P9AU_GATE,
            "proposal_written_under_proof_artifacts": True,
            "proposal_executes_anything": False,
            "default_enabled": False,
            "observe_only": True,
            "candidate_shadow_only": True,
            "executor_target_source": "baseline_only",
            "candidate_artifact_sink": "proof_artifacts_only",
            "dry_load_readback_executed": False,
            "timer_path_loaded": False,
            "supervisor_invoked": False,
            "remote_sync_performed": False,
            "required_boundaries": {
                "proof_artifacts_only": True,
                "default_off_only": True,
                "observe_only_shadow_artifacts_only": True,
                "executor_input_must_remain_baseline_only": True,
                "candidate_plan_must_not_be_referenced_by_executor": True,
                "candidate_order_authority": "disabled",
                "live_order_submission_authorized": False,
                "dry_load_readback_execution_authorized": False,
            },
            "authorizations": {
                "prepare_proposal_package": True,
                "dry_load_readback_execution": False,
                "timer_path_load": False,
                "supervisor_invocation": False,
                "remote_sync": False,
                "live_order_submission": False,
            },
            "source_evidence": common_sources,
        }
        self._write_json(p9as_package_path, p9as_package)
        p9as_summary = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9as_proposal_package.v1",
            "status": "ready",
            "blockers": [],
            "p9as_proposal_package_ready": True,
            "generated_proposal_package": True,
            "dry_load_readback_execution_authorized": False,
            "live_order_submission_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "output_files": {
                "summary": str(p9as_summary_path),
                "proposal_review_package": str(p9as_package_path),
            },
            "source_evidence": common_sources,
        }
        self._write_json(p9as_summary_path, p9as_summary)
        p9at_review = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9at_readiness_review.v1",
            "run_id": "fixture",
            "reviewed_only_retained_evidence": True,
            "entered_timer_path": False,
            "dry_load_executed": False,
            "supervisor_run": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "source_evidence": {
                **common_sources,
                "phase9as_summary": self._evidence(p9as_summary_path),
                "phase9as_proposal_review_package": self._evidence(p9as_package_path),
            },
            "verdict": {
                "ready_for_future_owner_default_off_dry_load_gate": True,
                "future_gate_required_before_any_dry_load_readback": True,
                "future_gate_must_keep_executor_baseline_only": True,
                "future_gate_must_keep_order_authority_disabled": True,
            },
        }
        self._write_json(p9at_review_path, p9at_review)
        self._write_json(
            p9at_checklist_path,
            {"contract_version": "hv_balanced_dth60_coinglass_phase9at_readiness_checklist.v1", "checks": {}},
        )
        p9at_summary = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9at_retained_readiness_review.v1",
            "status": "ready",
            "blockers": [],
            "p9at_retained_readiness_review_ready": True,
            "allowed_next_gate": P9AU_GATE,
            "dry_load_readback_execution_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "output_files": {
                "summary": str(p9at_summary_path),
                "readiness_review": str(p9at_review_path),
                "readiness_checklist": str(p9at_checklist_path),
            },
            "source_evidence": {
                **common_sources,
                "phase9as_summary": self._evidence(p9as_summary_path),
                "phase9as_proposal_review_package": self._evidence(p9as_package_path),
            },
        }
        self._write_json(p9at_summary_path, p9at_summary)
        p9au_sources = {
            **common_sources,
            "phase9at_summary": self._evidence(p9at_summary_path),
            "phase9at_readiness_review": self._evidence(p9at_review_path),
            "phase9at_readiness_checklist": self._evidence(p9at_checklist_path),
        }
        permission = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9au_dry_load_readback_gate_permission.v1",
            "run_id": "fixture",
            "source_evidence": p9au_sources,
            "allowed_next_gate": P9AV_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "dry_load_readback_executed_in_p9au": False,
            "timer_path_loaded_in_p9au": False,
            "supervisor_invoked_in_p9au": False,
            "required_boundaries_for_next_gate": {
                "owner_gated": True,
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
        self._deep_update(permission, permission_overrides or {})
        self._write_json(permission_path, permission)
        p9au_matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9au_non_authorization_matrix.v1",
            "run_id": "fixture",
            "authorizations": {
                "future_dry_load_readback_gate_request": True,
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
        self._write_json(p9au_matrix_path, p9au_matrix)
        p9au_control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9au_control_boundary_readback.v1",
            "run_id": "fixture",
            "live_supervisor_source_unchanged": True,
            "live_config_dir_unchanged": True,
            "live_supervisor_loads_candidate_hook": False,
            "dry_load_readback_executed": False,
            "entered_timer_path": False,
            "candidate_execution_performed": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        self._write_json(p9au_control_path, p9au_control)
        p9au_summary = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9au_allow_dry_load_readback_owner_gate.v1",
            "status": "ready",
            "blockers": [],
            "p9au_allow_future_dry_load_readback_gate_ready": True,
            "eligible_for_future_dry_load_readback_execution_gate_request": True,
            "allowed_next_gate": P9AV_GATE,
            "recommended_next_gate": P9AV_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
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
            "output_files": {
                "summary": str(p9au_summary_path),
                "dry_load_readback_gate_permission": str(permission_path),
                "non_authorization_matrix": str(p9au_matrix_path),
                "control_boundary_readback": str(p9au_control_path),
            },
            "source_evidence": p9au_sources,
        }
        for key in (
            "dry_load_readback_execution_authorized",
            "dry_load_readback_execution_authorized_in_p9au",
            "dry_load_readback_execution_gate_opened",
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
            p9au_summary[key] = False
        self._deep_update(p9au_summary, p9au_overrides or {})
        self._write_json(p9au_summary_path, p9au_summary)
        self.assertEqual(hook_sha, file_sha256(hook_module))
        self.assertEqual(supervisor_sha, file_sha256(supervisor))
        return {
            "project_profile": project_profile,
            "phase9au_summary": p9au_summary_path,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }

    def _evidence(self, path: Path) -> dict:
        return {"path": str(path), "exists": path.exists(), "sha256": file_sha256(path) if path.is_file() else ""}

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
                Phase9AVDefaultOffDryLoadReadbackTests._deep_update(target[key], value)
            else:
                target[key] = value


if __name__ == "__main__":
    unittest.main()
