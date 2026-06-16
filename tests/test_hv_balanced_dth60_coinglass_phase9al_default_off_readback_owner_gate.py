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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9al_default_off_readback_owner_gate import (  # noqa: E402
    APPROVE_P9AL_DECISION,
    P9AM_GATE,
    build_phase9al,
    p9ak_ready_for_p9al,
)


class Phase9ALDefaultOffReadbackOwnerGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="p9al-"))
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

    def test_p9al_allows_only_future_no_order_readback_execution_gate(self) -> None:
        p9ak = self._write_p9ak_bundle()
        summary, exit_code = build_phase9al(self._args(p9ak, self.temp_dir / "p9al-ready"), now_fn=_time_at(0))

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["status"], "ready")
        self.assertTrue(summary["p9al_default_off_observe_only_readback_owner_gate_ready"])
        self.assertTrue(summary["eligible_to_execute_default_off_observe_only_readback"])
        self.assertFalse(summary["executed_default_off_observe_only_readback"])
        self.assertFalse(summary["dry_load_readback_executed"])
        self.assertEqual(summary["allowed_next_gate"], P9AM_GATE)
        self.assertTrue(summary["allowed_next_gate_must_be_separately_requested"])
        self.assertEqual(summary["future_readback_artifact_sink_required"], "proof_artifacts_only")
        self.assertEqual(summary["future_readback_executor_input_required"], "baseline_only")
        self.assertEqual(summary["future_readback_candidate_order_authority_required"], "disabled")
        self.assertFalse(summary["future_readback_live_order_submission_authorized_required"])
        self.assertFalse(summary["future_readback_candidate_execution_authorized_required"])
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
        self.assertFalse(summary["remote_execution_performed"])
        self.assertEqual(summary["orders_submitted"], 0)
        self.assertEqual(summary["fill_count"], 0)

        proof_root = Path(summary["proof_root"])
        gate = _read_json(proof_root / "readback_execution_gate.json")
        self.assertEqual(gate["allowed_next_action"], "execute_default_off_observe_only_timer_path_dry_load_readback")
        self.assertEqual(gate["allowed_next_gate"], P9AM_GATE)
        self.assertFalse(gate["executed_in_p9al"])
        self.assertTrue(gate["allowed_next_action_constraints"]["default_off_required"])
        self.assertTrue(gate["allowed_next_action_constraints"]["observe_only_required"])
        self.assertTrue(gate["allowed_next_action_constraints"]["proof_artifacts_only"])
        self.assertEqual(gate["allowed_next_action_constraints"]["candidate_order_authority"], "disabled")
        self.assertEqual(gate["allowed_next_action_constraints"]["orders_submitted_must_equal"], 0)

    def test_p9al_blocks_if_p9ak_proposal_not_ready(self) -> None:
        p9ak = self._write_p9ak_bundle(p9ak_overrides={"p9ak_authorizes_dry_load_readback_execution": True})
        self.assertFalse(
            p9ak_ready_for_p9al(
                _read_json(p9ak),
                proposal=_read_json(Path(_read_json(p9ak)["output_files"]["default_off_observe_only_timer_path_readback_proposal"])),
                current_hook_sha256=_sha256(self.hook),
                current_supervisor_sha256=_sha256(self.supervisor),
            )
        )

        summary, exit_code = build_phase9al(self._args(p9ak, self.temp_dir / "p9al-block-p9ak"), now_fn=_time_at(1))
        self.assertEqual(exit_code, 2)
        self.assertIn("p9ak_default_off_readback_proposal_ready", summary["blockers"])
        self.assertFalse(summary["eligible_to_execute_default_off_observe_only_readback"])
        self.assertFalse(summary["dry_load_readback_execution_authorized"])

    def test_p9al_blocks_if_proposal_body_allows_orders(self) -> None:
        p9ak = self._write_p9ak_bundle(
            proposal_overrides={
                "proposed_future_readback_contract": {
                    "dry_load_readback_must_not_submit_orders": False,
                    "orders_submitted_must_equal": 1,
                }
            }
        )
        summary, exit_code = build_phase9al(self._args(p9ak, self.temp_dir / "p9al-block-proposal"), now_fn=_time_at(2))

        self.assertEqual(exit_code, 2)
        self.assertIn("p9ak_proposal_body_ready", summary["blockers"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_p9al_blocks_if_supervisor_now_loads_hook(self) -> None:
        p9ak = self._write_p9ak_bundle()
        self.supervisor.write_text(
            "from enhengclaw.live_trading.dth60_observe_only_shadow_hook import run_observe_only_shadow_hook\n",
            encoding="utf-8",
        )
        summary, exit_code = build_phase9al(
            self._args(p9ak, self.temp_dir / "p9al-block-supervisor"),
            now_fn=_time_at(3),
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("current_live_supervisor_not_loading_hook", summary["blockers"])
        self.assertTrue(summary["live_supervisor_loads_candidate_hook"])
        self.assertFalse(summary["timer_path_load_authorized"])
        self.assertFalse(summary["live_order_submission_authorized"])

    def test_p9al_blocks_wrong_owner_decision(self) -> None:
        p9ak = self._write_p9ak_bundle()
        args = self._args(p9ak, self.temp_dir / "p9al-block-owner")
        args.owner_decision = "approve_live_orders"
        summary, exit_code = build_phase9al(args, now_fn=_time_at(4))

        self.assertEqual(exit_code, 2)
        self.assertIn("owner_decision_p9al_readback_gate_only", summary["blockers"])
        self.assertFalse(summary["owner_decision"]["future_default_off_observe_only_readback_execution_gate_approved"])
        self.assertFalse(summary["eligible_to_execute_default_off_observe_only_readback"])

    def _args(self, p9ak: Path, output_root: Path) -> Namespace:
        return Namespace(
            output_root=str(output_root),
            project_profile=str(self.project_profile),
            phase9ak_summary=str(p9ak),
            hook_module=str(self.hook),
            supervisor=str(self.supervisor),
            live_config_dir=str(self.config_dir),
            owner="rulebook_owner",
            owner_decision=APPROVE_P9AL_DECISION,
            owner_decision_source="test",
        )

    def _write_p9ak_bundle(
        self,
        *,
        p9ak_overrides: dict[str, object] | None = None,
        proposal_overrides: dict[str, object] | None = None,
    ) -> Path:
        proposal_path = self.temp_dir / "proof_artifacts" / "p9ak" / "proposal.json"
        proposal = _proposal_body()
        _deep_update(proposal, proposal_overrides or {})
        _write_json(proposal_path, proposal)
        p9ak_path = self.temp_dir / "p9ak_summary.json"
        p9ak = _p9ak_summary(
            hook_path=self.hook,
            supervisor_path=self.supervisor,
            proposal_path=proposal_path,
        )
        _deep_update(p9ak, p9ak_overrides or {})
        _write_json(p9ak_path, p9ak)
        return p9ak_path


def _p9ak_summary(*, hook_path: Path, supervisor_path: Path, proposal_path: Path) -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ak_default_off_timer_path_readback_proposal.v1",
        "run_id": "20260607T042732Z",
        "status": "ready",
        "blockers": [],
        "proposal_scope": "owner_gated_default_off_observe_only_timer_path_readback_proposal_only",
        "p9ak_default_off_observe_only_timer_path_readback_proposal_ready": True,
        "eligible_for_future_default_off_observe_only_readback_owner_gate": True,
        "prepared_p9ak_proposal": True,
        "wrote_p9ak_proposal_body": True,
        "proposal_body_sink": "proof_artifacts_only",
        "p9ak_authorizes_dry_load_readback_execution": False,
        "future_readback_execution_gate_required": True,
        "proposed_future_gate": "P9AL_default_off_observe_only_hook_live_supervisor_timer_path_dry_load_readback_owner_gate_only_if_separately_requested",
        "proposed_readback_default_off": True,
        "proposed_readback_observe_only": True,
        "proposed_readback_mode": "proposal_only_not_executed",
        "proposed_timer_load_mode": "proposal_only_not_loaded",
        "proposed_executor_input_source": "baseline_only",
        "proposed_candidate_artifact_sink": "proof_artifacts_only",
        "proposed_candidate_order_authority": "disabled",
        "proposed_candidate_live_order_submission_authorized": False,
        "eligible_for_dry_load_readback_execution": False,
        "eligible_for_timer_hook_implementation": False,
        "eligible_for_hook_deployment": False,
        "eligible_for_timer_path_load": False,
        "eligible_for_supervisor_invocation": False,
        "eligible_for_remote_sync": False,
        "eligible_for_live_order_submission": False,
        "eligible_for_stage_governance_change": False,
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
        "live_supervisor_source_unchanged": True,
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "supervisor_invoked": False,
        "timer_path_invoked": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "remote_control_plane_touched": False,
        "candidate_execution_performed": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
        "exchange_order_submission": "disabled",
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "wrote_live_hook_config": False,
        "implemented_hook": False,
        "deployed_hook": False,
        "loaded_hook": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "owner_decision": {
            "decision": "approve_p9ak_prepare_default_off_observe_only_hook_live_supervisor_timer_path_dry_load_readback_proposal_only",
            "p9ak_proposal_preparation_approved": True,
            "proposal_body_write_approved": True,
            "future_owner_review_discussion_approved": True,
            "dry_load_readback_execution_approved": False,
            "timer_path_load_approved": False,
            "supervisor_invocation_approved": False,
            "remote_sync_approved": False,
            "live_order_submission_approved": False,
        },
        "source_evidence": {
            "hook_module": _evidence(hook_path),
            "live_supervisor": _evidence(supervisor_path),
        },
        "output_files": {
            "default_off_observe_only_timer_path_readback_proposal": str(proposal_path),
        },
        "gates": {
            "owner_decision_p9ak_proposal_only": True,
            "project_stage_boundary_preserved": True,
            "p9aj_scope_gate_ready": True,
            "current_live_supervisor_not_loading_hook": True,
            "current_hook_hash_matches_p9aj_source": True,
            "current_supervisor_hash_matches_p9aj_source": True,
            "proposal_output_under_proof_artifacts": True,
            "proposal_body_output_under_proof_artifacts": True,
            "proposal_default_off_required": True,
            "proposal_observe_only_required": True,
            "proposal_artifact_sink_proof_artifacts_only": True,
            "proposal_executor_input_source_baseline_only": True,
            "proposal_candidate_shadow_only": True,
            "proposal_candidate_order_authority_disabled": True,
            "proposal_requires_separate_future_readback_gate": True,
            "no_dry_load_readback_execution_in_p9ak": True,
            "no_timer_hook_implementation_in_p9ak": True,
            "no_hook_deployment_in_p9ak": True,
            "no_timer_path_load_in_p9ak": True,
            "no_supervisor_invocation_in_p9ak": True,
            "no_remote_sync_in_p9ak": True,
            "no_remote_execution_in_p9ak": True,
            "no_candidate_execution_in_p9ak": True,
            "no_executor_input_mutation_in_p9ak": True,
            "no_target_plan_replacement_in_p9ak": True,
            "no_live_mutation_in_p9ak": True,
            "zero_orders_fills_in_p9ak": True,
        },
    }


def _proposal_body() -> dict[str, object]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ak_timer_path_readback_proposal_body.v1",
        "run_id": "20260607T042732Z",
        "proposal_scope": "prepare_default_off_observe_only_hook_live_supervisor_timer_path_dry_load_readback_proposal_only",
        "proposal_status": "draft_for_future_owner_review",
        "p9ak_authorizes_dry_load_readback_execution": False,
        "p9ak_authorizes_timer_hook_implementation": False,
        "p9ak_authorizes_hook_deployment": False,
        "p9ak_authorizes_timer_path_load": False,
        "p9ak_authorizes_supervisor_invocation": False,
        "p9ak_authorizes_remote_sync": False,
        "p9ak_authorizes_live_orders": False,
        "future_gate_required": True,
        "proposed_future_gate": "P9AL_default_off_observe_only_hook_live_supervisor_timer_path_dry_load_readback_owner_gate_only_if_separately_requested",
        "proposed_future_gate_scope": "decide_whether_to_execute_default_off_observe_only_timer_path_dry_load_readback",
        "proposed_future_readback_contract": {
            "default_off_required": True,
            "hook_config_enabled_default": False,
            "observe_only_mode_required": True,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "execution_target_source": "baseline_only",
            "candidate_overlay_execution_path": "excluded",
            "candidate_artifact_sink": "proof_artifacts_only",
            "executor_input_must_remain_baseline_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "target_plan_must_not_be_replaced": True,
            "executor_input_must_not_change": True,
            "dry_load_readback_must_not_submit_orders": True,
            "remote_sync_must_not_occur_without_separate_gate": True,
            "live_config_must_not_change": True,
            "operator_state_must_not_change": True,
            "timer_state_must_not_change": True,
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
        },
        "default_off_hook_config_contract": {
            "ObserveOnlyShadowHookConfig.enabled": False,
            "ObserveOnlyShadowHookConfig.mode": "observe_only",
            "ObserveOnlyShadowHookConfig.artifact_sink": "proof_artifacts_only",
            "ObserveOnlyShadowHookConfig.candidate_order_authority": "disabled",
            "ObserveOnlyShadowHookConfig.candidate_live_order_submission_authorized": False,
            "ObserveOnlyShadowHookConfig.execution_target_source": "baseline_only",
            "ObserveOnlyShadowHookConfig.candidate_overlay_execution_path": "excluded",
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


def _deep_update(target: dict[str, object], patch: dict[str, object]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _time_at(minutes: int):
    base = datetime(2026, 6, 7, 5, 30, tzinfo=UTC)

    def _now() -> datetime:
        return base + timedelta(minutes=minutes)

    return _now
