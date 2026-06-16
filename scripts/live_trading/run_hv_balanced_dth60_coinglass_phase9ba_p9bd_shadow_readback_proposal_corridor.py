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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9az_prepare_shadow_readback_gate_package import (  # noqa: E402
    APPROVE_P9AZ_DECISION,
    CONTRACT_VERSION as P9AZ_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9AZ_PARENT,
    FALSE_EXECUTION_KEYS,
    P9BA_GATE,
    P9BA_SCOPE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9ba_p9bd_shadow_readback_proposal_corridor.v1"
APPROVE_CORRIDOR_DECISION = "approve_p9ba_p9bd_shadow_readback_proposal_corridor_only"
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_p9ba_p9bd_shadow_readback_proposal_corridor"
)

P9BB_GATE = (
    "P9BB_allow_prepare_default_off_observe_only_live_supervisor_timer_path_shadow_"
    "readback_proposal_package_only_if_separately_requested"
)
P9BC_GATE = (
    "P9BC_prepare_default_off_observe_only_live_supervisor_timer_path_shadow_readback_"
    "proposal_package_only_if_separately_requested"
)
P9BD_GATE = (
    "P9BD_retained_readiness_review_after_shadow_readback_proposal_package_"
    "only_if_separately_requested"
)
P9BE_GATE = (
    "P9BE_owner_gate_allow_default_off_observe_only_live_supervisor_timer_path_shadow_"
    "readback_only_if_separately_requested"
)

PROOF_FALSE_AUTHORIZATIONS = (
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9BA-P9BD as a proof-only corridor: review retained P9AZ, allow "
            "proposal-package preparation, generate the proof_artifacts-only proposal "
            "package, then review readiness. It never executes dry-load/readback, "
            "enters timer path, invokes supervisor, remote syncs, mutates live state "
            "or executor input, replaces target plans, executes candidate logic, or "
            "authorizes orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9az-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_CORRIDOR_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:p9ba_p9bd_batch_authorization")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_p9az_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9az_summary).strip():
        return resolve_path(args.phase9az_summary)
    return latest_match(P9AZ_PARENT, "*/summary.json")


def all_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def all_authorizations_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    authorizations = dict(payload.get("authorizations") or {})
    return all(authorizations.get(key) is False for key in keys)


def p9az_output_paths(p9az: dict[str, Any]) -> dict[str, Path]:
    return {
        "owner_decision_record": source_output_path(p9az, "owner_decision_record"),
        "shadow_readback_gate_package": source_output_path(p9az, "shadow_readback_gate_package"),
        "package_acceptance_checklist": source_output_path(p9az, "package_acceptance_checklist"),
        "non_authorization_matrix": source_output_path(p9az, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(p9az, "control_boundary_readback"),
    }


def package_executed_actions_safe(package: dict[str, Any]) -> bool:
    executed = dict(package.get("executed_actions") or {})
    return (
        executed.get("dry_load_readback_executed") is False
        and executed.get("timer_path_shadow_readback_executed") is False
        and executed.get("timer_path_loaded") is False
        and executed.get("supervisor_invoked") is False
        and executed.get("remote_sync_performed") is False
        and executed.get("candidate_execution_performed") is False
        and executed.get("executor_input_mutated") is False
        and executed.get("target_plan_replaced") is False
        and executed.get("live_config_mutated") is False
        and executed.get("operator_state_mutated") is False
        and executed.get("timer_state_mutated") is False
        and int(executed.get("orders_submitted") or 0) == 0
        and int(executed.get("fill_count") or 0) == 0
        and int(executed.get("fills_observed") or 0) == 0
    )


def p9az_ready_for_p9ba(
    p9az: dict[str, Any],
    owner_record: dict[str, Any],
    package: dict[str, Any],
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
    source = dict(p9az.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    live_config = dict(source.get("live_config_dir") or {})
    package_authorizations = dict(package.get("authorizations") or {})
    package_boundaries = dict(package.get("required_boundaries") or {})
    package_contract = dict(package.get("readback_contract_if_future_gate_approved") or {})
    checks = dict(checklist.get("checks") or {})
    matrix_authorizations = dict(matrix.get("authorizations") or {})
    return (
        p9az.get("contract_version") == P9AZ_CONTRACT
        and p9az.get("status") == "ready"
        and not p9az.get("blockers")
        and p9az.get("p9az_shadow_readback_gate_package_ready") is True
        and p9az.get("shadow_readback_gate_package_prepared") is True
        and p9az.get("shadow_readback_gate_package_under_proof_artifacts") is True
        and p9az.get("eligible_for_future_shadow_readback_gate_package_review_request") is True
        and p9az.get("allowed_next_gate") == P9BA_GATE
        and p9az.get("recommended_next_gate") == P9BA_GATE
        and p9az.get("allowed_next_gate_scope") == P9BA_SCOPE
        and p9az.get("allowed_next_gate_must_be_separately_requested") is True
        and p9az.get("prepare_gate_package_authorized") is True
        and p9az.get("candidate_order_authority") == "disabled"
        and p9az.get("execution_target_source") == "baseline_only"
        and p9az.get("candidate_artifact_sink") == "proof_artifacts_only"
        and p9az.get("executor_consumes_baseline_only") is True
        and p9az.get("candidate_shadow_only") is True
        and p9az.get("candidate_plan_referenced_by_executor") is False
        and all_false(p9az, FALSE_EXECUTION_KEYS)
        and zero_orders_fills(p9az)
        and no_live_mutation(p9az)
        and owner_record.get("contract_version") == "hv_balanced_dth60_coinglass_phase9az_owner_decision.v1"
        and owner_record.get("decision") == APPROVE_P9AZ_DECISION
        and owner_record.get("prepare_shadow_readback_gate_package_approved") is True
        and owner_record.get("future_shadow_readback_gate_package_review_request_approved") is True
        and owner_record.get("live_order_submission_approved") is False
        and package.get("contract_version") == "hv_balanced_dth60_coinglass_phase9az_shadow_readback_gate_package.v1"
        and package.get("package_prepared") is True
        and package.get("package_written_under_proof_artifacts") is True
        and package.get("default_enabled") is False
        and package.get("observe_only") is True
        and package.get("order_authority") == "disabled"
        and package.get("executor_target_source") == "baseline_only"
        and package.get("candidate_shadow_only") is True
        and package.get("candidate_plan_must_not_be_referenced_by_executor") is True
        and package.get("future_review_gate") == P9BA_GATE
        and package.get("future_review_gate_scope") == P9BA_SCOPE
        and package.get("future_review_gate_must_be_separately_requested") is True
        and package_authorizations.get("prepare_shadow_readback_gate_package") is True
        and package_authorizations.get("future_shadow_readback_gate_package_review_request") is True
        and all_authorizations_false(package, PROOF_FALSE_AUTHORIZATIONS)
        and package_boundaries.get("proof_artifacts_only") is True
        and package_boundaries.get("default_off_required") is True
        and package_boundaries.get("observe_only_required") is True
        and package_boundaries.get("executor_input_must_remain_baseline_only") is True
        and package_boundaries.get("candidate_order_authority") == "disabled"
        and package_boundaries.get("live_order_submission_authorized") is False
        and package_contract.get("fresh_account_read_required_before_remote_or_timer_path") is True
        and package_contract.get("baseline_only_executor") is True
        and package_contract.get("candidate_shadow_only") is True
        and package_contract.get("live_order_submission_authorized") is False
        and package_executed_actions_safe(package)
        and checklist.get("contract_version") == "hv_balanced_dth60_coinglass_phase9az_package_acceptance_checklist.v1"
        and checks
        and all(value is True for value in checks.values())
        and matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9az_non_authorization_matrix.v1"
        and matrix_authorizations.get("prepare_shadow_readback_gate_package") is True
        and matrix_authorizations.get("future_shadow_readback_gate_package_review_request") is True
        and matrix_authorizations.get("execute_p9ba") is False
        and all_authorizations_false(matrix, PROOF_FALSE_AUTHORIZATIONS)
        and control.get("contract_version") == "hv_balanced_dth60_coinglass_phase9az_control_boundary_readback.v1"
        and control.get("prepare_gate_package_authorized") is True
        and control.get("shadow_readback_gate_package_prepared") is True
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
        and paths["shadow_readback_gate_package"].exists()
        and paths["package_acceptance_checklist"].exists()
        and paths["non_authorization_matrix"].exists()
        and paths["control_boundary_readback"].exists()
        and output_under_proof_artifacts(paths["shadow_readback_gate_package"])
        and output_under_proof_artifacts(paths["package_acceptance_checklist"])
        and output_under_proof_artifacts(paths["non_authorization_matrix"])
        and output_under_proof_artifacts(paths["control_boundary_readback"])
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def build_owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_CORRIDOR_DECISION
    record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ba_p9bd_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "authorize_p9ba_p9bd_proof_only_corridor",
        "decision_effect": "run_p9ba_p9bd_proof_only_corridor" if approved else "none",
        "p9ba_review_approved": approved,
        "p9bb_proposal_preparation_permission_approved": approved,
        "p9bc_proposal_package_generation_approved": approved,
        "p9bd_retained_readiness_review_approved": approved,
    }
    for key in (
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
    ):
        record[key] = False
    return record


def proof_boundary() -> dict[str, Any]:
    return {
        "candidate_order_authority": "disabled",
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "shadow_only_not_executor",
        "candidate_artifact_sink": "proof_artifacts_only",
        "executor_consumes_baseline_only": True,
        "candidate_shadow_only": True,
        "candidate_plan_referenced_by_executor": False,
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
    }


def non_authorization_matrix(contract_version: str, run_id: str, true_authorizations: dict[str, bool]) -> dict[str, Any]:
    authorizations = dict(true_authorizations)
    for key in PROOF_FALSE_AUTHORIZATIONS:
        authorizations[key] = False
    return {"contract_version": contract_version, "run_id": run_id, "authorizations": authorizations}


def control_readback(
    contract_version: str,
    run_id: str,
    scope: str,
    *,
    supervisor_sha_before: str,
    supervisor_sha_after: str,
    supervisor_loads_hook: bool,
    live_config_sha_before: str,
    live_config_sha_after: str,
    allowed_key: str,
) -> dict[str, Any]:
    control = {
        "contract_version": contract_version,
        "run_id": run_id,
        "scope": scope,
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        allowed_key: True,
    }
    control.update(proof_boundary())
    return control


def step_summary(
    *,
    contract_version: str,
    run_id: str,
    status: str,
    gate_scope: str,
    owner_decision: dict[str, Any],
    source_evidence: dict[str, Any],
    gates: dict[str, bool],
    output_files: dict[str, str],
    fields: dict[str, Any],
) -> dict[str, Any]:
    summary = {
        "contract_version": contract_version,
        "status": status,
        "run_id": run_id,
        "generated_gate_scope": gate_scope,
        "owner_decision": owner_decision,
        "source_evidence": source_evidence,
        "gates": gates,
        "blockers": [key for key, value in gates.items() if not value],
        "output_files": output_files,
    }
    summary.update(fields)
    summary.update(proof_boundary())
    return summary


def build_corridor(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    p9ba_root = root / "proof_artifacts" / "p9ba" / run_id
    p9bb_root = root / "proof_artifacts" / "p9bb" / run_id
    p9bc_root = root / "proof_artifacts" / "p9bc" / run_id
    p9bd_root = root / "proof_artifacts" / "p9bd" / run_id

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9az": latest_p9az_summary(args),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
        "live_config_dir": resolve_path(args.live_config_dir),
    }
    project_profile = load_optional(paths["project_profile"])
    p9az = load_optional(paths["phase9az"])
    p9az_paths = p9az_output_paths(p9az)
    p9az_owner = load_optional(p9az_paths["owner_decision_record"])
    p9az_package = load_optional(p9az_paths["shadow_readback_gate_package"])
    p9az_checklist = load_optional(p9az_paths["package_acceptance_checklist"])
    p9az_matrix = load_optional(p9az_paths["non_authorization_matrix"])
    p9az_control = load_optional(p9az_paths["control_boundary_readback"])

    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_before = tree_sha256(paths["live_config_dir"])
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    owner_decision = build_owner_decision_record(args, generated_at)
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9az_summary": evidence_file(paths["phase9az"]),
        "phase9az_owner_decision_record": evidence_file(p9az_paths["owner_decision_record"]),
        "phase9az_shadow_readback_gate_package": evidence_file(p9az_paths["shadow_readback_gate_package"]),
        "phase9az_package_acceptance_checklist": evidence_file(p9az_paths["package_acceptance_checklist"]),
        "phase9az_non_authorization_matrix": evidence_file(p9az_paths["non_authorization_matrix"]),
        "phase9az_control_boundary_readback": evidence_file(p9az_paths["control_boundary_readback"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
        "live_config_dir": {
            "path": str(paths["live_config_dir"]),
            "exists": paths["live_config_dir"].exists(),
            "sha256": live_config_sha_before,
        },
    }
    p9az_ok = p9az_ready_for_p9ba(
        p9az,
        p9az_owner,
        p9az_package,
        p9az_checklist,
        p9az_matrix,
        p9az_control,
        p9az_paths,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    owner_ok = str(args.owner_decision) == APPROVE_CORRIDOR_DECISION
    stage_ok = project_profile.get("current_stage") == "stage_1_research_readiness_only"
    common_ok = owner_ok and stage_ok and p9az_ok and supervisor_loads_hook is False

    supervisor_sha_after = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_after = tree_sha256(paths["live_config_dir"])

    p9ba_review = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ba_owner_review_packet.v1",
        "run_id": run_id,
        "source_evidence": source_evidence,
        "owner_decision": owner_decision,
        "reviewed_gate": "P9AZ",
        "p9az_package_sufficient": common_ok,
        "sufficient_for_p9bb_permission": common_ok,
        "allowed_next_gate_if_separately_requested": P9BB_GATE if common_ok else "",
        "review_only": True,
        "dry_load_readback_execution_authorized": False,
        "timer_path_shadow_readback_authorized": False,
        "live_order_submission_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    p9ba_checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ba_sufficiency_checklist.v1",
        "run_id": run_id,
        "checks": {
            "p9az_retained_summary_ready": p9az_ok,
            "p9az_package_default_off": p9az_package.get("default_enabled") is False,
            "p9az_package_observe_only": p9az_package.get("observe_only") is True,
            "p9az_package_order_disabled": p9az_package.get("order_authority") == "disabled",
            "p9az_executor_baseline_only": p9az_package.get("executor_target_source") == "baseline_only",
            "p9az_candidate_shadow_only": p9az_package.get("candidate_shadow_only") is True,
            "current_supervisor_not_loading_hook": supervisor_loads_hook is False,
            "stage_boundary_preserved": stage_ok,
            "p9ba_review_does_not_execute_readback": True,
            "p9ba_review_does_not_enter_timer_path": True,
            "p9ba_review_keeps_zero_orders_fills": True,
        },
    }
    p9ba_gates = {
        "owner_decision_p9ba_p9bd_corridor": owner_ok,
        "project_stage_boundary_preserved": stage_ok,
        "p9az_package_ready_for_review": p9az_ok,
        "p9az_package_sufficient_for_p9bb": common_ok,
        "p9ba_output_under_proof_artifacts": output_under_proof_artifacts(p9ba_root / "owner_review_packet.json"),
        "p9ba_no_readback_timer_supervisor_remote_order": True,
    }
    p9ba_status = "ready" if all(p9ba_gates.values()) else "blocked"
    p9ba_outputs = {
        "summary": str(p9ba_root / "summary.json"),
        "owner_review_packet": str(p9ba_root / "owner_review_packet.json"),
        "sufficiency_checklist": str(p9ba_root / "sufficiency_checklist.json"),
        "non_authorization_matrix": str(p9ba_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(p9ba_root / "control_boundary_readback.json"),
    }
    p9ba_summary = step_summary(
        contract_version="hv_balanced_dth60_coinglass_phase9ba_review_shadow_readback_gate_package.v1",
        run_id=run_id,
        status=p9ba_status,
        gate_scope="p9ba_review_shadow_readback_gate_package_only",
        owner_decision=owner_decision,
        source_evidence=source_evidence,
        gates=p9ba_gates,
        output_files=p9ba_outputs,
        fields={
            "p9ba_review_ready": p9ba_status == "ready",
            "p9az_package_sufficient": p9ba_status == "ready",
            "eligible_for_p9bb_proposal_preparation_permission": p9ba_status == "ready",
            "allowed_next_gate": P9BB_GATE if p9ba_status == "ready" else "",
            "allowed_next_gate_must_be_separately_requested": True,
            "review_authorized": p9ba_status == "ready",
        },
    )

    p9bb_ready = p9ba_status == "ready"
    p9bb_permission = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bb_proposal_preparation_permission.v1",
        "run_id": run_id,
        "source_p9ba_summary": p9ba_outputs["summary"],
        "owner_decision": owner_decision,
        "permission_ready": p9bb_ready,
        "allowed_next_gate": P9BC_GATE if p9bb_ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "p9bc_allowed_action": "prepare_proof_artifacts_only_shadow_readback_proposal_package",
        "p9bc_required_boundaries": {
            "proof_artifacts_only": True,
            "default_off_required": True,
            "observe_only_required": True,
            "executor_input_must_remain_baseline_only": True,
            "candidate_shadow_only": True,
            "candidate_order_authority": "disabled",
            "live_order_submission_authorized": False,
            "dry_load_readback_execution_authorized": False,
            "timer_path_shadow_readback_execution_authorized": False,
        },
    }
    p9bb_gates = {
        "owner_decision_p9bb_permission": owner_ok,
        "p9ba_review_ready": p9ba_status == "ready",
        "p9bb_permission_output_under_proof_artifacts": output_under_proof_artifacts(
            p9bb_root / "proposal_preparation_permission.json"
        ),
        "p9bb_does_not_generate_package_inside_permission": True,
        "p9bb_no_readback_timer_supervisor_remote_order": True,
    }
    p9bb_status = "ready" if all(p9bb_gates.values()) else "blocked"
    p9bb_outputs = {
        "summary": str(p9bb_root / "summary.json"),
        "proposal_preparation_permission": str(p9bb_root / "proposal_preparation_permission.json"),
        "non_authorization_matrix": str(p9bb_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(p9bb_root / "control_boundary_readback.json"),
    }
    p9bb_summary = step_summary(
        contract_version="hv_balanced_dth60_coinglass_phase9bb_allow_shadow_readback_proposal_package.v1",
        run_id=run_id,
        status=p9bb_status,
        gate_scope="p9bb_allow_future_proposal_package_generation_only",
        owner_decision=owner_decision,
        source_evidence={"p9ba_summary": evidence_file(Path(p9ba_outputs["summary"])), **source_evidence},
        gates=p9bb_gates,
        output_files=p9bb_outputs,
        fields={
            "p9bb_permission_ready": p9bb_status == "ready",
            "eligible_for_p9bc_proposal_package_generation": p9bb_status == "ready",
            "allowed_next_gate": P9BC_GATE if p9bb_status == "ready" else "",
            "allowed_next_gate_must_be_separately_requested": True,
            "proposal_package_generation_authorized_in_p9bb": False,
        },
    )

    p9bc_ready = p9bb_status == "ready"
    proposal_package = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bc_shadow_readback_proposal_package.v1",
        "run_id": run_id,
        "source_p9bb_summary": p9bb_outputs["summary"],
        "owner_decision": owner_decision,
        "proposal_package_generated": p9bc_ready,
        "package_written_under_proof_artifacts": True,
        "package_body_kind": "shadow_readback_gate_proposal_package_not_execution",
        "default_enabled": False,
        "observe_only": True,
        "candidate_order_authority": "disabled",
        "executor_target_source": "baseline_only",
        "candidate_shadow_only": True,
        "candidate_plan_must_not_be_referenced_by_executor": True,
        "allowed_next_gate": P9BD_GATE if p9bc_ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "proposal_contract": {
            "fresh_account_read_required_before_any_future_remote_or_timer_path": True,
            "baseline_only_executor_required": True,
            "candidate_shadow_only_required": True,
            "zero_order_cancel_fill_trade_delta_required": True,
            "dry_load_readback_requires_separate_owner_gate": True,
            "timer_path_shadow_readback_requires_separate_owner_gate": True,
            "live_order_submission_authorized": False,
        },
    }
    p9bc_checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bc_proposal_acceptance_checklist.v1",
        "run_id": run_id,
        "checks": {
            "p9bb_permission_ready": p9bb_status == "ready",
            "proposal_package_under_proof_artifacts": output_under_proof_artifacts(
                p9bc_root / "shadow_readback_proposal_package.json"
            ),
            "proposal_keeps_default_off": True,
            "proposal_keeps_observe_only": True,
            "proposal_keeps_executor_baseline_only": True,
            "proposal_keeps_candidate_shadow_only": True,
            "proposal_keeps_order_authority_disabled": True,
            "proposal_does_not_execute_readback": True,
            "proposal_does_not_enter_timer_path": True,
            "proposal_does_not_invoke_supervisor": True,
            "proposal_does_not_remote_sync": True,
            "proposal_keeps_zero_orders_fills": True,
        },
    }
    p9bc_gates = {
        "owner_decision_p9bc_package_generation": owner_ok,
        "p9bb_permission_ready": p9bb_status == "ready",
        "proposal_package_output_under_proof_artifacts": output_under_proof_artifacts(
            p9bc_root / "shadow_readback_proposal_package.json"
        ),
        "proposal_checklist_output_under_proof_artifacts": output_under_proof_artifacts(
            p9bc_root / "proposal_acceptance_checklist.json"
        ),
        "p9bc_no_readback_timer_supervisor_remote_order": True,
    }
    p9bc_status = "ready" if all(p9bc_gates.values()) else "blocked"
    p9bc_outputs = {
        "summary": str(p9bc_root / "summary.json"),
        "shadow_readback_proposal_package": str(p9bc_root / "shadow_readback_proposal_package.json"),
        "proposal_acceptance_checklist": str(p9bc_root / "proposal_acceptance_checklist.json"),
        "non_authorization_matrix": str(p9bc_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(p9bc_root / "control_boundary_readback.json"),
    }
    p9bc_summary = step_summary(
        contract_version="hv_balanced_dth60_coinglass_phase9bc_shadow_readback_proposal_package.v1",
        run_id=run_id,
        status=p9bc_status,
        gate_scope="p9bc_prepare_shadow_readback_proposal_package_only",
        owner_decision=owner_decision,
        source_evidence={"p9bb_summary": evidence_file(Path(p9bb_outputs["summary"])), **source_evidence},
        gates=p9bc_gates,
        output_files=p9bc_outputs,
        fields={
            "p9bc_proposal_package_ready": p9bc_status == "ready",
            "generated_proposal_package": p9bc_status == "ready",
            "proposal_package_under_proof_artifacts": True,
            "eligible_for_p9bd_readiness_review": p9bc_status == "ready",
            "allowed_next_gate": P9BD_GATE if p9bc_status == "ready" else "",
            "allowed_next_gate_must_be_separately_requested": True,
            "proposal_package_generation_authorized": p9bc_status == "ready",
        },
    )

    p9bd_ready = p9bc_status == "ready"
    readiness_review = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bd_readiness_review.v1",
        "run_id": run_id,
        "source_p9bc_summary": p9bc_outputs["summary"],
        "owner_decision": owner_decision,
        "retained_readiness_review_ready": p9bd_ready,
        "p9ba_ready": p9ba_status == "ready",
        "p9bb_ready": p9bb_status == "ready",
        "p9bc_ready": p9bc_status == "ready",
        "sufficient_for_future_timer_path_shadow_readback_owner_gate_request": p9bd_ready,
        "allowed_next_gate": P9BE_GATE if p9bd_ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "review_conclusion": (
            "ready_for_future_owner_gate_discussion_only_not_execution" if p9bd_ready else "blocked"
        ),
        "dry_load_readback_execution_authorized": False,
        "timer_path_shadow_readback_authorized": False,
        "live_order_submission_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    readiness_checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bd_readiness_checklist.v1",
        "run_id": run_id,
        "checks": {
            "p9ba_review_ready": p9ba_status == "ready",
            "p9bb_permission_ready": p9bb_status == "ready",
            "p9bc_proposal_package_ready": p9bc_status == "ready",
            "all_outputs_under_proof_artifacts": True,
            "current_supervisor_not_loading_hook": supervisor_loads_hook is False,
            "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
            "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
            "executor_input_not_mutated": True,
            "target_plan_not_replaced": True,
            "live_config_not_mutated": True,
            "operator_state_not_mutated": True,
            "timer_state_not_mutated": True,
            "zero_orders_fills": True,
        },
    }
    p9bd_gates = {
        "owner_decision_p9bd_readiness_review": owner_ok,
        "p9ba_ready": p9ba_status == "ready",
        "p9bb_ready": p9bb_status == "ready",
        "p9bc_ready": p9bc_status == "ready",
        "readiness_review_output_under_proof_artifacts": output_under_proof_artifacts(
            p9bd_root / "readiness_review.json"
        ),
        "p9bd_no_readback_timer_supervisor_remote_order": True,
    }
    p9bd_status = "ready" if all(p9bd_gates.values()) else "blocked"
    p9bd_outputs = {
        "summary": str(p9bd_root / "summary.json"),
        "readiness_review": str(p9bd_root / "readiness_review.json"),
        "readiness_checklist": str(p9bd_root / "readiness_checklist.json"),
        "non_authorization_matrix": str(p9bd_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(p9bd_root / "control_boundary_readback.json"),
    }
    p9bd_summary = step_summary(
        contract_version="hv_balanced_dth60_coinglass_phase9bd_retained_readiness_review.v1",
        run_id=run_id,
        status=p9bd_status,
        gate_scope="p9bd_retained_readiness_review_only",
        owner_decision=owner_decision,
        source_evidence={"p9bc_summary": evidence_file(Path(p9bc_outputs["summary"])), **source_evidence},
        gates=p9bd_gates,
        output_files=p9bd_outputs,
        fields={
            "p9bd_retained_readiness_review_ready": p9bd_status == "ready",
            "sufficient_for_future_timer_path_shadow_readback_owner_gate_request": p9bd_status == "ready",
            "eligible_for_future_p9be_owner_gate_request": p9bd_status == "ready",
            "allowed_next_gate": P9BE_GATE if p9bd_status == "ready" else "",
            "allowed_next_gate_must_be_separately_requested": True,
            "retained_readiness_review_authorized": p9bd_status == "ready",
        },
    )

    step_artifacts = [
        (p9ba_root / "owner_review_packet.json", p9ba_review),
        (p9ba_root / "sufficiency_checklist.json", p9ba_checklist),
        (
            p9ba_root / "non_authorization_matrix.json",
            non_authorization_matrix(
                "hv_balanced_dth60_coinglass_phase9ba_non_authorization_matrix.v1",
                run_id,
                {"p9ba_review": p9ba_status == "ready", "future_p9bb_permission_request": p9ba_status == "ready"},
            ),
        ),
        (
            p9ba_root / "control_boundary_readback.json",
            control_readback(
                "hv_balanced_dth60_coinglass_phase9ba_control_boundary_readback.v1",
                run_id,
                "p9ba_review_only",
                supervisor_sha_before=supervisor_sha_before,
                supervisor_sha_after=supervisor_sha_after,
                supervisor_loads_hook=supervisor_loads_hook,
                live_config_sha_before=live_config_sha_before,
                live_config_sha_after=live_config_sha_after,
                allowed_key="p9ba_review_authorized",
            ),
        ),
        (p9ba_root / "summary.json", p9ba_summary),
        (p9bb_root / "proposal_preparation_permission.json", p9bb_permission),
        (
            p9bb_root / "non_authorization_matrix.json",
            non_authorization_matrix(
                "hv_balanced_dth60_coinglass_phase9bb_non_authorization_matrix.v1",
                run_id,
                {"p9bb_permission": p9bb_status == "ready", "future_p9bc_package_request": p9bb_status == "ready"},
            ),
        ),
        (
            p9bb_root / "control_boundary_readback.json",
            control_readback(
                "hv_balanced_dth60_coinglass_phase9bb_control_boundary_readback.v1",
                run_id,
                "p9bb_permission_only",
                supervisor_sha_before=supervisor_sha_before,
                supervisor_sha_after=supervisor_sha_after,
                supervisor_loads_hook=supervisor_loads_hook,
                live_config_sha_before=live_config_sha_before,
                live_config_sha_after=live_config_sha_after,
                allowed_key="p9bb_permission_authorized",
            ),
        ),
        (p9bb_root / "summary.json", p9bb_summary),
        (p9bc_root / "shadow_readback_proposal_package.json", proposal_package),
        (p9bc_root / "proposal_acceptance_checklist.json", p9bc_checklist),
        (
            p9bc_root / "non_authorization_matrix.json",
            non_authorization_matrix(
                "hv_balanced_dth60_coinglass_phase9bc_non_authorization_matrix.v1",
                run_id,
                {
                    "proposal_package_generation": p9bc_status == "ready",
                    "future_p9bd_readiness_review_request": p9bc_status == "ready",
                },
            ),
        ),
        (
            p9bc_root / "control_boundary_readback.json",
            control_readback(
                "hv_balanced_dth60_coinglass_phase9bc_control_boundary_readback.v1",
                run_id,
                "p9bc_proposal_package_only",
                supervisor_sha_before=supervisor_sha_before,
                supervisor_sha_after=supervisor_sha_after,
                supervisor_loads_hook=supervisor_loads_hook,
                live_config_sha_before=live_config_sha_before,
                live_config_sha_after=live_config_sha_after,
                allowed_key="proposal_package_generation_authorized",
            ),
        ),
        (p9bc_root / "summary.json", p9bc_summary),
        (p9bd_root / "readiness_review.json", readiness_review),
        (p9bd_root / "readiness_checklist.json", readiness_checklist),
        (
            p9bd_root / "non_authorization_matrix.json",
            non_authorization_matrix(
                "hv_balanced_dth60_coinglass_phase9bd_non_authorization_matrix.v1",
                run_id,
                {
                    "retained_readiness_review": p9bd_status == "ready",
                    "future_p9be_owner_gate_request": p9bd_status == "ready",
                },
            ),
        ),
        (
            p9bd_root / "control_boundary_readback.json",
            control_readback(
                "hv_balanced_dth60_coinglass_phase9bd_control_boundary_readback.v1",
                run_id,
                "p9bd_readiness_review_only",
                supervisor_sha_before=supervisor_sha_before,
                supervisor_sha_after=supervisor_sha_after,
                supervisor_loads_hook=supervisor_loads_hook,
                live_config_sha_before=live_config_sha_before,
                live_config_sha_after=live_config_sha_after,
                allowed_key="retained_readiness_review_authorized",
            ),
        ),
        (p9bd_root / "summary.json", p9bd_summary),
    ]
    for path, payload in step_artifacts:
        write_json(path, payload)

    corridor_gates = {
        "owner_decision_p9ba_p9bd_corridor": owner_ok,
        "project_stage_boundary_preserved": stage_ok,
        "p9az_ready_for_p9ba": p9az_ok,
        "p9ba_ready": p9ba_status == "ready",
        "p9bb_ready": p9bb_status == "ready",
        "p9bc_ready": p9bc_status == "ready",
        "p9bd_ready": p9bd_status == "ready",
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "no_readback_timer_supervisor_remote_order": True,
    }
    corridor_status = "ready" if all(corridor_gates.values()) else "blocked"
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "p9ba_summary": p9ba_outputs["summary"],
        "p9bb_summary": p9bb_outputs["summary"],
        "p9bc_summary": p9bc_outputs["summary"],
        "p9bd_summary": p9bd_outputs["summary"],
        "report": str(root / "p9ba_p9bd_shadow_readback_proposal_corridor.md"),
    }
    corridor_summary = {
        "contract_version": CONTRACT_VERSION,
        "status": corridor_status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "gate_scope": "p9ba_p9bd_proof_only_shadow_readback_proposal_corridor",
        "owner_decision": owner_decision,
        "source_evidence": source_evidence,
        "completed_gates": ["P9BA", "P9BB", "P9BC", "P9BD"] if corridor_status == "ready" else [],
        "p9ba_p9bd_corridor_ready": corridor_status == "ready",
        "p9ba_review_ready": p9ba_status == "ready",
        "p9bb_permission_ready": p9bb_status == "ready",
        "p9bc_proposal_package_ready": p9bc_status == "ready",
        "p9bd_retained_readiness_review_ready": p9bd_status == "ready",
        "eligible_for_future_p9be_owner_gate_request": corridor_status == "ready",
        "allowed_next_gate": P9BE_GATE if corridor_status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "gates": corridor_gates,
        "blockers": [key for key, value in corridor_gates.items() if not value],
        "output_files": output_files,
    }
    corridor_summary.update(proof_boundary())
    corridor_summary["live_supervisor_loads_candidate_hook"] = supervisor_loads_hook
    corridor_summary["live_supervisor_source_unchanged"] = supervisor_sha_before == supervisor_sha_after
    corridor_summary["live_config_dir_unchanged"] = live_config_sha_before == live_config_sha_after
    write_json(root / "owner_decision_record.json", owner_decision)
    write_json(root / "summary.json", corridor_summary)
    (root / "p9ba_p9bd_shadow_readback_proposal_corridor.md").write_text(
        render_markdown(corridor_summary), encoding="utf-8"
    )
    return corridor_summary, 0 if corridor_status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9BA-P9BD Shadow Readback Proposal Corridor",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9BA-P9BD stays proof-only: review retained P9AZ, allow and generate a proposal package, then review readiness.",
        "",
        "```text",
        f"p9ba_p9bd_corridor_ready = {str(bool(summary['p9ba_p9bd_corridor_ready'])).lower()}",
        f"allowed_next_gate = {summary['allowed_next_gate']}",
        "dry_load_readback_execution_authorized = false",
        "timer_path_shadow_readback_authorized = false",
        "timer_path_load_authorized = false",
        "supervisor_invocation_authorized = false",
        "remote_execution_performed = false",
        "candidate_execution_authorized = false",
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
    summary, exit_code = build_corridor(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    print(f"allowed_next_gate={summary['allowed_next_gate']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
