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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ax_define_next_scope_after_p9aw import (  # noqa: E402
    APPROVE_P9AX_DECISION,
    CONTRACT_VERSION as P9AX_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9AX_PARENT,
    NEXT_GATE_ID as P9AY_GATE,
    NEXT_GATE_SCOPE as P9AY_DEFINED_SCOPE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9ay_allow_prepare_shadow_readback_gate.v1"
APPROVE_P9AY_DECISION = (
    "approve_p9ay_allow_prepare_default_off_observe_only_live_supervisor_timer_path_shadow_readback_gate_only"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ay_allow_prepare_shadow_readback_gate"

P9AZ_GATE = (
    "P9AZ_prepare_default_off_observe_only_live_supervisor_timer_path_shadow_readback_gate_package_"
    "only_if_separately_requested"
)
P9AZ_SCOPE = "owner_gated_prepare_default_off_observe_only_timer_path_shadow_readback_gate_package_only"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9AY: an owner-gated permission step that only allows a future "
            "separately requested package-preparation gate for default-off/observe-only "
            "live-supervisor timer-path shadow readback. P9AY does not prepare the "
            "package, write a proposal body, execute readback, enter timer path, "
            "invoke the supervisor, remote sync, mutate live state or executor input, "
            "replace target plans, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ax-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AY_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9ay_allow_prepare_default_off_observe_only_timer_path_shadow_readback_gate_only",
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


def latest_p9ax_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9ax_summary).strip():
        return resolve_path(args.phase9ax_summary)
    return latest_match(P9AX_PARENT, "*/summary.json")


def all_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def all_authorizations_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    authorizations = dict(payload.get("authorizations") or {})
    return all(authorizations.get(key) is False for key in keys)


def int_equals(payload: dict[str, Any], key: str, expected: int) -> bool:
    try:
        return int(payload.get(key)) == expected
    except (TypeError, ValueError):
        return False


def p9ax_output_paths(p9ax: dict[str, Any]) -> dict[str, Path]:
    return {
        "owner_decision_record": source_output_path(p9ax, "owner_decision_record"),
        "next_gate_scope_definition": source_output_path(p9ax, "next_gate_scope_definition"),
        "scope_acceptance_checklist": source_output_path(p9ax, "scope_acceptance_checklist"),
        "non_authorization_matrix": source_output_path(p9ax, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(p9ax, "control_boundary_readback"),
    }


def p9ax_ready_for_p9ay(
    p9ax: dict[str, Any],
    owner_record: dict[str, Any],
    scope_definition: dict[str, Any],
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
    source = dict(p9ax.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    live_config = dict(source.get("live_config_dir") or {})
    owner = dict(p9ax.get("owner_decision") or {})
    scope_owner = dict(scope_definition.get("owner_decision") or {})
    checklist_checks = dict(checklist.get("checklist") or {})
    boundaries = dict(scope_definition.get("required_boundaries") or {})
    disallowed = dict(scope_definition.get("disallowed_actions_in_p9ax") or {})
    summary_false = (
        "defined_next_gate_authorized_in_p9ax",
        "defined_next_gate_execution_authorized",
        "prepare_gate_authorized",
        "proposal_body_write_authorized",
        "dry_load_readback_execution_authorized",
        "timer_path_shadow_readback_authorized",
        "timer_hook_implementation_authorized",
        "hook_deployment_authorized",
        "timer_path_load_authorized",
        "supervisor_invocation_authorized",
        "supervisor_run_authorized",
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
    owner_false = (
        "allow_prepare_shadow_readback_gate_approved_in_p9ax",
        "execute_defined_next_gate_approved",
        "prepare_shadow_readback_gate_approved",
        "prepare_proposal_package_approved",
        "proposal_body_write_approved",
        "dry_load_readback_execution_approved",
        "timer_path_shadow_readback_execution_approved",
        "candidate_execution_approved",
        "candidate_live_order_submission_approved",
        "timer_hook_implementation_approved",
        "hook_deployment_approved",
        "live_timer_path_load_approved",
        "production_timer_service_load_approved",
        "live_order_submission_approved",
        "target_plan_replacement_approved",
        "executor_input_mutation_approved",
        "live_config_mutation_approved",
        "operator_state_mutation_approved",
        "timer_or_service_mutation_approved",
        "remote_sync_approved",
        "remote_execution_approved",
        "supervisor_invocation_approved",
        "supervisor_run_approved",
        "repo_stage_change_approved",
    )
    forbidden_authorizations = (
        "allow_prepare_shadow_readback_gate_in_p9ax",
        "execute_defined_next_gate",
        "prepare_shadow_readback_gate",
        "prepare_proposal_package",
        "write_proposal_body",
        "dry_load_readback_execution",
        "timer_path_shadow_readback_execution",
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
    required_disallowed = (
        "execute_defined_next_gate",
        "prepare_shadow_readback_gate",
        "prepare_proposal_package",
        "write_proposal_body",
        "execute_dry_load_readback",
        "execute_timer_path_shadow_readback",
        "implement_hook",
        "deploy_hook",
        "load_live_timer_path",
        "run_supervisor",
        "invoke_timer_or_service",
        "mutate_executor_input",
        "replace_target_plan",
        "mutate_live_config",
        "mutate_operator_state",
        "mutate_timer_or_service_state",
        "remote_sync",
        "stage_governance_change",
        "submit_orders",
    )
    return (
        p9ax.get("contract_version") == P9AX_CONTRACT
        and p9ax.get("status") == "ready"
        and not p9ax.get("blockers")
        and p9ax.get("p9ax_next_gate_scope_definition_ready") is True
        and p9ax.get("next_gate_scope_defined") is True
        and p9ax.get("defined_next_gate") == P9AY_GATE
        and p9ax.get("defined_next_gate_scope") == P9AY_DEFINED_SCOPE
        and p9ax.get("defined_next_gate_must_be_separately_requested") is True
        and p9ax.get("eligible_for_future_p9ay_owner_gate_request") is True
        and p9ax.get("allowed_next_gate") == P9AY_GATE
        and p9ax.get("recommended_next_gate") == P9AY_GATE
        and p9ax.get("allowed_next_gate_must_be_separately_requested") is True
        and p9ax.get("candidate_order_authority") == "disabled"
        and p9ax.get("execution_target_source") == "baseline_only"
        and p9ax.get("candidate_overlay_execution_path") == "shadow_only_not_executor"
        and p9ax.get("candidate_artifact_sink") == "proof_artifacts_only"
        and p9ax.get("executor_consumes_baseline_only") is True
        and p9ax.get("candidate_shadow_only") is True
        and p9ax.get("candidate_plan_referenced_by_executor") is False
        and p9ax.get("live_supervisor_source_unchanged") is True
        and p9ax.get("live_config_dir_unchanged") is True
        and all_false(p9ax, summary_false)
        and no_live_mutation(p9ax)
        and zero_orders_fills(p9ax)
        and owner_record.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ax_owner_decision.v1"
        and owner_record.get("decision") == APPROVE_P9AX_DECISION
        and owner_record.get("define_next_gate_scope_approved") is True
        and owner_record.get("defined_next_gate") == P9AY_GATE
        and all_false(owner_record, owner_false)
        and owner == owner_record
        and scope_definition.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ax_next_gate_scope_definition.v1"
        and scope_definition.get("defined_next_gate") == P9AY_GATE
        and scope_definition.get("defined_next_gate_scope") == P9AY_DEFINED_SCOPE
        and scope_definition.get("defined_next_gate_must_be_separately_requested") is True
        and scope_definition.get("defined_next_gate_executes_in_p9ax") is False
        and scope_definition.get("defined_next_gate_authorized_in_p9ax") is False
        and scope_definition.get("defined_next_gate_execution_authorized") is False
        and scope_definition.get("prepare_gate_authorized_in_p9ax") is False
        and scope_definition.get("proposal_body_write_authorized_in_p9ax") is False
        and scope_definition.get("dry_load_readback_execution_authorized_in_p9ax") is False
        and scope_definition.get("timer_path_shadow_readback_execution_authorized_in_p9ax") is False
        and scope_owner == owner_record
        and boundaries.get("owner_gated") is True
        and boundaries.get("proof_artifacts_only") is True
        and boundaries.get("default_off_required") is True
        and boundaries.get("observe_only_required") is True
        and boundaries.get("no_order_required") is True
        and boundaries.get("executor_input_must_remain_baseline_only") is True
        and boundaries.get("candidate_shadow_only") is True
        and boundaries.get("candidate_plan_must_not_be_referenced_by_executor") is True
        and boundaries.get("live_order_submission_authorized") is False
        and boundaries.get("candidate_order_authority") == "disabled"
        and int_equals(boundaries, "orders_submitted_must_equal", 0)
        and int_equals(boundaries, "fill_count_must_equal", 0)
        and boundaries.get("dry_load_readback_execution_authorized") is False
        and boundaries.get("timer_path_shadow_readback_execution_authorized") is False
        and boundaries.get("timer_path_load_authorized") is False
        and boundaries.get("supervisor_invocation_authorized") is False
        and boundaries.get("production_timer_service_load_authorized") is False
        and boundaries.get("remote_sync_authorized") is False
        and boundaries.get("real_timer_path_shadow_readback_requires_separate_gate") is True
        and boundaries.get("account_read_proof_required_before_any_remote_or_timer_path") is True
        and all(disallowed.get(key) is True for key in required_disallowed)
        and checklist.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ax_scope_acceptance_checklist.v1"
        and checklist_checks
        and all(value is True for value in checklist_checks.values())
        and matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ax_non_authorization_matrix.v1"
        and dict(matrix.get("authorizations") or {}).get("define_next_gate_scope") is True
        and all_authorizations_false(matrix, forbidden_authorizations)
        and control.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ax_control_boundary_readback.v1"
        and control.get("live_supervisor_source_unchanged") is True
        and control.get("live_supervisor_loads_candidate_hook") is False
        and control.get("live_config_dir_unchanged") is True
        and control.get("defined_next_gate") == P9AY_GATE
        and control.get("defined_next_gate_authorized_in_p9ax") is False
        and control.get("defined_next_gate_execution_authorized") is False
        and control.get("prepare_gate_authorized") is False
        and control.get("proposal_body_write_authorized") is False
        and control.get("dry_load_readback_execution_authorized") is False
        and control.get("timer_path_shadow_readback_authorized") is False
        and control.get("timer_path_load_authorized") is False
        and control.get("supervisor_invocation_authorized") is False
        and control.get("remote_sync_authorized") is False
        and control.get("candidate_execution_authorized") is False
        and control.get("live_order_submission_authorized") is False
        and control.get("entered_timer_path") is False
        and control.get("live_timer_path_loaded") is False
        and control.get("ran_supervisor") is False
        and control.get("remote_execution_performed") is False
        and control.get("candidate_execution_performed") is False
        and control.get("executor_input_mutated") is False
        and control.get("target_plan_replaced") is False
        and control.get("live_config_changed") is False
        and control.get("operator_state_changed") is False
        and control.get("timer_state_changed") is False
        and zero_orders_fills(control)
        and paths["owner_decision_record"].exists()
        and paths["next_gate_scope_definition"].exists()
        and paths["scope_acceptance_checklist"].exists()
        and paths["non_authorization_matrix"].exists()
        and paths["control_boundary_readback"].exists()
        and output_under_proof_artifacts(paths["next_gate_scope_definition"])
        and output_under_proof_artifacts(paths["scope_acceptance_checklist"])
        and output_under_proof_artifacts(paths["non_authorization_matrix"])
        and output_under_proof_artifacts(paths["control_boundary_readback"])
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def build_owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9AY_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ay_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "allow_future_shadow_readback_gate_package_preparation_request_only",
        "decision_effect": "allow_future_p9az_gate_package_preparation_request_only" if approved else "none",
        "future_shadow_readback_gate_package_preparation_request_approved": approved,
        "prepare_shadow_readback_gate_in_p9ay_approved": False,
        "execute_p9az_approved": False,
        "prepare_gate_package_approved": False,
        "proposal_body_write_approved": False,
        "dry_load_readback_execution_approved": False,
        "timer_path_shadow_readback_execution_approved": False,
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


def build_preparation_permission(
    *,
    run_id: str,
    decision: dict[str, Any],
    source_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ay_shadow_readback_gate_preparation_permission.v1",
        "run_id": run_id,
        "source_evidence": source_evidence,
        "owner_decision": decision,
        "allowed_next_gate": P9AZ_GATE,
        "allowed_next_gate_must_be_separately_requested": True,
        "allowed_next_gate_scope": P9AZ_SCOPE,
        "opened_in_p9ay": False,
        "executed_in_p9ay": False,
        "prepared_in_p9ay": False,
        "p9az_allowed_question": (
            "whether to prepare a proof-artifacts-only gate package for default-off/observe-only "
            "live-supervisor timer-path shadow readback"
        ),
        "p9az_effect_if_approved": (
            "prepare only the next retained gate package under proof_artifacts; no timer-path "
            "readback execution, supervisor invocation, remote sync, executor mutation, or order action"
        ),
        "p9az_required_boundaries": {
            "owner_gated": True,
            "proof_artifacts_only": True,
            "default_off_required": True,
            "observe_only_required": True,
            "executor_input_must_remain_baseline_only": True,
            "candidate_shadow_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "candidate_order_authority": "disabled",
            "live_order_submission_authorized": False,
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
            "dry_load_readback_execution_authorized": False,
            "timer_path_shadow_readback_execution_authorized": False,
            "timer_path_load_authorized": False,
            "supervisor_invocation_authorized": False,
            "remote_sync_authorized": False,
        },
        "p9az_disallowed_actions": {
            "execute_p9az_inside_p9ay": True,
            "prepare_gate_package_inside_p9ay": True,
            "write_proposal_body_inside_p9ay": True,
            "execute_dry_load_readback": True,
            "execute_timer_path_shadow_readback": True,
            "implement_hook": True,
            "deploy_hook": True,
            "load_live_timer_path": True,
            "run_supervisor": True,
            "invoke_timer_or_service": True,
            "mutate_executor_input": True,
            "replace_target_plan": True,
            "mutate_live_config": True,
            "mutate_operator_state": True,
            "mutate_timer_or_service_state": True,
            "remote_sync": True,
            "remote_execution": True,
            "stage_governance_change": True,
            "submit_orders": True,
        },
    }


def build_phase9ay(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9ay" / run_id

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9ax": latest_p9ax_summary(args),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
        "live_config_dir": resolve_path(args.live_config_dir),
    }
    project_profile = load_optional(paths["project_profile"])
    p9ax = load_optional(paths["phase9ax"])
    p9ax_paths = p9ax_output_paths(p9ax)
    owner_record = load_optional(p9ax_paths["owner_decision_record"])
    scope_definition = load_optional(p9ax_paths["next_gate_scope_definition"])
    checklist = load_optional(p9ax_paths["scope_acceptance_checklist"])
    matrix = load_optional(p9ax_paths["non_authorization_matrix"])
    control = load_optional(p9ax_paths["control_boundary_readback"])

    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_before = tree_sha256(paths["live_config_dir"])
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    decision = build_owner_decision_record(args, generated_at)

    p9ax_ok = p9ax_ready_for_p9ay(
        p9ax,
        owner_record,
        scope_definition,
        checklist,
        matrix,
        control,
        p9ax_paths,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9ax_summary": evidence_file(paths["phase9ax"]),
        "phase9ax_owner_decision_record": evidence_file(p9ax_paths["owner_decision_record"]),
        "phase9ax_next_gate_scope_definition": evidence_file(p9ax_paths["next_gate_scope_definition"]),
        "phase9ax_scope_acceptance_checklist": evidence_file(p9ax_paths["scope_acceptance_checklist"]),
        "phase9ax_non_authorization_matrix": evidence_file(p9ax_paths["non_authorization_matrix"]),
        "phase9ax_control_boundary_readback": evidence_file(p9ax_paths["control_boundary_readback"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
        "live_config_dir": {
            "path": str(paths["live_config_dir"]),
            "exists": paths["live_config_dir"].exists(),
            "sha256": live_config_sha_before,
        },
    }
    permission = build_preparation_permission(run_id=run_id, decision=decision, source_evidence=source_evidence)
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ay_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "future_shadow_readback_gate_package_preparation_request": str(args.owner_decision)
            == APPROVE_P9AY_DECISION,
            "prepare_shadow_readback_gate_in_p9ay": False,
            "execute_p9az": False,
            "prepare_gate_package": False,
            "write_proposal_body": False,
            "dry_load_readback_execution": False,
            "timer_path_shadow_readback_execution": False,
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
    supervisor_sha_after = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_after = tree_sha256(paths["live_config_dir"])
    control_boundary_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ay_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "allow_future_shadow_readback_gate_package_preparation_request_only",
        "live_supervisor": source_evidence["live_supervisor"],
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "future_shadow_readback_gate_package_preparation_request_authorized": str(args.owner_decision)
        == APPROVE_P9AY_DECISION,
        "prepare_shadow_readback_gate_in_p9ay_authorized": False,
        "execute_p9az_authorized": False,
        "prepare_gate_package_authorized": False,
        "proposal_body_write_authorized": False,
        "dry_load_readback_execution_authorized": False,
        "timer_path_shadow_readback_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "supervisor_run_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "entered_timer_path": False,
        "live_timer_path_loaded": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
        "exchange_order_submission": "disabled",
    }
    gates = {
        "owner_decision_p9ay_allow_prepare_shadow_readback_gate_only": str(args.owner_decision)
        == APPROVE_P9AY_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage")
        == "stage_1_research_readiness_only",
        "p9ax_scope_definition_ready": p9ax_ok,
        "p9ax_defined_p9ay_only": p9ax.get("defined_next_gate") == P9AY_GATE
        and p9ax.get("defined_next_gate_scope") == P9AY_DEFINED_SCOPE,
        "p9ax_allowed_p9ay_only": p9ax.get("allowed_next_gate") == P9AY_GATE
        and p9ax.get("eligible_for_future_p9ay_owner_gate_request") is True,
        "p9ax_did_not_authorize_p9ay_execution": p9ax.get("defined_next_gate_authorized_in_p9ax") is False
        and p9ax.get("defined_next_gate_execution_authorized") is False,
        "p9ax_did_not_prepare_gate": p9ax.get("prepare_gate_authorized") is False,
        "p9ax_did_not_write_proposal_body": p9ax.get("proposal_body_write_authorized") is False,
        "p9ax_did_not_execute_readback": p9ax.get("dry_load_readback_execution_authorized") is False,
        "p9ax_did_not_enter_timer_path": p9ax.get("timer_path_load_authorized") is False,
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "current_hook_hash_matches_p9ax_source": dict(
            dict(p9ax.get("source_evidence") or {}).get("hook_module") or {}
        ).get("sha256")
        == hook_sha,
        "current_supervisor_hash_matches_p9ax_source": dict(
            dict(p9ax.get("source_evidence") or {}).get("live_supervisor") or {}
        ).get("sha256")
        == supervisor_sha_before,
        "current_live_config_hash_matches_p9ax_source": dict(
            dict(p9ax.get("source_evidence") or {}).get("live_config_dir") or {}
        ).get("sha256")
        == live_config_sha_before,
        "preparation_permission_output_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "shadow_readback_gate_preparation_permission.json"
        ),
        "p9ay_allows_future_p9az_request_only": True,
        "p9ay_does_not_execute_p9az": True,
        "p9ay_does_not_prepare_gate_package": True,
        "p9ay_does_not_write_proposal_body": True,
        "p9ay_does_not_execute_dry_load_readback": True,
        "p9ay_does_not_enter_timer_path": True,
        "p9ay_does_not_run_supervisor": True,
        "p9ay_does_not_remote_sync": True,
        "p9ay_does_not_mutate_executor_input": True,
        "p9ay_does_not_replace_target_plan": True,
        "p9ay_does_not_mutate_live_config": True,
        "p9ay_does_not_mutate_operator_state": True,
        "p9ay_does_not_mutate_timer_state": True,
        "p9az_must_be_separately_requested": True,
        "p9az_must_be_proof_artifacts_only": True,
        "p9az_must_keep_default_off": True,
        "p9az_must_keep_observe_only": True,
        "p9az_must_keep_executor_baseline_only": True,
        "p9az_must_keep_order_authority_disabled": True,
        "zero_orders_fills_in_p9ay": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    ready = status == "ready"
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "shadow_readback_gate_preparation_permission": str(
            proof_root / "shadow_readback_gate_preparation_permission.json"
        ),
        "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "p9ay_allow_prepare_shadow_readback_gate.md"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "gate_scope": "p9ay_allow_future_shadow_readback_gate_package_preparation_request_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9ay_allow_prepare_shadow_readback_gate_ready": ready,
        "eligible_for_future_shadow_readback_gate_package_preparation_request": ready,
        "future_shadow_readback_gate_package_preparation_request_authorized": ready,
        "allowed_next_gate": P9AZ_GATE if ready else "",
        "recommended_next_gate": P9AZ_GATE if ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "allowed_next_gate_scope": P9AZ_SCOPE if ready else "",
        "prepare_shadow_readback_gate_in_p9ay_authorized": False,
        "execute_p9az_authorized": False,
        "prepare_gate_package_authorized": False,
        "proposal_body_write_authorized": False,
        "dry_load_readback_execution_authorized": False,
        "timer_path_shadow_readback_authorized": False,
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
        "candidate_overlay_execution_path": "shadow_only_not_executor",
        "candidate_artifact_sink": "proof_artifacts_only",
        "executor_consumes_baseline_only": True,
        "candidate_shadow_only": True,
        "candidate_plan_referenced_by_executor": False,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_supervisor_source_unchanged": control_boundary_readback["live_supervisor_source_unchanged"],
        "live_config_dir_unchanged": control_boundary_readback["live_config_dir_unchanged"],
        "entered_timer_path": False,
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
        "proof_root": str(proof_root),
        "gates": gates,
        "blockers": blockers,
        "output_files": output_files,
    }
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "shadow_readback_gate_preparation_permission.json", permission)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix)
    write_json(proof_root / "control_boundary_readback.json", control_boundary_readback)
    write_json(root / "summary.json", summary)
    (root / "p9ay_allow_prepare_shadow_readback_gate.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9AY Allow Prepare Shadow Readback Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9AY only allows a future separately requested gate-package preparation step.",
        "",
        "```text",
        f"allowed_next_gate = {summary['allowed_next_gate']}",
        f"future_shadow_readback_gate_package_preparation_request_authorized = "
        f"{str(bool(summary['future_shadow_readback_gate_package_preparation_request_authorized'])).lower()}",
        "prepare_shadow_readback_gate_in_p9ay_authorized = false",
        "execute_p9az_authorized = false",
        "prepare_gate_package_authorized = false",
        "proposal_body_write_authorized = false",
        "dry_load_readback_execution_authorized = false",
        "timer_path_shadow_readback_authorized = false",
        "timer_path_load_authorized = false",
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
    summary, exit_code = build_phase9ay(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
