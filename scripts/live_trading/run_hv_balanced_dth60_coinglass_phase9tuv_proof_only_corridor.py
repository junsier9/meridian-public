from __future__ import annotations

import argparse
import hashlib
import json
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor.v1"
PHASE9S_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9s_next_gate_scope_definition"
PROJECT_PROFILE = "config/project_governance/project_profile.json"
HOOK_MODULE = "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"
SUPERVISOR_PATH = "src/enhengclaw/live_trading/mainnet_live_supervisor.py"
LIVE_CONFIG_DIR = "config/live_trading"

P9T_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9t_prepare_shadow_hook_load_proposal_gate"
P9U_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9u_shadow_hook_load_proposal_package"
P9V_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9v_dry_load_readiness_review"
CORRIDOR_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9tuv_proof_only_corridor"

APPROVE_P9T = "approve_p9t_prepare_default_off_shadow_hook_load_proposal_package_only"
APPROVE_P9U = "approve_p9u_generate_default_off_shadow_hook_load_proposal_package_only"
APPROVE_P9V = "approve_p9v_local_retained_dry_load_readiness_review_only"

P9T_GATE = "P9T_owner_gate_prepare_default_off_live_supervisor_shadow_hook_load_proposal_only"
P9U_GATE = "P9U_generate_default_off_live_supervisor_shadow_hook_load_proposal_package_only"
P9V_GATE = "P9V_local_retained_evidence_dry_load_readiness_review_only"
P9W_GATE = "P9W_owner_gate_default_off_timer_path_dry_load_execution_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the owner-authorized P9T/P9U/P9V proof-only corridor. "
            "The corridor stops before remote sync, timer-path load, supervisor "
            "execution, executor mutation, config mutation, target-plan replacement, "
            "or order authority."
        )
    )
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9s-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--output-root", default="")
    parser.add_argument("--artifacts-root", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision-source", default="user_chat:authorize_p9t_p9u_p9v_proof_only_corridor")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def bool_false(payload: dict[str, Any], key: str) -> bool:
    return payload.get(key) is False


def int_equals(payload: dict[str, Any], key: str, expected: int) -> bool:
    try:
        return int(payload.get(key)) == expected
    except (TypeError, ValueError):
        return False


def tree_sha256(path: Path) -> str:
    resolved = resolve_path(path)
    if not resolved.exists():
        return ""
    if resolved.is_file():
        return file_sha256(resolved)
    digest = hashlib.sha256()
    for file_path in sorted(p for p in resolved.rglob("*") if p.is_file()):
        relative = file_path.relative_to(resolved).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def phase_root(args: argparse.Namespace, default_parent: str, phase_name: str, run_id: str) -> Path:
    if str(getattr(args, "artifacts_root", "")).strip():
        return resolve_path(args.artifacts_root) / phase_name / run_id
    return resolve_path(default_parent) / run_id


def p9s_ready(
    summary: dict[str, Any],
    scope_definition: dict[str, Any],
    matrix: dict[str, Any],
    *,
    current_hook_sha256: str,
    current_supervisor_sha256: str,
    current_supervisor_loads_candidate_hook: bool,
) -> bool:
    source = dict(summary.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    owner = dict(summary.get("owner_decision") or {})
    authorizations = dict(matrix.get("authorizations") or {})
    gates = dict(summary.get("gates") or {})
    boundaries = dict(scope_definition.get("defined_next_gate_required_boundaries") or {})
    disallowed = dict(scope_definition.get("defined_next_gate_disallowed_actions") or {})
    required_gates = (
        "owner_decision_p9s_define_scope_only",
        "project_stage_boundary_preserved",
        "p9q_owner_gate_ready",
        "p9q_allows_p9s_scope_definition",
        "p9q_did_not_define_scope",
        "p9q_did_not_execute_next_gate",
        "current_live_supervisor_not_loading_hook",
        "current_hook_hash_matches_p9q_source",
        "current_supervisor_hash_matches_p9q_source",
        "next_gate_scope_definition_output_under_proof_artifacts",
        "p9s_defines_scope_only",
        "p9s_does_not_execute_defined_next_gate",
        "p9s_does_not_prepare_proposal",
        "p9s_requires_defined_gate_to_be_separately_requested",
        "defined_gate_must_be_proof_artifacts_only",
        "defined_gate_must_keep_order_authority_disabled",
        "defined_gate_must_not_authorize_live_order_submission",
        "defined_gate_must_not_load_live_timer_path",
        "defined_gate_must_not_mutate_executor_input",
        "defined_gate_must_not_replace_target_plan",
        "defined_gate_must_not_remote_sync",
        "no_timer_hook_implementation_in_p9s",
        "no_hook_deployment_in_p9s",
        "no_live_timer_path_load_in_p9s",
        "no_supervisor_run_in_p9s",
        "no_remote_execution_in_p9s",
        "no_executor_input_mutation_in_p9s",
        "no_target_plan_replacement_in_p9s",
        "no_live_mutation_in_p9s",
        "zero_orders_fills_in_p9s",
    )
    return (
        summary.get("contract_version") == "hv_balanced_dth60_coinglass_phase9s_define_next_gate_scope.v1"
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9s_next_gate_scope_definition_ready") is True
        and summary.get("next_gate_scope_defined") is True
        and summary.get("defined_next_gate")
        == "P9T_owner_gate_prepare_default_off_live_supervisor_shadow_hook_load_proposal_only_if_separately_requested"
        and summary.get("defined_next_gate_authorized_in_p9s") is False
        and summary.get("defined_next_gate_execution_authorized") is False
        and summary.get("prepare_proposal_authorized") is False
        and summary.get("defined_next_gate_must_be_separately_requested") is True
        and summary.get("defined_next_gate_must_be_proof_artifacts_only") is True
        and summary.get("defined_next_gate_must_keep_order_authority_disabled") is True
        and summary.get("defined_next_gate_must_not_authorize_live_order_submission") is True
        and summary.get("defined_next_gate_must_not_load_live_timer_path") is True
        and summary.get("timer_path_load_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("supervisor_run_authorized") is False
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_artifact_sink") == "proof_artifacts_only"
        and summary.get("live_supervisor_loads_candidate_hook") is False
        and summary.get("live_supervisor_source_unchanged") is True
        and summary.get("live_timer_path_loaded") is False
        and summary.get("live_timer_service_enabled_or_invoked") is False
        and summary.get("ran_supervisor") is False
        and summary.get("timer_path_invoked") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("remote_control_plane_touched") is False
        and summary.get("wrote_live_hook_config") is False
        and summary.get("implemented_hook") is False
        and summary.get("deployed_hook") is False
        and summary.get("loaded_hook") is False
        and summary.get("target_plan_replaced") is False
        and summary.get("executor_input_changed") is False
        and no_live_mutation(summary)
        and zero_orders_fills(summary)
        and owner.get("decision") == "approve_p9s_define_next_gate_scope_only"
        and owner.get("define_next_gate_scope_approved") is True
        and owner.get("execute_defined_next_gate_approved") is False
        and owner.get("prepare_proposal_approved") is False
        and owner.get("timer_hook_implementation_approved") is False
        and owner.get("hook_deployment_approved") is False
        and owner.get("live_timer_path_load_approved") is False
        and owner.get("live_order_submission_approved") is False
        and owner.get("target_plan_replacement_approved") is False
        and owner.get("executor_input_mutation_approved") is False
        and owner.get("live_config_mutation_approved") is False
        and owner.get("operator_state_mutation_approved") is False
        and owner.get("timer_or_service_mutation_approved") is False
        and owner.get("remote_sync_approved") is False
        and owner.get("supervisor_run_approved") is False
        and owner.get("repo_stage_change_approved") is False
        and scope_definition.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9s_next_gate_scope_definition.v1"
        and scope_definition.get("defined_next_gate")
        == "P9T_owner_gate_prepare_default_off_live_supervisor_shadow_hook_load_proposal_only_if_separately_requested"
        and scope_definition.get("defined_next_gate_must_be_separately_requested") is True
        and scope_definition.get("defined_next_gate_executes_in_p9s") is False
        and scope_definition.get("defined_next_gate_authorized_in_p9s") is False
        and boundaries.get("proof_artifacts_only") is True
        and boundaries.get("default_off_only") is True
        and boundaries.get("executor_input_must_remain_baseline_only") is True
        and boundaries.get("target_plan_must_not_be_replaced") is True
        and boundaries.get("candidate_plan_must_not_be_referenced_by_executor") is True
        and boundaries.get("candidate_order_authority") == "disabled"
        and int_equals(boundaries, "orders_submitted_must_equal", 0)
        and int_equals(boundaries, "fill_count_must_equal", 0)
        and all(disallowed.get(key) is True for key in (
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
        ))
        and authorizations.get("define_next_gate_scope") is True
        and authorizations.get("execute_defined_next_gate") is False
        and authorizations.get("prepare_proposal") is False
        and authorizations.get("timer_hook_implementation") is False
        and authorizations.get("hook_deployment") is False
        and authorizations.get("live_timer_path_load") is False
        and authorizations.get("live_order_submission") is False
        and authorizations.get("target_plan_replacement") is False
        and authorizations.get("executor_input_mutation") is False
        and authorizations.get("live_config_mutation") is False
        and authorizations.get("operator_state_mutation") is False
        and authorizations.get("timer_or_service_mutation") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("supervisor_run") is False
        and authorizations.get("stage_governance_change") is False
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and current_supervisor_loads_candidate_hook is False
        and all(gates.get(key) is True for key in required_gates)
    )


def p9t_ready(summary: dict[str, Any], permission_gate: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == "hv_balanced_dth60_coinglass_phase9t_prepare_proposal_gate.v1"
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("proposal_preparation_authorized") is True
        and summary.get("proposal_package_prepared_in_p9t") is False
        and summary.get("allowed_next_gate") == P9U_GATE
        and summary.get("timer_path_load_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("supervisor_run_authorized") is False
        and zero_orders_fills(summary)
        and no_live_mutation(summary)
        and permission_gate.get("allowed_next_gate") == P9U_GATE
        and permission_gate.get("prepared_in_p9t") is False
        and permission_gate.get("proof_artifacts_only") is True
    )


def p9u_ready(summary: dict[str, Any], package: dict[str, Any]) -> bool:
    boundaries = dict(package.get("required_boundaries") or {})
    return (
        summary.get("contract_version") == "hv_balanced_dth60_coinglass_phase9u_proposal_package.v1"
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("proposal_review_package_ready") is True
        and summary.get("generated_proposal_review_package") is True
        and summary.get("execute_proposal_authorized") is False
        and summary.get("allowed_next_gate") == P9V_GATE
        and summary.get("timer_path_load_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("supervisor_run_authorized") is False
        and zero_orders_fills(summary)
        and no_live_mutation(summary)
        and package.get("proposal_mode") == "default_off_observe_only_shadow_hook_load_path"
        and package.get("proposal_written_under_proof_artifacts") is True
        and package.get("proposal_executes_anything") is False
        and boundaries.get("proof_artifacts_only") is True
        and boundaries.get("default_off_only") is True
        and boundaries.get("executor_input_must_remain_baseline_only") is True
        and boundaries.get("live_config_mutation_allowed") is False
        and boundaries.get("live_timer_path_load_allowed") is False
        and boundaries.get("order_submission_allowed") is False
    )


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
    return {
        "contract_version": f"hv_balanced_dth60_coinglass_{phase}_owner_decision.v1",
        "owner": owner,
        "decision": decision,
        "decision_source": source,
        "recorded_at_utc": iso_z(started_at),
        "decision_question": question,
        "decision_effect": effect,
        allow_key: True,
        "execute_current_gate_follow_on_approved": False,
        "timer_hook_implementation_approved": False,
        "hook_deployment_approved": False,
        "live_timer_path_load_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "remote_sync_approved": False,
        "supervisor_run_approved": False,
        "repo_stage_change_approved": False,
    }


def common_execution_boundary() -> dict[str, Any]:
    return {
        "eligible_for_timer_hook_implementation": False,
        "eligible_for_hook_deployment": False,
        "eligible_for_live_timer_path_load": False,
        "eligible_for_live_order_submission": False,
        "eligible_for_stage_governance_change": False,
        "timer_hook_implementation_authorized": False,
        "hook_deployment_authorized": False,
        "timer_path_load_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "remote_sync_authorized": False,
        "supervisor_run_authorized": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "excluded",
        "candidate_artifact_sink": "proof_artifacts_only",
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
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
        "target_plan_replaced": False,
        "executor_input_changed": False,
    }


def build_p9t(args: argparse.Namespace, *, started_at: datetime, run_id: str) -> tuple[dict[str, Any], int]:
    root = phase_root(args, P9T_PARENT, "p9t_prepare_shadow_hook_load_proposal_gate", run_id)
    proof_root = root / "proof_artifacts" / "p9t" / run_id
    phase9s_path = resolve_path(args.phase9s_summary) if args.phase9s_summary else latest_match(PHASE9S_PARENT, "*/summary.json")
    p9s = load_optional(phase9s_path)
    p9s_scope_path = source_output_path(p9s, "next_gate_scope_definition")
    p9s_matrix_path = source_output_path(p9s, "non_authorization_matrix")
    p9s_scope = load_optional(p9s_scope_path)
    p9s_matrix = load_optional(p9s_matrix_path)
    project_profile = load_optional(resolve_path(args.project_profile))
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    hook_sha = file_sha256(hook_path) if hook_path.exists() else ""
    supervisor_sha = file_sha256(supervisor_path) if supervisor_path.exists() else ""
    supervisor_loads = current_supervisor_loads_hook(supervisor_path)
    p9s_ok = p9s_ready(
        p9s,
        p9s_scope,
        p9s_matrix,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha,
        current_supervisor_loads_candidate_hook=supervisor_loads,
    )
    source_evidence = {
        "project_profile": evidence_file(resolve_path(args.project_profile)),
        "phase9s_summary": evidence_file(phase9s_path),
        "phase9s_next_gate_scope_definition": evidence_file(p9s_scope_path),
        "phase9s_non_authorization_matrix": evidence_file(p9s_matrix_path),
        "hook_module": evidence_file(hook_path),
        "live_supervisor": evidence_file(supervisor_path),
    }
    decision = owner_decision(
        phase="phase9t",
        owner=args.owner,
        source=args.owner_decision_source,
        started_at=started_at,
        decision=APPROVE_P9T,
        question="allow_preparing_default_off_shadow_hook_load_proposal_package_only",
        effect="authorize_p9u_to_generate_proposal_package_only",
        allow_key="proposal_preparation_permission_approved",
    )
    permission_gate = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9t_proposal_preparation_permission_gate.v1",
        "run_id": run_id,
        "source_evidence": source_evidence,
        "owner_decision": decision,
        "allowed_next_action": "generate_default_off_shadow_hook_load_proposal_package",
        "allowed_next_gate": P9U_GATE,
        "prepared_in_p9t": False,
        "executed_in_p9t": False,
        "proof_artifacts_only": True,
        "constraints": {
            "must_consume_p9s_proof": True,
            "must_generate_package_under_proof_artifacts": True,
            "must_not_execute_proposal": True,
            "must_not_implement_hook": True,
            "must_not_deploy_hook": True,
            "must_not_load_live_timer_path": True,
            "must_not_run_supervisor": True,
            "must_not_mutate_executor_input": True,
            "must_not_replace_target_plan": True,
            "must_not_mutate_live_config": True,
            "must_not_mutate_operator_state": True,
            "must_not_remote_sync": True,
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
        },
    }
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9t_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "proposal_preparation_permission": True,
            "generate_proposal_package_in_p9t": False,
            "execute_proposal": False,
            "timer_hook_implementation": False,
            "hook_deployment": False,
            "live_timer_path_load": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "remote_sync": False,
            "supervisor_run": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9t_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "proposal_preparation_permission_only",
        "live_supervisor_sha256_before": supervisor_sha,
        "live_supervisor_sha256_after": file_sha256(supervisor_path) if supervisor_path.exists() else "",
        "live_supervisor_source_unchanged": True,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "remote_control_plane_touched": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    control["live_supervisor_source_unchanged"] = control["live_supervisor_sha256_before"] == control["live_supervisor_sha256_after"]
    gates = {
        "owner_decision_p9t_prepare_proposal_only": True,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9s_scope_definition_ready": p9s_ok,
        "p9s_defined_p9t": p9s.get("defined_next_gate") == "P9T_owner_gate_prepare_default_off_live_supervisor_shadow_hook_load_proposal_only_if_separately_requested",
        "current_live_supervisor_not_loading_hook": supervisor_loads is False,
        "proposal_permission_output_under_proof_artifacts": output_under_proof_artifacts(proof_root / "proposal_preparation_permission_gate.json"),
        "p9t_authorizes_p9u_only": True,
        "p9t_does_not_prepare_package": True,
        "p9t_does_not_execute_proposal": True,
        "no_timer_hook_implementation_in_p9t": True,
        "no_hook_deployment_in_p9t": True,
        "no_live_timer_path_load_in_p9t": True,
        "no_supervisor_run_in_p9t": True,
        "no_remote_execution_in_p9t": True,
        "no_executor_input_mutation_in_p9t": True,
        "no_target_plan_replacement_in_p9t": True,
        "no_live_mutation_in_p9t": True,
        "zero_orders_fills_in_p9t": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "proposal_preparation_permission_gate.json", permission_gate)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix)
    write_json(proof_root / "control_boundary_readback.json", control)
    summary = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9t_prepare_proposal_gate.v1",
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "gate_scope": "p9t_prepare_proposal_package_permission_only",
        "source_evidence": source_evidence,
        "owner_decision": decision,
        "p9t_prepare_proposal_gate_ready": status == "ready",
        "proposal_preparation_authorized": status == "ready",
        "proposal_package_prepared_in_p9t": False,
        "allowed_next_gate": P9U_GATE,
        "recommended_next_gate": P9U_GATE,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_supervisor_source_unchanged": control["live_supervisor_source_unchanged"],
        "gates": gates,
        "blockers": blockers,
        **common_execution_boundary(),
        "proof_root": str(proof_root),
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "proposal_preparation_permission_gate": str(proof_root / "proposal_preparation_permission_gate.json"),
            "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        },
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def build_p9u(
    args: argparse.Namespace,
    *,
    started_at: datetime,
    run_id: str,
    p9t_summary: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    root = phase_root(args, P9U_PARENT, "p9u_shadow_hook_load_proposal_package", run_id)
    proof_root = root / "proof_artifacts" / "p9u" / run_id
    p9t_permission_path = source_output_path(p9t_summary, "proposal_preparation_permission_gate")
    p9t_permission = load_optional(p9t_permission_path)
    project_profile = load_optional(resolve_path(args.project_profile))
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    supervisor_loads = current_supervisor_loads_hook(supervisor_path)
    source_evidence = {
        "project_profile": evidence_file(resolve_path(args.project_profile)),
        "phase9t_summary": evidence_file(source_output_path(p9t_summary, "summary")),
        "phase9t_proposal_preparation_permission_gate": evidence_file(p9t_permission_path),
        "hook_module": evidence_file(hook_path),
        "live_supervisor": evidence_file(supervisor_path),
    }
    decision = owner_decision(
        phase="phase9u",
        owner=args.owner,
        source=args.owner_decision_source,
        started_at=started_at,
        decision=APPROVE_P9U,
        question="generate_default_off_shadow_hook_load_proposal_package_only",
        effect="write_proposal_review_package_under_proof_artifacts_only",
        allow_key="proposal_package_generation_approved",
    )
    p9t_ok = p9t_ready(p9t_summary, p9t_permission)
    proposal_package = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9u_proposal_review_package.v1",
        "run_id": run_id,
        "source_evidence": source_evidence,
        "owner_decision": decision,
        "proposal_mode": "default_off_observe_only_shadow_hook_load_path",
        "proposal_written_under_proof_artifacts": True,
        "proposal_executes_anything": False,
        "proposal_target": {
            "hook_module": "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py",
            "supervisor_path": "src/enhengclaw/live_trading/mainnet_live_supervisor.py",
            "default_enabled": False,
            "artifact_sink": "proof_artifacts_only",
            "executor_target_source": "baseline_only",
        },
        "required_boundaries": {
            "proof_artifacts_only": True,
            "default_off_only": True,
            "observe_only_shadow_artifacts_only": True,
            "executor_input_must_remain_baseline_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "target_plan_must_not_be_replaced": True,
            "live_config_mutation_allowed": False,
            "live_timer_path_load_allowed": False,
            "supervisor_run_allowed": False,
            "remote_sync_allowed": False,
            "order_submission_allowed": False,
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
        },
        "future_review": {
            "allowed_next_gate": P9V_GATE,
            "purpose": "local retained-evidence dry-load readiness review only",
            "must_not_enter_timer_path": True,
            "must_not_mutate_executor": True,
            "must_not_mutate_config": True,
        },
    }
    checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9u_proposal_acceptance_checklist.v1",
        "run_id": run_id,
        "checks": {
            "proposal_package_under_proof_artifacts": True,
            "proposal_default_off": True,
            "proposal_observe_only": True,
            "proposal_does_not_execute": True,
            "executor_input_baseline_only": True,
            "target_plan_not_replaced": True,
            "live_config_not_changed": True,
            "timer_path_not_loaded": True,
            "supervisor_not_run": True,
            "remote_not_touched": True,
            "orders_fills_zero": True,
        },
    }
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9u_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "generate_proposal_review_package": True,
            "execute_proposal": False,
            "timer_hook_implementation": False,
            "hook_deployment": False,
            "live_timer_path_load": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "remote_sync": False,
            "supervisor_run": False,
            "stage_governance_change": False,
        },
    }
    supervisor_sha_before = file_sha256(supervisor_path) if supervisor_path.exists() else ""
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9u_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "proposal_package_generation_only",
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": file_sha256(supervisor_path) if supervisor_path.exists() else "",
        "live_supervisor_source_unchanged": True,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "remote_control_plane_touched": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    control["live_supervisor_source_unchanged"] = control["live_supervisor_sha256_before"] == control["live_supervisor_sha256_after"]
    gates = {
        "owner_decision_p9u_generate_package_only": True,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9t_prepare_proposal_gate_ready": p9t_ok,
        "p9t_authorizes_p9u": p9t_summary.get("allowed_next_gate") == P9U_GATE,
        "proposal_package_output_under_proof_artifacts": output_under_proof_artifacts(proof_root / "proposal_review_package.json"),
        "proposal_package_generated": True,
        "proposal_package_default_off": True,
        "proposal_package_does_not_execute": True,
        "current_live_supervisor_not_loading_hook": supervisor_loads is False,
        "no_timer_hook_implementation_in_p9u": True,
        "no_hook_deployment_in_p9u": True,
        "no_live_timer_path_load_in_p9u": True,
        "no_supervisor_run_in_p9u": True,
        "no_remote_execution_in_p9u": True,
        "no_executor_input_mutation_in_p9u": True,
        "no_target_plan_replacement_in_p9u": True,
        "no_live_mutation_in_p9u": True,
        "zero_orders_fills_in_p9u": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "proposal_review_package.json", proposal_package)
    write_json(proof_root / "proposal_acceptance_checklist.json", checklist)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix)
    write_json(proof_root / "control_boundary_readback.json", control)
    summary = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9u_proposal_package.v1",
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "gate_scope": "p9u_generate_proposal_review_package_only",
        "source_evidence": source_evidence,
        "owner_decision": decision,
        "proposal_review_package_ready": status == "ready",
        "generated_proposal_review_package": status == "ready",
        "execute_proposal_authorized": False,
        "allowed_next_gate": P9V_GATE,
        "recommended_next_gate": P9V_GATE,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_supervisor_source_unchanged": control["live_supervisor_source_unchanged"],
        "gates": gates,
        "blockers": blockers,
        **common_execution_boundary(),
        "proof_root": str(proof_root),
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "proposal_review_package": str(proof_root / "proposal_review_package.json"),
            "proposal_acceptance_checklist": str(proof_root / "proposal_acceptance_checklist.json"),
            "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        },
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def build_p9v(
    args: argparse.Namespace,
    *,
    started_at: datetime,
    run_id: str,
    p9u_summary: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    root = phase_root(args, P9V_PARENT, "p9v_dry_load_readiness_review", run_id)
    proof_root = root / "proof_artifacts" / "p9v" / run_id
    package_path = source_output_path(p9u_summary, "proposal_review_package")
    package = load_optional(package_path)
    project_profile = load_optional(resolve_path(args.project_profile))
    supervisor_path = resolve_path(args.supervisor)
    live_config_path = resolve_path(args.live_config_dir)
    supervisor_sha_before = file_sha256(supervisor_path) if supervisor_path.exists() else ""
    config_sha_before = tree_sha256(live_config_path)
    supervisor_loads = current_supervisor_loads_hook(supervisor_path)
    p9u_ok = p9u_ready(p9u_summary, package)
    source_evidence = {
        "project_profile": evidence_file(resolve_path(args.project_profile)),
        "phase9u_summary": evidence_file(source_output_path(p9u_summary, "summary")),
        "phase9u_proposal_review_package": evidence_file(package_path),
        "hook_module": evidence_file(resolve_path(args.hook_module)),
        "live_supervisor": evidence_file(supervisor_path),
        "live_config_dir": {"path": str(live_config_path), "exists": live_config_path.exists(), "sha256": config_sha_before},
    }
    decision = owner_decision(
        phase="phase9v",
        owner=args.owner,
        source=args.owner_decision_source,
        started_at=started_at,
        decision=APPROVE_P9V,
        question="run_local_retained_evidence_dry_load_readiness_review_only",
        effect="review_readiness_without_entering_timer_path_or_mutating_executor_or_config",
        allow_key="dry_load_readiness_review_approved",
    )
    review = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9v_dry_load_readiness_review.v1",
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
            "future_gate_required_before_any_timer_path_execution": True,
            "future_gate_must_stay_default_off": True,
            "future_gate_must_keep_executor_baseline_only": True,
            "future_gate_must_keep_order_authority_disabled": True,
        },
    }
    checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9v_readiness_checklist.v1",
        "run_id": run_id,
        "checks": {
            "p9u_package_ready": p9u_ok,
            "timer_path_not_entered": True,
            "supervisor_not_run": True,
            "executor_input_not_mutated": True,
            "live_config_not_mutated": True,
            "live_config_digest_unchanged": True,
            "live_supervisor_source_unchanged": True,
            "remote_not_touched": True,
            "orders_fills_zero": True,
        },
    }
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9v_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "dry_load_readiness_review": True,
            "dry_load_execution": False,
            "timer_hook_implementation": False,
            "hook_deployment": False,
            "live_timer_path_load": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "remote_sync": False,
            "supervisor_run": False,
            "stage_governance_change": False,
        },
    }
    supervisor_sha_after = file_sha256(supervisor_path) if supervisor_path.exists() else ""
    config_sha_after = tree_sha256(live_config_path)
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9v_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "local_retained_evidence_dry_load_readiness_review_only",
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_config_dir_sha256_before": config_sha_before,
        "live_config_dir_sha256_after": config_sha_after,
        "live_config_dir_unchanged": config_sha_before == config_sha_after,
        "entered_timer_path": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "remote_control_plane_touched": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    gates = {
        "owner_decision_p9v_readiness_review_only": True,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9u_proposal_package_ready": p9u_ok,
        "proposal_package_under_proof_artifacts": output_under_proof_artifacts(package_path),
        "readiness_review_output_under_proof_artifacts": output_under_proof_artifacts(proof_root / "dry_load_readiness_review.json"),
        "timer_path_not_entered": True,
        "supervisor_not_run": True,
        "executor_input_not_mutated": True,
        "live_config_not_mutated": True,
        "live_config_digest_unchanged": control["live_config_dir_unchanged"],
        "live_supervisor_source_unchanged": control["live_supervisor_source_unchanged"],
        "current_live_supervisor_not_loading_hook": supervisor_loads is False,
        "no_timer_hook_implementation_in_p9v": True,
        "no_hook_deployment_in_p9v": True,
        "no_live_timer_path_load_in_p9v": True,
        "no_remote_execution_in_p9v": True,
        "no_target_plan_replacement_in_p9v": True,
        "no_live_mutation_in_p9v": True,
        "zero_orders_fills_in_p9v": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "dry_load_readiness_review.json", review)
    write_json(proof_root / "dry_load_readiness_checklist.json", checklist)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix)
    write_json(proof_root / "control_boundary_readback.json", control)
    summary = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9v_dry_load_readiness_review.v1",
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "gate_scope": "p9v_local_retained_evidence_dry_load_readiness_review_only",
        "source_evidence": source_evidence,
        "owner_decision": decision,
        "p9v_dry_load_readiness_review_ready": status == "ready",
        "reviewed_only_retained_evidence": True,
        "entered_timer_path": False,
        "dry_load_executed": False,
        "executor_input_mutated": False,
        "live_config_mutated": False,
        "live_config_dir_unchanged": control["live_config_dir_unchanged"],
        "allowed_next_gate": P9W_GATE,
        "recommended_next_gate": P9W_GATE,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_supervisor_source_unchanged": control["live_supervisor_source_unchanged"],
        "gates": gates,
        "blockers": blockers,
        **common_execution_boundary(),
        "proof_root": str(proof_root),
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "dry_load_readiness_review": str(proof_root / "dry_load_readiness_review.json"),
            "dry_load_readiness_checklist": str(proof_root / "dry_load_readiness_checklist.json"),
            "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        },
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def build_corridor(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    p9t, p9t_code = build_p9t(args, started_at=started_at, run_id=run_id)
    p9u: dict[str, Any] = {"status": "skipped", "blockers": ["p9t_not_ready"], "output_files": {}}
    p9v: dict[str, Any] = {"status": "skipped", "blockers": ["p9u_not_ready"], "output_files": {}}
    p9u_code = 2
    p9v_code = 2
    if p9t_code == 0:
        p9u, p9u_code = build_p9u(args, started_at=started_at + timedelta(seconds=1), run_id=run_id, p9t_summary=p9t)
    if p9u_code == 0:
        p9v, p9v_code = build_p9v(args, started_at=started_at + timedelta(seconds=2), run_id=run_id, p9u_summary=p9u)
    status = "ready" if p9t_code == p9u_code == p9v_code == 0 else "blocked"
    if args.output_root:
        root = resolve_path(args.output_root)
    else:
        root = phase_root(args, CORRIDOR_PARENT, "p9tuv_proof_only_corridor", run_id)
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "authorized_corridor": "P9T_P9U_P9V_proof_only",
        "p9t_status": p9t.get("status"),
        "p9u_status": p9u.get("status"),
        "p9v_status": p9v.get("status"),
        "hard_stop_before": [
            "remote_sync",
            "live_timer_path_load",
            "supervisor_run",
            "executor_input_mutation",
            "target_plan_replacement",
            "operator_state_mutation",
            "stage_governance_change",
            "live_order_submission",
        ],
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
            "p9t_summary": dict(p9t.get("output_files") or {}).get("summary", ""),
            "p9u_summary": dict(p9u.get("output_files") or {}).get("summary", ""),
            "p9v_summary": dict(p9v.get("output_files") or {}).get("summary", ""),
        },
        "blockers": list(p9t.get("blockers") or []) + list(p9u.get("blockers") or []) + list(p9v.get("blockers") or []),
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_corridor(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['outputs']['corridor_summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
