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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bk_review_after_p9bh_p9bj import (  # noqa: E402
    APPROVE_P9BK_DECISION,
    P9BL_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bl_real_timer_path_shadow_readback_owner_gate import (  # noqa: E402
    APPROVE_P9BL_DECISION,
    FALSE_OWNER_KEYS,
    FALSE_SUMMARY_KEYS,
    P9BM_GATE,
    build_phase9bl,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9BLRealTimerPathShadowReadbackOwnerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bl-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_owner_gate_ready_allows_future_real_timer_path_shadow_readback_only(self) -> None:
        paths = self._write_ready_p9bk_bundle()
        output_root = self.temp_dir / "p9bl"

        summary, exit_code = build_phase9bl(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 22, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9bl_owner_gate_ready"])
        self.assertTrue(summary["p9bk_retained_evidence_ready_for_p9bl"])
        self.assertTrue(summary["future_real_timer_path_shadow_readback_authorized"])
        self.assertTrue(summary["p9bm_execution_gate_authorized"])
        self.assertEqual(summary["allowed_next_gate"], P9BM_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(summary["real_timer_path_shadow_readback_executed_in_p9bl"])
        self.assertFalse(summary["timer_path_load_authorized_in_p9bl"])
        self.assertFalse(summary["supervisor_invocation_authorized_in_p9bl"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["live_timer_path_loaded"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = output_root / "proof_artifacts" / "p9bl" / "20260608T220000Z"
        permission = self._load_json(proof_root / "execution_permission.json")
        acceptance = self._load_json(proof_root / "acceptance_contract.json")
        matrix = self._load_json(proof_root / "non_authorization_matrix.json")
        control = self._load_json(proof_root / "control_boundary_readback.json")
        self.assertTrue(permission["readback_execution_authorized_for_future_gate"])
        self.assertEqual(permission["allowed_next_gate"], P9BM_GATE)
        self.assertFalse(permission["readback_executed_in_p9bl"])
        self.assertFalse(permission["future_p9bm_must_reprove"]["live_order_submission_authorized"])
        self.assertTrue(acceptance["checks_required_before_p9bm_can_pass"]["baseline_only_executor"])
        self.assertFalse(acceptance["p9bl_executed_readback"])
        self.assertTrue(matrix["authorizations"]["future_real_timer_path_shadow_readback"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(control["live_supervisor_loads_candidate_hook"])
        self.assertFalse(control["live_order_submission_authorized"])
        self.assertEqual(control["orders_submitted"], 0)

    def test_owner_gate_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_p9bk_bundle()

        summary, exit_code = build_phase9bl(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_submission",
            ),
            now_fn=lambda: datetime(2026, 6, 8, 22, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn(
            "owner_decision_p9bl_allow_future_real_timer_path_shadow_readback_no_order_only",
            summary["blockers"],
        )
        self.assertFalse(summary["future_real_timer_path_shadow_readback_authorized"])
        self.assertFalse(summary["p9bm_execution_gate_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertEqual(summary["orders_submitted"], 0)

    def test_owner_gate_blocks_if_p9bk_does_not_allow_p9bl(self) -> None:
        paths = self._write_ready_p9bk_bundle(
            p9bk_overrides={"allowed_next_gate": "P9BAD_live_order_gate"}
        )

        summary, exit_code = build_phase9bl(
            self._args(paths, output_root=self.temp_dir / "bad-p9bk"),
            now_fn=lambda: datetime(2026, 6, 8, 22, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bk_retained_evidence_ready_for_p9bl", summary["blockers"])
        self.assertIn("p9bk_allows_p9bl_only", summary["blockers"])
        self.assertFalse(summary["future_real_timer_path_shadow_readback_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_owner_gate_blocks_if_current_supervisor_already_loads_hook(self) -> None:
        paths = self._write_ready_p9bk_bundle(
            supervisor_text="from dth60_observe_only_shadow_hook import run\n",
        )

        summary, exit_code = build_phase9bl(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 22, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bk_retained_evidence_ready_for_p9bl", summary["blockers"])
        self.assertIn("current_live_supervisor_not_already_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["future_real_timer_path_shadow_readback_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BL_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9bk_summary=str(paths["p9bk_summary"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9bk_bundle(
        self,
        *,
        p9bk_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        p9bk_root = self.temp_dir / "p9bk"
        proof_root = p9bk_root / "proof_artifacts" / "p9bk" / "run"
        summary_path = p9bk_root / "summary.json"
        owner_path = p9bk_root / "owner_decision_record.json"
        review_path = proof_root / "owner_review_packet.json"
        checklist_path = proof_root / "sufficiency_checklist.json"
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
        source = {
            "hook_module": {"path": str(hook_module), "exists": True, "sha256": hook_sha},
            "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
            "live_config_dir": {"path": str(live_config_dir), "exists": True, "sha256": live_config_sha},
        }
        owner = self._owner_record()
        review = self._review_packet(owner, source)
        checklist = self._checklist()
        matrix = self._matrix()
        control = self._control(source, supervisor_sha, live_config_sha)
        summary = {
            **self._false_summary_fields(),
            "contract_version": "hv_balanced_dth60_coinglass_phase9bk_review_after_p9bh_p9bj.v1",
            "status": "ready",
            "blockers": [],
            "run_id": "unit-test-p9bk",
            "review_scope": "p9bk_retained_evidence_review_after_p9bh_p9bj_only",
            "p9bk_retained_evidence_review_ready": True,
            "p9bh_p9bj_retained_evidence_sufficient": True,
            "sufficient_for_next_owner_gate_discussion": True,
            "eligible_for_future_p9bl_owner_gate_request": True,
            "allowed_next_gate": P9BL_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "shadow_only_not_executor",
            "candidate_artifact_sink": "proof_artifacts_only",
            "executor_consumes_baseline_only": True,
            "candidate_plan_referenced_by_executor": False,
            "exchange_order_submission": "disabled",
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "source_evidence": source,
            "owner_decision": owner,
            "output_files": {
                "summary": str(summary_path),
                "owner_decision_record": str(owner_path),
                "owner_review_packet": str(review_path),
                "sufficiency_checklist": str(checklist_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        if p9bk_overrides:
            summary.update(p9bk_overrides)
            review.update(p9bk_overrides)

        self._write_json(owner_path, owner)
        self._write_json(review_path, review)
        self._write_json(checklist_path, checklist)
        self._write_json(matrix_path, matrix)
        self._write_json(control_path, control)
        self._write_json(summary_path, summary)
        return {
            "project_profile": project_profile,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
            "p9bk_summary": summary_path,
        }

    @staticmethod
    def _false_summary_fields() -> dict[str, object]:
        payload = {key: False for key in FALSE_SUMMARY_KEYS}
        payload["orders_submitted"] = 0
        payload["fill_count"] = 0
        payload["fills_observed"] = 0
        payload["exchange_order_submission"] = "disabled"
        return payload

    @staticmethod
    def _owner_record() -> dict[str, object]:
        payload = {key: False for key in FALSE_OWNER_KEYS}
        payload.update(
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9bk_owner_decision.v1",
                "decision": APPROVE_P9BK_DECISION,
                "retained_evidence_review_approved": True,
                "p9bh_p9bj_sufficiency_review_approved": True,
            }
        )
        return payload

    def _review_packet(self, owner: dict[str, object], source: dict[str, object]) -> dict[str, object]:
        payload = self._false_summary_fields()
        payload.update(
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9bk_owner_review_packet.v1",
                "p9bh_p9bj_retained_evidence_sufficient": True,
                "sufficient_for_next_owner_gate_discussion": True,
                "allowed_next_gate": P9BL_GATE,
                "allowed_next_gate_must_be_separately_requested": True,
                "candidate_order_authority": "disabled",
                "execution_target_source": "baseline_only",
                "candidate_overlay_execution_path": "shadow_only_not_executor",
                "candidate_artifact_sink": "proof_artifacts_only",
                "executor_consumes_baseline_only": True,
                "candidate_plan_referenced_by_executor": False,
                "owner_decision": owner,
                "source_evidence": source,
            }
        )
        return payload

    @staticmethod
    def _checklist() -> dict[str, object]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bk_sufficiency_checklist.v1",
            "checks": {
                "p9bh_p9bj_status_ready": True,
                "p9bi_readback_executed": True,
                "p9bi_scope_local_proof_only": True,
                "baseline_executor_input_hash_unchanged": True,
                "executor_consumes_baseline_only": True,
                "candidate_not_executed": True,
                "live_timer_path_not_loaded": True,
                "supervisor_not_run": True,
                "remote_not_touched": True,
                "zero_orders_fills": True,
                "next_scope_not_defined_in_p9bk": True,
                "live_order_not_authorized": True,
            },
        }

    @staticmethod
    def _matrix() -> dict[str, object]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bk_non_authorization_matrix.v1",
            "authorizations": {
                "retained_evidence_review": True,
                "future_next_owner_gate_request": True,
                "define_next_gate_scope": False,
                "next_gate_execution": False,
                "timer_path_shadow_readback_execution": False,
                "candidate_execution": False,
                "candidate_live_order_submission": False,
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

    def _control(
        self,
        source: dict[str, object],
        supervisor_sha: str,
        live_config_sha: str,
    ) -> dict[str, object]:
        payload = self._false_summary_fields()
        payload.update(
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9bk_control_boundary_readback.v1",
                "source_evidence": source,
                "candidate_order_authority": "disabled",
                "execution_target_source": "baseline_only",
                "candidate_overlay_execution_path": "shadow_only_not_executor",
                "candidate_artifact_sink": "proof_artifacts_only",
                "executor_consumes_baseline_only": True,
                "candidate_plan_referenced_by_executor": False,
                "live_supervisor_source_unchanged": True,
                "live_supervisor_loads_candidate_hook": False,
                "live_config_dir_unchanged": True,
                "live_supervisor_sha256_before": supervisor_sha,
                "live_supervisor_sha256_after": supervisor_sha,
                "live_config_dir_sha256_before": live_config_sha,
                "live_config_dir_sha256_after": live_config_sha,
            }
        )
        return payload

    @staticmethod
    def _write_json(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _load_json(path: Path) -> dict[str, object]:
        with path.open(encoding="utf-8") as handle:
            return dict(json.load(handle))


if __name__ == "__main__":
    unittest.main()
