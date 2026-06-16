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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9w_default_off_timer_path_dry_load_owner_gate import (  # noqa: E402
    APPROVE_P9W_DECISION,
    P9X_GATE,
    build_phase9w,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    file_sha256,
    resolve_path,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    P9W_GATE,
    tree_sha256,
)


class HvBalancedDth60CoinglassPhase9wDefaultOffTimerPathDryLoadOwnerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9w-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9w_ready_allows_only_future_execution_gate_discussion(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9w(
            self._args(paths, output_root=self.temp_dir / "p9w"),
            now_fn=lambda: datetime(2026, 6, 8, 4, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["owner_decision"]["decision"], APPROVE_P9W_DECISION)
        self.assertTrue(summary["p9w_owner_gate_ready"])
        self.assertTrue(summary["p9w_review_scope_only_discusses_execution"])
        self.assertTrue(summary["eligible_for_future_p9x_execution_gate"])
        self.assertEqual(summary["allowed_next_gate"], P9X_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(summary["default_off_timer_path_dry_load_execution_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["live_config_mutation_authorized"])
        self.assertFalse(summary["remote_sync_authorized"])
        self.assertFalse(summary["supervisor_run_authorized"])
        self.assertFalse(summary["entered_timer_path"])
        self.assertFalse(summary["dry_load_executed"])
        self.assertFalse(summary["candidate_execution_enabled"])
        self.assertFalse(summary["live_supervisor_loads_candidate_hook"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = self.temp_dir / "p9w" / "proof_artifacts" / "p9w" / "20260608T040000Z"
        self.assertTrue((self.temp_dir / "p9w" / "summary.json").exists())
        self.assertTrue((self.temp_dir / "p9w" / "owner_decision_record.json").exists())
        self.assertTrue((proof_root / "dry_load_execution_owner_gate.json").exists())
        self.assertTrue((proof_root / "discussion_decision_matrix.json").exists())
        self.assertTrue((proof_root / "non_authorization_matrix.json").exists())
        self.assertTrue((proof_root / "control_boundary_readback.json").exists())
        gate = self._load_json(proof_root / "dry_load_execution_owner_gate.json")
        self.assertEqual(gate["allowed_next_gate"], P9X_GATE)
        self.assertFalse(gate["default_off_timer_path_dry_load_execution_authorized_in_p9w"])
        self.assertFalse(gate["candidate_execution_authorized_in_p9w"])
        matrix = self._load_json(proof_root / "non_authorization_matrix.json")
        self.assertTrue(matrix["authorizations"]["future_p9x_execution_gate_request"])
        self.assertFalse(matrix["authorizations"]["execute_default_off_timer_path_dry_load_in_p9w"])
        self.assertFalse(matrix["authorizations"]["candidate_execution"])
        self.assertFalse(matrix["authorizations"]["live_order_submission"])

    def test_phase9w_blocks_when_p9v_entered_timer_path(self) -> None:
        paths = self._write_ready_inputs(
            p9v_overrides={
                "entered_timer_path": True,
                "dry_load_executed": True,
                "gates": {
                    "timer_path_not_entered": False,
                },
            },
            readiness_overrides={
                "entered_timer_path": True,
                "dry_load_executed": True,
            },
            control_overrides={
                "entered_timer_path": True,
            },
        )

        summary, exit_code = build_phase9w(
            self._args(paths, output_root=self.temp_dir / "p9w-bad-p9v"),
            now_fn=lambda: datetime(2026, 6, 8, 4, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9v_readiness_review_ready", summary["blockers"])
        self.assertFalse(summary["eligible_for_future_p9x_execution_gate"])
        self.assertFalse(summary["default_off_timer_path_dry_load_execution_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9w_blocks_when_p9tuv_authorizes_timer_or_orders(self) -> None:
        paths = self._write_ready_inputs(
            p9tuv_overrides={
                "timer_path_load_authorized": True,
                "live_order_submission_authorized": True,
            }
        )

        summary, exit_code = build_phase9w(
            self._args(paths, output_root=self.temp_dir / "p9w-bad-corridor"),
            now_fn=lambda: datetime(2026, 6, 8, 4, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9tuv_corridor_ready", summary["blockers"])
        self.assertFalse(summary["eligible_for_future_p9x_execution_gate"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_phase9w_blocks_when_current_supervisor_loads_hook(self) -> None:
        paths = self._write_ready_inputs(supervisor_text="from dth60_observe_only_shadow_hook import run\n")

        summary, exit_code = build_phase9w(
            self._args(paths, output_root=self.temp_dir / "p9w-supervisor-hook"),
            now_fn=lambda: datetime(2026, 6, 8, 4, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("p9v_readiness_review_ready", summary["blockers"])
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["default_off_timer_path_dry_load_execution_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def _args(self, paths: dict[str, Path], *, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(paths["project_profile"]),
            phase9tuv_summary=str(paths["phase9tuv"]),
            phase9v_summary=str(paths["phase9v"]),
            hook_module=str(paths["hook_module"]),
            supervisor=str(paths["supervisor"]),
            live_config_dir=str(paths["live_config_dir"]),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9W_DECISION,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9tuv_overrides: dict | None = None,
        p9v_overrides: dict | None = None,
        readiness_overrides: dict | None = None,
        control_overrides: dict | None = None,
        supervisor_text: str = "# baseline supervisor\n",
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        project_profile = self.temp_dir / "project_profile.json"
        phase9tuv = self.temp_dir / "phase9tuv" / "summary.json"
        phase9v = self.temp_dir / "phase9v" / "summary.json"
        proof_root = self.temp_dir / "phase9v" / "proof_artifacts" / "p9v" / "run"
        readiness_path = proof_root / "dry_load_readiness_review.json"
        control_path = proof_root / "control_boundary_readback.json"
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
        p9tuv = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor.v1",
            "status": "ready",
            "blockers": [],
            "p9t_status": "ready",
            "p9u_status": "ready",
            "p9v_status": "ready",
            "hard_stop_before": [
                "remote_sync",
                "live_timer_path_load",
                "supervisor_run",
                "executor_input_mutation",
                "target_plan_replacement",
                "operator_state_mutation",
                "stage_governance_change",
                "live_order_submission",
            ],
            "remote_sync_authorized": False,
            "timer_path_load_authorized": False,
            "supervisor_run_authorized": False,
            "executor_input_mutation_authorized": False,
            "target_plan_replacement_authorized": False,
            "live_config_mutation_authorized": False,
            "live_order_submission_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "outputs": {
                "p9v_summary": str(phase9v),
            },
        }
        gates = {
            "project_stage_boundary_preserved": True,
            "p9u_proposal_package_ready": True,
            "proposal_package_under_proof_artifacts": True,
            "readiness_review_output_under_proof_artifacts": True,
            "timer_path_not_entered": True,
            "executor_input_not_mutated": True,
            "live_config_not_mutated": True,
            "live_config_digest_unchanged": True,
            "live_supervisor_source_unchanged": True,
            "current_live_supervisor_not_loading_hook": True,
            "supervisor_not_run": True,
            "no_remote_execution_in_p9v": True,
            "no_target_plan_replacement_in_p9v": True,
            "no_live_mutation_in_p9v": True,
            "zero_orders_fills_in_p9v": True,
        }
        p9v = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9v_dry_load_readiness_review.v1",
            "status": "ready",
            "blockers": [],
            "gate_scope": "p9v_local_retained_evidence_dry_load_readiness_review_only",
            "p9v_dry_load_readiness_review_ready": True,
            "reviewed_only_retained_evidence": True,
            "allowed_next_gate": P9W_GATE,
            "recommended_next_gate": P9W_GATE,
            "gates": gates,
            "entered_timer_path": False,
            "dry_load_executed": False,
            "executor_input_mutated": False,
            "executor_input_changed": False,
            "live_config_mutated": False,
            "live_config_changed": False,
            "live_config_dir_unchanged": True,
            "target_plan_replaced": False,
            "live_supervisor_loads_candidate_hook": False,
            "live_supervisor_source_unchanged": True,
            "live_timer_path_loaded": False,
            "live_timer_service_enabled_or_invoked": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "remote_execution_performed": False,
            "remote_control_plane_touched": False,
            "implemented_hook": False,
            "deployed_hook": False,
            "loaded_hook": False,
            "wrote_live_hook_config": False,
            "timer_path_load_authorized": False,
            "live_order_submission_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "remote_sync_authorized": False,
            "supervisor_run_authorized": False,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifact_sink": "proof_artifacts_only",
            "orders_submitted": 0,
            "fill_count": 0,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "source_evidence": {
                "hook_module": {"exists": True, "path": str(hook_path), "sha256": hook_sha},
                "live_supervisor": {"exists": True, "path": str(supervisor), "sha256": supervisor_sha},
                "live_config_dir": {"exists": True, "path": str(live_config_dir), "sha256": live_config_sha},
            },
            "output_files": {
                "dry_load_readiness_review": str(readiness_path),
                "control_boundary_readback": str(control_path),
            },
        }
        readiness = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9v_dry_load_readiness_review.v1",
            "review_mode": "local_retained_evidence_readiness_review_not_timer_path",
            "reviewed_only_retained_evidence": True,
            "entered_timer_path": False,
            "dry_load_executed": False,
            "executor_input_mutated": False,
            "live_config_mutated": False,
            "target_plan_replaced": False,
            "remote_sync_performed": False,
            "supervisor_run": False,
            "orders_submitted": 0,
            "fill_count": 0,
        }
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9v_control_boundary_readback.v1",
            "entered_timer_path": False,
            "executor_input_mutated": False,
            "live_config_changed": False,
            "live_config_dir_unchanged": True,
            "live_config_dir_sha256_before": live_config_sha,
            "live_config_dir_sha256_after": live_config_sha,
            "live_supervisor_loads_candidate_hook": False,
            "live_supervisor_source_unchanged": True,
            "live_supervisor_sha256_before": supervisor_sha,
            "live_supervisor_sha256_after": supervisor_sha,
            "target_plan_replaced": False,
            "remote_control_plane_touched": False,
            "orders_submitted": 0,
            "fill_count": 0,
        }
        self._deep_update(p9tuv, p9tuv_overrides or {})
        self._deep_update(p9v, p9v_overrides or {})
        self._deep_update(readiness, readiness_overrides or {})
        self._deep_update(control, control_overrides or {})
        self._write_json(phase9tuv, p9tuv)
        self._write_json(phase9v, p9v)
        self._write_json(readiness_path, readiness)
        self._write_json(control_path, control)
        return {
            "project_profile": project_profile,
            "phase9tuv": phase9tuv,
            "phase9v": phase9v,
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
