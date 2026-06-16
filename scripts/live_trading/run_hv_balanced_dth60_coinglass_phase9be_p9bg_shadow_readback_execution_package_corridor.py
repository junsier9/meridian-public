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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ba_p9bd_shadow_readback_proposal_corridor import (  # noqa: E402
    APPROVE_CORRIDOR_DECISION as APPROVE_P9BA_P9BD_DECISION,
    CONTRACT_VERSION as P9BA_P9BD_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9BA_P9BD_PARENT,
    P9BE_GATE,
    PROOF_FALSE_AUTHORIZATIONS,
    control_readback,
    non_authorization_matrix,
    proof_boundary,
    step_summary,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9be_p9bg_shadow_readback_execution_package_corridor.v1"
APPROVE_CORRIDOR_DECISION = "approve_p9be_p9bg_shadow_readback_execution_package_corridor_only"
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/hv_balanced_dth60_p9be_p9bg_shadow_readback_execution_package_corridor"
)

P9BF_GATE = (
    "P9BF_prepare_default_off_observe_only_live_supervisor_timer_path_shadow_readback_execution_"
    "package_only_if_separately_requested"
)
P9BG_GATE = (
    "P9BG_retained_readiness_review_after_shadow_readback_execution_package_only_if_separately_requested"
)
P9BH_GATE = (
    "P9BH_owner_gate_allow_default_off_observe_only_live_supervisor_timer_path_shadow_readback_"
    "execution_only_if_separately_requested"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9BE-P9BG as a proof-only corridor: owner gate, execution-package "
            "preparation, and retained readiness review. It does not execute dry-load/"
            "readback, enter timer path, invoke supervisor, remote sync, mutate live "
            "state or executor input, replace target plans, execute candidate logic, "
            "or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ba-p9bd-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_CORRIDOR_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:p9be_p9bg_batch_authorization")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_p9ba_p9bd_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9ba_p9bd_summary).strip():
        return resolve_path(args.phase9ba_p9bd_summary)
    return latest_match(P9BA_P9BD_PARENT, "*/summary.json")


def all_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def all_authorizations_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    authorizations = dict(payload.get("authorizations") or {})
    return all(authorizations.get(key) is False for key in keys)


def p9ba_p9bd_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    return {
        "owner_decision_record": source_output_path(summary, "owner_decision_record"),
        "p9ba_summary": source_output_path(summary, "p9ba_summary"),
        "p9bb_summary": source_output_path(summary, "p9bb_summary"),
        "p9bc_summary": source_output_path(summary, "p9bc_summary"),
        "p9bd_summary": source_output_path(summary, "p9bd_summary"),
    }


def p9bc_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    return {
        "shadow_readback_proposal_package": source_output_path(
            summary, "shadow_readback_proposal_package"
        ),
        "proposal_acceptance_checklist": source_output_path(summary, "proposal_acceptance_checklist"),
        "non_authorization_matrix": source_output_path(summary, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(summary, "control_boundary_readback"),
    }


def p9bd_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    return {
        "readiness_review": source_output_path(summary, "readiness_review"),
        "readiness_checklist": source_output_path(summary, "readiness_checklist"),
        "non_authorization_matrix": source_output_path(summary, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(summary, "control_boundary_readback"),
    }


def p9ba_p9bd_ready_for_p9be(
    corridor: dict[str, Any],
    owner_record: dict[str, Any],
    p9bc_summary: dict[str, Any],
    p9bd_summary: dict[str, Any],
    proposal_package: dict[str, Any],
    readiness_review: dict[str, Any],
    paths: dict[str, Path],
    p9bc_paths: dict[str, Path],
    p9bd_paths: dict[str, Path],
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
    proposal_contract = dict(proposal_package.get("proposal_contract") or {})
    return (
        corridor.get("contract_version") == P9BA_P9BD_CONTRACT
        and corridor.get("status") == "ready"
        and not corridor.get("blockers")
        and list(corridor.get("completed_gates") or []) == ["P9BA", "P9BB", "P9BC", "P9BD"]
        and corridor.get("p9ba_p9bd_corridor_ready") is True
        and corridor.get("p9ba_review_ready") is True
        and corridor.get("p9bb_permission_ready") is True
        and corridor.get("p9bc_proposal_package_ready") is True
        and corridor.get("p9bd_retained_readiness_review_ready") is True
        and corridor.get("eligible_for_future_p9be_owner_gate_request") is True
        and corridor.get("allowed_next_gate") == P9BE_GATE
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
        and corridor.get("supervisor_invocation_authorized") is False
        and corridor.get("remote_execution_authorized") is False
        and corridor.get("candidate_execution_authorized") is False
        and corridor.get("live_order_submission_authorized") is False
        and corridor.get("entered_timer_path") is False
        and corridor.get("ran_supervisor") is False
        and corridor.get("remote_execution_performed") is False
        and corridor.get("executor_input_changed") is False
        and corridor.get("target_plan_replaced") is False
        and no_live_mutation(corridor)
        and zero_orders_fills(corridor)
        and owner_record.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ba_p9bd_owner_decision.v1"
        and owner_record.get("decision") == APPROVE_P9BA_P9BD_DECISION
        and owner_record.get("p9ba_review_approved") is True
        and owner_record.get("p9bb_proposal_preparation_permission_approved") is True
        and owner_record.get("p9bc_proposal_package_generation_approved") is True
        and owner_record.get("p9bd_retained_readiness_review_approved") is True
        and owner_record.get("live_order_submission_approved") is False
        and p9bc_summary.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bc_shadow_readback_proposal_package.v1"
        and p9bc_summary.get("status") == "ready"
        and not p9bc_summary.get("blockers")
        and p9bc_summary.get("p9bc_proposal_package_ready") is True
        and p9bc_summary.get("generated_proposal_package") is True
        and p9bc_summary.get("proposal_package_generation_authorized") is True
        and p9bc_summary.get("allowed_next_gate")
        == "P9BD_retained_readiness_review_after_shadow_readback_proposal_package_only_if_separately_requested"
        and p9bc_summary.get("dry_load_readback_execution_authorized") is False
        and p9bc_summary.get("timer_path_shadow_readback_authorized") is False
        and p9bc_summary.get("live_order_submission_authorized") is False
        and p9bd_summary.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bd_retained_readiness_review.v1"
        and p9bd_summary.get("status") == "ready"
        and not p9bd_summary.get("blockers")
        and p9bd_summary.get("p9bd_retained_readiness_review_ready") is True
        and p9bd_summary.get("sufficient_for_future_timer_path_shadow_readback_owner_gate_request")
        is True
        and p9bd_summary.get("allowed_next_gate") == P9BE_GATE
        and p9bd_summary.get("dry_load_readback_execution_authorized") is False
        and p9bd_summary.get("timer_path_shadow_readback_authorized") is False
        and p9bd_summary.get("live_order_submission_authorized") is False
        and proposal_package.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bc_shadow_readback_proposal_package.v1"
        and proposal_package.get("proposal_package_generated") is True
        and proposal_package.get("package_written_under_proof_artifacts") is True
        and proposal_package.get("package_body_kind") == "shadow_readback_gate_proposal_package_not_execution"
        and proposal_package.get("default_enabled") is False
        and proposal_package.get("observe_only") is True
        and proposal_package.get("candidate_order_authority") == "disabled"
        and proposal_package.get("executor_target_source") == "baseline_only"
        and proposal_package.get("candidate_shadow_only") is True
        and proposal_package.get("candidate_plan_must_not_be_referenced_by_executor") is True
        and proposal_contract.get("fresh_account_read_required_before_any_future_remote_or_timer_path") is True
        and proposal_contract.get("baseline_only_executor_required") is True
        and proposal_contract.get("candidate_shadow_only_required") is True
        and proposal_contract.get("zero_order_cancel_fill_trade_delta_required") is True
        and proposal_contract.get("dry_load_readback_requires_separate_owner_gate") is True
        and proposal_contract.get("timer_path_shadow_readback_requires_separate_owner_gate") is True
        and proposal_contract.get("live_order_submission_authorized") is False
        and readiness_review.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bd_readiness_review.v1"
        and readiness_review.get("retained_readiness_review_ready") is True
        and readiness_review.get("sufficient_for_future_timer_path_shadow_readback_owner_gate_request") is True
        and readiness_review.get("allowed_next_gate") == P9BE_GATE
        and readiness_review.get("dry_load_readback_execution_authorized") is False
        and readiness_review.get("timer_path_shadow_readback_authorized") is False
        and readiness_review.get("live_order_submission_authorized") is False
        and int(readiness_review.get("orders_submitted") or 0) == 0
        and int(readiness_review.get("fill_count") or 0) == 0
        and paths["owner_decision_record"].exists()
        and paths["p9ba_summary"].exists()
        and paths["p9bb_summary"].exists()
        and paths["p9bc_summary"].exists()
        and paths["p9bd_summary"].exists()
        and p9bc_paths["shadow_readback_proposal_package"].exists()
        and p9bd_paths["readiness_review"].exists()
        and output_under_proof_artifacts(p9bc_paths["shadow_readback_proposal_package"])
        and output_under_proof_artifacts(p9bd_paths["readiness_review"])
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def build_owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_CORRIDOR_DECISION
    record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9be_p9bg_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "authorize_p9be_p9bg_execution_package_corridor_only",
        "decision_effect": "run_p9be_p9bg_proof_only_execution_package_corridor" if approved else "none",
        "p9be_owner_gate_approved": approved,
        "p9bf_execution_package_preparation_approved": approved,
        "p9bg_retained_readiness_review_approved": approved,
    }
    for key in (
        "dry_load_readback_execution_approved",
        "timer_path_shadow_readback_execution_approved",
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
    p9be_root = root / "proof_artifacts" / "p9be" / run_id
    p9bf_root = root / "proof_artifacts" / "p9bf" / run_id
    p9bg_root = root / "proof_artifacts" / "p9bg" / run_id

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9ba_p9bd": latest_p9ba_p9bd_summary(args),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
        "live_config_dir": resolve_path(args.live_config_dir),
    }
    project_profile = load_optional(paths["project_profile"])
    p9ba_p9bd = load_optional(paths["phase9ba_p9bd"])
    p9ba_p9bd_paths = p9ba_p9bd_output_paths(p9ba_p9bd)
    p9ba_p9bd_owner = load_optional(p9ba_p9bd_paths["owner_decision_record"])
    p9bc_summary = load_optional(p9ba_p9bd_paths["p9bc_summary"])
    p9bd_summary = load_optional(p9ba_p9bd_paths["p9bd_summary"])
    p9bc_paths = p9bc_output_paths(p9bc_summary)
    p9bd_paths = p9bd_output_paths(p9bd_summary)
    p9bc_proposal = load_optional(p9bc_paths["shadow_readback_proposal_package"])
    p9bd_review = load_optional(p9bd_paths["readiness_review"])

    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_before = tree_sha256(paths["live_config_dir"])
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    owner_decision = build_owner_decision_record(args, generated_at)
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9ba_p9bd_summary": evidence_file(paths["phase9ba_p9bd"]),
        "phase9ba_p9bd_owner_decision_record": evidence_file(p9ba_p9bd_paths["owner_decision_record"]),
        "phase9bc_summary": evidence_file(p9ba_p9bd_paths["p9bc_summary"]),
        "phase9bc_shadow_readback_proposal_package": evidence_file(
            p9bc_paths["shadow_readback_proposal_package"]
        ),
        "phase9bd_summary": evidence_file(p9ba_p9bd_paths["p9bd_summary"]),
        "phase9bd_readiness_review": evidence_file(p9bd_paths["readiness_review"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
        "live_config_dir": {
            "path": str(paths["live_config_dir"]),
            "exists": paths["live_config_dir"].exists(),
            "sha256": live_config_sha_before,
        },
    }
    previous_ok = p9ba_p9bd_ready_for_p9be(
        p9ba_p9bd,
        p9ba_p9bd_owner,
        p9bc_summary,
        p9bd_summary,
        p9bc_proposal,
        p9bd_review,
        p9ba_p9bd_paths,
        p9bc_paths,
        p9bd_paths,
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

    p9be_gate = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9be_owner_gate.v1",
        "run_id": run_id,
        "source_evidence": source_evidence,
        "owner_decision": owner_decision,
        "owner_gate_ready": common_ok,
        "reviewed_p9ba_p9bd_corridor": True,
        "allowed_next_gate": P9BF_GATE if common_ok else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "p9bf_allowed_action": "prepare_proof_artifacts_only_shadow_readback_execution_package",
        "p9bf_execution_authorized_in_p9be": False,
        "required_boundaries": {
            "proof_artifacts_only": True,
            "default_off_required": True,
            "observe_only_required": True,
            "executor_input_must_remain_baseline_only": True,
            "candidate_shadow_only": True,
            "candidate_order_authority": "disabled",
            "live_order_submission_authorized": False,
            "timer_path_shadow_readback_execution_authorized": False,
            "dry_load_readback_execution_authorized": False,
        },
    }
    p9be_checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9be_owner_gate_checklist.v1",
        "run_id": run_id,
        "checks": {
            "previous_corridor_ready": previous_ok,
            "p9bd_allowed_p9be_only": p9ba_p9bd.get("allowed_next_gate") == P9BE_GATE,
            "current_supervisor_not_loading_hook": supervisor_loads_hook is False,
            "stage_boundary_preserved": stage_ok,
            "owner_gate_does_not_prepare_package": True,
            "owner_gate_does_not_execute_readback": True,
            "owner_gate_does_not_enter_timer_path": True,
            "owner_gate_keeps_zero_orders_fills": True,
        },
    }
    p9be_gates = {
        "owner_decision_p9be_p9bg_corridor": owner_ok,
        "project_stage_boundary_preserved": stage_ok,
        "p9ba_p9bd_ready_for_p9be": previous_ok,
        "p9be_owner_gate_output_under_proof_artifacts": output_under_proof_artifacts(
            p9be_root / "owner_gate.json"
        ),
        "p9be_no_readback_timer_supervisor_remote_order": True,
    }
    p9be_status = "ready" if all(p9be_gates.values()) else "blocked"
    p9be_outputs = {
        "summary": str(p9be_root / "summary.json"),
        "owner_gate": str(p9be_root / "owner_gate.json"),
        "owner_gate_checklist": str(p9be_root / "owner_gate_checklist.json"),
        "non_authorization_matrix": str(p9be_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(p9be_root / "control_boundary_readback.json"),
    }
    p9be_summary = step_summary(
        contract_version="hv_balanced_dth60_coinglass_phase9be_owner_gate.v1",
        run_id=run_id,
        status=p9be_status,
        gate_scope="p9be_owner_gate_only",
        owner_decision=owner_decision,
        source_evidence=source_evidence,
        gates=p9be_gates,
        output_files=p9be_outputs,
        fields={
            "p9be_owner_gate_ready": p9be_status == "ready",
            "eligible_for_p9bf_execution_package_preparation": p9be_status == "ready",
            "allowed_next_gate": P9BF_GATE if p9be_status == "ready" else "",
            "allowed_next_gate_must_be_separately_requested": True,
            "execution_package_preparation_authorized": p9be_status == "ready",
            "execution_authorized_in_p9be": False,
        },
    )

    p9bf_ready = p9be_status == "ready"
    execution_package = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bf_shadow_readback_execution_package.v1",
        "run_id": run_id,
        "source_p9be_summary": p9be_outputs["summary"],
        "source_p9bc_proposal_package": str(p9bc_paths["shadow_readback_proposal_package"]),
        "owner_decision": owner_decision,
        "execution_package_prepared": p9bf_ready,
        "package_written_under_proof_artifacts": True,
        "package_body_kind": "shadow_readback_execution_package_not_execution",
        "default_enabled": False,
        "observe_only": True,
        "candidate_order_authority": "disabled",
        "executor_target_source": "baseline_only",
        "candidate_shadow_only": True,
        "candidate_plan_must_not_be_referenced_by_executor": True,
        "allowed_next_gate": P9BG_GATE if p9bf_ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "future_execution_contract": {
            "fresh_account_read_required_before_any_future_remote_or_timer_path": True,
            "pre_position_fingerprint_required": True,
            "post_position_fingerprint_required": True,
            "baseline_only_executor_required": True,
            "candidate_shadow_only_required": True,
            "candidate_plan_must_not_be_referenced_by_executor": True,
            "zero_order_cancel_fill_trade_delta_required": True,
            "dry_load_readback_execution_requires_separate_owner_gate": True,
            "timer_path_shadow_readback_execution_requires_separate_owner_gate": True,
            "production_timer_service_load_requires_separate_owner_gate": True,
            "live_order_submission_authorized": False,
        },
        "executed_actions": {
            "dry_load_readback_executed": False,
            "timer_path_shadow_readback_executed": False,
            "timer_path_loaded": False,
            "supervisor_invoked": False,
            "remote_sync_performed": False,
            "candidate_execution_performed": False,
            "executor_input_mutated": False,
            "target_plan_replaced": False,
            "live_config_mutated": False,
            "operator_state_mutated": False,
            "timer_state_mutated": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "fills_observed": 0,
        },
    }
    p9bf_checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bf_execution_package_checklist.v1",
        "run_id": run_id,
        "checks": {
            "p9be_owner_gate_ready": p9be_status == "ready",
            "execution_package_under_proof_artifacts": output_under_proof_artifacts(
                p9bf_root / "shadow_readback_execution_package.json"
            ),
            "package_keeps_default_off": True,
            "package_keeps_observe_only": True,
            "package_keeps_executor_baseline_only": True,
            "package_keeps_candidate_shadow_only": True,
            "package_keeps_order_authority_disabled": True,
            "package_does_not_execute_readback": True,
            "package_does_not_enter_timer_path": True,
            "package_does_not_invoke_supervisor": True,
            "package_does_not_remote_sync": True,
            "package_keeps_zero_orders_fills": True,
        },
    }
    p9bf_gates = {
        "owner_decision_p9bf_execution_package": owner_ok,
        "p9be_owner_gate_ready": p9be_status == "ready",
        "execution_package_output_under_proof_artifacts": output_under_proof_artifacts(
            p9bf_root / "shadow_readback_execution_package.json"
        ),
        "execution_package_checklist_output_under_proof_artifacts": output_under_proof_artifacts(
            p9bf_root / "execution_package_checklist.json"
        ),
        "p9bf_no_readback_timer_supervisor_remote_order": True,
    }
    p9bf_status = "ready" if all(p9bf_gates.values()) else "blocked"
    p9bf_outputs = {
        "summary": str(p9bf_root / "summary.json"),
        "shadow_readback_execution_package": str(p9bf_root / "shadow_readback_execution_package.json"),
        "execution_package_checklist": str(p9bf_root / "execution_package_checklist.json"),
        "non_authorization_matrix": str(p9bf_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(p9bf_root / "control_boundary_readback.json"),
    }
    p9bf_summary = step_summary(
        contract_version="hv_balanced_dth60_coinglass_phase9bf_shadow_readback_execution_package.v1",
        run_id=run_id,
        status=p9bf_status,
        gate_scope="p9bf_prepare_shadow_readback_execution_package_only",
        owner_decision=owner_decision,
        source_evidence={"p9be_summary": evidence_file(Path(p9be_outputs["summary"])), **source_evidence},
        gates=p9bf_gates,
        output_files=p9bf_outputs,
        fields={
            "p9bf_execution_package_ready": p9bf_status == "ready",
            "execution_package_prepared": p9bf_status == "ready",
            "execution_package_under_proof_artifacts": True,
            "eligible_for_p9bg_readiness_review": p9bf_status == "ready",
            "allowed_next_gate": P9BG_GATE if p9bf_status == "ready" else "",
            "allowed_next_gate_must_be_separately_requested": True,
            "execution_package_preparation_authorized": p9bf_status == "ready",
            "execution_authorized_in_p9bf": False,
        },
    )

    p9bg_ready = p9bf_status == "ready"
    readiness_review = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bg_readiness_review.v1",
        "run_id": run_id,
        "source_p9bf_summary": p9bf_outputs["summary"],
        "owner_decision": owner_decision,
        "retained_readiness_review_ready": p9bg_ready,
        "p9be_ready": p9be_status == "ready",
        "p9bf_ready": p9bf_status == "ready",
        "sufficient_for_future_shadow_readback_execution_owner_gate_request": p9bg_ready,
        "allowed_next_gate": P9BH_GATE if p9bg_ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "review_conclusion": (
            "ready_for_future_owner_gate_discussion_only_not_execution" if p9bg_ready else "blocked"
        ),
        "dry_load_readback_execution_authorized": False,
        "timer_path_shadow_readback_authorized": False,
        "live_order_submission_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    readiness_checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bg_readiness_checklist.v1",
        "run_id": run_id,
        "checks": {
            "p9be_owner_gate_ready": p9be_status == "ready",
            "p9bf_execution_package_ready": p9bf_status == "ready",
            "all_outputs_under_proof_artifacts": True,
            "current_supervisor_not_loading_hook": supervisor_loads_hook is False,
            "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
            "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
            "executor_input_not_mutated": True,
            "target_plan_not_replaced": True,
            "live_config_not_mutated": True,
            "operator_state_not_mutated": True,
            "timer_state_not_mutated": True,
            "zero_orders_fills": True,
        },
    }
    p9bg_gates = {
        "owner_decision_p9bg_readiness_review": owner_ok,
        "p9be_ready": p9be_status == "ready",
        "p9bf_ready": p9bf_status == "ready",
        "readiness_review_output_under_proof_artifacts": output_under_proof_artifacts(
            p9bg_root / "readiness_review.json"
        ),
        "p9bg_no_readback_timer_supervisor_remote_order": True,
    }
    p9bg_status = "ready" if all(p9bg_gates.values()) else "blocked"
    p9bg_outputs = {
        "summary": str(p9bg_root / "summary.json"),
        "readiness_review": str(p9bg_root / "readiness_review.json"),
        "readiness_checklist": str(p9bg_root / "readiness_checklist.json"),
        "non_authorization_matrix": str(p9bg_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(p9bg_root / "control_boundary_readback.json"),
    }
    p9bg_summary = step_summary(
        contract_version="hv_balanced_dth60_coinglass_phase9bg_retained_readiness_review.v1",
        run_id=run_id,
        status=p9bg_status,
        gate_scope="p9bg_retained_readiness_review_only",
        owner_decision=owner_decision,
        source_evidence={"p9bf_summary": evidence_file(Path(p9bf_outputs["summary"])), **source_evidence},
        gates=p9bg_gates,
        output_files=p9bg_outputs,
        fields={
            "p9bg_retained_readiness_review_ready": p9bg_status == "ready",
            "sufficient_for_future_shadow_readback_execution_owner_gate_request": p9bg_status == "ready",
            "eligible_for_future_p9bh_owner_gate_request": p9bg_status == "ready",
            "allowed_next_gate": P9BH_GATE if p9bg_status == "ready" else "",
            "allowed_next_gate_must_be_separately_requested": True,
            "retained_readiness_review_authorized": p9bg_status == "ready",
        },
    )

    step_artifacts = [
        (p9be_root / "owner_gate.json", p9be_gate),
        (p9be_root / "owner_gate_checklist.json", p9be_checklist),
        (
            p9be_root / "non_authorization_matrix.json",
            non_authorization_matrix(
                "hv_balanced_dth60_coinglass_phase9be_non_authorization_matrix.v1",
                run_id,
                {
                    "p9be_owner_gate": p9be_status == "ready",
                    "future_p9bf_execution_package_request": p9be_status == "ready",
                },
            ),
        ),
        (
            p9be_root / "control_boundary_readback.json",
            control_readback(
                "hv_balanced_dth60_coinglass_phase9be_control_boundary_readback.v1",
                run_id,
                "p9be_owner_gate_only",
                supervisor_sha_before=supervisor_sha_before,
                supervisor_sha_after=supervisor_sha_after,
                supervisor_loads_hook=supervisor_loads_hook,
                live_config_sha_before=live_config_sha_before,
                live_config_sha_after=live_config_sha_after,
                allowed_key="p9be_owner_gate_authorized",
            ),
        ),
        (p9be_root / "summary.json", p9be_summary),
        (p9bf_root / "shadow_readback_execution_package.json", execution_package),
        (p9bf_root / "execution_package_checklist.json", p9bf_checklist),
        (
            p9bf_root / "non_authorization_matrix.json",
            non_authorization_matrix(
                "hv_balanced_dth60_coinglass_phase9bf_non_authorization_matrix.v1",
                run_id,
                {
                    "execution_package_preparation": p9bf_status == "ready",
                    "future_p9bg_readiness_review_request": p9bf_status == "ready",
                },
            ),
        ),
        (
            p9bf_root / "control_boundary_readback.json",
            control_readback(
                "hv_balanced_dth60_coinglass_phase9bf_control_boundary_readback.v1",
                run_id,
                "p9bf_execution_package_only",
                supervisor_sha_before=supervisor_sha_before,
                supervisor_sha_after=supervisor_sha_after,
                supervisor_loads_hook=supervisor_loads_hook,
                live_config_sha_before=live_config_sha_before,
                live_config_sha_after=live_config_sha_after,
                allowed_key="execution_package_preparation_authorized",
            ),
        ),
        (p9bf_root / "summary.json", p9bf_summary),
        (p9bg_root / "readiness_review.json", readiness_review),
        (p9bg_root / "readiness_checklist.json", readiness_checklist),
        (
            p9bg_root / "non_authorization_matrix.json",
            non_authorization_matrix(
                "hv_balanced_dth60_coinglass_phase9bg_non_authorization_matrix.v1",
                run_id,
                {
                    "retained_readiness_review": p9bg_status == "ready",
                    "future_p9bh_owner_gate_request": p9bg_status == "ready",
                },
            ),
        ),
        (
            p9bg_root / "control_boundary_readback.json",
            control_readback(
                "hv_balanced_dth60_coinglass_phase9bg_control_boundary_readback.v1",
                run_id,
                "p9bg_readiness_review_only",
                supervisor_sha_before=supervisor_sha_before,
                supervisor_sha_after=supervisor_sha_after,
                supervisor_loads_hook=supervisor_loads_hook,
                live_config_sha_before=live_config_sha_before,
                live_config_sha_after=live_config_sha_after,
                allowed_key="retained_readiness_review_authorized",
            ),
        ),
        (p9bg_root / "summary.json", p9bg_summary),
    ]
    for path, payload in step_artifacts:
        write_json(path, payload)

    corridor_gates = {
        "owner_decision_p9be_p9bg_corridor": owner_ok,
        "project_stage_boundary_preserved": stage_ok,
        "p9ba_p9bd_ready_for_p9be": previous_ok,
        "p9be_ready": p9be_status == "ready",
        "p9bf_ready": p9bf_status == "ready",
        "p9bg_ready": p9bg_status == "ready",
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "no_readback_timer_supervisor_remote_order": True,
    }
    corridor_status = "ready" if all(corridor_gates.values()) else "blocked"
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "p9be_summary": p9be_outputs["summary"],
        "p9bf_summary": p9bf_outputs["summary"],
        "p9bg_summary": p9bg_outputs["summary"],
        "report": str(root / "p9be_p9bg_shadow_readback_execution_package_corridor.md"),
    }
    corridor_summary = {
        "contract_version": CONTRACT_VERSION,
        "status": corridor_status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "gate_scope": "p9be_p9bg_proof_only_shadow_readback_execution_package_corridor",
        "owner_decision": owner_decision,
        "source_evidence": source_evidence,
        "completed_gates": ["P9BE", "P9BF", "P9BG"] if corridor_status == "ready" else [],
        "p9be_p9bg_corridor_ready": corridor_status == "ready",
        "p9be_owner_gate_ready": p9be_status == "ready",
        "p9bf_execution_package_ready": p9bf_status == "ready",
        "p9bg_retained_readiness_review_ready": p9bg_status == "ready",
        "dry_load_readback_execution_authorized_in_p9be": False,
        "dry_load_readback_execution_authorized_in_p9bf": False,
        "dry_load_readback_execution_authorized_in_p9bg": False,
        "timer_path_shadow_readback_execution_authorized_in_p9be": False,
        "timer_path_shadow_readback_execution_authorized_in_p9bf": False,
        "timer_path_shadow_readback_execution_authorized_in_p9bg": False,
        "eligible_for_future_p9bh_owner_gate_request": corridor_status == "ready",
        "allowed_next_gate": P9BH_GATE if corridor_status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "gates": corridor_gates,
        "blockers": [key for key, value in corridor_gates.items() if not value],
        "output_files": output_files,
    }
    corridor_summary.update(proof_boundary())
    corridor_summary["live_supervisor_loads_candidate_hook"] = supervisor_loads_hook
    corridor_summary["live_supervisor_source_unchanged"] = supervisor_sha_before == supervisor_sha_after
    corridor_summary["live_config_dir_unchanged"] = live_config_sha_before == live_config_sha_after
    write_json(root / "owner_decision_record.json", owner_decision)
    write_json(root / "summary.json", corridor_summary)
    (root / "p9be_p9bg_shadow_readback_execution_package_corridor.md").write_text(
        render_markdown(corridor_summary), encoding="utf-8"
    )
    return corridor_summary, 0 if corridor_status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9BE-P9BG Shadow Readback Execution Package Corridor",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9BE-P9BG stays proof-only: owner gate, execution-package preparation, then readiness review.",
        "",
        "```text",
        f"p9be_p9bg_corridor_ready = {str(bool(summary['p9be_p9bg_corridor_ready'])).lower()}",
        f"allowed_next_gate = {summary['allowed_next_gate']}",
        "dry_load_readback_execution_authorized = false",
        "timer_path_shadow_readback_authorized = false",
        "timer_path_load_authorized = false",
        "supervisor_invocation_authorized = false",
        "remote_execution_performed = false",
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
    summary, exit_code = build_corridor(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    print(f"allowed_next_gate={summary['allowed_next_gate']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
