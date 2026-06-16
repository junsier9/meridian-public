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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bo_prepare_timer_path_shadow_cycles_proposal import (  # noqa: E402
    APPROVE_P9BO_DECISION,
    CONTRACT_VERSION as P9BO_CONTRACT,
    FALSE_RUNTIME_KEYS as P9BO_FALSE_RUNTIME_KEYS,
    P9BP_GATE,
    P9BP_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bp_owner_gate_allow_timer_path_shadow_cycles import (  # noqa: E402
    APPROVE_P9BP_DECISION,
    P9BQ_GATE,
    build_p9bp,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9BPOwnerGateAllowTimerPathShadowCyclesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9bp-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_owner_gate_ready_allows_future_p9bq_only(self) -> None:
        paths = self._write_ready_p9bo_bundle()
        output_root = self.temp_dir / "p9bp"

        summary, exit_code = build_p9bp(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 10, 3, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9bp_owner_gate_ready"])
        self.assertTrue(summary["p9bo_proposal_review_package_ready_for_p9bp"])
        self.assertTrue(summary["future_continuous_timer_path_shadow_cycles_execution_authorized"])
        self.assertTrue(summary["continuous_timer_path_shadow_cycles_execution_authorized_for_future_gate"])
        self.assertTrue(summary["p9bq_execution_gate_authorized"])
        self.assertEqual(summary["allowed_next_gate"], P9BQ_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(summary["continuous_timer_path_shadow_cycles_execution_authorized"])
        self.assertFalse(summary["continuous_timer_path_shadow_cycles_executed_in_p9bp"])
        self.assertFalse(summary["execute_cycles_inside_p9bp_authorized"])
        self.assertFalse(summary["timer_path_load_authorized_in_p9bp"])
        self.assertFalse(summary["supervisor_invocation_authorized_in_p9bp"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["entered_timer_path"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = output_root / "proof_artifacts" / "p9bp" / "20260610T030000Z"
        permission = _load_json(proof_root / "execution_permission.json")
        acceptance = _load_json(proof_root / "acceptance_contract.json")
        matrix = _load_json(proof_root / "non_authorization_matrix.json")
        control = _load_json(proof_root / "control_boundary_readback.json")
        self.assertTrue(permission["permission_ready"])
        self.assertTrue(permission["continuous_timer_path_shadow_cycles_execution_authorized_for_future_gate"])
        self.assertFalse(permission["execute_cycles_inside_p9bp"])
        self.assertEqual(permission["allowed_next_gate"], P9BQ_GATE)
        self.assertEqual(acceptance["minimum_cycle_count"], 3)
        self.assertTrue(acceptance["fresh_proof_each_cycle"])
        self.assertTrue(acceptance["baseline_only_executor_input_each_cycle"])
        self.assertTrue(acceptance["candidate_shadow_only_each_cycle"])
        self.assertTrue(acceptance["candidate_artifacts_under_proof_artifacts_only_each_cycle"])
        self.assertTrue(acceptance["candidate_plan_must_not_be_referenced_by_executor_each_cycle"])
        self.assertFalse(acceptance["live_order_submission_authorized"])
        self.assertTrue(matrix["authorizations"]["future_continuous_timer_path_shadow_cycles_execution"])
        self.assertFalse(matrix["authorizations"]["execute_cycles_inside_p9bp"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(control["live_supervisor_loads_candidate_hook"])
        self.assertFalse(control["continuous_timer_path_shadow_cycles_executed_in_p9bp"])
        self.assertFalse(control["live_order_submission_authorized"])
        self.assertEqual(control["orders_submitted"], 0)

    def test_owner_gate_blocks_wrong_owner_decision(self) -> None:
        paths = self._write_ready_p9bo_bundle()

        summary, exit_code = build_p9bp(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_live_order_submission",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 3, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn(
            "owner_decision_p9bp_allow_future_continuous_cycles_no_order_only",
            summary["blockers"],
        )
        self.assertFalse(summary["future_continuous_timer_path_shadow_cycles_execution_authorized"])
        self.assertFalse(summary["p9bq_execution_gate_authorized"])
        self.assertFalse(summary["continuous_timer_path_shadow_cycles_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_owner_gate_blocks_if_p9bo_does_not_allow_p9bp(self) -> None:
        paths = self._write_ready_p9bo_bundle(
            p9bo_overrides={"allowed_next_gate": "P9BAD_live_order_gate"}
        )

        summary, exit_code = build_p9bp(
            self._args(paths, output_root=self.temp_dir / "bad-p9bo"),
            now_fn=lambda: datetime(2026, 6, 10, 3, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bo_proposal_review_package_ready_for_p9bp", summary["blockers"])
        self.assertIn("p9bo_allows_p9bp_only", summary["blockers"])
        self.assertFalse(summary["future_continuous_timer_path_shadow_cycles_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_owner_gate_blocks_if_current_supervisor_already_loads_hook(self) -> None:
        paths = self._write_ready_p9bo_bundle(
            supervisor_text="from dth60_observe_only_shadow_hook import run\n"
        )

        summary, exit_code = build_p9bp(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 10, 3, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bo_proposal_review_package_ready_for_p9bp", summary["blockers"])
        self.assertIn("current_live_supervisor_not_already_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["future_continuous_timer_path_shadow_cycles_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BP_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9bo_summary=str(paths["p9bo_summary"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9bo_bundle(
        self,
        *,
        p9bo_overrides: dict[str, object] | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        p9bo_root = self.temp_dir / "p9bo"
        proof_root = p9bo_root / "proof_artifacts" / "p9bo" / "run"
        summary_path = p9bo_root / "summary.json"
        owner_path = p9bo_root / "owner_decision_record.json"
        package_path = proof_root / "proposal_review_package.json"
        acceptance_path = proof_root / "acceptance_contract.json"
        checklist_path = proof_root / "review_checklist.json"
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
        acceptance = self._acceptance()
        owner = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bo_owner_decision.v1",
            "decision": APPROVE_P9BO_DECISION,
            "proposal_review_package_preparation_approved": True,
            "future_continuous_timer_path_shadow_cycles_owner_gate_discussion_approved": True,
            "continuous_timer_path_shadow_cycles_execution_approved": False,
            "timer_path_shadow_readback_execution_approved": False,
            "supervisor_invocation_approved": False,
            "candidate_execution_approved": False,
            "live_order_submission_approved": False,
        }
        package = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bo_proposal_review_package.v1",
            "package_prepared": True,
            "package_sink": "proof_artifacts_only",
            "proposed_future_gate": P9BP_GATE,
            "proposed_future_gate_scope": P9BP_SCOPE,
            "proposed_future_gate_must_be_separately_requested": True,
            "acceptance_contract": acceptance,
            "execution_authorized_in_p9bo": False,
            "supervisor_invocation_authorized_in_p9bo": False,
            "remote_sync_authorized_in_p9bo": False,
            "candidate_execution_authorized_in_p9bo": False,
            "live_order_submission_authorized_in_p9bo": False,
        }
        checklist = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bo_review_checklist.v1",
            "checks": {
                "minimum_cycle_count_is_three": True,
                "fresh_proof_each_cycle_required": True,
                "same_risk_inputs_required": True,
                "baseline_only_executor_required": True,
                "candidate_shadow_only_required": True,
                "candidate_artifacts_proof_only_required": True,
                "candidate_plan_not_referenced_required": True,
                "zero_order_cancel_fill_trade_required": True,
                "no_live_config_operator_timer_mutation_required": True,
                "p9bo_execution_not_authorized": True,
            },
        }
        matrix = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bo_non_authorization_matrix.v1",
            "authorizations": {
                "proposal_review_package_preparation": True,
                "future_continuous_timer_path_shadow_cycles_owner_gate_discussion": True,
            },
        }
        for key in (
            "continuous_timer_path_shadow_cycles_execution",
            "timer_path_shadow_readback_execution",
            "supervisor_invocation",
            "supervisor_run",
            "remote_sync",
            "remote_execution",
            "candidate_execution",
            "candidate_live_order_submission",
            "live_order_submission",
            "target_plan_replacement",
            "executor_input_mutation",
            "live_config_mutation",
            "operator_state_mutation",
            "timer_or_service_mutation",
            "production_timer_service_load",
            "stage_governance_change",
        ):
            matrix["authorizations"][key] = False
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bo_control_boundary_readback.v1",
            "live_supervisor_source_unchanged": True,
            "live_supervisor_loads_candidate_hook": False,
            "live_config_dir_unchanged": True,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "trade_count": 0,
            "exchange_order_submission": "disabled",
        }
        summary = {
            "contract_version": P9BO_CONTRACT,
            "status": "ready",
            "blockers": [],
            "p9bo_proposal_review_package_ready": True,
            "proposal_review_package_prepared": True,
            "proposal_review_package_under_proof_artifacts": True,
            "eligible_for_future_p9bp_owner_gate_request": True,
            "allowed_next_gate": P9BP_GATE,
            "allowed_next_gate_scope": P9BP_SCOPE,
            "allowed_next_gate_must_be_separately_requested": True,
            "candidate_order_authority": "disabled",
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "shadow_only_not_executor",
            "candidate_artifact_sink": "proof_artifacts_only",
            "executor_consumes_baseline_only": True,
            "candidate_plan_referenced_by_executor": False,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "trade_count": 0,
            "exchange_order_submission": "disabled",
            "source_evidence": source,
            "output_files": {
                "summary": str(summary_path),
                "owner_decision_record": str(owner_path),
                "proposal_review_package": str(package_path),
                "acceptance_contract": str(acceptance_path),
                "review_checklist": str(checklist_path),
                "non_authorization_matrix": str(matrix_path),
                "control_boundary_readback": str(control_path),
            },
        }
        for key in P9BO_FALSE_RUNTIME_KEYS:
            summary[key] = False
            control[key] = False
        if p9bo_overrides:
            summary.update(p9bo_overrides)
        _write_json(owner_path, owner)
        _write_json(package_path, package)
        _write_json(acceptance_path, acceptance)
        _write_json(checklist_path, checklist)
        _write_json(matrix_path, matrix)
        _write_json(control_path, control)
        _write_json(summary_path, summary)
        return {
            "project_profile": project_profile,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
            "p9bo_summary": summary_path,
        }

    @staticmethod
    def _acceptance() -> dict[str, object]:
        return {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bo_acceptance_contract.v1",
            "future_gate": P9BP_GATE,
            "future_gate_scope": P9BP_SCOPE,
            "future_gate_must_be_separately_requested": True,
            "minimum_cycle_count": 3,
            "cycles_must_be_continuous": True,
            "cycles_must_share_same_no_order_config": True,
            "cycles_must_use_real_live_supervisor_timer_path": True,
            "production_timer_service_load_requires_separate_gate": True,
            "fresh_proof_each_cycle": True,
            "unique_timestamp_each_cycle": True,
            "same_risk_inputs_as_baseline_plan_each_cycle": True,
            "baseline_only_executor_input_each_cycle": True,
            "candidate_shadow_only_each_cycle": True,
            "candidate_artifacts_under_proof_artifacts_only_each_cycle": True,
            "candidate_plan_must_not_be_referenced_by_executor_each_cycle": True,
            "target_plan_must_not_be_replaced_each_cycle": True,
            "executor_input_must_not_change_each_cycle": True,
            "zero_order_delta_each_cycle": True,
            "zero_cancel_delta_each_cycle": True,
            "zero_fill_delta_each_cycle": True,
            "zero_trade_delta_each_cycle": True,
            "live_config_must_not_change": True,
            "operator_state_must_not_change": True,
            "timer_state_must_not_change": True,
            "candidate_order_authority": "disabled",
            "live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
        }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
