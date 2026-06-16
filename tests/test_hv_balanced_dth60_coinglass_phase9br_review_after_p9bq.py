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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bq_timer_path_shadow_cycles import (  # noqa: E402
    APPROVE_P9BQ_DECISION,
    CONTRACT_VERSION as P9BQ_CONTRACT,
    P9BR_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9br_review_after_p9bq import (  # noqa: E402
    APPROVE_P9BR_DECISION,
    P9BS_GATE,
    build_p9br,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9BRReviewAfterP9BQTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9br-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_ready_p9bq_shadow_cycles_are_sufficient_for_execution_path_change_discussion_only(
        self,
    ) -> None:
        paths = self._write_ready_p9bq_bundle()

        summary, exit_code = build_p9br(
            self._args(paths, output_root=self.temp_dir / "p9br"),
            now_fn=lambda: datetime(2026, 6, 10, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9br_retained_evidence_review_ready"])
        self.assertTrue(summary["p9bq_retained_shadow_cycles_sufficient"])
        self.assertTrue(summary["sufficient_for_execution_path_change_discussion"])
        self.assertEqual(summary["allowed_next_gate"], P9BS_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(summary["execution_path_change_discussion_scope_definition_authorized"])
        self.assertFalse(summary["execution_path_change_implementation_authorized"])
        self.assertFalse(summary["execution_path_change_execution_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["entered_timer_path"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = self.temp_dir / "p9br" / "proof_artifacts" / "p9br" / "20260610T050000Z"
        review = _load_json(proof_root / "owner_review_packet.json")
        checklist = _load_json(proof_root / "sufficiency_checklist.json")
        matrix = _load_json(proof_root / "non_authorization_matrix.json")
        control = _load_json(proof_root / "control_boundary_readback.json")
        self.assertTrue(review["sufficient_for_execution_path_change_discussion"])
        self.assertTrue(checklist["checks"]["p9bq_completed_at_least_three_cycles"])
        self.assertTrue(checklist["checks"]["all_cycle_readbacks_ready"])
        self.assertTrue(checklist["checks"]["current_live_supervisor_not_loading_hook"])
        self.assertFalse(matrix["authorizations"]["execution_path_change_implementation"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])
        self.assertFalse(control["supervisor_entrypoint_invoked"])
        self.assertFalse(control["remote_sync_performed"])

    def test_wrong_owner_decision_blocks_without_opening_discussion_gate(self) -> None:
        paths = self._write_ready_p9bq_bundle()

        summary, exit_code = build_p9br(
            self._args(
                paths,
                output_root=self.temp_dir / "wrong-owner",
                owner_decision="approve_execution_path_change_implementation",
            ),
            now_fn=lambda: datetime(2026, 6, 10, 5, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9br_review_only", summary["blockers"])
        self.assertFalse(summary["p9br_retained_evidence_review_ready"])
        self.assertFalse(summary["execution_path_change_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_fewer_than_three_shadow_cycles_blocks_sufficiency(self) -> None:
        paths = self._write_ready_p9bq_bundle(
            p9bq_overrides={
                "completed_shadow_cycles": 2,
                "target_plan_sha256_each_cycle": [TARGET_SHA, TARGET_SHA],
            }
        )

        summary, exit_code = build_p9br(
            self._args(paths, output_root=self.temp_dir / "too-few-cycles"),
            now_fn=lambda: datetime(2026, 6, 10, 5, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9bq_completed_at_least_three_cycles", summary["blockers"])
        self.assertIn("p9bq_retained_shadow_cycles_sufficient", summary["blockers"])
        self.assertFalse(summary["sufficient_for_execution_path_change_discussion"])
        self.assertFalse(summary["execution_path_change_implementation_authorized"])

    def test_current_supervisor_loading_hook_blocks_sufficiency_discussion(self) -> None:
        paths = self._write_ready_p9bq_bundle(
            supervisor_text="from enhengclaw.live_trading import dth60_observe_only_shadow_hook\n"
        )

        summary, exit_code = build_p9br(
            self._args(paths, output_root=self.temp_dir / "supervisor-loads-hook"),
            now_fn=lambda: datetime(2026, 6, 10, 5, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertIn("p9bq_retained_shadow_cycles_sufficient", summary["blockers"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9BR_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9bq_summary=str(paths["p9bq_summary"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_p9bq_bundle(
        self,
        *,
        p9bq_overrides: dict[str, object] | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        run_id = "20260610T044500Z"
        project_profile = self.temp_dir / "project_profile.json"
        hook_module = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        p9bq_root = self.temp_dir / "p9bq"
        proof_root = p9bq_root / "proof_artifacts" / "p9bq" / run_id
        summary_path = p9bq_root / "summary.json"
        owner_path = p9bq_root / "owner_decision_record.json"
        generated_config_path = proof_root / "generated_no_order_timer_path_config.json"
        position_fixture_path = proof_root / "position_reference" / "run_summary.json"
        retained_fixture_path = proof_root / "acct_fx" / "retained_account_plan_fixture_summary.json"
        control_path = proof_root / "control_boundary_readback.json"
        matrix_path = proof_root / "non_authorization_matrix.json"
        cycle_paths = [
            proof_root / f"cycle_{index:03d}_timer_path_shadow_readback.json"
            for index in range(1, 4)
        ]

        live_config_dir.mkdir(parents=True)
        hook_module.write_text("# hook fixture\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        _write_json(project_profile, {"current_stage": "stage_1_research_readiness_only"})

        hook_sha = file_sha256(hook_module)
        supervisor_sha = file_sha256(supervisor)
        live_config_sha = tree_sha256(live_config_dir)
        owner = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bq_owner_decision.v1",
            "decision": APPROVE_P9BQ_DECISION,
            "continuous_timer_path_shadow_cycles_execution_approved": True,
            "supervisor_entrypoint_invocation_approved": True,
            "observe_only_hook_invocation_approved": True,
            "retained_pit_safe_fixture_use_approved": True,
            "generated_no_order_config_approved": True,
            "candidate_execution_approved": False,
            "candidate_live_order_submission_approved": False,
            "live_order_submission_approved": False,
            "target_plan_replacement_approved": False,
            "executor_input_mutation_approved": False,
            "live_config_mutation_approved": False,
            "operator_state_mutation_approved": False,
            "timer_or_service_mutation_approved": False,
            "production_timer_service_load_approved": False,
            "remote_sync_approved": False,
            "remote_execution_approved": False,
            "repo_stage_change_approved": False,
        }
        generated_config = {"risk": {"trading_enabled": False}}
        position_fixture = {"status": "position_genesis_snapshot", "proof_artifacts_only": True}
        retained_fixture = {"status": "ready", "proof_artifacts_only": True}
        control = {
            "supervisor_entrypoint_invoked": True,
            "completed_shadow_cycles": 3,
            "production_timer_service_loaded_or_modified": False,
            "systemd_timer_service_invoked": False,
            "remote_sync_performed": False,
            "live_config_changed": False,
            "timer_state_changed": False,
            "executor_input_changed": False,
            "target_plan_replaced": False,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
        }
        matrix = {
            "authorizations": {
                "continuous_timer_path_shadow_cycles_execution": True,
                "generated_no_order_config": True,
                "observe_only_hook_invocation": True,
                "retained_pit_safe_fixture_use": True,
                "supervisor_entrypoint_invocation": True,
                "candidate_execution": False,
                "candidate_live_order_submission": False,
                "executor_input_mutation": False,
                "live_config_mutation": False,
                "live_order_submission": False,
                "operator_state_mutation": False,
                "production_timer_service_load": False,
                "remote_execution": False,
                "remote_sync": False,
                "stage_governance_change": False,
                "target_plan_replacement": False,
                "timer_or_service_mutation": False,
            }
        }
        cycles = [self._cycle_row(index) for index in range(1, 4)]
        for path, row in zip(cycle_paths, cycles):
            _write_json(path, row)
        _write_json(owner_path, owner)
        _write_json(generated_config_path, generated_config)
        _write_json(position_fixture_path, position_fixture)
        _write_json(retained_fixture_path, retained_fixture)
        _write_json(control_path, control)
        _write_json(matrix_path, matrix)

        summary = {
            "contract_version": P9BQ_CONTRACT,
            "status": "ready",
            "blockers": [],
            "p9bq_timer_path_shadow_cycles_ready": True,
            "continuous_timer_path_shadow_cycles_ready": True,
            "continuous_timer_path_shadow_cycles_executed": True,
            "completed_shadow_cycles": 3,
            "fresh_proof_each_cycle": True,
            "same_risk_no_order_config_each_cycle": True,
            "same_target_plan_hash_each_cycle": True,
            "target_plan_sha256_each_cycle": [TARGET_SHA, TARGET_SHA, TARGET_SHA],
            "supervisor_entrypoint_invoked": True,
            "systemd_timer_service_invoked": False,
            "production_timer_service_loaded_or_modified": False,
            "executor_consumes_baseline_only": True,
            "execution_target_source": "baseline_only",
            "candidate_shadow_only": True,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "candidate_order_authority": "disabled",
            "candidate_overlay_execution_path": "shadow_only_not_executor",
            "candidate_execution_authorized": False,
            "candidate_execution_performed": False,
            "candidate_live_order_submission_authorized": False,
            "live_order_submission_authorized": False,
            "candidate_plan_referenced_by_executor": False,
            "executor_input_changed": False,
            "target_plan_replaced": False,
            "live_config_changed": False,
            "operator_state_changed_outside_generated_p9bq_state": False,
            "timer_state_changed": False,
            "remote_sync_performed": False,
            "remote_execution_performed": False,
            "zero_order_cancel_fill_trade_delta": True,
            "orders_submitted": 0,
            "orders_canceled": 0,
            "fill_count": 0,
            "trade_count": 0,
            "allowed_next_gate": P9BR_GATE,
            "allowed_next_gate_must_be_separately_requested": True,
            "cycle_rows": cycles,
            "source_evidence": {
                "hook_module": {"path": str(hook_module), "exists": True, "sha256": hook_sha},
                "live_supervisor": {"path": str(supervisor), "exists": True, "sha256": supervisor_sha},
                "live_config_dir": {
                    "path": str(live_config_dir),
                    "exists": True,
                    "sha256": live_config_sha,
                },
            },
            "output_files": {
                "owner_decision_record": str(owner_path),
                "generated_no_order_config": str(generated_config_path),
                "position_reference_fixture": str(position_fixture_path),
                "retained_account_plan_fixture": str(retained_fixture_path),
                "control_boundary_readback": str(control_path),
                "non_authorization_matrix": str(matrix_path),
                "cycle_001_readback": str(cycle_paths[0]),
                "cycle_002_readback": str(cycle_paths[1]),
                "cycle_003_readback": str(cycle_paths[2]),
            },
        }
        summary.update(p9bq_overrides or {})
        _write_json(summary_path, summary)

        return {
            "project_profile": project_profile,
            "hook_module": hook_module,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
            "p9bq_summary": summary_path,
        }

    def _cycle_row(self, index: int) -> dict[str, object]:
        return {
            "cycle_index": index,
            "cycle_ready": True,
            "supervisor_exit_code": 0,
            "target_plan_sha256": TARGET_SHA,
            "supervisor_summary": {
                "status": "mainnet_live_supervisor_completed",
                "blockers": [],
                "completed_cycle_count": 1,
                "live_delta_authorized": False,
                "orders_submitted": 0,
                "fill_count": 0,
                "exchange_order_submission": "disabled",
            },
            "hook_summary": {
                "contract_version": "hv_balanced_dth60_observe_only_shadow_hook.v1",
                "status": "ready",
                "blockers": [],
                "hook_enabled": True,
                "mode": "observe_only",
                "artifact_sink": "proof_artifacts_only",
                "candidate_order_authority": "disabled",
                "candidate_live_order_submission_authorized": False,
                "mainnet_order_submission_authorized": False,
                "exchange_order_submission": "disabled",
                "execution_target_source": "baseline_only",
                "candidate_overlay_execution_path": "excluded",
                "candidate_artifacts_under_proof_artifacts_only": True,
                "candidate_artifacts_written_count": 4,
                "executor_consumes_baseline_only": True,
                "executor_input_plan_hash_equals_baseline": True,
                "executor_input_plan_hash_unchanged": True,
                "executor_input_plan_sha256_before_hook": TARGET_SHA,
                "executor_input_plan_sha256_after_hook": TARGET_SHA,
                "baseline_target_plan_byte_for_byte_unchanged": True,
                "candidate_plan_referenced_by_executor": False,
                "candidate_shadow_plan_sha256": CANDIDATE_SHA,
                "live_config_changed": False,
                "operator_state_changed": False,
                "timer_state_changed": False,
                "candidate_orders_submitted": 0,
                "candidate_fill_count": 0,
                "orders_submitted": 0,
                "fill_count": 0,
            },
        }


TARGET_SHA = "a" * 64
CANDIDATE_SHA = "b" * 64


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))

