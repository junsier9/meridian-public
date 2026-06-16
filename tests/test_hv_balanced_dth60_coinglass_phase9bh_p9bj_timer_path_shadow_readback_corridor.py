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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ba_p9bd_shadow_readback_proposal_corridor import (  # noqa: E402
    proof_boundary,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9be_p9bg_shadow_readback_execution_package_corridor import (  # noqa: E402
    APPROVE_CORRIDOR_DECISION as APPROVE_P9BE_P9BG_DECISION,
    CONTRACT_VERSION as P9BE_P9BG_CONTRACT,
    P9BH_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bh_p9bj_timer_path_shadow_readback_corridor import (  # noqa: E402
    APPROVE_CORRIDOR_DECISION,
    LOCAL_TIMER_READBACK_SCOPE,
    P9BI_GATE,
    P9BJ_GATE,
    P9BK_GATE,
    build_corridor,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9BHP9BJTimerPathShadowReadbackCorridorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bh-p9bj-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_corridor_ready_runs_p9bh_p9bj_no_order_readback(self) -> None:
        paths = self._write_ready_p9be_p9bg_bundle()
        output_root = self.temp_dir / "corridor"

        summary, exit_code = build_corridor(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 20, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["completed_gates"], ["P9BH", "P9BI", "P9BJ"])
        self.assertTrue(summary["p9bh_p9bj_corridor_ready"])
        self.assertTrue(summary["p9bh_owner_gate_ready"])
        self.assertTrue(summary["p9bi_timer_path_shadow_readback_ready"])
        self.assertTrue(summary["p9bj_retained_readiness_review_ready"])
        self.assertEqual(summary["timer_path_shadow_readback_scope"], LOCAL_TIMER_READBACK_SCOPE)
        self.assertTrue(summary["timer_path_shadow_readback_executed"])
        self.assertEqual(summary["allowed_next_gate"], P9BK_GATE)
        self.assertFalse(summary["live_timer_path_loaded"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["candidate_execution_performed"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertFalse(summary["live_config_changed"])
        self.assertFalse(summary["operator_state_changed"])
        self.assertFalse(summary["timer_state_changed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = output_root / "proof_artifacts"
        p9bh_summary = self._load_json(proof_root / "p9bh" / "20260608T200000Z" / "summary.json")
        p9bi_summary = self._load_json(proof_root / "p9bi" / "20260608T200000Z" / "summary.json")
        p9bj_summary = self._load_json(proof_root / "p9bj" / "20260608T200000Z" / "summary.json")
        package = self._load_json(
            proof_root
            / "p9bi"
            / "20260608T200000Z"
            / "timer_path_shadow_readback_execution_package.json"
        )
        readback = self._load_json(
            proof_root / "p9bi" / "20260608T200000Z" / "timer_path_shadow_readback.json"
        )
        guard = self._load_json(proof_root / "p9bi" / "20260608T200000Z" / "executor_input_guard.json")
        readiness = self._load_json(proof_root / "p9bj" / "20260608T200000Z" / "readiness_review.json")
        self.assertTrue(p9bh_summary["p9bh_owner_gate_ready"])
        self.assertEqual(p9bh_summary["allowed_next_gate"], P9BI_GATE)
        self.assertTrue(p9bh_summary["timer_path_shadow_readback_execution_authorized_in_p9bh"])
        self.assertTrue(p9bi_summary["p9bi_timer_path_shadow_readback_ready"])
        self.assertEqual(p9bi_summary["allowed_next_gate"], P9BJ_GATE)
        self.assertTrue(package["timer_path_shadow_readback_executed"])
        self.assertEqual(package["execution_scope"], LOCAL_TIMER_READBACK_SCOPE)
        self.assertFalse(package["default_enabled"])
        self.assertTrue(package["observe_only"])
        self.assertEqual(package["candidate_order_authority"], "disabled")
        self.assertEqual(package["executor_target_source"], "baseline_only")
        self.assertFalse(package["live_order_submission_authorized"])
        self.assertFalse(package["candidate_execution_authorized"])
        self.assertFalse(package["live_timer_path_loaded"])
        self.assertFalse(package["supervisor_invoked"])
        self.assertFalse(package["remote_sync_performed"])
        self.assertTrue(readback["timer_path_shadow_readback_executed"])
        self.assertEqual(readback["timer_path_shadow_readback_mode"], LOCAL_TIMER_READBACK_SCOPE)
        self.assertFalse(readback["live_timer_path_loaded"])
        self.assertFalse(readback["ran_supervisor"])
        self.assertFalse(readback["candidate_execution_performed"])
        self.assertEqual(readback["orders_submitted"], 0)
        self.assertTrue(guard["baseline_executor_input_hash_unchanged"])
        self.assertTrue(guard["executor_consumes_baseline_only"])
        self.assertFalse(guard["candidate_plan_referenced_by_executor"])
        self.assertTrue(p9bj_summary["p9bj_retained_readiness_review_ready"])
        self.assertEqual(p9bj_summary["allowed_next_gate"], P9BK_GATE)
        self.assertTrue(readiness["sufficient_for_future_p9bk_owner_gate_request"])
        self.assertFalse(readiness["candidate_execution_authorized"])
        self.assertFalse(readiness["live_order_submission_authorized"])

    def test_corridor_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_p9be_p9bg_bundle()

        summary, exit_code = build_corridor(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_submission",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 20, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9bh_p9bj_corridor", summary["blockers"])
        self.assertFalse(summary["p9bh_p9bj_corridor_ready"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_corridor_blocks_if_p9be_p9bg_does_not_point_to_p9bh(self) -> None:
        paths = self._write_ready_p9be_p9bg_bundle(
            p9be_p9bg_overrides={"allowed_next_gate": "P9BAD_live_order_gate"}
        )

        summary, exit_code = build_corridor(
            self._args(paths, output_root=self.temp_dir / "bad-p9be-p9bg"),
            now_fn=lambda: datetime(2026, 6, 8, 20, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9be_p9bg_ready_for_p9bh", summary["blockers"])
        self.assertFalse(summary["p9bh_p9bj_corridor_ready"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_corridor_blocks_if_current_supervisor_loads_candidate_hook(self) -> None:
        paths = self._write_ready_p9be_p9bg_bundle(
            supervisor_text="from dth60_observe_only_shadow_hook import run\n",
        )

        summary, exit_code = build_corridor(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 20, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9be_p9bg_ready_for_p9bh", summary["blockers"])
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
            phase9be_p9bg_summary=str(paths["p9be_p9bg_summary"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9be_p9bg_bundle(
        self,
        *,
        p9be_p9bg_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        p9be_p9bg_root = self.temp_dir / "p9be_p9bg"
        proof_root = p9be_p9bg_root / "proof_artifacts"
        p9be_p9bg_summary = p9be_p9bg_root / "summary.json"
        owner_record_path = p9be_p9bg_root / "owner_decision_record.json"
        p9be_summary_path = proof_root / "p9be" / "run" / "summary.json"
        p9bf_root = proof_root / "p9bf" / "run"
        p9bg_root = proof_root / "p9bg" / "run"
        p9bf_summary_path = p9bf_root / "summary.json"
        p9bg_summary_path = p9bg_root / "summary.json"
        execution_package_path = p9bf_root / "shadow_readback_execution_package.json"
        execution_checklist_path = p9bf_root / "execution_package_checklist.json"
        p9bf_matrix_path = p9bf_root / "non_authorization_matrix.json"
        p9bf_control_path = p9bf_root / "control_boundary_readback.json"
        readiness_path = p9bg_root / "readiness_review.json"
        readiness_checklist_path = p9bg_root / "readiness_checklist.json"
        p9bg_matrix_path = p9bg_root / "non_authorization_matrix.json"
        p9bg_control_path = p9bg_root / "control_boundary_readback.json"

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
        owner_record = self._p9be_p9bg_owner_record()
        p9bf_summary = self._p9bf_summary(
            execution_package_path,
            execution_checklist_path,
            p9bf_matrix_path,
            p9bf_control_path,
        )
        p9bg_summary = self._p9bg_summary(
            readiness_path,
            readiness_checklist_path,
            p9bg_matrix_path,
            p9bg_control_path,
        )
        execution_package = self._p9bf_execution_package(owner_record)
        readiness = self._p9bg_readiness(owner_record)
        self._write_json(owner_record_path, owner_record)
        self._write_json(p9be_summary_path, {"status": "ready"})
        self._write_json(p9bf_summary_path, p9bf_summary)
        self._write_json(p9bg_summary_path, p9bg_summary)
        self._write_json(execution_package_path, execution_package)
        self._write_json(execution_checklist_path, {"status": "ready"})
        self._write_json(p9bf_matrix_path, {"status": "ready"})
        self._write_json(p9bf_control_path, {"status": "ready"})
        self._write_json(readiness_path, readiness)
        self._write_json(readiness_checklist_path, {"status": "ready"})
        self._write_json(p9bg_matrix_path, {"status": "ready"})
        self._write_json(p9bg_control_path, {"status": "ready"})

        summary = {
            "contract_version": P9BE_P9BG_CONTRACT,
            "status": "ready",
            "blockers": [],
            "run_id": "unit-test-p9be-p9bg",
            "completed_gates": ["P9BE", "P9BF", "P9BG"],
            "p9be_p9bg_corridor_ready": True,
            "p9be_owner_gate_ready": True,
            "p9bf_execution_package_ready": True,
            "p9bg_retained_readiness_review_ready": True,
            "eligible_for_future_p9bh_owner_gate_request": True,
            "allowed_next_gate": P9BH_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "owner_decision": owner_record,
            "source_evidence": sources,
            "live_supervisor_source_unchanged": True,
            "live_config_dir_unchanged": True,
            "output_files": {
                "summary": str(p9be_p9bg_summary),
                "owner_decision_record": str(owner_record_path),
                "p9be_summary": str(p9be_summary_path),
                "p9bf_summary": str(p9bf_summary_path),
                "p9bg_summary": str(p9bg_summary_path),
            },
        }
        summary.update(proof_boundary())
        self._deep_update(summary, p9be_p9bg_overrides or {})
        self._write_json(p9be_p9bg_summary, summary)
        return {
            "project_profile": project_profile,
            "p9be_p9bg_summary": p9be_p9bg_summary,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }

    @staticmethod
    def _p9be_p9bg_owner_record() -> dict:
        record = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9be_p9bg_owner_decision.v1",
            "owner": "rulebook_owner",
            "decision": APPROVE_P9BE_P9BG_DECISION,
            "decision_source": "unit_test",
            "recorded_at_utc": "2026-06-08T19:00:00Z",
            "p9be_owner_gate_approved": True,
            "p9bf_execution_package_preparation_approved": True,
            "p9bg_retained_readiness_review_approved": True,
        }
        for key in (
            "timer_path_shadow_readback_execution_approved",
            "live_order_submission_approved",
            "dry_load_readback_execution_approved",
            "candidate_execution_approved",
            "remote_sync_approved",
            "remote_execution_approved",
            "supervisor_invocation_approved",
            "supervisor_run_approved",
        ):
            record[key] = False
        return record

    @staticmethod
    def _p9bf_summary(
        package_path: Path,
        checklist_path: Path,
        matrix_path: Path,
        control_path: Path,
    ) -> dict:
        summary = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bf_shadow_readback_execution_package.v1",
            "status": "ready",
            "blockers": [],
            "p9bf_execution_package_ready": True,
            "execution_package_prepared": True,
            "execution_authorized_in_p9bf": False,
            "allowed_next_gate": (
                "P9BG_retained_readiness_review_after_shadow_readback_execution_package_only_"
                "if_separately_requested"
            ),
            "output_files": {
                "shadow_readback_execution_package": str(package_path),
                "execution_package_checklist": str(checklist_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        summary.update(proof_boundary())
        return summary

    @staticmethod
    def _p9bg_summary(
        readiness_path: Path,
        checklist_path: Path,
        matrix_path: Path,
        control_path: Path,
    ) -> dict:
        summary = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bg_retained_readiness_review.v1",
            "status": "ready",
            "blockers": [],
            "p9bg_retained_readiness_review_ready": True,
            "eligible_for_future_p9bh_owner_gate_request": True,
            "allowed_next_gate": P9BH_GATE,
            "readiness_review_authorized": True,
            "output_files": {
                "readiness_review": str(readiness_path),
                "readiness_checklist": str(checklist_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        summary.update(proof_boundary())
        return summary

    @staticmethod
    def _p9bf_execution_package(owner_record: dict) -> dict:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bf_shadow_readback_execution_package.v1",
            "run_id": "unit-test-p9be-p9bg",
            "owner_decision": owner_record,
            "execution_package_prepared": True,
            "package_written_under_proof_artifacts": True,
            "package_body_kind": "shadow_readback_execution_package_not_execution",
            "default_enabled": False,
            "observe_only": True,
            "candidate_order_authority": "disabled",
            "executor_target_source": "baseline_only",
            "candidate_shadow_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "future_execution_contract": {
                "baseline_only_executor_required": True,
                "candidate_shadow_only_required": True,
                "candidate_plan_must_not_be_referenced_by_executor": True,
                "zero_order_cancel_fill_trade_delta_required": True,
                "timer_path_shadow_readback_execution_requires_separate_owner_gate": True,
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

    @staticmethod
    def _p9bg_readiness(owner_record: dict) -> dict:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bg_readiness_review.v1",
            "run_id": "unit-test-p9be-p9bg",
            "owner_decision": owner_record,
            "retained_readiness_review_ready": True,
            "sufficient_for_future_shadow_readback_execution_owner_gate_request": True,
            "allowed_next_gate": P9BH_GATE,
            "dry_load_readback_execution_authorized": False,
            "timer_path_shadow_readback_authorized": False,
            "live_order_submission_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
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
                Phase9BHP9BJTimerPathShadowReadbackCorridorTests._deep_update(target[key], value)
            else:
                target[key] = value


if __name__ == "__main__":
    unittest.main()
