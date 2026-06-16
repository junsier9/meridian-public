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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bo_prepare_timer_path_shadow_cycles_proposal import (  # noqa: E402
    APPROVE_P9BO_DECISION,
    CONTRACT_VERSION as P9BO_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9BO_PARENT,
    FALSE_RUNTIME_KEYS as P9BO_FALSE_RUNTIME_KEYS,
    P9BP_GATE,
    P9BP_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    current_supervisor_loads_hook,
    evidence_file,
    file_sha256,
    latest_match,
    load_optional,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9bp_owner_gate_timer_path_shadow_cycles.v1"
APPROVE_P9BP_DECISION = (
    "approve_p9bp_allow_continuous_real_timer_path_shadow_cycles_no_order_only"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_p9bp_owner_gate_timer_path_shadow_cycles"
)
P9BQ_GATE = (
    "P9BQ_execute_at_least_3_continuous_real_timer_path_shadow_cycles_no_order_"
    "only_if_separately_requested"
)
P9BQ_SCOPE = (
    "execute_at_least_3_continuous_real_timer_path_shadow_cycles_default_off_"
    "observe_only_baseline_executor_candidate_shadow_no_order"
)

FALSE_CURRENT_RUNTIME_KEYS = (
    "continuous_timer_path_shadow_cycles_execution_authorized",
    "continuous_timer_path_shadow_cycles_executed",
    "continuous_timer_path_shadow_cycles_executed_in_p9bp",
    "execute_cycles_inside_p9bp_authorized",
    "timer_path_shadow_readback_execution_authorized",
    "timer_path_shadow_readback_authorized",
    "dry_load_readback_execution_authorized",
    "timer_hook_implementation_authorized",
    "hook_deployment_authorized",
    "timer_path_load_authorized",
    "timer_path_load_authorized_in_p9bp",
    "supervisor_invocation_authorized",
    "supervisor_invocation_authorized_in_p9bp",
    "supervisor_run_authorized",
    "supervisor_run_authorized_in_p9bp",
    "remote_sync_authorized",
    "remote_sync_authorized_in_p9bp",
    "remote_execution_authorized",
    "remote_execution_authorized_in_p9bp",
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
    "entered_timer_path",
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9BP: an owner gate that allows a future separately requested "
            "P9BQ execution gate for at least three continuous real timer-path "
            "shadow cycles. P9BP itself does not execute cycles, enter timer path, "
            "invoke the supervisor, remote sync, execute the candidate, mutate "
            "live state or executor input, replace target plans, or authorize live "
            "orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9bo-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BP_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9bp_allow_continuous_timer_path_shadow_cycles_no_order_only",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_p9bo_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bo_summary).strip():
        return resolve_path(args.phase9bo_summary)
    return latest_match(P9BO_PARENT, "*/summary.json")


def all_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def authorizations_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    authorizations = dict(payload.get("authorizations") or {})
    return all(authorizations.get(key) is False for key in keys)


def p9bo_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    return {
        "owner_decision_record": source_output_path(summary, "owner_decision_record"),
        "proposal_review_package": source_output_path(summary, "proposal_review_package"),
        "acceptance_contract": source_output_path(summary, "acceptance_contract"),
        "review_checklist": source_output_path(summary, "review_checklist"),
        "non_authorization_matrix": source_output_path(summary, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(summary, "control_boundary_readback"),
    }


def acceptance_contract_ready(acceptance: dict[str, Any]) -> bool:
    return (
        acceptance.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bo_acceptance_contract.v1"
        and acceptance.get("future_gate") == P9BP_GATE
        and acceptance.get("future_gate_scope") == P9BP_SCOPE
        and acceptance.get("future_gate_must_be_separately_requested") is True
        and int(acceptance.get("minimum_cycle_count") or 0) >= 3
        and acceptance.get("cycles_must_be_continuous") is True
        and acceptance.get("cycles_must_share_same_no_order_config") is True
        and acceptance.get("cycles_must_use_real_live_supervisor_timer_path") is True
        and acceptance.get("fresh_proof_each_cycle") is True
        and acceptance.get("same_risk_inputs_as_baseline_plan_each_cycle") is True
        and acceptance.get("baseline_only_executor_input_each_cycle") is True
        and acceptance.get("candidate_shadow_only_each_cycle") is True
        and acceptance.get("candidate_artifacts_under_proof_artifacts_only_each_cycle") is True
        and acceptance.get("candidate_plan_must_not_be_referenced_by_executor_each_cycle") is True
        and acceptance.get("target_plan_must_not_be_replaced_each_cycle") is True
        and acceptance.get("executor_input_must_not_change_each_cycle") is True
        and acceptance.get("zero_order_delta_each_cycle") is True
        and acceptance.get("zero_cancel_delta_each_cycle") is True
        and acceptance.get("zero_fill_delta_each_cycle") is True
        and acceptance.get("zero_trade_delta_each_cycle") is True
        and acceptance.get("live_config_must_not_change") is True
        and acceptance.get("operator_state_must_not_change") is True
        and acceptance.get("timer_state_must_not_change") is True
        and acceptance.get("candidate_order_authority") == "disabled"
        and acceptance.get("live_order_submission_authorized") is False
        and acceptance.get("candidate_execution_authorized") is False
    )


def p9bo_ready_for_p9bp(
    summary: dict[str, Any],
    owner: dict[str, Any],
    package: dict[str, Any],
    acceptance: dict[str, Any],
    checklist: dict[str, Any],
    matrix: dict[str, Any],
    control: dict[str, Any],
    paths: dict[str, Path],
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
    package_acceptance = dict(package.get("acceptance_contract") or {})
    checks = dict(checklist.get("checks") or {})
    authorizations = dict(matrix.get("authorizations") or {})
    forbidden = (
        "continuous_timer_path_shadow_cycles_execution",
        "timer_path_shadow_readback_execution",
        "supervisor_invocation",
        "supervisor_run",
        "remote_sync",
        "remote_execution",
        "candidate_execution",
        "candidate_live_order_submission",
        "live_order_submission",
        "target_plan_replacement",
        "executor_input_mutation",
        "live_config_mutation",
        "operator_state_mutation",
        "timer_or_service_mutation",
        "production_timer_service_load",
        "stage_governance_change",
    )
    return (
        summary.get("contract_version") == P9BO_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9bo_proposal_review_package_ready") is True
        and summary.get("proposal_review_package_prepared") is True
        and summary.get("proposal_review_package_under_proof_artifacts") is True
        and summary.get("eligible_for_future_p9bp_owner_gate_request") is True
        and summary.get("allowed_next_gate") == P9BP_GATE
        and summary.get("allowed_next_gate_scope") == P9BP_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and all_false(summary, P9BO_FALSE_RUNTIME_KEYS)
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_overlay_execution_path") == "shadow_only_not_executor"
        and summary.get("candidate_artifact_sink") == "proof_artifacts_only"
        and summary.get("executor_consumes_baseline_only") is True
        and summary.get("candidate_plan_referenced_by_executor") is False
        and zero_orders_fills(summary)
        and owner.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bo_owner_decision.v1"
        and owner.get("decision") == APPROVE_P9BO_DECISION
        and owner.get("proposal_review_package_preparation_approved") is True
        and owner.get("future_continuous_timer_path_shadow_cycles_owner_gate_discussion_approved")
        is True
        and owner.get("continuous_timer_path_shadow_cycles_execution_approved") is False
        and owner.get("timer_path_shadow_readback_execution_approved") is False
        and owner.get("supervisor_invocation_approved") is False
        and owner.get("candidate_execution_approved") is False
        and owner.get("live_order_submission_approved") is False
        and package.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bo_proposal_review_package.v1"
        and package.get("package_prepared") is True
        and package.get("package_sink") == "proof_artifacts_only"
        and package.get("proposed_future_gate") == P9BP_GATE
        and package.get("proposed_future_gate_scope") == P9BP_SCOPE
        and package.get("proposed_future_gate_must_be_separately_requested") is True
        and package.get("execution_authorized_in_p9bo") is False
        and package.get("supervisor_invocation_authorized_in_p9bo") is False
        and package.get("remote_sync_authorized_in_p9bo") is False
        and package.get("candidate_execution_authorized_in_p9bo") is False
        and package.get("live_order_submission_authorized_in_p9bo") is False
        and acceptance_contract_ready(acceptance)
        and acceptance_contract_ready(package_acceptance)
        and checklist.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bo_review_checklist.v1"
        and all(value is True for value in checks.values())
        and matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bo_non_authorization_matrix.v1"
        and authorizations.get("proposal_review_package_preparation") is True
        and authorizations.get("future_continuous_timer_path_shadow_cycles_owner_gate_discussion")
        is True
        and authorizations_false(matrix, forbidden)
        and control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bo_control_boundary_readback.v1"
        and control.get("live_supervisor_source_unchanged") is True
        and control.get("live_supervisor_loads_candidate_hook") is False
        and control.get("live_config_dir_unchanged") is True
        and all_false(control, P9BO_FALSE_RUNTIME_KEYS)
        and zero_orders_fills(control)
        and all(path.exists() for path in paths.values() if str(path))
        and output_under_proof_artifacts(paths["proposal_review_package"])
        and output_under_proof_artifacts(paths["acceptance_contract"])
        and output_under_proof_artifacts(paths["review_checklist"])
        and output_under_proof_artifacts(paths["non_authorization_matrix"])
        and output_under_proof_artifacts(paths["control_boundary_readback"])
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9BP_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bp_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "allow_future_continuous_real_timer_path_shadow_cycles_no_order_only",
        "decision_effect": "allow_future_p9bq_continuous_shadow_cycles_no_order_only"
        if approved
        else "none",
        "future_continuous_timer_path_shadow_cycles_execution_approved": approved,
        "p9bq_execution_gate_approved": approved,
        "execute_cycles_inside_p9bp_approved": False,
        "timer_path_shadow_readback_execution_inside_p9bp_approved": False,
        "supervisor_invocation_inside_p9bp_approved": False,
        "remote_sync_inside_p9bp_approved": False,
        "remote_execution_inside_p9bp_approved": False,
        "candidate_execution_approved": False,
        "candidate_live_order_submission_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "production_timer_service_load_approved": False,
        "repo_stage_change_approved": False,
    }


def p9bq_acceptance_contract(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bp_p9bq_acceptance_contract.v1",
        "run_id": run_id,
        "accepted_next_gate": P9BQ_GATE,
        "accepted_next_gate_scope": P9BQ_SCOPE,
        "p9bq_must_be_separately_requested": True,
        "minimum_cycle_count": 3,
        "cycles_must_be_continuous": True,
        "cycles_must_share_same_no_order_config": True,
        "cycles_must_use_real_live_supervisor_timer_path": True,
        "fresh_proof_each_cycle": True,
        "unique_timestamp_each_cycle": True,
        "same_risk_inputs_as_baseline_plan_each_cycle": True,
        "baseline_only_executor_input_each_cycle": True,
        "candidate_shadow_only_each_cycle": True,
        "candidate_artifacts_under_proof_artifacts_only_each_cycle": True,
        "candidate_plan_must_not_be_referenced_by_executor_each_cycle": True,
        "target_plan_must_not_be_replaced_each_cycle": True,
        "executor_input_must_not_change_each_cycle": True,
        "zero_order_delta_each_cycle": True,
        "zero_cancel_delta_each_cycle": True,
        "zero_fill_delta_each_cycle": True,
        "zero_trade_delta_each_cycle": True,
        "live_config_must_not_change": True,
        "operator_state_must_not_change": True,
        "timer_state_must_not_change": True,
        "production_timer_service_must_not_be_loaded_or_modified": True,
        "remote_control_boundary_must_not_change": True,
        "candidate_order_authority": "disabled",
        "executor_target_source": "baseline_only",
        "candidate_overlay_execution_path": "shadow_only_not_executor",
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "allowed_next_step_after_p9bq_success": "owner_retained_evidence_review_only",
    }


def execution_permission(
    *,
    run_id: str,
    ready: bool,
    decision: dict[str, Any],
    source_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bp_execution_permission.v1",
        "run_id": run_id,
        "permission_kind": "future_continuous_real_timer_path_shadow_cycles_no_order_only",
        "permission_ready": ready,
        "source_evidence": source_evidence,
        "owner_decision": decision,
        "allowed_next_gate": P9BQ_GATE if ready else "",
        "allowed_next_gate_scope": P9BQ_SCOPE if ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "continuous_timer_path_shadow_cycles_execution_authorized_for_future_gate": ready,
        "p9bq_execution_gate_authorized": ready,
        "execute_cycles_inside_p9bp": False,
        "default_off": True,
        "observe_only": True,
        "candidate_order_authority": "disabled",
        "executor_target_source": "baseline_only",
        "candidate_shadow_only": True,
        "candidate_plan_must_not_be_referenced_by_executor": True,
        "acceptance_contract": p9bq_acceptance_contract(run_id),
        "disallowed_in_p9bp": {
            "execute_cycles": True,
            "enter_timer_path": True,
            "invoke_supervisor": True,
            "remote_sync": True,
            "remote_execution": True,
            "execute_candidate": True,
            "mutate_executor_input": True,
            "replace_target_plan": True,
            "mutate_live_config": True,
            "mutate_operator_state": True,
            "mutate_timer_or_service_state": True,
            "enable_production_timer_service": True,
            "submit_orders": True,
            "stage_governance_change": True,
        },
    }


def non_authorization_matrix(run_id: str, ready: bool) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bp_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "future_continuous_timer_path_shadow_cycles_execution": ready,
            "p9bq_execution_gate": ready,
            "execute_cycles_inside_p9bp": False,
            "timer_path_shadow_readback_execution_inside_p9bp": False,
            "supervisor_invocation_inside_p9bp": False,
            "supervisor_run_inside_p9bp": False,
            "remote_sync_inside_p9bp": False,
            "remote_execution_inside_p9bp": False,
            "candidate_execution": False,
            "candidate_live_order_submission": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "production_timer_service_load": False,
            "stage_governance_change": False,
        },
    }


def no_order_boundary(*, ready: bool, supervisor_loads_hook: bool) -> dict[str, Any]:
    payload = {
        "future_continuous_timer_path_shadow_cycles_execution_authorized": ready,
        "p9bq_execution_gate_authorized": ready,
        "real_live_supervisor_timer_path_allowed_for_future_gate": ready,
        "continuous_timer_path_shadow_cycles_execution_authorized_for_future_gate": ready,
        "candidate_order_authority": "disabled",
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "shadow_only_not_executor",
        "candidate_artifact_sink": "proof_artifacts_only_until_p9bq",
        "executor_consumes_baseline_only": True,
        "candidate_shadow_only": True,
        "candidate_plan_referenced_by_executor": False,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "fills_observed": 0,
        "trade_count": 0,
        "exchange_order_submission": "disabled",
    }
    for key in FALSE_CURRENT_RUNTIME_KEYS:
        payload[key] = False
    return payload


def build_p9bp(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9bp" / run_id

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9bo": latest_p9bo_summary(args),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
        "live_config_dir": resolve_path(args.live_config_dir),
    }
    project_profile = load_optional(paths["project_profile"])
    p9bo = load_optional(paths["phase9bo"])
    p9bo_paths = p9bo_output_paths(p9bo)
    p9bo_owner = load_optional(p9bo_paths["owner_decision_record"])
    p9bo_package = load_optional(p9bo_paths["proposal_review_package"])
    p9bo_acceptance = load_optional(p9bo_paths["acceptance_contract"])
    p9bo_checklist = load_optional(p9bo_paths["review_checklist"])
    p9bo_matrix = load_optional(p9bo_paths["non_authorization_matrix"])
    p9bo_control = load_optional(p9bo_paths["control_boundary_readback"])

    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_before = tree_sha256(paths["live_config_dir"])
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    supervisor_sha_after = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_after = tree_sha256(paths["live_config_dir"])

    decision = owner_decision_record(args, generated_at)
    p9bo_ok = p9bo_ready_for_p9bp(
        p9bo,
        p9bo_owner,
        p9bo_package,
        p9bo_acceptance,
        p9bo_checklist,
        p9bo_matrix,
        p9bo_control,
        p9bo_paths,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9bo_summary": evidence_file(paths["phase9bo"]),
        "phase9bo_owner_decision_record": evidence_file(p9bo_paths["owner_decision_record"]),
        "phase9bo_proposal_review_package": evidence_file(p9bo_paths["proposal_review_package"]),
        "phase9bo_acceptance_contract": evidence_file(p9bo_paths["acceptance_contract"]),
        "phase9bo_review_checklist": evidence_file(p9bo_paths["review_checklist"]),
        "phase9bo_non_authorization_matrix": evidence_file(p9bo_paths["non_authorization_matrix"]),
        "phase9bo_control_boundary_readback": evidence_file(p9bo_paths["control_boundary_readback"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
        "live_config_dir": {
            "path": str(paths["live_config_dir"]),
            "exists": paths["live_config_dir"].exists(),
            "sha256": live_config_sha_before,
        },
    }
    owner_ok = str(args.owner_decision) == APPROVE_P9BP_DECISION
    gates = {
        "owner_decision_p9bp_allow_future_continuous_cycles_no_order_only": owner_ok,
        "project_stage_boundary_preserved": project_profile.get("current_stage")
        == "stage_1_research_readiness_only",
        "p9bo_proposal_review_package_ready_for_p9bp": p9bo_ok,
        "p9bo_allows_p9bp_only": p9bo.get("allowed_next_gate") == P9BP_GATE
        and p9bo.get("eligible_for_future_p9bp_owner_gate_request") is True,
        "p9bo_required_separate_request": p9bo.get("allowed_next_gate_must_be_separately_requested")
        is True,
        "p9bo_acceptance_contract_requires_three_cycles": acceptance_contract_ready(
            p9bo_acceptance
        ),
        "current_live_supervisor_not_already_loading_hook": supervisor_loads_hook is False,
        "current_hook_hash_matches_p9bo_source": dict(
            dict(p9bo.get("source_evidence") or {}).get("hook_module") or {}
        ).get("sha256")
        == hook_sha,
        "current_supervisor_hash_matches_p9bo_source": dict(
            dict(p9bo.get("source_evidence") or {}).get("live_supervisor") or {}
        ).get("sha256")
        == supervisor_sha_before,
        "current_live_config_hash_matches_p9bo_source": dict(
            dict(p9bo.get("source_evidence") or {}).get("live_config_dir") or {}
        ).get("sha256")
        == live_config_sha_before,
        "execution_permission_output_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "execution_permission.json"
        ),
        "acceptance_contract_output_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "acceptance_contract.json"
        ),
        "control_boundary_source_unchanged": supervisor_sha_before == supervisor_sha_after
        and live_config_sha_before == live_config_sha_after,
        "p9bp_does_not_execute_cycles": True,
        "p9bp_does_not_enter_timer_path": True,
        "p9bp_does_not_run_supervisor": True,
        "p9bp_does_not_remote_sync": True,
        "p9bp_does_not_mutate_executor_input": True,
        "p9bp_does_not_replace_target_plan": True,
        "p9bp_does_not_mutate_live_config": True,
        "p9bp_does_not_mutate_operator_state": True,
        "p9bp_does_not_mutate_timer_state": True,
        "p9bp_keeps_live_order_submission_disabled": True,
        "p9bq_must_be_separately_requested": True,
        "p9bq_must_remain_no_order": True,
        "zero_orders_fills_in_p9bp": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    ready = status == "ready"
    permission = execution_permission(
        run_id=run_id,
        ready=ready,
        decision=decision,
        source_evidence=source_evidence,
    )
    acceptance = p9bq_acceptance_contract(run_id)
    checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bp_acceptance_checklist.v1",
        "run_id": run_id,
        "checks": {
            "p9bo_status_ready": p9bo.get("status") == "ready",
            "p9bo_blockers_empty": not p9bo.get("blockers"),
            "p9bo_proposal_package_ready": p9bo.get("p9bo_proposal_review_package_ready")
            is True,
            "p9bo_acceptance_contract_ready": acceptance_contract_ready(p9bo_acceptance),
            "future_gate_requires_at_least_three_cycles": acceptance["minimum_cycle_count"] >= 3,
            "future_gate_requires_fresh_proof_each_cycle": acceptance["fresh_proof_each_cycle"]
            is True,
            "future_gate_requires_same_risk_inputs": acceptance[
                "same_risk_inputs_as_baseline_plan_each_cycle"
            ]
            is True,
            "future_gate_requires_baseline_only_executor": acceptance[
                "baseline_only_executor_input_each_cycle"
            ]
            is True,
            "future_gate_requires_candidate_shadow_only": acceptance[
                "candidate_shadow_only_each_cycle"
            ]
            is True,
            "future_gate_requires_zero_order_cancel_fill_trade": (
                acceptance["zero_order_delta_each_cycle"]
                and acceptance["zero_cancel_delta_each_cycle"]
                and acceptance["zero_fill_delta_each_cycle"]
                and acceptance["zero_trade_delta_each_cycle"]
            ),
            "future_gate_keeps_live_order_submission_disabled": acceptance[
                "live_order_submission_authorized"
            ]
            is False,
            "p9bp_executes_nothing": True,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bp_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "owner_gate_allow_future_continuous_timer_path_shadow_cycles_no_order_only",
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        **no_order_boundary(ready=ready, supervisor_loads_hook=supervisor_loads_hook),
    }
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "execution_permission": str(proof_root / "execution_permission.json"),
        "acceptance_contract": str(proof_root / "acceptance_contract.json"),
        "acceptance_checklist": str(proof_root / "acceptance_checklist.json"),
        "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "p9bp_owner_gate_timer_path_shadow_cycles.md"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "gate_scope": "p9bp_allow_future_continuous_timer_path_shadow_cycles_no_order_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9bp_owner_gate_ready": ready,
        "p9bo_proposal_review_package_ready_for_p9bp": p9bo_ok,
        "eligible_for_future_p9bq_continuous_timer_path_shadow_cycles": ready,
        "allowed_next_gate": P9BQ_GATE if ready else "",
        "recommended_next_gate": P9BQ_GATE if ready else "",
        "allowed_next_gate_scope": P9BQ_SCOPE if ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "proof_root": str(proof_root),
        "gates": gates,
        "blockers": blockers,
        "output_files": output_files,
        **no_order_boundary(ready=ready, supervisor_loads_hook=supervisor_loads_hook),
    }
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "execution_permission.json", permission)
    write_json(proof_root / "acceptance_contract.json", acceptance)
    write_json(proof_root / "acceptance_checklist.json", checklist)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix(run_id, ready))
    write_json(proof_root / "control_boundary_readback.json", control)
    write_json(root / "summary.json", summary)
    (root / "p9bp_owner_gate_timer_path_shadow_cycles.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9BP Timer-Path Shadow Cycles Owner Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9BP allows only a future separately requested no-order P9BQ continuous real timer-path shadow-cycle execution gate.",
        "",
        "```text",
        f"p9bp_owner_gate_ready = {str(bool(summary['p9bp_owner_gate_ready'])).lower()}",
        f"allowed_next_gate = {summary['allowed_next_gate']}",
        "continuous_timer_path_shadow_cycles_execution_authorized_for_future_gate = "
        f"{str(bool(summary['continuous_timer_path_shadow_cycles_execution_authorized_for_future_gate'])).lower()}",
        "continuous_timer_path_shadow_cycles_executed_in_p9bp = false",
        "execute_cycles_inside_p9bp_authorized = false",
        "timer_path_load_authorized_in_p9bp = false",
        "supervisor_invocation_authorized_in_p9bp = false",
        "candidate_execution_authorized = false",
        "live_order_submission_authorized = false",
        "execution_target_source = baseline_only",
        "candidate_artifact_sink = proof_artifacts_only_until_p9bq",
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
    summary, exit_code = build_p9bp(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    print(f"allowed_next_gate={summary['allowed_next_gate']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
