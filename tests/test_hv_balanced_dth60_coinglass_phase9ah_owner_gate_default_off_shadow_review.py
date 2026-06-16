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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ah_owner_gate_default_off_shadow_review import (  # noqa: E402
    APPROVE_P9AH_DECISION,
    P9AI_GATE,
    build_phase9ah,
    p9ag_ready_for_p9ah,
    remote_sync_manifest_proof_harness_only,
)


class Phase9AHDefaultOffShadowReviewOwnerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p9ah-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)
        self.project_profile = self.temp_dir / "project_profile.json"
        _write_json(self.project_profile, {"current_stage": "stage_1_research_readiness_only"})
        self.hook = self.temp_dir / "dth60_observe_only_shadow_hook.py"
        self.hook.write_text("# observe only hook\n", encoding="utf-8")
        self.supervisor = self.temp_dir / "mainnet_live_supervisor.py"
        self.supervisor.write_text("def run():\n    return 'baseline supervisor'\n", encoding="utf-8")
        self.config_dir = self.temp_dir / "live_config"
        self.config_dir.mkdir()
        (self.config_dir / "config.yaml").write_text("trading_enabled: false\n", encoding="utf-8")

    def test_p9ah_allows_future_p9ai_review_without_authorizing_execution(self) -> None:
        p9ag = self._write_p9ag_bundle()
        summary, exit_code = build_phase9ah(
            self._args(p9ag, self.temp_dir / "p9ah-ready"),
            now_fn=_time_at(0),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9ah_default_off_shadow_review_owner_gate_ready"])
        self.assertTrue(summary["eligible_for_future_default_off_observe_only_live_supervisor_shadow_review"])
        self.assertEqual(summary["allowed_next_gate"], P9AI_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(summary["default_off_live_supervisor_shadow_review_authorized"])
        self.assertFalse(summary["p9ai_shadow_review_execution_authorized"])
        self.assertFalse(summary["remote_sync_authorized"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["production_timer_service_load_authorized"])
        self.assertFalse(summary["remote_sync_performed"])
        self.assertFalse(summary["remote_execution_performed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

    def test_p9ah_blocks_if_p9aa_no_longer_baseline_only(self) -> None:
        p9ag = self._write_p9ag_bundle(p9aa_overrides={"execution_target_source": "candidate"})
        summary, exit_code = build_phase9ah(
            self._args(p9ag, self.temp_dir / "p9ah-block-baseline"),
            now_fn=_time_at(1),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("p9ag_summary_ready", summary["blockers"])
        self.assertIn("p9ag_three_fresh_shadow_cycles", summary["blockers"])
        self.assertFalse(summary["p9ah_default_off_shadow_review_owner_gate_ready"])
        self.assertFalse(summary["remote_execution_performed"])

    def test_p9ah_blocks_if_remote_sync_touches_live_config(self) -> None:
        p9ag = self._write_p9ag_bundle(sync_manifest=_remote_sync_manifest(disallowed_live_config=True))
        payload = _read_json(p9ag)
        p9aa = _read_json(Path(payload["remote_p9aa_summary"]["path"]))
        sync = _read_json(Path(payload["remote_sync_manifest"]["path"]))

        self.assertFalse(remote_sync_manifest_proof_harness_only(sync))
        self.assertFalse(p9ag_ready_for_p9ah(payload, p9aa_summary=p9aa, sync_manifest=sync))

        summary, exit_code = build_phase9ah(
            self._args(p9ag, self.temp_dir / "p9ah-block-sync"),
            now_fn=_time_at(2),
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("p9ag_remote_sync_proof_harness_only", summary["blockers"])
        self.assertFalse(summary["remote_sync_authorized"])

    def test_p9ah_blocks_if_current_supervisor_loads_hook(self) -> None:
        p9ag = self._write_p9ag_bundle()
        self.supervisor.write_text(
            "from enhengclaw.live_trading.dth60_observe_only_shadow_hook import run_observe_only_shadow_hook\n",
            encoding="utf-8",
        )

        summary, exit_code = build_phase9ah(
            self._args(p9ag, self.temp_dir / "p9ah-block-supervisor"),
            now_fn=_time_at(3),
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("current_live_supervisor_still_not_loading_hook", summary["blockers"])
        self.assertFalse(summary["p9ai_shadow_review_execution_authorized"])

    def _args(self, p9ag: Path, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(self.project_profile),
            phase9ag_summary=str(p9ag),
            hook_module=str(self.hook),
            supervisor=str(self.supervisor),
            live_config_dir=str(self.config_dir),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9AH_DECISION,
            owner_decision_source="test",
        )

    def _write_p9ag_bundle(
        self,
        *,
        p9aa_overrides: dict[str, object] | None = None,
        sync_manifest: dict[str, object] | None = None,
    ) -> Path:
        p9aa_path = self.temp_dir / "remote_p9aa_summary_inline.json"
        p9aa = _p9aa_summary()
        p9aa.update(p9aa_overrides or {})
        _write_json(p9aa_path, p9aa)

        sync_path = self.temp_dir / "remote_sync_manifest.json"
        _write_json(sync_path, sync_manifest or _remote_sync_manifest())

        p9ag_path = self.temp_dir / "p9ag_summary.json"
        _write_json(p9ag_path, _p9ag_summary(p9aa_path=p9aa_path, sync_path=sync_path))
        return p9ag_path


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


def _p9aa_summary() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.v1",
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


def _remote_sync_manifest(*, disallowed_live_config: bool = False) -> dict[str, object]:
    path = (
        "config/live_trading/hv_balanced_live.yaml"
        if disallowed_live_config
        else "scripts/live_trading/run_hv_balanced_dth60_coinglass_phase9aa_timer_path_shadow_cycles.py"
    )
    return {
        "remote_root": "/root/meridian_alpha_live_runner/proof_artifacts/p9ag/20260607T031446Z",
        "files": [
            {
                "path": path,
                "status": "synced",
                "copy_returncode": 0,
                "local_sha256": "d" * 64,
                "remote_sha256": "d" * 64,
            },
            {
                "path": "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py",
                "status": "already_matching",
                "copy_returncode": None,
                "local_sha256": "e" * 64,
                "remote_sha256": "e" * 64,
            },
        ],
    }


def _evidence(path: str | Path) -> dict[str, object]:
    return {"exists": True, "path": str(path), "sha256": "f" * 64}


def _time_at(offset: int):
    base = datetime(2026, 6, 7, 3, 30, 0, tzinfo=UTC)
    return lambda: base + timedelta(seconds=offset)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
