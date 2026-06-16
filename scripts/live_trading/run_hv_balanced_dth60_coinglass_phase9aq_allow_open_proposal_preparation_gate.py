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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ap_define_next_gate_scope_after_p9am import (  # noqa: E402
    CONTRACT_VERSION as P9AP_CONTRACT,
    NEXT_GATE_ID as P9AQ_GATE,
    NEXT_GATE_SCOPE as P9AQ_DEFINED_SCOPE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9aq_allow_open_proposal_preparation_gate.v1"
APPROVE_P9AQ_DECISION = "approve_p9aq_allow_open_proposal_preparation_gate_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9aq_allow_open_proposal_preparation_gate"
PHASE9AP_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ap_define_next_gate_scope_after_p9am"
P9AR_GATE = (
    "P9AR_open_default_off_observe_only_live_supervisor_timer_path_shadow_readback_"
    "proposal_preparation_gate_only_if_separately_requested"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9AQ as the owner gate that only decides whether a future "
            "proposal-preparation gate may be separately requested. P9AQ does "
            "not prepare a proposal, write a proposal body, execute readback, "
            "load timer paths, invoke the supervisor, mutate live state, remote "
            "sync, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ap-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AQ_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:allow_p9aq_open_proposal_preparation_gate_only")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def int_equals(payload: dict[str, Any], key: str, expected: int) -> bool:
    try:
        return int(payload.get(key)) == expected
    except (TypeError, ValueError):
        return False


def p9ap_ready_for_p9aq(
    summary: dict[str, Any],
    scope_definition: dict[str, Any],
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
    authorizations = dict(matrix.get("authorizations") or {})
    disallowed = dict(scope_definition.get("defined_next_gate_disallowed_actions") or {})
    boundaries = dict(scope_definition.get("defined_next_gate_required_boundaries") or {})
    required_gates = (
        "owner_decision_p9ap_define_scope_only",
        "project_stage_boundary_preserved",
        "p9ao_scope_permission_gate_ready",
        "p9ao_allows_p9ap_scope_definition",
        "p9ao_did_not_define_scope",
        "p9ao_did_not_execute_next_gate",
        "current_live_supervisor_not_loading_hook",
        "current_hook_hash_matches_p9ao_source",
        "current_supervisor_hash_matches_p9ao_source",
        "current_live_config_hash_matches_p9ao_source",
        "next_gate_scope_definition_output_under_proof_artifacts",
        "p9ap_defines_scope_only",
        "p9ap_does_not_execute_defined_next_gate",
        "p9ap_does_not_prepare_proposal",
        "p9ap_does_not_write_proposal_body",
        "p9ap_does_not_execute_dry_load_readback",
        "p9ap_requires_defined_gate_to_be_separately_requested",
        "defined_gate_must_be_proof_artifacts_only",
        "defined_gate_must_keep_order_authority_disabled",
        "defined_gate_must_not_authorize_live_order_submission",
        "defined_gate_must_not_load_live_timer_path",
        "defined_gate_must_not_mutate_executor_input",
        "defined_gate_must_not_replace_target_plan",
        "defined_gate_must_not_remote_sync",
        "no_timer_hook_implementation_in_p9ap",
        "no_hook_deployment_in_p9ap",
        "no_live_timer_path_load_in_p9ap",
        "no_production_timer_service_load_in_p9ap",
        "no_supervisor_run_in_p9ap",
        "no_remote_execution_in_p9ap",
        "no_candidate_execution_in_p9ap",
        "no_executor_input_mutation_in_p9ap",
        "no_target_plan_replacement_in_p9ap",
        "no_live_mutation_in_p9ap",
        "zero_orders_fills_in_p9ap",
    )
    false_summary_keys = (
        "defined_next_gate_authorized_in_p9ap",
        "defined_next_gate_execution_authorized",
        "prepare_proposal_authorized",
        "proposal_body_write_authorized",
        "dry_load_readback_execution_authorized",
        "eligible_for_timer_hook_implementation",
        "eligible_for_hook_deployment",
        "eligible_for_live_timer_path_load",
        "eligible_for_supervisor_invocation",
        "eligible_for_remote_sync",
        "eligible_for_live_order_submission",
        "eligible_for_stage_governance_change",
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
        "target_plan_replaced",
        "wrote_live_hook_config",
        "implemented_hook",
        "deployed_hook",
        "loaded_hook",
        "executor_input_changed",
        "applied_to_live",
        "live_config_changed",
        "operator_state_changed",
        "timer_state_changed",
    )
    false_authorizations = (
        "execute_defined_next_gate",
        "prepare_proposal",
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
    required_disallowed = (
        "execute_next_gate_inside_p9ap",
        "prepare_proposal_inside_p9ap",
        "write_proposal_body_inside_p9ap",
        "execute_dry_load_readback",
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
    return (
        summary.get("contract_version") == P9AP_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9ap_next_gate_scope_definition_ready") is True
        and summary.get("next_gate_scope_defined") is True
        and summary.get("defined_next_gate") == P9AQ_GATE
        and summary.get("defined_next_gate_scope") == P9AQ_DEFINED_SCOPE
        and summary.get("defined_next_gate_must_be_separately_requested") is True
        and summary.get("defined_next_gate_must_be_proof_artifacts_only") is True
        and summary.get("defined_next_gate_must_keep_order_authority_disabled") is True
        and summary.get("defined_next_gate_must_not_authorize_live_order_submission") is True
        and summary.get("defined_next_gate_must_not_load_live_timer_path") is True
        and summary.get("defined_next_gate_must_not_execute_follow_on") is True
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_overlay_execution_path") == "excluded"
        and summary.get("candidate_artifact_sink") == "proof_artifacts_only"
        and summary.get("live_supervisor_source_unchanged") is True
        and summary.get("live_config_dir_unchanged") is True
        and all(summary.get(key) is False for key in false_summary_keys)
        and no_live_mutation(summary)
        and zero_orders_fills(summary)
        and all(gates.get(key) is True for key in required_gates)
        and owner.get("decision") == "approve_p9ap_define_next_gate_scope_after_p9am_only"
        and owner.get("define_next_gate_scope_after_p9am_approved") is True
        and owner.get("execute_defined_next_gate_approved") is False
        and owner.get("prepare_proposal_approved") is False
        and owner.get("proposal_body_write_approved") is False
        and owner.get("dry_load_readback_execution_approved") is False
        and scope_definition.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ap_next_gate_scope_definition.v1"
        and scope_definition.get("defined_next_gate") == P9AQ_GATE
        and scope_definition.get("defined_next_gate_scope") == P9AQ_DEFINED_SCOPE
        and scope_definition.get("defined_next_gate_must_be_separately_requested") is True
        and scope_definition.get("defined_next_gate_executes_in_p9ap") is False
        and scope_definition.get("defined_next_gate_authorized_in_p9ap") is False
        and all(disallowed.get(key) is True for key in required_disallowed)
        and boundaries.get("proof_artifacts_only") is True
        and boundaries.get("default_off_only") is True
        and boundaries.get("observe_only_shadow_artifacts_only") is True
        and boundaries.get("executor_input_must_remain_baseline_only") is True
        and boundaries.get("target_plan_must_not_be_replaced") is True
        and boundaries.get("candidate_plan_must_not_be_referenced_by_executor") is True
        and boundaries.get("candidate_order_authority") == "disabled"
        and boundaries.get("live_order_submission_authorized") is False
        and int_equals(boundaries, "orders_submitted_must_equal", 0)
        and int_equals(boundaries, "fill_count_must_equal", 0)
        and matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ap_non_authorization_matrix.v1"
        and authorizations.get("define_next_gate_scope_after_p9am") is True
        and all(authorizations.get(key) is False for key in false_authorizations)
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9AQ_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aq_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "allow_future_proposal_preparation_gate_to_be_opened_only",
        "decision_effect": "allow_future_p9ar_proposal_preparation_gate_request_only" if approved else "none",
        "future_proposal_preparation_gate_request_approved": approved,
        "open_proposal_preparation_gate_in_p9aq_approved": False,
        "execute_p9ar_approved": False,
        "prepare_proposal_approved": False,
        "proposal_body_write_approved": False,
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


def build_proposal_preparation_gate_permission(
    *,
    run_id: str,
    decision: dict[str, Any],
    source_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aq_proposal_preparation_gate_permission.v1",
        "run_id": run_id,
        "source_evidence": source_evidence,
        "owner_decision": decision,
        "allowed_next_gate": P9AR_GATE,
        "allowed_next_gate_must_be_separately_requested": True,
        "allowed_next_gate_scope": "owner_gated_open_proposal_preparation_gate_only",
        "opened_in_p9aq": False,
        "executed_in_p9aq": False,
        "p9ar_allowed_question": (
            "whether to allow a future proposal-preparation action for a default-off "
            "observe-only live-supervisor timer-path shadow readback proposal"
        ),
        "p9ar_effect_if_approved": (
            "open only the next proposal-preparation step under proof_artifacts; "
            "no proposal body, readback, timer path, supervisor, or order action"
        ),
        "p9ar_required_boundaries": {
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
        "p9ar_disallowed_actions": {
            "execute_p9ar_inside_p9aq": True,
            "prepare_proposal_inside_p9aq": True,
            "write_proposal_body_inside_p9aq": True,
            "execute_dry_load_readback": True,
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


def build_phase9aq(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = (
        resolve_path(args.output_root)
        if str(args.output_root).strip()
        else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    )
    proof_root = output_root / "proof_artifacts" / "p9aq" / run_id

    project_profile_path = resolve_path(args.project_profile)
    phase9ap_path = (
        resolve_path(args.phase9ap_summary)
        if str(args.phase9ap_summary).strip()
        else latest_match(PHASE9AP_PARENT, "*/summary.json")
    )
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)

    project_profile = load_optional(project_profile_path)
    p9ap = load_optional(phase9ap_path)
    scope_path = source_output_path(p9ap, "next_gate_scope_definition")
    matrix_path = source_output_path(p9ap, "non_authorization_matrix")
    p9ap_scope = load_optional(scope_path)
    p9ap_matrix = load_optional(matrix_path)
    hook_sha = file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else ""
    supervisor_sha_before = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    live_config_sha_before = tree_sha256(live_config_dir)
    supervisor_loads_hook = current_supervisor_loads_hook(supervisor_path)
    decision = owner_decision_record(args, generated_at)

    p9ap_ok = p9ap_ready_for_p9aq(
        p9ap,
        p9ap_scope,
        p9ap_matrix,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    source_evidence = {
        "project_profile": evidence_file(project_profile_path),
        "phase9ap_summary": evidence_file(phase9ap_path),
        "phase9ap_next_gate_scope_definition": evidence_file(scope_path),
        "phase9ap_non_authorization_matrix": evidence_file(matrix_path),
        "hook_module": evidence_file(hook_path),
        "live_supervisor": evidence_file(supervisor_path),
        "live_config_dir": {
            "path": str(live_config_dir),
            "exists": live_config_dir.exists(),
            "sha256": live_config_sha_before,
        },
    }
    permission = build_proposal_preparation_gate_permission(
        run_id=run_id,
        decision=decision,
        source_evidence=source_evidence,
    )
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aq_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "future_proposal_preparation_gate_request": str(args.owner_decision) == APPROVE_P9AQ_DECISION,
            "open_proposal_preparation_gate_in_p9aq": False,
            "execute_p9ar": False,
            "prepare_proposal": False,
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
    supervisor_sha_after = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    live_config_sha_after = tree_sha256(live_config_dir)
    control_boundary_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aq_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "allow_future_proposal_preparation_gate_request_only",
        "live_supervisor": source_evidence["live_supervisor"],
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "entered_timer_path": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "timer_service_enabled_or_invoked": False,
        "remote_control_plane_touched": False,
        "candidate_execution_performed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
    }
    gates = {
        "owner_decision_p9aq_allow_open_proposal_preparation_gate_only": str(args.owner_decision)
        == APPROVE_P9AQ_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9ap_scope_definition_ready": p9ap_ok,
        "p9ap_defined_p9aq_only": p9ap.get("defined_next_gate") == P9AQ_GATE
        and p9ap.get("defined_next_gate_scope") == P9AQ_DEFINED_SCOPE,
        "p9ap_did_not_authorize_p9aq_execution": p9ap.get("defined_next_gate_authorized_in_p9ap") is False
        and p9ap.get("defined_next_gate_execution_authorized") is False,
        "p9ap_did_not_prepare_proposal": p9ap.get("prepare_proposal_authorized") is False,
        "p9ap_did_not_write_proposal_body": p9ap.get("proposal_body_write_authorized") is False,
        "p9ap_did_not_execute_readback": p9ap.get("dry_load_readback_execution_authorized") is False,
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "current_hook_hash_matches_p9ap_source": dict(
            dict(p9ap.get("source_evidence") or {}).get("hook_module") or {}
        ).get("sha256")
        == hook_sha,
        "current_supervisor_hash_matches_p9ap_source": dict(
            dict(p9ap.get("source_evidence") or {}).get("live_supervisor") or {}
        ).get("sha256")
        == supervisor_sha_before,
        "current_live_config_hash_matches_p9ap_source": dict(
            dict(p9ap.get("source_evidence") or {}).get("live_config_dir") or {}
        ).get("sha256")
        == live_config_sha_before,
        "permission_gate_output_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "proposal_preparation_gate_permission.json"
        ),
        "p9aq_discusses_opening_only": True,
        "p9aq_does_not_open_p9ar": True,
        "p9aq_does_not_execute_p9ar": True,
        "p9aq_does_not_prepare_proposal": True,
        "p9aq_does_not_write_proposal_body": True,
        "p9aq_does_not_execute_dry_load_readback": True,
        "p9ar_must_be_separately_requested": True,
        "p9ar_must_be_proof_artifacts_only": True,
        "p9ar_must_keep_default_off": True,
        "p9ar_must_keep_observe_only": True,
        "p9ar_must_keep_order_authority_disabled": True,
        "no_timer_hook_implementation_in_p9aq": True,
        "no_hook_deployment_in_p9aq": True,
        "no_live_timer_path_load_in_p9aq": True,
        "no_production_timer_service_load_in_p9aq": True,
        "no_supervisor_run_in_p9aq": True,
        "no_remote_execution_in_p9aq": True,
        "no_candidate_execution_in_p9aq": True,
        "no_executor_input_mutation_in_p9aq": True,
        "no_target_plan_replacement_in_p9aq": True,
        "no_live_mutation_in_p9aq": True,
        "zero_orders_fills_in_p9aq": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    ready = status == "ready"

    write_json(output_root / "owner_decision_record.json", decision)
    write_json(proof_root / "proposal_preparation_gate_permission.json", permission)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix)
    write_json(proof_root / "control_boundary_readback.json", control_boundary_readback)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "gate_scope": "p9aq_allow_future_proposal_preparation_gate_request_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9aq_allow_open_proposal_preparation_gate_ready": ready,
        "eligible_for_future_proposal_preparation_gate_request": ready,
        "allowed_next_gate": P9AR_GATE if ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "opened_proposal_preparation_gate": False,
        "open_proposal_preparation_gate_in_p9aq_authorized": False,
        "proposal_preparation_gate_execution_authorized": False,
        "prepare_proposal_authorized": False,
        "proposal_body_write_authorized": False,
        "dry_load_readback_execution_authorized": False,
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
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_supervisor_source_unchanged": control_boundary_readback["live_supervisor_source_unchanged"],
        "live_config_dir_unchanged": control_boundary_readback["live_config_dir_unchanged"],
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
        "recommended_next_gate": P9AR_GATE if ready else "",
        "proof_root": str(proof_root),
        "gates": gates,
        "blockers": blockers,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "owner_decision_record": str(output_root / "owner_decision_record.json"),
            "proposal_preparation_gate_permission": str(proof_root / "proposal_preparation_gate_permission.json"),
            "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
            "report": str(output_root / "p9aq_allow_open_proposal_preparation_gate.md"),
        },
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9aq_allow_open_proposal_preparation_gate.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9AQ Allow Open Proposal-Preparation Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9AQ only decides whether a future proposal-preparation gate may be separately requested.",
        "",
        "```text",
        f"allowed_next_gate = {summary['allowed_next_gate']}",
        "opened_proposal_preparation_gate = false",
        "proposal_preparation_gate_execution_authorized = false",
        "prepare_proposal_authorized = false",
        "proposal_body_write_authorized = false",
        "dry_load_readback_execution_authorized = false",
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
    summary, exit_code = build_phase9aq(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
