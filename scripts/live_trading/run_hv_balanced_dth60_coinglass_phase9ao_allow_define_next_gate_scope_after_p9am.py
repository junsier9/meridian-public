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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9an_review_after_default_off_observe_only_readback import (  # noqa: E402
    CONTRACT_VERSION as P9AN_CONTRACT,
    P9AO_GATE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9ao_allow_define_next_gate_scope_after_p9am.v1"
APPROVE_P9AO_DECISION = "approve_p9ao_allow_define_next_gate_scope_after_p9am_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ao_allow_define_next_gate_scope_after_p9am"
PHASE9AN_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9an_review_after_default_off_observe_only_readback"
P9AP_GATE = "P9AP_define_next_gate_scope_after_p9am_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9AO as a narrow owner gate after P9AN. P9AO only decides "
            "whether a future gate may define the concrete next-gate scope "
            "after the retained P9AM readback. It does not define that scope, "
            "execute the next gate, write a proposal body, dry-load, load timer "
            "paths, invoke the supervisor, mutate live state, remote sync, or "
            "authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9an-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AO_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:allow_p9ao_define_next_gate_scope_after_p9am_discussion_only",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _false(payload: dict[str, Any], key: str) -> bool:
    return payload.get(key) is False


def _all_true(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is True for key in keys)


def _all_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9AO_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ao_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "allow_future_definition_of_next_gate_scope_after_p9am_readback_only",
        "decision_effect": "authorize_future_next_gate_scope_definition_after_p9am_only" if approved else "none",
        "future_next_gate_scope_definition_after_p9am_approved": approved,
        "define_next_gate_scope_in_p9ao_approved": False,
        "execute_next_gate_approved": False,
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


def p9an_ready_for_p9ao(
    summary: dict[str, Any],
    matrix: dict[str, Any],
    packet: dict[str, Any],
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
    minimum_proof = dict(matrix.get("minimum_proof") or {})
    review_result = dict(packet.get("review_result") or {})
    required_gates = (
        "owner_decision_p9an_review_only",
        "stage_boundary_preserved",
        "p9am_summary_ready",
        "p9am_default_off_observe_only_readback_executed",
        "p9am_readback_default_off",
        "p9am_readback_observe_only_shadow_writer",
        "p9am_readback_not_live_timer_service",
        "proof_files_exist",
        "proof_files_under_proof_artifacts",
        "dry_load_manifest_ready",
        "default_off_config_readback_ready",
        "observe_only_shadow_readback_summary_ready",
        "executor_input_readback_ready",
        "control_boundary_readback_ready",
        "candidate_shadow_artifacts_written",
        "candidate_artifacts_under_proof_artifacts_only",
        "baseline_executor_input_hash_unchanged",
        "executor_consumes_baseline_only",
        "candidate_shadow_hash_differs_from_executor",
        "candidate_plan_not_referenced_by_executor",
        "target_plan_not_replaced",
        "live_supervisor_not_loading_hook",
        "live_config_dir_unchanged",
        "live_timer_path_not_loaded",
        "supervisor_not_run",
        "remote_not_touched",
        "candidate_execution_not_performed",
        "zero_orders_fills",
        "no_live_mutation",
        "review_output_under_proof_artifacts",
        "no_define_next_gate_scope_in_p9an",
        "no_timer_hook_implementation_in_p9an",
        "no_hook_deployment_in_p9an",
        "no_timer_path_load_in_p9an",
        "no_production_timer_service_load_in_p9an",
        "no_supervisor_run_in_p9an",
        "no_remote_execution_in_p9an",
        "no_candidate_execution_in_p9an",
        "no_executor_input_mutation_in_p9an",
        "no_target_plan_replacement_in_p9an",
        "no_live_mutation_in_p9an",
        "zero_orders_fills_in_p9an",
    )
    required_summary_false = (
        "next_owner_gate_execution_authorized",
        "define_next_gate_scope_in_p9an_authorized",
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
        "candidate_execution_authorized",
        "live_order_submission_authorized",
        "target_plan_replacement_authorized",
        "executor_input_mutation_authorized",
        "live_config_mutation_authorized",
        "operator_state_mutation_authorized",
        "timer_or_service_mutation_authorized",
        "candidate_live_order_submission_authorized",
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
    required_auth_false = (
        "define_next_gate_scope_in_p9an",
        "execute_next_owner_gate",
        "candidate_execution",
        "candidate_live_order_submission",
        "timer_hook_implementation",
        "hook_deployment",
        "timer_path_load",
        "production_timer_service_load",
        "live_order_submission",
        "target_plan_replacement",
        "executor_input_mutation",
        "live_config_mutation",
        "operator_state_mutation",
        "timer_or_service_mutation",
        "remote_sync",
        "supervisor_invocation",
        "supervisor_run",
        "stage_governance_change",
    )
    return (
        summary.get("contract_version") == P9AN_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("review_scope") == "owner_gated_p9am_default_off_observe_only_readback_sufficiency_review_only"
        and summary.get("p9am_default_off_observe_only_readback_sufficient_for_next_owner_gate") is True
        and summary.get("eligible_for_next_owner_gate_discussion") is True
        and summary.get("allowed_next_gate") == P9AO_GATE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("default_off_observe_only_readback_executed") is True
        and summary.get("default_off_observe_only_readback_proof_files_ready") is True
        and summary.get("default_off_readback_not_live_timer_service") is True
        and summary.get("observe_only_shadow_readback_ready") is True
        and int(summary.get("candidate_shadow_artifacts_written_count") or 0) > 0
        and summary.get("candidate_artifacts_under_proof_artifacts_only") is True
        and summary.get("baseline_executor_input_hash_unchanged") is True
        and summary.get("executor_consumes_baseline_only") is True
        and summary.get("candidate_shadow_hash_differs_from_executor") is True
        and summary.get("candidate_plan_referenced_by_executor") is False
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_overlay_execution_path") == "excluded"
        and summary.get("candidate_artifact_sink") == "proof_artifacts_only"
        and summary.get("live_supervisor_source_unchanged") is True
        and summary.get("live_config_dir_unchanged") is True
        and zero_orders_fills(summary)
        and no_live_mutation(summary)
        and _all_false(summary, required_summary_false)
        and _all_true(gates, required_gates)
        and owner.get("decision") == "approve_p9an_review_default_off_observe_only_readback_sufficiency_only"
        and owner.get("review_default_off_observe_only_readback_sufficiency_approved") is True
        and owner.get("enter_separate_next_owner_gate_discussion_approved") is True
        and owner.get("define_next_gate_scope_in_p9an_approved") is False
        and owner.get("execute_next_owner_gate_approved") is False
        and owner.get("live_order_submission_approved") is False
        and matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9an_review_decision_matrix.v1"
        and authorizations.get("p9an_review_default_off_observe_only_readback_sufficiency") is True
        and authorizations.get("enter_separate_next_owner_gate_discussion") is True
        and _all_false(authorizations, required_auth_false)
        and bool(minimum_proof)
        and all(value is True for value in minimum_proof.values())
        and packet.get("contract_version") == "hv_balanced_dth60_coinglass_phase9an_owner_review_packet.v1"
        and packet.get("review_scope") == summary.get("review_scope")
        and review_result.get("p9am_default_off_observe_only_readback_sufficient_for_next_owner_gate") is True
        and review_result.get("next_owner_gate_execution_authorized") is False
        and review_result.get("define_next_gate_scope_in_p9an_authorized") is False
        and review_result.get("timer_path_load_authorized") is False
        and review_result.get("live_order_submission_authorized") is False
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def build_phase9ao(
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
    proof_root = output_root / "proof_artifacts" / "p9ao" / run_id

    project_profile_path = resolve_path(args.project_profile)
    phase9an_path = (
        resolve_path(args.phase9an_summary)
        if str(args.phase9an_summary).strip()
        else latest_match(PHASE9AN_PARENT, "*/summary.json")
    )
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)

    project_profile = load_optional(project_profile_path)
    p9an = load_optional(phase9an_path)
    matrix_path = source_output_path(p9an, "review_decision_matrix")
    packet_path = source_output_path(p9an, "owner_review_packet")
    matrix = load_optional(matrix_path)
    packet = load_optional(packet_path)
    hook_sha = file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else ""
    supervisor_sha_before = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    live_config_sha_before = tree_sha256(live_config_dir)
    supervisor_loads_hook = current_supervisor_loads_hook(supervisor_path)
    decision = owner_decision_record(args, generated_at)

    p9an_ok = p9an_ready_for_p9ao(
        p9an,
        matrix,
        packet,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    source_evidence = {
        "project_profile": evidence_file(project_profile_path),
        "phase9an_summary": evidence_file(phase9an_path),
        "phase9an_review_decision_matrix": evidence_file(matrix_path),
        "phase9an_owner_review_packet": evidence_file(packet_path),
        "hook_module": evidence_file(hook_path),
        "live_supervisor": evidence_file(supervisor_path),
        "live_config_dir": {
            "path": str(live_config_dir),
            "exists": live_config_dir.exists(),
            "sha256": live_config_sha_before,
        },
    }
    scope_permission_gate = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ao_next_gate_scope_permission_gate.v1",
        "run_id": run_id,
        "gate_scope": "owner_gated_allow_future_next_gate_scope_definition_after_p9am_readback_only",
        "source_evidence": source_evidence,
        "owner_decision": decision,
        "allowed_next_action": "define_next_gate_scope_after_p9am_readback",
        "allowed_next_gate": P9AP_GATE,
        "allowed_next_gate_must_be_separately_requested": True,
        "defined_in_p9ao": False,
        "executed_in_p9ao": False,
        "allowed_next_action_constraints": {
            "scope_definition_only": True,
            "proof_artifacts_only": True,
            "must_consume_p9an_proof": True,
            "must_not_execute_next_gate": True,
            "must_not_prepare_proposal": True,
            "must_not_write_proposal_body": True,
            "must_not_execute_dry_load_readback": True,
            "must_not_implement_hook": True,
            "must_not_deploy_hook": True,
            "must_not_load_live_timer_path": True,
            "must_not_invoke_supervisor": True,
            "must_not_replace_target_plan": True,
            "must_not_mutate_executor_input": True,
            "must_not_modify_live_config": True,
            "must_not_modify_operator_state": True,
            "must_not_modify_timer_or_service_state": True,
            "must_not_remote_sync": True,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
        },
    }
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ao_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "future_next_gate_scope_definition_after_p9am": str(args.owner_decision) == APPROVE_P9AO_DECISION,
            "define_next_gate_scope_in_p9ao": False,
            "execute_next_gate": False,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9ao_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "future_next_gate_scope_definition_after_p9am_permission_only",
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
        "owner_decision_p9ao_allow_define_scope_only": str(args.owner_decision) == APPROVE_P9AO_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9an_review_ready": p9an_ok,
        "p9an_sufficient_for_next_owner_gate_discussion": p9an.get(
            "p9am_default_off_observe_only_readback_sufficient_for_next_owner_gate"
        )
        is True
        and p9an.get("eligible_for_next_owner_gate_discussion") is True,
        "p9an_allows_p9ao_only": p9an.get("allowed_next_gate") == P9AO_GATE
        and p9an.get("allowed_next_gate_must_be_separately_requested") is True,
        "p9an_did_not_define_scope": p9an.get("define_next_gate_scope_in_p9an_authorized") is False,
        "p9an_next_gate_execution_not_authorized": p9an.get("next_owner_gate_execution_authorized") is False,
        "p9an_zero_orders_fills": zero_orders_fills(p9an),
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "current_hook_hash_matches_p9an_source": dict(
            dict(p9an.get("source_evidence") or {}).get("hook_module") or {}
        ).get("sha256")
        == hook_sha,
        "current_supervisor_hash_matches_p9an_source": dict(
            dict(p9an.get("source_evidence") or {}).get("live_supervisor") or {}
        ).get("sha256")
        == supervisor_sha_before,
        "current_live_config_hash_matches_p9an_source": dict(
            dict(p9an.get("source_evidence") or {}).get("live_config_dir") or {}
        ).get("sha256")
        == live_config_sha_before,
        "scope_permission_output_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "next_gate_scope_permission_gate.json"
        ),
        "future_scope_definition_must_be_proof_artifacts_only": True,
        "future_scope_definition_must_not_execute_next_gate": True,
        "future_scope_definition_must_not_prepare_proposal": True,
        "future_scope_definition_must_keep_order_authority_disabled": True,
        "future_scope_definition_must_not_authorize_live_order_submission": True,
        "future_scope_definition_must_not_load_live_timer_path": True,
        "future_scope_definition_must_not_mutate_executor_input": True,
        "future_scope_definition_must_not_replace_target_plan": True,
        "future_scope_definition_must_not_remote_sync": True,
        "no_scope_definition_in_p9ao": True,
        "no_next_gate_execution_in_p9ao": True,
        "no_proposal_body_write_in_p9ao": True,
        "no_dry_load_readback_execution_in_p9ao": True,
        "no_timer_hook_implementation_in_p9ao": True,
        "no_hook_deployment_in_p9ao": True,
        "no_live_timer_path_load_in_p9ao": True,
        "no_production_timer_service_load_in_p9ao": True,
        "no_supervisor_run_in_p9ao": True,
        "no_remote_execution_in_p9ao": True,
        "no_candidate_execution_in_p9ao": True,
        "no_executor_input_mutation_in_p9ao": True,
        "no_target_plan_replacement_in_p9ao": True,
        "no_live_mutation_in_p9ao": True,
        "zero_orders_fills_in_p9ao": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    gate_ready = status == "ready"

    write_json(output_root / "owner_decision_record.json", decision)
    write_json(proof_root / "next_gate_scope_permission_gate.json", scope_permission_gate)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix)
    write_json(proof_root / "control_boundary_readback.json", control_boundary_readback)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "gate_scope": "owner_gated_allow_future_next_gate_scope_definition_after_p9am_readback_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9ao_allow_define_next_gate_scope_after_p9am_ready": gate_ready,
        "eligible_to_define_next_gate_scope_after_p9am": gate_ready,
        "defined_next_gate_scope": False,
        "next_gate_scope_definition_in_p9ao_authorized": False,
        "next_gate_execution_authorized": False,
        "allowed_next_gate": P9AP_GATE if gate_ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "future_scope_definition_must_be_proof_artifacts_only": True,
        "future_scope_definition_must_not_execute_next_gate": True,
        "future_scope_definition_must_not_prepare_proposal": True,
        "future_scope_definition_must_keep_order_authority_disabled": True,
        "future_scope_definition_must_not_authorize_live_order_submission": True,
        "p9an_default_off_observe_only_readback_review_ready": p9an_ok,
        "p9an_sufficient_for_next_owner_gate_discussion": gates[
            "p9an_sufficient_for_next_owner_gate_discussion"
        ],
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
        "recommended_next_gate": P9AP_GATE if gate_ready else "",
        "proof_root": str(proof_root),
        "gates": gates,
        "blockers": blockers,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "owner_decision_record": str(output_root / "owner_decision_record.json"),
            "next_gate_scope_permission_gate": str(proof_root / "next_gate_scope_permission_gate.json"),
            "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
            "report": str(output_root / "p9ao_allow_define_next_gate_scope_after_p9am.md"),
        },
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9ao_allow_define_next_gate_scope_after_p9am.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9AO Allow Define Next Gate Scope After P9AM",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9AO only decides whether a future gate may define the concrete next-gate scope after P9AM.",
        "",
        "```text",
        "gate_scope = owner_gated_allow_future_next_gate_scope_definition_after_p9am_readback_only",
        "eligible_to_define_next_gate_scope_after_p9am = "
        f"{str(bool(summary['eligible_to_define_next_gate_scope_after_p9am'])).lower()}",
        "defined_next_gate_scope = false",
        "next_gate_scope_definition_in_p9ao_authorized = false",
        "next_gate_execution_authorized = false",
        f"allowed_next_gate = {summary['allowed_next_gate']}",
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
    summary, exit_code = build_phase9ao(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
