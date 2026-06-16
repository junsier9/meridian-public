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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bh_p9bj_timer_path_shadow_readback_corridor import (  # noqa: E402
    CONTRACT_VERSION as P9BH_P9BJ_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9BH_P9BJ_PARENT,
    LOCAL_TIMER_READBACK_SCOPE,
    P9BJ_GATE,
    P9BK_GATE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9bk_review_after_p9bh_p9bj.v1"
APPROVE_P9BK_DECISION = "approve_p9bk_review_p9bh_p9bj_retained_evidence_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9bk_review_after_p9bh_p9bj"
P9BL_GATE = "P9BL_owner_gate_define_next_gate_scope_after_p9bk_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9BK as a retained-evidence review only. P9BK reads the retained "
            "P9BH-P9BJ no-order timer-path shadow readback and decides whether it is "
            "sufficient for a separately requested next owner gate. It does not define "
            "the next scope, execute another readback, enter timer path, invoke the "
            "supervisor, remote sync, execute the candidate, mutate live state or "
            "executor input, replace target plans, or authorize live orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9bh-p9bj-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BK_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9bk_review_p9bh_p9bj_retained_evidence_only",
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


def latest_p9bh_p9bj_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bh_p9bj_summary).strip():
        return resolve_path(args.phase9bh_p9bj_summary)
    return latest_match(P9BH_P9BJ_PARENT, "*/summary.json")


def all_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def p9bh_p9bj_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    return {
        "owner_decision_record": source_output_path(summary, "owner_decision_record"),
        "p9bh_summary": source_output_path(summary, "p9bh_summary"),
        "p9bi_summary": source_output_path(summary, "p9bi_summary"),
        "p9bj_summary": source_output_path(summary, "p9bj_summary"),
    }


def p9bi_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    return {
        "timer_path_shadow_readback_execution_package": source_output_path(
            summary, "timer_path_shadow_readback_execution_package"
        ),
        "timer_path_shadow_readback_manifest": source_output_path(
            summary, "timer_path_shadow_readback_manifest"
        ),
        "candidate_shadow_artifact": source_output_path(summary, "candidate_shadow_artifact"),
        "executor_input_guard": source_output_path(summary, "executor_input_guard"),
        "timer_path_shadow_readback": source_output_path(summary, "timer_path_shadow_readback"),
        "non_authorization_matrix": source_output_path(summary, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(summary, "control_boundary_readback"),
    }


def p9bj_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    return {
        "readiness_review": source_output_path(summary, "readiness_review"),
        "readiness_checklist": source_output_path(summary, "readiness_checklist"),
        "non_authorization_matrix": source_output_path(summary, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(summary, "control_boundary_readback"),
    }


def p9bh_p9bj_retained_evidence_sufficient(
    corridor: dict[str, Any],
    owner_record: dict[str, Any],
    p9bi_summary: dict[str, Any],
    p9bj_summary: dict[str, Any],
    p9bi_package: dict[str, Any],
    p9bi_readback: dict[str, Any],
    p9bi_guard: dict[str, Any],
    p9bj_review: dict[str, Any],
    corridor_paths: dict[str, Path],
    p9bi_paths: dict[str, Path],
    p9bj_paths: dict[str, Path],
    *,
    current_hook_sha256: str,
    current_supervisor_sha256: str,
    current_live_config_sha256: str,
    current_supervisor_loads_candidate_hook: bool,
) -> bool:
    source = dict(corridor.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    live_config = dict(source.get("live_config_dir") or {})
    false_keys = (
        "live_timer_path_loaded",
        "live_timer_service_enabled_or_invoked",
        "ran_supervisor",
        "timer_path_invoked",
        "remote_execution_performed",
        "remote_control_plane_touched",
        "candidate_execution_authorized",
        "candidate_execution_performed",
        "candidate_live_order_submission_authorized",
        "live_order_submission_authorized",
        "executor_input_changed",
        "target_plan_replaced",
        "live_config_changed",
        "operator_state_changed",
        "timer_state_changed",
        "wrote_live_hook_config",
        "implemented_hook",
        "deployed_hook",
        "loaded_hook",
    )
    return (
        corridor.get("contract_version") == P9BH_P9BJ_CONTRACT
        and corridor.get("status") == "ready"
        and not corridor.get("blockers")
        and list(corridor.get("completed_gates") or []) == ["P9BH", "P9BI", "P9BJ"]
        and corridor.get("p9bh_p9bj_corridor_ready") is True
        and corridor.get("p9bh_owner_gate_ready") is True
        and corridor.get("p9bi_timer_path_shadow_readback_ready") is True
        and corridor.get("p9bj_retained_readiness_review_ready") is True
        and corridor.get("timer_path_shadow_readback_executed") is True
        and corridor.get("timer_path_shadow_readback_scope") == LOCAL_TIMER_READBACK_SCOPE
        and corridor.get("eligible_for_future_p9bk_owner_gate_request") is True
        and corridor.get("allowed_next_gate") == P9BK_GATE
        and corridor.get("allowed_next_gate_must_be_separately_requested") is True
        and all_false(corridor, false_keys)
        and corridor.get("candidate_order_authority") == "disabled"
        and corridor.get("execution_target_source") == "baseline_only"
        and corridor.get("candidate_artifact_sink") == "proof_artifacts_only"
        and corridor.get("executor_consumes_baseline_only") is True
        and corridor.get("candidate_shadow_only") is True
        and corridor.get("candidate_plan_referenced_by_executor") is False
        and no_live_mutation(corridor)
        and zero_orders_fills(corridor)
        and owner_record.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bh_p9bj_owner_decision.v1"
        and owner_record.get("decision")
        == "approve_p9bh_p9bj_default_off_observe_only_timer_path_shadow_readback_corridor_only"
        and owner_record.get("p9bh_owner_gate_approved") is True
        and owner_record.get("p9bi_timer_path_shadow_readback_execution_approved") is True
        and owner_record.get("p9bj_retained_readiness_review_approved") is True
        and owner_record.get("live_order_submission_approved") is False
        and owner_record.get("candidate_execution_approved") is False
        and p9bi_summary.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bi_timer_path_shadow_readback.v1"
        and p9bi_summary.get("status") == "ready"
        and not p9bi_summary.get("blockers")
        and p9bi_summary.get("p9bi_timer_path_shadow_readback_ready") is True
        and p9bi_summary.get("timer_path_shadow_readback_executed") is True
        and p9bi_summary.get("timer_path_shadow_readback_scope") == LOCAL_TIMER_READBACK_SCOPE
        and p9bi_summary.get("timer_path_shadow_readback_mode") == LOCAL_TIMER_READBACK_SCOPE
        and p9bi_summary.get("allowed_next_gate") == P9BJ_GATE
        and p9bi_summary.get("candidate_execution_performed") is False
        and p9bi_summary.get("live_order_submission_authorized") is False
        and zero_orders_fills(p9bi_summary)
        and p9bi_package.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bi_timer_path_shadow_readback_execution_package.v1"
        and p9bi_package.get("package_written_under_proof_artifacts") is True
        and p9bi_package.get("execution_scope") == LOCAL_TIMER_READBACK_SCOPE
        and p9bi_package.get("default_enabled") is False
        and p9bi_package.get("observe_only") is True
        and p9bi_package.get("candidate_order_authority") == "disabled"
        and p9bi_package.get("executor_target_source") == "baseline_only"
        and p9bi_package.get("candidate_shadow_only") is True
        and p9bi_package.get("candidate_plan_must_not_be_referenced_by_executor") is True
        and p9bi_package.get("live_order_submission_authorized") is False
        and p9bi_package.get("candidate_execution_authorized") is False
        and p9bi_package.get("timer_path_shadow_readback_executed") is True
        and p9bi_package.get("live_timer_path_loaded") is False
        and p9bi_package.get("supervisor_invoked") is False
        and p9bi_package.get("remote_sync_performed") is False
        and int(p9bi_package.get("orders_submitted") or 0) == 0
        and int(p9bi_package.get("fill_count") or 0) == 0
        and p9bi_readback.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bi_timer_path_shadow_readback.v1"
        and p9bi_readback.get("timer_path_shadow_readback_ok") is True
        and p9bi_readback.get("timer_path_shadow_readback_executed") is True
        and p9bi_readback.get("timer_path_shadow_readback_mode") == LOCAL_TIMER_READBACK_SCOPE
        and p9bi_readback.get("default_enabled") is False
        and p9bi_readback.get("observe_only") is True
        and p9bi_readback.get("executor_consumes_baseline_only") is True
        and p9bi_readback.get("candidate_shadow_only") is True
        and p9bi_readback.get("candidate_execution_performed") is False
        and p9bi_readback.get("candidate_plan_referenced_by_executor") is False
        and p9bi_readback.get("baseline_executor_input_hash_unchanged") is True
        and p9bi_readback.get("live_timer_path_loaded") is False
        and p9bi_readback.get("ran_supervisor") is False
        and p9bi_readback.get("remote_execution_performed") is False
        and p9bi_readback.get("executor_input_changed") is False
        and p9bi_readback.get("target_plan_replaced") is False
        and p9bi_readback.get("applied_to_live") in (False, None)
        and p9bi_readback.get("live_config_changed") is False
        and p9bi_readback.get("operator_state_changed") is False
        and p9bi_readback.get("timer_state_changed") is False
        and zero_orders_fills(p9bi_readback)
        and p9bi_guard.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bi_executor_input_guard.v1"
        and p9bi_guard.get("baseline_executor_input_hash_unchanged") is True
        and p9bi_guard.get("executor_consumes_baseline_only") is True
        and p9bi_guard.get("candidate_plan_referenced_by_executor") is False
        and p9bi_guard.get("executor_input_changed") is False
        and p9bi_guard.get("target_plan_replaced") is False
        and zero_orders_fills(p9bi_guard)
        and p9bj_summary.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bj_retained_readiness_review.v1"
        and p9bj_summary.get("status") == "ready"
        and not p9bj_summary.get("blockers")
        and p9bj_summary.get("p9bj_retained_readiness_review_ready") is True
        and p9bj_summary.get("eligible_for_future_p9bk_owner_gate_request") is True
        and p9bj_summary.get("allowed_next_gate") == P9BK_GATE
        and p9bj_summary.get("candidate_execution_authorized") is False
        and p9bj_summary.get("live_order_submission_authorized") is False
        and zero_orders_fills(p9bj_summary)
        and p9bj_review.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bj_readiness_review.v1"
        and p9bj_review.get("retained_readiness_review_ready") is True
        and p9bj_review.get("timer_path_shadow_readback_executed_in_p9bi") is True
        and p9bj_review.get("timer_path_shadow_readback_scope") == LOCAL_TIMER_READBACK_SCOPE
        and p9bj_review.get("sufficient_for_future_p9bk_owner_gate_request") is True
        and p9bj_review.get("allowed_next_gate") == P9BK_GATE
        and p9bj_review.get("candidate_execution_authorized") is False
        and p9bj_review.get("live_order_submission_authorized") is False
        and int(p9bj_review.get("orders_submitted") or 0) == 0
        and int(p9bj_review.get("fill_count") or 0) == 0
        and corridor_paths["owner_decision_record"].exists()
        and corridor_paths["p9bh_summary"].exists()
        and corridor_paths["p9bi_summary"].exists()
        and corridor_paths["p9bj_summary"].exists()
        and p9bi_paths["timer_path_shadow_readback_execution_package"].exists()
        and p9bi_paths["timer_path_shadow_readback"].exists()
        and p9bi_paths["executor_input_guard"].exists()
        and p9bj_paths["readiness_review"].exists()
        and output_under_proof_artifacts(p9bi_paths["timer_path_shadow_readback_execution_package"])
        and output_under_proof_artifacts(p9bi_paths["timer_path_shadow_readback"])
        and output_under_proof_artifacts(p9bi_paths["executor_input_guard"])
        and output_under_proof_artifacts(p9bj_paths["readiness_review"])
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def build_owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9BK_DECISION
    record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bk_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "review_p9bh_p9bj_retained_evidence_sufficiency_only",
        "decision_effect": "review_retained_p9bh_p9bj_evidence_only" if approved else "none",
        "retained_evidence_review_approved": approved,
        "p9bh_p9bj_sufficiency_review_approved": approved,
        "define_next_gate_scope_approved": False,
        "next_gate_execution_approved": False,
    }
    for key in (
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
    ):
        record[key] = False
    return record


def review_boundary(*, review_authorized: bool) -> dict[str, Any]:
    return {
        "retained_evidence_review_authorized": review_authorized,
        "p9bh_p9bj_sufficiency_review_authorized": review_authorized,
        "define_next_gate_scope_authorized": False,
        "next_gate_execution_authorized": False,
        "timer_path_shadow_readback_execution_authorized": False,
        "timer_path_shadow_readback_authorized": False,
        "dry_load_readback_execution_authorized": False,
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
        "executor_consumes_baseline_only": True,
        "candidate_plan_referenced_by_executor": False,
    }


def build_p9bk(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9bk" / run_id

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9bh_p9bj": latest_p9bh_p9bj_summary(args),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
        "live_config_dir": resolve_path(args.live_config_dir),
    }
    project_profile = load_optional(paths["project_profile"])
    p9bh_p9bj = load_optional(paths["phase9bh_p9bj"])
    corridor_paths = p9bh_p9bj_output_paths(p9bh_p9bj)
    owner_record = load_optional(corridor_paths["owner_decision_record"])
    p9bi_summary = load_optional(corridor_paths["p9bi_summary"])
    p9bj_summary = load_optional(corridor_paths["p9bj_summary"])
    p9bi_paths = p9bi_output_paths(p9bi_summary)
    p9bj_paths = p9bj_output_paths(p9bj_summary)
    p9bi_package = load_optional(p9bi_paths["timer_path_shadow_readback_execution_package"])
    p9bi_readback = load_optional(p9bi_paths["timer_path_shadow_readback"])
    p9bi_guard = load_optional(p9bi_paths["executor_input_guard"])
    p9bj_review = load_optional(p9bj_paths["readiness_review"])

    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_before = tree_sha256(paths["live_config_dir"])
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    supervisor_sha_after = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_after = tree_sha256(paths["live_config_dir"])
    decision = build_owner_decision_record(args, generated_at)
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9bh_p9bj_summary": evidence_file(paths["phase9bh_p9bj"]),
        "phase9bh_p9bj_owner_decision_record": evidence_file(corridor_paths["owner_decision_record"]),
        "phase9bi_summary": evidence_file(corridor_paths["p9bi_summary"]),
        "phase9bi_timer_path_shadow_readback_execution_package": evidence_file(
            p9bi_paths["timer_path_shadow_readback_execution_package"]
        ),
        "phase9bi_timer_path_shadow_readback": evidence_file(
            p9bi_paths["timer_path_shadow_readback"]
        ),
        "phase9bi_executor_input_guard": evidence_file(p9bi_paths["executor_input_guard"]),
        "phase9bj_summary": evidence_file(corridor_paths["p9bj_summary"]),
        "phase9bj_readiness_review": evidence_file(p9bj_paths["readiness_review"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
        "live_config_dir": {
            "path": str(paths["live_config_dir"]),
            "exists": paths["live_config_dir"].exists(),
            "sha256": live_config_sha_before,
        },
    }
    evidence_ok = p9bh_p9bj_retained_evidence_sufficient(
        p9bh_p9bj,
        owner_record,
        p9bi_summary,
        p9bj_summary,
        p9bi_package,
        p9bi_readback,
        p9bi_guard,
        p9bj_review,
        corridor_paths,
        p9bi_paths,
        p9bj_paths,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    gates = {
        "owner_decision_p9bk_review_only": str(args.owner_decision) == APPROVE_P9BK_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage")
        == "stage_1_research_readiness_only",
        "p9bh_p9bj_retained_evidence_sufficient": evidence_ok,
        "p9bj_allowed_p9bk_only": p9bh_p9bj.get("allowed_next_gate") == P9BK_GATE,
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "review_output_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "owner_review_packet.json"
        ),
        "p9bk_no_new_readback_timer_supervisor_remote_order": True,
        "p9bk_no_candidate_execution_or_live_mutation": True,
    }
    status = "ready" if all(gates.values()) else "blocked"
    review_packet = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bk_owner_review_packet.v1",
        "run_id": run_id,
        "reviewed_at_utc": iso_z(generated_at),
        "review_scope": "p9bk_retained_evidence_review_after_p9bh_p9bj_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9bh_p9bj_retained_evidence_sufficient": evidence_ok,
        "sufficient_for_next_owner_gate_discussion": status == "ready",
        "allowed_next_gate": P9BL_GATE if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "review_conclusion": "ready_for_next_owner_gate_scope_discussion_only" if status == "ready" else "blocked",
        **review_boundary(review_authorized=status == "ready"),
    }
    checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bk_sufficiency_checklist.v1",
        "run_id": run_id,
        "checks": {
            "p9bh_p9bj_status_ready": p9bh_p9bj.get("status") == "ready",
            "p9bi_readback_executed": p9bh_p9bj.get("timer_path_shadow_readback_executed") is True,
            "p9bi_scope_local_proof_only": p9bh_p9bj.get("timer_path_shadow_readback_scope")
            == LOCAL_TIMER_READBACK_SCOPE,
            "baseline_executor_input_hash_unchanged": p9bi_guard.get(
                "baseline_executor_input_hash_unchanged"
            )
            is True,
            "executor_consumes_baseline_only": p9bi_guard.get("executor_consumes_baseline_only")
            is True,
            "candidate_not_executed": p9bi_readback.get("candidate_execution_performed") is False,
            "live_timer_path_not_loaded": p9bi_readback.get("live_timer_path_loaded") is False,
            "supervisor_not_run": p9bi_readback.get("ran_supervisor") is False,
            "remote_not_touched": p9bi_readback.get("remote_execution_performed") is False,
            "zero_orders_fills": zero_orders_fills(p9bi_readback),
            "no_live_mutation": no_live_mutation(p9bi_readback),
            "next_scope_not_defined_in_p9bk": True,
            "live_order_not_authorized": True,
        },
    }
    matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bk_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "retained_evidence_review": status == "ready",
            "future_next_owner_gate_request": status == "ready",
            "define_next_gate_scope": False,
            "next_gate_execution": False,
            "timer_path_shadow_readback_execution": False,
            "candidate_execution": False,
            "candidate_live_order_submission": False,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9bk_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "p9bk_retained_evidence_review_only",
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        **review_boundary(review_authorized=status == "ready"),
    }
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "owner_review_packet": str(proof_root / "owner_review_packet.json"),
        "sufficiency_checklist": str(proof_root / "sufficiency_checklist.json"),
        "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "p9bk_review_after_p9bh_p9bj.md"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "review_scope": "p9bk_retained_evidence_review_after_p9bh_p9bj_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9bk_retained_evidence_review_ready": status == "ready",
        "p9bh_p9bj_retained_evidence_sufficient": evidence_ok,
        "sufficient_for_next_owner_gate_discussion": status == "ready",
        "eligible_for_future_p9bl_owner_gate_request": status == "ready",
        "allowed_next_gate": P9BL_GATE if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "gates": gates,
        "blockers": [key for key, value in gates.items() if not value],
        "output_files": output_files,
        **review_boundary(review_authorized=status == "ready"),
    }
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "owner_review_packet.json", review_packet)
    write_json(proof_root / "sufficiency_checklist.json", checklist)
    write_json(proof_root / "non_authorization_matrix.json", matrix)
    write_json(proof_root / "control_boundary_readback.json", control)
    write_json(root / "summary.json", summary)
    (root / "p9bk_review_after_p9bh_p9bj.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9BK Retained-Evidence Review",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9BK reviews retained P9BH-P9BJ evidence only. It does not define the next scope or authorize live order.",
        "",
        "```text",
        f"p9bk_retained_evidence_review_ready = {str(bool(summary['p9bk_retained_evidence_review_ready'])).lower()}",
        f"allowed_next_gate = {summary['allowed_next_gate']}",
        "define_next_gate_scope_authorized = false",
        "next_gate_execution_authorized = false",
        "timer_path_shadow_readback_execution_authorized = false",
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
    summary, exit_code = build_p9bk(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    print(f"allowed_next_gate={summary['allowed_next_gate']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
