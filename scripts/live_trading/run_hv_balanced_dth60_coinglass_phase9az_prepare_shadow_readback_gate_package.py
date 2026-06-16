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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ay_allow_prepare_shadow_readback_gate import (  # noqa: E402
    APPROVE_P9AY_DECISION,
    CONTRACT_VERSION as P9AY_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9AY_PARENT,
    P9AZ_GATE,
    P9AZ_SCOPE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9az_prepare_shadow_readback_gate_package.v1"
APPROVE_P9AZ_DECISION = (
    "approve_p9az_prepare_default_off_observe_only_live_supervisor_timer_path_"
    "shadow_readback_gate_package_only"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9az_prepare_shadow_readback_gate_package"

P9BA_GATE = (
    "P9BA_review_default_off_observe_only_live_supervisor_timer_path_shadow_readback_gate_package_"
    "only_if_separately_requested"
)
P9BA_SCOPE = "owner_gated_review_default_off_observe_only_timer_path_shadow_readback_gate_package_only"

FALSE_EXECUTION_KEYS = (
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

P9AY_FALSE_KEYS = (
    "prepare_shadow_readback_gate_in_p9ay_authorized",
    "execute_p9az_authorized",
    "prepare_gate_package_authorized",
    *FALSE_EXECUTION_KEYS,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9AZ: prepare only the default-off/observe-only live-supervisor "
            "timer-path shadow-readback gate package under proof_artifacts. P9AZ does "
            "not execute readback, enter timer path, invoke supervisor, remote sync, "
            "mutate executor/config/operator/timer state, replace target plans, or "
            "authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ay-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AZ_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9az_prepare_shadow_readback_gate_package_only",
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


def latest_p9ay_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9ay_summary).strip():
        return resolve_path(args.phase9ay_summary)
    return latest_match(P9AY_PARENT, "*/summary.json")


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


def p9ay_output_paths(p9ay: dict[str, Any]) -> dict[str, Path]:
    return {
        "owner_decision_record": source_output_path(p9ay, "owner_decision_record"),
        "shadow_readback_gate_preparation_permission": source_output_path(
            p9ay, "shadow_readback_gate_preparation_permission"
        ),
        "non_authorization_matrix": source_output_path(p9ay, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(p9ay, "control_boundary_readback"),
    }


def p9ay_ready_for_p9az(
    p9ay: dict[str, Any],
    owner_record: dict[str, Any],
    permission: dict[str, Any],
    matrix: dict[str, Any],
    control: dict[str, Any],
    paths: dict[str, Path],
    *,
    current_hook_sha256: str,
    current_supervisor_sha256: str,
    current_live_config_sha256: str,
    current_supervisor_loads_candidate_hook: bool,
) -> bool:
    source = dict(p9ay.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    live_config = dict(source.get("live_config_dir") or {})
    summary_owner = dict(p9ay.get("owner_decision") or {})
    permission_owner = dict(permission.get("owner_decision") or {})
    boundaries = dict(permission.get("p9az_required_boundaries") or {})
    disallowed = dict(permission.get("p9az_disallowed_actions") or {})
    authorizations = dict(matrix.get("authorizations") or {})
    required_disallowed = (
        "execute_p9az_inside_p9ay",
        "prepare_gate_package_inside_p9ay",
        "write_proposal_body_inside_p9ay",
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
        "remote_execution",
        "stage_governance_change",
        "submit_orders",
    )
    forbidden_authorizations = (
        "prepare_shadow_readback_gate_in_p9ay",
        "execute_p9az",
        "prepare_gate_package",
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
    return (
        p9ay.get("contract_version") == P9AY_CONTRACT
        and p9ay.get("status") == "ready"
        and not p9ay.get("blockers")
        and p9ay.get("p9ay_allow_prepare_shadow_readback_gate_ready") is True
        and p9ay.get("eligible_for_future_shadow_readback_gate_package_preparation_request") is True
        and p9ay.get("future_shadow_readback_gate_package_preparation_request_authorized") is True
        and p9ay.get("allowed_next_gate") == P9AZ_GATE
        and p9ay.get("recommended_next_gate") == P9AZ_GATE
        and p9ay.get("allowed_next_gate_scope") == P9AZ_SCOPE
        and p9ay.get("allowed_next_gate_must_be_separately_requested") is True
        and p9ay.get("candidate_order_authority") == "disabled"
        and p9ay.get("execution_target_source") == "baseline_only"
        and p9ay.get("candidate_overlay_execution_path") == "shadow_only_not_executor"
        and p9ay.get("candidate_artifact_sink") == "proof_artifacts_only"
        and p9ay.get("executor_consumes_baseline_only") is True
        and p9ay.get("candidate_shadow_only") is True
        and p9ay.get("candidate_plan_referenced_by_executor") is False
        and p9ay.get("live_supervisor_source_unchanged") is True
        and p9ay.get("live_config_dir_unchanged") is True
        and all_false(p9ay, P9AY_FALSE_KEYS)
        and no_live_mutation(p9ay)
        and zero_orders_fills(p9ay)
        and owner_record.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ay_owner_decision.v1"
        and owner_record.get("decision") == APPROVE_P9AY_DECISION
        and owner_record.get("future_shadow_readback_gate_package_preparation_request_approved") is True
        and owner_record.get("prepare_gate_package_approved") is False
        and owner_record.get("proposal_body_write_approved") is False
        and owner_record.get("dry_load_readback_execution_approved") is False
        and owner_record.get("timer_path_shadow_readback_execution_approved") is False
        and owner_record.get("live_timer_path_load_approved") is False
        and owner_record.get("supervisor_invocation_approved") is False
        and owner_record.get("remote_execution_approved") is False
        and owner_record.get("candidate_execution_approved") is False
        and owner_record.get("live_order_submission_approved") is False
        and summary_owner == owner_record
        and permission.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ay_shadow_readback_gate_preparation_permission.v1"
        and permission.get("allowed_next_gate") == P9AZ_GATE
        and permission.get("allowed_next_gate_scope") == P9AZ_SCOPE
        and permission.get("allowed_next_gate_must_be_separately_requested") is True
        and permission.get("opened_in_p9ay") is False
        and permission.get("executed_in_p9ay") is False
        and permission.get("prepared_in_p9ay") is False
        and permission_owner == owner_record
        and boundaries.get("owner_gated") is True
        and boundaries.get("proof_artifacts_only") is True
        and boundaries.get("default_off_required") is True
        and boundaries.get("observe_only_required") is True
        and boundaries.get("executor_input_must_remain_baseline_only") is True
        and boundaries.get("candidate_shadow_only") is True
        and boundaries.get("candidate_plan_must_not_be_referenced_by_executor") is True
        and boundaries.get("candidate_order_authority") == "disabled"
        and boundaries.get("live_order_submission_authorized") is False
        and int_equals(boundaries, "orders_submitted_must_equal", 0)
        and int_equals(boundaries, "fill_count_must_equal", 0)
        and boundaries.get("dry_load_readback_execution_authorized") is False
        and boundaries.get("timer_path_shadow_readback_execution_authorized") is False
        and boundaries.get("timer_path_load_authorized") is False
        and boundaries.get("supervisor_invocation_authorized") is False
        and boundaries.get("remote_sync_authorized") is False
        and all(disallowed.get(key) is True for key in required_disallowed)
        and matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ay_non_authorization_matrix.v1"
        and authorizations.get("future_shadow_readback_gate_package_preparation_request") is True
        and all_authorizations_false(matrix, forbidden_authorizations)
        and control.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ay_control_boundary_readback.v1"
        and control.get("future_shadow_readback_gate_package_preparation_request_authorized") is True
        and control.get("prepare_gate_package_authorized") is False
        and control.get("proposal_body_write_authorized") is False
        and control.get("dry_load_readback_execution_authorized") is False
        and control.get("timer_path_shadow_readback_authorized") is False
        and control.get("timer_path_load_authorized") is False
        and control.get("supervisor_invocation_authorized") is False
        and control.get("remote_execution_authorized") is False
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
        and paths["shadow_readback_gate_preparation_permission"].exists()
        and paths["non_authorization_matrix"].exists()
        and paths["control_boundary_readback"].exists()
        and output_under_proof_artifacts(paths["shadow_readback_gate_preparation_permission"])
        and output_under_proof_artifacts(paths["non_authorization_matrix"])
        and output_under_proof_artifacts(paths["control_boundary_readback"])
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def build_owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9AZ_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9az_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "prepare_shadow_readback_gate_package_only",
        "decision_effect": "prepare_shadow_readback_gate_package_under_proof_artifacts_only"
        if approved
        else "none",
        "prepare_shadow_readback_gate_package_approved": approved,
        "future_shadow_readback_gate_package_review_request_approved": approved,
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


def build_shadow_readback_gate_package(
    *,
    run_id: str,
    prepared: bool,
    decision: dict[str, Any],
    source_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9az_shadow_readback_gate_package.v1",
        "run_id": run_id,
        "package_type": "default_off_observe_only_live_supervisor_timer_path_shadow_readback_gate_package",
        "package_prepared": prepared,
        "package_written_under_proof_artifacts": True,
        "source_evidence": source_evidence,
        "owner_decision": decision,
        "default_enabled": False,
        "observe_only": True,
        "order_authority": "disabled",
        "executor_target_source": "baseline_only",
        "candidate_shadow_only": True,
        "candidate_plan_must_not_be_referenced_by_executor": True,
        "future_review_gate": P9BA_GATE if prepared else "",
        "future_review_gate_scope": P9BA_SCOPE if prepared else "",
        "future_review_gate_must_be_separately_requested": True,
        "readback_contract_if_future_gate_approved": {
            "fresh_account_read_required_before_remote_or_timer_path": True,
            "pre_position_fingerprint_required": True,
            "post_position_fingerprint_required": True,
            "baseline_only_executor": True,
            "candidate_shadow_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "zero_order_delta_required": True,
            "zero_cancel_delta_required": True,
            "zero_fill_delta_required": True,
            "zero_trade_delta_required": True,
            "dry_load_readback_must_be_separately_requested": True,
            "timer_path_shadow_readback_must_be_separately_requested": True,
            "production_timer_service_load_requires_separate_owner_gate": True,
            "live_config_mutation_requires_separate_owner_gate": True,
            "operator_state_mutation_requires_separate_owner_gate": True,
            "timer_state_mutation_requires_separate_owner_gate": True,
            "live_order_submission_authorized": False,
        },
        "authorizations": {
            "prepare_shadow_readback_gate_package": prepared,
            "future_shadow_readback_gate_package_review_request": prepared,
            "proposal_body_write": False,
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
        "required_boundaries": {
            "owner_gated": True,
            "proof_artifacts_only": True,
            "default_off_required": True,
            "observe_only_required": True,
            "no_order_required": True,
            "executor_input_must_remain_baseline_only": True,
            "candidate_shadow_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "candidate_order_authority": "disabled",
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
            "dry_load_readback_execution_authorized": False,
            "timer_path_shadow_readback_execution_authorized": False,
            "timer_path_load_authorized": False,
            "supervisor_invocation_authorized": False,
            "remote_sync_authorized": False,
            "live_order_submission_authorized": False,
        },
        "executed_actions": {
            "dry_load_readback_executed": False,
            "timer_path_shadow_readback_executed": False,
            "timer_path_loaded": False,
            "supervisor_invoked": False,
            "remote_sync_performed": False,
            "candidate_execution_performed": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
            "live_config_mutated": False,
            "operator_state_mutated": False,
            "timer_state_mutated": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
        },
    }


def build_phase9az(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9az" / run_id

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9ay": latest_p9ay_summary(args),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
        "live_config_dir": resolve_path(args.live_config_dir),
    }
    project_profile = load_optional(paths["project_profile"])
    p9ay = load_optional(paths["phase9ay"])
    p9ay_paths = p9ay_output_paths(p9ay)
    p9ay_owner = load_optional(p9ay_paths["owner_decision_record"])
    p9ay_permission = load_optional(p9ay_paths["shadow_readback_gate_preparation_permission"])
    p9ay_matrix = load_optional(p9ay_paths["non_authorization_matrix"])
    p9ay_control = load_optional(p9ay_paths["control_boundary_readback"])

    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_before = tree_sha256(paths["live_config_dir"])
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    decision = build_owner_decision_record(args, generated_at)
    p9ay_ok = p9ay_ready_for_p9az(
        p9ay,
        p9ay_owner,
        p9ay_permission,
        p9ay_matrix,
        p9ay_control,
        p9ay_paths,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9ay_summary": evidence_file(paths["phase9ay"]),
        "phase9ay_owner_decision_record": evidence_file(p9ay_paths["owner_decision_record"]),
        "phase9ay_shadow_readback_gate_preparation_permission": evidence_file(
            p9ay_paths["shadow_readback_gate_preparation_permission"]
        ),
        "phase9ay_non_authorization_matrix": evidence_file(p9ay_paths["non_authorization_matrix"]),
        "phase9ay_control_boundary_readback": evidence_file(p9ay_paths["control_boundary_readback"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
        "live_config_dir": {
            "path": str(paths["live_config_dir"]),
            "exists": paths["live_config_dir"].exists(),
            "sha256": live_config_sha_before,
        },
    }

    owner_ok = str(args.owner_decision) == APPROVE_P9AZ_DECISION
    base_ready = (
        owner_ok
        and project_profile.get("current_stage") == "stage_1_research_readiness_only"
        and p9ay_ok
        and supervisor_loads_hook is False
        and output_under_proof_artifacts(proof_root / "shadow_readback_gate_package.json")
        and output_under_proof_artifacts(proof_root / "package_acceptance_checklist.json")
        and output_under_proof_artifacts(proof_root / "non_authorization_matrix.json")
        and output_under_proof_artifacts(proof_root / "control_boundary_readback.json")
    )
    package = build_shadow_readback_gate_package(
        run_id=run_id,
        prepared=base_ready,
        decision=decision,
        source_evidence=source_evidence,
    )
    checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9az_package_acceptance_checklist.v1",
        "run_id": run_id,
        "checks": {
            "p9az_package_preparation_only": base_ready,
            "p9ay_retained_permission_ready": p9ay_ok,
            "package_output_under_proof_artifacts": output_under_proof_artifacts(
                proof_root / "shadow_readback_gate_package.json"
            ),
            "package_keeps_default_off": package["default_enabled"] is False,
            "package_keeps_observe_only": package["observe_only"] is True,
            "package_keeps_executor_baseline_only": package["executor_target_source"] == "baseline_only",
            "package_keeps_candidate_shadow_only": package["candidate_shadow_only"] is True,
            "package_keeps_order_authority_disabled": package["order_authority"] == "disabled",
            "future_review_gate_must_be_separately_requested": package[
                "future_review_gate_must_be_separately_requested"
            ]
            is True,
            "dry_load_readback_not_executed": True,
            "timer_path_shadow_readback_not_executed": True,
            "timer_path_not_loaded": True,
            "supervisor_not_invoked": True,
            "remote_not_touched": True,
            "executor_input_not_mutated": True,
            "target_plan_not_replaced": True,
            "live_config_not_mutated": True,
            "operator_state_not_mutated": True,
            "timer_state_not_mutated": True,
            "zero_orders_fills": True,
        },
    }
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9az_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "prepare_shadow_readback_gate_package": base_ready,
            "future_shadow_readback_gate_package_review_request": base_ready,
            "execute_p9ba": False,
            "proposal_body_write": False,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9az_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "prepare_shadow_readback_gate_package_only",
        "live_supervisor": source_evidence["live_supervisor"],
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "prepare_gate_package_authorized": base_ready,
        "shadow_readback_gate_package_prepared": base_ready,
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
        "owner_decision_p9az_prepare_package_only": owner_ok,
        "project_stage_boundary_preserved": project_profile.get("current_stage")
        == "stage_1_research_readiness_only",
        "p9ay_permission_ready_for_p9az": p9ay_ok,
        "p9ay_allows_p9az_only": p9ay.get("allowed_next_gate") == P9AZ_GATE
        and p9ay.get("future_shadow_readback_gate_package_preparation_request_authorized") is True,
        "p9ay_did_not_prepare_package": p9ay.get("prepare_gate_package_authorized") is False,
        "p9ay_did_not_execute_p9az": p9ay.get("execute_p9az_authorized") is False,
        "p9ay_did_not_execute_readback": p9ay.get("dry_load_readback_execution_authorized") is False,
        "p9ay_did_not_enter_timer_path": p9ay.get("timer_path_load_authorized") is False,
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "current_hook_hash_matches_p9ay_source": dict(source_evidence["phase9ay_summary"] or {})
        .get("exists")
        is True
        and dict(dict(p9ay.get("source_evidence") or {}).get("hook_module") or {}).get("sha256") == hook_sha,
        "current_supervisor_hash_matches_p9ay_source": dict(
            dict(p9ay.get("source_evidence") or {}).get("live_supervisor") or {}
        ).get("sha256")
        == supervisor_sha_before,
        "current_live_config_hash_matches_p9ay_source": dict(
            dict(p9ay.get("source_evidence") or {}).get("live_config_dir") or {}
        ).get("sha256")
        == live_config_sha_before,
        "shadow_readback_gate_package_output_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "shadow_readback_gate_package.json"
        ),
        "package_acceptance_checklist_output_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "package_acceptance_checklist.json"
        ),
        "p9az_prepares_package_only": base_ready,
        "p9az_does_not_write_proposal_body": True,
        "p9az_does_not_execute_dry_load_readback": True,
        "p9az_does_not_execute_timer_path_shadow_readback": True,
        "p9az_does_not_enter_timer_path": True,
        "p9az_does_not_run_supervisor": True,
        "p9az_does_not_remote_sync": True,
        "p9az_does_not_mutate_executor_input": True,
        "p9az_does_not_replace_target_plan": True,
        "p9az_does_not_mutate_live_config": True,
        "p9az_does_not_mutate_operator_state": True,
        "p9az_does_not_mutate_timer_state": True,
        "p9az_keeps_default_off": True,
        "p9az_keeps_observe_only": True,
        "p9az_keeps_executor_baseline_only": True,
        "p9az_keeps_candidate_shadow_only": True,
        "p9az_keeps_order_authority_disabled": True,
        "p9ba_review_gate_must_be_separately_requested": True,
        "zero_orders_fills_in_p9az": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    ready = status == "ready"
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "shadow_readback_gate_package": str(proof_root / "shadow_readback_gate_package.json"),
        "package_acceptance_checklist": str(proof_root / "package_acceptance_checklist.json"),
        "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "p9az_prepare_shadow_readback_gate_package.md"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "gate_scope": "p9az_prepare_default_off_observe_only_shadow_readback_gate_package_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9az_shadow_readback_gate_package_ready": ready,
        "shadow_readback_gate_package_prepared": ready,
        "shadow_readback_gate_package_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "shadow_readback_gate_package.json"
        ),
        "eligible_for_future_shadow_readback_gate_package_review_request": ready,
        "allowed_next_gate": P9BA_GATE if ready else "",
        "recommended_next_gate": P9BA_GATE if ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "allowed_next_gate_scope": P9BA_SCOPE if ready else "",
        "prepare_gate_package_authorized": ready,
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
    write_json(proof_root / "shadow_readback_gate_package.json", package)
    write_json(proof_root / "package_acceptance_checklist.json", checklist)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix)
    write_json(proof_root / "control_boundary_readback.json", control_boundary_readback)
    write_json(root / "summary.json", summary)
    (root / "p9az_prepare_shadow_readback_gate_package.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9AZ Prepare Shadow Readback Gate Package",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9AZ only prepares the retained default-off/observe-only timer-path shadow-readback gate package.",
        "",
        "```text",
        f"shadow_readback_gate_package_prepared = "
        f"{str(bool(summary['shadow_readback_gate_package_prepared'])).lower()}",
        f"allowed_next_gate = {summary['allowed_next_gate']}",
        "prepare_gate_package_authorized = "
        f"{str(bool(summary['prepare_gate_package_authorized'])).lower()}",
        "proposal_body_write_authorized = false",
        "dry_load_readback_execution_authorized = false",
        "timer_path_shadow_readback_authorized = false",
        "timer_path_load_authorized = false",
        "supervisor_invocation_authorized = false",
        "remote_execution_performed = false",
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
    summary, exit_code = build_phase9az(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    print(f"shadow_readback_gate_package={summary['output_files']['shadow_readback_gate_package']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
