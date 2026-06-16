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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bq_timer_path_shadow_cycles import (  # noqa: E402
    APPROVE_P9BQ_DECISION,
    CONTRACT_VERSION as P9BQ_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9BQ_PARENT,
    P9BR_GATE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9br_review_after_p9bq.v1"
APPROVE_P9BR_DECISION = (
    "approve_p9br_review_p9bq_shadow_cycles_sufficiency_for_execution_path_change_discussion_only"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9br_review_after_p9bq"
P9BS_GATE = (
    "P9BS_define_execution_path_change_discussion_scope_only_if_separately_requested"
)
P9BS_SCOPE = (
    "define_scope_for_execution_path_change_discussion_only_no_implementation_no_execution"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9BR as a retained-evidence review only. P9BR reviews whether "
            "the retained P9BQ continuous no-order shadow cycles are sufficient "
            "to discuss a future execution-path change. It does not define that "
            "future scope, implement or execute an execution-path change, invoke "
            "the supervisor, load timer path, remote sync, mutate executor input, "
            "replace target plans, mutate live state, execute the candidate, or "
            "authorize live orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9bq-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BR_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9br_review_shadow_cycles_sufficiency_for_execution_path_change_discussion",
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


def latest_p9bq_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bq_summary).strip():
        return resolve_path(args.phase9bq_summary)
    return latest_match(P9BQ_PARENT, "*/summary.json")


def all_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def path_exists_file(path: Path) -> bool:
    return bool(path) and str(path) not in {"", "."} and path.exists() and path.is_file()


def proof_file(path: Path) -> bool:
    return path_exists_file(path) and output_under_proof_artifacts(path)


def p9bq_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    paths = {
        "owner_decision_record": source_output_path(summary, "owner_decision_record"),
        "generated_no_order_config": source_output_path(summary, "generated_no_order_config"),
        "position_reference_fixture": source_output_path(summary, "position_reference_fixture"),
        "retained_account_plan_fixture": source_output_path(
            summary, "retained_account_plan_fixture"
        ),
        "control_boundary_readback": source_output_path(summary, "control_boundary_readback"),
        "non_authorization_matrix": source_output_path(summary, "non_authorization_matrix"),
    }
    for index in range(1, 4):
        paths[f"cycle_{index:03d}_readback"] = source_output_path(
            summary, f"cycle_{index:03d}_readback"
        )
    return paths


def hook_cycle_ready(hook: dict[str, Any], expected_target_sha: str) -> bool:
    return (
        hook.get("contract_version") == "hv_balanced_dth60_observe_only_shadow_hook.v1"
        and hook.get("status") == "ready"
        and not hook.get("blockers")
        and hook.get("hook_enabled") is True
        and hook.get("mode") == "observe_only"
        and hook.get("artifact_sink") == "proof_artifacts_only"
        and hook.get("candidate_order_authority") == "disabled"
        and hook.get("candidate_live_order_submission_authorized") is False
        and hook.get("mainnet_order_submission_authorized") is False
        and hook.get("exchange_order_submission") == "disabled"
        and hook.get("execution_target_source") == "baseline_only"
        and hook.get("candidate_overlay_execution_path") == "excluded"
        and hook.get("candidate_artifacts_under_proof_artifacts_only") is True
        and int(hook.get("candidate_artifacts_written_count") or 0) > 0
        and hook.get("executor_consumes_baseline_only") is True
        and hook.get("executor_input_plan_hash_equals_baseline") is True
        and hook.get("executor_input_plan_hash_unchanged") is True
        and hook.get("executor_input_plan_sha256_before_hook") == expected_target_sha
        and hook.get("executor_input_plan_sha256_after_hook") == expected_target_sha
        and hook.get("baseline_target_plan_byte_for_byte_unchanged") is True
        and hook.get("candidate_plan_referenced_by_executor") is False
        and hook.get("candidate_shadow_plan_sha256")
        and hook.get("candidate_shadow_plan_sha256") != expected_target_sha
        and hook.get("live_config_changed") is False
        and hook.get("operator_state_changed") is False
        and hook.get("timer_state_changed") is False
        and int_zero(hook, "candidate_orders_submitted")
        and int_zero(hook, "candidate_fill_count")
        and zero_orders_fills(hook)
    )


def supervisor_cycle_ready(supervisor: dict[str, Any]) -> bool:
    return (
        supervisor.get("status") == "mainnet_live_supervisor_completed"
        and not supervisor.get("blockers")
        and supervisor.get("live_delta_authorized") is False
        and int(supervisor.get("completed_cycle_count") or 0) >= 1
        and zero_orders_fills(supervisor)
    )


def cycle_ready(row: dict[str, Any], expected_index: int, expected_target_sha: str) -> bool:
    hook = dict(row.get("hook_summary") or {})
    supervisor = dict(row.get("supervisor_summary") or {})
    return (
        int(row.get("cycle_index") or 0) == expected_index
        and row.get("cycle_ready") is True
        and int(row.get("supervisor_exit_code") or 0) == 0
        and row.get("target_plan_sha256") == expected_target_sha
        and supervisor_cycle_ready(supervisor)
        and hook_cycle_ready(hook, expected_target_sha)
    )


def control_boundary_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("supervisor_entrypoint_invoked") is True
        and int(control.get("completed_shadow_cycles") or 0) >= 3
        and control.get("production_timer_service_loaded_or_modified") is False
        and control.get("systemd_timer_service_invoked") is False
        and control.get("remote_sync_performed") is False
        and control.get("live_config_changed") is False
        and control.get("timer_state_changed") is False
        and control.get("executor_input_changed") is False
        and control.get("target_plan_replaced") is False
        and int_zero(control, "orders_submitted")
        and int_zero(control, "orders_canceled")
        and int_zero(control, "fill_count")
        and int_zero(control, "trade_count")
    )


def non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    true_keys = (
        "continuous_timer_path_shadow_cycles_execution",
        "generated_no_order_config",
        "observe_only_hook_invocation",
        "retained_pit_safe_fixture_use",
        "supervisor_entrypoint_invocation",
    )
    false_keys = (
        "candidate_execution",
        "candidate_live_order_submission",
        "executor_input_mutation",
        "live_config_mutation",
        "live_order_submission",
        "operator_state_mutation",
        "production_timer_service_load",
        "remote_execution",
        "remote_sync",
        "stage_governance_change",
        "target_plan_replacement",
        "timer_or_service_mutation",
    )
    return all(authorizations.get(key) is True for key in true_keys) and all(
        authorizations.get(key) is False for key in false_keys
    )


def p9bq_retained_shadow_cycles_sufficient(
    summary: dict[str, Any],
    owner_record: dict[str, Any],
    control: dict[str, Any],
    matrix: dict[str, Any],
    cycle_readbacks: list[dict[str, Any]],
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
    target_hashes = [str(item) for item in list(summary.get("target_plan_sha256_each_cycle") or [])]
    expected_target_sha = target_hashes[0] if target_hashes else ""
    cycle_rows = [dict(row) for row in list(summary.get("cycle_rows") or [])]
    required_false_summary = (
        "candidate_execution_authorized",
        "candidate_execution_performed",
        "candidate_live_order_submission_authorized",
        "live_order_submission_authorized",
        "candidate_plan_referenced_by_executor",
        "executor_input_changed",
        "target_plan_replaced",
        "live_config_changed",
        "operator_state_changed_outside_generated_p9bq_state",
        "timer_state_changed",
        "production_timer_service_loaded_or_modified",
        "systemd_timer_service_invoked",
        "remote_sync_performed",
        "remote_execution_performed",
    )
    required_proof_paths = (
        "generated_no_order_config",
        "position_reference_fixture",
        "retained_account_plan_fixture",
        "control_boundary_readback",
        "non_authorization_matrix",
        "cycle_001_readback",
        "cycle_002_readback",
        "cycle_003_readback",
    )
    return (
        summary.get("contract_version") == P9BQ_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9bq_timer_path_shadow_cycles_ready") is True
        and summary.get("continuous_timer_path_shadow_cycles_ready") is True
        and summary.get("continuous_timer_path_shadow_cycles_executed") is True
        and int(summary.get("completed_shadow_cycles") or 0) >= 3
        and summary.get("fresh_proof_each_cycle") is True
        and summary.get("same_risk_no_order_config_each_cycle") is True
        and summary.get("same_target_plan_hash_each_cycle") is True
        and len(target_hashes) >= 3
        and len(set(target_hashes)) == 1
        and bool(expected_target_sha)
        and summary.get("supervisor_entrypoint_invoked") is True
        and summary.get("executor_consumes_baseline_only") is True
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_shadow_only") is True
        and summary.get("candidate_artifacts_under_proof_artifacts_only") is True
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("candidate_overlay_execution_path") == "shadow_only_not_executor"
        and summary.get("zero_order_cancel_fill_trade_delta") is True
        and all_false(summary, required_false_summary)
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and summary.get("allowed_next_gate") == P9BR_GATE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and owner_record.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bq_owner_decision.v1"
        and owner_record.get("decision") == APPROVE_P9BQ_DECISION
        and owner_record.get("continuous_timer_path_shadow_cycles_execution_approved") is True
        and owner_record.get("supervisor_entrypoint_invocation_approved") is True
        and owner_record.get("observe_only_hook_invocation_approved") is True
        and owner_record.get("retained_pit_safe_fixture_use_approved") is True
        and owner_record.get("candidate_execution_approved") is False
        and owner_record.get("candidate_live_order_submission_approved") is False
        and owner_record.get("live_order_submission_approved") is False
        and owner_record.get("target_plan_replacement_approved") is False
        and owner_record.get("executor_input_mutation_approved") is False
        and owner_record.get("live_config_mutation_approved") is False
        and owner_record.get("operator_state_mutation_approved") is False
        and owner_record.get("timer_or_service_mutation_approved") is False
        and owner_record.get("production_timer_service_load_approved") is False
        and owner_record.get("remote_sync_approved") is False
        and owner_record.get("remote_execution_approved") is False
        and owner_record.get("repo_stage_change_approved") is False
        and control_boundary_ready(control)
        and non_authorization_ready(matrix)
        and all(proof_file(paths[key]) for key in required_proof_paths)
        and path_exists_file(paths["owner_decision_record"])
        and len(cycle_rows) >= 3
        and len(cycle_readbacks) >= 3
        and all(cycle_ready(cycle_rows[index], index + 1, expected_target_sha) for index in range(3))
        and all(cycle_ready(cycle_readbacks[index], index + 1, expected_target_sha) for index in range(3))
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def build_p9br(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9br" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9bq_summary_path = latest_p9bq_summary(args)
    p9bq = load_optional(p9bq_summary_path)
    paths = p9bq_output_paths(p9bq)
    owner_record = load_optional(paths["owner_decision_record"])
    control = load_optional(paths["control_boundary_readback"])
    matrix = load_optional(paths["non_authorization_matrix"])
    cycle_readbacks = [
        load_optional(paths[f"cycle_{index:03d}_readback"]) for index in range(1, 4)
    ]

    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)
    current_hook_sha = file_sha256(hook_path) if hook_path.exists() else ""
    current_supervisor_sha = file_sha256(supervisor_path) if supervisor_path.exists() else ""
    current_live_config_sha = tree_sha256(live_config_dir)
    supervisor_loads_hook = current_supervisor_loads_hook(supervisor_path)
    owner_decision_ok = str(args.owner_decision) == APPROVE_P9BR_DECISION
    project_stage_ok = project_profile.get("current_stage") == "stage_1_research_readiness_only"

    sufficient = p9bq_retained_shadow_cycles_sufficient(
        p9bq,
        owner_record,
        control,
        matrix,
        cycle_readbacks,
        paths,
        current_hook_sha256=current_hook_sha,
        current_supervisor_sha256=current_supervisor_sha,
        current_live_config_sha256=current_live_config_sha,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )

    checks: dict[str, bool] = {
        "owner_decision_p9br_review_only": owner_decision_ok,
        "project_stage_boundary_preserved": project_stage_ok,
        "p9bq_summary_exists": path_exists_file(p9bq_summary_path),
        "p9bq_summary_ready": p9bq.get("status") == "ready",
        "p9bq_allowed_p9br_only": p9bq.get("allowed_next_gate") == P9BR_GATE,
        "p9bq_completed_at_least_three_cycles": int(p9bq.get("completed_shadow_cycles") or 0) >= 3,
        "p9bq_continuous_cycles_executed": p9bq.get("continuous_timer_path_shadow_cycles_executed")
        is True,
        "fresh_proof_each_cycle": p9bq.get("fresh_proof_each_cycle") is True,
        "same_risk_no_order_config_each_cycle": p9bq.get("same_risk_no_order_config_each_cycle")
        is True,
        "same_target_plan_hash_each_cycle": p9bq.get("same_target_plan_hash_each_cycle")
        is True,
        "supervisor_entrypoint_invoked": p9bq.get("supervisor_entrypoint_invoked") is True,
        "systemd_timer_service_not_invoked": p9bq.get("systemd_timer_service_invoked") is False,
        "production_timer_service_not_loaded_or_modified": p9bq.get(
            "production_timer_service_loaded_or_modified"
        )
        is False,
        "executor_consumes_baseline_only": p9bq.get("executor_consumes_baseline_only") is True,
        "candidate_shadow_only": p9bq.get("candidate_shadow_only") is True,
        "candidate_artifacts_under_proof_artifacts_only": p9bq.get(
            "candidate_artifacts_under_proof_artifacts_only"
        )
        is True,
        "candidate_plan_not_referenced_by_executor": p9bq.get(
            "candidate_plan_referenced_by_executor"
        )
        is False,
        "executor_input_not_changed": p9bq.get("executor_input_changed") is False,
        "target_plan_not_replaced": p9bq.get("target_plan_replaced") is False,
        "live_config_not_changed": p9bq.get("live_config_changed") is False,
        "operator_state_not_changed_outside_generated_state": p9bq.get(
            "operator_state_changed_outside_generated_p9bq_state"
        )
        is False,
        "timer_state_not_changed": p9bq.get("timer_state_changed") is False,
        "remote_sync_not_performed": p9bq.get("remote_sync_performed") is False,
        "remote_execution_not_performed": p9bq.get("remote_execution_performed") is False,
        "zero_order_cancel_fill_trade_delta": p9bq.get("zero_order_cancel_fill_trade_delta")
        is True,
        "all_cycle_readbacks_exist": all(
            path_exists_file(paths[f"cycle_{index:03d}_readback"]) for index in range(1, 4)
        ),
        "all_cycle_readbacks_under_proof_artifacts": all(
            proof_file(paths[f"cycle_{index:03d}_readback"]) for index in range(1, 4)
        ),
        "all_cycle_readbacks_ready": all(
            bool(cycle_readbacks[index - 1].get("cycle_ready")) for index in range(1, 4)
        ),
        "control_boundary_ready": control_boundary_ready(control),
        "non_authorization_matrix_ready": non_authorization_ready(matrix),
        "current_hook_hash_unchanged": dict(p9bq.get("source_evidence") or {})
        .get("hook_module", {})
        .get("sha256")
        == current_hook_sha,
        "current_supervisor_hash_unchanged": dict(p9bq.get("source_evidence") or {})
        .get("live_supervisor", {})
        .get("sha256")
        == current_supervisor_sha,
        "current_live_config_hash_unchanged": dict(p9bq.get("source_evidence") or {})
        .get("live_config_dir", {})
        .get("sha256")
        == current_live_config_sha,
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "p9bq_retained_shadow_cycles_sufficient": sufficient,
    }

    ready = owner_decision_ok and project_stage_ok and sufficient
    blockers = [key for key, value in checks.items() if not value]

    owner_decision_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9br_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "review_p9bq_shadow_cycles_sufficiency_for_execution_path_change_discussion_only",
        "decision_effect": "review_only_no_execution_path_change",
        "recorded_at_utc": iso_z(now),
        "p9bq_shadow_cycles_sufficiency_review_approved": owner_decision_ok,
        "execution_path_change_discussion_scope_definition_approved": False,
        "execution_path_change_proposal_approved": False,
        "execution_path_change_implementation_approved": False,
        "execution_path_change_execution_approved": False,
        "timer_path_load_approved": False,
        "production_timer_service_load_approved": False,
        "supervisor_invocation_approved": False,
        "remote_sync_approved": False,
        "remote_execution_approved": False,
        "candidate_execution_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "repo_stage_change_approved": False,
    }

    source_evidence = {
        "phase9bq_summary": evidence_file(p9bq_summary_path),
        "phase9bq_owner_decision_record": evidence_file(paths["owner_decision_record"]),
        "phase9bq_generated_no_order_config": evidence_file(paths["generated_no_order_config"]),
        "phase9bq_control_boundary_readback": evidence_file(paths["control_boundary_readback"]),
        "phase9bq_non_authorization_matrix": evidence_file(paths["non_authorization_matrix"]),
        "phase9bq_cycle_001_readback": evidence_file(paths["cycle_001_readback"]),
        "phase9bq_cycle_002_readback": evidence_file(paths["cycle_002_readback"]),
        "phase9bq_cycle_003_readback": evidence_file(paths["cycle_003_readback"]),
        "hook_module": evidence_file(hook_path),
        "live_supervisor": evidence_file(supervisor_path),
        "live_config_dir": {
            "path": str(live_config_dir),
            "exists": live_config_dir.exists(),
            "sha256": current_live_config_sha,
        },
        "project_profile": evidence_file(project_profile_path),
    }

    review_packet = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9br_owner_review_packet.v1",
        "run_id": run_id,
        "status": "ready" if ready else "blocked",
        "review_scope": "p9bq_shadow_cycles_sufficiency_for_execution_path_change_discussion_only",
        "p9bq_retained_shadow_cycles_sufficient": sufficient,
        "sufficient_for_execution_path_change_discussion": ready,
        "eligible_for_future_p9bs_scope_gate_request": ready,
        "allowed_next_gate": P9BS_GATE if ready else "",
        "allowed_next_gate_scope": P9BS_SCOPE if ready else "",
        "allowed_next_gate_must_be_separately_requested": ready,
        "execution_path_change_discussion_scope_definition_authorized": False,
        "execution_path_change_proposal_authorized": False,
        "execution_path_change_implementation_authorized": False,
        "execution_path_change_execution_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "blockers": blockers,
        "source_evidence": source_evidence,
    }

    sufficiency_checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9br_sufficiency_checklist.v1",
        "run_id": run_id,
        "checks": checks,
        "passed": ready,
        "blockers": blockers,
    }

    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9br_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "review_p9bq_retained_shadow_cycles": owner_decision_ok,
            "allow_future_p9bs_scope_gate_request": ready,
            "define_execution_path_change_scope_in_p9br": False,
            "execution_path_change_discussion_executed": False,
            "execution_path_change_proposal_preparation": False,
            "execution_path_change_implementation": False,
            "execution_path_change_execution": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
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
            "stage_governance_change": False,
        },
    }

    control_boundary = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9br_control_boundary_readback.v1",
        "run_id": run_id,
        "review_scope": "retained_evidence_only",
        "phase9bq_summary": source_evidence["phase9bq_summary"],
        "live_supervisor_sha256_before": current_supervisor_sha,
        "live_supervisor_sha256_after": current_supervisor_sha,
        "live_supervisor_source_unchanged": True,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_config_dir_sha256_before": current_live_config_sha,
        "live_config_dir_sha256_after": current_live_config_sha,
        "live_config_dir_unchanged": True,
        "hook_module_sha256_before": current_hook_sha,
        "hook_module_sha256_after": current_hook_sha,
        "hook_module_unchanged": True,
        "supervisor_entrypoint_invoked": False,
        "systemd_timer_service_invoked": False,
        "production_timer_service_loaded_or_modified": False,
        "timer_path_load_authorized": False,
        "timer_path_invoked": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "executor_input_changed": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }

    owner_path = root / "owner_decision_record.json"
    review_path = proof_root / "owner_review_packet.json"
    checklist_path = proof_root / "sufficiency_checklist.json"
    matrix_path = proof_root / "non_authorization_matrix.json"
    control_path = proof_root / "control_boundary_readback.json"
    report_path = root / "p9br_review_after_p9bq.md"
    summary_path = root / "summary.json"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "owner_review_packet": str(review_path),
        "sufficiency_checklist": str(checklist_path),
        "non_authorization_matrix": str(matrix_path),
        "control_boundary_readback": str(control_path),
        "report": str(report_path),
    }

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "p9br_retained_evidence_review_ready": ready,
        "p9bq_retained_shadow_cycles_sufficient": sufficient,
        "sufficient_for_execution_path_change_discussion": ready,
        "eligible_for_future_p9bs_execution_path_change_discussion_scope_gate_request": ready,
        "allowed_next_gate": P9BS_GATE if ready else "",
        "allowed_next_gate_scope": P9BS_SCOPE if ready else "",
        "allowed_next_gate_must_be_separately_requested": ready,
        "execution_path_change_discussion_scope_definition_authorized": False,
        "execution_path_change_proposal_authorized": False,
        "execution_path_change_implementation_authorized": False,
        "execution_path_change_execution_authorized": False,
        "timer_path_load_authorized": False,
        "production_timer_service_load_authorized": False,
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
        "repo_stage_change_authorized": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "executor_input_changed": False,
        "target_plan_replaced": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "source_evidence": source_evidence,
        "output_files": output_files,
    }

    write_json(owner_path, owner_decision_record)
    write_json(review_path, review_packet)
    write_json(checklist_path, sufficiency_checklist)
    write_json(matrix_path, non_authorization_matrix)
    write_json(control_path, control_boundary)
    write_json(summary_path, summary)
    report_lines = [
        "# hv_balanced DTH60/CoinGlass P9BR Review After P9BQ",
        "",
        f"`Status: {'ready' if ready else 'blocked'}`",
        "",
        "## Scope",
        "",
        "P9BR reviews whether retained P9BQ no-order shadow cycles are sufficient to discuss a future execution-path change.",
        "",
        "It does not define the future scope, implement or execute an execution-path change, load timer path, invoke the supervisor, remote sync, execute the candidate, mutate executor input, replace target plans, mutate live state, or authorize orders.",
        "",
        "## Decision",
        "",
        "```text",
        f"p9bq_retained_shadow_cycles_sufficient = {str(sufficient).lower()}",
        f"sufficient_for_execution_path_change_discussion = {str(ready).lower()}",
        f"allowed_next_gate = {summary['allowed_next_gate']}",
        "execution_path_change_implementation_authorized = false",
        "execution_path_change_execution_authorized = false",
        "candidate_execution_authorized = false",
        "live_order_submission_authorized = false",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Blockers",
        "",
    ]
    report_lines.extend([f"- {blocker}" for blocker in blockers] or ["- none"])
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return summary, 0 if ready else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p9br(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

