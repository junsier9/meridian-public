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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9aj_define_next_gate_after_shadow_review import (  # noqa: E402
    APPROVE_P9AJ_DECISION,
    P9AK_GATE,
    build_phase9aj,
    p9ai_ready_for_p9aj,
    packet_ready_for_p9aj,
)


class Phase9AJDefineNextGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p9aj-"))
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

    def test_p9aj_defines_p9ak_scope_without_preparing_proposal(self) -> None:
        p9ai = self._write_p9ai_bundle()
        summary, exit_code = build_phase9aj(self._args(p9ai, self.temp_dir / "p9aj-ready"), now_fn=_time_at(0))

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9aj_define_next_gate_after_shadow_review_ready"])
        self.assertTrue(summary["p9ai_sufficient_for_future_p9ak_proposal_preparation"])
        self.assertEqual(summary["allowed_next_gate"], P9AK_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertFalse(summary["p9ak_proposal_preparation_authorized"])
        self.assertFalse(summary["prepared_p9ak_proposal"])
        self.assertFalse(summary["wrote_p9ak_proposal_body"])
        self.assertFalse(summary["dry_load_readback_execution_authorized"])
        self.assertFalse(summary["remote_sync_authorized"])
        self.assertFalse(summary["remote_execution_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["entered_timer_path"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        self.assertTrue(summary["next_gate_scope"]["p9ak_may_prepare_proposal_body"])
        self.assertFalse(summary["next_gate_scope"]["p9ak_may_execute_proposal"])
        self.assertTrue(summary["next_gate_scope"]["future_dry_load_readback_execution_gate_required"])

    def test_p9aj_blocks_if_p9ai_authorized_timer_path_load(self) -> None:
        p9ai = self._write_p9ai_bundle(p9ai_overrides={"timer_path_load_authorized": True})
        packet = _read_json(Path(_read_json(p9ai)["output_files"]["shadow_review_packet"]))
        self.assertFalse(p9ai_ready_for_p9aj(_read_json(p9ai), packet))

        summary, exit_code = build_phase9aj(self._args(p9ai, self.temp_dir / "p9aj-block-timer"), now_fn=_time_at(1))
        self.assertEqual(exit_code, 2)
        self.assertIn("p9ai_summary_ready", summary["blockers"])
        self.assertFalse(summary["p9ak_proposal_preparation_authorized"])

    def test_p9aj_blocks_if_shadow_packet_cycle_not_ready(self) -> None:
        packet_overrides = {"all_cycle_reviews_ready": False}
        p9ai = self._write_p9ai_bundle(packet_overrides=packet_overrides)
        packet = _read_json(Path(_read_json(p9ai)["output_files"]["shadow_review_packet"]))
        self.assertFalse(packet_ready_for_p9aj(packet))

        summary, exit_code = build_phase9aj(self._args(p9ai, self.temp_dir / "p9aj-block-packet"), now_fn=_time_at(2))
        self.assertEqual(exit_code, 2)
        self.assertIn("p9ai_shadow_review_packet_ready", summary["blockers"])

    def test_p9aj_blocks_if_supervisor_now_loads_hook(self) -> None:
        p9ai = self._write_p9ai_bundle()
        self.supervisor.write_text(
            "from enhengclaw.live_trading.dth60_observe_only_shadow_hook import run_observe_only_shadow_hook\n",
            encoding="utf-8",
        )
        summary, exit_code = build_phase9aj(self._args(p9ai, self.temp_dir / "p9aj-block-supervisor"), now_fn=_time_at(3))

        self.assertEqual(exit_code, 2)
        self.assertIn("current_live_supervisor_still_not_loading_hook", summary["blockers"])
        self.assertFalse(summary["remote_sync_authorized"])

    def _args(self, p9ai: Path, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(self.project_profile),
            phase9ai_summary=str(p9ai),
            hook_module=str(self.hook),
            supervisor=str(self.supervisor),
            live_config_dir=str(self.config_dir),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9AJ_DECISION,
            owner_decision_source="test",
        )

    def _write_p9ai_bundle(
        self,
        *,
        p9ai_overrides: dict[str, object] | None = None,
        packet_overrides: dict[str, object] | None = None,
    ) -> Path:
        packet_path = self.temp_dir / "shadow_review_packet.json"
        packet = _packet()
        packet.update(packet_overrides or {})
        _write_json(packet_path, packet)
        summary_path = self.temp_dir / "p9ai_summary.json"
        p9ai = _p9ai_summary(packet_path=packet_path, hook_path=self.hook, supervisor_path=self.supervisor)
        p9ai.update(p9ai_overrides or {})
        _write_json(summary_path, p9ai)
        return summary_path


def _p9ai_summary(*, packet_path: Path, hook_path: Path, supervisor_path: Path) -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ai_default_off_observe_only_shadow_review.v1",
        "run_id": "20260607T034228Z",
        "status": "ready",
        "blockers": [],
        "p9ai_default_off_observe_only_shadow_review_ready": True,
        "default_off_observe_only_live_supervisor_shadow_review_completed": True,
        "eligible_for_future_owner_gate_discussion": True,
        "allowed_next_gate": "P9AJ_define_next_gate_after_default_off_shadow_review_only_if_separately_requested",
        "allowed_next_gate_must_be_separately_requested": True,
        "p9ai_shadow_review_authorized": True,
        "p9ai_shadow_review_performed": True,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "production_timer_service_load_authorized": False,
        "repo_stage_change_authorized": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "live_supervisor_hook_loaded": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "reviewed_cycle_count": 3,
        "source_evidence": {
            "hook_module": _evidence(hook_path),
            "live_supervisor": _evidence(supervisor_path),
        },
        "output_files": {"shadow_review_packet": str(packet_path)},
        "gates": {
            "owner_decision_p9ai_shadow_review_only": True,
            "project_stage_boundary_preserved": True,
            "p9ah_owner_gate_ready": True,
            "p9ag_summary_revalidated": True,
            "p9aa_shadow_cycles_ready": True,
            "shadow_review_packet_under_proof_artifacts": True,
            "reviewed_at_least_three_cycles": True,
            "all_cycle_reviews_ready": True,
            "executor_hashes_distinct_from_candidate_hashes": True,
            "all_hook_status_ready": True,
            "all_hook_enabled_observe_only": True,
            "all_baseline_target_plan_byte_for_byte_unchanged": True,
            "all_executor_consumes_baseline_only": True,
            "all_executor_input_plan_hash_equals_baseline": True,
            "all_candidate_plan_not_referenced_by_executor": True,
            "all_candidate_artifacts_under_proof_artifacts_only": True,
            "all_candidate_artifacts_written": True,
            "all_candidate_order_authority_disabled": True,
            "all_candidate_overlay_execution_path_excluded": True,
            "all_candidate_orders_fills_zero": True,
            "all_hook_orders_fills_zero": True,
            "all_no_live_mutation": True,
            "current_live_supervisor_still_not_loading_hook": True,
            "no_remote_sync_in_p9ai": True,
            "no_remote_execution_in_p9ai": True,
            "no_timer_path_load_in_p9ai": True,
            "no_supervisor_invocation_in_p9ai": True,
            "no_live_config_operator_timer_mutation_in_p9ai": True,
            "zero_orders_fills_in_p9ai": True,
        },
    }


def _packet() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ai_shadow_review_packet.v1",
        "review_mode": "retained_p9aa_cycle_hook_summary_review_only",
        "all_cycle_reviews_ready": True,
        "reviewed_cycle_count": 3,
        "executor_hashes_distinct_from_candidate_hashes": True,
        "authorizations": {
            "remote_sync": False,
            "remote_execution": False,
            "timer_path_load": False,
            "supervisor_invocation": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "production_timer_service_load": False,
        },
        "reviewed_cycles": [_packet_row(index) for index in range(1, 4)],
    }


def _packet_row(index: int) -> dict[str, object]:
    return {
        "ready": True,
        "cycle_ready": True,
        "supervisor_exit_code": 0,
        "hook_status": "ready",
        "hook_enabled": True,
        "mode": "observe_only",
        "artifact_sink": "proof_artifacts_only",
        "proof_root": f"/root/proof_artifacts/p9ai/cycle_{index:03d}/hook",
        "proof_root_under_proof_artifacts": True,
        "baseline_target_plan_byte_for_byte_unchanged": True,
        "executor_consumes_baseline_only": True,
        "executor_input_plan_hash_equals_baseline": True,
        "executor_input_plan_sha256_after_hook": "a" * 64,
        "candidate_shadow_plan_sha256": str(index) * 63 + "b",
        "candidate_plan_referenced_by_executor": False,
        "candidate_artifacts_under_proof_artifacts_only": True,
        "candidate_artifacts_written_count": 4,
        "candidate_order_authority": "disabled",
        "candidate_overlay_execution_path": "excluded",
        "candidate_live_order_submission_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "candidate_orders_submitted": 0,
        "candidate_fill_count": 0,
        "applied_to_live": False,
        "deployed_hook": False,
        "wrote_hook_config": False,
        "ran_supervisor": False,
        "timer_path_invoked": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
    }


def _evidence(path: str | Path) -> dict[str, object]:
    return {"exists": True, "path": str(path), "sha256": _sha(path)}


def _sha(path: str | Path) -> str:
    path = Path(path)
    if path.exists() and path.is_file():
        import hashlib

        return hashlib.sha256(path.read_bytes()).hexdigest()
    return "f" * 64


def _time_at(offset: int):
    base = datetime(2026, 6, 7, 3, 55, 0, tzinfo=UTC)
    return lambda: base + timedelta(seconds=offset)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
