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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9al_default_off_readback_owner_gate import (  # noqa: E402
    P9AM_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9am_default_off_readback_execution import (  # noqa: E402
    APPROVE_P9AM_DECISION,
    build_phase9am,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
    resolve_path,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    tree_sha256,
)


class Phase9AMDefaultOffReadbackExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-p9am-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9am_executes_default_off_observe_only_shadow_readback(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "p9am-ready"

        summary, exit_code = build_phase9am(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 8, 6, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9am_default_off_observe_only_readback_ready"])
        self.assertTrue(summary["default_off_observe_only_readback_execution_authorized"])
        self.assertTrue(summary["executed_default_off_observe_only_readback"])
        self.assertTrue(summary["dry_load_readback_executed"])
        self.assertTrue(summary["dry_load_outputs_under_proof_artifacts"])
        self.assertTrue(summary["default_off_config_loaded"])
        self.assertFalse(summary["default_off_hook_enabled"])
        self.assertTrue(summary["observe_only_shadow_writer_enabled_in_proof_harness"])
        self.assertTrue(summary["observe_only_shadow_readback_ready"])
        self.assertGreater(summary["candidate_shadow_artifacts_written_count"], 0)
        self.assertTrue(summary["candidate_artifacts_under_proof_artifacts_only"])
        self.assertTrue(summary["baseline_target_plan_byte_for_byte_unchanged"])
        self.assertTrue(summary["executor_input_hash_unchanged"])
        self.assertTrue(summary["executor_input_hash_equals_baseline"])
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertTrue(summary["candidate_shadow_hash_differs_from_executor"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["target_plan_replaced"])
        self.assertFalse(summary["executor_input_changed"])
        self.assertTrue(summary["eligible_for_owner_p9an_review"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertFalse(summary["remote_sync_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["entered_live_timer_path"])
        self.assertFalse(summary["live_timer_path_loaded"])
        self.assertFalse(summary["live_timer_service_enabled_or_invoked"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["fills_observed"], 0)

        proof_root = output_root / "proof_artifacts" / "p9am" / "20260608T060000Z"
        for name in (
            "dry_load_execution_manifest.json",
            "default_off_config_readback.json",
            "observe_only_shadow_readback_summary.json",
            "executor_input_readback.json",
            "control_boundary_readback.json",
            "input_plans/baseline_target_plan.json",
            "input_plans/executor_input_target_plan.json",
            "input_plans/candidate_shadow_plan.json",
            "observe_only_shadow_output/shadow_hook/candidate_shadow_plan.json",
        ):
            self.assertTrue((proof_root / name).exists(), name)

        config = self._load_json(proof_root / "default_off_config_readback.json")
        self.assertFalse(config["hook_config_enabled_default"])
        self.assertTrue(config["observe_only_shadow_writer_enabled_in_proof_harness"])
        self.assertEqual(config["artifact_sink"], "proof_artifacts_only")
        self.assertEqual(config["candidate_order_authority"], "disabled")
        self.assertFalse(config["candidate_live_order_submission_authorized"])
        self.assertEqual(config["execution_target_source"], "baseline_only")

        executor = self._load_json(proof_root / "executor_input_readback.json")
        self.assertTrue(executor["executor_input_hash_equals_baseline"])
        self.assertTrue(executor["candidate_shadow_hash_differs_from_executor"])
        self.assertFalse(executor["candidate_plan_referenced_by_executor"])
        self.assertEqual(executor["orders_submitted"], 0)

        shadow = self._load_json(proof_root / "observe_only_shadow_readback_summary.json")
        self.assertTrue(shadow["hook_enabled"])
        self.assertTrue(shadow["executor_consumes_baseline_only"])
        self.assertGreater(shadow["candidate_artifacts_written_count"], 0)
        self.assertTrue(shadow["candidate_artifacts_under_proof_artifacts_only"])

    def test_phase9am_blocks_wrong_owner_without_readback(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "wrong-owner"

        summary, exit_code = build_phase9am(
            self._args(paths, output_root=output_root, owner_decision="approve_live_orders"),
            now_fn=lambda: datetime(2026, 6, 8, 6, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_p9am_execute_readback_only", summary["blockers"])
        self.assertFalse(summary["executed_default_off_observe_only_readback"])
        self.assertFalse(summary["dry_load_readback_executed"])
        self.assertFalse(summary["observe_only_shadow_writer_enabled_in_proof_harness"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        proof_root = output_root / "proof_artifacts" / "p9am" / "20260608T060500Z"
        self.assertFalse((proof_root / "input_plans" / "baseline_target_plan.json").exists())
        self.assertTrue((proof_root / "control_boundary_readback.json").exists())

    def test_phase9am_blocks_when_p9al_gate_allows_orders(self) -> None:
        paths = self._write_ready_inputs(
            p9al_gate_overrides={
                "allowed_next_action_constraints": {
                    "candidate_live_order_submission_authorized": True,
                    "orders_submitted_must_equal": 1,
                }
            }
        )

        summary, exit_code = build_phase9am(
            self._args(paths, output_root=self.temp_dir / "bad-gate"),
            now_fn=lambda: datetime(2026, 6, 8, 6, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9al_readback_owner_gate_ready", summary["blockers"])
        self.assertFalse(summary["executed_default_off_observe_only_readback"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9am_blocks_when_current_supervisor_loads_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9am(
            self._args(paths, output_root=self.temp_dir / "supervisor-imports-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 6, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["executed_default_off_observe_only_readback"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9AM_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9al_summary=str(paths["phase9al"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9al_summary_overrides: dict | None = None,
        p9al_gate_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9al = self.temp_dir / "phase9al" / "summary.json"
        proof_root = self.temp_dir / "phase9al" / "proof_artifacts" / "p9al" / "run"
        gate_path = proof_root / "readback_execution_gate.json"
        supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        live_config_dir = self.temp_dir / "config" / "live_trading"
        live_config_dir.mkdir(parents=True)
        (live_config_dir / "baseline.yaml").write_text("baseline: true\n", encoding="utf-8")
        supervisor.write_text(supervisor_text, encoding="utf-8")
        supervisor_sha = file_sha256(supervisor)
        live_config_sha = tree_sha256(live_config_dir)
        self._write_json(
            project_profile,
            {
                "current_stage": "stage_1_research_readiness_only",
                "target_stage": "stage_4_automated_execution",
            },
        )
        source_evidence = {
            "hook_module": {"exists": True, "path": str(hook_path), "sha256": hook_sha},
            "live_supervisor": {"exists": True, "path": str(supervisor), "sha256": supervisor_sha},
            "live_config_dir": {"exists": True, "path": str(live_config_dir), "sha256": live_config_sha},
        }
        p9al_summary = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9al_default_off_readback_owner_gate.v1",
            "status": "ready",
            "blockers": [],
            "gate_scope": "owner_gated_default_off_observe_only_timer_path_dry_load_readback_execution_permission_only",
            "p9al_default_off_observe_only_readback_owner_gate_ready": True,
            "eligible_to_execute_default_off_observe_only_readback": True,
            "executed_default_off_observe_only_readback": False,
            "dry_load_readback_executed": False,
            "allowed_next_gate": P9AM_GATE,
            "future_readback_default_off_required": True,
            "future_readback_observe_only_required": True,
            "future_readback_artifact_sink_required": "proof_artifacts_only",
            "future_readback_executor_input_required": "baseline_only",
            "future_readback_candidate_order_authority_required": "disabled",
            "future_readback_live_order_submission_authorized_required": False,
            "future_readback_candidate_execution_authorized_required": False,
            "dry_load_readback_execution_authorized": False,
            "timer_hook_implementation_authorized": False,
            "hook_deployment_authorized": False,
            "timer_path_load_authorized": False,
            "supervisor_invocation_authorized": False,
            "remote_sync_authorized": False,
            "remote_execution_authorized": False,
            "candidate_execution_authorized": False,
            "live_order_submission_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "live_config_mutation_authorized": False,
            "operator_state_mutation_authorized": False,
            "timer_or_service_mutation_authorized": False,
            "production_timer_service_load_authorized": False,
            "repo_stage_change_authorized": False,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifact_sink": "proof_artifacts_only",
            "live_supervisor_loads_candidate_hook": False,
            "live_timer_path_loaded": False,
            "live_timer_service_enabled_or_invoked": False,
            "ran_supervisor": False,
            "supervisor_invoked": False,
            "remote_sync_performed": False,
            "remote_execution_performed": False,
            "candidate_execution_performed": False,
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "target_plan_replaced": False,
            "executor_input_changed": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
            "owner_decision": {
                "decision": "approve_p9al_execute_default_off_observe_only_timer_path_dry_load_readback_only",
                "future_default_off_observe_only_readback_execution_gate_approved": True,
                "dry_load_readback_execution_approved": False,
                "timer_path_load_approved": False,
                "live_order_submission_approved": False,
            },
            "source_evidence": source_evidence,
            "output_files": {"readback_execution_gate": str(gate_path)},
            "gates": {
                "owner_decision_p9al_readback_gate_only": True,
                "project_stage_boundary_preserved": True,
                "p9ak_default_off_readback_proposal_ready": True,
                "p9ak_proposal_body_ready": True,
                "current_live_supervisor_not_loading_hook": True,
                "current_hook_hash_matches_p9ak_source": True,
                "current_supervisor_hash_matches_p9ak_source": True,
                "readback_execution_gate_output_under_proof_artifacts": True,
                "future_readback_must_be_default_off": True,
                "future_readback_must_be_observe_only": True,
                "future_readback_must_be_proof_artifacts_only": True,
                "future_readback_must_keep_order_authority_disabled": True,
                "future_readback_must_keep_executor_baseline_only": True,
                "future_readback_must_keep_candidate_shadow_only": True,
                "future_readback_must_not_replace_target_plan": True,
                "future_readback_must_not_mutate_executor_input": True,
                "future_readback_must_not_submit_orders": True,
                "no_readback_execution_in_p9al": True,
                "no_timer_hook_implementation_in_p9al": True,
                "no_hook_deployment_in_p9al": True,
                "no_timer_path_load_in_p9al": True,
                "no_supervisor_invocation_in_p9al": True,
                "no_remote_sync_in_p9al": True,
                "no_remote_execution_in_p9al": True,
                "no_candidate_execution_in_p9al": True,
                "no_executor_input_mutation_in_p9al": True,
                "no_target_plan_replacement_in_p9al": True,
                "no_live_mutation_in_p9al": True,
                "zero_orders_fills_in_p9al": True,
            },
        }
        p9al_gate = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9al_readback_execution_gate.v1",
            "run_id": "unit-p9al",
            "gate_scope": "owner_gated_default_off_observe_only_timer_path_dry_load_readback_execution_permission_only",
            "allowed_next_action": "execute_default_off_observe_only_timer_path_dry_load_readback",
            "allowed_next_gate": P9AM_GATE,
            "executed_in_p9al": False,
            "allowed_next_action_constraints": {
                "default_off_required": True,
                "observe_only_required": True,
                "proof_artifacts_only": True,
                "candidate_order_authority": "disabled",
                "candidate_live_order_submission_authorized": False,
                "candidate_execution_authorized": False,
                "executor_input_must_remain_baseline_only": True,
                "candidate_plan_must_not_be_referenced_by_executor": True,
                "candidate_artifacts_under_proof_artifacts_only": True,
                "target_plan_must_not_be_replaced": True,
                "executor_input_must_not_change": True,
                "must_not_modify_mainnet_live_supervisor": True,
                "must_not_modify_live_config": True,
                "must_not_modify_operator_state": True,
                "must_not_modify_timer_or_service_state": True,
                "must_not_enable_live_timer_service": True,
                "must_not_submit_orders": True,
                "orders_submitted_must_equal": 0,
                "fill_count_must_equal": 0,
                "fills_observed_must_equal": 0,
            },
            "owner_decision": {
                "decision": "approve_p9al_execute_default_off_observe_only_timer_path_dry_load_readback_only",
                "future_default_off_observe_only_readback_execution_gate_approved": True,
                "dry_load_readback_execution_approved": False,
                "timer_path_load_approved": False,
                "supervisor_invocation_approved": False,
                "remote_sync_approved": False,
                "candidate_execution_approved": False,
                "live_order_submission_approved": False,
                "target_plan_replacement_approved": False,
                "executor_input_mutation_approved": False,
                "live_config_mutation_approved": False,
                "operator_state_mutation_approved": False,
                "timer_or_service_mutation_approved": False,
                "production_timer_service_load_approved": False,
            },
        }
        self._deep_update(p9al_summary, p9al_summary_overrides or {})
        self._deep_update(p9al_gate, p9al_gate_overrides or {})
        self._write_json(phase9al, p9al_summary)
        self._write_json(gate_path, p9al_gate)
        return {
            "project_profile": project_profile,
            "phase9al": phase9al,
            "hook_module": hook_path,
            "supervisor": supervisor,
            "live_config_dir": live_config_dir,
        }

    def _deep_update(self, base: dict, override: dict) -> None:
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _load_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
