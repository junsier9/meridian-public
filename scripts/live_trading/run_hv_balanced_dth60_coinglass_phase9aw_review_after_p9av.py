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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9av_default_off_dry_load_readback import (  # noqa: E402
    CONTRACT_VERSION as P9AV_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9AV_PARENT,
    P9AW_GATE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9aw_review_after_p9av.v1"
APPROVE_P9AW_DECISION = "approve_p9aw_review_after_default_off_observe_only_dry_load_readback_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9aw_review_after_p9av"
P9AX_GATE = "P9AX_allow_define_next_gate_scope_after_p9aw_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the P9AW retained-evidence review after P9AV. P9AW only "
            "reviews whether retained P9AV proof is sufficient for a separately "
            "requested next-gate scope discussion. It does not define the next "
            "scope, execute any gate, enter timer path, invoke the supervisor, "
            "remote sync, mutate live state, change executor input, replace target "
            "plans, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9av-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AW_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9aw_review_p9av_retained_evidence_sufficiency_only",
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


def latest_p9av_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9av_summary).strip():
        return resolve_path(args.phase9av_summary)
    return latest_match(P9AV_PARENT, "*/summary.json")


def all_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def p9aw_owner_decision(args: argparse.Namespace, started_at: datetime) -> dict[str, Any]:
    approved = args.owner_decision == APPROVE_P9AW_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aw_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(started_at),
        "decision_question": "review_p9av_retained_evidence_sufficiency_only",
        "decision_effect": "review_retained_p9av_evidence_without_opening_execution_gate" if approved else "none",
        "retained_evidence_review_approved": approved,
        "p9av_sufficiency_review_approved": approved,
        "define_next_gate_scope_approved": False,
        "next_gate_execution_approved": False,
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


def review_execution_boundary(*, review_authorized: bool) -> dict[str, Any]:
    return {
        "retained_evidence_review_authorized": review_authorized,
        "p9av_sufficiency_review_authorized": review_authorized,
        "define_next_gate_scope_authorized": False,
        "next_gate_execution_authorized": False,
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


def artifact_paths(p9av: dict[str, Any]) -> dict[str, Path]:
    return {
        "dry_load_manifest": source_output_path(p9av, "dry_load_manifest"),
        "candidate_shadow_artifact": source_output_path(p9av, "candidate_shadow_artifact"),
        "dry_load_readback": source_output_path(p9av, "dry_load_readback"),
        "executor_input_guard": source_output_path(p9av, "executor_input_guard"),
        "non_authorization_matrix": source_output_path(p9av, "non_authorization_matrix"),
        "control_boundary_readback": source_output_path(p9av, "control_boundary_readback"),
    }


def p9av_retained_evidence_sufficient(
    p9av: dict[str, Any],
    manifest: dict[str, Any],
    candidate_shadow: dict[str, Any],
    readback: dict[str, Any],
    guard: dict[str, Any],
    matrix: dict[str, Any],
    control: dict[str, Any],
    paths: dict[str, Path],
    *,
    current_hook_sha256: str,
    current_supervisor_sha256: str,
    current_live_config_sha256: str,
    current_supervisor_loads_candidate_hook: bool,
) -> bool:
    source = dict(p9av.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    live_config = dict(source.get("live_config_dir") or {})
    authorizations = dict(matrix.get("authorizations") or {})
    summary_false = (
        "entered_timer_path",
        "live_timer_path_loaded",
        "live_timer_service_enabled_or_invoked",
        "ran_supervisor",
        "timer_path_invoked",
        "remote_execution_performed",
        "remote_control_plane_touched",
        "candidate_execution_performed",
        "candidate_live_order_submission_authorized",
        "live_order_submission_authorized",
        "target_plan_replaced",
        "executor_input_changed",
        "live_supervisor_loads_candidate_hook",
        "live_config_changed",
        "operator_state_changed",
        "timer_state_changed",
        "wrote_live_hook_config",
        "implemented_hook",
        "deployed_hook",
        "loaded_hook",
    )
    forbidden_authorizations = (
        "dry_load_readback_execution_in_timer_path",
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
        p9av.get("contract_version") == P9AV_CONTRACT
        and p9av.get("status") == "ready"
        and not p9av.get("blockers")
        and p9av.get("p9av_default_off_observe_only_dry_load_readback_ready") is True
        and p9av.get("eligible_for_owner_p9aw_review_after_readback") is True
        and p9av.get("allowed_next_gate") == P9AW_GATE
        and p9av.get("recommended_next_gate") == P9AW_GATE
        and p9av.get("allowed_next_gate_must_be_separately_requested") is True
        and p9av.get("dry_load_readback_executed") is True
        and p9av.get("dry_load_readback_execution_scope") == "local_proof_artifacts_only_not_timer_path"
        and p9av.get("dry_load_readback_mode") == "local_proof_artifacts_only_not_timer_path"
        and p9av.get("dry_load_manifest_under_proof_artifacts") is True
        and p9av.get("dry_load_readback_under_proof_artifacts") is True
        and p9av.get("candidate_shadow_artifact_under_proof_artifacts") is True
        and p9av.get("executor_input_guard_under_proof_artifacts") is True
        and p9av.get("executor_consumes_baseline_only") is True
        and p9av.get("candidate_shadow_only") is True
        and p9av.get("candidate_plan_referenced_by_executor") is False
        and p9av.get("candidate_order_authority") == "disabled"
        and p9av.get("execution_target_source") == "baseline_only"
        and p9av.get("candidate_artifact_sink") == "proof_artifacts_only"
        and p9av.get("live_supervisor_source_unchanged") is True
        and p9av.get("live_config_dir_unchanged") is True
        and no_live_mutation(p9av)
        and zero_orders_fills(p9av)
        and all_false(p9av, summary_false)
        and all(path.exists() and output_under_proof_artifacts(path) for path in paths.values())
        and manifest.get("contract_version") == "hv_balanced_dth60_coinglass_phase9av_dry_load_manifest.v1"
        and manifest.get("dry_load_mode") == "default_off_observe_only_local_proof_artifacts_only_not_timer_path"
        and manifest.get("default_enabled") is False
        and manifest.get("observe_only") is True
        and manifest.get("executor_target_source") == "baseline_only"
        and manifest.get("candidate_artifact_sink") == "proof_artifacts_only"
        and manifest.get("candidate_shadow_only") is True
        and manifest.get("candidate_order_authority") == "disabled"
        and manifest.get("timer_path_loaded") is False
        and manifest.get("supervisor_invoked") is False
        and manifest.get("remote_sync_performed") is False
        and manifest.get("live_config_mutated") is False
        and manifest.get("operator_state_mutated") is False
        and manifest.get("timer_state_mutated") is False
        and manifest.get("executor_input_mutated") is False
        and manifest.get("target_plan_replaced") is False
        and zero_orders_fills(manifest)
        and candidate_shadow.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9av_candidate_shadow_artifact.v1"
        and candidate_shadow.get("candidate_shadow_only") is True
        and candidate_shadow.get("default_enabled") is False
        and candidate_shadow.get("observe_only") is True
        and candidate_shadow.get("candidate_order_authority") == "disabled"
        and candidate_shadow.get("candidate_plan_referenced_by_executor") is False
        and candidate_shadow.get("executor_target_source") == "baseline_only"
        and zero_orders_fills(candidate_shadow)
        and readback.get("contract_version") == "hv_balanced_dth60_coinglass_phase9av_dry_load_readback.v1"
        and readback.get("dry_load_readback_ok") is True
        and readback.get("dry_load_readback_executed") is True
        and readback.get("dry_load_readback_mode") == "local_proof_artifacts_only_not_timer_path"
        and readback.get("default_enabled") is False
        and readback.get("observe_only") is True
        and readback.get("executor_target_source") == "baseline_only"
        and readback.get("executor_consumes_baseline_only") is True
        and readback.get("candidate_shadow_only") is True
        and readback.get("candidate_plan_referenced_by_executor") is False
        and readback.get("baseline_executor_input_hash_unchanged") is True
        and readback.get("candidate_shadow_hash_differs_from_executor_input") is True
        and readback.get("entered_timer_path") is False
        and readback.get("live_timer_path_loaded") is False
        and readback.get("live_timer_service_enabled_or_invoked") is False
        and readback.get("ran_supervisor") is False
        and readback.get("timer_path_invoked") is False
        and readback.get("remote_sync_performed") is False
        and readback.get("remote_execution_performed") is False
        and readback.get("remote_control_plane_touched") is False
        and readback.get("candidate_execution_performed") is False
        and readback.get("executor_input_changed") is False
        and readback.get("target_plan_replaced") is False
        and readback.get("live_config_changed") is False
        and readback.get("operator_state_changed") is False
        and readback.get("timer_state_changed") is False
        and zero_orders_fills(readback)
        and guard.get("contract_version") == "hv_balanced_dth60_coinglass_phase9av_executor_input_guard.v1"
        and guard.get("baseline_executor_input_hash_unchanged") is True
        and guard.get("candidate_shadow_hash_differs_from_executor_input") is True
        and guard.get("executor_consumes_baseline_only") is True
        and guard.get("candidate_plan_referenced_by_executor") is False
        and guard.get("executor_input_changed") is False
        and guard.get("target_plan_replaced") is False
        and zero_orders_fills(guard)
        and matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9av_non_authorization_matrix.v1"
        and authorizations.get("default_off_observe_only_local_dry_load_readback") is True
        and authorizations.get("proof_artifacts_dry_load_readback_execution") is True
        and all(authorizations.get(key) is False for key in forbidden_authorizations)
        and control.get("contract_version") == "hv_balanced_dth60_coinglass_phase9av_control_boundary_readback.v1"
        and control.get("live_supervisor_source_unchanged") is True
        and control.get("live_supervisor_loads_candidate_hook") is False
        and control.get("live_config_dir_unchanged") is True
        and control.get("dry_load_readback_executed") is True
        and control.get("dry_load_readback_mode") == "local_proof_artifacts_only_not_timer_path"
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
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def build_p9aw(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9aw" / run_id
    p9av_summary_path = latest_p9av_summary(args)
    p9av = load_optional(p9av_summary_path)
    paths = artifact_paths(p9av)
    manifest = load_optional(paths["dry_load_manifest"])
    candidate_shadow = load_optional(paths["candidate_shadow_artifact"])
    readback = load_optional(paths["dry_load_readback"])
    guard = load_optional(paths["executor_input_guard"])
    matrix = load_optional(paths["non_authorization_matrix"])
    control = load_optional(paths["control_boundary_readback"])

    project_profile_path = resolve_path(args.project_profile)
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_path = resolve_path(args.live_config_dir)
    project_profile = load_optional(project_profile_path)
    hook_sha = file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else ""
    supervisor_sha_before = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    live_config_sha_before = tree_sha256(live_config_path)
    supervisor_loads = current_supervisor_loads_hook(supervisor_path)
    decision = p9aw_owner_decision(args, started_at)

    sufficient = p9av_retained_evidence_sufficient(
        p9av,
        manifest,
        candidate_shadow,
        readback,
        guard,
        matrix,
        control,
        paths,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads,
    )
    gates = {
        "owner_decision_p9aw_review_only": args.owner_decision == APPROVE_P9AW_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9av_retained_evidence_sufficient": sufficient,
        "p9av_allows_p9aw_only": p9av.get("allowed_next_gate") == P9AW_GATE,
        "p9av_required_separate_request": p9av.get("allowed_next_gate_must_be_separately_requested") is True,
        "review_packet_under_proof_artifacts": output_under_proof_artifacts(proof_root / "owner_review_packet.json"),
        "sufficiency_checklist_under_proof_artifacts": output_under_proof_artifacts(proof_root / "sufficiency_checklist.json"),
        "current_live_supervisor_not_loading_hook": supervisor_loads is False,
        "current_hook_hash_matches_p9av_source": dict(dict(p9av.get("source_evidence") or {}).get("hook_module") or {}).get(
            "sha256"
        )
        == hook_sha,
        "current_supervisor_hash_matches_p9av_source": dict(
            dict(p9av.get("source_evidence") or {}).get("live_supervisor") or {}
        ).get("sha256")
        == supervisor_sha_before,
        "current_live_config_hash_matches_p9av_source": dict(
            dict(p9av.get("source_evidence") or {}).get("live_config_dir") or {}
        ).get("sha256")
        == live_config_sha_before,
        "p9aw_reviews_only_retained_evidence": True,
        "p9aw_does_not_define_next_gate_scope": True,
        "p9aw_does_not_execute_next_gate": True,
        "p9aw_does_not_execute_dry_load_readback": True,
        "p9aw_does_not_enter_timer_path": True,
        "p9aw_does_not_run_supervisor": True,
        "p9aw_does_not_remote_sync": True,
        "p9aw_does_not_mutate_executor_input": True,
        "p9aw_does_not_replace_target_plan": True,
        "p9aw_does_not_mutate_live_config": True,
        "p9aw_does_not_mutate_operator_state": True,
        "p9aw_does_not_mutate_timer_state": True,
        "zero_orders_fills_in_p9aw": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    review_packet = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aw_owner_review_packet.v1",
        "run_id": run_id,
        "reviewed_at_utc": iso_z(started_at),
        "review_mode": "retained_p9av_evidence_sufficiency_only",
        "reviewed_only_retained_evidence": True,
        "owner_decision": decision,
        "source_evidence": {
            "project_profile": evidence_file(project_profile_path),
            "phase9av_summary": evidence_file(p9av_summary_path),
            "phase9av_dry_load_manifest": evidence_file(paths["dry_load_manifest"]),
            "phase9av_candidate_shadow_artifact": evidence_file(paths["candidate_shadow_artifact"]),
            "phase9av_dry_load_readback": evidence_file(paths["dry_load_readback"]),
            "phase9av_executor_input_guard": evidence_file(paths["executor_input_guard"]),
            "phase9av_non_authorization_matrix": evidence_file(paths["non_authorization_matrix"]),
            "phase9av_control_boundary_readback": evidence_file(paths["control_boundary_readback"]),
            "hook_module": evidence_file(hook_path),
            "live_supervisor": evidence_file(supervisor_path),
            "live_config_dir": {
                "path": str(live_config_path),
                "exists": live_config_path.exists(),
                "sha256": live_config_sha_before,
            },
        },
        "p9av_retained_evidence_sufficient": sufficient,
        "sufficient_for_next_gate_scope_discussion": status == "ready",
        "allowed_next_gate_if_separately_requested": P9AX_GATE if status == "ready" else "",
        "define_next_gate_scope_in_p9aw_authorized": False,
        "next_gate_execution_authorized": False,
        "entered_timer_path": False,
        "dry_load_readback_executed_in_p9aw": False,
        "supervisor_run": False,
        "remote_sync_performed": False,
        "candidate_execution_performed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "live_config_mutated": False,
        "operator_state_mutated": False,
        "timer_state_mutated": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "verdict": {
            "p9av_ready": sufficient,
            "p9av_local_proof_artifacts_only": p9av.get("dry_load_readback_execution_scope")
            == "local_proof_artifacts_only_not_timer_path",
            "p9av_executor_baseline_only": p9av.get("executor_consumes_baseline_only") is True,
            "p9av_candidate_shadow_only": p9av.get("candidate_shadow_only") is True,
            "p9av_zero_orders_fills": zero_orders_fills(p9av),
            "sufficient_for_p9ax_scope_discussion_only": status == "ready",
        },
    }
    checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aw_sufficiency_checklist.v1",
        "run_id": run_id,
        "checks": gates,
    }
    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aw_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "retained_evidence_review": status == "ready",
            "future_next_gate_scope_discussion_request": status == "ready",
            "define_next_gate_scope_in_p9aw": False,
            "next_gate_execution": False,
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
    live_config_sha_after = tree_sha256(live_config_path)
    control_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aw_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "retained_p9av_evidence_review_only",
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "define_next_gate_scope_authorized": False,
        "next_gate_execution_authorized": False,
        "dry_load_readback_executed": False,
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
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "owner_review_packet": str(proof_root / "owner_review_packet.json"),
        "sufficiency_checklist": str(proof_root / "sufficiency_checklist.json"),
        "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "gate_scope": "p9aw_retained_p9av_evidence_review_only",
        "owner_decision": decision,
        "source_evidence": review_packet["source_evidence"],
        "p9aw_retained_evidence_review_ready": status == "ready",
        "p9av_retained_evidence_sufficient": sufficient,
        "sufficient_for_next_gate_scope_discussion": status == "ready",
        "eligible_for_future_next_gate_scope_definition_request": status == "ready",
        "allowed_next_gate": P9AX_GATE if status == "ready" else "",
        "recommended_next_gate": P9AX_GATE if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "gates": gates,
        "blockers": blockers,
        **review_execution_boundary(review_authorized=status == "ready"),
        "proof_root": str(proof_root),
        "output_files": output_files,
    }
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "owner_review_packet.json", review_packet)
    write_json(proof_root / "sufficiency_checklist.json", checklist)
    write_json(proof_root / "non_authorization_matrix.json", non_authorization_matrix)
    write_json(proof_root / "control_boundary_readback.json", control_readback)
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p9aw(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    print(f"owner_review_packet={summary['output_files']['owner_review_packet']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
