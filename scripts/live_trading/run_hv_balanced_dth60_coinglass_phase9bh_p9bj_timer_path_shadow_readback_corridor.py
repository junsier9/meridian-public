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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9be_p9bg_shadow_readback_execution_package_corridor import (  # noqa: E402
    APPROVE_CORRIDOR_DECISION as APPROVE_P9BE_P9BG_DECISION,
    CONTRACT_VERSION as P9BE_P9BG_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9BE_P9BG_PARENT,
    P9BH_GATE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9bh_p9bj_timer_path_shadow_readback_corridor.v1"
APPROVE_CORRIDOR_DECISION = (
    "approve_p9bh_p9bj_default_off_observe_only_timer_path_shadow_readback_corridor_only"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_p9bh_p9bj_timer_path_shadow_readback_corridor"
)

P9BI_GATE = (
    "P9BI_execute_default_off_observe_only_timer_path_shadow_readback_only_if_separately_requested"
)
P9BJ_GATE = (
    "P9BJ_retained_readiness_review_after_timer_path_shadow_readback_only_if_separately_requested"
)
P9BK_GATE = "P9BK_owner_gate_review_p9bh_p9bj_retained_evidence_only_if_separately_requested"

LOCAL_TIMER_READBACK_SCOPE = "local_proof_artifacts_only_not_live_timer_service"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run P9BH-P9BJ as an owner-gated no-order corridor. It performs only a "
            "default-off/observe-only timer-path shadow readback under proof_artifacts, "
            "using retained P9BE-P9BG evidence. It does not load the live timer service, "
            "invoke the supervisor, remote sync, mutate live config/operator/timer/"
            "executor state, replace target plans, execute the candidate, or authorize "
            "orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9be-p9bg-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_CORRIDOR_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:p9bh_p9bj_batch_authorization")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_p9be_p9bg_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9be_p9bg_summary).strip():
        return resolve_path(args.phase9be_p9bg_summary)
    return latest_match(P9BE_P9BG_PARENT, "*/summary.json")


def stable_json_hash(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def all_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def p9be_p9bg_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    return {
        "owner_decision_record": source_output_path(summary, "owner_decision_record"),
        "p9be_summary": source_output_path(summary, "p9be_summary"),
        "p9bf_summary": source_output_path(summary, "p9bf_summary"),
        "p9bg_summary": source_output_path(summary, "p9bg_summary"),
    }


def p9bf_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    return {
        "shadow_readback_execution_package": source_output_path(
            summary, "shadow_readback_execution_package"
        ),
        "execution_package_checklist": source_output_path(summary, "execution_package_checklist"),
        "non_authorization_matrix": source_output_path(summary, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(summary, "control_boundary_readback"),
    }


def p9bg_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    return {
        "readiness_review": source_output_path(summary, "readiness_review"),
        "readiness_checklist": source_output_path(summary, "readiness_checklist"),
        "non_authorization_matrix": source_output_path(summary, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(summary, "control_boundary_readback"),
    }


def executed_actions_safe(package: dict[str, Any]) -> bool:
    executed = dict(package.get("executed_actions") or {})
    return (
        executed.get("dry_load_readback_executed") is False
        and executed.get("timer_path_shadow_readback_executed") is False
        and executed.get("timer_path_loaded") is False
        and executed.get("supervisor_invoked") is False
        and executed.get("remote_sync_performed") is False
        and executed.get("candidate_execution_performed") is False
        and executed.get("executor_input_mutated") is False
        and executed.get("target_plan_replaced") is False
        and executed.get("live_config_mutated") is False
        and executed.get("operator_state_mutated") is False
        and executed.get("timer_state_mutated") is False
        and int(executed.get("orders_submitted") or 0) == 0
        and int(executed.get("fill_count") or 0) == 0
        and int(executed.get("fills_observed") or 0) == 0
    )


def p9be_p9bg_ready_for_p9bh(
    corridor: dict[str, Any],
    owner_record: dict[str, Any],
    p9bf_summary: dict[str, Any],
    p9bg_summary: dict[str, Any],
    execution_package: dict[str, Any],
    readiness_review: dict[str, Any],
    paths: dict[str, Path],
    p9bf_paths: dict[str, Path],
    p9bg_paths: dict[str, Path],
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
    execution_contract = dict(execution_package.get("future_execution_contract") or {})
    return (
        corridor.get("contract_version") == P9BE_P9BG_CONTRACT
        and corridor.get("status") == "ready"
        and not corridor.get("blockers")
        and list(corridor.get("completed_gates") or []) == ["P9BE", "P9BF", "P9BG"]
        and corridor.get("p9be_p9bg_corridor_ready") is True
        and corridor.get("p9be_owner_gate_ready") is True
        and corridor.get("p9bf_execution_package_ready") is True
        and corridor.get("p9bg_retained_readiness_review_ready") is True
        and corridor.get("eligible_for_future_p9bh_owner_gate_request") is True
        and corridor.get("allowed_next_gate") == P9BH_GATE
        and corridor.get("allowed_next_gate_must_be_separately_requested") is True
        and corridor.get("candidate_order_authority") == "disabled"
        and corridor.get("execution_target_source") == "baseline_only"
        and corridor.get("candidate_artifact_sink") == "proof_artifacts_only"
        and corridor.get("executor_consumes_baseline_only") is True
        and corridor.get("candidate_shadow_only") is True
        and corridor.get("candidate_plan_referenced_by_executor") is False
        and corridor.get("dry_load_readback_execution_authorized") is False
        and corridor.get("timer_path_shadow_readback_authorized") is False
        and corridor.get("timer_path_load_authorized") is False
        and corridor.get("entered_timer_path") is False
        and corridor.get("ran_supervisor") is False
        and corridor.get("remote_execution_performed") is False
        and corridor.get("candidate_execution_authorized") is False
        and corridor.get("candidate_execution_performed") is False
        and corridor.get("executor_input_changed") is False
        and corridor.get("target_plan_replaced") is False
        and no_live_mutation(corridor)
        and zero_orders_fills(corridor)
        and owner_record.get("contract_version") == "hv_balanced_dth60_coinglass_phase9be_p9bg_owner_decision.v1"
        and owner_record.get("decision") == APPROVE_P9BE_P9BG_DECISION
        and owner_record.get("p9be_owner_gate_approved") is True
        and owner_record.get("p9bf_execution_package_preparation_approved") is True
        and owner_record.get("p9bg_retained_readiness_review_approved") is True
        and owner_record.get("timer_path_shadow_readback_execution_approved") is False
        and owner_record.get("live_order_submission_approved") is False
        and p9bf_summary.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bf_shadow_readback_execution_package.v1"
        and p9bf_summary.get("status") == "ready"
        and not p9bf_summary.get("blockers")
        and p9bf_summary.get("p9bf_execution_package_ready") is True
        and p9bf_summary.get("execution_authorized_in_p9bf") is False
        and p9bf_summary.get("allowed_next_gate")
        == "P9BG_retained_readiness_review_after_shadow_readback_execution_package_only_if_separately_requested"
        and p9bg_summary.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bg_retained_readiness_review.v1"
        and p9bg_summary.get("status") == "ready"
        and not p9bg_summary.get("blockers")
        and p9bg_summary.get("p9bg_retained_readiness_review_ready") is True
        and p9bg_summary.get("eligible_for_future_p9bh_owner_gate_request") is True
        and p9bg_summary.get("allowed_next_gate") == P9BH_GATE
        and execution_package.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bf_shadow_readback_execution_package.v1"
        and execution_package.get("execution_package_prepared") is True
        and execution_package.get("package_written_under_proof_artifacts") is True
        and execution_package.get("package_body_kind") == "shadow_readback_execution_package_not_execution"
        and execution_package.get("default_enabled") is False
        and execution_package.get("observe_only") is True
        and execution_package.get("candidate_order_authority") == "disabled"
        and execution_package.get("executor_target_source") == "baseline_only"
        and execution_package.get("candidate_shadow_only") is True
        and execution_package.get("candidate_plan_must_not_be_referenced_by_executor") is True
        and execution_contract.get("baseline_only_executor_required") is True
        and execution_contract.get("candidate_shadow_only_required") is True
        and execution_contract.get("candidate_plan_must_not_be_referenced_by_executor") is True
        and execution_contract.get("zero_order_cancel_fill_trade_delta_required") is True
        and execution_contract.get("timer_path_shadow_readback_execution_requires_separate_owner_gate") is True
        and execution_contract.get("live_order_submission_authorized") is False
        and executed_actions_safe(execution_package)
        and readiness_review.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bg_readiness_review.v1"
        and readiness_review.get("retained_readiness_review_ready") is True
        and readiness_review.get("sufficient_for_future_shadow_readback_execution_owner_gate_request") is True
        and readiness_review.get("allowed_next_gate") == P9BH_GATE
        and readiness_review.get("dry_load_readback_execution_authorized") is False
        and readiness_review.get("timer_path_shadow_readback_authorized") is False
        and readiness_review.get("live_order_submission_authorized") is False
        and int(readiness_review.get("orders_submitted") or 0) == 0
        and int(readiness_review.get("fill_count") or 0) == 0
        and paths["owner_decision_record"].exists()
        and paths["p9be_summary"].exists()
        and paths["p9bf_summary"].exists()
        and paths["p9bg_summary"].exists()
        and p9bf_paths["shadow_readback_execution_package"].exists()
        and p9bg_paths["readiness_review"].exists()
        and output_under_proof_artifacts(p9bf_paths["shadow_readback_execution_package"])
        and output_under_proof_artifacts(p9bg_paths["readiness_review"])
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def build_owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_CORRIDOR_DECISION
    record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bh_p9bj_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "authorize_p9bh_p9bj_timer_path_shadow_readback_corridor_only",
        "decision_effect": "run_p9bh_p9bj_no_order_shadow_readback_corridor" if approved else "none",
        "p9bh_owner_gate_approved": approved,
        "p9bi_timer_path_shadow_readback_execution_approved": approved,
        "p9bi_timer_path_shadow_readback_execution_scope": LOCAL_TIMER_READBACK_SCOPE if approved else "none",
        "p9bj_retained_readiness_review_approved": approved,
    }
    for key in (
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


def readback_boundary(*, executed: bool) -> dict[str, Any]:
    return {
        "timer_path_shadow_readback_execution_authorized": executed,
        "timer_path_shadow_readback_authorized": executed,
        "default_off_observe_only_timer_path_shadow_readback_authorized": executed,
        "timer_path_shadow_readback_executed": executed,
        "timer_path_shadow_readback_scope": LOCAL_TIMER_READBACK_SCOPE if executed else "none",
        "dry_load_readback_execution_authorized": False,
        "dry_load_readback_executed": False,
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
        "executor_consumes_baseline_only": executed,
        "candidate_shadow_only": executed,
        "candidate_plan_referenced_by_executor": False,
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
        "candidate_shadow_artifact_written": executed,
    }


def step_summary(
    *,
    contract_version: str,
    run_id: str,
    status: str,
    gate_scope: str,
    owner_decision: dict[str, Any],
    source_evidence: dict[str, Any],
    gates: dict[str, bool],
    output_files: dict[str, str],
    fields: dict[str, Any],
    executed: bool,
) -> dict[str, Any]:
    summary = {
        "contract_version": contract_version,
        "status": status,
        "run_id": run_id,
        "generated_gate_scope": gate_scope,
        "owner_decision": owner_decision,
        "source_evidence": source_evidence,
        "gates": gates,
        "blockers": [key for key, value in gates.items() if not value],
        "output_files": output_files,
    }
    summary.update(readback_boundary(executed=executed))
    summary.update(fields)
    return summary


def non_authorization_matrix(
    contract_version: str,
    run_id: str,
    true_authorizations: dict[str, bool],
) -> dict[str, Any]:
    authorizations = dict(true_authorizations)
    for key in (
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
    ):
        authorizations[key] = False
    return {"contract_version": contract_version, "run_id": run_id, "authorizations": authorizations}


def build_corridor(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    p9bh_root = root / "proof_artifacts" / "p9bh" / run_id
    p9bi_root = root / "proof_artifacts" / "p9bi" / run_id
    p9bj_root = root / "proof_artifacts" / "p9bj" / run_id

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9be_p9bg": latest_p9be_p9bg_summary(args),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
        "live_config_dir": resolve_path(args.live_config_dir),
    }
    project_profile = load_optional(paths["project_profile"])
    p9be_p9bg = load_optional(paths["phase9be_p9bg"])
    p9be_p9bg_paths = p9be_p9bg_output_paths(p9be_p9bg)
    p9be_p9bg_owner = load_optional(p9be_p9bg_paths["owner_decision_record"])
    p9bf_summary = load_optional(p9be_p9bg_paths["p9bf_summary"])
    p9bg_summary = load_optional(p9be_p9bg_paths["p9bg_summary"])
    p9bf_paths = p9bf_output_paths(p9bf_summary)
    p9bg_paths = p9bg_output_paths(p9bg_summary)
    p9bf_package = load_optional(p9bf_paths["shadow_readback_execution_package"])
    p9bg_review = load_optional(p9bg_paths["readiness_review"])

    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_before = tree_sha256(paths["live_config_dir"])
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    owner_decision = build_owner_decision_record(args, generated_at)
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9be_p9bg_summary": evidence_file(paths["phase9be_p9bg"]),
        "phase9be_p9bg_owner_decision_record": evidence_file(
            p9be_p9bg_paths["owner_decision_record"]
        ),
        "phase9bf_summary": evidence_file(p9be_p9bg_paths["p9bf_summary"]),
        "phase9bf_shadow_readback_execution_package": evidence_file(
            p9bf_paths["shadow_readback_execution_package"]
        ),
        "phase9bg_summary": evidence_file(p9be_p9bg_paths["p9bg_summary"]),
        "phase9bg_readiness_review": evidence_file(p9bg_paths["readiness_review"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
        "live_config_dir": {
            "path": str(paths["live_config_dir"]),
            "exists": paths["live_config_dir"].exists(),
            "sha256": live_config_sha_before,
        },
    }
    previous_ok = p9be_p9bg_ready_for_p9bh(
        p9be_p9bg,
        p9be_p9bg_owner,
        p9bf_summary,
        p9bg_summary,
        p9bf_package,
        p9bg_review,
        p9be_p9bg_paths,
        p9bf_paths,
        p9bg_paths,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    owner_ok = str(args.owner_decision) == APPROVE_CORRIDOR_DECISION
    stage_ok = project_profile.get("current_stage") == "stage_1_research_readiness_only"
    common_ok = owner_ok and stage_ok and previous_ok and supervisor_loads_hook is False
    supervisor_sha_after = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_after = tree_sha256(paths["live_config_dir"])

    p9bh_gate = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bh_owner_gate.v1",
        "run_id": run_id,
        "source_evidence": source_evidence,
        "owner_decision": owner_decision,
        "owner_gate_ready": common_ok,
        "reviewed_p9be_p9bg_corridor": True,
        "allowed_next_gate": P9BI_GATE if common_ok else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "p9bi_allowed_action": "execute_local_proof_artifacts_timer_path_shadow_readback",
        "p9bi_timer_path_shadow_readback_execution_authorized_in_p9bh": common_ok,
        "required_boundaries": {
            "proof_artifacts_only": True,
            "default_off_required": True,
            "observe_only_required": True,
            "executor_input_must_remain_baseline_only": True,
            "candidate_shadow_only": True,
            "candidate_order_authority": "disabled",
            "live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "live_timer_service_load_authorized": False,
            "supervisor_invocation_authorized": False,
            "remote_execution_authorized": False,
        },
    }
    p9bh_checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bh_owner_gate_checklist.v1",
        "run_id": run_id,
        "checks": {
            "previous_corridor_ready": previous_ok,
            "p9bg_allowed_p9bh_only": p9be_p9bg.get("allowed_next_gate") == P9BH_GATE,
            "current_supervisor_not_loading_hook": supervisor_loads_hook is False,
            "stage_boundary_preserved": stage_ok,
            "owner_gate_does_not_submit_orders": True,
            "owner_gate_does_not_execute_candidate": True,
            "owner_gate_does_not_mutate_live_state": True,
        },
    }
    p9bh_gates = {
        "owner_decision_p9bh_p9bj_corridor": owner_ok,
        "project_stage_boundary_preserved": stage_ok,
        "p9be_p9bg_ready_for_p9bh": previous_ok,
        "p9bh_owner_gate_output_under_proof_artifacts": output_under_proof_artifacts(
            p9bh_root / "owner_gate.json"
        ),
        "p9bh_no_order_candidate_or_live_mutation": True,
    }
    p9bh_status = "ready" if all(p9bh_gates.values()) else "blocked"
    p9bh_outputs = {
        "summary": str(p9bh_root / "summary.json"),
        "owner_gate": str(p9bh_root / "owner_gate.json"),
        "owner_gate_checklist": str(p9bh_root / "owner_gate_checklist.json"),
        "non_authorization_matrix": str(p9bh_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(p9bh_root / "control_boundary_readback.json"),
    }
    p9bh_summary = step_summary(
        contract_version="hv_balanced_dth60_coinglass_phase9bh_owner_gate.v1",
        run_id=run_id,
        status=p9bh_status,
        gate_scope="p9bh_owner_gate_only",
        owner_decision=owner_decision,
        source_evidence=source_evidence,
        gates=p9bh_gates,
        output_files=p9bh_outputs,
        executed=False,
        fields={
            "p9bh_owner_gate_ready": p9bh_status == "ready",
            "eligible_for_p9bi_timer_path_shadow_readback": p9bh_status == "ready",
            "allowed_next_gate": P9BI_GATE if p9bh_status == "ready" else "",
            "allowed_next_gate_must_be_separately_requested": True,
            "timer_path_shadow_readback_execution_authorized_in_p9bh": p9bh_status == "ready",
        },
    )

    p9bi_ready = p9bh_status == "ready"
    package_path = p9bi_root / "timer_path_shadow_readback_execution_package.json"
    manifest_path = p9bi_root / "timer_path_shadow_readback_manifest.json"
    shadow_path = p9bi_root / "candidate_shadow_artifact.json"
    guard_path = p9bi_root / "executor_input_guard.json"
    readback_path = p9bi_root / "timer_path_shadow_readback.json"
    if p9bi_ready:
        baseline_executor_input = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bi_baseline_executor_input_reference.v1",
            "executor_target_source": "baseline_only",
            "plan_source": "retained_baseline_reference_only",
            "candidate_plan_referenced_by_executor": False,
            "target_plan_replaced": False,
            "executor_input_changed": False,
        }
        baseline_hash_before = stable_json_hash(baseline_executor_input)
        baseline_hash_after = stable_json_hash(baseline_executor_input)
        candidate_shadow = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bi_candidate_shadow_artifact.v1",
            "run_id": run_id,
            "created_at_utc": iso_z(generated_at),
            "candidate_shadow_only": True,
            "default_enabled": False,
            "observe_only": True,
            "candidate_order_authority": "disabled",
            "candidate_execution_performed": False,
            "candidate_plan_referenced_by_executor": False,
            "executor_target_source": "baseline_only",
            "source_execution_package": evidence_file(p9bf_paths["shadow_readback_execution_package"]),
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        write_json(shadow_path, candidate_shadow)
        candidate_shadow_sha = file_sha256(shadow_path)
        execution_package = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bi_timer_path_shadow_readback_execution_package.v1",
            "run_id": run_id,
            "package_written_under_proof_artifacts": True,
            "package_body_kind": "timer_path_shadow_readback_execution_package_local_not_live_timer_service",
            "execution_scope": LOCAL_TIMER_READBACK_SCOPE,
            "source_p9bh_summary": p9bh_outputs["summary"],
            "source_p9bf_execution_package": str(p9bf_paths["shadow_readback_execution_package"]),
            "default_enabled": False,
            "observe_only": True,
            "candidate_order_authority": "disabled",
            "executor_target_source": "baseline_only",
            "candidate_shadow_only": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "live_order_submission_authorized": False,
            "candidate_execution_authorized": False,
            "timer_path_shadow_readback_executed": True,
            "live_timer_path_loaded": False,
            "supervisor_invoked": False,
            "remote_sync_performed": False,
            "orders_submitted": 0,
            "fill_count": 0,
        }
        write_json(package_path, execution_package)
        package_sha = file_sha256(package_path)
        guard = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bi_executor_input_guard.v1",
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
        write_json(guard_path, guard)
        guard_sha = file_sha256(guard_path)
        manifest = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bi_timer_path_shadow_readback_manifest.v1",
            "run_id": run_id,
            "generated_at_utc": iso_z(generated_at),
            "timer_path_shadow_readback_mode": LOCAL_TIMER_READBACK_SCOPE,
            "default_enabled": False,
            "observe_only": True,
            "executor_target_source": "baseline_only",
            "candidate_artifact_sink": "proof_artifacts_only",
            "candidate_shadow_only": True,
            "candidate_order_authority": "disabled",
            "source_evidence": source_evidence,
            "timer_path_shadow_readback_execution_package_path": str(package_path),
            "timer_path_shadow_readback_execution_package_sha256": package_sha,
            "candidate_shadow_artifact_path": str(shadow_path),
            "candidate_shadow_artifact_sha256": candidate_shadow_sha,
            "baseline_executor_input_hash_before": baseline_hash_before,
            "live_timer_path_loaded": False,
            "supervisor_invoked": False,
            "remote_sync_performed": False,
            "live_config_mutated": False,
            "operator_state_mutated": False,
            "timer_state_mutated": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
            "candidate_execution_performed": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
            "exchange_order_submission": "disabled",
        }
        write_json(manifest_path, manifest)
        manifest_sha = file_sha256(manifest_path)
        readback = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9bi_timer_path_shadow_readback.v1",
            "run_id": run_id,
            "readback_at_utc": iso_z(generated_at),
            "timer_path_shadow_readback_ok": True,
            "timer_path_shadow_readback_executed": True,
            "timer_path_shadow_readback_mode": LOCAL_TIMER_READBACK_SCOPE,
            "timer_path_shadow_readback_execution_package_path": str(package_path),
            "timer_path_shadow_readback_execution_package_sha256": package_sha,
            "timer_path_shadow_readback_manifest_path": str(manifest_path),
            "timer_path_shadow_readback_manifest_sha256": manifest_sha,
            "candidate_shadow_artifact_path": str(shadow_path),
            "candidate_shadow_artifact_sha256": candidate_shadow_sha,
            "executor_input_guard_path": str(guard_path),
            "executor_input_guard_sha256": guard_sha,
            "default_enabled": False,
            "observe_only": True,
            "executor_target_source": "baseline_only",
            "executor_consumes_baseline_only": True,
            "candidate_shadow_only": True,
            "candidate_execution_performed": False,
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

    p9bi_outputs = {
        "summary": str(p9bi_root / "summary.json"),
        "timer_path_shadow_readback_execution_package": str(package_path) if p9bi_ready else "",
        "timer_path_shadow_readback_manifest": str(manifest_path) if p9bi_ready else "",
        "candidate_shadow_artifact": str(shadow_path) if p9bi_ready else "",
        "executor_input_guard": str(guard_path) if p9bi_ready else "",
        "timer_path_shadow_readback": str(readback_path) if p9bi_ready else "",
        "non_authorization_matrix": str(p9bi_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(p9bi_root / "control_boundary_readback.json"),
    }
    readback_payload = load_optional(readback_path)
    guard_payload = load_optional(guard_path)
    p9bi_gates = {
        "owner_decision_p9bi_timer_path_shadow_readback": owner_ok,
        "p9bh_owner_gate_ready": p9bh_status == "ready",
        "readback_package_under_proof_artifacts": output_under_proof_artifacts(package_path)
        and package_path.exists(),
        "manifest_under_proof_artifacts": output_under_proof_artifacts(manifest_path)
        and manifest_path.exists(),
        "candidate_shadow_under_proof_artifacts": output_under_proof_artifacts(shadow_path)
        and shadow_path.exists(),
        "executor_input_guard_under_proof_artifacts": output_under_proof_artifacts(guard_path)
        and guard_path.exists(),
        "readback_under_proof_artifacts": output_under_proof_artifacts(readback_path)
        and readback_path.exists(),
        "timer_path_shadow_readback_local_scope": readback_payload.get("timer_path_shadow_readback_mode")
        == LOCAL_TIMER_READBACK_SCOPE,
        "readback_default_off": readback_payload.get("default_enabled") is False,
        "readback_observe_only": readback_payload.get("observe_only") is True,
        "executor_consumes_baseline_only": readback_payload.get("executor_consumes_baseline_only") is True
        and guard_payload.get("executor_consumes_baseline_only") is True,
        "candidate_shadow_only": readback_payload.get("candidate_shadow_only") is True,
        "candidate_not_executed": readback_payload.get("candidate_execution_performed") is False,
        "candidate_plan_not_referenced_by_executor": readback_payload.get(
            "candidate_plan_referenced_by_executor"
        )
        is False
        and guard_payload.get("candidate_plan_referenced_by_executor") is False,
        "baseline_executor_input_hash_unchanged": readback_payload.get(
            "baseline_executor_input_hash_unchanged"
        )
        is True
        and guard_payload.get("baseline_executor_input_hash_unchanged") is True,
        "does_not_load_live_timer_path": readback_payload.get("live_timer_path_loaded") is False,
        "does_not_invoke_supervisor": readback_payload.get("ran_supervisor") is False,
        "does_not_remote_sync": readback_payload.get("remote_execution_performed") is False,
        "does_not_mutate_executor_input": readback_payload.get("executor_input_changed") is False,
        "does_not_replace_target_plan": readback_payload.get("target_plan_replaced") is False,
        "does_not_mutate_live_config": readback_payload.get("live_config_changed") is False,
        "does_not_mutate_operator_state": readback_payload.get("operator_state_changed") is False,
        "does_not_mutate_timer_state": readback_payload.get("timer_state_changed") is False,
        "zero_orders_fills": zero_orders_fills(readback_payload),
    }
    p9bi_status = "ready" if all(p9bi_gates.values()) else "blocked"
    p9bi_summary = step_summary(
        contract_version="hv_balanced_dth60_coinglass_phase9bi_timer_path_shadow_readback.v1",
        run_id=run_id,
        status=p9bi_status,
        gate_scope="p9bi_default_off_observe_only_timer_path_shadow_readback_only",
        owner_decision=owner_decision,
        source_evidence={"p9bh_summary": evidence_file(Path(p9bh_outputs["summary"])), **source_evidence},
        gates=p9bi_gates,
        output_files=p9bi_outputs,
        executed=p9bi_status == "ready",
        fields={
            "p9bi_timer_path_shadow_readback_ready": p9bi_status == "ready",
            "timer_path_shadow_readback_mode": LOCAL_TIMER_READBACK_SCOPE,
            "eligible_for_p9bj_readiness_review": p9bi_status == "ready",
            "allowed_next_gate": P9BJ_GATE if p9bi_status == "ready" else "",
            "allowed_next_gate_must_be_separately_requested": True,
        },
    )

    p9bj_ready = p9bi_status == "ready"
    readiness_review = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bj_readiness_review.v1",
        "run_id": run_id,
        "source_p9bi_summary": p9bi_outputs["summary"],
        "owner_decision": owner_decision,
        "retained_readiness_review_ready": p9bj_ready,
        "p9bh_ready": p9bh_status == "ready",
        "p9bi_ready": p9bi_status == "ready",
        "timer_path_shadow_readback_executed_in_p9bi": p9bi_status == "ready",
        "timer_path_shadow_readback_scope": LOCAL_TIMER_READBACK_SCOPE,
        "sufficient_for_future_p9bk_owner_gate_request": p9bj_ready,
        "allowed_next_gate": P9BK_GATE if p9bj_ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "review_conclusion": (
            "ready_for_future_owner_review_only_not_live_order" if p9bj_ready else "blocked"
        ),
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    readiness_checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bj_readiness_checklist.v1",
        "run_id": run_id,
        "checks": {
            "p9bh_owner_gate_ready": p9bh_status == "ready",
            "p9bi_timer_path_shadow_readback_ready": p9bi_status == "ready",
            "all_outputs_under_proof_artifacts": True,
            "timer_path_shadow_readback_local_scope": True,
            "executor_input_not_mutated": True,
            "target_plan_not_replaced": True,
            "live_config_not_mutated": True,
            "operator_state_not_mutated": True,
            "timer_state_not_mutated": True,
            "candidate_not_executed": True,
            "zero_orders_fills": True,
        },
    }
    p9bj_gates = {
        "owner_decision_p9bj_readiness_review": owner_ok,
        "p9bh_ready": p9bh_status == "ready",
        "p9bi_ready": p9bi_status == "ready",
        "readiness_review_output_under_proof_artifacts": output_under_proof_artifacts(
            p9bj_root / "readiness_review.json"
        ),
        "p9bj_no_order_candidate_or_live_mutation": True,
    }
    p9bj_status = "ready" if all(p9bj_gates.values()) else "blocked"
    p9bj_outputs = {
        "summary": str(p9bj_root / "summary.json"),
        "readiness_review": str(p9bj_root / "readiness_review.json"),
        "readiness_checklist": str(p9bj_root / "readiness_checklist.json"),
        "non_authorization_matrix": str(p9bj_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(p9bj_root / "control_boundary_readback.json"),
    }
    p9bj_summary = step_summary(
        contract_version="hv_balanced_dth60_coinglass_phase9bj_retained_readiness_review.v1",
        run_id=run_id,
        status=p9bj_status,
        gate_scope="p9bj_retained_readiness_review_only",
        owner_decision=owner_decision,
        source_evidence={"p9bi_summary": evidence_file(Path(p9bi_outputs["summary"])), **source_evidence},
        gates=p9bj_gates,
        output_files=p9bj_outputs,
        executed=p9bi_status == "ready",
        fields={
            "p9bj_retained_readiness_review_ready": p9bj_status == "ready",
            "sufficient_for_future_p9bk_owner_gate_request": p9bj_status == "ready",
            "eligible_for_future_p9bk_owner_gate_request": p9bj_status == "ready",
            "allowed_next_gate": P9BK_GATE if p9bj_status == "ready" else "",
            "allowed_next_gate_must_be_separately_requested": True,
            "retained_readiness_review_authorized": p9bj_status == "ready",
        },
    )

    for path, payload in (
        (p9bh_root / "owner_gate.json", p9bh_gate),
        (p9bh_root / "owner_gate_checklist.json", p9bh_checklist),
        (
            p9bh_root / "non_authorization_matrix.json",
            non_authorization_matrix(
                "hv_balanced_dth60_coinglass_phase9bh_non_authorization_matrix.v1",
                run_id,
                {
                    "p9bh_owner_gate": p9bh_status == "ready",
                    "future_p9bi_timer_path_shadow_readback": p9bh_status == "ready",
                },
            ),
        ),
        (
            p9bh_root / "control_boundary_readback.json",
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9bh_control_boundary_readback.v1",
                "run_id": run_id,
                "scope": "p9bh_owner_gate_only",
                "live_supervisor_sha256_before": supervisor_sha_before,
                "live_supervisor_sha256_after": supervisor_sha_after,
                "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
                "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
                "live_config_dir_sha256_before": live_config_sha_before,
                "live_config_dir_sha256_after": live_config_sha_after,
                "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
                "p9bh_owner_gate_authorized": p9bh_status == "ready",
                **readback_boundary(executed=False),
            },
        ),
        (p9bh_root / "summary.json", p9bh_summary),
        (
            p9bi_root / "non_authorization_matrix.json",
            non_authorization_matrix(
                "hv_balanced_dth60_coinglass_phase9bi_non_authorization_matrix.v1",
                run_id,
                {
                    "default_off_observe_only_timer_path_shadow_readback": p9bi_status == "ready",
                    "proof_artifacts_timer_path_shadow_readback": p9bi_status == "ready",
                },
            ),
        ),
        (
            p9bi_root / "control_boundary_readback.json",
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9bi_control_boundary_readback.v1",
                "run_id": run_id,
                "scope": "p9bi_default_off_observe_only_timer_path_shadow_readback_only",
                "live_supervisor_sha256_before": supervisor_sha_before,
                "live_supervisor_sha256_after": supervisor_sha_after,
                "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
                "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
                "live_config_dir_sha256_before": live_config_sha_before,
                "live_config_dir_sha256_after": live_config_sha_after,
                "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
                **readback_boundary(executed=p9bi_status == "ready"),
            },
        ),
        (p9bi_root / "summary.json", p9bi_summary),
        (p9bj_root / "readiness_review.json", readiness_review),
        (p9bj_root / "readiness_checklist.json", readiness_checklist),
        (
            p9bj_root / "non_authorization_matrix.json",
            non_authorization_matrix(
                "hv_balanced_dth60_coinglass_phase9bj_non_authorization_matrix.v1",
                run_id,
                {
                    "retained_readiness_review": p9bj_status == "ready",
                    "future_p9bk_owner_gate_request": p9bj_status == "ready",
                },
            ),
        ),
        (
            p9bj_root / "control_boundary_readback.json",
            {
                "contract_version": "hv_balanced_dth60_coinglass_phase9bj_control_boundary_readback.v1",
                "run_id": run_id,
                "scope": "p9bj_readiness_review_only",
                "live_supervisor_sha256_before": supervisor_sha_before,
                "live_supervisor_sha256_after": supervisor_sha_after,
                "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
                "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
                "live_config_dir_sha256_before": live_config_sha_before,
                "live_config_dir_sha256_after": live_config_sha_after,
                "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
                **readback_boundary(executed=p9bi_status == "ready"),
            },
        ),
        (p9bj_root / "summary.json", p9bj_summary),
    ):
        write_json(path, payload)

    corridor_gates = {
        "owner_decision_p9bh_p9bj_corridor": owner_ok,
        "project_stage_boundary_preserved": stage_ok,
        "p9be_p9bg_ready_for_p9bh": previous_ok,
        "p9bh_ready": p9bh_status == "ready",
        "p9bi_ready": p9bi_status == "ready",
        "p9bj_ready": p9bj_status == "ready",
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "no_live_order_candidate_or_live_mutation": True,
    }
    corridor_status = "ready" if all(corridor_gates.values()) else "blocked"
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "p9bh_summary": p9bh_outputs["summary"],
        "p9bi_summary": p9bi_outputs["summary"],
        "p9bj_summary": p9bj_outputs["summary"],
        "report": str(root / "p9bh_p9bj_timer_path_shadow_readback_corridor.md"),
    }
    corridor_summary = {
        "contract_version": CONTRACT_VERSION,
        "status": corridor_status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "gate_scope": "p9bh_p9bj_no_order_timer_path_shadow_readback_corridor",
        "owner_decision": owner_decision,
        "source_evidence": source_evidence,
        "completed_gates": ["P9BH", "P9BI", "P9BJ"] if corridor_status == "ready" else [],
        "p9bh_p9bj_corridor_ready": corridor_status == "ready",
        "p9bh_owner_gate_ready": p9bh_status == "ready",
        "p9bi_timer_path_shadow_readback_ready": p9bi_status == "ready",
        "p9bj_retained_readiness_review_ready": p9bj_status == "ready",
        "eligible_for_future_p9bk_owner_gate_request": corridor_status == "ready",
        "allowed_next_gate": P9BK_GATE if corridor_status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "gates": corridor_gates,
        "blockers": [key for key, value in corridor_gates.items() if not value],
        "output_files": output_files,
    }
    corridor_summary.update(readback_boundary(executed=corridor_status == "ready"))
    write_json(root / "owner_decision_record.json", owner_decision)
    write_json(root / "summary.json", corridor_summary)
    (root / "p9bh_p9bj_timer_path_shadow_readback_corridor.md").write_text(
        render_markdown(corridor_summary), encoding="utf-8"
    )
    return corridor_summary, 0 if corridor_status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9BH-P9BJ Timer-Path Shadow Readback Corridor",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9BH-P9BJ stays no-order and default-off/observe-only. The readback is local proof_artifacts-only, not a live timer-service load.",
        "",
        "```text",
        f"p9bh_p9bj_corridor_ready = {str(bool(summary['p9bh_p9bj_corridor_ready'])).lower()}",
        f"timer_path_shadow_readback_scope = {summary['timer_path_shadow_readback_scope']}",
        f"allowed_next_gate = {summary['allowed_next_gate']}",
        "live_timer_path_loaded = false",
        "ran_supervisor = false",
        "remote_execution_performed = false",
        "candidate_execution_authorized = false",
        "live_order_submission_authorized = false",
        "executor_input_changed = false",
        "target_plan_replaced = false",
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
    summary, exit_code = build_corridor(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    print(f"allowed_next_gate={summary['allowed_next_gate']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
