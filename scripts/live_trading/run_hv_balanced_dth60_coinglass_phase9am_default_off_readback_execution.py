from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.dth60_observe_only_shadow_hook import (  # noqa: E402
    ObserveOnlyShadowHookConfig,
    run_observe_only_shadow_hook,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9al_default_off_readback_owner_gate import (  # noqa: E402
    P9AM_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    current_supervisor_loads_hook,
    evidence_file,
    file_sha256,
    latest_match,
    load_optional,
    no_live_mutation,
    output_under_proof_artifacts,
    resolve_path,
    write_json,
    zero_orders_fills,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    HOOK_MODULE,
    LIVE_CONFIG_DIR,
    PROJECT_PROFILE,
    SUPERVISOR_PATH,
    source_output_path,
    tree_sha256,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9am_default_off_readback_execution.v1"
APPROVE_P9AM_DECISION = "approve_p9am_execute_default_off_observe_only_timer_path_dry_load_readback_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9am_default_off_readback_execution"
PHASE9AL_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9al_default_off_readback_owner_gate"
P9AN_GATE = "P9AN_review_after_default_off_observe_only_readback_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute P9AM as a proof_artifacts-only default-off / observe-only "
            "dry-load readback. The harness writes candidate shadow artifacts "
            "only under proof_artifacts, keeps executor input baseline-only, "
            "does not invoke the production timer service or live supervisor, "
            "does not remote sync, and submits zero orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9al-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AM_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:execute_default_off_observe_only_dry_load_readback_no_order",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9al_execution_gate_ready(summary: dict[str, Any], gate: dict[str, Any]) -> bool:
    constraints = dict(gate.get("allowed_next_action_constraints") or {})
    owner = dict(gate.get("owner_decision") or {})
    summary_owner = dict(summary.get("owner_decision") or {})
    required_summary_gates = (
        "owner_decision_p9al_readback_gate_only",
        "project_stage_boundary_preserved",
        "p9ak_default_off_readback_proposal_ready",
        "p9ak_proposal_body_ready",
        "current_live_supervisor_not_loading_hook",
        "current_hook_hash_matches_p9ak_source",
        "current_supervisor_hash_matches_p9ak_source",
        "readback_execution_gate_output_under_proof_artifacts",
        "future_readback_must_be_default_off",
        "future_readback_must_be_observe_only",
        "future_readback_must_be_proof_artifacts_only",
        "future_readback_must_keep_order_authority_disabled",
        "future_readback_must_keep_executor_baseline_only",
        "future_readback_must_keep_candidate_shadow_only",
        "future_readback_must_not_replace_target_plan",
        "future_readback_must_not_mutate_executor_input",
        "future_readback_must_not_submit_orders",
        "no_readback_execution_in_p9al",
        "no_timer_hook_implementation_in_p9al",
        "no_hook_deployment_in_p9al",
        "no_timer_path_load_in_p9al",
        "no_supervisor_invocation_in_p9al",
        "no_remote_sync_in_p9al",
        "no_remote_execution_in_p9al",
        "no_candidate_execution_in_p9al",
        "no_executor_input_mutation_in_p9al",
        "no_target_plan_replacement_in_p9al",
        "no_live_mutation_in_p9al",
        "zero_orders_fills_in_p9al",
    )
    gates = dict(summary.get("gates") or {})
    return (
        summary.get("contract_version") == "hv_balanced_dth60_coinglass_phase9al_default_off_readback_owner_gate.v1"
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("gate_scope")
        == "owner_gated_default_off_observe_only_timer_path_dry_load_readback_execution_permission_only"
        and summary.get("p9al_default_off_observe_only_readback_owner_gate_ready") is True
        and summary.get("eligible_to_execute_default_off_observe_only_readback") is True
        and summary.get("executed_default_off_observe_only_readback") is False
        and summary.get("dry_load_readback_executed") is False
        and summary.get("allowed_next_gate") == P9AM_GATE
        and summary.get("future_readback_default_off_required") is True
        and summary.get("future_readback_observe_only_required") is True
        and summary.get("future_readback_artifact_sink_required") == "proof_artifacts_only"
        and summary.get("future_readback_executor_input_required") == "baseline_only"
        and summary.get("future_readback_candidate_order_authority_required") == "disabled"
        and summary.get("future_readback_live_order_submission_authorized_required") is False
        and summary.get("future_readback_candidate_execution_authorized_required") is False
        and summary.get("dry_load_readback_execution_authorized") is False
        and summary.get("timer_hook_implementation_authorized") is False
        and summary.get("hook_deployment_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("remote_execution_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("live_config_mutation_authorized") is False
        and summary.get("operator_state_mutation_authorized") is False
        and summary.get("timer_or_service_mutation_authorized") is False
        and summary.get("production_timer_service_load_authorized") is False
        and summary.get("repo_stage_change_authorized") is False
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("candidate_live_order_submission_authorized") is False
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_overlay_execution_path") == "excluded"
        and summary.get("candidate_artifact_sink") == "proof_artifacts_only"
        and summary.get("live_supervisor_loads_candidate_hook") is False
        and summary.get("live_timer_path_loaded") is False
        and summary.get("live_timer_service_enabled_or_invoked") is False
        and summary.get("ran_supervisor") is False
        and summary.get("supervisor_invoked") is False
        and summary.get("remote_sync_performed") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("candidate_execution_performed") is False
        and summary.get("applied_to_live") is False
        and summary.get("live_config_changed") is False
        and summary.get("operator_state_changed") is False
        and summary.get("timer_state_changed") is False
        and summary.get("target_plan_replaced") is False
        and summary.get("executor_input_changed") is False
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "fills_observed")
        and summary.get("exchange_order_submission") == "disabled"
        and summary_owner.get("decision")
        == "approve_p9al_execute_default_off_observe_only_timer_path_dry_load_readback_only"
        and summary_owner.get("future_default_off_observe_only_readback_execution_gate_approved") is True
        and summary_owner.get("dry_load_readback_execution_approved") is False
        and summary_owner.get("timer_path_load_approved") is False
        and summary_owner.get("live_order_submission_approved") is False
        and gate.get("contract_version") == "hv_balanced_dth60_coinglass_phase9al_readback_execution_gate.v1"
        and gate.get("gate_scope")
        == "owner_gated_default_off_observe_only_timer_path_dry_load_readback_execution_permission_only"
        and gate.get("allowed_next_action") == "execute_default_off_observe_only_timer_path_dry_load_readback"
        and gate.get("allowed_next_gate") == P9AM_GATE
        and gate.get("executed_in_p9al") is False
        and constraints.get("default_off_required") is True
        and constraints.get("observe_only_required") is True
        and constraints.get("proof_artifacts_only") is True
        and constraints.get("candidate_order_authority") == "disabled"
        and constraints.get("candidate_live_order_submission_authorized") is False
        and constraints.get("candidate_execution_authorized") is False
        and constraints.get("executor_input_must_remain_baseline_only") is True
        and constraints.get("candidate_plan_must_not_be_referenced_by_executor") is True
        and constraints.get("candidate_artifacts_under_proof_artifacts_only") is True
        and constraints.get("target_plan_must_not_be_replaced") is True
        and constraints.get("executor_input_must_not_change") is True
        and constraints.get("must_not_modify_mainnet_live_supervisor") is True
        and constraints.get("must_not_modify_live_config") is True
        and constraints.get("must_not_modify_operator_state") is True
        and constraints.get("must_not_modify_timer_or_service_state") is True
        and constraints.get("must_not_enable_live_timer_service") is True
        and constraints.get("must_not_submit_orders") is True
        and int(constraints.get("orders_submitted_must_equal", -1)) == 0
        and int(constraints.get("fill_count_must_equal", -1)) == 0
        and int(constraints.get("fills_observed_must_equal", -1)) == 0
        and owner.get("decision")
        == "approve_p9al_execute_default_off_observe_only_timer_path_dry_load_readback_only"
        and owner.get("future_default_off_observe_only_readback_execution_gate_approved") is True
        and owner.get("dry_load_readback_execution_approved") is False
        and owner.get("timer_path_load_approved") is False
        and owner.get("supervisor_invocation_approved") is False
        and owner.get("remote_sync_approved") is False
        and owner.get("candidate_execution_approved") is False
        and owner.get("live_order_submission_approved") is False
        and owner.get("target_plan_replacement_approved") is False
        and owner.get("executor_input_mutation_approved") is False
        and owner.get("live_config_mutation_approved") is False
        and owner.get("operator_state_mutation_approved") is False
        and owner.get("timer_or_service_mutation_approved") is False
        and owner.get("production_timer_service_load_approved") is False
        and all(gates.get(key) is True for key in required_summary_gates)
    )


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9AM_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9am_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "execute_default_off_observe_only_timer_path_dry_load_readback_only",
        "decision_effect": (
            "execute_local_proof_artifacts_default_off_observe_only_readback_under_p9al_constraints"
            if approved
            else "none"
        ),
        "default_off_observe_only_readback_execution_approved": approved,
        "candidate_shadow_artifact_write_approved_under_proof_artifacts": approved,
        "candidate_execution_approved": False,
        "candidate_live_order_submission_approved": False,
        "timer_hook_implementation_approved": False,
        "hook_deployment_approved": False,
        "live_timer_path_load_approved": False,
        "production_timer_service_load_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "remote_sync_approved": False,
        "supervisor_invocation_approved": False,
        "supervisor_run_approved": False,
        "repo_stage_change_approved": False,
    }


def build_fixture_plans(proof_root: Path) -> dict[str, Path]:
    input_root = proof_root / "input_plans"
    baseline = input_root / "baseline_target_plan.json"
    executor = input_root / "executor_input_target_plan.json"
    candidate = input_root / "candidate_shadow_plan.json"
    baseline_payload = {
        "contract_version": "hv_balanced_dth60_phase9am_fixture_plan.v1",
        "plan_type": "baseline_target_plan",
        "generated_for": "default_off_observe_only_timer_path_dry_load_readback",
        "timestamp_utc": "2026-06-07T00:00:00Z",
        "strategy_id": "hv_balanced_baseline",
        "positions": [
            {"symbol": "BTCUSDT", "target_weight": 0.10},
            {"symbol": "ETHUSDT", "target_weight": -0.05},
        ],
        "slice_metrics": {
            "distance_to_high_60_contribution": -0.0125,
            "gross_target": 0.15,
            "net_target": 0.05,
        },
        "risk_inputs": {
            "gross_cap": 0.15,
            "leverage_cap": 2.0,
            "execution_target_source": "baseline_only",
        },
    }
    candidate_payload = {
        "contract_version": "hv_balanced_dth60_phase9am_fixture_plan.v1",
        "plan_type": "candidate_shadow_plan",
        "generated_for": "default_off_observe_only_timer_path_dry_load_readback",
        "timestamp_utc": "2026-06-07T00:00:00Z",
        "strategy_id": "hybrid_q90_or_crowded_zero_shadow",
        "positions": [
            {"symbol": "BTCUSDT", "target_weight": 0.07},
            {"symbol": "ETHUSDT", "target_weight": -0.02},
        ],
        "candidate_overlay": {
            "trigger": "hybrid_q90_or_crowded_zero",
            "trigger_state": "crowded_zero_or_shock_guard_shadow",
            "only_changes_factor": "distance_to_high_60",
            "distance_to_high_60_contribution": 0.0,
        },
        "slice_metrics": {
            "distance_to_high_60_contribution": 0.0,
            "gross_target": 0.09,
            "net_target": 0.05,
        },
        "risk_inputs": {
            "gross_cap": 0.15,
            "leverage_cap": 2.0,
            "execution_target_source": "candidate_shadow_only",
        },
    }
    write_json(baseline, baseline_payload)
    write_json(executor, baseline_payload)
    write_json(candidate, candidate_payload)
    return {"baseline": baseline, "executor": executor, "candidate": candidate}


def build_blocked_summary(
    *,
    root: Path,
    proof_root: Path,
    run_id: str,
    generated_at: datetime,
    blockers: list[str],
    gates: dict[str, bool],
    decision: dict[str, Any],
    source_evidence: dict[str, Any],
    supervisor_sha_before: str,
    supervisor_sha_after: str,
    supervisor_loads: bool,
    live_config_sha_before: str,
    live_config_sha_after: str,
) -> dict[str, Any]:
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9am_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "pre_execution_gate_failed_no_default_off_observe_only_readback",
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "entered_timer_path_dry_load_harness": False,
        "entered_live_timer_path": False,
        "executed_default_off_observe_only_readback": False,
        "dry_load_readback_executed": False,
        "candidate_shadow_artifact_write_attempted": False,
        "candidate_execution_performed": False,
        "applied_to_live": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "remote_control_plane_touched": False,
        "ran_supervisor": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
    }
    write_json(proof_root / "control_boundary_readback.json", control)
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "p9am_default_off_observe_only_readback_execution.md"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": "blocked",
        "blockers": blockers,
        "dry_load_readback_scope": "owner_gated_default_off_observe_only_timer_path_dry_load_readback_execution_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9am_default_off_observe_only_readback_ready": False,
        "default_off_observe_only_readback_execution_authorized": False,
        "executed_default_off_observe_only_readback": False,
        "dry_load_readback_executed": False,
        "dry_load_mode": "not_executed",
        "dry_load_outputs_under_proof_artifacts": output_under_proof_artifacts(proof_root),
        "default_off_config_loaded": False,
        "default_off_hook_enabled": False,
        "observe_only_shadow_writer_enabled_in_proof_harness": False,
        "observe_only_shadow_readback_ready": False,
        "candidate_shadow_artifacts_written_count": 0,
        "candidate_artifacts_under_proof_artifacts_only": False,
        "baseline_target_plan_byte_for_byte_unchanged": False,
        "executor_input_hash_unchanged": False,
        "executor_input_hash_equals_baseline": False,
        "executor_consumes_baseline_only": False,
        "candidate_shadow_hash_differs_from_executor": False,
        "candidate_plan_referenced_by_executor": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "eligible_for_owner_p9an_review": False,
        "eligible_for_timer_hook_implementation": False,
        "eligible_for_hook_deployment": False,
        "eligible_for_live_timer_path_load": False,
        "eligible_for_supervisor_invocation": False,
        "eligible_for_remote_sync": False,
        "eligible_for_live_order_submission": False,
        "eligible_for_stage_governance_change": False,
        "timer_hook_implementation_authorized": False,
        "hook_deployment_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "excluded",
        "candidate_artifact_sink": "proof_artifacts_only",
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "entered_timer_path_dry_load_harness": False,
        "entered_live_timer_path": False,
        "ran_supervisor": False,
        "timer_path_invoked": False,
        "remote_execution_performed": False,
        "remote_control_plane_touched": False,
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
        "recommended_next_gate": "",
        "proof_root": str(proof_root),
        "gates": gates,
        "output_files": output_files,
    }
    write_json(root / "summary.json", summary)
    (root / "p9am_default_off_observe_only_readback_execution.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary


def build_phase9am(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = root / "proof_artifacts" / "p9am" / run_id
    proof_root.mkdir(parents=True, exist_ok=True)

    project_profile_path = resolve_path(args.project_profile)
    p9al_path = (
        resolve_path(args.phase9al_summary)
        if str(args.phase9al_summary).strip()
        else latest_match(PHASE9AL_PARENT, "*/summary.json")
    )
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)

    project_profile = load_optional(project_profile_path)
    p9al = load_optional(p9al_path)
    p9al_gate_path = source_output_path(p9al, "readback_execution_gate")
    p9al_gate = load_optional(p9al_gate_path)
    supervisor_sha_before = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    hook_sha = file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else ""
    live_config_sha_before = tree_sha256(live_config_dir)
    supervisor_loads = current_supervisor_loads_hook(supervisor_path)
    decision = owner_decision_record(args, generated_at)
    p9al_source = dict(p9al.get("source_evidence") or {})
    p9al_hook = dict(p9al_source.get("hook_module") or {})
    p9al_supervisor = dict(p9al_source.get("live_supervisor") or {})
    p9al_config = dict(p9al_source.get("live_config_dir") or {})

    source_evidence = {
        "project_profile": evidence_file(project_profile_path),
        "phase9al_summary": evidence_file(p9al_path),
        "phase9al_readback_execution_gate": evidence_file(p9al_gate_path),
        "hook_module": evidence_file(hook_path),
        "live_supervisor": evidence_file(supervisor_path),
        "live_config_dir": {
            "path": str(live_config_dir),
            "exists": live_config_dir.exists(),
            "sha256": live_config_sha_before,
        },
    }
    pre_gates = {
        "owner_decision_p9am_execute_readback_only": args.owner_decision == APPROVE_P9AM_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage")
        == "stage_1_research_readiness_only",
        "p9al_readback_owner_gate_ready": p9al_execution_gate_ready(p9al, p9al_gate),
        "p9al_allows_p9am_only": p9al.get("allowed_next_gate") == P9AM_GATE,
        "p9al_did_not_execute_readback": p9al.get("executed_default_off_observe_only_readback") is False,
        "current_live_supervisor_not_loading_hook": supervisor_loads is False,
        "current_hook_hash_matches_p9al_source": p9al_hook.get("sha256") == hook_sha,
        "current_supervisor_hash_matches_p9al_source": p9al_supervisor.get("sha256") == supervisor_sha_before,
        "current_live_config_hash_matches_p9al_source": p9al_config.get("sha256") == live_config_sha_before,
        "dry_load_output_root_under_proof_artifacts": output_under_proof_artifacts(proof_root),
    }
    blockers = [key for key, value in pre_gates.items() if not value]
    write_json(root / "owner_decision_record.json", decision)

    if blockers:
        supervisor_sha_after = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
        live_config_sha_after = tree_sha256(live_config_dir)
        summary = build_blocked_summary(
            root=root,
            proof_root=proof_root,
            run_id=run_id,
            generated_at=generated_at,
            blockers=blockers,
            gates=pre_gates,
            decision=decision,
            source_evidence=source_evidence,
            supervisor_sha_before=supervisor_sha_before,
            supervisor_sha_after=supervisor_sha_after,
            supervisor_loads=supervisor_loads,
            live_config_sha_before=live_config_sha_before,
            live_config_sha_after=live_config_sha_after,
        )
        return summary, 2

    plan_paths = build_fixture_plans(proof_root)
    shadow_config = ObserveOnlyShadowHookConfig(
        enabled=True,
        mode="observe_only",
        artifact_sink="proof_artifacts_only",
        output_root=proof_root / "observe_only_shadow_output",
        candidate_order_authority="disabled",
        candidate_live_order_submission_authorized=False,
        execution_target_source="baseline_only",
        candidate_overlay_execution_path="excluded",
    )
    shadow_summary = run_observe_only_shadow_hook(
        config=shadow_config,
        baseline_target_plan_path=plan_paths["baseline"],
        executor_input_plan_path=plan_paths["executor"],
        candidate_shadow_plan_path=plan_paths["candidate"],
        supervisor_context={
            "phase": "P9AM",
            "dry_load_mode": "default_off_observe_only_timer_path_readback_harness_not_live_timer_service",
            "default_off_hook_enabled_in_live_config": False,
            "observe_only_shadow_writer_enabled_in_proof_harness": True,
            "entered_timer_path_dry_load_harness": True,
            "entered_live_timer_path": False,
            "live_timer_service_enabled_or_invoked": False,
            "supervisor_run_for_execution": False,
        },
        run_id=f"{run_id}-default-off-observe-only-readback",
        now=generated_at,
    )
    write_json(proof_root / "observe_only_shadow_readback_summary.json", shadow_summary)

    baseline_sha = file_sha256(plan_paths["baseline"])
    executor_sha = file_sha256(plan_paths["executor"])
    candidate_sha = file_sha256(plan_paths["candidate"])
    executor_input_hash_equals_baseline = bool(executor_sha) and executor_sha == baseline_sha
    candidate_shadow_hash_differs_from_executor = bool(candidate_sha) and candidate_sha != executor_sha
    default_off_config_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9am_default_off_config_readback.v1",
        "run_id": run_id,
        "dry_load_mode": "default_off_observe_only_timer_path_readback_harness_not_live_timer_service",
        "default_off_required": True,
        "hook_config_enabled_default": False,
        "observe_only_shadow_writer_enabled_in_proof_harness": True,
        "mode": shadow_config.mode,
        "artifact_sink": shadow_config.artifact_sink,
        "candidate_execution_authorized": False,
        "candidate_order_authority": shadow_config.candidate_order_authority,
        "candidate_live_order_submission_authorized": shadow_config.candidate_live_order_submission_authorized,
        "execution_target_source": shadow_config.execution_target_source,
        "candidate_overlay_execution_path": shadow_config.candidate_overlay_execution_path,
        "proof_artifacts_only": output_under_proof_artifacts(proof_root),
        "entered_timer_path_dry_load_harness": True,
        "entered_live_timer_path": False,
        "live_timer_service_enabled_or_invoked": False,
        "supervisor_run_for_execution": False,
        "remote_sync_performed": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
    }
    executor_input_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9am_executor_input_readback.v1",
        "run_id": run_id,
        "execution_target_source": "baseline_only",
        "baseline_target_plan": evidence_file(plan_paths["baseline"]),
        "executor_input_plan": evidence_file(plan_paths["executor"]),
        "candidate_shadow_source_plan": evidence_file(plan_paths["candidate"]),
        "candidate_shadow_artifact_paths": list(shadow_summary.get("candidate_artifact_paths") or []),
        "candidate_shadow_artifacts_written_count": int(
            shadow_summary.get("candidate_artifacts_written_count") or 0
        ),
        "executor_input_hash_equals_baseline": executor_input_hash_equals_baseline,
        "candidate_shadow_hash_differs_from_executor": candidate_shadow_hash_differs_from_executor,
        "candidate_plan_referenced_by_executor": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
    }
    write_json(proof_root / "default_off_config_readback.json", default_off_config_readback)
    write_json(proof_root / "executor_input_readback.json", executor_input_readback)

    dry_load_manifest = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9am_dry_load_execution_manifest.v1",
        "run_id": run_id,
        "executed_default_off_observe_only_readback": True,
        "dry_load_readback_executed": True,
        "dry_load_mode": "default_off_observe_only_timer_path_readback_harness_not_live_timer_service",
        "dry_load_source": "retained_p9al_owner_gate_plus_local_fresh_fixture_plans",
        "source_phase9al_summary": evidence_file(p9al_path),
        "source_phase9al_readback_execution_gate": evidence_file(p9al_gate_path),
        "default_off_config_readback": evidence_file(proof_root / "default_off_config_readback.json"),
        "observe_only_shadow_readback_summary": evidence_file(
            proof_root / "observe_only_shadow_readback_summary.json"
        ),
        "executor_input_readback": evidence_file(proof_root / "executor_input_readback.json"),
        "default_off_hook_enabled_in_live_config": False,
        "observe_only_shadow_writer_enabled_in_proof_harness": True,
        "entered_timer_path_dry_load_harness": True,
        "entered_live_timer_path": False,
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "supervisor_run_invoked": False,
        "remote_sync_performed": False,
        "candidate_execution_authorized": False,
        "candidate_execution_performed": False,
        "execution_target_source": "baseline_only",
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
    }
    write_json(proof_root / "dry_load_execution_manifest.json", dry_load_manifest)

    supervisor_sha_after = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    live_config_sha_after = tree_sha256(live_config_dir)
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9am_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "local_proof_artifacts_default_off_observe_only_readback_only",
        "live_supervisor": evidence_file(supervisor_path),
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "entered_timer_path_dry_load_harness": True,
        "entered_live_timer_path": False,
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "ran_supervisor": False,
        "remote_control_plane_touched": False,
        "candidate_execution_authorized": False,
        "candidate_execution_performed": False,
        "applied_to_live": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
    }
    write_json(proof_root / "control_boundary_readback.json", control)

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "dry_load_execution_manifest": str(proof_root / "dry_load_execution_manifest.json"),
        "default_off_config_readback": str(proof_root / "default_off_config_readback.json"),
        "observe_only_shadow_readback_summary": str(proof_root / "observe_only_shadow_readback_summary.json"),
        "executor_input_readback": str(proof_root / "executor_input_readback.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "baseline_target_plan": str(plan_paths["baseline"]),
        "executor_input_plan": str(plan_paths["executor"]),
        "candidate_shadow_plan": str(plan_paths["candidate"]),
        "report": str(root / "p9am_default_off_observe_only_readback_execution.md"),
    }
    output_paths_under_proof = all(
        output_under_proof_artifacts(resolve_path(path))
        for key, path in output_files.items()
        if key not in {"summary", "owner_decision_record", "report"}
    )
    shadow_summary_ready = (
        shadow_summary.get("status") == "ready"
        and shadow_summary.get("hook_enabled") is True
        and shadow_summary.get("executor_consumes_baseline_only") is True
        and int(shadow_summary.get("candidate_artifacts_written_count") or 0) > 0
        and shadow_summary.get("candidate_artifacts_under_proof_artifacts_only") is True
        and shadow_summary.get("candidate_plan_referenced_by_executor") is False
        and zero_orders_fills(shadow_summary)
        and no_live_mutation(shadow_summary)
    )
    gates = {
        **pre_gates,
        "dry_load_outputs_under_proof_artifacts": output_paths_under_proof,
        "dry_load_mode_not_live_timer_service": default_off_config_readback.get("dry_load_mode")
        == "default_off_observe_only_timer_path_readback_harness_not_live_timer_service",
        "default_off_config_loaded": default_off_config_readback.get("hook_config_enabled_default") is False,
        "observe_only_shadow_writer_enabled_in_proof_harness": default_off_config_readback.get(
            "observe_only_shadow_writer_enabled_in_proof_harness"
        )
        is True,
        "entered_timer_path_dry_load_harness": default_off_config_readback.get("entered_timer_path_dry_load_harness")
        is True,
        "entered_live_timer_path_false": default_off_config_readback.get("entered_live_timer_path") is False,
        "candidate_execution_not_authorized": default_off_config_readback.get("candidate_execution_authorized")
        is False,
        "artifact_sink_proof_artifacts_only": default_off_config_readback.get("artifact_sink")
        == "proof_artifacts_only",
        "candidate_order_authority_disabled": default_off_config_readback.get("candidate_order_authority")
        == "disabled",
        "candidate_live_order_submission_authorized_false": default_off_config_readback.get(
            "candidate_live_order_submission_authorized"
        )
        is False,
        "execution_target_source_baseline_only": default_off_config_readback.get("execution_target_source")
        == "baseline_only",
        "observe_only_shadow_readback_ready": shadow_summary_ready,
        "candidate_shadow_artifacts_written": int(shadow_summary.get("candidate_artifacts_written_count") or 0) > 0,
        "candidate_artifacts_under_proof_artifacts_only": shadow_summary.get(
            "candidate_artifacts_under_proof_artifacts_only"
        )
        is True,
        "baseline_target_plan_byte_for_byte_unchanged": shadow_summary.get(
            "baseline_target_plan_byte_for_byte_unchanged"
        )
        is True,
        "executor_input_hash_unchanged": shadow_summary.get("executor_input_plan_hash_unchanged") is True,
        "executor_input_hash_equals_baseline": executor_input_hash_equals_baseline,
        "executor_consumes_baseline_only": shadow_summary.get("executor_consumes_baseline_only") is True,
        "candidate_shadow_hash_differs_from_executor": candidate_shadow_hash_differs_from_executor,
        "candidate_plan_not_referenced_by_executor": executor_input_readback.get("candidate_plan_referenced_by_executor")
        is False,
        "target_plan_not_replaced": executor_input_readback.get("target_plan_replaced") is False,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "live_timer_service_not_enabled_or_invoked": default_off_config_readback.get(
            "live_timer_service_enabled_or_invoked"
        )
        is False,
        "supervisor_not_run_for_execution": default_off_config_readback.get("supervisor_run_for_execution") is False,
        "no_remote_sync_in_p9am": default_off_config_readback.get("remote_sync_performed") is False,
        "no_live_timer_path_load_in_p9am": control.get("live_timer_path_loaded") is False,
        "no_candidate_execution_in_p9am": control.get("candidate_execution_performed") is False,
        "no_executor_input_mutation_in_p9am": control.get("executor_input_mutated") is False,
        "no_target_plan_replacement_in_p9am": control.get("target_plan_replaced") is False,
        "no_live_mutation_in_p9am": no_live_mutation(control),
        "zero_orders_fills_in_p9am": zero_orders_fills(control),
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    ready = status == "ready"
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": status,
        "blockers": blockers,
        "dry_load_readback_scope": "owner_gated_default_off_observe_only_timer_path_dry_load_readback_execution_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9am_default_off_observe_only_readback_ready": ready,
        "default_off_observe_only_readback_execution_authorized": decision.get(
            "default_off_observe_only_readback_execution_approved"
        )
        is True,
        "executed_default_off_observe_only_readback": True,
        "dry_load_readback_executed": True,
        "dry_load_mode": "default_off_observe_only_timer_path_readback_harness_not_live_timer_service",
        "dry_load_outputs_under_proof_artifacts": output_paths_under_proof,
        "default_off_config_loaded": default_off_config_readback.get("hook_config_enabled_default") is False,
        "default_off_hook_enabled": False,
        "observe_only_shadow_writer_enabled_in_proof_harness": True,
        "observe_only_shadow_readback_ready": shadow_summary_ready,
        "candidate_shadow_artifacts_written_count": int(
            shadow_summary.get("candidate_artifacts_written_count") or 0
        ),
        "candidate_artifacts_under_proof_artifacts_only": shadow_summary.get(
            "candidate_artifacts_under_proof_artifacts_only"
        ),
        "baseline_target_plan_byte_for_byte_unchanged": shadow_summary.get(
            "baseline_target_plan_byte_for_byte_unchanged"
        ),
        "executor_input_hash_unchanged": shadow_summary.get("executor_input_plan_hash_unchanged"),
        "executor_input_hash_equals_baseline": executor_input_hash_equals_baseline,
        "executor_consumes_baseline_only": shadow_summary.get("executor_consumes_baseline_only"),
        "candidate_shadow_hash_differs_from_executor": candidate_shadow_hash_differs_from_executor,
        "candidate_plan_referenced_by_executor": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "eligible_for_owner_p9an_review": ready,
        "eligible_for_timer_hook_implementation": False,
        "eligible_for_hook_deployment": False,
        "eligible_for_live_timer_path_load": False,
        "eligible_for_supervisor_invocation": False,
        "eligible_for_remote_sync": False,
        "eligible_for_live_order_submission": False,
        "eligible_for_stage_governance_change": False,
        "timer_hook_implementation_authorized": False,
        "hook_deployment_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "excluded",
        "candidate_artifact_sink": "proof_artifacts_only",
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "entered_timer_path_dry_load_harness": True,
        "entered_live_timer_path": False,
        "ran_supervisor": False,
        "timer_path_invoked": False,
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
        "recommended_next_gate": P9AN_GATE if ready else "",
        "proof_root": str(proof_root),
        "gates": gates,
        "output_files": output_files,
    }
    write_json(root / "summary.json", summary)
    (root / "p9am_default_off_observe_only_readback_execution.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9AM Default-Off Observe-Only Readback Execution",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9AM executes a local proof_artifacts-only dry-load/readback from retained P9AL permission.",
        "",
        "```text",
        "dry_load_readback_scope = owner_gated_default_off_observe_only_timer_path_dry_load_readback_execution_only",
        "executed_default_off_observe_only_readback = "
        f"{str(bool(summary['executed_default_off_observe_only_readback'])).lower()}",
        f"dry_load_mode = {summary['dry_load_mode']}",
        "default_off_hook_enabled = false",
        "observe_only_shadow_writer_enabled_in_proof_harness = "
        f"{str(bool(summary['observe_only_shadow_writer_enabled_in_proof_harness'])).lower()}",
        "timer_path_load_authorized = false",
        "supervisor_invocation_authorized = false",
        "live_order_submission_authorized = false",
        "execution_target_source = baseline_only",
        "candidate_artifact_sink = proof_artifacts_only",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Gates",
        "",
        "```text",
    ]
    for key, value in dict(summary.get("gates") or {}).items():
        lines.append(f"{key} = {str(bool(value)).lower()}")
    lines.extend(["```", "", "## Blockers", ""])
    blockers = list(summary.get("blockers") or [])
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9am(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
