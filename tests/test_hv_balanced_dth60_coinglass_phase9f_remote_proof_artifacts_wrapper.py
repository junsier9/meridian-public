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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9f_remote_proof_artifacts_wrapper import (  # noqa: E402
    APPROVE_P9F_DECISION,
    build_phase9f,
    file_sha256,
    resolve_path,
)


class HvBalancedDth60CoinglassPhase9fRemoteProofArtifactsWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="dth60-cg-phase9f-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_phase9f_ready_from_p9e_and_retained_p9b_remote_proof(self) -> None:
        paths = self._write_ready_inputs()
        output_root = self.temp_dir / "phase9f"

        summary, exit_code = build_phase9f(
            self._args(paths, output_root=output_root),
            now_fn=lambda: datetime(2026, 6, 7, 14, 0, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["wrapper_scope"], "owner_gated_remote_proof_artifacts_wrapper_only")
        self.assertEqual(summary["owner_decision"]["decision"], APPROVE_P9F_DECISION)
        self.assertTrue(summary["p9e_ready"])
        self.assertTrue(summary["p9b_remote_wrapper_ready"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertTrue(summary["remote_proof_artifacts_semantics"])
        self.assertTrue(summary["uses_retained_remote_supervisor_artifacts"])
        self.assertTrue(summary["wrapper_output_under_proof_artifacts"])
        self.assertTrue(summary["executor_consumes_baseline_only"])
        self.assertTrue(summary["executor_input_plan_hash_equals_baseline"])
        self.assertFalse(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["candidate_shadow_plan_generated"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertFalse(summary["timer_path_invoked"])
        self.assertFalse(summary["eligible_for_timer_path_load"])
        self.assertFalse(summary["eligible_for_live_order_submission"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertTrue((output_root / "owner_decision_record.json").exists())
        proof_root = output_root / "proof_artifacts" / "p9f" / "20260607T140000Z"
        self.assertTrue((proof_root / "remote_proof_readback_manifest.json").exists())
        self.assertTrue((proof_root / "executor_input_readback.json").exists())
        self.assertTrue((proof_root / "candidate_readonly_manifest.json").exists())

    def test_phase9f_blocks_when_owner_decision_is_not_p9f_wrapper_only(self) -> None:
        paths = self._write_ready_inputs()

        summary, exit_code = build_phase9f(
            self._args(paths, output_root=self.temp_dir / "wrong-owner", owner_decision="approve_timer_hook_review"),
            now_fn=lambda: datetime(2026, 6, 7, 14, 5, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("owner_decision_not_p9f_remote_proof_artifacts_wrapper_only", summary["blockers"])
        self.assertIn("owner_decision_p9f_wrapper_only", summary["blockers"])
        self.assertFalse(summary["eligible_for_timer_path_load"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def test_phase9f_blocks_when_retained_p9b_references_candidate_plan(self) -> None:
        paths = self._write_ready_inputs(
            p9b_overrides={
                "candidate_plan_referenced_by_executor": True,
                "gates": {"candidate_plan_not_referenced_by_executor": False},
            }
        )

        summary, exit_code = build_phase9f(
            self._args(paths, output_root=self.temp_dir / "candidate-referenced"),
            now_fn=lambda: datetime(2026, 6, 7, 14, 10, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("phase9b_not_ready_for_p9f", summary["blockers"])
        self.assertIn("phase9b_remote_wrapper_ready", summary["blockers"])
        self.assertIn("p9b_candidate_plan_not_referenced_by_executor", summary["blockers"])
        self.assertTrue(summary["candidate_plan_referenced_by_executor"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def test_phase9f_blocks_when_retained_p9b_invoked_timer_path(self) -> None:
        paths = self._write_ready_inputs(p9b_overrides={"timer_path_invoked": True})

        summary, exit_code = build_phase9f(
            self._args(paths, output_root=self.temp_dir / "timer-invoked"),
            now_fn=lambda: datetime(2026, 6, 7, 14, 15, tzinfo=UTC),
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(summary["status"], "blocked")
        self.assertIn("phase9b_not_ready_for_p9f", summary["blockers"])
        self.assertIn("phase9b_remote_wrapper_ready", summary["blockers"])
        self.assertIn("p9b_timer_path_not_invoked", summary["blockers"])
        self.assertFalse(summary["eligible_for_timer_path_load"])
        self.assertFalse(summary["eligible_for_live_order_submission"])

    def _args(
        self,
        paths: dict[str, Path],
        *,
        output_root: Path,
        owner_decision: str = APPROVE_P9F_DECISION,
    ) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            phase9e_summary=str(paths["phase9e"]),
            phase9b_summary=str(paths["phase9b"]),
            owner="rulebook_owner",
            owner_decision=owner_decision,
            owner_decision_source="unit_test",
        )

    def _write_ready_inputs(
        self,
        *,
        p9e_overrides: dict | None = None,
        p9b_overrides: dict | None = None,
    ) -> dict[str, Path]:
        hook_path = resolve_path("src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py")
        hook_sha = file_sha256(hook_path)
        p9e = {
            "status": "ready",
            "blockers": [],
            "run_id": "p9e",
            "fixture_scope": "owner_gated_timer_adjacent_local_fixture_only",
            "owner_decision": {
                "decision": "approve_p9e_timer_adjacent_local_fixture_only",
                "decision_effect": "authorize_p9e_timer_adjacent_local_fixture_only",
                "hook_deployment_approved": False,
                "timer_path_load_approved": False,
                "live_order_submission_approved": False,
                "target_plan_replacement_approved": False,
                "executor_input_mutation_approved": False,
                "live_config_mutation_approved": False,
                "operator_state_mutation_approved": False,
                "timer_or_service_mutation_approved": False,
                "repo_stage_change_approved": False,
            },
            "hook_enabled_inside_fixture": True,
            "default_live_hook_enabled": False,
            "hook_deployment_authorized": False,
            "timer_path_load_authorized": False,
            "live_order_submission_authorized": False,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifact_sink": "proof_artifacts_only",
            "baseline_target_plan_sha256": "baseline-hash",
            "executor_input_plan_sha256_after_hook": "baseline-hash",
            "candidate_shadow_plan_sha256": "candidate-hash",
            "executor_consumes_baseline_only": True,
            "candidate_plan_referenced_by_executor": False,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "live_supervisor_loads_candidate_hook": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "mainnet_order_submission_authorized": False,
            "exchange_order_submission": "disabled",
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "wrote_live_hook_config": False,
            "deployed_hook": False,
            "eligible_for_timer_path_load": False,
            "eligible_for_live_order_submission": False,
            "source_evidence": {
                "hook_module": {"path": str(hook_path), "exists": True, "sha256": hook_sha},
            },
        }
        p9e.update(p9e_overrides or {})
        p9b_gates = {
            "executor_input_plan_hash_equals_baseline": True,
            "candidate_plan_not_referenced_by_executor": True,
            "wrapper_output_under_proof_artifacts": True,
            "control_plane_unchanged": True,
        }
        p9b = {
            "status": "ready",
            "blockers": [],
            "run_id": "p9b",
            "output_root": "/root/meridian_alpha_live_runner/proof_artifacts/hv_balanced_dth60_p9b/run/verdict",
            "supervisor": {"run_id": "supervisor-run", "status": "mainnet_live_supervisor_completed"},
            "source_evidence": {"plan_artifact_root": "/root/meridian_alpha_live_runner/repo/artifacts/live/plan"},
            "executor_consumes_baseline_only": True,
            "executor_input_plan_hash_equals_baseline": True,
            "baseline_plan_hash": "remote-baseline-plan-hash",
            "executor_source_manifest_plan_hash": "",
            "executor_input_reference_kind": "core_loop_inline_strategy_plan",
            "executor_input_reference_plan_root": "/root/meridian_alpha_live_runner/repo/artifacts/live/plan",
            "candidate_plan_referenced_by_executor": False,
            "candidate_shadow_plan_generated": False,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "execution_target_source": "baseline_only",
            "candidate_artifact_sink": "proof_artifacts_only",
            "wrapper_output_under_proof_artifacts": True,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "read_only_supervisor_artifacts": True,
            "candidate_orders_submitted": 0,
            "candidate_fill_count": 0,
            "orders_submitted": 0,
            "fill_count": 0,
            "mainnet_order_submission_authorized": False,
            "applied_to_live": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "exchange_order_submission": "disabled",
            "eligible_for_live_order_submission": False,
            "control_plane": {"checked": True, "unchanged": True},
            "gates": p9b_gates,
        }
        if p9b_overrides:
            p9b.update(p9b_overrides)
            if "gates" in p9b_overrides:
                merged = dict(p9b_gates)
                merged.update(dict(p9b_overrides["gates"]))
                p9b["gates"] = merged
        p9e_path = self.temp_dir / "p9e_summary.json"
        p9b_path = self.temp_dir / "p9b_summary.json"
        self._write_json(p9e_path, p9e)
        self._write_json(p9b_path, p9b)
        return {"phase9e": p9e_path, "phase9b": p9b_path}

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
