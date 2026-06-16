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
    APPROVE_CORRIDOR_DECISION as APPROVE_P9BA_P9BD_DECISION,
    CONTRACT_VERSION as P9BA_P9BD_CONTRACT,
    P9BE_GATE,
    proof_boundary,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9be_p9bg_shadow_readback_execution_package_corridor import (  # noqa: E402
    APPROVE_CORRIDOR_DECISION,
    P9BF_GATE,
    P9BG_GATE,
    P9BH_GATE,
    build_corridor,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9BEP9BGShadowReadbackExecutionPackageCorridorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9be-p9bg-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_corridor_ready_runs_p9be_p9bg_proof_only(self) -> None:
        paths = self._write_ready_p9ba_p9bd_bundle()
        output_root = self.temp_dir / "corridor"

        summary, exit_code = build_corridor(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 19, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9be_p9bg_corridor_ready"])
        self.assertEqual(summary["completed_gates"], ["P9BE", "P9BF", "P9BG"])
        self.assertTrue(summary["p9be_owner_gate_ready"])
        self.assertTrue(summary["p9bf_execution_package_ready"])
        self.assertTrue(summary["p9bg_retained_readiness_review_ready"])
        self.assertEqual(summary["allowed_next_gate"], P9BH_GATE)
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
        p9be_summary = self._load_json(proof_root / "p9be" / "20260608T190000Z" / "summary.json")
        p9bf_summary = self._load_json(proof_root / "p9bf" / "20260608T190000Z" / "summary.json")
        p9bg_summary = self._load_json(proof_root / "p9bg" / "20260608T190000Z" / "summary.json")
        package = self._load_json(
            proof_root / "p9bf" / "20260608T190000Z" / "shadow_readback_execution_package.json"
        )
        readiness = self._load_json(proof_root / "p9bg" / "20260608T190000Z" / "readiness_review.json")
        self.assertTrue(p9be_summary["p9be_owner_gate_ready"])
        self.assertEqual(p9be_summary["allowed_next_gate"], P9BF_GATE)
        self.assertFalse(p9be_summary["execution_authorized_in_p9be"])
        self.assertTrue(p9bf_summary["p9bf_execution_package_ready"])
        self.assertEqual(p9bf_summary["allowed_next_gate"], P9BG_GATE)
        self.assertFalse(p9bf_summary["execution_authorized_in_p9bf"])
        self.assertTrue(package["execution_package_prepared"])
        self.assertFalse(package["default_enabled"])
        self.assertTrue(package["observe_only"])
        self.assertEqual(package["candidate_order_authority"], "disabled")
        self.assertEqual(package["executor_target_source"], "baseline_only")
        self.assertFalse(package["future_execution_contract"]["live_order_submission_authorized"])
        self.assertFalse(package["executed_actions"]["dry_load_readback_executed"])
        self.assertFalse(package["executed_actions"]["timer_path_shadow_readback_executed"])
        self.assertFalse(package["executed_actions"]["supervisor_invoked"])
        self.assertFalse(package["executed_actions"]["candidate_execution_performed"])
        self.assertEqual(package["executed_actions"]["orders_submitted"], 0)
        self.assertTrue(p9bg_summary["p9bg_retained_readiness_review_ready"])
        self.assertEqual(p9bg_summary["allowed_next_gate"], P9BH_GATE)
        self.assertTrue(readiness["sufficient_for_future_shadow_readback_execution_owner_gate_request"])
        self.assertFalse(readiness["timer_path_shadow_readback_authorized"])
        self.assertFalse(readiness["live_order_submission_authorized"])

    def test_corridor_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_p9ba_p9bd_bundle()

        summary, exit_code = build_corridor(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_submission",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 19, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9be_p9bg_corridor", summary["blockers"])
        self.assertFalse(summary["p9be_p9bg_corridor_ready"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_corridor_blocks_if_p9ba_p9bd_does_not_point_to_p9be(self) -> None:
        paths = self._write_ready_p9ba_p9bd_bundle(
            p9ba_p9bd_overrides={"allowed_next_gate": "P9BAD_live_order_gate"}
        )

        summary, exit_code = build_corridor(
            self._args(paths, output_root=self.temp_dir / "bad-p9ba-p9bd"),
            now_fn=lambda: datetime(2026, 6, 8, 19, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9ba_p9bd_ready_for_p9be", summary["blockers"])
        self.assertFalse(summary["p9be_p9bg_corridor_ready"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_corridor_blocks_if_current_supervisor_loads_candidate_hook(self) -> None:
        paths = self._write_ready_p9ba_p9bd_bundle(
            supervisor_text="from dth60_observe_only_shadow_hook import run\n",
        )

        summary, exit_code = build_corridor(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 19, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9ba_p9bd_ready_for_p9be", summary["blockers"])
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
            phase9ba_p9bd_summary=str(paths["p9ba_p9bd_summary"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9ba_p9bd_bundle(
        self,
        *,
        p9ba_p9bd_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        p9ba_p9bd_root = self.temp_dir / "p9ba_p9bd"
        proof_root = p9ba_p9bd_root / "proof_artifacts"
        p9ba_p9bd_summary = p9ba_p9bd_root / "summary.json"
        owner_record_path = p9ba_p9bd_root / "owner_decision_record.json"
        p9ba_summary_path = proof_root / "p9ba" / "run" / "summary.json"
        p9bb_summary_path = proof_root / "p9bb" / "run" / "summary.json"
        p9bc_root = proof_root / "p9bc" / "run"
        p9bd_root = proof_root / "p9bd" / "run"
        p9bc_summary_path = p9bc_root / "summary.json"
        p9bd_summary_path = p9bd_root / "summary.json"
        proposal_path = p9bc_root / "shadow_readback_proposal_package.json"
        proposal_checklist_path = p9bc_root / "proposal_acceptance_checklist.json"
        p9bc_matrix_path = p9bc_root / "non_authorization_matrix.json"
        p9bc_control_path = p9bc_root / "control_boundary_readback.json"
        readiness_path = p9bd_root / "readiness_review.json"
        readiness_checklist_path = p9bd_root / "readiness_checklist.json"
        p9bd_matrix_path = p9bd_root / "non_authorization_matrix.json"
        p9bd_control_path = p9bd_root / "control_boundary_readback.json"

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
        owner_record = self._p9ba_p9bd_owner_record()
        p9bc_summary = self._p9bc_summary(
            proposal_path,
            proposal_checklist_path,
            p9bc_matrix_path,
            p9bc_control_path,
        )
        p9bd_summary = self._p9bd_summary(
            readiness_path,
            readiness_checklist_path,
            p9bd_matrix_path,
            p9bd_control_path,
        )
        proposal = self._p9bc_proposal(owner_record)
        readiness = self._p9bd_readiness(owner_record)
        self._write_json(owner_record_path, owner_record)
        self._write_json(p9ba_summary_path, {"status": "ready"})
        self._write_json(p9bb_summary_path, {"status": "ready"})
        self._write_json(p9bc_summary_path, p9bc_summary)
        self._write_json(p9bd_summary_path, p9bd_summary)
        self._write_json(proposal_path, proposal)
        self._write_json(proposal_checklist_path, {"status": "ready"})
        self._write_json(p9bc_matrix_path, {"status": "ready"})
        self._write_json(p9bc_control_path, {"status": "ready"})
        self._write_json(readiness_path, readiness)
        self._write_json(readiness_checklist_path, {"status": "ready"})
        self._write_json(p9bd_matrix_path, {"status": "ready"})
        self._write_json(p9bd_control_path, {"status": "ready"})

        summary = {
            "contract_version": P9BA_P9BD_CONTRACT,
            "status": "ready",
            "blockers": [],
            "run_id": "unit-test-p9ba-p9bd",
            "completed_gates": ["P9BA", "P9BB", "P9BC", "P9BD"],
            "p9ba_p9bd_corridor_ready": True,
            "p9ba_review_ready": True,
            "p9bb_permission_ready": True,
            "p9bc_proposal_package_ready": True,
            "p9bd_retained_readiness_review_ready": True,
            "eligible_for_future_p9be_owner_gate_request": True,
            "allowed_next_gate": P9BE_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "owner_decision": owner_record,
            "source_evidence": sources,
            "output_files": {
                "summary": str(p9ba_p9bd_summary),
                "owner_decision_record": str(owner_record_path),
                "p9ba_summary": str(p9ba_summary_path),
                "p9bb_summary": str(p9bb_summary_path),
                "p9bc_summary": str(p9bc_summary_path),
                "p9bd_summary": str(p9bd_summary_path),
            },
        }
        summary.update(proof_boundary())
        self._deep_update(summary, p9ba_p9bd_overrides or {})
        self._write_json(p9ba_p9bd_summary, summary)
        return {
            "project_profile": project_profile,
            "p9ba_p9bd_summary": p9ba_p9bd_summary,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }

    @staticmethod
    def _p9ba_p9bd_owner_record() -> dict:
        record = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9ba_p9bd_owner_decision.v1",
            "owner": "rulebook_owner",
            "decision": APPROVE_P9BA_P9BD_DECISION,
            "decision_source": "unit_test",
            "recorded_at_utc": "2026-06-08T18:00:00Z",
            "p9ba_review_approved": True,
            "p9bb_proposal_preparation_permission_approved": True,
            "p9bc_proposal_package_generation_approved": True,
            "p9bd_retained_readiness_review_approved": True,
        }
        for key in (
            "live_order_submission_approved",
            "dry_load_readback_execution_approved",
            "timer_path_shadow_readback_execution_approved",
            "candidate_execution_approved",
            "remote_sync_approved",
            "remote_execution_approved",
            "supervisor_invocation_approved",
            "supervisor_run_approved",
        ):
            record[key] = False
        return record

    @staticmethod
    def _p9bc_summary(
        proposal_path: Path,
        checklist_path: Path,
        matrix_path: Path,
        control_path: Path,
    ) -> dict:
        summary = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bc_shadow_readback_proposal_package.v1",
            "status": "ready",
            "blockers": [],
            "p9bc_proposal_package_ready": True,
            "generated_proposal_package": True,
            "proposal_package_generation_authorized": True,
            "allowed_next_gate": (
                "P9BD_retained_readiness_review_after_shadow_readback_proposal_package_only_"
                "if_separately_requested"
            ),
            "dry_load_readback_execution_authorized": False,
            "timer_path_shadow_readback_authorized": False,
            "live_order_submission_authorized": False,
            "output_files": {
                "shadow_readback_proposal_package": str(proposal_path),
                "proposal_acceptance_checklist": str(checklist_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        summary.update(proof_boundary())
        return summary

    @staticmethod
    def _p9bd_summary(
        readiness_path: Path,
        checklist_path: Path,
        matrix_path: Path,
        control_path: Path,
    ) -> dict:
        summary = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bd_retained_readiness_review.v1",
            "status": "ready",
            "blockers": [],
            "p9bd_retained_readiness_review_ready": True,
            "sufficient_for_future_timer_path_shadow_readback_owner_gate_request": True,
            "allowed_next_gate": P9BE_GATE,
            "dry_load_readback_execution_authorized": False,
            "timer_path_shadow_readback_authorized": False,
            "live_order_submission_authorized": False,
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
    def _p9bc_proposal(owner_record: dict) -> dict:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bc_shadow_readback_proposal_package.v1",
            "run_id": "unit-test-p9ba-p9bd",
            "proposal_package_generated": True,
            "package_written_under_proof_artifacts": True,
            "package_body_kind": "shadow_readback_gate_proposal_package_not_execution",
            "default_enabled": False,
            "observe_only": True,
            "candidate_order_authority": "disabled",
            "executor_target_source": "baseline_only",
            "candidate_shadow_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "owner_decision": owner_record,
            "proposal_contract": {
                "fresh_account_read_required_before_any_future_remote_or_timer_path": True,
                "baseline_only_executor_required": True,
                "candidate_shadow_only_required": True,
                "zero_order_cancel_fill_trade_delta_required": True,
                "dry_load_readback_requires_separate_owner_gate": True,
                "timer_path_shadow_readback_requires_separate_owner_gate": True,
                "live_order_submission_authorized": False,
            },
        }

    @staticmethod
    def _p9bd_readiness(owner_record: dict) -> dict:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bd_readiness_review.v1",
            "run_id": "unit-test-p9ba-p9bd",
            "owner_decision": owner_record,
            "retained_readiness_review_ready": True,
            "sufficient_for_future_timer_path_shadow_readback_owner_gate_request": True,
            "allowed_next_gate": P9BE_GATE,
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
                Phase9BEP9BGShadowReadbackExecutionPackageCorridorTests._deep_update(
                    target[key], value
                )
            else:
                target[key] = value


if __name__ == "__main__":
    unittest.main()
