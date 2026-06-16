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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9aw_review_after_p9av import (  # noqa: E402
    APPROVE_P9AW_DECISION,
    CONTRACT_VERSION as P9AW_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9AW_PARENT,
    P9AX_GATE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9ax_define_next_scope_after_p9aw.v1"
APPROVE_P9AX_DECISION = "approve_p9ax_define_next_gate_scope_after_p9aw_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ax_define_next_scope_after_p9aw"

NEXT_GATE_ID = (
    "P9AY_allow_prepare_default_off_observe_only_live_supervisor_timer_path_shadow_readback_gate_"
    "only_if_separately_requested"
)
NEXT_GATE_SCOPE = (
    "owner_gated_allow_prepare_default_off_observe_only_live_supervisor_timer_path_shadow_"
    "readback_gate_scope_only"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9AX: a proof-only concrete scope definition after P9AW. "
            "P9AX only defines the next gate's scope: whether to allow preparing "
            "a default-off/observe-only live-supervisor timer-path shadow readback "
            "gate. It does not prepare a proposal, execute a dry-load/readback, "
            "enter timer path, invoke the supervisor, remote sync, mutate live "
            "state or executor input, replace target plans, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9aw-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AX_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9ax_define_scope_for_default_off_observe_only_timer_path_shadow_readback_gate_only",
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


def latest_p9aw_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9aw_summary).strip():
        return resolve_path(args.phase9aw_summary)
    return latest_match(P9AW_PARENT, "*/summary.json")


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


def p9aw_output_paths(p9aw: dict[str, Any]) -> dict[str, Path]:
    return {
        "owner_decision_record": source_output_path(p9aw, "owner_decision_record"),
        "owner_review_packet": source_output_path(p9aw, "owner_review_packet"),
        "sufficiency_checklist": source_output_path(p9aw, "sufficiency_checklist"),
        "non_authorization_matrix": source_output_path(p9aw, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(p9aw, "control_boundary_readback"),
    }


def p9aw_ready_for_p9ax(
    p9aw: dict[str, Any],
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
    source = dict(p9aw.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    live_config = dict(source.get("live_config_dir") or {})
    owner = dict(p9aw.get("owner_decision") or {})
    review_owner = dict(review_packet.get("owner_decision") or {})
    checklist_checks = dict(checklist.get("checks") or {})
    summary_false = (
        "define_next_gate_scope_authorized",
        "next_gate_execution_authorized",
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
        "define_next_gate_scope_approved",
        "next_gate_execution_approved",
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
    forbidden_authorizations = (
        "define_next_gate_scope_in_p9aw",
        "next_gate_execution",
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
    return (
        p9aw.get("contract_version") == P9AW_CONTRACT
        and p9aw.get("status") == "ready"
        and not p9aw.get("blockers")
        and p9aw.get("gate_scope") == "p9aw_retained_p9av_evidence_review_only"
        and p9aw.get("p9aw_retained_evidence_review_ready") is True
        and p9aw.get("p9av_retained_evidence_sufficient") is True
        and p9aw.get("sufficient_for_next_gate_scope_discussion") is True
        and p9aw.get("eligible_for_future_next_gate_scope_definition_request") is True
        and p9aw.get("allowed_next_gate") == P9AX_GATE
        and p9aw.get("recommended_next_gate") == P9AX_GATE
        and p9aw.get("allowed_next_gate_must_be_separately_requested") is True
        and p9aw.get("retained_evidence_review_authorized") is True
        and p9aw.get("p9av_sufficiency_review_authorized") is True
        and p9aw.get("candidate_order_authority") == "disabled"
        and p9aw.get("execution_target_source") == "baseline_only"
        and p9aw.get("candidate_overlay_execution_path") == "shadow_only_not_executor"
        and p9aw.get("candidate_artifact_sink") == "proof_artifacts_only"
        and p9aw.get("executor_consumes_baseline_only") is True
        and p9aw.get("candidate_plan_referenced_by_executor") is False
        and all_false(p9aw, summary_false)
        and zero_orders_fills(p9aw)
        and no_live_mutation(p9aw)
        and owner_record.get("contract_version") == "hv_balanced_dth60_coinglass_phase9aw_owner_decision.v1"
        and owner_record.get("decision") == APPROVE_P9AW_DECISION
        and owner_record.get("retained_evidence_review_approved") is True
        and owner_record.get("p9av_sufficiency_review_approved") is True
        and all_false(owner_record, owner_false)
        and owner == owner_record
        and owner.get("decision") == APPROVE_P9AW_DECISION
        and review_packet.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9aw_owner_review_packet.v1"
        and review_packet.get("reviewed_only_retained_evidence") is True
        and review_packet.get("p9av_retained_evidence_sufficient") is True
        and review_packet.get("sufficient_for_next_gate_scope_discussion") is True
        and review_packet.get("allowed_next_gate_if_separately_requested") == P9AX_GATE
        and review_packet.get("define_next_gate_scope_in_p9aw_authorized") is False
        and review_packet.get("next_gate_execution_authorized") is False
        and review_packet.get("entered_timer_path") is False
        and review_packet.get("dry_load_readback_executed_in_p9aw") is False
        and review_packet.get("supervisor_run") is False
        and review_packet.get("remote_sync_performed") is False
        and review_packet.get("candidate_execution_performed") is False
        and review_packet.get("executor_input_mutated") is False
        and review_packet.get("target_plan_replaced") is False
        and review_packet.get("live_config_mutated") is False
        and review_packet.get("operator_state_mutated") is False
        and review_packet.get("timer_state_mutated") is False
        and zero_orders_fills(review_packet)
        and review_owner == owner_record
        and dict(review_packet.get("verdict") or {}).get("sufficient_for_p9ax_scope_discussion_only") is True
        and checklist.get("contract_version") == "hv_balanced_dth60_coinglass_phase9aw_sufficiency_checklist.v1"
        and checklist_checks
        and all(value is True for value in checklist_checks.values())
        and matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9aw_non_authorization_matrix.v1"
        and dict(matrix.get("authorizations") or {}).get("retained_evidence_review") is True
        and dict(matrix.get("authorizations") or {}).get("future_next_gate_scope_discussion_request") is True
        and all_authorizations_false(matrix, forbidden_authorizations)
        and control.get("contract_version") == "hv_balanced_dth60_coinglass_phase9aw_control_boundary_readback.v1"
        and control.get("live_supervisor_source_unchanged") is True
        and control.get("live_supervisor_loads_candidate_hook") is False
        and control.get("live_config_dir_unchanged") is True
        and control.get("define_next_gate_scope_authorized") is False
        and control.get("next_gate_execution_authorized") is False
        and control.get("dry_load_readback_executed") is False
        and control.get("entered_timer_path") is False
        and control.get("live_timer_path_loaded") is False
        and control.get("ran_supervisor") is False
        and control.get("remote_sync_performed") is False
        and control.get("remote_execution_performed") is False
        and control.get("candidate_execution_performed") is False
        and control.get("executor_input_mutated") is False
        and control.get("target_plan_replaced") is False
        and control.get("live_config_changed") is False
        and control.get("operator_state_changed") is False
        and control.get("timer_state_changed") is False
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


def build_owner_decision_record(args: argparse.Namespace, started_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9AX_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ax_owner_decision.v1",
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "recorded_at_utc": iso_z(started_at),
        "decision_question": "define_next_gate_scope_after_p9aw_only",
        "decision_effect": "define_concrete_next_gate_scope_under_proof_artifacts_only" if approved else "none",
        "define_next_gate_scope_approved": approved,
        "defined_next_gate": NEXT_GATE_ID if approved else "",
        "defined_next_gate_question": (
            "whether_to_allow_preparing_default_off_observe_only_live_supervisor_timer_path_shadow_readback_gate"
            if approved
            else ""
        ),
        "allow_prepare_shadow_readback_gate_approved_in_p9ax": False,
        "execute_defined_next_gate_approved": False,
        "prepare_shadow_readback_gate_approved": False,
        "prepare_proposal_package_approved": False,
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


def build_next_gate_scope_definition(
    *,
    run_id: str,
    owner_decision_record: dict[str, Any],
    source_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ax_next_gate_scope_definition.v1",
        "run_id": run_id,
        "source_evidence": source_evidence,
        "owner_decision": owner_decision_record,
        "scope_defined_for_question": (
            "whether_to_allow_preparing_default_off_observe_only_live_supervisor_timer_path_shadow_readback_gate"
        ),
        "defined_next_gate": NEXT_GATE_ID,
        "defined_next_gate_scope": NEXT_GATE_SCOPE,
        "defined_next_gate_question": (
            "whether to allow preparing a default-off/observe-only live-supervisor timer-path "
            "shadow readback gate"
        ),
        "defined_next_gate_effect_if_approved": (
            "authorize only preparation of a later gate/proposal package for shadow readback; "
            "still no dry-load execution, timer-path load, supervisor invocation, remote sync, "
            "executor mutation, target-plan replacement, or order authority"
        ),
        "defined_next_gate_effect_if_rejected": "stop before any gate/proposal preparation or execution work",
        "defined_next_gate_must_be_separately_requested": True,
        "defined_next_gate_executes_in_p9ax": False,
        "defined_next_gate_authorized_in_p9ax": False,
        "defined_next_gate_execution_authorized": False,
        "prepare_gate_authorized_in_p9ax": False,
        "proposal_body_write_authorized_in_p9ax": False,
        "dry_load_readback_execution_authorized_in_p9ax": False,
        "timer_path_shadow_readback_execution_authorized_in_p9ax": False,
        "defined_next_gate_allowed_actions": [
            "read retained P9AV/P9AW/P9AX proof artifacts and current source hashes",
            "decide whether a future gate/proposal package may be prepared",
            "write owner decision artifacts under proof_artifacts only",
        ],
        "defined_next_gate_required_inputs": [
            "retained P9AV default-off observe-only local proof_artifacts dry-load/readback proof",
            "retained P9AW sufficiency-only review after P9AV",
            "retained P9AX concrete scope definition",
            "current hook, live-supervisor, and live-config source hashes",
            "fresh account-read proof before any later remote or timer-path request",
        ],
        "required_boundaries": {
            "owner_gated": True,
            "proof_artifacts_only": True,
            "default_off_required": True,
            "observe_only_required": True,
            "no_order_required": True,
            "executor_input_must_remain_baseline_only": True,
            "candidate_shadow_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "target_plan_replacement_authorized": False,
            "executor_input_mutation_authorized": False,
            "live_order_submission_authorized": False,
            "candidate_order_authority": "disabled",
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
            "cancel_delta_must_equal": 0,
            "trade_delta_must_equal": 0,
            "dry_load_readback_execution_authorized": False,
            "timer_path_shadow_readback_execution_authorized": False,
            "timer_path_load_authorized": False,
            "supervisor_invocation_authorized": False,
            "production_timer_service_load_authorized": False,
            "live_config_mutation_authorized": False,
            "operator_state_mutation_authorized": False,
            "timer_or_service_mutation_authorized": False,
            "remote_sync_authorized": False,
            "real_timer_path_shadow_readback_requires_separate_gate": True,
            "account_read_proof_required_before_any_remote_or_timer_path": True,
        },
        "disallowed_actions_in_p9ax": {
            "execute_defined_next_gate": True,
            "prepare_shadow_readback_gate": True,
            "prepare_proposal_package": True,
            "write_proposal_body": True,
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
            "stage_governance_change": True,
            "submit_orders": True,
        },
        "future_follow_on_after_defined_gate": (
            "Only if P9AY is separately requested and approved may a later package preparation "
            "gate be opened. P9AY itself must still remain no-order and must not execute "
            "timer-path readback."
        ),
    }


def build_phase9ax(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9ax" / run_id

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9aw": latest_p9aw_summary(args),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
        "live_config_dir": resolve_path(args.live_config_dir),
    }
    project_profile = load_optional(paths["project_profile"])
    p9aw = load_optional(paths["phase9aw"])
    p9aw_paths = p9aw_output_paths(p9aw)
    owner_record = load_optional(p9aw_paths["owner_decision_record"])
    review_packet = load_optional(p9aw_paths["owner_review_packet"])
    checklist = load_optional(p9aw_paths["sufficiency_checklist"])
    matrix = load_optional(p9aw_paths["non_authorization_matrix"])
    control = load_optional(p9aw_paths["control_boundary_readback"])

    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_before = tree_sha256(paths["live_config_dir"])
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    owner_decision_record = build_owner_decision_record(args, started_at)
    p9aw_ok = p9aw_ready_for_p9ax(
        p9aw,
        owner_record,
        review_packet,
        checklist,
        matrix,
        control,
        p9aw_paths,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9aw_summary": evidence_file(paths["phase9aw"]),
        "phase9aw_owner_decision_record": evidence_file(p9aw_paths["owner_decision_record"]),
        "phase9aw_owner_review_packet": evidence_file(p9aw_paths["owner_review_packet"]),
        "phase9aw_sufficiency_checklist": evidence_file(p9aw_paths["sufficiency_checklist"]),
        "phase9aw_non_authorization_matrix": evidence_file(p9aw_paths["non_authorization_matrix"]),
        "phase9aw_control_boundary_readback": evidence_file(p9aw_paths["control_boundary_readback"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
        "live_config_dir": {
            "path": str(paths["live_config_dir"]),
            "exists": paths["live_config_dir"].exists(),
            "sha256": live_config_sha_before,
        },
    }
    next_gate_scope_definition = build_next_gate_scope_definition(
        run_id=run_id,
        owner_decision_record=owner_decision_record,
        source_evidence=source_evidence,
    )
    scope_acceptance_checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ax_scope_acceptance_checklist.v1",
        "run_id": run_id,
        "defined_next_gate": NEXT_GATE_ID,
        "scope_defined_for_question": next_gate_scope_definition["scope_defined_for_question"],
        "checklist": {
            "p9ax_defines_scope_only": True,
            "defined_gate_must_be_separately_requested": True,
            "defined_gate_is_owner_gated": True,
            "defined_gate_only_decides_whether_to_allow_preparing_gate": True,
            "defined_gate_cannot_prepare_gate_inside_p9ax": True,
            "defined_gate_cannot_write_proposal_body_inside_p9ax": True,
            "defined_gate_cannot_execute_dry_load_readback": True,
            "defined_gate_cannot_load_timer_path": True,
            "defined_gate_cannot_run_supervisor": True,
            "defined_gate_cannot_remote_sync": True,
            "defined_gate_cannot_mutate_executor_input": True,
            "defined_gate_cannot_replace_target_plan": True,
            "defined_gate_cannot_submit_orders": True,
            "defined_gate_must_keep_executor_baseline_only": True,
            "defined_gate_must_keep_order_authority_disabled": True,
            "future_remote_or_timer_path_requires_fresh_account_read": True,
        },
    }
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ax_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "define_next_gate_scope": str(args.owner_decision) == APPROVE_P9AX_DECISION,
            "allow_prepare_shadow_readback_gate_in_p9ax": False,
            "execute_defined_next_gate": False,
            "prepare_shadow_readback_gate": False,
            "prepare_proposal_package": False,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9ax_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "next_gate_scope_definition_only_after_p9aw",
        "live_supervisor": source_evidence["live_supervisor"],
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "defined_next_gate": NEXT_GATE_ID,
        "defined_next_gate_authorized_in_p9ax": False,
        "defined_next_gate_execution_authorized": False,
        "prepare_gate_authorized": False,
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
        "owner_decision_p9ax_define_scope_only": str(args.owner_decision) == APPROVE_P9AX_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage")
        == "stage_1_research_readiness_only",
        "p9aw_retained_evidence_review_ready": p9aw_ok,
        "p9aw_allows_p9ax_scope_definition": p9aw.get("eligible_for_future_next_gate_scope_definition_request")
        is True
        and p9aw.get("allowed_next_gate") == P9AX_GATE,
        "p9aw_required_separate_request": p9aw.get("allowed_next_gate_must_be_separately_requested") is True,
        "p9aw_did_not_define_next_scope": p9aw.get("define_next_gate_scope_authorized") is False,
        "p9aw_did_not_execute_next_gate": p9aw.get("next_gate_execution_authorized") is False,
        "p9aw_did_not_execute_dry_load_readback": p9aw.get("dry_load_readback_execution_authorized") is False,
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "current_hook_hash_matches_p9aw_source": dict(
            dict(p9aw.get("source_evidence") or {}).get("hook_module") or {}
        ).get("sha256")
        == hook_sha,
        "current_supervisor_hash_matches_p9aw_source": dict(
            dict(p9aw.get("source_evidence") or {}).get("live_supervisor") or {}
        ).get("sha256")
        == supervisor_sha_before,
        "current_live_config_hash_matches_p9aw_source": dict(
            dict(p9aw.get("source_evidence") or {}).get("live_config_dir") or {}
        ).get("sha256")
        == live_config_sha_before,
        "next_gate_scope_definition_output_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "next_gate_scope_definition.json"
        ),
        "scope_acceptance_checklist_output_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "scope_acceptance_checklist.json"
        ),
        "p9ax_defines_scope_only": True,
        "p9ax_does_not_authorize_defined_next_gate": True,
        "p9ax_does_not_prepare_gate": True,
        "p9ax_does_not_write_proposal_body": True,
        "p9ax_does_not_execute_dry_load_readback": True,
        "p9ax_does_not_enter_timer_path": True,
        "p9ax_does_not_run_supervisor": True,
        "p9ax_does_not_remote_sync": True,
        "p9ax_does_not_mutate_executor_input": True,
        "p9ax_does_not_replace_target_plan": True,
        "p9ax_does_not_mutate_live_config": True,
        "p9ax_does_not_mutate_operator_state": True,
        "p9ax_does_not_mutate_timer_state": True,
        "p9ax_requires_defined_gate_to_be_separately_requested": True,
        "defined_gate_only_decides_whether_to_allow_prepare_gate": True,
        "defined_gate_must_keep_executor_baseline_only": True,
        "defined_gate_must_keep_order_authority_disabled": True,
        "defined_gate_must_not_authorize_live_order_submission": True,
        "defined_gate_must_not_execute_dry_load_readback": True,
        "defined_gate_must_not_load_timer_path": True,
        "defined_gate_must_not_run_supervisor": True,
        "defined_gate_must_not_remote_sync": True,
        "zero_orders_fills_in_p9ax": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    ready = status == "ready"

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "next_gate_scope_definition": str(proof_root / "next_gate_scope_definition.json"),
        "scope_acceptance_checklist": str(proof_root / "scope_acceptance_checklist.json"),
        "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "p9ax_define_next_scope_after_p9aw.md"),
    }

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "gate_scope": "p9ax_define_next_gate_scope_after_p9aw_only",
        "owner_decision": owner_decision_record,
        "source_evidence": source_evidence,
        "p9ax_next_gate_scope_definition_ready": ready,
        "next_gate_scope_defined": ready,
        "scope_defined_for_question": next_gate_scope_definition["scope_defined_for_question"],
        "defined_next_gate": NEXT_GATE_ID if ready else "",
        "defined_next_gate_scope": NEXT_GATE_SCOPE if ready else "",
        "defined_next_gate_must_be_separately_requested": True,
        "defined_next_gate_authorized_in_p9ax": False,
        "defined_next_gate_execution_authorized": False,
        "eligible_for_future_p9ay_owner_gate_request": ready,
        "prepare_gate_authorized": False,
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
        "allowed_next_gate": NEXT_GATE_ID if ready else "",
        "recommended_next_gate": NEXT_GATE_ID if ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "proof_root": str(proof_root),
        "gates": gates,
        "blockers": blockers,
        "output_files": output_files,
    }

    write_json(root / "owner_decision_record.json", owner_decision_record)
    write_json(proof_root / "next_gate_scope_definition.json", next_gate_scope_definition)
    write_json(proof_root / "scope_acceptance_checklist.json", scope_acceptance_checklist)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix)
    write_json(proof_root / "control_boundary_readback.json", control_boundary_readback)
    write_json(root / "summary.json", summary)
    (root / "p9ax_define_next_scope_after_p9aw.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9AX Define Next Scope After P9AW",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Defined Scope",
        "",
        "```text",
        f"scope_defined_for_question = {summary['scope_defined_for_question']}",
        f"defined_next_gate = {summary['defined_next_gate']}",
        f"defined_next_gate_scope = {summary['defined_next_gate_scope']}",
        f"next_gate_scope_defined = {str(bool(summary['next_gate_scope_defined'])).lower()}",
        "defined_next_gate_authorized_in_p9ax = false",
        "defined_next_gate_execution_authorized = false",
        "prepare_gate_authorized = false",
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
    summary, exit_code = build_phase9ax(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    print(f"next_gate_scope_definition={summary['output_files']['next_gate_scope_definition']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
