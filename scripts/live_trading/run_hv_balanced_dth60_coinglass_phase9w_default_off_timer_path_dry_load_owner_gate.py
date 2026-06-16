from __future__ import annotations

import argparse
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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    current_supervisor_loads_hook,
    evidence_file,
    file_sha256,
    latest_match,
    load_optional,
    output_under_proof_artifacts,
    resolve_path,
    write_json,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    CORRIDOR_PARENT,
    HOOK_MODULE,
    LIVE_CONFIG_DIR,
    P9V_PARENT,
    P9W_GATE,
    PROJECT_PROFILE,
    SUPERVISOR_PATH,
    source_output_path,
    tree_sha256,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9w_default_off_timer_path_dry_load_owner_gate.v1"
APPROVE_P9W_DECISION = "approve_p9w_discuss_default_off_timer_path_dry_load_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9w_default_off_timer_path_dry_load_owner_gate"
P9X_GATE = "P9X_default_off_timer_path_dry_load_execution_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the P9W owner gate that only reviews whether a future "
            "default-off timer-path dry-load execution gate may be requested. "
            "P9W does not execute dry-load, enter the timer path, mutate "
            "executor/config state, run the supervisor, sync remote state, "
            "enable candidate execution, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9tuv-summary", default="")
    parser.add_argument("--phase9v-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9W_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9w_owner_gate_discuss_default_off_timer_path_dry_load_only",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_required_json(path: Path) -> dict[str, Any]:
    with resolve_path(path).open(encoding="utf-8") as handle:
        return dict(json.load(handle))


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def zero_orders_fills_basic(payload: dict[str, Any]) -> bool:
    return int_zero(payload, "orders_submitted") and int_zero(payload, "fill_count")


def no_live_mutation_basic(payload: dict[str, Any]) -> bool:
    return (
        payload.get("live_config_changed") is False
        and payload.get("operator_state_changed") is False
        and payload.get("timer_state_changed") is False
    )


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9w_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "discuss_whether_to_execute_default_off_timer_path_dry_load_only",
        "decision_effect": "allow_only_a_future_separately_requested_execution_gate_discussion",
        "p9w_owner_gate_review_approved": args.owner_decision == APPROVE_P9W_DECISION,
        "future_default_off_timer_path_dry_load_gate_discussion_approved": args.owner_decision
        == APPROVE_P9W_DECISION,
        "execute_default_off_timer_path_dry_load_approved": False,
        "candidate_execution_approved": False,
        "live_order_submission_approved": False,
        "live_timer_path_load_approved": False,
        "timer_hook_implementation_approved": False,
        "hook_deployment_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "remote_sync_approved": False,
        "supervisor_run_approved": False,
        "repo_stage_change_approved": False,
    }


def p9tuv_ready(summary: dict[str, Any]) -> bool:
    hard_stops = set(summary.get("hard_stop_before") or [])
    required_stops = {
        "remote_sync",
        "live_timer_path_load",
        "supervisor_run",
        "executor_input_mutation",
        "target_plan_replacement",
        "operator_state_mutation",
        "stage_governance_change",
        "live_order_submission",
    }
    return (
        summary.get("contract_version") == "hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor.v1"
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9t_status") == "ready"
        and summary.get("p9u_status") == "ready"
        and summary.get("p9v_status") == "ready"
        and required_stops.issubset(hard_stops)
        and summary.get("remote_sync_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_run_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("live_config_mutation_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and zero_orders_fills_basic(summary)
    )


def p9v_ready(
    summary: dict[str, Any],
    readiness_review: dict[str, Any],
    control_readback: dict[str, Any],
    *,
    current_hook_sha256: str,
    current_supervisor_sha256: str,
    current_live_config_sha256: str,
    current_supervisor_loads_candidate_hook: bool,
) -> bool:
    gates = dict(summary.get("gates") or {})
    source = dict(summary.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    live_config = dict(source.get("live_config_dir") or {})
    required_gates = (
        "project_stage_boundary_preserved",
        "p9u_proposal_package_ready",
        "proposal_package_under_proof_artifacts",
        "readiness_review_output_under_proof_artifacts",
        "timer_path_not_entered",
        "executor_input_not_mutated",
        "live_config_not_mutated",
        "live_config_digest_unchanged",
        "live_supervisor_source_unchanged",
        "current_live_supervisor_not_loading_hook",
        "supervisor_not_run",
        "no_remote_execution_in_p9v",
        "no_target_plan_replacement_in_p9v",
        "no_live_mutation_in_p9v",
        "zero_orders_fills_in_p9v",
    )
    return (
        summary.get("contract_version") == "hv_balanced_dth60_coinglass_phase9v_dry_load_readiness_review.v1"
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("gate_scope") == "p9v_local_retained_evidence_dry_load_readiness_review_only"
        and summary.get("p9v_dry_load_readiness_review_ready") is True
        and summary.get("reviewed_only_retained_evidence") is True
        and summary.get("allowed_next_gate") == P9W_GATE
        and summary.get("recommended_next_gate") == P9W_GATE
        and all(gates.get(gate) is True for gate in required_gates)
        and summary.get("entered_timer_path") is False
        and summary.get("dry_load_executed") is False
        and summary.get("executor_input_mutated") is False
        and summary.get("executor_input_changed") is False
        and summary.get("live_config_mutated") is False
        and summary.get("live_config_changed") is False
        and summary.get("live_config_dir_unchanged") is True
        and summary.get("target_plan_replaced") is False
        and summary.get("live_supervisor_loads_candidate_hook") is False
        and current_supervisor_loads_candidate_hook is False
        and summary.get("live_supervisor_source_unchanged") is True
        and summary.get("live_timer_path_loaded") is False
        and summary.get("live_timer_service_enabled_or_invoked") is False
        and summary.get("ran_supervisor") is False
        and summary.get("timer_path_invoked") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("remote_control_plane_touched") is False
        and summary.get("implemented_hook") is False
        and summary.get("deployed_hook") is False
        and summary.get("loaded_hook") is False
        and summary.get("wrote_live_hook_config") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("supervisor_run_authorized") is False
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("candidate_live_order_submission_authorized") is False
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_overlay_execution_path") == "excluded"
        and summary.get("candidate_artifact_sink") == "proof_artifacts_only"
        and zero_orders_fills_basic(summary)
        and no_live_mutation_basic(summary)
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and readiness_review.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9v_dry_load_readiness_review.v1"
        and readiness_review.get("review_mode") == "local_retained_evidence_readiness_review_not_timer_path"
        and readiness_review.get("reviewed_only_retained_evidence") is True
        and readiness_review.get("entered_timer_path") is False
        and readiness_review.get("dry_load_executed") is False
        and readiness_review.get("executor_input_mutated") is False
        and readiness_review.get("live_config_mutated") is False
        and readiness_review.get("target_plan_replaced") is False
        and readiness_review.get("remote_sync_performed") is False
        and readiness_review.get("supervisor_run") is False
        and zero_orders_fills_basic(readiness_review)
        and control_readback.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9v_control_boundary_readback.v1"
        and control_readback.get("entered_timer_path") is False
        and control_readback.get("executor_input_mutated") is False
        and control_readback.get("live_config_changed") is False
        and control_readback.get("live_config_dir_unchanged") is True
        and control_readback.get("live_config_dir_sha256_before") == current_live_config_sha256
        and control_readback.get("live_config_dir_sha256_after") == current_live_config_sha256
        and control_readback.get("live_supervisor_loads_candidate_hook") is False
        and control_readback.get("live_supervisor_source_unchanged") is True
        and control_readback.get("live_supervisor_sha256_before") == current_supervisor_sha256
        and control_readback.get("live_supervisor_sha256_after") == current_supervisor_sha256
        and control_readback.get("target_plan_replaced") is False
        and control_readback.get("remote_control_plane_touched") is False
        and zero_orders_fills_basic(control_readback)
    )


def build_phase9w(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = root / "proof_artifacts" / "p9w" / run_id

    project_profile = load_optional(resolve_path(args.project_profile))
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)
    phase9tuv_path = (
        resolve_path(args.phase9tuv_summary)
        if str(args.phase9tuv_summary).strip()
        else latest_match(CORRIDOR_PARENT, "*/summary.json")
    )
    phase9tuv_summary = load_optional(phase9tuv_path)
    phase9v_path = (
        resolve_path(args.phase9v_summary)
        if str(args.phase9v_summary).strip()
        else resolve_path(dict(phase9tuv_summary.get("outputs") or {}).get("p9v_summary") or "")
    )
    if not phase9v_path.exists() or not phase9v_path.is_file():
        phase9v_path = latest_match(P9V_PARENT, "*/summary.json")
    phase9v_summary = load_optional(phase9v_path)
    readiness_review_path = source_output_path(phase9v_summary, "dry_load_readiness_review")
    control_readback_path = source_output_path(phase9v_summary, "control_boundary_readback")
    readiness_review = load_optional(readiness_review_path)
    control_readback = load_optional(control_readback_path)

    hook_sha = file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else ""
    supervisor_sha = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    live_config_sha = tree_sha256(live_config_dir)
    supervisor_loads = current_supervisor_loads_hook(supervisor_path)
    decision = owner_decision_record(args, generated_at)
    p9tuv_ok = p9tuv_ready(phase9tuv_summary)
    p9v_ok = p9v_ready(
        phase9v_summary,
        readiness_review,
        control_readback,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha,
        current_live_config_sha256=live_config_sha,
        current_supervisor_loads_candidate_hook=supervisor_loads,
    )

    gates = {
        "owner_decision_p9w_discussion_only": args.owner_decision == APPROVE_P9W_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9tuv_corridor_ready": p9tuv_ok,
        "p9v_readiness_review_ready": p9v_ok,
        "p9v_allowed_next_gate_is_p9w": phase9v_summary.get("allowed_next_gate") == P9W_GATE,
        "p9v_did_not_enter_timer_path": phase9v_summary.get("entered_timer_path") is False,
        "p9v_did_not_execute_dry_load": phase9v_summary.get("dry_load_executed") is False,
        "p9v_did_not_mutate_executor": phase9v_summary.get("executor_input_mutated") is False,
        "p9v_did_not_mutate_live_config": phase9v_summary.get("live_config_mutated") is False,
        "p9v_live_config_digest_unchanged": phase9v_summary.get("live_config_dir_unchanged") is True,
        "readiness_review_under_proof_artifacts": output_under_proof_artifacts(readiness_review_path),
        "control_readback_under_proof_artifacts": output_under_proof_artifacts(control_readback_path),
        "current_live_supervisor_not_loading_hook": supervisor_loads is False,
        "current_live_config_matches_p9v_readback": live_config_sha
        == control_readback.get("live_config_dir_sha256_after"),
        "current_supervisor_matches_p9v_readback": supervisor_sha
        == control_readback.get("live_supervisor_sha256_after"),
        "future_gate_discussion_only": True,
        "dry_load_execution_not_authorized_in_p9w": True,
        "candidate_execution_not_authorized_in_p9w": True,
        "live_order_submission_not_authorized_in_p9w": True,
        "no_timer_path_load_in_p9w": True,
        "no_supervisor_run_in_p9w": True,
        "no_remote_execution_in_p9w": True,
        "no_executor_input_mutation_in_p9w": True,
        "no_target_plan_replacement_in_p9w": True,
        "no_live_config_mutation_in_p9w": True,
        "zero_orders_fills_in_p9w": True,
    }
    blockers = [name for name, passed in gates.items() if not passed]
    status = "ready" if not blockers else "blocked"

    gate = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9w_execution_discussion_owner_gate.v1",
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "owner_decision": decision,
        "gate_scope": "discuss_default_off_timer_path_dry_load_execution_only",
        "gate_status": status,
        "source_phase9tuv_summary": str(phase9tuv_path),
        "source_phase9v_summary": str(phase9v_path),
        "question_under_review": "whether a future default-off timer-path dry-load execution gate may be requested",
        "eligible_for_future_p9x_execution_gate": status == "ready",
        "allowed_next_gate": P9X_GATE,
        "allowed_next_gate_must_be_separately_requested": True,
        "allowed_next_gate_scope": "execute_default_off_timer_path_dry_load_only",
        "default_off_timer_path_dry_load_execution_authorized_in_p9w": False,
        "candidate_execution_authorized_in_p9w": False,
        "live_order_submission_authorized_in_p9w": False,
        "required_future_boundaries": {
            "default_off_required": True,
            "proof_artifacts_only": True,
            "baseline_only_executor_input": True,
            "candidate_execution_forbidden": True,
            "live_order_submission_forbidden": True,
            "target_plan_replacement_forbidden": True,
            "executor_input_mutation_forbidden": True,
            "live_config_mutation_forbidden": True,
            "remote_sync_forbidden": True,
            "supervisor_execution_forbidden": True,
            "timer_service_enable_or_invoke_forbidden": True,
            "orders_submitted_must_equal": 0,
            "fill_count_must_equal": 0,
        },
    }
    matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9w_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "p9w_owner_gate_review": args.owner_decision == APPROVE_P9W_DECISION,
            "future_p9x_execution_gate_request": status == "ready",
            "execute_default_off_timer_path_dry_load_in_p9w": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "live_timer_path_load": False,
            "timer_hook_implementation": False,
            "hook_deployment": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "remote_sync": False,
            "supervisor_run": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9w_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "owner_gate_discussion_only_not_dry_load_execution",
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_supervisor_sha256": supervisor_sha,
        "live_config_dir_sha256": live_config_sha,
        "entered_timer_path": False,
        "dry_load_executed": False,
        "candidate_execution_enabled": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "remote_control_plane_touched": False,
        "supervisor_run": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": status,
        "gate_scope": "owner_gated_discuss_default_off_timer_path_dry_load_only",
        "owner_decision": decision,
        "p9w_owner_gate_ready": status == "ready",
        "p9w_review_scope_only_discusses_execution": True,
        "eligible_for_future_p9x_execution_gate": status == "ready",
        "allowed_next_gate": P9X_GATE,
        "allowed_next_gate_must_be_separately_requested": True,
        "default_off_timer_path_dry_load_execution_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "timer_path_load_authorized": False,
        "timer_hook_implementation_authorized": False,
        "hook_deployment_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "remote_sync_authorized": False,
        "supervisor_run_authorized": False,
        "stage_governance_change_authorized": False,
        "entered_timer_path": False,
        "dry_load_executed": False,
        "candidate_execution_enabled": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "remote_execution_performed": False,
        "ran_supervisor": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "excluded",
        "candidate_artifact_sink": "proof_artifacts_only",
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {
            "project_profile": evidence_file(resolve_path(args.project_profile)),
            "phase9tuv_summary": evidence_file(phase9tuv_path),
            "phase9v_summary": evidence_file(phase9v_path),
            "phase9v_dry_load_readiness_review": evidence_file(readiness_review_path),
            "phase9v_control_boundary_readback": evidence_file(control_readback_path),
            "hook_module": evidence_file(hook_path),
            "live_supervisor": evidence_file(supervisor_path),
            "live_config_dir": {"path": str(live_config_dir), "exists": live_config_dir.exists(), "sha256": live_config_sha},
        },
        "proof_root": str(proof_root),
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "dry_load_execution_owner_gate": str(proof_root / "dry_load_execution_owner_gate.json"),
            "discussion_decision_matrix": str(proof_root / "discussion_decision_matrix.json"),
            "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        },
    }

    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "dry_load_execution_owner_gate.json", gate)
    write_json(proof_root / "discussion_decision_matrix.json", {"contract_version": "hv_balanced_dth60_coinglass_phase9w_discussion_decision_matrix.v1", "run_id": run_id, "gates": gates, "blockers": blockers})
    write_json(proof_root / "non_authorization_matrix.json", matrix)
    write_json(proof_root / "control_boundary_readback.json", control)
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9w(parse_args(argv))
    print(
        "status={status} run_id={run_id} summary={summary}".format(
            status=summary.get("status"),
            run_id=summary.get("run_id"),
            summary=summary.get("output_files", {}).get("summary", ""),
        )
    )
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
