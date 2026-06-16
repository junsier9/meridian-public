from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime, timedelta
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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ai_default_off_shadow_review import (  # noqa: E402
    APPROVE_P9AI_DECISION,
    P9AJ_GATE,
    build_phase9ai,
    hook_summary_review,
    p9ah_ready_for_p9ai,
)


class Phase9AIDefaultOffShadowReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p9ai-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.project_profile = self.temp_dir / "project_profile.json"
        _write_json(self.project_profile, {"current_stage": "stage_1_research_readiness_only"})
        self.hook = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        self.hook.write_text("# hook\n", encoding="utf-8")
        self.supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        self.supervisor.write_text("def run():\n    return 'baseline supervisor'\n", encoding="utf-8")
        self.config_dir = self.temp_dir / "live_config"
        self.config_dir.mkdir()
        (self.config_dir / "config.yaml").write_text("trading_enabled: false\n", encoding="utf-8")

    def test_p9ai_reviews_retained_shadow_cycles_without_live_authority(self) -> None:
        p9ah = self._write_bundle()
        summary, exit_code = build_phase9ai(self._args(p9ah, self.temp_dir / "p9ai-ready"), now_fn=_time_at(0))

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9ai_default_off_observe_only_shadow_review_ready"])
        self.assertTrue(summary["default_off_observe_only_live_supervisor_shadow_review_completed"])
        self.assertTrue(summary["p9ai_shadow_review_authorized"])
        self.assertTrue(summary["p9ai_shadow_review_performed"])
        self.assertEqual(summary["allowed_next_gate"], P9AJ_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(summary["remote_sync_authorized"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["live_supervisor_hook_loaded"])
        self.assertFalse(summary["entered_timer_path"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertEqual(summary["reviewed_cycle_count"], 3)

    def test_p9ai_blocks_if_hook_stops_being_baseline_only(self) -> None:
        p9ah = self._write_bundle(cycle_hook_overrides={"executor_consumes_baseline_only": False})
        summary, exit_code = build_phase9ai(self._args(p9ah, self.temp_dir / "p9ai-block-baseline"), now_fn=_time_at(1))

        self.assertEqual(exit_code, 2)
        self.assertIn("all_cycle_reviews_ready", summary["blockers"])
        self.assertIn("all_executor_consumes_baseline_only", summary["blockers"])
        self.assertFalse(summary["p9ai_default_off_observe_only_shadow_review_ready"])
        self.assertFalse(summary["remote_execution_performed"])

    def test_p9ai_blocks_if_candidate_artifact_path_is_not_proof_artifacts(self) -> None:
        p9ah = self._write_bundle(cycle_hook_overrides={"candidate_artifact_paths": ["C:/tmp/candidate_shadow_plan.json"]})
        summary, exit_code = build_phase9ai(self._args(p9ah, self.temp_dir / "p9ai-block-path"), now_fn=_time_at(2))

        self.assertEqual(exit_code, 2)
        self.assertIn("all_cycle_reviews_ready", summary["blockers"])
        self.assertFalse(summary["remote_sync_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_p9ai_blocks_if_p9ah_did_not_open_p9ai(self) -> None:
        p9ah = self._write_bundle(p9ah_overrides={"allowed_next_gate": ""})
        p9ah_payload = _read_json(p9ah)
        self.assertFalse(p9ah_ready_for_p9ai(p9ah_payload))

        summary, exit_code = build_phase9ai(self._args(p9ah, self.temp_dir / "p9ai-block-p9ah"), now_fn=_time_at(3))
        self.assertEqual(exit_code, 2)
        self.assertIn("p9ah_owner_gate_ready", summary["blockers"])

    def test_hook_review_detects_candidate_executor_reference(self) -> None:
        row = _cycle_row(1, hook_overrides={"candidate_plan_referenced_by_executor": True})
        review = hook_summary_review(row)
        self.assertFalse(review["ready"])
        self.assertTrue(review["candidate_plan_referenced_by_executor"])

    def _args(self, p9ah: Path, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(self.project_profile),
            phase9ah_summary=str(p9ah),
            hook_module=str(self.hook),
            supervisor=str(self.supervisor),
            live_config_dir=str(self.config_dir),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9AI_DECISION,
            owner_decision_source="test",
        )

    def _write_bundle(
        self,
        *,
        cycle_hook_overrides: dict[str, object] | None = None,
        p9ah_overrides: dict[str, object] | None = None,
    ) -> Path:
        p9aa_path = self.temp_dir / "remote_p9aa_summary_inline.json"
        _write_json(p9aa_path, _p9aa_summary(cycle_hook_overrides=cycle_hook_overrides or {}))
        sync_path = self.temp_dir / "remote_sync_manifest.json"
        _write_json(sync_path, _remote_sync_manifest())
        p9ag_path = self.temp_dir / "p9ag_summary.json"
        _write_json(p9ag_path, _p9ag_summary(p9aa_path=p9aa_path, sync_path=sync_path))
        p9ah_path = self.temp_dir / "p9ah_summary.json"
        payload = _p9ah_summary(p9ag_path=p9ag_path, p9aa_path=p9aa_path, sync_path=sync_path)
        payload.update(p9ah_overrides or {})
        _write_json(p9ah_path, payload)
        return p9ah_path


def _p9ah_summary(*, p9ag_path: Path, p9aa_path: Path, sync_path: Path) -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ah_default_off_shadow_review_owner_gate.v1",
        "status": "ready",
        "blockers": [],
        "p9ah_default_off_shadow_review_owner_gate_ready": True,
        "eligible_for_future_default_off_observe_only_live_supervisor_shadow_review": True,
        "allowed_next_gate": "P9AI_default_off_observe_only_live_supervisor_shadow_review_only_if_separately_requested",
        "allowed_next_gate_must_be_separately_requested": True,
        "default_off_live_supervisor_shadow_review_authorized": False,
        "p9ai_shadow_review_execution_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "timer_path_load_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "source_evidence": {
            "phase9ag_summary": _evidence(p9ag_path),
            "phase9ag_remote_p9aa_summary": _evidence(p9aa_path),
            "phase9ag_remote_sync_manifest": _evidence(sync_path),
        },
        "gates": {
            "owner_decision_p9ah_review_only": True,
            "project_stage_boundary_preserved": True,
            "p9ag_summary_ready": True,
            "p9ag_position_reference_fixture_pit_safe": True,
            "p9ag_three_fresh_shadow_cycles": True,
            "p9ag_remote_sync_proof_harness_only": True,
            "current_live_supervisor_still_not_loading_hook": True,
            "p9ai_must_be_separately_requested": True,
            "p9ai_not_executed_in_p9ah": True,
            "remote_sync_not_authorized_in_p9ah": True,
            "remote_execution_not_authorized_in_p9ah": True,
            "timer_path_load_not_authorized_in_p9ah": True,
            "candidate_execution_forbidden": True,
            "live_order_submission_forbidden": True,
            "target_plan_replacement_forbidden": True,
            "executor_input_mutation_forbidden": True,
            "production_timer_service_load_forbidden": True,
            "zero_orders_fills_in_p9ah": True,
        },
    }


def _p9ag_summary(*, p9aa_path: Path, sync_path: Path) -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ag_nonflat_remote_readback.v1",
        "run_id": "20260607T031446Z",
        "status": "ready",
        "blockers": [],
        "p9ag_nonflat_remote_no_order_readback_ready": True,
        "fresh_remote_account_read_pre": _evidence("fresh_remote_account_read_pre.json"),
        "fresh_remote_account_read_post": _evidence("fresh_remote_account_read_post.json"),
        "position_fingerprint_pre": _evidence("position_fingerprint_pre.json"),
        "position_fingerprint_post": _evidence("position_fingerprint_post.json"),
        "pre_control_snapshot": _evidence("pre_control_snapshot.json"),
        "post_control_snapshot": _evidence("post_control_snapshot.json"),
        "remote_p9aa_summary": _evidence(p9aa_path),
        "remote_sync_manifest": _evidence(sync_path),
        "source_evidence": {
            "phase9af_summary": {"exists": True, "path": "p9af.json", "sha256": "a" * 64},
            "phase9z_summary": {"exists": True, "path": "p9z.json", "sha256": "b" * 64},
        },
        "position_fingerprint_stable": True,
        "order_cancel_fill_trade_delta_zero": True,
        "completed_shadow_cycles": 3,
        "fresh_proof_each_cycle": True,
        "same_risk_no_order_config_each_cycle": True,
        "baseline_only_executor_input": True,
        "candidate_shadow_only": True,
        "candidate_execution_authorized": False,
        "candidate_live_order_submission_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replaced": False,
        "executor_input_mutated": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "production_timer_service_loaded_or_modified": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "open_order_count_pre": 0,
        "open_order_count_post": 0,
        "open_position_count_pre": 11,
        "open_position_count_post": 11,
        "pit_safe_position_reference_fixture_ready": True,
        "position_reference_fixture": {
            "exists": True,
            "path": "/root/meridian_alpha_live_runner/proof_artifacts/p9ag/run/p9aa/proof_artifacts/position_reference/run_summary.json",
            "sha256": "c" * 64,
        },
        "remote_sync_files_copied": 1,
        "gates": {
            "owner_decision_p9ag_execute_only": True,
            "p9af_owner_gate_ready": True,
            "phase9z_summary_exists": True,
            "fresh_remote_account_read_pre_nonflat_ready": True,
            "position_fingerprint_pre_ready": True,
            "remote_sync_all_files_ready": True,
            "remote_py_compile_passed": True,
            "remote_p9aa_no_order_readback_ready": True,
            "pit_safe_position_reference_fixture_ready": True,
            "position_fingerprint_post_ready": True,
            "position_fingerprint_stable": True,
            "fresh_remote_account_read_post_nonflat_ready": True,
            "zero_order_cancel_fill_trade_delta": True,
            "remote_control_boundary_unchanged": True,
            "shadow_cycles_at_least_three": True,
            "fresh_proof_each_cycle": True,
            "same_risk_no_order_config_each_cycle": True,
            "baseline_only_executor_input": True,
            "candidate_shadow_only": True,
            "candidate_execution_forbidden": True,
            "live_order_submission_forbidden": True,
            "target_plan_replacement_forbidden": True,
            "executor_input_mutation_forbidden": True,
            "production_timer_service_not_loaded_or_modified": True,
        },
    }


def _p9aa_summary(*, cycle_hook_overrides: dict[str, object]) -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.v1",
        "run_id": "20260607T031501Z",
        "status": "ready",
        "blockers": [],
        "timer_path_shadow_cycles_ready": True,
        "completed_shadow_cycles": 3,
        "fresh_proof_each_cycle": True,
        "same_risk_no_order_config_each_cycle": True,
        "execution_target_source": "baseline_only",
        "candidate_order_authority": "disabled",
        "candidate_overlay_execution_path": "excluded",
        "timer_path_supervisor_entrypoint_invoked": True,
        "systemd_timer_service_invoked": False,
        "production_timer_service_loaded_or_modified": False,
        "candidate_execution_enabled": False,
        "candidate_live_order_submission_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replaced": False,
        "executor_input_mutated": False,
        "live_config_changed": False,
        "operator_state_changed_outside_generated_p9aa_state": False,
        "timer_state_changed": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "plan_artifact_missing_cycles": [],
        "supervisor_cycle_blockers": [],
        "position_reference_fixture_requested": True,
        "position_reference_fixture_ready": True,
        "position_reference_fixture": {
            "exists": True,
            "path": "/root/meridian_alpha_live_runner/proof_artifacts/p9ag/run/p9aa/proof_artifacts/position_reference/run_summary.json",
            "sha256": "c" * 64,
        },
        "position_reference_fixture_summary": {
            "source_created_before_p9aa": True,
            "read_only": True,
            "proof_artifacts_only": True,
            "orders_submitted": 0,
            "fill_count": 0,
            "source_open_order_count": 0,
            "source_open_position_count": 11,
        },
        "cycle_rows": [_cycle_row(index, hook_overrides=cycle_hook_overrides) for index in range(1, 4)],
        "gates": {
            "all_cycles_ready": True,
            "fresh_supervisor_run_each_cycle": True,
            "fresh_hook_proof_root_each_cycle": True,
            "all_executor_baseline_only": True,
            "all_candidate_artifacts_shadow_only": True,
            "all_candidate_plan_not_referenced_by_executor": True,
            "no_candidate_execution": True,
            "no_live_order_submission": True,
            "no_target_plan_replacement": True,
            "no_executor_input_mutation": True,
            "no_production_timer_service_mutation": True,
            "position_reference_fixture_ready": True,
        },
    }


def _cycle_row(index: int, *, hook_overrides: dict[str, object] | None = None) -> dict[str, object]:
    hook = {
        "contract_version": "hv_balanced_dth60_observe_only_shadow_hook.v1",
        "run_id": f"cycle-{index}",
        "status": "ready",
        "blockers": [],
        "hook_enabled": True,
        "mode": "observe_only",
        "artifact_sink": "proof_artifacts_only",
        "proof_root": f"/root/proof_artifacts/p9aa/cycle_{index:03d}/hook/shadow_hook",
        "applied_to_live": False,
        "deployed_hook": False,
        "wrote_hook_config": False,
        "ran_supervisor": False,
        "timer_path_invoked": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "candidate_overlay_execution_path": "excluded",
        "execution_target_source": "baseline_only",
        "exchange_order_submission": "disabled",
        "mainnet_order_submission_authorized": False,
        "baseline_target_plan": _evidence("/root/proof_artifacts/p9aa/baseline.json"),
        "executor_input_plan": _evidence("/root/proof_artifacts/p9aa/baseline.json"),
        "candidate_source_plan": _evidence(f"/root/proof_artifacts/p9aa/cycle_{index:03d}/candidate.json"),
        "baseline_target_plan_byte_for_byte_unchanged": True,
        "baseline_target_plan_sha256_before_hook": "a" * 64,
        "baseline_target_plan_sha256_after_hook": "a" * 64,
        "executor_input_plan_hash_equals_baseline": True,
        "executor_input_plan_hash_unchanged": True,
        "executor_consumes_baseline_only": True,
        "executor_input_plan_sha256_before_hook": "a" * 64,
        "executor_input_plan_sha256_after_hook": "a" * 64,
        "candidate_plan_referenced_by_executor": False,
        "candidate_shadow_plan_sha256": str(index) * 63 + "b",
        "candidate_artifacts_under_proof_artifacts_only": True,
        "candidate_artifacts_written_count": 4,
        "candidate_artifact_paths": [f"/root/proof_artifacts/p9aa/cycle_{index:03d}/hook/shadow_hook/candidate_shadow_plan.json"],
        "candidate_orders_submitted": 0,
        "candidate_fill_count": 0,
        "orders_submitted": 0,
        "fill_count": 0,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "gates": {
            "mode_observe_only": True,
            "artifact_sink_proof_artifacts_only": True,
            "candidate_order_authority_disabled": True,
            "candidate_live_order_submission_authorized_false": True,
            "candidate_overlay_execution_path_excluded": True,
            "execution_target_source_baseline_only": True,
            "baseline_target_plan_exists": True,
            "baseline_target_plan_byte_for_byte_unchanged": True,
            "executor_input_plan_exists": True,
            "executor_input_plan_hash_equals_baseline": True,
            "executor_input_plan_hash_unchanged": True,
            "executor_consumes_baseline_only": True,
            "candidate_shadow_plan_exists": True,
            "candidate_shadow_artifact_written": True,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "candidate_orders_submitted_zero": True,
            "candidate_fill_count_zero": True,
            "enabled_hook_output_root_under_proof_artifacts": True,
        },
    }
    hook.update(hook_overrides or {})
    return {"cycle_index": index, "cycle_ready": True, "supervisor_exit_code": 0, "hook_summary": hook}


def _remote_sync_manifest() -> dict[str, object]:
    return {
        "remote_root": "/root/meridian_alpha_live_runner/proof_artifacts/p9ag/20260607T031446Z",
        "files": [
            {
                "path": "scripts/live_trading/run_hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.py",
                "status": "synced",
                "copy_returncode": 0,
                "local_sha256": "d" * 64,
                "remote_sha256": "d" * 64,
            }
        ],
    }


def _evidence(path: str | Path) -> dict[str, object]:
    return {"exists": True, "path": str(path), "sha256": "f" * 64}


def _time_at(offset: int):
    base = datetime(2026, 6, 7, 3, 45, 0, tzinfo=UTC)
    return lambda: base + timedelta(seconds=offset)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
