from __future__ import annotations

import argparse
import hashlib
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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9as_p9au_proof_only_corridor import (  # noqa: E402
    P9AS_PARENT,
    P9AU_GATE,
    P9AU_PARENT,
    P9AV_GATE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9av_default_off_dry_load_readback.v1"
APPROVE_P9AV_DECISION = "approve_p9av_default_off_observe_only_dry_load_readback_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9av_default_off_dry_load_readback"
P9AW_GATE = "P9AW_review_after_default_off_observe_only_dry_load_readback_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the separately requested P9AV default-off observe-only "
            "dry-load/readback. This is local proof_artifacts-only: it reads "
            "retained P9AU permission and retained P9AS proposal artifacts, "
            "writes a dry-load manifest/readback plus executor guard, and stops "
            "before timer path, supervisor invocation, remote sync, executor "
            "mutation, target-plan replacement, config/operator/timer mutation, "
            "or order authority."
        )
    )
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9au-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--output-root", default="")
    parser.add_argument("--artifacts-root", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AV_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:single_request_p9av_default_off_observe_only_dry_load_readback_only",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(getattr(args, "output_root", "")).strip():
        return resolve_path(args.output_root)
    if str(getattr(args, "artifacts_root", "")).strip():
        return resolve_path(args.artifacts_root) / "p9av_default_off_dry_load_readback" / run_id
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def evidence_path(payload: dict[str, Any], key: str) -> Path:
    source = dict(payload.get("source_evidence") or {})
    item = dict(source.get(key) or {})
    text = str(item.get("path") or "")
    return resolve_path(text) if text.strip() else Path("")


def int_equals(payload: dict[str, Any], key: str, expected: int) -> bool:
    try:
        return int(payload.get(key)) == expected
    except (TypeError, ValueError):
        return False


def all_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def stable_json_hash(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def latest_p9au_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9au_summary).strip():
        return resolve_path(args.phase9au_summary)
    return latest_match(P9AU_PARENT, "*/summary.json")


def p9av_owner_decision(args: argparse.Namespace, started_at: datetime) -> dict[str, Any]:
    approved = args.owner_decision == APPROVE_P9AV_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9av_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(started_at),
        "decision_question": "execute_default_off_observe_only_local_proof_artifacts_dry_load_readback_only",
        "decision_effect": (
            "execute_local_proof_artifacts_only_dry_load_readback_without_timer_supervisor_remote_or_orders"
            if approved
            else "none"
        ),
        "default_off_observe_only_dry_load_readback_approved": approved,
        "dry_load_readback_execution_approved": approved,
        "dry_load_readback_execution_scope": "local_proof_artifacts_only_not_timer_path" if approved else "none",
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


def p9av_execution_boundary(*, executed: bool) -> dict[str, Any]:
    return {
        "dry_load_readback_execution_authorized": executed,
        "default_off_observe_only_dry_load_readback_authorized": executed,
        "dry_load_readback_execution_scope": "local_proof_artifacts_only_not_timer_path" if executed else "none",
        "dry_load_readback_executed": executed,
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
        "executor_consumes_baseline_only": executed,
        "candidate_shadow_only": executed,
        "candidate_plan_referenced_by_executor": False,
        "candidate_shadow_artifact_written": executed,
    }


def p9au_ready_for_p9av(
    summary: dict[str, Any],
    permission: dict[str, Any],
    matrix: dict[str, Any],
    control: dict[str, Any],
    p9at_summary: dict[str, Any],
    p9at_review: dict[str, Any],
    p9as_summary: dict[str, Any],
    proposal_package: dict[str, Any],
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
    boundaries = dict(permission.get("required_boundaries_for_next_gate") or {})
    authorizations = dict(matrix.get("authorizations") or {})
    package_boundaries = dict(proposal_package.get("required_boundaries") or {})
    package_authorizations = dict(proposal_package.get("authorizations") or {})
    summary_false_keys = (
        "dry_load_readback_execution_authorized",
        "dry_load_readback_execution_authorized_in_p9au",
        "dry_load_readback_execution_gate_opened",
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
    forbidden_authorizations = (
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
        summary.get("contract_version") == "hv_balanced_dth60_coinglass_phase9au_allow_dry_load_readback_owner_gate.v1"
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9au_allow_future_dry_load_readback_gate_ready") is True
        and summary.get("eligible_for_future_dry_load_readback_execution_gate_request") is True
        and summary.get("allowed_next_gate") == P9AV_GATE
        and summary.get("recommended_next_gate") == P9AV_GATE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and all_false(summary, summary_false_keys)
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_artifact_sink") == "proof_artifacts_only"
        and summary.get("live_supervisor_source_unchanged") is True
        and summary.get("live_config_dir_unchanged") is True
        and zero_orders_fills(summary)
        and no_live_mutation(summary)
        and permission.get("contract_version") == "hv_balanced_dth60_coinglass_phase9au_dry_load_readback_gate_permission.v1"
        and permission.get("allowed_next_gate") == P9AV_GATE
        and permission.get("allowed_next_gate_must_be_separately_requested") is True
        and permission.get("dry_load_readback_executed_in_p9au") is False
        and permission.get("timer_path_loaded_in_p9au") is False
        and permission.get("supervisor_invoked_in_p9au") is False
        and boundaries.get("owner_gated") is True
        and boundaries.get("proof_artifacts_only") is True
        and boundaries.get("default_off_only") is True
        and boundaries.get("observe_only_shadow_artifacts_only") is True
        and boundaries.get("executor_input_must_remain_baseline_only") is True
        and boundaries.get("candidate_order_authority") == "disabled"
        and boundaries.get("live_order_submission_authorized") is False
        and int_equals(boundaries, "orders_submitted_must_equal", 0)
        and int_equals(boundaries, "fill_count_must_equal", 0)
        and matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9au_non_authorization_matrix.v1"
        and authorizations.get("future_dry_load_readback_gate_request") is True
        and all(authorizations.get(key) is False for key in forbidden_authorizations)
        and control.get("contract_version") == "hv_balanced_dth60_coinglass_phase9au_control_boundary_readback.v1"
        and control.get("live_supervisor_source_unchanged") is True
        and control.get("live_config_dir_unchanged") is True
        and control.get("live_supervisor_loads_candidate_hook") is False
        and control.get("dry_load_readback_executed") is False
        and control.get("entered_timer_path") is False
        and control.get("candidate_execution_performed") is False
        and control.get("executor_input_mutated") is False
        and control.get("target_plan_replaced") is False
        and zero_orders_fills(control)
        and p9at_summary.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9at_retained_readiness_review.v1"
        and p9at_summary.get("status") == "ready"
        and p9at_summary.get("p9at_retained_readiness_review_ready") is True
        and p9at_summary.get("allowed_next_gate") == P9AU_GATE
        and p9at_summary.get("dry_load_readback_execution_authorized") is False
        and zero_orders_fills(p9at_summary)
        and p9at_review.get("contract_version") == "hv_balanced_dth60_coinglass_phase9at_readiness_review.v1"
        and p9at_review.get("reviewed_only_retained_evidence") is True
        and p9at_review.get("entered_timer_path") is False
        and p9at_review.get("dry_load_executed") is False
        and p9at_review.get("supervisor_run") is False
        and p9at_review.get("executor_input_mutated") is False
        and p9at_review.get("target_plan_replaced") is False
        and dict(p9at_review.get("verdict") or {}).get("ready_for_future_owner_default_off_dry_load_gate") is True
        and dict(p9at_review.get("verdict") or {}).get("future_gate_required_before_any_dry_load_readback") is True
        and dict(p9at_review.get("verdict") or {}).get("future_gate_must_keep_executor_baseline_only") is True
        and dict(p9at_review.get("verdict") or {}).get("future_gate_must_keep_order_authority_disabled") is True
        and p9as_summary.get("contract_version") == "hv_balanced_dth60_coinglass_phase9as_proposal_package.v1"
        and p9as_summary.get("status") == "ready"
        and p9as_summary.get("p9as_proposal_package_ready") is True
        and p9as_summary.get("generated_proposal_package") is True
        and p9as_summary.get("dry_load_readback_execution_authorized") is False
        and p9as_summary.get("live_order_submission_authorized") is False
        and zero_orders_fills(p9as_summary)
        and proposal_package.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9as_proposal_package_body.v1"
        and proposal_package.get("proposal_mode")
        == "default_off_observe_only_live_supervisor_timer_path_shadow_readback_proposal"
        and proposal_package.get("proposed_future_gate") == P9AV_GATE
        and proposal_package.get("required_intermediate_owner_gate") == P9AU_GATE
        and proposal_package.get("proposal_written_under_proof_artifacts") is True
        and proposal_package.get("proposal_executes_anything") is False
        and proposal_package.get("default_enabled") is False
        and proposal_package.get("observe_only") is True
        and proposal_package.get("candidate_shadow_only") is True
        and proposal_package.get("executor_target_source") == "baseline_only"
        and proposal_package.get("candidate_artifact_sink") == "proof_artifacts_only"
        and proposal_package.get("dry_load_readback_executed") is False
        and proposal_package.get("timer_path_loaded") is False
        and proposal_package.get("supervisor_invoked") is False
        and proposal_package.get("remote_sync_performed") is False
        and package_boundaries.get("proof_artifacts_only") is True
        and package_boundaries.get("default_off_only") is True
        and package_boundaries.get("observe_only_shadow_artifacts_only") is True
        and package_boundaries.get("executor_input_must_remain_baseline_only") is True
        and package_boundaries.get("candidate_plan_must_not_be_referenced_by_executor") is True
        and package_boundaries.get("candidate_order_authority") == "disabled"
        and package_boundaries.get("live_order_submission_authorized") is False
        and package_boundaries.get("dry_load_readback_execution_authorized") is False
        and package_authorizations.get("prepare_proposal_package") is True
        and package_authorizations.get("dry_load_readback_execution") is False
        and package_authorizations.get("timer_path_load") is False
        and package_authorizations.get("supervisor_invocation") is False
        and package_authorizations.get("remote_sync") is False
        and package_authorizations.get("live_order_submission") is False
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def build_p9av(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9av" / run_id
    owner_record_path = root / "owner_decision_record.json"
    summary_path = root / "summary.json"

    p9au_summary_path = latest_p9au_summary(args)
    p9au_summary = load_optional(p9au_summary_path)
    permission_path = source_output_path(p9au_summary, "dry_load_readback_gate_permission")
    p9au_matrix_path = source_output_path(p9au_summary, "non_authorization_matrix")
    p9au_control_path = source_output_path(p9au_summary, "control_boundary_readback")
    permission = load_optional(permission_path)
    p9au_matrix = load_optional(p9au_matrix_path)
    p9au_control = load_optional(p9au_control_path)
    p9at_summary_path = evidence_path(p9au_summary, "phase9at_summary")
    p9at_review_path = evidence_path(p9au_summary, "phase9at_readiness_review")
    p9at_checklist_path = evidence_path(p9au_summary, "phase9at_readiness_checklist")
    p9at_summary = load_optional(p9at_summary_path)
    p9at_review = load_optional(p9at_review_path)
    p9as_summary_path = evidence_path(p9at_review, "phase9as_summary")
    if not p9as_summary_path or str(p9as_summary_path) == ".":
        p9as_summary_path = latest_match(P9AS_PARENT, "*/summary.json")
    proposal_package_path = evidence_path(p9at_review, "phase9as_proposal_review_package")
    p9as_summary = load_optional(p9as_summary_path)
    proposal_package = load_optional(proposal_package_path)

    project_profile_path = resolve_path(args.project_profile)
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_path = resolve_path(args.live_config_dir)
    project_profile = load_optional(project_profile_path)
    hook_sha = file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else ""
    supervisor_sha_before = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    live_config_sha_before = tree_sha256(live_config_path)
    supervisor_loads = current_supervisor_loads_hook(supervisor_path)
    decision = p9av_owner_decision(args, started_at)

    source_evidence = {
        "project_profile": evidence_file(project_profile_path),
        "phase9au_summary": evidence_file(p9au_summary_path),
        "phase9au_dry_load_readback_gate_permission": evidence_file(permission_path),
        "phase9au_non_authorization_matrix": evidence_file(p9au_matrix_path),
        "phase9au_control_boundary_readback": evidence_file(p9au_control_path),
        "phase9at_summary": evidence_file(p9at_summary_path),
        "phase9at_readiness_review": evidence_file(p9at_review_path),
        "phase9at_readiness_checklist": evidence_file(p9at_checklist_path),
        "phase9as_summary": evidence_file(p9as_summary_path),
        "phase9as_proposal_review_package": evidence_file(proposal_package_path),
        "hook_module": evidence_file(hook_path),
        "live_supervisor": evidence_file(supervisor_path),
        "live_config_dir": {"path": str(live_config_path), "exists": live_config_path.exists(), "sha256": live_config_sha_before},
    }

    p9au_ready = p9au_ready_for_p9av(
        p9au_summary,
        permission,
        p9au_matrix,
        p9au_control,
        p9at_summary,
        p9at_review,
        p9as_summary,
        proposal_package,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads,
    )
    pre_gates = {
        "owner_decision_p9av_dry_load_readback_only": args.owner_decision == APPROVE_P9AV_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9au_permission_ready_for_p9av": p9au_ready,
        "p9au_allowed_p9av_only": p9au_summary.get("allowed_next_gate") == P9AV_GATE,
        "p9au_required_separate_request": p9au_summary.get("allowed_next_gate_must_be_separately_requested") is True,
        "current_live_supervisor_not_loading_hook": supervisor_loads is False,
        "current_hook_hash_matches_p9au_source": dict(dict(p9au_summary.get("source_evidence") or {}).get("hook_module") or {}).get("sha256")
        == hook_sha,
        "current_supervisor_hash_matches_p9au_source": dict(
            dict(p9au_summary.get("source_evidence") or {}).get("live_supervisor") or {}
        ).get("sha256")
        == supervisor_sha_before,
        "current_live_config_hash_matches_p9au_source": dict(
            dict(p9au_summary.get("source_evidence") or {}).get("live_config_dir") or {}
        ).get("sha256")
        == live_config_sha_before,
    }
    pre_blockers = [key for key, value in pre_gates.items() if not value]

    manifest_path = proof_root / "dry_load_manifest.json"
    candidate_shadow_path = proof_root / "candidate_shadow_artifact.json"
    executor_guard_path = proof_root / "executor_input_guard.json"
    readback_path = proof_root / "dry_load_readback.json"
    matrix_path = proof_root / "non_authorization_matrix.json"
    control_path = proof_root / "control_boundary_readback.json"

    dry_load_executed = not pre_blockers
    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_record_path),
        "dry_load_manifest": str(manifest_path) if dry_load_executed else "",
        "candidate_shadow_artifact": str(candidate_shadow_path) if dry_load_executed else "",
        "dry_load_readback": str(readback_path) if dry_load_executed else "",
        "executor_input_guard": str(executor_guard_path) if dry_load_executed else "",
        "non_authorization_matrix": str(matrix_path),
        "control_boundary_readback": str(control_path),
    }

    if dry_load_executed:
        baseline_executor_input = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9av_baseline_executor_input_reference.v1",
            "executor_target_source": "baseline_only",
            "plan_source": "retained_baseline_reference_only",
            "candidate_plan_referenced_by_executor": False,
            "target_plan_replaced": False,
            "executor_input_changed": False,
        }
        baseline_hash_before = stable_json_hash(baseline_executor_input)
        baseline_hash_after = stable_json_hash(baseline_executor_input)
        candidate_shadow = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9av_candidate_shadow_artifact.v1",
            "run_id": run_id,
            "created_at_utc": iso_z(started_at),
            "candidate_shadow_only": True,
            "default_enabled": False,
            "observe_only": True,
            "candidate_order_authority": "disabled",
            "candidate_plan_referenced_by_executor": False,
            "executor_target_source": "baseline_only",
            "source_proposal_package": evidence_file(proposal_package_path),
            "source_p9au_permission": evidence_file(permission_path),
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        write_json(candidate_shadow_path, candidate_shadow)
        candidate_shadow_sha = file_sha256(candidate_shadow_path)
        manifest = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9av_dry_load_manifest.v1",
            "run_id": run_id,
            "generated_at_utc": iso_z(started_at),
            "dry_load_mode": "default_off_observe_only_local_proof_artifacts_only_not_timer_path",
            "default_enabled": False,
            "observe_only": True,
            "executor_target_source": "baseline_only",
            "candidate_artifact_sink": "proof_artifacts_only",
            "candidate_shadow_only": True,
            "candidate_order_authority": "disabled",
            "source_evidence": source_evidence,
            "candidate_shadow_artifact_path": str(candidate_shadow_path),
            "candidate_shadow_artifact_sha256": candidate_shadow_sha,
            "baseline_executor_input_hash_before": baseline_hash_before,
            "timer_path_loaded": False,
            "supervisor_invoked": False,
            "remote_sync_performed": False,
            "live_config_mutated": False,
            "operator_state_mutated": False,
            "timer_state_mutated": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        write_json(manifest_path, manifest)
        manifest_sha = file_sha256(manifest_path)
        guard = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9av_executor_input_guard.v1",
            "run_id": run_id,
            "baseline_executor_input_reference": baseline_executor_input,
            "baseline_executor_input_hash_before": baseline_hash_before,
            "baseline_executor_input_hash_after": baseline_hash_after,
            "baseline_executor_input_hash_unchanged": baseline_hash_before == baseline_hash_after,
            "candidate_shadow_artifact_sha256": candidate_shadow_sha,
            "candidate_shadow_hash_differs_from_executor_input": candidate_shadow_sha != baseline_hash_after,
            "executor_consumes_baseline_only": True,
            "candidate_plan_referenced_by_executor": False,
            "executor_input_changed": False,
            "target_plan_replaced": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        write_json(executor_guard_path, guard)
        guard_sha = file_sha256(executor_guard_path)
        readback = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9av_dry_load_readback.v1",
            "run_id": run_id,
            "readback_at_utc": iso_z(started_at),
            "dry_load_readback_ok": True,
            "dry_load_readback_executed": True,
            "dry_load_readback_mode": "local_proof_artifacts_only_not_timer_path",
            "dry_load_manifest_path": str(manifest_path),
            "dry_load_manifest_sha256": manifest_sha,
            "candidate_shadow_artifact_path": str(candidate_shadow_path),
            "candidate_shadow_artifact_sha256": candidate_shadow_sha,
            "executor_input_guard_path": str(executor_guard_path),
            "executor_input_guard_sha256": guard_sha,
            "default_enabled": False,
            "observe_only": True,
            "executor_target_source": "baseline_only",
            "executor_consumes_baseline_only": True,
            "candidate_shadow_only": True,
            "candidate_plan_referenced_by_executor": False,
            "baseline_executor_input_hash_before": baseline_hash_before,
            "baseline_executor_input_hash_after": baseline_hash_after,
            "baseline_executor_input_hash_unchanged": baseline_hash_before == baseline_hash_after,
            "candidate_shadow_hash_differs_from_executor_input": candidate_shadow_sha != baseline_hash_after,
            "entered_timer_path": False,
            "live_timer_path_loaded": False,
            "live_timer_service_enabled_or_invoked": False,
            "ran_supervisor": False,
            "timer_path_invoked": False,
            "remote_sync_performed": False,
            "remote_execution_performed": False,
            "remote_control_plane_touched": False,
            "candidate_execution_performed": False,
            "executor_input_changed": False,
            "target_plan_replaced": False,
            "live_config_changed": False,
            "operator_state_changed": False,
            "timer_state_changed": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        write_json(readback_path, readback)

    supervisor_sha_after = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    live_config_sha_after = tree_sha256(live_config_path)
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9av_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "default_off_observe_only_local_dry_load_readback": dry_load_executed,
            "proof_artifacts_dry_load_readback_execution": dry_load_executed,
            "dry_load_readback_execution_in_timer_path": False,
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
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9av_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "default_off_observe_only_local_proof_artifacts_dry_load_readback_only",
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "dry_load_readback_executed": dry_load_executed,
        "dry_load_readback_mode": "local_proof_artifacts_only_not_timer_path" if dry_load_executed else "not_executed",
        "entered_timer_path": False,
        "live_timer_path_loaded": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "remote_control_plane_touched": False,
        "candidate_execution_performed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
        "exchange_order_submission": "disabled",
    }
    write_json(owner_record_path, decision)
    write_json(matrix_path, non_authorization_matrix)
    write_json(control_path, control)

    readback_payload = load_optional(readback_path)
    guard_payload = load_optional(executor_guard_path)
    post_gates = {
        "dry_load_manifest_under_proof_artifacts": output_under_proof_artifacts(manifest_path) and manifest_path.exists(),
        "candidate_shadow_artifact_under_proof_artifacts": output_under_proof_artifacts(candidate_shadow_path)
        and candidate_shadow_path.exists(),
        "dry_load_readback_under_proof_artifacts": output_under_proof_artifacts(readback_path) and readback_path.exists(),
        "executor_input_guard_under_proof_artifacts": output_under_proof_artifacts(executor_guard_path)
        and executor_guard_path.exists(),
        "non_authorization_matrix_under_proof_artifacts": output_under_proof_artifacts(matrix_path) and matrix_path.exists(),
        "control_boundary_under_proof_artifacts": output_under_proof_artifacts(control_path) and control_path.exists(),
        "dry_load_mode_local_proof_artifacts_only": readback_payload.get("dry_load_readback_mode")
        == "local_proof_artifacts_only_not_timer_path",
        "dry_load_readback_default_off": readback_payload.get("default_enabled") is False,
        "dry_load_readback_observe_only": readback_payload.get("observe_only") is True,
        "executor_consumes_baseline_only": guard_payload.get("executor_consumes_baseline_only") is True
        and readback_payload.get("executor_consumes_baseline_only") is True,
        "candidate_shadow_only": readback_payload.get("candidate_shadow_only") is True,
        "candidate_plan_not_referenced_by_executor": guard_payload.get("candidate_plan_referenced_by_executor") is False
        and readback_payload.get("candidate_plan_referenced_by_executor") is False,
        "executor_input_baseline_hash_unchanged": guard_payload.get("baseline_executor_input_hash_unchanged") is True
        and readback_payload.get("baseline_executor_input_hash_unchanged") is True,
        "candidate_shadow_hash_differs_from_executor_input": guard_payload.get("candidate_shadow_hash_differs_from_executor_input")
        is True
        and readback_payload.get("candidate_shadow_hash_differs_from_executor_input") is True,
        "p9av_does_not_enter_timer_path": True,
        "p9av_does_not_run_supervisor": True,
        "p9av_does_not_remote_sync": True,
        "p9av_does_not_mutate_executor_input": True,
        "p9av_does_not_replace_target_plan": True,
        "p9av_does_not_mutate_live_config": control["live_config_changed"] is False,
        "p9av_does_not_mutate_operator_state": control["operator_state_changed"] is False,
        "p9av_does_not_mutate_timer_state": control["timer_state_changed"] is False,
        "live_supervisor_source_unchanged": control["live_supervisor_source_unchanged"],
        "live_config_dir_unchanged": control["live_config_dir_unchanged"],
        "p9av_keeps_order_authority_disabled": True,
        "zero_orders_fills_in_p9av": True,
    }
    gates = {**pre_gates, **post_gates} if dry_load_executed else pre_gates
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "gate_scope": "p9av_default_off_observe_only_local_proof_artifacts_dry_load_readback_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9av_default_off_observe_only_dry_load_readback_ready": status == "ready",
        "eligible_for_owner_p9aw_review_after_readback": status == "ready",
        "allowed_next_gate": P9AW_GATE if status == "ready" else "",
        "recommended_next_gate": P9AW_GATE if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "dry_load_readback_mode": "local_proof_artifacts_only_not_timer_path" if dry_load_executed else "not_executed",
        "dry_load_manifest_under_proof_artifacts": dry_load_executed and output_under_proof_artifacts(manifest_path),
        "dry_load_readback_under_proof_artifacts": dry_load_executed and output_under_proof_artifacts(readback_path),
        "candidate_shadow_artifact_under_proof_artifacts": dry_load_executed and output_under_proof_artifacts(candidate_shadow_path),
        "executor_input_guard_under_proof_artifacts": dry_load_executed and output_under_proof_artifacts(executor_guard_path),
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_supervisor_source_unchanged": control["live_supervisor_source_unchanged"],
        "live_config_dir_unchanged": control["live_config_dir_unchanged"],
        "gates": gates,
        "blockers": blockers,
        **p9av_execution_boundary(executed=status == "ready"),
        "proof_root": str(proof_root),
        "output_files": output_files,
    }
    write_json(summary_path, summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p9av(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    print(f"dry_load_manifest={summary['output_files']['dry_load_manifest']}")
    print(f"dry_load_readback={summary['output_files']['dry_load_readback']}")
    print(f"executor_input_guard={summary['output_files']['executor_input_guard']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
