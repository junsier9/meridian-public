from __future__ import annotations

import argparse
import json
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9s_define_next_gate_scope.v1"
APPROVE_P9S_DECISION = "approve_p9s_define_next_gate_scope_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9s_next_gate_scope_definition"
PHASE9Q_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9q_define_next_gate_scope_gate"
PROJECT_PROFILE = "config/project_governance/project_profile.json"
HOOK_MODULE = "src/enhengclaw/live_trading/dth60_observe_only_shadow_hook.py"
SUPERVISOR_PATH = "src/enhengclaw/live_trading/mainnet_live_supervisor.py"

NEXT_GATE_ID = (
    "P9T_owner_gate_prepare_default_off_live_supervisor_shadow_hook_load_proposal_only_if_separately_requested"
)
NEXT_GATE_SCOPE = "owner_gated_prepare_default_off_live_supervisor_shadow_hook_load_proposal_scope_only"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the P9S proof-only scope definition for the next owner gate. "
            "P9S defines scope only and does not execute the next gate, load "
            "timer paths, mutate executor input, remote sync, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9q-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9S_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:define_next_gate_scope_only")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_equals(payload: dict[str, Any], key: str, expected: int) -> bool:
    try:
        return int(payload.get(key)) == expected
    except (TypeError, ValueError):
        return False


def p9q_ready(
    summary: dict[str, Any],
    scope_gate: dict[str, Any],
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
    scope_constraints = dict(scope_gate.get("allowed_next_action_constraints") or {})
    required_gates = (
        "owner_decision_p9q_define_scope_only",
        "project_stage_boundary_preserved",
        "p9p_owner_review_ready",
        "p9p_sufficient_for_next_owner_gate_discussion",
        "p9p_next_gate_execution_not_authorized",
        "current_live_supervisor_not_loading_hook",
        "current_hook_hash_matches_p9p_source",
        "current_supervisor_hash_matches_p9p_source",
        "scope_definition_gate_output_under_proof_artifacts",
        "future_scope_definition_must_be_proof_artifacts_only",
        "future_scope_definition_must_not_execute_next_gate",
        "future_scope_definition_must_keep_order_authority_disabled",
        "future_scope_definition_must_not_authorize_live_order_submission",
        "no_scope_definition_in_p9q",
        "no_next_gate_execution_in_p9q",
        "no_timer_hook_implementation_in_p9q",
        "no_hook_deployment_in_p9q",
        "no_live_timer_path_load_in_p9q",
        "no_supervisor_run_in_p9q",
        "no_remote_execution_in_p9q",
        "no_executor_input_mutation_in_p9q",
        "no_target_plan_replacement_in_p9q",
        "no_live_mutation_in_p9q",
        "zero_orders_fills_in_p9q",
    )
    return (
        summary.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate.v1"
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("gate_scope") == "owner_gated_allow_future_next_gate_scope_definition_only"
        and summary.get("p9q_define_next_gate_scope_owner_gate_ready") is True
        and summary.get("eligible_to_define_next_gate_scope") is True
        and summary.get("defined_next_gate_scope") is False
        and summary.get("next_gate_scope_definition_in_p9q_authorized") is False
        and summary.get("next_gate_execution_authorized") is False
        and summary.get("allowed_next_gate") == "P9S_define_next_gate_scope_only_if_separately_requested"
        and summary.get("future_scope_definition_must_be_proof_artifacts_only") is True
        and summary.get("future_scope_definition_must_not_execute_next_gate") is True
        and summary.get("future_scope_definition_must_keep_order_authority_disabled") is True
        and summary.get("future_scope_definition_must_not_authorize_live_order_submission") is True
        and summary.get("eligible_for_live_timer_path_load") is False
        and summary.get("eligible_for_live_order_submission") is False
        and summary.get("eligible_for_stage_governance_change") is False
        and summary.get("timer_hook_implementation_authorized") is False
        and summary.get("hook_deployment_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("supervisor_run_authorized") is False
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("candidate_live_order_submission_authorized") is False
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_overlay_execution_path") == "excluded"
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
        and owner.get("decision") == "approve_p9q_allow_define_next_gate_scope_only"
        and owner.get("future_next_gate_scope_definition_approved") is True
        and owner.get("define_next_gate_scope_in_p9q_approved") is False
        and owner.get("execute_next_gate_approved") is False
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
        and scope_gate.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9q_next_gate_scope_definition_gate.v1"
        and scope_gate.get("allowed_next_action") == "define_next_gate_concrete_scope"
        and scope_gate.get("allowed_next_gate") == "P9S_define_next_gate_scope_only_if_separately_requested"
        and scope_gate.get("defined_in_p9q") is False
        and scope_gate.get("executed_in_p9q") is False
        and scope_constraints.get("scope_definition_only") is True
        and scope_constraints.get("proof_artifacts_only") is True
        and scope_constraints.get("must_not_execute_next_gate") is True
        and scope_constraints.get("must_not_implement_hook") is True
        and scope_constraints.get("must_not_deploy_hook") is True
        and scope_constraints.get("must_not_load_live_timer_path") is True
        and scope_constraints.get("must_not_replace_target_plan") is True
        and scope_constraints.get("must_not_mutate_executor_input") is True
        and scope_constraints.get("must_not_modify_live_config") is True
        and scope_constraints.get("must_not_modify_operator_state") is True
        and scope_constraints.get("must_not_modify_timer_or_service_state") is True
        and scope_constraints.get("must_not_remote_sync") is True
        and scope_constraints.get("must_not_run_supervisor") is True
        and scope_constraints.get("candidate_order_authority") == "disabled"
        and scope_constraints.get("candidate_live_order_submission_authorized") is False
        and int_equals(scope_constraints, "orders_submitted_must_equal", 0)
        and int_equals(scope_constraints, "fill_count_must_equal", 0)
        and authorizations.get("future_next_gate_scope_definition") is True
        and authorizations.get("define_next_gate_scope_in_p9q") is False
        and authorizations.get("execute_next_gate") is False
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


def build_owner_decision_record(args: argparse.Namespace, started_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9S_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9s_owner_decision.v1",
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_question": "define_next_gate_concrete_scope_only",
        "decision_effect": "define_next_gate_scope_under_proof_artifacts_only" if approved else "none",
        "define_next_gate_scope_approved": approved,
        "execute_defined_next_gate_approved": False,
        "prepare_proposal_approved": False,
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


def build_next_gate_scope_definition(
    *,
    run_id: str,
    owner_decision_record: dict[str, Any],
    source_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9s_next_gate_scope_definition.v1",
        "run_id": run_id,
        "source_evidence": source_evidence,
        "owner_decision": owner_decision_record,
        "defined_next_gate": NEXT_GATE_ID,
        "defined_next_gate_scope": NEXT_GATE_SCOPE,
        "defined_next_gate_question": (
            "whether to allow preparing a proof-artifacts-only proposal package for a "
            "default-off live-supervisor observe-only shadow-hook load path"
        ),
        "defined_next_gate_effect_if_approved": (
            "authorize preparation of a future proposal/review package only"
        ),
        "defined_next_gate_effect_if_rejected": "stop before any proposal preparation or execution work",
        "defined_next_gate_must_be_separately_requested": True,
        "defined_next_gate_executes_in_p9s": False,
        "defined_next_gate_authorized_in_p9s": False,
        "defined_next_gate_allowed_actions": [
            "read P9Q and P9S proof artifacts",
            "decide whether a future proposal package may be prepared",
            "write owner decision artifacts under proof_artifacts only",
        ],
        "defined_next_gate_required_inputs": [
            "retained P9R research-to-live parity proof",
            "retained P9D default-off observe-only hook contract proof",
            "retained P9E timer-adjacent fixture proof",
            "retained P9F remote proof_artifacts wrapper proof",
            "retained P9G timer-hook review pack",
            "retained P9H implementation/load proposal pack",
            "retained P9I default-off local implementation diff fixture",
            "retained P9J proof-artifacts dry-load readback",
            "retained P9K owner review after dry-load readback",
            "retained P9O default-off timer-path dry-load readback",
            "retained P9P sufficiency-only owner review",
            "retained P9Q next-scope-definition owner gate",
            "retained P9S next-gate scope definition",
            "current hook and live-supervisor source hashes",
        ],
        "defined_next_gate_disallowed_actions": {
            "execute_next_gate_inside_p9s": True,
            "prepare_proposal_inside_p9s": True,
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
            "stage_governance_change": True,
            "submit_orders": True,
        },
        "defined_next_gate_required_boundaries": {
            "proof_artifacts_only": True,
            "default_off_only": True,
            "observe_only_shadow_artifacts_only": True,
            "executor_input_must_remain_baseline_only": True,
            "target_plan_must_not_be_replaced": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "candidate_order_authority": "disabled",
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
        },
        "future_follow_on_after_defined_gate": (
            "Only if P9T is separately requested and approved may a later package prepare "
            "the default-off proposal. P9T itself must not load timer paths or submit orders."
        ),
    }


def build_phase9s(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = resolve_path(args.output_root) if args.output_root else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = output_root / "proof_artifacts" / "p9s" / run_id
    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9q": resolve_path(args.phase9q_summary)
        if args.phase9q_summary
        else latest_match(PHASE9Q_PARENT, "*/summary.json"),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
    }
    project_profile = load_optional(paths["project_profile"])
    p9q = load_optional(paths["phase9q"])
    p9q_scope_gate_path = source_output_path(p9q, "next_gate_scope_definition_gate")
    p9q_matrix_path = source_output_path(p9q, "non_authorization_matrix")
    p9q_scope_gate = load_optional(p9q_scope_gate_path)
    p9q_matrix = load_optional(p9q_matrix_path)
    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    owner_decision_record = build_owner_decision_record(args, started_at)
    p9q_ok = p9q_ready(
        p9q,
        p9q_scope_gate,
        p9q_matrix,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9q_summary": evidence_file(paths["phase9q"]),
        "phase9q_next_gate_scope_definition_gate": evidence_file(p9q_scope_gate_path),
        "phase9q_non_authorization_matrix": evidence_file(p9q_matrix_path),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
    }
    next_gate_scope_definition = build_next_gate_scope_definition(
        run_id=run_id,
        owner_decision_record=owner_decision_record,
        source_evidence=source_evidence,
    )
    scope_acceptance_checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9s_scope_acceptance_checklist.v1",
        "run_id": run_id,
        "defined_next_gate": NEXT_GATE_ID,
        "checklist": {
            "p9s_defines_scope_only": True,
            "defined_gate_must_be_separately_requested": True,
            "defined_gate_is_owner_gated": True,
            "defined_gate_is_proof_artifacts_only": True,
            "defined_gate_can_only_decide_proposal_preparation": True,
            "defined_gate_cannot_execute_its_follow_on": True,
            "defined_gate_cannot_implement_hook": True,
            "defined_gate_cannot_deploy_hook": True,
            "defined_gate_cannot_load_live_timer_path": True,
            "defined_gate_cannot_run_supervisor": True,
            "defined_gate_cannot_mutate_executor_input": True,
            "defined_gate_cannot_replace_target_plan": True,
            "defined_gate_cannot_remote_sync": True,
            "defined_gate_cannot_submit_orders": True,
            "defined_gate_must_keep_order_authority_disabled": True,
        },
    }
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9s_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "define_next_gate_scope": str(args.owner_decision) == APPROVE_P9S_DECISION,
            "execute_defined_next_gate": False,
            "prepare_proposal": False,
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
    control_boundary_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9s_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "next_gate_scope_definition_only",
        "live_supervisor": source_evidence["live_supervisor"],
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else "",
        "live_supervisor_source_unchanged": True,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "timer_service_enabled_or_invoked": False,
        "remote_control_plane_touched": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    control_boundary_readback["live_supervisor_source_unchanged"] = (
        control_boundary_readback["live_supervisor_sha256_before"]
        == control_boundary_readback["live_supervisor_sha256_after"]
    )
    gates = {
        "owner_decision_p9s_define_scope_only": str(args.owner_decision) == APPROVE_P9S_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage")
        == "stage_1_research_readiness_only",
        "p9q_owner_gate_ready": p9q_ok,
        "p9q_allows_p9s_scope_definition": p9q.get("eligible_to_define_next_gate_scope") is True
        and p9q.get("allowed_next_gate") == "P9S_define_next_gate_scope_only_if_separately_requested",
        "p9q_did_not_define_scope": p9q.get("defined_next_gate_scope") is False,
        "p9q_did_not_execute_next_gate": p9q.get("next_gate_execution_authorized") is False,
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "current_hook_hash_matches_p9q_source": dict(dict(p9q.get("source_evidence") or {}).get("hook_module") or {}).get(
            "sha256"
        )
        == hook_sha,
        "current_supervisor_hash_matches_p9q_source": dict(
            dict(p9q.get("source_evidence") or {}).get("live_supervisor") or {}
        ).get("sha256")
        == supervisor_sha_before,
        "next_gate_scope_definition_output_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "next_gate_scope_definition.json"
        ),
        "p9s_defines_scope_only": True,
        "p9s_does_not_execute_defined_next_gate": True,
        "p9s_does_not_prepare_proposal": True,
        "p9s_requires_defined_gate_to_be_separately_requested": True,
        "defined_gate_must_be_proof_artifacts_only": True,
        "defined_gate_must_keep_order_authority_disabled": True,
        "defined_gate_must_not_authorize_live_order_submission": True,
        "defined_gate_must_not_load_live_timer_path": True,
        "defined_gate_must_not_mutate_executor_input": True,
        "defined_gate_must_not_replace_target_plan": True,
        "defined_gate_must_not_remote_sync": True,
        "no_timer_hook_implementation_in_p9s": True,
        "no_hook_deployment_in_p9s": True,
        "no_live_timer_path_load_in_p9s": True,
        "no_supervisor_run_in_p9s": True,
        "no_remote_execution_in_p9s": True,
        "no_executor_input_mutation_in_p9s": True,
        "no_target_plan_replacement_in_p9s": True,
        "no_live_mutation_in_p9s": True,
        "zero_orders_fills_in_p9s": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    ready = status == "ready"

    write_json(output_root / "owner_decision_record.json", owner_decision_record)
    write_json(proof_root / "next_gate_scope_definition.json", next_gate_scope_definition)
    write_json(proof_root / "scope_acceptance_checklist.json", scope_acceptance_checklist)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix)
    write_json(proof_root / "control_boundary_readback.json", control_boundary_readback)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "gate_scope": "p9s_define_next_gate_scope_only",
        "owner_decision": owner_decision_record,
        "source_evidence": source_evidence,
        "p9s_next_gate_scope_definition_ready": ready,
        "next_gate_scope_defined": ready,
        "defined_next_gate": NEXT_GATE_ID,
        "defined_next_gate_scope": NEXT_GATE_SCOPE,
        "defined_next_gate_authorized_in_p9s": False,
        "defined_next_gate_execution_authorized": False,
        "defined_next_gate_must_be_separately_requested": True,
        "defined_next_gate_must_be_proof_artifacts_only": True,
        "defined_next_gate_must_keep_order_authority_disabled": True,
        "defined_next_gate_must_not_authorize_live_order_submission": True,
        "defined_next_gate_must_not_load_live_timer_path": True,
        "defined_next_gate_must_not_execute_follow_on": True,
        "prepare_proposal_authorized": False,
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
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_supervisor_source_unchanged": control_boundary_readback["live_supervisor_source_unchanged"],
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
        "allowed_next_gate": NEXT_GATE_ID,
        "recommended_next_gate": NEXT_GATE_ID,
        "proof_root": str(proof_root),
        "gates": gates,
        "blockers": blockers,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "owner_decision_record": str(output_root / "owner_decision_record.json"),
            "next_gate_scope_definition": str(proof_root / "next_gate_scope_definition.json"),
            "scope_acceptance_checklist": str(proof_root / "scope_acceptance_checklist.json"),
            "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
            "report": str(output_root / "p9s_define_next_gate_scope.md"),
        },
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9s_define_next_gate_scope.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9S Define Next-Gate Scope",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Defined Scope",
        "",
        "```text",
        f"defined_next_gate = {summary['defined_next_gate']}",
        f"defined_next_gate_scope = {summary['defined_next_gate_scope']}",
        f"next_gate_scope_defined = {str(bool(summary['next_gate_scope_defined'])).lower()}",
        "defined_next_gate_authorized_in_p9s = false",
        "defined_next_gate_execution_authorized = false",
        "prepare_proposal_authorized = false",
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
    summary, exit_code = build_phase9s(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
