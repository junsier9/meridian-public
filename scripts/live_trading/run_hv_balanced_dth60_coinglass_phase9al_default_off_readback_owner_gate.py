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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ak_default_off_timer_path_readback_proposal import (  # noqa: E402
    CONTRACT_VERSION as P9AK_CONTRACT,
    P9AL_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    current_supervisor_loads_hook,
    evidence_file,
    file_sha256,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    HOOK_MODULE,
    LIVE_CONFIG_DIR,
    PROJECT_PROFILE,
    SUPERVISOR_PATH,
    tree_sha256,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9al_default_off_readback_owner_gate.v1"
APPROVE_P9AL_DECISION = "approve_p9al_execute_default_off_observe_only_timer_path_dry_load_readback_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9al_default_off_readback_owner_gate"
PHASE9AK_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ak_default_off_timer_path_readback_proposal"
P9AM_GATE = "P9AM_default_off_observe_only_timer_path_dry_load_readback_execution_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9AL as the owner gate that decides whether a future "
            "default-off / observe-only timer-path dry-load/readback execution "
            "may be separately requested. P9AL itself does not execute the "
            "readback, remote sync, load a timer path, invoke the supervisor, "
            "mutate live state, replace target plans, mutate executor input, "
            "or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ak-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AL_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:review_allow_default_off_observe_only_dry_load_readback_no_order",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def proof_artifacts_path(path_text: str) -> bool:
    return "proof_artifacts" in str(path_text).replace("\\", "/").lower().split("/")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def proposed_contract_ready(proposal: dict[str, Any]) -> bool:
    contract = dict(proposal.get("proposed_future_readback_contract") or {})
    hook_config = dict(proposal.get("default_off_hook_config_contract") or {})
    required_false = (
        "p9ak_authorizes_dry_load_readback_execution",
        "p9ak_authorizes_timer_hook_implementation",
        "p9ak_authorizes_hook_deployment",
        "p9ak_authorizes_timer_path_load",
        "p9ak_authorizes_supervisor_invocation",
        "p9ak_authorizes_remote_sync",
        "p9ak_authorizes_live_orders",
    )
    return (
        proposal.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ak_timer_path_readback_proposal_body.v1"
        and proposal.get("proposal_scope")
        == "prepare_default_off_observe_only_hook_live_supervisor_timer_path_dry_load_readback_proposal_only"
        and proposal.get("proposal_status") == "draft_for_future_owner_review"
        and proposal.get("future_gate_required") is True
        and proposal.get("proposed_future_gate") == P9AL_GATE
        and proposal.get("proposed_future_gate_scope")
        == "decide_whether_to_execute_default_off_observe_only_timer_path_dry_load_readback"
        and all(proposal.get(key) is False for key in required_false)
        and contract.get("default_off_required") is True
        and contract.get("hook_config_enabled_default") is False
        and contract.get("observe_only_mode_required") is True
        and contract.get("candidate_order_authority") == "disabled"
        and contract.get("candidate_live_order_submission_authorized") is False
        and contract.get("candidate_execution_authorized") is False
        and contract.get("execution_target_source") == "baseline_only"
        and contract.get("candidate_overlay_execution_path") == "excluded"
        and contract.get("candidate_artifact_sink") == "proof_artifacts_only"
        and contract.get("executor_input_must_remain_baseline_only") is True
        and contract.get("candidate_plan_must_not_be_referenced_by_executor") is True
        and contract.get("target_plan_must_not_be_replaced") is True
        and contract.get("executor_input_must_not_change") is True
        and contract.get("dry_load_readback_must_not_submit_orders") is True
        and contract.get("remote_sync_must_not_occur_without_separate_gate") is True
        and contract.get("live_config_must_not_change") is True
        and contract.get("operator_state_must_not_change") is True
        and contract.get("timer_state_must_not_change") is True
        and int(contract.get("orders_submitted_must_equal", -1)) == 0
        and int(contract.get("fill_count_must_equal", -1)) == 0
        and hook_config.get("ObserveOnlyShadowHookConfig.enabled") is False
        and hook_config.get("ObserveOnlyShadowHookConfig.mode") == "observe_only"
        and hook_config.get("ObserveOnlyShadowHookConfig.artifact_sink") == "proof_artifacts_only"
        and hook_config.get("ObserveOnlyShadowHookConfig.candidate_order_authority") == "disabled"
        and hook_config.get("ObserveOnlyShadowHookConfig.candidate_live_order_submission_authorized") is False
        and hook_config.get("ObserveOnlyShadowHookConfig.execution_target_source") == "baseline_only"
        and hook_config.get("ObserveOnlyShadowHookConfig.candidate_overlay_execution_path") == "excluded"
    )


def p9ak_ready_for_p9al(
    summary: dict[str, Any],
    *,
    proposal: dict[str, Any],
    current_hook_sha256: str,
    current_supervisor_sha256: str,
) -> bool:
    gates = dict(summary.get("gates") or {})
    source = dict(summary.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    owner = dict(summary.get("owner_decision") or {})
    required_gates = (
        "owner_decision_p9ak_proposal_only",
        "project_stage_boundary_preserved",
        "p9aj_scope_gate_ready",
        "current_live_supervisor_not_loading_hook",
        "current_hook_hash_matches_p9aj_source",
        "current_supervisor_hash_matches_p9aj_source",
        "proposal_output_under_proof_artifacts",
        "proposal_body_output_under_proof_artifacts",
        "proposal_default_off_required",
        "proposal_observe_only_required",
        "proposal_artifact_sink_proof_artifacts_only",
        "proposal_executor_input_source_baseline_only",
        "proposal_candidate_shadow_only",
        "proposal_candidate_order_authority_disabled",
        "proposal_requires_separate_future_readback_gate",
        "no_dry_load_readback_execution_in_p9ak",
        "no_timer_hook_implementation_in_p9ak",
        "no_hook_deployment_in_p9ak",
        "no_timer_path_load_in_p9ak",
        "no_supervisor_invocation_in_p9ak",
        "no_remote_sync_in_p9ak",
        "no_remote_execution_in_p9ak",
        "no_candidate_execution_in_p9ak",
        "no_executor_input_mutation_in_p9ak",
        "no_target_plan_replacement_in_p9ak",
        "no_live_mutation_in_p9ak",
        "zero_orders_fills_in_p9ak",
    )
    return (
        summary.get("contract_version") == P9AK_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("proposal_scope") == "owner_gated_default_off_observe_only_timer_path_readback_proposal_only"
        and summary.get("p9ak_default_off_observe_only_timer_path_readback_proposal_ready") is True
        and summary.get("eligible_for_future_default_off_observe_only_readback_owner_gate") is True
        and summary.get("prepared_p9ak_proposal") is True
        and summary.get("wrote_p9ak_proposal_body") is True
        and summary.get("proposal_body_sink") == "proof_artifacts_only"
        and summary.get("p9ak_authorizes_dry_load_readback_execution") is False
        and summary.get("future_readback_execution_gate_required") is True
        and summary.get("proposed_future_gate") == P9AL_GATE
        and summary.get("proposed_readback_default_off") is True
        and summary.get("proposed_readback_observe_only") is True
        and summary.get("proposed_readback_mode") == "proposal_only_not_executed"
        and summary.get("proposed_timer_load_mode") == "proposal_only_not_loaded"
        and summary.get("proposed_executor_input_source") == "baseline_only"
        and summary.get("proposed_candidate_artifact_sink") == "proof_artifacts_only"
        and summary.get("proposed_candidate_order_authority") == "disabled"
        and summary.get("proposed_candidate_live_order_submission_authorized") is False
        and summary.get("eligible_for_dry_load_readback_execution") is False
        and summary.get("eligible_for_timer_hook_implementation") is False
        and summary.get("eligible_for_hook_deployment") is False
        and summary.get("eligible_for_timer_path_load") is False
        and summary.get("eligible_for_supervisor_invocation") is False
        and summary.get("eligible_for_remote_sync") is False
        and summary.get("eligible_for_live_order_submission") is False
        and summary.get("eligible_for_stage_governance_change") is False
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
        and summary.get("live_supervisor_source_unchanged") is True
        and summary.get("live_timer_path_loaded") is False
        and summary.get("live_timer_service_enabled_or_invoked") is False
        and summary.get("entered_timer_path") is False
        and summary.get("ran_supervisor") is False
        and summary.get("supervisor_invoked") is False
        and summary.get("timer_path_invoked") is False
        and summary.get("remote_sync_performed") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("remote_control_plane_touched") is False
        and summary.get("candidate_execution_performed") is False
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "fills_observed")
        and summary.get("exchange_order_submission") == "disabled"
        and summary.get("applied_to_live") is False
        and summary.get("live_config_changed") is False
        and summary.get("operator_state_changed") is False
        and summary.get("timer_state_changed") is False
        and summary.get("wrote_live_hook_config") is False
        and summary.get("implemented_hook") is False
        and summary.get("deployed_hook") is False
        and summary.get("loaded_hook") is False
        and summary.get("target_plan_replaced") is False
        and summary.get("executor_input_changed") is False
        and owner.get("decision") == "approve_p9ak_prepare_default_off_observe_only_hook_live_supervisor_timer_path_dry_load_readback_proposal_only"
        and owner.get("p9ak_proposal_preparation_approved") is True
        and owner.get("proposal_body_write_approved") is True
        and owner.get("future_owner_review_discussion_approved") is True
        and owner.get("dry_load_readback_execution_approved") is False
        and owner.get("timer_path_load_approved") is False
        and owner.get("supervisor_invocation_approved") is False
        and owner.get("remote_sync_approved") is False
        and owner.get("live_order_submission_approved") is False
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and all(gates.get(key) is True for key in required_gates)
        and proposed_contract_ready(proposal)
    )


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9AL_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9al_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "allow_future_default_off_observe_only_timer_path_dry_load_readback_execution_only",
        "decision_effect": (
            "authorize_future_default_off_observe_only_timer_path_dry_load_readback_execution_gate_only"
            if approved
            else "none"
        ),
        "p9al_owner_gate_approved": approved,
        "future_default_off_observe_only_readback_execution_gate_approved": approved,
        "write_p9al_owner_gate_artifact_approved": approved,
        "execute_readback_in_p9al_approved": False,
        "dry_load_readback_execution_approved": False,
        "timer_hook_implementation_approved": False,
        "hook_deployment_approved": False,
        "timer_path_load_approved": False,
        "supervisor_invocation_approved": False,
        "remote_sync_approved": False,
        "remote_execution_approved": False,
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


def readback_execution_gate(
    *,
    run_id: str,
    owner_decision: dict[str, Any],
    source_evidence: dict[str, Any],
    ready: bool,
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9al_readback_execution_gate.v1",
        "run_id": run_id,
        "gate_scope": "owner_gated_default_off_observe_only_timer_path_dry_load_readback_execution_permission_only",
        "owner_decision": owner_decision,
        "source_evidence": source_evidence,
        "allowed_next_action": "execute_default_off_observe_only_timer_path_dry_load_readback" if ready else "",
        "allowed_next_gate": P9AM_GATE if ready else "",
        "allowed_next_action_constraints": {
            "default_off_required": True,
            "observe_only_required": True,
            "proof_artifacts_only": True,
            "candidate_order_authority": "disabled",
            "candidate_live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "executor_input_must_remain_baseline_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "candidate_artifacts_under_proof_artifacts_only": True,
            "target_plan_must_not_be_replaced": True,
            "executor_input_must_not_change": True,
            "must_not_modify_mainnet_live_supervisor": True,
            "must_not_modify_live_config": True,
            "must_not_modify_operator_state": True,
            "must_not_modify_timer_or_service_state": True,
            "must_not_enable_live_timer_service": True,
            "must_not_submit_orders": True,
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
            "fills_observed_must_equal": 0,
        },
        "executed_in_p9al": False,
        "explicitly_not_authorized": [
            "execute_readback_inside_p9al",
            "timer_hook_implementation",
            "hook_deployment",
            "timer_path_load",
            "supervisor_invocation",
            "remote_sync",
            "remote_execution",
            "candidate_execution",
            "live_order_submission",
            "target_plan_replacement",
            "executor_input_mutation",
            "live_config_mutation",
            "operator_state_mutation",
            "timer_or_service_mutation",
            "production_timer_service_load",
            "stage_governance_change",
        ],
    }


def non_authorization_matrix(run_id: str, ready: bool) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9al_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "allow_future_default_off_observe_only_readback_execution_gate": ready,
            "write_p9al_owner_gate_artifact_under_proof_artifacts": ready,
            "execute_readback_inside_p9al": False,
            "dry_load_readback_execution": False,
            "timer_hook_implementation": False,
            "hook_deployment": False,
            "timer_path_load": False,
            "supervisor_invocation": False,
            "remote_sync": False,
            "remote_execution": False,
            "candidate_execution": False,
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


def build_phase9al(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = root / "proof_artifacts" / "p9al" / run_id
    proof_root.mkdir(parents=True, exist_ok=True)

    project_profile_path = resolve_path(args.project_profile)
    p9ak_path = (
        resolve_path(args.phase9ak_summary)
        if str(args.phase9ak_summary).strip()
        else latest_match(PHASE9AK_PARENT, "*/summary.json")
    )
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)

    project_profile = load_optional(project_profile_path)
    p9ak = load_optional(p9ak_path)
    proposal_path_text = str(
        dict(p9ak.get("output_files") or {}).get("default_off_observe_only_timer_path_readback_proposal") or ""
    )
    proposal_path = resolve_path(proposal_path_text) if proposal_path_text.strip() else Path("")
    proposal = load_optional(proposal_path)
    current_hook_sha = file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else ""
    supervisor_sha_before = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    supervisor_loads_hook = current_supervisor_loads_hook(supervisor_path)

    decision = owner_decision_record(args, generated_at)
    source_evidence = {
        "project_profile": evidence_file(project_profile_path),
        "phase9ak_summary": evidence_file(p9ak_path),
        "phase9ak_proposal_body": evidence_file(proposal_path),
        "hook_module": evidence_file(hook_path),
        "live_supervisor": evidence_file(supervisor_path),
        "live_config_dir": {
            "path": str(live_config_dir),
            "exists": live_config_dir.exists(),
            "sha256": tree_sha256(live_config_dir),
        },
    }
    p9ak_ok = p9ak_ready_for_p9al(
        p9ak,
        proposal=proposal,
        current_hook_sha256=current_hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
    )

    gates = {
        "owner_decision_p9al_readback_gate_only": str(args.owner_decision) == APPROVE_P9AL_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9ak_default_off_readback_proposal_ready": p9ak_ok,
        "p9ak_proposal_body_ready": proposed_contract_ready(proposal),
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "current_hook_hash_matches_p9ak_source": (
            dict(dict(p9ak.get("source_evidence") or {}).get("hook_module") or {}).get("sha256")
            == current_hook_sha
        ),
        "current_supervisor_hash_matches_p9ak_source": (
            dict(dict(p9ak.get("source_evidence") or {}).get("live_supervisor") or {}).get("sha256")
            == supervisor_sha_before
        ),
        "readback_execution_gate_output_under_proof_artifacts": proof_artifacts_path(str(proof_root)),
        "future_readback_must_be_default_off": True,
        "future_readback_must_be_observe_only": True,
        "future_readback_must_be_proof_artifacts_only": True,
        "future_readback_must_keep_order_authority_disabled": True,
        "future_readback_must_keep_executor_baseline_only": True,
        "future_readback_must_keep_candidate_shadow_only": True,
        "future_readback_must_not_replace_target_plan": True,
        "future_readback_must_not_mutate_executor_input": True,
        "future_readback_must_not_submit_orders": True,
        "no_readback_execution_in_p9al": True,
        "no_timer_hook_implementation_in_p9al": True,
        "no_hook_deployment_in_p9al": True,
        "no_timer_path_load_in_p9al": True,
        "no_supervisor_invocation_in_p9al": True,
        "no_remote_sync_in_p9al": True,
        "no_remote_execution_in_p9al": True,
        "no_candidate_execution_in_p9al": True,
        "no_executor_input_mutation_in_p9al": True,
        "no_target_plan_replacement_in_p9al": True,
        "no_live_mutation_in_p9al": True,
        "zero_orders_fills_in_p9al": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    gate_ready = status == "ready"

    control_boundary_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9al_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "local_source_and_retained_p9ak_proposal_only",
        "live_supervisor": source_evidence["live_supervisor"],
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": file_sha256(supervisor_path) if supervisor_path.exists() else "",
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "eligible_to_execute_default_off_observe_only_readback": gate_ready,
        "executed_default_off_observe_only_readback": False,
        "dry_load_readback_executed": False,
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "ran_supervisor": False,
        "supervisor_invoked": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "remote_control_plane_touched": False,
        "candidate_execution_performed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
    }
    control_boundary_readback["live_supervisor_source_unchanged"] = (
        control_boundary_readback["live_supervisor_sha256_before"]
        == control_boundary_readback["live_supervisor_sha256_after"]
    )

    gate = readback_execution_gate(
        run_id=run_id,
        owner_decision=decision,
        source_evidence=source_evidence,
        ready=gate_ready,
    )
    matrix = non_authorization_matrix(run_id, gate_ready)
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "readback_execution_gate.json", gate)
    write_json(proof_root / "non_authorization_matrix.json", matrix)
    write_json(proof_root / "control_boundary_readback.json", control_boundary_readback)

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "readback_execution_gate": str(proof_root / "readback_execution_gate.json"),
        "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "p9al_default_off_observe_only_readback_owner_gate.md"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": status,
        "blockers": blockers,
        "gate_scope": "owner_gated_default_off_observe_only_timer_path_dry_load_readback_execution_permission_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9al_default_off_observe_only_readback_owner_gate_ready": gate_ready,
        "eligible_to_execute_default_off_observe_only_readback": gate_ready,
        "executed_default_off_observe_only_readback": False,
        "dry_load_readback_executed": False,
        "allowed_next_gate": P9AM_GATE if gate_ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "future_readback_default_off_required": True,
        "future_readback_observe_only_required": True,
        "future_readback_artifact_sink_required": "proof_artifacts_only",
        "future_readback_executor_input_required": "baseline_only",
        "future_readback_candidate_order_authority_required": "disabled",
        "future_readback_live_order_submission_authorized_required": False,
        "future_readback_candidate_execution_authorized_required": False,
        "future_readback_must_not_replace_target_plan": True,
        "future_readback_must_not_mutate_executor_input": True,
        "eligible_for_timer_hook_implementation": False,
        "eligible_for_hook_deployment": False,
        "eligible_for_live_timer_path_load": False,
        "eligible_for_supervisor_invocation": False,
        "eligible_for_remote_sync": False,
        "eligible_for_live_order_submission": False,
        "eligible_for_stage_governance_change": False,
        "dry_load_readback_execution_authorized": False,
        "timer_hook_implementation_authorized": False,
        "hook_deployment_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "production_timer_service_load_authorized": False,
        "repo_stage_change_authorized": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "excluded",
        "candidate_artifact_sink": "proof_artifacts_only",
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_supervisor_source_unchanged": control_boundary_readback["live_supervisor_source_unchanged"],
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "supervisor_invoked": False,
        "timer_path_invoked": False,
        "remote_sync_performed": False,
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
        "recommended_next_gate": P9AM_GATE if gate_ready else "",
        "proof_root": str(proof_root),
        "gates": gates,
        "output_files": output_files,
    }
    write_json(root / "summary.json", summary)
    (root / "p9al_default_off_observe_only_readback_owner_gate.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9AL Default-Off Observe-Only Readback Owner Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9AL only decides whether a future default-off / observe-only timer-path dry-load/readback may be executed.",
        "",
        "```text",
        "gate_scope = owner_gated_default_off_observe_only_timer_path_dry_load_readback_execution_permission_only",
        "eligible_to_execute_default_off_observe_only_readback = "
        f"{str(bool(summary['eligible_to_execute_default_off_observe_only_readback'])).lower()}",
        "executed_default_off_observe_only_readback = false",
        "dry_load_readback_execution_authorized = false",
        "timer_path_load_authorized = false",
        "supervisor_invocation_authorized = false",
        "remote_sync_authorized = false",
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
    summary, exit_code = build_phase9al(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
