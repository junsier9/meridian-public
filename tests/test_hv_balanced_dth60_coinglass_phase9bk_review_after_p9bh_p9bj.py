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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bh_p9bj_timer_path_shadow_readback_corridor import (  # noqa: E402
    APPROVE_CORRIDOR_DECISION as APPROVE_P9BH_P9BJ_DECISION,
    CONTRACT_VERSION as P9BH_P9BJ_CONTRACT,
    LOCAL_TIMER_READBACK_SCOPE,
    P9BJ_GATE,
    P9BK_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bk_review_after_p9bh_p9bj import (  # noqa: E402
    APPROVE_P9BK_DECISION,
    P9BL_GATE,
    build_p9bk,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9BKReviewAfterP9BHP9BJTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bk-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_review_ready_only_opens_next_owner_gate_scope_discussion(self) -> None:
        paths = self._write_ready_p9bh_p9bj_bundle()
        output_root = self.temp_dir / "p9bk"

        summary, exit_code = build_p9bk(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 21, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9bk_retained_evidence_review_ready"])
        self.assertTrue(summary["p9bh_p9bj_retained_evidence_sufficient"])
        self.assertTrue(summary["sufficient_for_next_owner_gate_discussion"])
        self.assertEqual(summary["allowed_next_gate"], P9BL_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(summary["define_next_gate_scope_authorized"])
        self.assertFalse(summary["next_gate_execution_authorized"])
        self.assertFalse(summary["timer_path_shadow_readback_execution_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["live_timer_path_loaded"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = output_root / "proof_artifacts" / "p9bk" / "20260608T210000Z"
        review = self._load_json(proof_root / "owner_review_packet.json")
        checklist = self._load_json(proof_root / "sufficiency_checklist.json")
        matrix = self._load_json(proof_root / "non_authorization_matrix.json")
        self.assertTrue(review["p9bh_p9bj_retained_evidence_sufficient"])
        self.assertEqual(review["allowed_next_gate"], P9BL_GATE)
        self.assertFalse(review["define_next_gate_scope_authorized"])
        self.assertFalse(review["live_order_submission_authorized"])
        self.assertTrue(checklist["checks"]["p9bi_readback_executed"])
        self.assertTrue(checklist["checks"]["p9bi_scope_local_proof_only"])
        self.assertTrue(checklist["checks"]["zero_orders_fills"])
        self.assertFalse(matrix["authorizations"]["define_next_gate_scope"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])

    def test_review_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_p9bh_p9bj_bundle()

        summary, exit_code = build_p9bk(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_submission",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 21, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9bk_review_only", summary["blockers"])
        self.assertFalse(summary["p9bk_retained_evidence_review_ready"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_review_blocks_if_p9bh_p9bj_does_not_point_to_p9bk(self) -> None:
        paths = self._write_ready_p9bh_p9bj_bundle(
            p9bh_p9bj_overrides={"allowed_next_gate": "P9BAD_live_order_gate"}
        )

        summary, exit_code = build_p9bk(
            self._args(paths, output_root=self.temp_dir / "bad-p9bh-p9bj"),
            now_fn=lambda: datetime(2026, 6, 8, 21, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bh_p9bj_retained_evidence_sufficient", summary["blockers"])
        self.assertIn("p9bj_allowed_p9bk_only", summary["blockers"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_review_blocks_if_current_supervisor_loads_candidate_hook(self) -> None:
        paths = self._write_ready_p9bh_p9bj_bundle(
            supervisor_text="from dth60_observe_only_shadow_hook import run\n",
        )

        summary, exit_code = build_p9bk(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 21, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bh_p9bj_retained_evidence_sufficient", summary["blockers"])
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BK_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9bh_p9bj_summary=str(paths["p9bh_p9bj_summary"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9bh_p9bj_bundle(
        self,
        *,
        p9bh_p9bj_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        root = self.temp_dir / "p9bh_p9bj"
        proof_root = root / "proof_artifacts"
        summary_path = root / "summary.json"
        owner_record_path = root / "owner_decision_record.json"
        p9bh_summary_path = proof_root / "p9bh" / "run" / "summary.json"
        p9bi_root = proof_root / "p9bi" / "run"
        p9bj_root = proof_root / "p9bj" / "run"
        p9bi_summary_path = p9bi_root / "summary.json"
        p9bj_summary_path = p9bj_root / "summary.json"
        package_path = p9bi_root / "timer_path_shadow_readback_execution_package.json"
        manifest_path = p9bi_root / "timer_path_shadow_readback_manifest.json"
        shadow_path = p9bi_root / "candidate_shadow_artifact.json"
        guard_path = p9bi_root / "executor_input_guard.json"
        readback_path = p9bi_root / "timer_path_shadow_readback.json"
        p9bi_matrix_path = p9bi_root / "non_authorization_matrix.json"
        p9bi_control_path = p9bi_root / "control_boundary_readback.json"
        readiness_path = p9bj_root / "readiness_review.json"
        readiness_checklist_path = p9bj_root / "readiness_checklist.json"
        p9bj_matrix_path = p9bj_root / "non_authorization_matrix.json"
        p9bj_control_path = p9bj_root / "control_boundary_readback.json"

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
        owner = self._owner_record()
        package = self._p9bi_package()
        readback = self._p9bi_readback()
        guard = self._p9bi_guard()
        p9bi_summary = self._p9bi_summary(
            package_path,
            manifest_path,
            shadow_path,
            guard_path,
            readback_path,
            p9bi_matrix_path,
            p9bi_control_path,
        )
        p9bj_summary = self._p9bj_summary(
            readiness_path,
            readiness_checklist_path,
            p9bj_matrix_path,
            p9bj_control_path,
        )
        readiness = self._p9bj_readiness(owner)
        self._write_json(owner_record_path, owner)
        self._write_json(p9bh_summary_path, {"status": "ready"})
        self._write_json(package_path, package)
        self._write_json(manifest_path, {"status": "ready"})
        self._write_json(shadow_path, {"status": "ready"})
        self._write_json(guard_path, guard)
        self._write_json(readback_path, readback)
        self._write_json(p9bi_matrix_path, {"status": "ready"})
        self._write_json(p9bi_control_path, {"status": "ready"})
        self._write_json(readiness_path, readiness)
        self._write_json(readiness_checklist_path, {"status": "ready"})
        self._write_json(p9bj_matrix_path, {"status": "ready"})
        self._write_json(p9bj_control_path, {"status": "ready"})
        self._write_json(p9bi_summary_path, p9bi_summary)
        self._write_json(p9bj_summary_path, p9bj_summary)

        summary = {
            "contract_version": P9BH_P9BJ_CONTRACT,
            "status": "ready",
            "blockers": [],
            "run_id": "unit-test-p9bh-p9bj",
            "completed_gates": ["P9BH", "P9BI", "P9BJ"],
            "p9bh_p9bj_corridor_ready": True,
            "p9bh_owner_gate_ready": True,
            "p9bi_timer_path_shadow_readback_ready": True,
            "p9bj_retained_readiness_review_ready": True,
            "timer_path_shadow_readback_executed": True,
            "timer_path_shadow_readback_scope": LOCAL_TIMER_READBACK_SCOPE,
            "eligible_for_future_p9bk_owner_gate_request": True,
            "allowed_next_gate": P9BK_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
            "candidate_artifact_sink": "proof_artifacts_only",
            "executor_consumes_baseline_only": True,
            "candidate_shadow_only": True,
            "candidate_plan_referenced_by_executor": False,
            "owner_decision": owner,
            "source_evidence": sources,
            "output_files": {
                "summary": str(summary_path),
                "owner_decision_record": str(owner_record_path),
                "p9bh_summary": str(p9bh_summary_path),
                "p9bi_summary": str(p9bi_summary_path),
                "p9bj_summary": str(p9bj_summary_path),
            },
            **self._no_live_fields(),
        }
        self._deep_update(summary, p9bh_p9bj_overrides or {})
        self._write_json(summary_path, summary)
        return {
            "project_profile": project_profile,
            "p9bh_p9bj_summary": summary_path,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }

    @staticmethod
    def _owner_record() -> dict:
        record = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bh_p9bj_owner_decision.v1",
            "owner": "rulebook_owner",
            "decision": APPROVE_P9BH_P9BJ_DECISION,
            "decision_source": "unit_test",
            "recorded_at_utc": "2026-06-08T20:00:00Z",
            "p9bh_owner_gate_approved": True,
            "p9bi_timer_path_shadow_readback_execution_approved": True,
            "p9bj_retained_readiness_review_approved": True,
            "p9bi_timer_path_shadow_readback_execution_scope": LOCAL_TIMER_READBACK_SCOPE,
        }
        for key in (
            "live_order_submission_approved",
            "candidate_execution_approved",
            "remote_sync_approved",
            "remote_execution_approved",
            "supervisor_invocation_approved",
            "supervisor_run_approved",
        ):
            record[key] = False
        return record

    @staticmethod
    def _p9bi_summary(
        package_path: Path,
        manifest_path: Path,
        shadow_path: Path,
        guard_path: Path,
        readback_path: Path,
        matrix_path: Path,
        control_path: Path,
    ) -> dict:
        summary = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bi_timer_path_shadow_readback.v1",
            "status": "ready",
            "blockers": [],
            "p9bi_timer_path_shadow_readback_ready": True,
            "timer_path_shadow_readback_mode": LOCAL_TIMER_READBACK_SCOPE,
            "timer_path_shadow_readback_scope": LOCAL_TIMER_READBACK_SCOPE,
            "timer_path_shadow_readback_executed": True,
            "allowed_next_gate": P9BJ_GATE,
            "candidate_execution_performed": False,
            "live_order_submission_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "output_files": {
                "timer_path_shadow_readback_execution_package": str(package_path),
                "timer_path_shadow_readback_manifest": str(manifest_path),
                "candidate_shadow_artifact": str(shadow_path),
                "executor_input_guard": str(guard_path),
                "timer_path_shadow_readback": str(readback_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
            **Phase9BKReviewAfterP9BHP9BJTests._no_live_fields(),
        }
        return summary

    @staticmethod
    def _p9bi_package() -> dict:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bi_timer_path_shadow_readback_execution_package.v1",
            "package_written_under_proof_artifacts": True,
            "execution_scope": LOCAL_TIMER_READBACK_SCOPE,
            "default_enabled": False,
            "observe_only": True,
            "candidate_order_authority": "disabled",
            "executor_target_source": "baseline_only",
            "candidate_shadow_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "timer_path_shadow_readback_executed": True,
            "live_timer_path_loaded": False,
            "supervisor_invoked": False,
            "remote_sync_performed": False,
            "orders_submitted": 0,
            "fill_count": 0,
        }

    @staticmethod
    def _p9bi_readback() -> dict:
        no_live_fields = Phase9BKReviewAfterP9BHP9BJTests._no_live_fields()
        no_live_fields.pop("applied_to_live")
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bi_timer_path_shadow_readback.v1",
            "timer_path_shadow_readback_ok": True,
            "timer_path_shadow_readback_executed": True,
            "timer_path_shadow_readback_mode": LOCAL_TIMER_READBACK_SCOPE,
            "default_enabled": False,
            "observe_only": True,
            "executor_consumes_baseline_only": True,
            "candidate_shadow_only": True,
            "candidate_execution_performed": False,
            "candidate_plan_referenced_by_executor": False,
            "baseline_executor_input_hash_unchanged": True,
            "live_timer_path_loaded": False,
            "ran_supervisor": False,
            "remote_execution_performed": False,
            "executor_input_changed": False,
            "target_plan_replaced": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            **no_live_fields,
        }

    @staticmethod
    def _p9bi_guard() -> dict:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bi_executor_input_guard.v1",
            "baseline_executor_input_hash_unchanged": True,
            "executor_consumes_baseline_only": True,
            "candidate_plan_referenced_by_executor": False,
            "executor_input_changed": False,
            "target_plan_replaced": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }

    @staticmethod
    def _p9bj_summary(
        readiness_path: Path,
        checklist_path: Path,
        matrix_path: Path,
        control_path: Path,
    ) -> dict:
        summary = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bj_retained_readiness_review.v1",
            "status": "ready",
            "blockers": [],
            "p9bj_retained_readiness_review_ready": True,
            "eligible_for_future_p9bk_owner_gate_request": True,
            "allowed_next_gate": P9BK_GATE,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "output_files": {
                "readiness_review": str(readiness_path),
                "readiness_checklist": str(checklist_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
            **Phase9BKReviewAfterP9BHP9BJTests._no_live_fields(),
        }
        return summary

    @staticmethod
    def _p9bj_readiness(owner: dict) -> dict:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bj_readiness_review.v1",
            "owner_decision": owner,
            "retained_readiness_review_ready": True,
            "timer_path_shadow_readback_executed_in_p9bi": True,
            "timer_path_shadow_readback_scope": LOCAL_TIMER_READBACK_SCOPE,
            "sufficient_for_future_p9bk_owner_gate_request": True,
            "allowed_next_gate": P9BK_GATE,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
        }

    @staticmethod
    def _no_live_fields() -> dict:
        return {
            "live_timer_path_loaded": False,
            "live_timer_service_enabled_or_invoked": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "remote_execution_performed": False,
            "remote_control_plane_touched": False,
            "candidate_execution_authorized": False,
            "candidate_execution_performed": False,
            "candidate_live_order_submission_authorized": False,
            "live_order_submission_authorized": False,
            "executor_input_changed": False,
            "target_plan_replaced": False,
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "wrote_live_hook_config": False,
            "implemented_hook": False,
            "deployed_hook": False,
            "loaded_hook": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }

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
                Phase9BKReviewAfterP9BHP9BJTests._deep_update(target[key], value)
            else:
                target[key] = value


if __name__ == "__main__":
    unittest.main()
