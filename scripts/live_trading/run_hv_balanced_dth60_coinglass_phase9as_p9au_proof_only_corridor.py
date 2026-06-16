from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ar_open_proposal_preparation_gate import (  # noqa: E402
    APPROVE_P9AR_DECISION,
    CONTRACT_VERSION as P9AR_CONTRACT,
    DEFAULT_OUTPUT_PARENT as PHASE9AR_PARENT,
    P9AS_GATE,
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
    source_output_path,
    write_json,
    zero_orders_fills,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    HOOK_MODULE,
    LIVE_CONFIG_DIR,
    PROJECT_PROFILE,
    SUPERVISOR_PATH,
    tree_sha256,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9as_p9au_proof_only_corridor.v1"
APPROVE_CORRIDOR_DECISION = "approve_p9as_p9au_proof_only_corridor"

P9AS_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9as_proposal_package"
P9AT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9at_retained_readiness_review"
P9AU_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9au_allow_dry_load_readback_owner_gate"
CORRIDOR_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9as_p9au_proof_only_corridor"

P9AT_GATE = "P9AT_local_retained_evidence_readiness_review_only"
P9AU_GATE = (
    "P9AU_owner_gate_allow_default_off_observe_only_dry_load_readback_"
    "only_if_separately_requested"
)
P9AV_GATE = (
    "P9AV_execute_default_off_observe_only_dry_load_readback_"
    "only_if_separately_requested"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the owner-authorized P9AS/P9AT/P9AU proof-only corridor. "
            "The corridor may generate a default-off observe-only proposal package, "
            "review retained evidence, and open a future dry-load/readback request "
            "gate. It stops before dry-load/readback, timer-path load, supervisor "
            "execution, remote sync, executor mutation, config mutation, target-plan "
            "replacement, or order authority."
        )
    )
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ar-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--output-root", default="")
    parser.add_argument("--artifacts-root", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_CORRIDOR_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:authorize_p9as_p9au_proof_only_corridor",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase_root(args: argparse.Namespace, default_parent: str, phase_name: str, run_id: str) -> Path:
    if str(getattr(args, "artifacts_root", "")).strip():
        return resolve_path(args.artifacts_root) / phase_name / run_id
    return resolve_path(default_parent) / run_id


def int_equals(payload: dict[str, Any], key: str, expected: int) -> bool:
    try:
        return int(payload.get(key)) == expected
    except (TypeError, ValueError):
        return False


def all_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def common_execution_boundary() -> dict[str, Any]:
    return {
        "dry_load_readback_execution_authorized": False,
        "timer_hook_implementation_authorized": False,
        "hook_deployment_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "supervisor_run_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "candidate_execution_authorized": False,
        "candidate_live_order_submission_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "production_timer_service_load_authorized": False,
        "repo_stage_change_authorized": False,
        "candidate_order_authority": "disabled",
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "excluded",
        "candidate_artifact_sink": "proof_artifacts_only",
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
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
        "target_plan_replaced": False,
        "executor_input_changed": False,
    }


def owner_decision(
    *,
    phase: str,
    owner: str,
    source: str,
    started_at: datetime,
    decision: str,
    question: str,
    effect: str,
    allow_key: str,
) -> dict[str, Any]:
    approved = decision == APPROVE_CORRIDOR_DECISION
    return {
        "contract_version": f"hv_balanced_dth60_coinglass_{phase}_owner_decision.v1",
        "owner": owner,
        "decision": decision,
        "decision_source": source,
        "recorded_at_utc": iso_z(started_at),
        "decision_question": question,
        "decision_effect": effect if approved else "none",
        allow_key: approved,
        "dry_load_readback_execution_approved": False,
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
        "remote_execution_approved": False,
        "supervisor_invocation_approved": False,
        "supervisor_run_approved": False,
        "repo_stage_change_approved": False,
    }


def p9ar_ready_for_p9as(
    summary: dict[str, Any],
    gate_opening: dict[str, Any],
    matrix: dict[str, Any],
    *,
    current_hook_sha256: str,
    current_supervisor_sha256: str,
    current_live_config_sha256: str,
    current_supervisor_loads_candidate_hook: bool,
) -> bool:
    source = dict(summary.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    live_config = dict(source.get("live_config_dir") or {})
    owner = dict(summary.get("owner_decision") or {})
    gates = dict(summary.get("gates") or {})
    boundaries = dict(gate_opening.get("required_boundaries_for_next_gate") or {})
    authorizations = dict(matrix.get("authorizations") or {})
    false_summary_keys = (
        "proposal_preparation_action_authorized",
        "prepare_proposal_authorized",
        "proposal_package_generation_authorized",
        "proposal_body_write_authorized",
        "dry_load_readback_execution_authorized",
        "timer_hook_implementation_authorized",
        "hook_deployment_authorized",
        "timer_path_load_authorized",
        "supervisor_invocation_authorized",
        "remote_sync_authorized",
        "remote_execution_authorized",
        "candidate_execution_authorized",
        "candidate_live_order_submission_authorized",
        "live_order_submission_authorized",
        "target_plan_replacement_authorized",
        "executor_input_mutation_authorized",
        "live_config_mutation_authorized",
        "operator_state_mutation_authorized",
        "timer_or_service_mutation_authorized",
        "production_timer_service_load_authorized",
        "repo_stage_change_authorized",
        "live_supervisor_loads_candidate_hook",
        "live_timer_path_loaded",
        "live_timer_service_enabled_or_invoked",
        "ran_supervisor",
        "timer_path_invoked",
        "remote_execution_performed",
        "remote_control_plane_touched",
        "candidate_execution_performed",
        "applied_to_live",
        "live_config_changed",
        "operator_state_changed",
        "timer_state_changed",
        "wrote_live_hook_config",
        "implemented_hook",
        "deployed_hook",
        "loaded_hook",
        "target_plan_replaced",
        "executor_input_changed",
    )
    false_authorizations = (
        "prepare_proposal",
        "proposal_package_generation",
        "proposal_body_write",
        "dry_load_readback_execution",
        "candidate_execution",
        "candidate_live_order_submission",
        "timer_hook_implementation",
        "hook_deployment",
        "live_timer_path_load",
        "production_timer_service_load",
        "live_order_submission",
        "target_plan_replacement",
        "executor_input_mutation",
        "live_config_mutation",
        "operator_state_mutation",
        "timer_or_service_mutation",
        "remote_sync",
        "remote_execution",
        "supervisor_invocation",
        "supervisor_run",
        "stage_governance_change",
    )
    required_gates = (
        "owner_decision_p9ar_open_gate_only",
        "project_stage_boundary_preserved",
        "p9aq_permission_gate_ready",
        "p9aq_allowed_p9ar_only",
        "p9aq_did_not_open_gate",
        "p9aq_did_not_prepare_proposal",
        "p9aq_did_not_write_proposal_body",
        "p9aq_did_not_execute_readback",
        "current_live_supervisor_not_loading_hook",
        "current_hook_hash_matches_p9aq_source",
        "current_supervisor_hash_matches_p9aq_source",
        "current_live_config_hash_matches_p9aq_source",
        "gate_opening_output_under_proof_artifacts",
        "p9ar_opens_gate_only",
        "p9ar_does_not_prepare_proposal",
        "p9ar_does_not_generate_proposal_package",
        "p9ar_does_not_write_proposal_body",
        "p9ar_does_not_execute_dry_load_readback",
        "p9as_must_be_separately_requested",
        "p9as_must_be_proof_artifacts_only",
        "p9as_must_keep_default_off",
        "p9as_must_keep_observe_only",
        "p9as_must_keep_order_authority_disabled",
        "no_timer_hook_implementation_in_p9ar",
        "no_hook_deployment_in_p9ar",
        "no_live_timer_path_load_in_p9ar",
        "no_production_timer_service_load_in_p9ar",
        "no_supervisor_run_in_p9ar",
        "no_remote_execution_in_p9ar",
        "no_candidate_execution_in_p9ar",
        "no_executor_input_mutation_in_p9ar",
        "no_target_plan_replacement_in_p9ar",
        "no_live_mutation_in_p9ar",
        "zero_orders_fills_in_p9ar",
    )
    return (
        summary.get("contract_version") == P9AR_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9ar_open_proposal_preparation_gate_ready") is True
        and summary.get("proposal_preparation_gate_opened") is True
        and summary.get("eligible_for_future_proposal_package_preparation_request") is True
        and summary.get("allowed_next_gate") == P9AS_GATE
        and summary.get("recommended_next_gate") == P9AS_GATE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("open_proposal_preparation_gate_authorized") is True
        and all_false(summary, false_summary_keys)
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_artifact_sink") == "proof_artifacts_only"
        and summary.get("live_supervisor_source_unchanged") is True
        and summary.get("live_config_dir_unchanged") is True
        and zero_orders_fills(summary)
        and no_live_mutation(summary)
        and all(gates.get(key) is True for key in required_gates)
        and owner.get("decision") == APPROVE_P9AR_DECISION
        and owner.get("proposal_preparation_gate_open_approved") is True
        and owner.get("future_proposal_package_preparation_request_approved") is True
        and owner.get("prepare_proposal_approved") is False
        and owner.get("proposal_package_generation_approved") is False
        and owner.get("proposal_body_write_approved") is False
        and owner.get("dry_load_readback_execution_approved") is False
        and gate_opening.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ar_gate_opening.v1"
        and gate_opening.get("proposal_preparation_gate_opened") is True
        and gate_opening.get("allowed_next_gate") == P9AS_GATE
        and gate_opening.get("prepare_proposal_in_p9ar") is False
        and gate_opening.get("proposal_package_generated_in_p9ar") is False
        and gate_opening.get("proposal_body_written_in_p9ar") is False
        and gate_opening.get("dry_load_readback_executed_in_p9ar") is False
        and boundaries.get("proof_artifacts_only") is True
        and boundaries.get("default_off_only") is True
        and boundaries.get("observe_only_shadow_artifacts_only") is True
        and boundaries.get("executor_input_must_remain_baseline_only") is True
        and boundaries.get("candidate_order_authority") == "disabled"
        and boundaries.get("live_order_submission_authorized") is False
        and int_equals(boundaries, "orders_submitted_must_equal", 0)
        and int_equals(boundaries, "fill_count_must_equal", 0)
        and matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ar_non_authorization_matrix.v1"
        and authorizations.get("open_proposal_preparation_gate") is True
        and authorizations.get("future_proposal_package_preparation_request") is True
        and all(authorizations.get(key) is False for key in false_authorizations)
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def p9as_ready_for_p9at(summary: dict[str, Any], package: dict[str, Any]) -> bool:
    boundaries = dict(package.get("required_boundaries") or {})
    authorizations = dict(package.get("authorizations") or {})
    return (
        summary.get("contract_version") == "hv_balanced_dth60_coinglass_phase9as_proposal_package.v1"
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9as_proposal_package_ready") is True
        and summary.get("generated_proposal_package") is True
        and summary.get("allowed_next_gate") == P9AT_GATE
        and summary.get("prepare_proposal_authorized") is True
        and summary.get("proposal_package_generation_authorized") is True
        and summary.get("proposal_body_write_authorized") is False
        and summary.get("dry_load_readback_execution_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and zero_orders_fills(summary)
        and no_live_mutation(summary)
        and package.get("contract_version") == "hv_balanced_dth60_coinglass_phase9as_proposal_package_body.v1"
        and package.get("proposal_mode")
        == "default_off_observe_only_live_supervisor_timer_path_shadow_readback_proposal"
        and package.get("proposal_written_under_proof_artifacts") is True
        and package.get("proposal_executes_anything") is False
        and package.get("dry_load_readback_executed") is False
        and package.get("timer_path_loaded") is False
        and package.get("supervisor_invoked") is False
        and package.get("remote_sync_performed") is False
        and boundaries.get("proof_artifacts_only") is True
        and boundaries.get("default_off_only") is True
        and boundaries.get("observe_only_shadow_artifacts_only") is True
        and boundaries.get("executor_input_must_remain_baseline_only") is True
        and boundaries.get("candidate_order_authority") == "disabled"
        and boundaries.get("live_order_submission_authorized") is False
        and boundaries.get("dry_load_readback_execution_authorized") is False
        and authorizations.get("prepare_proposal_package") is True
        and authorizations.get("dry_load_readback_execution") is False
        and authorizations.get("timer_path_load") is False
        and authorizations.get("live_order_submission") is False
    )


def p9at_ready_for_p9au(summary: dict[str, Any], review: dict[str, Any], checklist: dict[str, Any]) -> bool:
    verdict = dict(review.get("verdict") or {})
    checks = dict(checklist.get("checks") or {})
    return (
        summary.get("contract_version") == "hv_balanced_dth60_coinglass_phase9at_retained_readiness_review.v1"
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9at_retained_readiness_review_ready") is True
        and summary.get("p9as_proposal_package_ready") is True
        and summary.get("eligible_for_future_dry_load_readback_owner_gate_request") is True
        and summary.get("allowed_next_gate") == P9AU_GATE
        and summary.get("dry_load_readback_execution_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and zero_orders_fills(summary)
        and no_live_mutation(summary)
        and review.get("contract_version") == "hv_balanced_dth60_coinglass_phase9at_readiness_review.v1"
        and review.get("review_mode") == "local_retained_evidence_readiness_review_not_timer_path"
        and review.get("reviewed_only_retained_evidence") is True
        and review.get("entered_timer_path") is False
        and review.get("dry_load_executed") is False
        and review.get("supervisor_run") is False
        and review.get("executor_input_mutated") is False
        and review.get("live_config_mutated") is False
        and review.get("target_plan_replaced") is False
        and review.get("remote_sync_performed") is False
        and int_equals(review, "orders_submitted", 0)
        and int_equals(review, "fill_count", 0)
        and verdict.get("ready_for_future_owner_default_off_dry_load_gate") is True
        and verdict.get("future_gate_required_before_any_dry_load_readback") is True
        and verdict.get("future_gate_must_keep_executor_baseline_only") is True
        and verdict.get("future_gate_must_keep_order_authority_disabled") is True
        and all(value is True for value in checks.values())
    )


def build_p9as(
    args: argparse.Namespace,
    *,
    started_at: datetime,
    run_id: str,
) -> tuple[dict[str, Any], int]:
    root = phase_root(args, P9AS_PARENT, "p9as_proposal_package", run_id)
    proof_root = root / "proof_artifacts" / "p9as" / run_id
    project_profile_path = resolve_path(args.project_profile)
    p9ar_path = (
        resolve_path(args.phase9ar_summary)
        if str(args.phase9ar_summary).strip()
        else latest_match(PHASE9AR_PARENT, "*/summary.json")
    )
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_path = resolve_path(args.live_config_dir)
    project_profile = load_optional(project_profile_path)
    p9ar = load_optional(p9ar_path)
    opening_path = source_output_path(p9ar, "proposal_preparation_gate_opening")
    p9ar_matrix_path = source_output_path(p9ar, "non_authorization_matrix")
    opening = load_optional(opening_path)
    p9ar_matrix = load_optional(p9ar_matrix_path)
    hook_sha = file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else ""
    supervisor_sha_before = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    config_sha_before = tree_sha256(live_config_path)
    supervisor_loads = current_supervisor_loads_hook(supervisor_path)
    p9ar_ok = p9ar_ready_for_p9as(
        p9ar,
        opening,
        p9ar_matrix,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads,
    )
    source_evidence = {
        "project_profile": evidence_file(project_profile_path),
        "phase9ar_summary": evidence_file(p9ar_path),
        "phase9ar_gate_opening": evidence_file(opening_path),
        "phase9ar_non_authorization_matrix": evidence_file(p9ar_matrix_path),
        "hook_module": evidence_file(hook_path),
        "live_supervisor": evidence_file(supervisor_path),
        "live_config_dir": {"path": str(live_config_path), "exists": live_config_path.exists(), "sha256": config_sha_before},
    }
    decision = owner_decision(
        phase="phase9as",
        owner=args.owner,
        source=args.owner_decision_source,
        started_at=started_at,
        decision=args.owner_decision,
        question="prepare_default_off_observe_only_proposal_package_under_proof_artifacts_only",
        effect="write_proposal_package_without_dry_load_readback_or_timer_path_execution",
        allow_key="proposal_package_preparation_approved",
    )
    package = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9as_proposal_package_body.v1",
        "run_id": run_id,
        "source_evidence": source_evidence,
        "owner_decision": decision,
        "proposal_mode": "default_off_observe_only_live_supervisor_timer_path_shadow_readback_proposal",
        "proposal_written_under_proof_artifacts": True,
        "proposal_executes_anything": False,
        "default_enabled": False,
        "observe_only": True,
        "candidate_shadow_only": True,
        "executor_target_source": "baseline_only",
        "candidate_artifact_sink": "proof_artifacts_only",
        "dry_load_readback_executed": False,
        "timer_path_loaded": False,
        "supervisor_invoked": False,
        "remote_sync_performed": False,
        "proposed_future_gate": P9AV_GATE,
        "required_intermediate_owner_gate": P9AU_GATE,
        "required_boundaries": {
            "proof_artifacts_only": True,
            "default_off_only": True,
            "observe_only_shadow_artifacts_only": True,
            "executor_input_must_remain_baseline_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "candidate_order_authority": "disabled",
            "live_order_submission_authorized": False,
            "dry_load_readback_execution_authorized": False,
            "live_timer_path_load_authorized": False,
            "remote_sync_authorized": False,
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
        },
        "authorizations": {
            "prepare_proposal_package": args.owner_decision == APPROVE_CORRIDOR_DECISION,
            "dry_load_readback_execution": False,
            "timer_path_load": False,
            "supervisor_invocation": False,
            "remote_sync": False,
            "candidate_execution": False,
            "live_order_submission": False,
        },
    }
    supervisor_sha_after = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    config_sha_after = tree_sha256(live_config_path)
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9as_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "proposal_package_generation_only",
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_config_dir_sha256_before": config_sha_before,
        "live_config_dir_sha256_after": config_sha_after,
        "live_config_dir_unchanged": config_sha_before == config_sha_after,
        "entered_timer_path": False,
        "dry_load_readback_executed": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "remote_control_plane_touched": False,
        "candidate_execution_performed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    gates = {
        "owner_decision_p9as_p9au_corridor": args.owner_decision == APPROVE_CORRIDOR_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9ar_gate_opening_ready": p9ar_ok,
        "p9ar_allows_p9as": p9ar.get("allowed_next_gate") == P9AS_GATE,
        "current_live_supervisor_not_loading_hook": supervisor_loads is False,
        "current_hook_hash_matches_p9ar_source": dict(dict(p9ar.get("source_evidence") or {}).get("hook_module") or {}).get("sha256")
        == hook_sha,
        "current_supervisor_hash_matches_p9ar_source": dict(dict(p9ar.get("source_evidence") or {}).get("live_supervisor") or {}).get("sha256")
        == supervisor_sha_before,
        "current_live_config_hash_matches_p9ar_source": dict(dict(p9ar.get("source_evidence") or {}).get("live_config_dir") or {}).get("sha256")
        == config_sha_before,
        "proposal_package_output_under_proof_artifacts": output_under_proof_artifacts(proof_root / "proposal_review_package.json"),
        "p9as_generates_package_only": True,
        "p9as_does_not_write_live_config": True,
        "p9as_does_not_execute_dry_load_readback": True,
        "p9as_does_not_enter_timer_path": True,
        "p9as_does_not_run_supervisor": True,
        "p9as_does_not_remote_sync": True,
        "p9as_does_not_mutate_executor_input": True,
        "p9as_does_not_replace_target_plan": True,
        "p9as_keeps_order_authority_disabled": True,
        "zero_orders_fills_in_p9as": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    summary = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9as_proposal_package.v1",
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "gate_scope": "p9as_prepare_proof_artifacts_only_proposal_package",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9as_proposal_package_ready": status == "ready",
        "generated_proposal_package": status == "ready",
        "prepare_proposal_authorized": status == "ready",
        "proposal_package_generation_authorized": status == "ready",
        "proposal_body_write_authorized": False,
        "execute_proposal_authorized": False,
        "allowed_next_gate": P9AT_GATE if status == "ready" else "",
        "recommended_next_gate": P9AT_GATE if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": False,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_supervisor_source_unchanged": control["live_supervisor_source_unchanged"],
        "live_config_dir_unchanged": control["live_config_dir_unchanged"],
        "gates": gates,
        "blockers": blockers,
        **common_execution_boundary(),
        "proof_root": str(proof_root),
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "proposal_review_package": str(proof_root / "proposal_review_package.json"),
            "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        },
    }
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9as_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "prepare_proposal_package": status == "ready",
            "proposal_body_write": False,
            "dry_load_readback_execution": False,
            "candidate_execution": False,
            "candidate_live_order_submission": False,
            "timer_hook_implementation": False,
            "hook_deployment": False,
            "live_timer_path_load": False,
            "production_timer_service_load": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "remote_sync": False,
            "remote_execution": False,
            "supervisor_invocation": False,
            "supervisor_run": False,
            "stage_governance_change": False,
        },
    }
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "proposal_review_package.json", package)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix)
    write_json(proof_root / "control_boundary_readback.json", control)
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def build_p9at(
    args: argparse.Namespace,
    *,
    started_at: datetime,
    run_id: str,
    p9as_summary: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    root = phase_root(args, P9AT_PARENT, "p9at_retained_readiness_review", run_id)
    proof_root = root / "proof_artifacts" / "p9at" / run_id
    package_path = source_output_path(p9as_summary, "proposal_review_package")
    package = load_optional(package_path)
    project_profile = load_optional(resolve_path(args.project_profile))
    supervisor_path = resolve_path(args.supervisor)
    live_config_path = resolve_path(args.live_config_dir)
    supervisor_sha_before = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    config_sha_before = tree_sha256(live_config_path)
    supervisor_loads = current_supervisor_loads_hook(supervisor_path)
    p9as_ok = p9as_ready_for_p9at(p9as_summary, package)
    source_evidence = {
        "project_profile": evidence_file(resolve_path(args.project_profile)),
        "phase9as_summary": evidence_file(source_output_path(p9as_summary, "summary")),
        "phase9as_proposal_review_package": evidence_file(package_path),
        "hook_module": evidence_file(resolve_path(args.hook_module)),
        "live_supervisor": evidence_file(supervisor_path),
        "live_config_dir": {"path": str(live_config_path), "exists": live_config_path.exists(), "sha256": config_sha_before},
    }
    decision = owner_decision(
        phase="phase9at",
        owner=args.owner,
        source=args.owner_decision_source,
        started_at=started_at,
        decision=args.owner_decision,
        question="run_local_retained_evidence_readiness_review_only",
        effect="review_proposal_package_without_dry_load_readback_or_timer_path_execution",
        allow_key="retained_readiness_review_approved",
    )
    review = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9at_readiness_review.v1",
        "run_id": run_id,
        "source_evidence": source_evidence,
        "owner_decision": decision,
        "review_mode": "local_retained_evidence_readiness_review_not_timer_path",
        "reviewed_only_retained_evidence": True,
        "entered_timer_path": False,
        "dry_load_executed": False,
        "supervisor_run": False,
        "executor_input_mutated": False,
        "live_config_mutated": False,
        "target_plan_replaced": False,
        "remote_sync_performed": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "verdict": {
            "ready_for_future_owner_default_off_dry_load_gate": True,
            "future_gate_required_before_any_dry_load_readback": True,
            "future_gate_must_stay_default_off": True,
            "future_gate_must_keep_executor_baseline_only": True,
            "future_gate_must_keep_order_authority_disabled": True,
        },
    }
    checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9at_readiness_checklist.v1",
        "run_id": run_id,
        "checks": {
            "reviewed_retained_p9as_package": p9as_ok,
            "proposal_package_under_proof_artifacts": output_under_proof_artifacts(package_path),
            "proposal_does_not_execute_anything": package.get("proposal_executes_anything") is False,
            "proposal_default_off": package.get("default_enabled") is False,
            "proposal_observe_only": package.get("observe_only") is True,
            "proposal_keeps_executor_baseline_only": dict(package.get("required_boundaries") or {}).get(
                "executor_input_must_remain_baseline_only"
            )
            is True,
            "proposal_keeps_order_authority_disabled": dict(package.get("required_boundaries") or {}).get(
                "candidate_order_authority"
            )
            == "disabled",
            "timer_path_not_entered": True,
            "dry_load_readback_not_executed": True,
            "supervisor_not_run": True,
            "remote_not_touched": True,
            "executor_input_not_mutated": True,
            "live_config_not_mutated": True,
            "target_plan_not_replaced": True,
            "zero_orders_fills": True,
        },
    }
    supervisor_sha_after = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    config_sha_after = tree_sha256(live_config_path)
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9at_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "local_retained_evidence_readiness_review_only",
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_config_dir_sha256_before": config_sha_before,
        "live_config_dir_sha256_after": config_sha_after,
        "live_config_dir_unchanged": config_sha_before == config_sha_after,
        "entered_timer_path": False,
        "dry_load_readback_executed": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "remote_control_plane_touched": False,
        "candidate_execution_performed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    gates = {
        "owner_decision_p9as_p9au_corridor": args.owner_decision == APPROVE_CORRIDOR_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9as_proposal_package_ready": p9as_ok,
        "proposal_package_under_proof_artifacts": output_under_proof_artifacts(package_path),
        "readiness_review_output_under_proof_artifacts": output_under_proof_artifacts(proof_root / "readiness_review.json"),
        "current_live_supervisor_not_loading_hook": supervisor_loads is False,
        "timer_path_not_entered": True,
        "dry_load_readback_not_executed": True,
        "supervisor_not_run": True,
        "remote_not_touched": True,
        "executor_input_not_mutated": True,
        "live_config_not_mutated": True,
        "target_plan_not_replaced": True,
        "zero_orders_fills_in_p9at": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    summary = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9at_retained_readiness_review.v1",
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "gate_scope": "p9at_local_retained_evidence_readiness_review_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9at_retained_readiness_review_ready": status == "ready",
        "p9as_proposal_package_ready": p9as_ok,
        "eligible_for_future_dry_load_readback_owner_gate_request": status == "ready",
        "allowed_next_gate": P9AU_GATE if status == "ready" else "",
        "recommended_next_gate": P9AU_GATE if status == "ready" else "",
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_supervisor_source_unchanged": control["live_supervisor_source_unchanged"],
        "live_config_dir_unchanged": control["live_config_dir_unchanged"],
        "gates": gates,
        "blockers": blockers,
        **common_execution_boundary(),
        "proof_root": str(proof_root),
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "readiness_review": str(proof_root / "readiness_review.json"),
            "readiness_checklist": str(proof_root / "readiness_checklist.json"),
            "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        },
    }
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9at_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "retained_readiness_review": status == "ready",
            "dry_load_readback_execution": False,
            "candidate_execution": False,
            "candidate_live_order_submission": False,
            "timer_hook_implementation": False,
            "hook_deployment": False,
            "live_timer_path_load": False,
            "production_timer_service_load": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "remote_sync": False,
            "remote_execution": False,
            "supervisor_invocation": False,
            "supervisor_run": False,
            "stage_governance_change": False,
        },
    }
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "readiness_review.json", review)
    write_json(proof_root / "readiness_checklist.json", checklist)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix)
    write_json(proof_root / "control_boundary_readback.json", control)
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def build_p9au(
    args: argparse.Namespace,
    *,
    started_at: datetime,
    run_id: str,
    p9at_summary: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    root = phase_root(args, P9AU_PARENT, "p9au_allow_dry_load_readback_owner_gate", run_id)
    proof_root = root / "proof_artifacts" / "p9au" / run_id
    review_path = source_output_path(p9at_summary, "readiness_review")
    checklist_path = source_output_path(p9at_summary, "readiness_checklist")
    review = load_optional(review_path)
    checklist = load_optional(checklist_path)
    project_profile = load_optional(resolve_path(args.project_profile))
    supervisor_path = resolve_path(args.supervisor)
    live_config_path = resolve_path(args.live_config_dir)
    supervisor_sha_before = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    config_sha_before = tree_sha256(live_config_path)
    supervisor_loads = current_supervisor_loads_hook(supervisor_path)
    p9at_ok = p9at_ready_for_p9au(p9at_summary, review, checklist)
    source_evidence = {
        "project_profile": evidence_file(resolve_path(args.project_profile)),
        "phase9at_summary": evidence_file(source_output_path(p9at_summary, "summary")),
        "phase9at_readiness_review": evidence_file(review_path),
        "phase9at_readiness_checklist": evidence_file(checklist_path),
        "hook_module": evidence_file(resolve_path(args.hook_module)),
        "live_supervisor": evidence_file(supervisor_path),
        "live_config_dir": {"path": str(live_config_path), "exists": live_config_path.exists(), "sha256": config_sha_before},
    }
    decision = owner_decision(
        phase="phase9au",
        owner=args.owner,
        source=args.owner_decision_source,
        started_at=started_at,
        decision=args.owner_decision,
        question="allow_future_default_off_observe_only_dry_load_readback_gate_request_only",
        effect="allow_future_p9av_request_without_executing_dry_load_readback",
        allow_key="future_dry_load_readback_gate_request_approved",
    )
    permission = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9au_dry_load_readback_gate_permission.v1",
        "run_id": run_id,
        "source_evidence": source_evidence,
        "owner_decision": decision,
        "allowed_next_gate": P9AV_GATE if p9at_ok and args.owner_decision == APPROVE_CORRIDOR_DECISION else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "dry_load_readback_executed_in_p9au": False,
        "timer_path_loaded_in_p9au": False,
        "supervisor_invoked_in_p9au": False,
        "required_boundaries_for_next_gate": {
            "owner_gated": True,
            "proof_artifacts_only": True,
            "default_off_only": True,
            "observe_only_shadow_artifacts_only": True,
            "executor_input_must_remain_baseline_only": True,
            "candidate_order_authority": "disabled",
            "live_order_submission_authorized": False,
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
        },
    }
    supervisor_sha_after = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    config_sha_after = tree_sha256(live_config_path)
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9au_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "allow_future_dry_load_readback_gate_request_only",
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_config_dir_sha256_before": config_sha_before,
        "live_config_dir_sha256_after": config_sha_after,
        "live_config_dir_unchanged": config_sha_before == config_sha_after,
        "entered_timer_path": False,
        "dry_load_readback_executed": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "remote_control_plane_touched": False,
        "candidate_execution_performed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    gates = {
        "owner_decision_p9as_p9au_corridor": args.owner_decision == APPROVE_CORRIDOR_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9at_retained_readiness_review_ready": p9at_ok,
        "p9at_allows_p9au": p9at_summary.get("allowed_next_gate") == P9AU_GATE,
        "permission_output_under_proof_artifacts": output_under_proof_artifacts(proof_root / "dry_load_readback_gate_permission.json"),
        "current_live_supervisor_not_loading_hook": supervisor_loads is False,
        "p9au_discusses_future_p9av_only": True,
        "p9au_does_not_execute_dry_load_readback": True,
        "p9au_does_not_enter_timer_path": True,
        "p9au_does_not_run_supervisor": True,
        "p9au_does_not_remote_sync": True,
        "p9au_does_not_mutate_executor_input": True,
        "p9au_does_not_replace_target_plan": True,
        "p9au_keeps_order_authority_disabled": True,
        "zero_orders_fills_in_p9au": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    summary = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9au_allow_dry_load_readback_owner_gate.v1",
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "gate_scope": "p9au_allow_future_dry_load_readback_gate_request_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9au_allow_future_dry_load_readback_gate_ready": status == "ready",
        "eligible_for_future_dry_load_readback_execution_gate_request": status == "ready",
        "allowed_next_gate": P9AV_GATE if status == "ready" else "",
        "recommended_next_gate": P9AV_GATE if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "dry_load_readback_execution_gate_opened": False,
        "dry_load_readback_execution_authorized_in_p9au": False,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_supervisor_source_unchanged": control["live_supervisor_source_unchanged"],
        "live_config_dir_unchanged": control["live_config_dir_unchanged"],
        "gates": gates,
        "blockers": blockers,
        **common_execution_boundary(),
        "proof_root": str(proof_root),
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "dry_load_readback_gate_permission": str(proof_root / "dry_load_readback_gate_permission.json"),
            "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        },
    }
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9au_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "future_dry_load_readback_gate_request": status == "ready",
            "dry_load_readback_execution": False,
            "candidate_execution": False,
            "candidate_live_order_submission": False,
            "timer_hook_implementation": False,
            "hook_deployment": False,
            "live_timer_path_load": False,
            "production_timer_service_load": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "remote_sync": False,
            "remote_execution": False,
            "supervisor_invocation": False,
            "supervisor_run": False,
            "stage_governance_change": False,
        },
    }
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "dry_load_readback_gate_permission.json", permission)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix)
    write_json(proof_root / "control_boundary_readback.json", control)
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def build_corridor(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    p9as, p9as_code = build_p9as(args, started_at=started_at, run_id=run_id)
    p9at: dict[str, Any] = {"status": "skipped", "blockers": ["p9as_not_ready"], "output_files": {}}
    p9au: dict[str, Any] = {"status": "skipped", "blockers": ["p9at_not_ready"], "output_files": {}}
    p9at_code = 2
    p9au_code = 2
    if p9as_code == 0:
        p9at, p9at_code = build_p9at(args, started_at=started_at + timedelta(seconds=1), run_id=run_id, p9as_summary=p9as)
    if p9at_code == 0:
        p9au, p9au_code = build_p9au(args, started_at=started_at + timedelta(seconds=2), run_id=run_id, p9at_summary=p9at)
    status = "ready" if p9as_code == p9at_code == p9au_code == 0 else "blocked"
    root = resolve_path(args.output_root) if str(args.output_root).strip() else phase_root(args, CORRIDOR_PARENT, "p9as_p9au_proof_only_corridor", run_id)
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "authorized_corridor": "P9AS_P9AT_P9AU_proof_only",
        "p9as_status": p9as.get("status"),
        "p9at_status": p9at.get("status"),
        "p9au_status": p9au.get("status"),
        "hard_stop_before": [
            "dry_load_readback_execution",
            "remote_sync",
            "live_timer_path_load",
            "supervisor_run",
            "executor_input_mutation",
            "target_plan_replacement",
            "operator_state_mutation",
            "stage_governance_change",
            "live_order_submission",
        ],
        "dry_load_readback_execution_authorized": False,
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
            "corridor_summary": str(root / "summary.json"),
            "p9as_summary": dict(p9as.get("output_files") or {}).get("summary", ""),
            "p9at_summary": dict(p9at.get("output_files") or {}).get("summary", ""),
            "p9au_summary": dict(p9au.get("output_files") or {}).get("summary", ""),
        },
        "blockers": list(p9as.get("blockers") or []) + list(p9at.get("blockers") or []) + list(p9au.get("blockers") or []),
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_corridor(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['outputs']['corridor_summary']}")
    print(f"p9as_summary={summary['outputs']['p9as_summary']}")
    print(f"p9at_summary={summary['outputs']['p9at_summary']}")
    print(f"p9au_summary={summary['outputs']['p9au_summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
