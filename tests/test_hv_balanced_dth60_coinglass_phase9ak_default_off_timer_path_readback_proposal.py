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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ak_default_off_timer_path_readback_proposal import (  # noqa: E402
    APPROVE_P9AK_DECISION,
    P9AL_GATE,
    build_phase9ak,
    p9aj_ready_for_p9ak,
)


class Phase9AKDefaultOffReadbackProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p9ak-"))
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

    def test_p9ak_prepares_only_proof_artifacts_proposal(self) -> None:
        p9aj = self._write_p9aj_bundle()
        summary, exit_code = build_phase9ak(self._args(p9aj, self.temp_dir / "p9ak-ready"), now_fn=_time_at(0))

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9ak_default_off_observe_only_timer_path_readback_proposal_ready"])
        self.assertTrue(summary["prepared_p9ak_proposal"])
        self.assertTrue(summary["wrote_p9ak_proposal_body"])
        self.assertEqual(summary["proposal_body_sink"], "proof_artifacts_only")
        self.assertEqual(summary["proposed_future_gate"], P9AL_GATE)
        self.assertTrue(summary["future_readback_execution_gate_required"])
        self.assertFalse(summary["p9ak_authorizes_dry_load_readback_execution"])
        self.assertFalse(summary["dry_load_readback_execution_authorized"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["supervisor_invocation_authorized"])
        self.assertFalse(summary["remote_sync_authorized"])
        self.assertFalse(summary["candidate_execution_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])
        self.assertFalse(summary["target_plan_replacement_authorized"])
        self.assertFalse(summary["executor_input_mutation_authorized"])
        self.assertFalse(summary["entered_timer_path"])
        self.assertFalse(summary["ran_supervisor"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)
        proposal_path = Path(summary["output_files"]["default_off_observe_only_timer_path_readback_proposal"])
        self.assertTrue(proposal_path.exists())
        self.assertIn("proof_artifacts", {part.lower() for part in proposal_path.parts})
        proposal = _read_json(proposal_path)
        self.assertFalse(proposal["p9ak_authorizes_dry_load_readback_execution"])
        self.assertTrue(proposal["proposed_future_readback_contract"]["default_off_required"])
        self.assertEqual(proposal["proposed_future_readback_contract"]["execution_target_source"], "baseline_only")
        self.assertEqual(proposal["proposed_future_readback_contract"]["candidate_order_authority"], "disabled")

    def test_p9ak_blocks_if_p9aj_not_ready_for_scope(self) -> None:
        p9aj = self._write_p9aj_bundle(p9aj_overrides={"dry_load_readback_execution_authorized": True})
        self.assertFalse(
            p9aj_ready_for_p9ak(
                _read_json(p9aj),
                current_hook_sha256=_sha256(self.hook),
                current_supervisor_sha256=_sha256(self.supervisor),
            )
        )

        summary, exit_code = build_phase9ak(self._args(p9aj, self.temp_dir / "p9ak-block-p9aj"), now_fn=_time_at(1))
        self.assertEqual(exit_code, 2)
        self.assertIn("p9aj_scope_gate_ready", summary["blockers"])
        self.assertFalse(summary["prepared_p9ak_proposal"])
        self.assertNotIn("default_off_observe_only_timer_path_readback_proposal", summary["output_files"])

    def test_p9ak_blocks_if_supervisor_now_loads_hook(self) -> None:
        p9aj = self._write_p9aj_bundle()
        self.supervisor.write_text(
            "from enhengclaw.live_trading.dth60_observe_only_shadow_hook import run_observe_only_shadow_hook\n",
            encoding="utf-8",
        )
        summary, exit_code = build_phase9ak(
            self._args(p9aj, self.temp_dir / "p9ak-block-supervisor"),
            now_fn=_time_at(2),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertFalse(summary["timer_path_load_authorized"])

    def test_p9ak_blocks_if_owner_decision_not_exact(self) -> None:
        p9aj = self._write_p9aj_bundle()
        args = self._args(p9aj, self.temp_dir / "p9ak-block-owner")
        args.owner_decision = "approve_live_orders"
        summary, exit_code = build_phase9ak(args, now_fn=_time_at(3))

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p9ak_proposal_only", summary["blockers"])
        self.assertFalse(summary["owner_decision"]["p9ak_proposal_preparation_approved"])
        self.assertFalse(summary["prepared_p9ak_proposal"])

    def _args(self, p9aj: Path, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(self.project_profile),
            phase9aj_summary=str(p9aj),
            hook_module=str(self.hook),
            supervisor=str(self.supervisor),
            live_config_dir=str(self.config_dir),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9AK_DECISION,
            owner_decision_source="test",
        )

    def _write_p9aj_bundle(self, *, p9aj_overrides: dict[str, object] | None = None) -> Path:
        p9aj_path = self.temp_dir / "p9aj_summary.json"
        p9aj = _p9aj_summary(hook_path=self.hook, supervisor_path=self.supervisor)
        p9aj.update(p9aj_overrides or {})
        _write_json(p9aj_path, p9aj)
        return p9aj_path


def _p9aj_summary(*, hook_path: Path, supervisor_path: Path) -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aj_define_next_gate_after_shadow_review.v1",
        "run_id": "20260607T041527Z",
        "status": "ready",
        "blockers": [],
        "p9aj_define_next_gate_after_shadow_review_ready": True,
        "p9ai_sufficient_for_future_p9ak_proposal_preparation": True,
        "allowed_next_gate": (
            "P9AK_prepare_default_off_observe_only_hook_live_supervisor_timer_path_"
            "dry_load_readback_proposal_only_if_separately_requested"
        ),
        "allowed_next_gate_must_be_separately_requested": True,
        "p9ak_proposal_preparation_authorized": False,
        "prepared_p9ak_proposal": False,
        "wrote_p9ak_proposal_body": False,
        "dry_load_readback_execution_authorized": False,
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
        "entered_timer_path": False,
        "ran_supervisor": False,
        "live_supervisor_hook_loaded": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "source_evidence": {
            "hook_module": _evidence(hook_path),
            "live_supervisor": _evidence(supervisor_path),
        },
        "owner_decision": {
            "decision": "approve_p9aj_define_next_gate_after_default_off_shadow_review_scope_only",
            "p9aj_define_scope_approved": True,
            "p9ak_may_be_separately_requested": True,
            "p9ak_proposal_preparation_approved": False,
        },
        "next_gate_scope": {
            "allowed_next_gate": (
                "P9AK_prepare_default_off_observe_only_hook_live_supervisor_timer_path_"
                "dry_load_readback_proposal_only_if_separately_requested"
            ),
            "p9ak_may_prepare_proposal_body": True,
            "p9ak_may_execute_proposal": False,
            "future_dry_load_readback_execution_gate_required": True,
            "future_timer_path_load_gate_required": True,
            "p9ak_required_boundaries": {
                "proposal_only": True,
                "proof_artifacts_only": True,
                "default_off": True,
                "observe_only": True,
                "order_submission_disabled": True,
                "candidate_execution_disabled": True,
                "executor_consumes_baseline_only": True,
                "candidate_shadow_artifact_only": True,
            },
            "current_gate_authorizations": {
                "p9ak_proposal_preparation": False,
                "proposal_body_write": False,
                "dry_load_readback_execution": False,
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
                "stage_governance_change": False,
            },
        },
        "gates": {
            "owner_decision_p9aj_define_scope_only": True,
            "project_stage_boundary_preserved": True,
            "p9ai_summary_ready": True,
            "p9ai_shadow_review_packet_ready": True,
            "next_gate_scope_definition_under_proof_artifacts": True,
            "p9aj_defines_scope_only": True,
            "p9aj_does_not_prepare_p9ak_proposal": True,
            "p9aj_does_not_write_proposal_body": True,
            "p9ak_must_be_separately_requested": True,
            "p9ak_must_remain_proposal_only": True,
            "p9ak_must_keep_default_off": True,
            "p9ak_must_keep_order_submission_disabled": True,
            "p9ak_must_keep_executor_baseline_only": True,
            "p9ak_must_keep_candidate_shadow_only": True,
            "p9ak_must_not_execute_dry_load": True,
            "p9ak_must_not_load_timer_path": True,
            "p9ak_must_not_invoke_supervisor": True,
            "current_live_supervisor_still_not_loading_hook": True,
            "current_hook_hash_matches_p9ai_source": True,
            "current_supervisor_hash_matches_p9ai_source": True,
            "remote_sync_not_authorized_in_p9aj": True,
            "remote_execution_not_authorized_in_p9aj": True,
            "timer_path_load_not_authorized_in_p9aj": True,
            "supervisor_invocation_not_authorized_in_p9aj": True,
            "candidate_execution_forbidden": True,
            "live_order_submission_forbidden": True,
            "target_plan_replacement_forbidden": True,
            "executor_input_mutation_forbidden": True,
            "live_config_operator_timer_mutation_forbidden": True,
            "production_timer_service_load_forbidden": True,
            "zero_orders_fills_in_p9aj": True,
        },
    }


def _evidence(path: Path) -> dict[str, object]:
    return {"path": str(path), "exists": path.exists(), "sha256": _sha256(path)}


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def _time_at(minutes: int):
    base = datetime(2026, 6, 7, 5, 0, tzinfo=UTC)

    def _now() -> datetime:
        return base + timedelta(minutes=minutes)

    return _now
