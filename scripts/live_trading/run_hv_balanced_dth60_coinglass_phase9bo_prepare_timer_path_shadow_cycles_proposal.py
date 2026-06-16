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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bn_review_after_p9bm import (  # noqa: E402
    APPROVE_P9BN_DECISION,
    CONTRACT_VERSION as P9BN_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9BN_PARENT,
    P9BO_GATE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9bo_timer_path_shadow_cycles_proposal.v1"
APPROVE_P9BO_DECISION = (
    "approve_p9bo_prepare_default_off_observe_only_continuous_real_timer_path_"
    "shadow_cycles_proposal_review_package_only"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_p9bo_timer_path_shadow_cycles_proposal"
)
P9BP_GATE = (
    "P9BP_owner_gate_allow_continuous_real_timer_path_shadow_cycles_no_order_"
    "only_if_separately_requested"
)
P9BP_SCOPE = (
    "decide_whether_to_execute_at_least_3_continuous_real_timer_path_shadow_cycles_"
    "default_off_observe_only_baseline_executor_candidate_shadow_no_order"
)


FALSE_RUNTIME_KEYS = (
    "continuous_timer_path_shadow_cycles_execution_authorized",
    "timer_path_shadow_readback_execution_authorized",
    "timer_path_shadow_readback_authorized",
    "dry_load_readback_execution_authorized",
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
    "continuous_timer_path_shadow_cycles_executed",
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

P9BN_FALSE_RUNTIME_KEYS = tuple(
    key for key in FALSE_RUNTIME_KEYS if not key.startswith("continuous_timer_path_shadow_cycles_")
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9BO: prepare only a proposal/review package for a future "
            "default-off/observe-only continuous real timer-path shadow-cycle "
            "readback. P9BO does not execute cycles, enter timer path, invoke "
            "the supervisor, remote sync, execute the candidate, mutate live "
            "state or executor input, replace target plans, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9bn-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BO_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9bo_prepare_timer_path_shadow_cycles_proposal_review_package",
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


def latest_p9bn_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bn_summary).strip():
        return resolve_path(args.phase9bn_summary)
    return latest_match(P9BN_PARENT, "*/summary.json")


def all_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def p9bn_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    return {
        "owner_decision_record": source_output_path(summary, "owner_decision_record"),
        "owner_review_packet": source_output_path(summary, "owner_review_packet"),
        "sufficiency_checklist": source_output_path(summary, "sufficiency_checklist"),
        "non_authorization_matrix": source_output_path(summary, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(summary, "control_boundary_readback"),
    }


def authorizations_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    authorizations = dict(payload.get("authorizations") or {})
    return all(authorizations.get(key) is False for key in keys)


def p9bn_ready_for_p9bo(
    summary: dict[str, Any],
    owner_record: dict[str, Any],
    review_packet: dict[str, Any],
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
    checks = dict(checklist.get("checks") or {})
    forbidden_authorizations = (
        "prepare_proposal",
        "proposal_execution",
        "next_gate_execution",
        "timer_path_shadow_readback_execution",
        "candidate_execution",
        "candidate_live_order_submission",
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
        summary.get("contract_version") == P9BN_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9bn_owner_gate_ready") is True
        and summary.get("p9bm_retained_evidence_sufficient") is True
        and summary.get("sufficient_for_next_proposal_review_gate") is True
        and summary.get("eligible_for_future_p9bo_proposal_review_gate_request") is True
        and summary.get("allowed_next_gate") == P9BO_GATE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("proposal_preparation_authorized") is False
        and all_false(summary, P9BN_FALSE_RUNTIME_KEYS)
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_overlay_execution_path") == "shadow_only_not_executor"
        and summary.get("candidate_artifact_sink") == "proof_artifacts_only"
        and summary.get("executor_consumes_baseline_only") is True
        and summary.get("candidate_plan_referenced_by_executor") is False
        and zero_orders_fills(summary)
        and owner_record.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bn_owner_decision.v1"
        and owner_record.get("decision") == APPROVE_P9BN_DECISION
        and owner_record.get("retained_evidence_review_approved") is True
        and owner_record.get("p9bm_sufficiency_review_approved") is True
        and owner_record.get("future_proposal_review_gate_discussion_approved") is True
        and owner_record.get("prepare_proposal_approved") is False
        and owner_record.get("proposal_execution_approved") is False
        and owner_record.get("next_gate_execution_approved") is False
        and review_packet.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bn_owner_review_packet.v1"
        and review_packet.get("p9bm_retained_evidence_sufficient") is True
        and review_packet.get("sufficient_for_next_proposal_review_gate") is True
        and review_packet.get("allowed_next_gate") == P9BO_GATE
        and review_packet.get("proposal_preparation_authorized") is False
        and review_packet.get("next_gate_execution_authorized") is False
        and review_packet.get("timer_path_shadow_readback_execution_authorized") is False
        and review_packet.get("supervisor_invocation_authorized") is False
        and review_packet.get("candidate_execution_authorized") is False
        and review_packet.get("live_order_submission_authorized") is False
        and checklist.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bn_sufficiency_checklist.v1"
        and all(checks.get(key) is True for key in checks)
        and matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bn_non_authorization_matrix.v1"
        and dict(matrix.get("authorizations") or {}).get("future_proposal_review_gate_discussion") is True
        and authorizations_false(matrix, forbidden_authorizations)
        and control.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bn_control_boundary_readback.v1"
        and control.get("live_supervisor_source_unchanged") is True
        and control.get("live_supervisor_loads_candidate_hook") is False
        and control.get("live_config_dir_unchanged") is True
        and control.get("proposal_preparation_authorized") is False
        and control.get("next_gate_execution_authorized") is False
        and control.get("timer_path_shadow_readback_execution_authorized") is False
        and control.get("supervisor_invocation_authorized") is False
        and control.get("candidate_execution_authorized") is False
        and control.get("live_order_submission_authorized") is False
        and all_false(control, P9BN_FALSE_RUNTIME_KEYS)
        and zero_orders_fills(control)
        and all(path.exists() for path in paths.values() if str(path))
        and output_under_proof_artifacts(paths["owner_review_packet"])
        and output_under_proof_artifacts(paths["sufficiency_checklist"])
        and output_under_proof_artifacts(paths["non_authorization_matrix"])
        and output_under_proof_artifacts(paths["control_boundary_readback"])
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9BO_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bo_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "prepare_continuous_real_timer_path_shadow_cycles_proposal_review_package_only",
        "decision_effect": "prepare_p9bo_proposal_review_package_under_proof_artifacts_only"
        if approved
        else "none",
        "proposal_review_package_preparation_approved": approved,
        "future_continuous_timer_path_shadow_cycles_owner_gate_discussion_approved": approved,
        "continuous_timer_path_shadow_cycles_execution_approved": False,
        "timer_path_shadow_readback_execution_approved": False,
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


def acceptance_contract(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bo_acceptance_contract.v1",
        "run_id": run_id,
        "future_gate": P9BP_GATE,
        "future_gate_scope": P9BP_SCOPE,
        "future_gate_must_be_separately_requested": True,
        "minimum_cycle_count": 3,
        "cycles_must_be_continuous": True,
        "cycles_must_share_same_no_order_config": True,
        "cycles_must_use_real_live_supervisor_timer_path": True,
        "production_timer_service_load_requires_separate_gate": True,
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
        "candidate_order_authority": "disabled",
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "allowed_next_step_after_future_success": "owner_review_only",
    }


def proposal_review_package(
    *,
    run_id: str,
    decision: dict[str, Any],
    source_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bo_proposal_review_package.v1",
        "run_id": run_id,
        "package_type": "continuous_real_timer_path_shadow_cycles_proposal_review_package",
        "package_prepared": True,
        "package_sink": "proof_artifacts_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "proposed_future_gate": P9BP_GATE,
        "proposed_future_gate_scope": P9BP_SCOPE,
        "proposed_future_gate_must_be_separately_requested": True,
        "proposal_objective": (
            "prove at least three continuous real timer-path shadow cycles with fresh proof, "
            "baseline-only executor input, candidate shadow artifacts only, zero orders/fills, "
            "and no control-plane anomalies"
        ),
        "acceptance_contract": acceptance_contract(run_id),
        "execution_authorized_in_p9bo": False,
        "supervisor_invocation_authorized_in_p9bo": False,
        "remote_sync_authorized_in_p9bo": False,
        "candidate_execution_authorized_in_p9bo": False,
        "live_order_submission_authorized_in_p9bo": False,
    }


def non_authorization_matrix(run_id: str, ready: bool) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bo_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "proposal_review_package_preparation": ready,
            "future_continuous_timer_path_shadow_cycles_owner_gate_discussion": ready,
            "continuous_timer_path_shadow_cycles_execution": False,
            "timer_path_shadow_readback_execution": False,
            "supervisor_invocation": False,
            "supervisor_run": False,
            "remote_sync": False,
            "remote_execution": False,
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


def boundary(*, ready: bool) -> dict[str, Any]:
    payload = {
        "proposal_review_package_preparation_authorized": ready,
        "future_continuous_timer_path_shadow_cycles_owner_gate_discussion_authorized": ready,
        "allowed_next_gate": P9BP_GATE if ready else "",
        "allowed_next_gate_scope": P9BP_SCOPE if ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "shadow_only_not_executor",
        "candidate_artifact_sink": "proof_artifacts_only",
        "executor_consumes_baseline_only": True,
        "candidate_plan_referenced_by_executor": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "fills_observed": 0,
        "trade_count": 0,
        "exchange_order_submission": "disabled",
    }
    for key in FALSE_RUNTIME_KEYS:
        payload[key] = False
    return payload


def build_p9bo(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9bo" / run_id

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9bn": latest_p9bn_summary(args),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
        "live_config_dir": resolve_path(args.live_config_dir),
    }
    project_profile = load_optional(paths["project_profile"])
    p9bn = load_optional(paths["phase9bn"])
    p9bn_paths = p9bn_output_paths(p9bn)
    p9bn_owner = load_optional(p9bn_paths["owner_decision_record"])
    p9bn_review = load_optional(p9bn_paths["owner_review_packet"])
    p9bn_checklist = load_optional(p9bn_paths["sufficiency_checklist"])
    p9bn_matrix = load_optional(p9bn_paths["non_authorization_matrix"])
    p9bn_control = load_optional(p9bn_paths["control_boundary_readback"])

    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_before = tree_sha256(paths["live_config_dir"])
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    supervisor_sha_after = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_after = tree_sha256(paths["live_config_dir"])
    decision = owner_decision_record(args, generated_at)

    p9bn_ok = p9bn_ready_for_p9bo(
        p9bn,
        p9bn_owner,
        p9bn_review,
        p9bn_checklist,
        p9bn_matrix,
        p9bn_control,
        p9bn_paths,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9bn_summary": evidence_file(paths["phase9bn"]),
        "phase9bn_owner_decision_record": evidence_file(p9bn_paths["owner_decision_record"]),
        "phase9bn_owner_review_packet": evidence_file(p9bn_paths["owner_review_packet"]),
        "phase9bn_sufficiency_checklist": evidence_file(p9bn_paths["sufficiency_checklist"]),
        "phase9bn_non_authorization_matrix": evidence_file(p9bn_paths["non_authorization_matrix"]),
        "phase9bn_control_boundary_readback": evidence_file(p9bn_paths["control_boundary_readback"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
        "live_config_dir": {
            "path": str(paths["live_config_dir"]),
            "exists": paths["live_config_dir"].exists(),
            "sha256": live_config_sha_before,
        },
    }
    gates = {
        "owner_decision_p9bo_prepare_package_only": str(args.owner_decision) == APPROVE_P9BO_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage")
        == "stage_1_research_readiness_only",
        "p9bn_ready_for_p9bo": p9bn_ok,
        "p9bn_allows_p9bo_only": p9bn.get("allowed_next_gate") == P9BO_GATE
        and p9bn.get("eligible_for_future_p9bo_proposal_review_gate_request") is True,
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "current_hook_hash_matches_p9bn_source": dict(
            dict(p9bn.get("source_evidence") or {}).get("hook_module") or {}
        ).get("sha256")
        == hook_sha,
        "current_supervisor_hash_matches_p9bn_source": dict(
            dict(p9bn.get("source_evidence") or {}).get("live_supervisor") or {}
        ).get("sha256")
        == supervisor_sha_before,
        "current_live_config_hash_matches_p9bn_source": dict(
            dict(p9bn.get("source_evidence") or {}).get("live_config_dir") or {}
        ).get("sha256")
        == live_config_sha_before,
        "proposal_package_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "proposal_review_package.json"
        ),
        "acceptance_contract_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "acceptance_contract.json"
        ),
        "p9bo_does_not_execute_cycles": True,
        "p9bo_does_not_enter_timer_path": True,
        "p9bo_does_not_invoke_supervisor": True,
        "p9bo_does_not_remote_sync": True,
        "p9bo_does_not_mutate_executor_input": True,
        "p9bo_does_not_replace_target_plan": True,
        "p9bo_does_not_mutate_live_config": True,
        "p9bo_does_not_mutate_operator_state": True,
        "p9bo_does_not_mutate_timer_state": True,
        "p9bo_keeps_order_authority_disabled": True,
        "future_p9bp_must_be_separately_requested": True,
        "zero_orders_fills_in_p9bo": True,
    }
    status = "ready" if all(gates.values()) else "blocked"
    ready = status == "ready"
    package = proposal_review_package(
        run_id=run_id,
        decision=decision,
        source_evidence=source_evidence,
    )
    accept = acceptance_contract(run_id)
    review_checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bo_review_checklist.v1",
        "run_id": run_id,
        "checks": {
            "minimum_cycle_count_is_three": accept["minimum_cycle_count"] == 3,
            "fresh_proof_each_cycle_required": accept["fresh_proof_each_cycle"] is True,
            "same_risk_inputs_required": accept["same_risk_inputs_as_baseline_plan_each_cycle"]
            is True,
            "baseline_only_executor_required": accept["baseline_only_executor_input_each_cycle"] is True,
            "candidate_shadow_only_required": accept["candidate_shadow_only_each_cycle"] is True,
            "candidate_artifacts_proof_only_required": accept[
                "candidate_artifacts_under_proof_artifacts_only_each_cycle"
            ]
            is True,
            "candidate_plan_not_referenced_required": accept[
                "candidate_plan_must_not_be_referenced_by_executor_each_cycle"
            ]
            is True,
            "zero_order_cancel_fill_trade_required": (
                accept["zero_order_delta_each_cycle"]
                and accept["zero_cancel_delta_each_cycle"]
                and accept["zero_fill_delta_each_cycle"]
                and accept["zero_trade_delta_each_cycle"]
            ),
            "no_live_config_operator_timer_mutation_required": (
                accept["live_config_must_not_change"]
                and accept["operator_state_must_not_change"]
                and accept["timer_state_must_not_change"]
            ),
            "p9bo_execution_not_authorized": True,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bo_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "prepare_timer_path_shadow_cycles_proposal_review_package_only",
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        **boundary(ready=ready),
    }
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "proposal_review_package": str(proof_root / "proposal_review_package.json"),
        "acceptance_contract": str(proof_root / "acceptance_contract.json"),
        "review_checklist": str(proof_root / "review_checklist.json"),
        "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "p9bo_timer_path_shadow_cycles_proposal.md"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "gate_scope": "p9bo_prepare_timer_path_shadow_cycles_proposal_review_package_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9bo_proposal_review_package_ready": ready,
        "proposal_review_package_prepared": ready,
        "proposal_review_package_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "proposal_review_package.json"
        ),
        "eligible_for_future_p9bp_owner_gate_request": ready,
        "recommended_next_gate": P9BP_GATE if ready else "",
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "gates": gates,
        "blockers": [key for key, value in gates.items() if not value],
        "output_files": output_files,
        **boundary(ready=ready),
    }
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "proposal_review_package.json", package)
    write_json(proof_root / "acceptance_contract.json", accept)
    write_json(proof_root / "review_checklist.json", review_checklist)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix(run_id, ready))
    write_json(proof_root / "control_boundary_readback.json", control)
    write_json(root / "summary.json", summary)
    (root / "p9bo_timer_path_shadow_cycles_proposal.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9BO Timer-Path Shadow Cycles Proposal",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9BO only prepares the proposal/review package for a future continuous real timer-path shadow-cycle readback.",
        "",
        "```text",
        f"p9bo_proposal_review_package_ready = {str(bool(summary['p9bo_proposal_review_package_ready'])).lower()}",
        f"allowed_next_gate = {summary['allowed_next_gate']}",
        "continuous_timer_path_shadow_cycles_execution_authorized = false",
        "timer_path_shadow_readback_execution_authorized = false",
        "supervisor_invocation_authorized = false",
        "remote_sync_authorized = false",
        "candidate_execution_authorized = false",
        "live_order_submission_authorized = false",
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
    summary, exit_code = build_p9bo(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    print(f"allowed_next_gate={summary['allowed_next_gate']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
