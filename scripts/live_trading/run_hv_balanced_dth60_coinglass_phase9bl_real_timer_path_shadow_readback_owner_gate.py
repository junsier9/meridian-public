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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bk_review_after_p9bh_p9bj import (  # noqa: E402
    APPROVE_P9BK_DECISION,
    CONTRACT_VERSION as P9BK_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9BK_PARENT,
    P9BL_GATE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9bl_real_timer_path_shadow_readback_owner_gate.v1"
APPROVE_P9BL_DECISION = (
    "approve_p9bl_allow_default_off_observe_only_real_live_supervisor_timer_path_"
    "shadow_readback_no_order_only"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_p9bl_real_timer_path_shadow_readback_owner_gate"
)

P9BM_GATE = (
    "P9BM_execute_default_off_observe_only_real_live_supervisor_timer_path_shadow_readback_"
    "no_order_only_if_separately_requested"
)
P9BM_SCOPE = (
    "execute_real_live_supervisor_timer_path_shadow_readback_default_off_observe_only_"
    "baseline_executor_candidate_shadow_no_order"
)


FALSE_SUMMARY_KEYS = (
    "define_next_gate_scope_authorized",
    "next_gate_execution_authorized",
    "timer_path_shadow_readback_execution_authorized",
    "timer_path_shadow_readback_authorized",
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

FALSE_OWNER_KEYS = (
    "define_next_gate_scope_approved",
    "next_gate_execution_approved",
    "timer_path_shadow_readback_execution_approved",
    "dry_load_readback_execution_approved",
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9BL: an owner gate that permits a future separately requested "
            "default-off/observe-only candidate hook shadow readback in the real "
            "live-supervisor/timer path. P9BL itself does not execute the readback, "
            "load the timer path, invoke the supervisor, remote sync, mutate live "
            "config/operator/timer/executor state, replace target plans, execute "
            "the candidate, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9bk-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BL_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9bl_allow_real_timer_path_shadow_readback_no_order_only",
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


def latest_p9bk_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bk_summary).strip():
        return resolve_path(args.phase9bk_summary)
    return latest_match(P9BK_PARENT, "*/summary.json")


def all_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def all_authorizations_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    authorizations = dict(payload.get("authorizations") or {})
    return all(authorizations.get(key) is False for key in keys)


def p9bk_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    return {
        "owner_decision_record": source_output_path(summary, "owner_decision_record"),
        "owner_review_packet": source_output_path(summary, "owner_review_packet"),
        "sufficiency_checklist": source_output_path(summary, "sufficiency_checklist"),
        "non_authorization_matrix": source_output_path(summary, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(summary, "control_boundary_readback"),
    }


def p9bk_ready_for_p9bl(
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
    summary_owner = dict(summary.get("owner_decision") or {})
    review_owner = dict(review_packet.get("owner_decision") or {})
    checks = dict(checklist.get("checks") or {})
    forbidden_authorizations = (
        "define_next_gate_scope",
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
        summary.get("contract_version") == P9BK_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9bk_retained_evidence_review_ready") is True
        and summary.get("p9bh_p9bj_retained_evidence_sufficient") is True
        and summary.get("sufficient_for_next_owner_gate_discussion") is True
        and summary.get("eligible_for_future_p9bl_owner_gate_request") is True
        and summary.get("allowed_next_gate") == P9BL_GATE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_overlay_execution_path") == "shadow_only_not_executor"
        and summary.get("candidate_artifact_sink") == "proof_artifacts_only"
        and summary.get("executor_consumes_baseline_only") is True
        and summary.get("candidate_plan_referenced_by_executor") is False
        and all_false(summary, FALSE_SUMMARY_KEYS)
        and no_live_mutation(summary)
        and zero_orders_fills(summary)
        and owner_record.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bk_owner_decision.v1"
        and owner_record.get("decision") == APPROVE_P9BK_DECISION
        and owner_record.get("retained_evidence_review_approved") is True
        and owner_record.get("p9bh_p9bj_sufficiency_review_approved") is True
        and all_false(owner_record, FALSE_OWNER_KEYS)
        and summary_owner == owner_record
        and review_packet.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bk_owner_review_packet.v1"
        and review_packet.get("p9bh_p9bj_retained_evidence_sufficient") is True
        and review_packet.get("sufficient_for_next_owner_gate_discussion") is True
        and review_packet.get("allowed_next_gate") == P9BL_GATE
        and review_packet.get("allowed_next_gate_must_be_separately_requested") is True
        and review_packet.get("define_next_gate_scope_authorized") is False
        and review_packet.get("next_gate_execution_authorized") is False
        and review_packet.get("timer_path_shadow_readback_execution_authorized") is False
        and review_packet.get("live_order_submission_authorized") is False
        and zero_orders_fills(review_packet)
        and no_live_mutation(review_packet)
        and review_owner == owner_record
        and checklist.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bk_sufficiency_checklist.v1"
        and checks.get("p9bh_p9bj_status_ready") is True
        and checks.get("p9bi_readback_executed") is True
        and checks.get("p9bi_scope_local_proof_only") is True
        and checks.get("baseline_executor_input_hash_unchanged") is True
        and checks.get("executor_consumes_baseline_only") is True
        and checks.get("candidate_not_executed") is True
        and checks.get("live_timer_path_not_loaded") is True
        and checks.get("supervisor_not_run") is True
        and checks.get("remote_not_touched") is True
        and checks.get("zero_orders_fills") is True
        and checks.get("next_scope_not_defined_in_p9bk") is True
        and checks.get("live_order_not_authorized") is True
        and matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bk_non_authorization_matrix.v1"
        and dict(matrix.get("authorizations") or {}).get("retained_evidence_review") is True
        and dict(matrix.get("authorizations") or {}).get("future_next_owner_gate_request") is True
        and all_authorizations_false(matrix, forbidden_authorizations)
        and control.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bk_control_boundary_readback.v1"
        and control.get("live_supervisor_source_unchanged") is True
        and control.get("live_supervisor_loads_candidate_hook") is False
        and control.get("live_config_dir_unchanged") is True
        and control.get("define_next_gate_scope_authorized") is False
        and control.get("next_gate_execution_authorized") is False
        and control.get("timer_path_shadow_readback_execution_authorized") is False
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
        and control.get("executor_input_changed") is False
        and control.get("target_plan_replaced") is False
        and no_live_mutation(control)
        and zero_orders_fills(control)
        and paths["owner_decision_record"].exists()
        and paths["owner_review_packet"].exists()
        and paths["sufficiency_checklist"].exists()
        and paths["non_authorization_matrix"].exists()
        and paths["control_boundary_readback"].exists()
        and output_under_proof_artifacts(paths["owner_review_packet"])
        and output_under_proof_artifacts(paths["sufficiency_checklist"])
        and output_under_proof_artifacts(paths["non_authorization_matrix"])
        and output_under_proof_artifacts(paths["control_boundary_readback"])
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def build_owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9BL_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bl_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": (
            "allow_future_default_off_observe_only_real_live_supervisor_timer_path_"
            "shadow_readback_no_order_only"
        ),
        "decision_effect": "allow_future_p9bm_real_timer_path_shadow_readback_no_order_only"
        if approved
        else "none",
        "future_real_timer_path_shadow_readback_approved": approved,
        "p9bm_execution_gate_approved": approved,
        "execute_readback_inside_p9bl_approved": False,
        "candidate_execution_approved": False,
        "candidate_live_order_submission_approved": False,
        "timer_hook_implementation_approved": False,
        "hook_deployment_approved": False,
        "live_timer_path_load_approved_in_p9bl": False,
        "production_timer_service_load_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "remote_sync_approved_in_p9bl": False,
        "remote_execution_approved_in_p9bl": False,
        "supervisor_invocation_approved_in_p9bl": False,
        "supervisor_run_approved_in_p9bl": False,
        "repo_stage_change_approved": False,
    }


def build_execution_permission(
    *,
    run_id: str,
    decision: dict[str, Any],
    source_evidence: dict[str, Any],
    ready: bool,
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bl_execution_permission.v1",
        "run_id": run_id,
        "permission_kind": "future_real_live_supervisor_timer_path_shadow_readback_no_order_only",
        "permission_ready": ready,
        "source_evidence": source_evidence,
        "owner_decision": decision,
        "allowed_next_gate": P9BM_GATE if ready else "",
        "allowed_next_gate_scope": P9BM_SCOPE if ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "readback_execution_authorized_for_future_gate": ready,
        "readback_executed_in_p9bl": False,
        "real_live_supervisor_timer_path_allowed_for_future_gate": ready,
        "default_enabled": False,
        "observe_only": True,
        "candidate_order_authority": "disabled",
        "executor_target_source": "baseline_only",
        "candidate_shadow_only": True,
        "candidate_plan_must_not_be_referenced_by_executor": True,
        "future_p9bm_must_reprove": {
            "fresh_timer_path_readback_proof": True,
            "fresh_account_read_if_remote_or_account_state_is_used": True,
            "same_risk_inputs_as_baseline_plan": True,
            "baseline_only_executor_input": True,
            "candidate_shadow_artifact_only": True,
            "candidate_plan_not_referenced_by_executor": True,
            "target_plan_not_replaced": True,
            "executor_input_not_mutated": True,
            "zero_order_delta": True,
            "zero_cancel_delta": True,
            "zero_fill_delta": True,
            "zero_trade_delta": True,
            "pre_post_live_config_fingerprint_unchanged": True,
            "pre_post_operator_state_fingerprint_unchanged": True,
            "pre_post_timer_state_fingerprint_unchanged": True,
            "production_timer_service_not_enabled_or_mutated": True,
            "live_order_submission_authorized": False,
        },
        "disallowed_in_p9bl": {
            "execute_readback": True,
            "load_timer_path": True,
            "invoke_supervisor": True,
            "run_supervisor": True,
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


def no_order_boundary(*, ready: bool, supervisor_loads_hook: bool) -> dict[str, Any]:
    return {
        "future_real_timer_path_shadow_readback_authorized": ready,
        "p9bm_execution_gate_authorized": ready,
        "real_live_supervisor_timer_path_allowed_for_future_gate": ready,
        "real_timer_path_shadow_readback_execution_authorized_for_future_gate": ready,
        "execute_readback_inside_p9bl_authorized": False,
        "real_timer_path_shadow_readback_executed_in_p9bl": False,
        "timer_path_load_authorized_in_p9bl": False,
        "supervisor_invocation_authorized_in_p9bl": False,
        "supervisor_run_authorized_in_p9bl": False,
        "remote_sync_authorized_in_p9bl": False,
        "remote_execution_authorized_in_p9bl": False,
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
        "candidate_artifact_sink": "proof_artifacts_only_until_p9bm",
        "executor_consumes_baseline_only": True,
        "candidate_shadow_only": True,
        "candidate_plan_referenced_by_executor": False,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
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


def build_phase9bl(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9bl" / run_id

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9bk": latest_p9bk_summary(args),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
        "live_config_dir": resolve_path(args.live_config_dir),
    }
    project_profile = load_optional(paths["project_profile"])
    p9bk = load_optional(paths["phase9bk"])
    p9bk_paths = p9bk_output_paths(p9bk)
    p9bk_owner = load_optional(p9bk_paths["owner_decision_record"])
    p9bk_review = load_optional(p9bk_paths["owner_review_packet"])
    p9bk_checklist = load_optional(p9bk_paths["sufficiency_checklist"])
    p9bk_matrix = load_optional(p9bk_paths["non_authorization_matrix"])
    p9bk_control = load_optional(p9bk_paths["control_boundary_readback"])

    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_before = tree_sha256(paths["live_config_dir"])
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    decision = build_owner_decision_record(args, generated_at)
    p9bk_ok = p9bk_ready_for_p9bl(
        p9bk,
        p9bk_owner,
        p9bk_review,
        p9bk_checklist,
        p9bk_matrix,
        p9bk_control,
        p9bk_paths,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9bk_summary": evidence_file(paths["phase9bk"]),
        "phase9bk_owner_decision_record": evidence_file(p9bk_paths["owner_decision_record"]),
        "phase9bk_owner_review_packet": evidence_file(p9bk_paths["owner_review_packet"]),
        "phase9bk_sufficiency_checklist": evidence_file(p9bk_paths["sufficiency_checklist"]),
        "phase9bk_non_authorization_matrix": evidence_file(p9bk_paths["non_authorization_matrix"]),
        "phase9bk_control_boundary_readback": evidence_file(p9bk_paths["control_boundary_readback"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
        "live_config_dir": {
            "path": str(paths["live_config_dir"]),
            "exists": paths["live_config_dir"].exists(),
            "sha256": live_config_sha_before,
        },
    }

    owner_ok = str(args.owner_decision) == APPROVE_P9BL_DECISION
    base_ready = (
        owner_ok
        and project_profile.get("current_stage") == "stage_1_research_readiness_only"
        and p9bk_ok
        and supervisor_loads_hook is False
        and output_under_proof_artifacts(proof_root / "execution_permission.json")
        and output_under_proof_artifacts(proof_root / "acceptance_contract.json")
        and output_under_proof_artifacts(proof_root / "non_authorization_matrix.json")
        and output_under_proof_artifacts(proof_root / "control_boundary_readback.json")
    )
    permission = build_execution_permission(
        run_id=run_id,
        decision=decision,
        source_evidence=source_evidence,
        ready=base_ready,
    )
    acceptance = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bl_acceptance_contract.v1",
        "run_id": run_id,
        "accepted_next_gate": P9BM_GATE if base_ready else "",
        "p9bm_required_mode": "real_live_supervisor_timer_path_shadow_readback_no_order",
        "p9bm_must_be_separately_requested": True,
        "checks_required_before_p9bm_can_pass": {
            "default_off": True,
            "observe_only": True,
            "baseline_only_executor": True,
            "candidate_shadow_only": True,
            "candidate_plan_not_referenced_by_executor": True,
            "fresh_proof": True,
            "same_risk_inputs": True,
            "zero_orders": True,
            "zero_cancels": True,
            "zero_fills": True,
            "zero_trades": True,
            "no_target_plan_replacement": True,
            "no_executor_input_mutation": True,
            "no_live_config_mutation": True,
            "no_operator_state_mutation": True,
            "no_timer_state_mutation": True,
            "production_timer_service_not_enabled": True,
            "live_order_submission_authorized": False,
        },
        "p9bl_executed_readback": False,
        "p9bl_loaded_timer_path": False,
        "p9bl_invoked_supervisor": False,
        "p9bl_remote_synced": False,
        "p9bl_submitted_orders": False,
    }
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bl_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "future_real_timer_path_shadow_readback": base_ready,
            "p9bm_execution_gate": base_ready,
            "execute_readback_inside_p9bl": False,
            "candidate_execution": False,
            "candidate_live_order_submission": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "production_timer_service_load": False,
            "remote_sync_inside_p9bl": False,
            "remote_execution_inside_p9bl": False,
            "supervisor_invocation_inside_p9bl": False,
            "supervisor_run_inside_p9bl": False,
            "stage_governance_change": False,
        },
    }
    supervisor_sha_after = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_after = tree_sha256(paths["live_config_dir"])
    control_boundary_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bl_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "owner_gate_allow_future_real_timer_path_shadow_readback_no_order_only",
        "live_supervisor": source_evidence["live_supervisor"],
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        **no_order_boundary(ready=base_ready, supervisor_loads_hook=supervisor_loads_hook),
    }
    gates = {
        "owner_decision_p9bl_allow_future_real_timer_path_shadow_readback_no_order_only": owner_ok,
        "project_stage_boundary_preserved": project_profile.get("current_stage")
        == "stage_1_research_readiness_only",
        "p9bk_retained_evidence_ready_for_p9bl": p9bk_ok,
        "p9bk_allows_p9bl_only": p9bk.get("allowed_next_gate") == P9BL_GATE
        and p9bk.get("eligible_for_future_p9bl_owner_gate_request") is True,
        "p9bk_required_separate_request": p9bk.get("allowed_next_gate_must_be_separately_requested")
        is True,
        "p9bk_did_not_authorize_execution": p9bk.get("next_gate_execution_authorized") is False
        and p9bk.get("timer_path_shadow_readback_execution_authorized") is False,
        "current_live_supervisor_not_already_loading_hook": supervisor_loads_hook is False,
        "current_hook_hash_matches_p9bk_source": dict(
            dict(p9bk.get("source_evidence") or {}).get("hook_module") or {}
        ).get("sha256")
        == hook_sha,
        "current_supervisor_hash_matches_p9bk_source": dict(
            dict(p9bk.get("source_evidence") or {}).get("live_supervisor") or {}
        ).get("sha256")
        == supervisor_sha_before,
        "current_live_config_hash_matches_p9bk_source": dict(
            dict(p9bk.get("source_evidence") or {}).get("live_config_dir") or {}
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
        "p9bl_does_not_execute_readback": True,
        "p9bl_does_not_enter_timer_path": True,
        "p9bl_does_not_run_supervisor": True,
        "p9bl_does_not_remote_sync": True,
        "p9bl_does_not_mutate_executor_input": True,
        "p9bl_does_not_replace_target_plan": True,
        "p9bl_does_not_mutate_live_config": True,
        "p9bl_does_not_mutate_operator_state": True,
        "p9bl_does_not_mutate_timer_state": True,
        "p9bl_keeps_live_order_submission_disabled": True,
        "p9bm_must_be_separately_requested": True,
        "p9bm_must_remain_no_order": True,
        "zero_orders_fills_in_p9bl": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    ready = status == "ready"
    # Rebuild ready-dependent payloads after all gates are evaluated.
    permission = build_execution_permission(
        run_id=run_id,
        decision=decision,
        source_evidence=source_evidence,
        ready=ready,
    )
    non_authorization_matrix["authorizations"]["future_real_timer_path_shadow_readback"] = ready
    non_authorization_matrix["authorizations"]["p9bm_execution_gate"] = ready
    control_boundary_readback.update(no_order_boundary(ready=ready, supervisor_loads_hook=supervisor_loads_hook))

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "execution_permission": str(proof_root / "execution_permission.json"),
        "acceptance_contract": str(proof_root / "acceptance_contract.json"),
        "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "p9bl_real_timer_path_shadow_readback_owner_gate.md"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "gate_scope": "p9bl_allow_future_real_timer_path_shadow_readback_no_order_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9bl_owner_gate_ready": ready,
        "p9bk_retained_evidence_ready_for_p9bl": p9bk_ok,
        "eligible_for_future_p9bm_real_timer_path_shadow_readback": ready,
        "allowed_next_gate": P9BM_GATE if ready else "",
        "recommended_next_gate": P9BM_GATE if ready else "",
        "allowed_next_gate_scope": P9BM_SCOPE if ready else "",
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
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix)
    write_json(proof_root / "control_boundary_readback.json", control_boundary_readback)
    write_json(root / "summary.json", summary)
    (root / "p9bl_real_timer_path_shadow_readback_owner_gate.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9BL Real Timer-Path Shadow Readback Owner Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9BL allows only a future separately requested no-order real live-supervisor/timer-path shadow readback gate.",
        "",
        "```text",
        f"p9bl_owner_gate_ready = {str(bool(summary['p9bl_owner_gate_ready'])).lower()}",
        f"allowed_next_gate = {summary['allowed_next_gate']}",
        "future_real_timer_path_shadow_readback_authorized = "
        f"{str(bool(summary['future_real_timer_path_shadow_readback_authorized'])).lower()}",
        "real_timer_path_shadow_readback_executed_in_p9bl = false",
        "timer_path_load_authorized_in_p9bl = false",
        "supervisor_invocation_authorized_in_p9bl = false",
        "candidate_execution_authorized = false",
        "live_order_submission_authorized = false",
        "execution_target_source = baseline_only",
        "candidate_artifact_sink = proof_artifacts_only_until_p9bm",
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
    summary, exit_code = build_phase9bl(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    print(f"allowed_next_gate={summary['allowed_next_gate']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
