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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bm_real_timer_path_shadow_readback import (  # noqa: E402
    APPROVE_P9BM_DECISION,
    CONTRACT_VERSION as P9BM_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9BM_PARENT,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9bn_review_after_p9bm.v1"
APPROVE_P9BN_DECISION = (
    "approve_p9bn_review_p9bm_retained_evidence_sufficiency_for_next_proposal_review_gate_only"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9bn_review_after_p9bm"
P9BO_GATE = (
    "P9BO_prepare_default_off_observe_only_live_supervisor_timer_path_readback_"
    "proposal_review_package_only_if_separately_requested"
)


FALSE_OWNER_KEYS = (
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

FALSE_BOUNDARY_KEYS = (
    "proposal_preparation_authorized",
    "proposal_execution_authorized",
    "next_gate_execution_authorized",
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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9BN as a retained-evidence review only. P9BN reviews the retained "
            "P9BM default-off/observe-only real live-supervisor timer-path shadow "
            "readback evidence and decides whether it is sufficient to allow a "
            "separately requested proposal/review gate. It does not prepare the "
            "proposal, execute another readback, enter timer path, invoke the "
            "supervisor, remote sync, execute the candidate, mutate live state or "
            "executor input, replace target plans, or authorize live orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9bm-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BN_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9bn_review_p9bm_retained_evidence_for_next_proposal_review_gate",
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


def latest_p9bm_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bm_summary).strip():
        return resolve_path(args.phase9bm_summary)
    return latest_match(P9BM_PARENT, "*/summary.json")


def all_false(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def int_zero(payload: dict[str, Any], key: str) -> bool:
    return int(payload.get(key) or 0) == 0


def p9bm_output_paths(summary: dict[str, Any]) -> dict[str, Path]:
    return {
        "owner_decision_record": source_output_path(summary, "owner_decision_record"),
        "generated_no_order_config": source_output_path(summary, "generated_no_order_config"),
        "supervisor_readback_summary": source_output_path(summary, "supervisor_readback_summary"),
        "hook_shadow_readback_summary": source_output_path(summary, "hook_shadow_readback_summary"),
        "position_reference_fixture": source_output_path(summary, "position_reference_fixture"),
        "retained_account_plan_fixture": source_output_path(summary, "retained_account_plan_fixture"),
        "control_boundary_readback": source_output_path(summary, "control_boundary_readback"),
        "non_authorization_matrix": source_output_path(summary, "non_authorization_matrix"),
    }


def path_exists_and_proof_artifact(path: Path) -> bool:
    return path.exists() and output_under_proof_artifacts(path)


def hook_summary_ready(hook: dict[str, Any]) -> bool:
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
        and hook.get("execution_target_source") == "baseline_only"
        and hook.get("candidate_overlay_execution_path") == "excluded"
        and hook.get("candidate_artifacts_under_proof_artifacts_only") is True
        and int(hook.get("candidate_artifacts_written_count") or 0) > 0
        and hook.get("executor_consumes_baseline_only") is True
        and hook.get("executor_input_plan_hash_equals_baseline") is True
        and hook.get("executor_input_plan_hash_unchanged") is True
        and hook.get("candidate_plan_referenced_by_executor") is False
        and hook.get("baseline_target_plan_byte_for_byte_unchanged") is True
        and hook.get("candidate_shadow_plan_sha256")
        and hook.get("candidate_shadow_plan_sha256") != hook.get("executor_input_plan_sha256_after_hook")
        and hook.get("live_config_changed") is False
        and hook.get("operator_state_changed") is False
        and hook.get("timer_state_changed") is False
        and zero_orders_fills(hook)
    )


def supervisor_readback_ready(supervisor: dict[str, Any]) -> bool:
    cycles = [dict(row) for row in list(supervisor.get("cycles") or [])]
    cycle = cycles[-1] if cycles else {}
    core = dict(cycle.get("core_loop_summary") or {})
    return (
        supervisor.get("status") == "mainnet_live_supervisor_completed"
        and not supervisor.get("blockers")
        and supervisor.get("live_delta_authorized") is False
        and supervisor.get("supervisor_uses_core_loop") is True
        and int(supervisor.get("completed_cycle_count") or len(cycles)) >= 1
        and zero_orders_fills(supervisor)
        and cycle.get("status") == "cycle_observed_no_order"
        and cycle.get("execute_live_delta_requested") is False
        and cycle.get("live_delta_authorized") is False
        and zero_orders_fills(cycle)
        and core.get("status") == "mainnet_core_loop_completed"
        and not core.get("blockers")
        and core.get("execution_requested") is False
        and core.get("live_delta_authorized") is False
        and zero_orders_fills(core)
    )


def position_reference_ready(position: dict[str, Any]) -> bool:
    side_effects = dict(position.get("side_effects") or {})
    return (
        position.get("contract_version") == "hv_balanced_dth60_coinglass_phase9aa_nonflat_position_reference_fixture.v1"
        and position.get("status") == "position_genesis_snapshot"
        and position.get("read_only") is True
        and position.get("proof_artifacts_only") is True
        and position.get("source_created_before_p9aa") is True
        and int(position.get("source_open_order_count") or 0) == 0
        and int(position.get("source_open_position_count") or 0) > 0
        and int(position.get("expected_position_count") or 0) > 0
        and int(position.get("orders_submitted") or 0) == 0
        and int(position.get("orders_canceled") or 0) == 0
        and int(position.get("fill_count") or 0) == 0
        and (
            side_effects.get("only_http_get_endpoints") is True
            or side_effects.get("only_local_retained_artifact_reads") is True
        )
        and int(side_effects.get("order_test_calls") or 0) == 0
        and int(side_effects.get("orders_canceled") or 0) == 0
        and int(side_effects.get("orders_submitted") or 0) == 0
    )


def retained_account_plan_fixture_ready(fixture: dict[str, Any]) -> bool:
    side_effects = dict(fixture.get("side_effects") or {})
    output_files = dict(fixture.get("output_files") or {})
    core = dict(fixture.get("core_loop_summary") or {})
    return (
        fixture.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bm_retained_account_plan_fixture.v1"
        and fixture.get("status") == "ready"
        and fixture.get("account_proof_mode") == "retained_pit_safe_read_only_fixture"
        and fixture.get("read_only") is True
        and fixture.get("proof_artifacts_only") is True
        and fixture.get("position_reference_fixture_status") == "position_genesis_snapshot"
        and fixture.get("position_reference_source_created_before_p9bm") is True
        and fixture.get("source_account_proof_finished_before_p9bm") is True
        and int(fixture.get("open_order_count") or 0) == 0
        and int(fixture.get("open_position_count") or 0) > 0
        and int(fixture.get("orders_submitted") or 0) == 0
        and int(fixture.get("orders_canceled") or 0) == 0
        and int(fixture.get("fill_count") or 0) == 0
        and (
            side_effects.get("only_http_get_endpoints") is True
            or side_effects.get("only_local_retained_artifact_reads") is True
        )
        and int(side_effects.get("order_test_calls") or 0) == 0
        and int(side_effects.get("orders_canceled") or 0) == 0
        and int(side_effects.get("orders_submitted") or 0) == 0
        and bool(str(output_files.get("target_portfolio") or ""))
        and core.get("status") == "mainnet_core_loop_completed"
        and not core.get("blockers")
        and core.get("execution_requested") is False
        and core.get("live_delta_authorized") is False
        and zero_orders_fills(core)
    )


def p9bm_retained_evidence_sufficient(
    summary: dict[str, Any],
    owner_record: dict[str, Any],
    control: dict[str, Any],
    matrix: dict[str, Any],
    hook: dict[str, Any],
    supervisor: dict[str, Any],
    position: dict[str, Any],
    retained_fixture: dict[str, Any],
    paths: dict[str, Path],
    *,
    current_hook_sha256: str,
    current_supervisor_sha256: str,
    current_live_config_sha256: str,
    current_supervisor_loads_candidate_hook: bool,
) -> bool:
    source = dict(summary.get("source_evidence") or {})
    hook_source = dict(source.get("hook_module") or {})
    supervisor_source = dict(source.get("live_supervisor") or {})
    live_config_source = dict(source.get("live_config_dir") or {})
    authorizations = dict(matrix.get("authorizations") or {})
    p9bm_gates = dict(summary.get("gates") or {})
    allowed_true_authorizations = {
        "real_timer_path_shadow_readback_execution",
        "supervisor_entrypoint_invocation",
        "observe_only_hook_invocation",
        "generated_no_order_config",
    }
    return (
        summary.get("contract_version") == P9BM_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("gate_scope") == "p9bm_real_timer_path_shadow_readback_no_order_only"
        and summary.get("p9bm_real_timer_path_shadow_readback_ready") is True
        and all(bool(value) for value in p9bm_gates.values())
        and summary.get("real_timer_path_shadow_readback_executed") is True
        and summary.get("supervisor_entrypoint_invoked") is True
        and int(summary.get("supervisor_exit_code") or 0) == 0
        and summary.get("timer_path_shadow_readback_mode")
        == "real_supervisor_entrypoint_with_retained_pit_safe_account_position_reference_fixture"
        and summary.get("account_proof_mode") == "retained_pit_safe_read_only_fixture"
        and summary.get("retained_account_fixture_requested") is True
        and summary.get("retained_account_proof_ready") is True
        and summary.get("pit_safe_position_reference_fixture_ready") is True
        and summary.get("fresh_proof") is True
        and summary.get("same_risk_no_order_config") is True
        and int(summary.get("completed_shadow_cycles") or 0) >= 1
        and summary.get("execution_target_source") == "baseline_only"
        and summary.get("candidate_overlay_execution_path") == "shadow_only_not_executor"
        and summary.get("candidate_order_authority") == "disabled"
        and summary.get("candidate_execution_authorized") is False
        and summary.get("candidate_execution_performed") is False
        and summary.get("candidate_live_order_submission_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_shadow_only") is True
        and summary.get("candidate_artifacts_under_proof_artifacts_only") is True
        and summary.get("executor_consumes_baseline_only") is True
        and summary.get("candidate_plan_referenced_by_executor") is False
        and summary.get("target_plan_replaced") is False
        and summary.get("executor_input_changed") is False
        and summary.get("systemd_timer_service_invoked") is False
        and summary.get("production_timer_service_loaded_or_modified") is False
        and summary.get("remote_sync_performed") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("live_config_changed") is False
        and summary.get("operator_state_changed_outside_generated_p9bm_state") is False
        and summary.get("timer_state_changed") is False
        and not summary.get("account_read_blockers")
        and not summary.get("supervisor_or_core_loop_blockers")
        and summary.get("plan_artifact_missing") is False
        and summary.get("zero_order_cancel_fill_trade_delta") is True
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and owner_record.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bm_owner_decision.v1"
        and owner_record.get("decision") == APPROVE_P9BM_DECISION
        and owner_record.get("real_timer_path_shadow_readback_execution_approved") is True
        and owner_record.get("supervisor_entrypoint_invocation_approved") is True
        and owner_record.get("observe_only_hook_invocation_approved") is True
        and owner_record.get("generated_no_order_config_approved") is True
        and all_false(owner_record, (
            "candidate_execution_approved",
            "candidate_live_order_submission_approved",
            "live_order_submission_approved",
            "target_plan_replacement_approved",
            "executor_input_mutation_approved",
            "live_config_mutation_approved",
            "operator_state_mutation_approved",
            "timer_or_service_mutation_approved",
            "production_timer_service_load_approved",
            "remote_sync_approved",
            "repo_stage_change_approved",
        ))
        and control.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bm_control_boundary_readback.v1"
        and control.get("scope") == "real_supervisor_entrypoint_shadow_readback_no_order_only"
        and control.get("live_supervisor_source_unchanged") is True
        and control.get("live_supervisor_loads_candidate_hook") is False
        and control.get("live_config_dir_unchanged") is True
        and control.get("generated_config_under_proof_artifacts") is True
        and control.get("supervisor_entrypoint_invoked") is True
        and control.get("systemd_timer_service_invoked") is False
        and control.get("production_timer_service_loaded_or_modified") is False
        and control.get("remote_sync_performed") is False
        and control.get("remote_execution_performed") is False
        and control.get("candidate_execution_performed") is False
        and control.get("live_order_submission_authorized") is False
        and control.get("executor_input_changed") is False
        and control.get("target_plan_replaced") is False
        and control.get("live_config_changed") is False
        and control.get("operator_state_changed_outside_generated_p9bm_state") is False
        and control.get("timer_state_changed") is False
        and int_zero(control, "orders_submitted")
        and int_zero(control, "orders_canceled")
        and int_zero(control, "fill_count")
        and int_zero(control, "trade_count")
        and matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9bm_non_authorization_matrix.v1"
        and all(authorizations.get(key) is True for key in allowed_true_authorizations)
        and all(
            authorizations.get(key) is False
            for key in (
                "candidate_execution",
                "candidate_live_order_submission",
                "executor_input_mutation",
                "live_config_mutation",
                "live_order_submission",
                "operator_state_mutation",
                "production_timer_service_load",
                "remote_sync",
                "stage_governance_change",
                "target_plan_replacement",
                "timer_or_service_mutation",
            )
        )
        and hook_summary_ready(hook)
        and supervisor_readback_ready(supervisor)
        and position_reference_ready(position)
        and retained_account_plan_fixture_ready(retained_fixture)
        and all(path.exists() for path in paths.values() if str(path))
        and path_exists_and_proof_artifact(paths["generated_no_order_config"])
        and path_exists_and_proof_artifact(paths["supervisor_readback_summary"])
        and path_exists_and_proof_artifact(paths["hook_shadow_readback_summary"])
        and path_exists_and_proof_artifact(paths["position_reference_fixture"])
        and path_exists_and_proof_artifact(paths["retained_account_plan_fixture"])
        and path_exists_and_proof_artifact(paths["control_boundary_readback"])
        and path_exists_and_proof_artifact(paths["non_authorization_matrix"])
        and hook_source.get("sha256") == current_hook_sha256
        and supervisor_source.get("sha256") == current_supervisor_sha256
        and live_config_source.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
    )


def build_owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9BN_DECISION
    record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bn_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "review_p9bm_retained_evidence_sufficiency_for_next_proposal_review_gate_only",
        "decision_effect": "review_p9bm_retained_evidence_only" if approved else "none",
        "retained_evidence_review_approved": approved,
        "p9bm_sufficiency_review_approved": approved,
        "future_proposal_review_gate_discussion_approved": approved,
        "prepare_proposal_approved": False,
        "proposal_execution_approved": False,
        "next_gate_execution_approved": False,
    }
    for key in FALSE_OWNER_KEYS:
        record[key] = False
    return record


def review_boundary(*, review_authorized: bool) -> dict[str, Any]:
    payload = {
        "retained_evidence_review_authorized": review_authorized,
        "p9bm_sufficiency_review_authorized": review_authorized,
        "future_proposal_review_gate_discussion_authorized": review_authorized,
        "allowed_next_gate_must_be_separately_requested": True,
        "candidate_order_authority": "disabled",
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "shadow_only_not_executor",
        "candidate_artifact_sink": "proof_artifacts_only",
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "fills_observed": 0,
        "trade_count": 0,
        "exchange_order_submission": "disabled",
        "executor_consumes_baseline_only": True,
        "candidate_plan_referenced_by_executor": False,
    }
    for key in FALSE_BOUNDARY_KEYS:
        payload[key] = False
    return payload


def build_p9bn(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9bn" / run_id

    paths = {
        "project_profile": resolve_path(args.project_profile),
        "phase9bm": latest_p9bm_summary(args),
        "hook_module": resolve_path(args.hook_module),
        "supervisor": resolve_path(args.supervisor),
        "live_config_dir": resolve_path(args.live_config_dir),
    }
    project_profile = load_optional(paths["project_profile"])
    p9bm = load_optional(paths["phase9bm"])
    p9bm_paths = p9bm_output_paths(p9bm)
    owner_record = load_optional(p9bm_paths["owner_decision_record"])
    control = load_optional(p9bm_paths["control_boundary_readback"])
    matrix = load_optional(p9bm_paths["non_authorization_matrix"])
    hook = load_optional(p9bm_paths["hook_shadow_readback_summary"])
    supervisor = load_optional(p9bm_paths["supervisor_readback_summary"])
    position = load_optional(p9bm_paths["position_reference_fixture"])
    retained_fixture = load_optional(p9bm_paths["retained_account_plan_fixture"])

    hook_sha = file_sha256(paths["hook_module"]) if paths["hook_module"].exists() else ""
    supervisor_sha_before = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_before = tree_sha256(paths["live_config_dir"])
    supervisor_loads_hook = current_supervisor_loads_hook(paths["supervisor"])
    supervisor_sha_after = file_sha256(paths["supervisor"]) if paths["supervisor"].exists() else ""
    live_config_sha_after = tree_sha256(paths["live_config_dir"])

    decision = build_owner_decision_record(args, generated_at)
    source_evidence = {
        "project_profile": evidence_file(paths["project_profile"]),
        "phase9bm_summary": evidence_file(paths["phase9bm"]),
        "phase9bm_owner_decision_record": evidence_file(p9bm_paths["owner_decision_record"]),
        "phase9bm_generated_no_order_config": evidence_file(p9bm_paths["generated_no_order_config"]),
        "phase9bm_supervisor_readback_summary": evidence_file(p9bm_paths["supervisor_readback_summary"]),
        "phase9bm_hook_shadow_readback_summary": evidence_file(p9bm_paths["hook_shadow_readback_summary"]),
        "phase9bm_position_reference_fixture": evidence_file(p9bm_paths["position_reference_fixture"]),
        "phase9bm_retained_account_plan_fixture": evidence_file(
            p9bm_paths["retained_account_plan_fixture"]
        ),
        "phase9bm_control_boundary_readback": evidence_file(p9bm_paths["control_boundary_readback"]),
        "phase9bm_non_authorization_matrix": evidence_file(p9bm_paths["non_authorization_matrix"]),
        "hook_module": evidence_file(paths["hook_module"]),
        "live_supervisor": evidence_file(paths["supervisor"]),
        "live_config_dir": {
            "path": str(paths["live_config_dir"]),
            "exists": paths["live_config_dir"].exists(),
            "sha256": live_config_sha_before,
        },
    }
    evidence_ok = p9bm_retained_evidence_sufficient(
        p9bm,
        owner_record,
        control,
        matrix,
        hook,
        supervisor,
        position,
        retained_fixture,
        p9bm_paths,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    owner_ok = str(args.owner_decision) == APPROVE_P9BN_DECISION
    gates = {
        "owner_decision_p9bn_review_only": owner_ok,
        "project_stage_boundary_preserved": project_profile.get("current_stage")
        == "stage_1_research_readiness_only",
        "p9bm_retained_evidence_sufficient": evidence_ok,
        "p9bm_summary_ready": p9bm.get("status") == "ready"
        and p9bm.get("p9bm_real_timer_path_shadow_readback_ready") is True,
        "p9bm_used_retained_pit_safe_account_fixture": p9bm.get("account_proof_mode")
        == "retained_pit_safe_read_only_fixture",
        "p9bm_supervisor_entrypoint_invoked_no_order": p9bm.get("supervisor_entrypoint_invoked") is True
        and p9bm.get("real_timer_path_shadow_readback_executed") is True
        and int(p9bm.get("orders_submitted") or 0) == 0
        and int(p9bm.get("fill_count") or 0) == 0,
        "p9bm_executor_baseline_only": p9bm.get("executor_consumes_baseline_only") is True
        and p9bm.get("candidate_plan_referenced_by_executor") is False
        and p9bm.get("executor_input_changed") is False,
        "p9bm_candidate_shadow_only": p9bm.get("candidate_shadow_only") is True
        and p9bm.get("candidate_execution_performed") is False,
        "p9bm_no_live_order_or_mutation": p9bm.get("live_order_submission_authorized") is False
        and p9bm.get("target_plan_replaced") is False
        and p9bm.get("live_config_changed") is False
        and p9bm.get("timer_state_changed") is False
        and p9bm.get("remote_sync_performed") is False,
        "current_live_supervisor_not_loading_hook": supervisor_loads_hook is False,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "review_output_under_proof_artifacts": output_under_proof_artifacts(
            proof_root / "owner_review_packet.json"
        ),
        "p9bn_no_proposal_preparation": True,
        "p9bn_no_timer_supervisor_remote_order_execution": True,
    }
    status = "ready" if all(gates.values()) else "blocked"
    ready = status == "ready"
    review_packet = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bn_owner_review_packet.v1",
        "run_id": run_id,
        "reviewed_at_utc": iso_z(generated_at),
        "review_scope": "p9bn_review_p9bm_retained_evidence_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9bm_retained_evidence_sufficient": evidence_ok,
        "sufficient_for_next_proposal_review_gate": ready,
        "allowed_next_gate": P9BO_GATE if ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "review_conclusion": "ready_for_separately_requested_proposal_review_gate_only"
        if ready
        else "blocked",
        **review_boundary(review_authorized=ready),
    }
    checklist = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bn_sufficiency_checklist.v1",
        "run_id": run_id,
        "checks": {
            "p9bm_status_ready": p9bm.get("status") == "ready",
            "p9bm_blockers_empty": not p9bm.get("blockers"),
            "retained_pit_safe_account_fixture": p9bm.get("account_proof_mode")
            == "retained_pit_safe_read_only_fixture",
            "pit_safe_position_reference_fixture_ready": p9bm.get(
                "pit_safe_position_reference_fixture_ready"
            )
            is True,
            "retained_account_plan_fixture_ready": retained_account_plan_fixture_ready(
                retained_fixture
            ),
            "real_supervisor_entrypoint_invoked": p9bm.get("supervisor_entrypoint_invoked")
            is True,
            "supervisor_readback_no_order_ready": supervisor_readback_ready(supervisor),
            "hook_shadow_readback_ready": hook_summary_ready(hook),
            "baseline_only_executor": p9bm.get("executor_consumes_baseline_only") is True,
            "candidate_plan_not_referenced_by_executor": p9bm.get(
                "candidate_plan_referenced_by_executor"
            )
            is False,
            "target_plan_not_replaced": p9bm.get("target_plan_replaced") is False,
            "executor_input_not_mutated": p9bm.get("executor_input_changed") is False,
            "zero_order_cancel_fill_trade_delta": p9bm.get("zero_order_cancel_fill_trade_delta")
            is True,
            "no_live_config_operator_timer_remote_mutation": (
                p9bm.get("live_config_changed") is False
                and p9bm.get("operator_state_changed_outside_generated_p9bm_state") is False
                and p9bm.get("timer_state_changed") is False
                and p9bm.get("remote_sync_performed") is False
                and p9bm.get("remote_execution_performed") is False
            ),
            "proposal_not_prepared_in_p9bn": True,
            "live_order_not_authorized": True,
        },
    }
    matrix_payload = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bn_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "retained_evidence_review": ready,
            "future_proposal_review_gate_discussion": ready,
            "prepare_proposal": False,
            "proposal_execution": False,
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
    control_payload = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bn_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "p9bn_retained_evidence_review_only",
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        **review_boundary(review_authorized=ready),
    }
    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "owner_review_packet": str(proof_root / "owner_review_packet.json"),
        "sufficiency_checklist": str(proof_root / "sufficiency_checklist.json"),
        "non_authorization_matrix": str(proof_root / "non_authorization_matrix.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "p9bn_review_after_p9bm.md"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "review_scope": "p9bn_review_p9bm_retained_evidence_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9bn_owner_gate_ready": ready,
        "p9bm_retained_evidence_sufficient": evidence_ok,
        "sufficient_for_next_proposal_review_gate": ready,
        "eligible_for_future_p9bo_proposal_review_gate_request": ready,
        "allowed_next_gate": P9BO_GATE if ready else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "gates": gates,
        "blockers": [key for key, value in gates.items() if not value],
        "output_files": output_files,
        **review_boundary(review_authorized=ready),
    }
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "owner_review_packet.json", review_packet)
    write_json(proof_root / "sufficiency_checklist.json", checklist)
    write_json(proof_root / "non_authorization_matrix.json", matrix_payload)
    write_json(proof_root / "control_boundary_readback.json", control_payload)
    write_json(root / "summary.json", summary)
    (root / "p9bn_review_after_p9bm.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9BN Review After P9BM",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9BN reviews retained P9BM evidence only. It does not prepare a proposal, execute another readback, enter timer path, invoke the supervisor, sync remote state, execute the candidate, or authorize orders.",
        "",
        "```text",
        f"p9bn_owner_gate_ready = {str(bool(summary['p9bn_owner_gate_ready'])).lower()}",
        f"p9bm_retained_evidence_sufficient = {str(bool(summary['p9bm_retained_evidence_sufficient'])).lower()}",
        f"allowed_next_gate = {summary['allowed_next_gate']}",
        "proposal_preparation_authorized = false",
        "next_gate_execution_authorized = false",
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
    summary, exit_code = build_p9bn(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    print(f"allowed_next_gate={summary['allowed_next_gate']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
