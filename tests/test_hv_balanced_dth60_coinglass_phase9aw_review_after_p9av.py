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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9av_default_off_dry_load_readback import (  # noqa: E402
    P9AW_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9aw_review_after_p9av import (  # noqa: E402
    APPROVE_P9AW_DECISION,
    P9AX_GATE,
    build_p9aw,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9AWReviewAfterP9AVTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9aw-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_p9aw_ready_reviews_p9av_retained_evidence_only(self) -> None:
        paths = self._write_ready_p9av_bundle()

        summary, exit_code = build_p9aw(
            self._args(paths),
            now_fn=lambda: datetime(2026, 6, 8, 14, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9aw_retained_evidence_review_ready"])
        self.assertTrue(summary["p9av_retained_evidence_sufficient"])
        self.assertTrue(summary["sufficient_for_next_gate_scope_discussion"])
        self.assertEqual(summary["allowed_next_gate"], P9AX_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertTrue(summary["retained_evidence_review_authorized"])
        self.assertFalse(summary["define_next_gate_scope_authorized"])
        self.assertFalse(summary["next_gate_execution_authorized"])
        self.assertFalse(summary["dry_load_readback_execution_authorized"])
        self.assertFalse(summary["entered_timer_path"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["candidate_execution_performed"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        review = self._load_json(Path(summary["output_files"]["owner_review_packet"]))
        checklist = self._load_json(Path(summary["output_files"]["sufficiency_checklist"]))
        matrix = self._load_json(Path(summary["output_files"]["non_authorization_matrix"]))
        control = self._load_json(Path(summary["output_files"]["control_boundary_readback"]))
        self.assertTrue(review["reviewed_only_retained_evidence"])
        self.assertTrue(review["p9av_retained_evidence_sufficient"])
        self.assertTrue(review["verdict"]["sufficient_for_p9ax_scope_discussion_only"])
        self.assertTrue(checklist["checks"]["p9av_retained_evidence_sufficient"])
        self.assertTrue(matrix["authorizations"]["retained_evidence_review"])
        self.assertTrue(matrix["authorizations"]["future_next_gate_scope_discussion_request"])
        self.assertFalse(matrix["authorizations"]["define_next_gate_scope_in_p9aw"])
        self.assertFalse(matrix["authorizations"]["next_gate_execution"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(control["define_next_gate_scope_authorized"])
        self.assertFalse(control["dry_load_readback_executed"])
        self.assertFalse(control["entered_timer_path"])
        self.assertEqual(control["orders_submitted"], 0)

    def test_p9aw_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_p9av_bundle()

        summary, exit_code = build_p9aw(
            self._args(paths, owner_decision="approve_live_orders"),
            now_fn=lambda: datetime(2026, 6, 8, 14, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9aw_review_only", summary["blockers"])
        self.assertFalse(summary["retained_evidence_review_authorized"])
        self.assertFalse(summary["define_next_gate_scope_authorized"])
        self.assertFalse(summary["next_gate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_p9aw_blocks_if_p9av_readback_entered_timer_path(self) -> None:
        paths = self._write_ready_p9av_bundle(readback_overrides={"entered_timer_path": True})

        summary, exit_code = build_p9aw(
            self._args(paths),
            now_fn=lambda: datetime(2026, 6, 8, 14, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9av_retained_evidence_sufficient", summary["blockers"])
        self.assertFalse(summary["p9av_retained_evidence_sufficient"])
        self.assertFalse(summary["next_gate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_p9aw_blocks_when_current_supervisor_loads_candidate_hook(self) -> None:
        paths = self._write_ready_p9av_bundle(
            supervisor_text="from dth60_observe_only_shadow_hook import run\n",
        )

        summary, exit_code = build_p9aw(
            self._args(paths),
            now_fn=lambda: datetime(2026, 6, 8, 14, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertFalse(summary["p9av_retained_evidence_sufficient"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(self, paths: dict[str, Path], *, owner_decision: str = APPROVE_P9AW_DECISION) -> Namespace:
        return Namespace(
            output_root=str(self.temp_dir / "p9aw"),
            project_profile=str(paths["project_profile"]),
            phase9av_summary=str(paths["p9av_summary"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9av_bundle(
        self,
        *,
        readback_overrides: dict | None = None,
        summary_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        p9av_root = self.temp_dir / "p9av"
        proof_root = p9av_root / "proof_artifacts" / "p9av" / "run"
        summary_path = p9av_root / "summary.json"
        manifest_path = proof_root / "dry_load_manifest.json"
        candidate_shadow_path = proof_root / "candidate_shadow_artifact.json"
        readback_path = proof_root / "dry_load_readback.json"
        guard_path = proof_root / "executor_input_guard.json"
        matrix_path = proof_root / "non_authorization_matrix.json"
        control_path = proof_root / "control_boundary_readback.json"

        live_config_dir.mkdir(parents=True)
        hook_module.write_text("# hook module fixture\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        self._write_json(project_profile, {"current_stage": "stage_1_research_readiness_only"})
        live_config_sha = tree_sha256(live_config_dir)
        sources = {
            "project_profile": self._evidence(project_profile),
            "hook_module": self._evidence(hook_module),
            "live_supervisor": self._evidence(supervisor),
            "live_config_dir": {"path": str(live_config_dir), "exists": True, "sha256": live_config_sha},
        }
        baseline_hash = "baseline-hash"
        candidate_hash = "candidate-shadow-hash"
        manifest = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9av_dry_load_manifest.v1",
            "run_id": "fixture",
            "dry_load_mode": "default_off_observe_only_local_proof_artifacts_only_not_timer_path",
            "default_enabled": False,
            "observe_only": True,
            "executor_target_source": "baseline_only",
            "candidate_artifact_sink": "proof_artifacts_only",
            "candidate_shadow_only": True,
            "candidate_order_authority": "disabled",
            "timer_path_loaded": False,
            "supervisor_invoked": False,
            "remote_sync_performed": False,
            "live_config_mutated": False,
            "operator_state_mutated": False,
            "timer_state_mutated": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        self._write_json(manifest_path, manifest)
        candidate_shadow = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9av_candidate_shadow_artifact.v1",
            "run_id": "fixture",
            "candidate_shadow_only": True,
            "default_enabled": False,
            "observe_only": True,
            "candidate_order_authority": "disabled",
            "candidate_plan_referenced_by_executor": False,
            "executor_target_source": "baseline_only",
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        self._write_json(candidate_shadow_path, candidate_shadow)
        guard = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9av_executor_input_guard.v1",
            "run_id": "fixture",
            "baseline_executor_input_hash_before": baseline_hash,
            "baseline_executor_input_hash_after": baseline_hash,
            "baseline_executor_input_hash_unchanged": True,
            "candidate_shadow_artifact_sha256": candidate_hash,
            "candidate_shadow_hash_differs_from_executor_input": True,
            "executor_consumes_baseline_only": True,
            "candidate_plan_referenced_by_executor": False,
            "executor_input_changed": False,
            "target_plan_replaced": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        self._write_json(guard_path, guard)
        readback = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9av_dry_load_readback.v1",
            "run_id": "fixture",
            "dry_load_readback_ok": True,
            "dry_load_readback_executed": True,
            "dry_load_readback_mode": "local_proof_artifacts_only_not_timer_path",
            "default_enabled": False,
            "observe_only": True,
            "executor_target_source": "baseline_only",
            "executor_consumes_baseline_only": True,
            "candidate_shadow_only": True,
            "candidate_plan_referenced_by_executor": False,
            "baseline_executor_input_hash_before": baseline_hash,
            "baseline_executor_input_hash_after": baseline_hash,
            "baseline_executor_input_hash_unchanged": True,
            "candidate_shadow_hash_differs_from_executor_input": True,
            "entered_timer_path": False,
            "live_timer_path_loaded": False,
            "live_timer_service_enabled_or_invoked": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "remote_sync_performed": False,
            "remote_execution_performed": False,
            "remote_control_plane_touched": False,
            "candidate_execution_performed": False,
            "executor_input_changed": False,
            "target_plan_replaced": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        self._deep_update(readback, readback_overrides or {})
        self._write_json(readback_path, readback)
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9av_non_authorization_matrix.v1",
            "run_id": "fixture",
            "authorizations": {
                "default_off_observe_only_local_dry_load_readback": True,
                "proof_artifacts_dry_load_readback_execution": True,
                "dry_load_readback_execution_in_timer_path": False,
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
        self._write_json(matrix_path, matrix)
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9av_control_boundary_readback.v1",
            "run_id": "fixture",
            "live_supervisor_source_unchanged": True,
            "live_supervisor_loads_candidate_hook": False,
            "live_config_dir_unchanged": True,
            "dry_load_readback_executed": True,
            "dry_load_readback_mode": "local_proof_artifacts_only_not_timer_path",
            "entered_timer_path": False,
            "live_timer_path_loaded": False,
            "ran_supervisor": False,
            "remote_sync_performed": False,
            "remote_execution_performed": False,
            "candidate_execution_performed": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        self._write_json(control_path, control)
        summary = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9av_default_off_dry_load_readback.v1",
            "status": "ready",
            "blockers": [],
            "p9av_default_off_observe_only_dry_load_readback_ready": True,
            "eligible_for_owner_p9aw_review_after_readback": True,
            "allowed_next_gate": P9AW_GATE,
            "recommended_next_gate": P9AW_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "dry_load_readback_executed": True,
            "dry_load_readback_execution_scope": "local_proof_artifacts_only_not_timer_path",
            "dry_load_readback_mode": "local_proof_artifacts_only_not_timer_path",
            "dry_load_manifest_under_proof_artifacts": True,
            "dry_load_readback_under_proof_artifacts": True,
            "candidate_shadow_artifact_under_proof_artifacts": True,
            "executor_input_guard_under_proof_artifacts": True,
            "executor_consumes_baseline_only": True,
            "candidate_shadow_only": True,
            "candidate_plan_referenced_by_executor": False,
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
            "source_evidence": sources,
            "output_files": {
                "summary": str(summary_path),
                "dry_load_manifest": str(manifest_path),
                "candidate_shadow_artifact": str(candidate_shadow_path),
                "dry_load_readback": str(readback_path),
                "executor_input_guard": str(guard_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        for key in (
            "entered_timer_path",
            "live_timer_path_loaded",
            "live_timer_service_enabled_or_invoked",
            "ran_supervisor",
            "timer_path_invoked",
            "remote_execution_performed",
            "remote_control_plane_touched",
            "candidate_execution_performed",
            "candidate_live_order_submission_authorized",
            "live_order_submission_authorized",
            "target_plan_replaced",
            "executor_input_changed",
            "live_supervisor_loads_candidate_hook",
            "wrote_live_hook_config",
            "implemented_hook",
            "deployed_hook",
            "loaded_hook",
        ):
            summary[key] = False
        self._deep_update(summary, summary_overrides or {})
        self._write_json(summary_path, summary)
        return {
            "project_profile": project_profile,
            "p9av_summary": summary_path,
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
                Phase9AWReviewAfterP9AVTests._deep_update(target[key], value)
            else:
                target[key] = value


if __name__ == "__main__":
    unittest.main()
