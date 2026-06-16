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

from enhengclaw.live_trading.dth60_observe_only_shadow_hook import (  # noqa: E402
    ObserveOnlyShadowHookConfig,
    run_observe_only_shadow_hook,
)
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
    HOOK_MODULE,
    LIVE_CONFIG_DIR,
    PROJECT_PROFILE,
    SUPERVISOR_PATH,
    source_output_path,
    tree_sha256,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9w_default_off_timer_path_dry_load_owner_gate import (  # noqa: E402
    P9X_GATE,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9x_default_off_timer_path_dry_load.v1"
APPROVE_P9X_DECISION = "approve_p9x_execute_default_off_timer_path_dry_load_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9x_default_off_timer_path_dry_load"
PHASE9W_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9w_default_off_timer_path_dry_load_owner_gate"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute P9X as a default-off timer-path dry-load proof only. "
            "This writes proof_artifacts evidence, keeps candidate execution "
            "disabled, preserves baseline-only executor input, does not invoke "
            "the live timer service or supervisor, and submits zero orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9w-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9X_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:authorize_p9x")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def zero_orders_fills(payload: dict[str, Any]) -> bool:
    return int_zero(payload, "orders_submitted") and int_zero(payload, "fill_count")


def no_live_mutation(payload: dict[str, Any]) -> bool:
    return (
        payload.get("live_config_changed") is False
        and payload.get("operator_state_changed") is False
        and payload.get("timer_state_changed") is False
    )


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = args.owner_decision == APPROVE_P9X_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9x_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "execute_default_off_timer_path_dry_load_only",
        "decision_effect": "execute_local_proof_artifacts_default_off_timer_path_dry_load" if approved else "none",
        "default_off_timer_path_dry_load_execution_approved": approved,
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


def p9w_execution_gate_ready(summary: dict[str, Any], gate: dict[str, Any], matrix: dict[str, Any]) -> bool:
    required = dict(gate.get("required_future_boundaries") or {})
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        summary.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9w_default_off_timer_path_dry_load_owner_gate.v1"
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9w_owner_gate_ready") is True
        and summary.get("eligible_for_future_p9x_execution_gate") is True
        and summary.get("allowed_next_gate") == P9X_GATE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("default_off_timer_path_dry_load_execution_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("live_config_mutation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("supervisor_run_authorized") is False
        and summary.get("entered_timer_path") is False
        and summary.get("dry_load_executed") is False
        and summary.get("candidate_execution_enabled") is False
        and zero_orders_fills(summary)
        and gate.get("contract_version") == "hv_balanced_dth60_coinglass_phase9w_execution_discussion_owner_gate.v1"
        and gate.get("gate_status") == "ready"
        and gate.get("eligible_for_future_p9x_execution_gate") is True
        and gate.get("allowed_next_gate") == P9X_GATE
        and gate.get("default_off_timer_path_dry_load_execution_authorized_in_p9w") is False
        and gate.get("candidate_execution_authorized_in_p9w") is False
        and gate.get("live_order_submission_authorized_in_p9w") is False
        and required.get("default_off_required") is True
        and required.get("proof_artifacts_only") is True
        and required.get("baseline_only_executor_input") is True
        and required.get("candidate_execution_forbidden") is True
        and required.get("live_order_submission_forbidden") is True
        and required.get("target_plan_replacement_forbidden") is True
        and required.get("executor_input_mutation_forbidden") is True
        and required.get("live_config_mutation_forbidden") is True
        and required.get("remote_sync_forbidden") is True
        and required.get("supervisor_execution_forbidden") is True
        and required.get("timer_service_enable_or_invoke_forbidden") is True
        and int(required.get("orders_submitted_must_equal", -1)) == 0
        and int(required.get("fill_count_must_equal", -1)) == 0
        and matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9w_non_authorization_matrix.v1"
        and authorizations.get("future_p9x_execution_gate_request") is True
        and authorizations.get("execute_default_off_timer_path_dry_load_in_p9w") is False
        and authorizations.get("candidate_execution") is False
        and authorizations.get("live_order_submission") is False
        and authorizations.get("live_timer_path_load") is False
        and authorizations.get("executor_input_mutation") is False
        and authorizations.get("live_config_mutation") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("supervisor_run") is False
    )


def build_fixture_plans(proof_root: Path) -> dict[str, Path]:
    input_root = proof_root / "input_plans"
    baseline = input_root / "baseline_target_plan.json"
    executor = input_root / "executor_input_target_plan.json"
    candidate = input_root / "candidate_shadow_plan.json"
    baseline_payload = {
        "contract_version": "hv_balanced_dth60_phase9x_fixture_plan.v1",
        "plan_type": "baseline_target_plan",
        "generated_for": "default_off_timer_path_dry_load",
        "positions": [
            {"symbol": "BTCUSDT", "target_weight": 0.10},
            {"symbol": "ETHUSDT", "target_weight": -0.05},
        ],
        "risk_inputs": {"gross_cap": 0.15, "execution_target_source": "baseline_only"},
    }
    candidate_payload = {
        "contract_version": "hv_balanced_dth60_phase9x_fixture_plan.v1",
        "plan_type": "candidate_shadow_plan",
        "generated_for": "default_off_timer_path_dry_load",
        "positions": [
            {"symbol": "BTCUSDT", "target_weight": 0.07},
            {"symbol": "ETHUSDT", "target_weight": -0.02},
        ],
        "risk_inputs": {"gross_cap": 0.15, "execution_target_source": "candidate_shadow_only"},
    }
    write_json(baseline, baseline_payload)
    write_json(executor, baseline_payload)
    write_json(candidate, candidate_payload)
    return {"baseline": baseline, "executor": executor, "candidate": candidate}


def build_phase9x(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = root / "proof_artifacts" / "p9x" / run_id

    project_profile = load_optional(resolve_path(args.project_profile))
    phase9w_path = (
        resolve_path(args.phase9w_summary)
        if str(args.phase9w_summary).strip()
        else latest_match(PHASE9W_PARENT, "*/summary.json")
    )
    phase9w_summary = load_optional(phase9w_path)
    phase9w_gate_path = source_output_path(phase9w_summary, "dry_load_execution_owner_gate")
    phase9w_matrix_path = source_output_path(phase9w_summary, "non_authorization_matrix")
    phase9w_gate = load_optional(phase9w_gate_path)
    phase9w_matrix = load_optional(phase9w_matrix_path)
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)
    live_config_sha_before = tree_sha256(live_config_dir)
    supervisor_sha_before = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    hook_sha = file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else ""
    supervisor_loads = current_supervisor_loads_hook(supervisor_path)
    p9w_source = dict(phase9w_summary.get("source_evidence") or {})
    p9w_hook = dict(p9w_source.get("hook_module") or {})
    p9w_supervisor = dict(p9w_source.get("live_supervisor") or {})
    p9w_config = dict(p9w_source.get("live_config_dir") or {})
    decision = owner_decision_record(args, generated_at)

    pre_gates = {
        "owner_decision_p9x_execute_default_off_dry_load_only": args.owner_decision == APPROVE_P9X_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9w_owner_gate_ready": p9w_execution_gate_ready(phase9w_summary, phase9w_gate, phase9w_matrix),
        "p9w_allows_future_p9x_gate_request": phase9w_summary.get("eligible_for_future_p9x_execution_gate") is True,
        "p9w_did_not_execute_dry_load": phase9w_summary.get("dry_load_executed") is False,
        "p9w_did_not_authorize_candidate_execution": phase9w_summary.get("candidate_execution_authorized") is False,
        "p9w_did_not_authorize_live_orders": phase9w_summary.get("live_order_submission_authorized") is False,
        "current_live_supervisor_not_loading_hook": supervisor_loads is False,
        "current_hook_matches_p9w_source": p9w_hook.get("sha256") == hook_sha,
        "current_supervisor_matches_p9w_source": p9w_supervisor.get("sha256") == supervisor_sha_before,
        "current_live_config_matches_p9w_source": p9w_config.get("sha256") == live_config_sha_before,
    }
    blockers = [key for key, value in pre_gates.items() if not value]

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
    }
    write_json(root / "owner_decision_record.json", decision)

    if blockers:
        supervisor_sha_after = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
        live_config_sha_after = tree_sha256(live_config_dir)
        control = {
            "contract_version": "hv_balanced_dth60_coinglass_phase9x_control_boundary_readback.v1",
            "run_id": run_id,
            "scope": "pre_execution_gate_failed_no_default_off_timer_path_dry_load",
            "live_supervisor_sha256_before": supervisor_sha_before,
            "live_supervisor_sha256_after": supervisor_sha_after,
            "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
            "live_config_dir_sha256_before": live_config_sha_before,
            "live_config_dir_sha256_after": live_config_sha_after,
            "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
            "live_supervisor_loads_candidate_hook": supervisor_loads,
            "entered_timer_path_dry_load_harness": False,
            "entered_live_timer_path": False,
            "default_off_timer_path_dry_load_executed": False,
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
        write_json(proof_root / "control_boundary_readback.json", control)
        summary = {
            "contract_version": CONTRACT_VERSION,
            "run_id": run_id,
            "generated_at_utc": iso_z(generated_at),
            "status": "blocked",
            "blockers": blockers,
            "owner_decision": decision,
            "default_off_timer_path_dry_load_ready": False,
            "default_off_timer_path_dry_load_execution_authorized": False,
            "default_off_timer_path_dry_load_executed": False,
            "entered_timer_path_dry_load_harness": False,
            "entered_live_timer_path": False,
            "candidate_execution_enabled": False,
            "live_order_submission_authorized": False,
            "orders_submitted": 0,
            "fill_count": 0,
            "gates": pre_gates,
            "source_evidence": {
                "phase9w_summary": evidence_file(phase9w_path),
                "phase9w_dry_load_execution_owner_gate": evidence_file(phase9w_gate_path),
                "phase9w_non_authorization_matrix": evidence_file(phase9w_matrix_path),
                "hook_module": evidence_file(hook_path),
                "live_supervisor": evidence_file(supervisor_path),
                "live_config_dir": {"path": str(live_config_dir), "exists": live_config_dir.exists(), "sha256": live_config_sha_before},
            },
            "proof_root": str(proof_root),
            "output_files": output_files,
        }
        write_json(root / "summary.json", summary)
        return summary, 2

    plan_paths = build_fixture_plans(proof_root)
    dry_load_config = ObserveOnlyShadowHookConfig(
        enabled=False,
        mode="observe_only",
        artifact_sink="proof_artifacts_only",
        output_root=proof_root / "default_off_hook_disabled_output",
        candidate_order_authority="disabled",
        candidate_live_order_submission_authorized=False,
        execution_target_source="baseline_only",
        candidate_overlay_execution_path="excluded",
    )
    hook_summary = run_observe_only_shadow_hook(
        config=dry_load_config,
        baseline_target_plan_path=plan_paths["baseline"],
        executor_input_plan_path=plan_paths["executor"],
        candidate_shadow_plan_path=plan_paths["candidate"],
        supervisor_context={
            "phase": "P9X",
            "dry_load_mode": "default_off_timer_path_dry_load_harness_not_live_timer_service",
            "entered_timer_path_dry_load_harness": True,
            "entered_live_timer_path": False,
            "live_timer_service_enabled_or_invoked": False,
            "supervisor_run_for_execution": False,
        },
        run_id=f"{run_id}-default-off-timer-path-dry-load",
        now=generated_at,
    )
    write_json(proof_root / "disabled_hook_readback_summary.json", hook_summary)

    baseline_sha = file_sha256(plan_paths["baseline"])
    executor_sha = file_sha256(plan_paths["executor"])
    candidate_sha = file_sha256(plan_paths["candidate"])
    executor_input_hash_equals_baseline = bool(executor_sha) and executor_sha == baseline_sha
    candidate_shadow_hash_differs_from_executor = bool(candidate_sha) and candidate_sha != executor_sha
    default_off_config_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9x_default_off_config_readback.v1",
        "run_id": run_id,
        "dry_load_mode": "default_off_timer_path_dry_load_harness_not_live_timer_service",
        "default_off_required": True,
        "hook_config_enabled": dry_load_config.enabled,
        "mode": dry_load_config.mode,
        "artifact_sink": dry_load_config.artifact_sink,
        "candidate_execution_enabled": False,
        "candidate_order_authority": dry_load_config.candidate_order_authority,
        "candidate_live_order_submission_authorized": dry_load_config.candidate_live_order_submission_authorized,
        "execution_target_source": dry_load_config.execution_target_source,
        "candidate_overlay_execution_path": dry_load_config.candidate_overlay_execution_path,
        "proof_artifacts_only": output_under_proof_artifacts(proof_root),
        "entered_timer_path_dry_load_harness": True,
        "entered_live_timer_path": False,
        "live_timer_service_enabled_or_invoked": False,
        "supervisor_run_for_execution": False,
        "remote_sync_performed": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    executor_input_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9x_executor_input_readback.v1",
        "run_id": run_id,
        "execution_target_source": "baseline_only",
        "baseline_target_plan": evidence_file(plan_paths["baseline"]),
        "executor_input_plan": evidence_file(plan_paths["executor"]),
        "candidate_shadow_plan": evidence_file(plan_paths["candidate"]),
        "executor_input_hash_equals_baseline": executor_input_hash_equals_baseline,
        "candidate_shadow_hash_differs_from_executor": candidate_shadow_hash_differs_from_executor,
        "candidate_plan_referenced_by_executor": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    write_json(proof_root / "default_off_config_readback.json", default_off_config_readback)
    write_json(proof_root / "executor_input_readback.json", executor_input_readback)
    dry_load_manifest = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9x_dry_load_execution_manifest.v1",
        "run_id": run_id,
        "default_off_timer_path_dry_load_executed": True,
        "dry_load_mode": "default_off_timer_path_dry_load_harness_not_live_timer_service",
        "dry_load_source": "retained_p9w_owner_gate_plus_local_fresh_fixture_plans",
        "source_phase9w_summary": evidence_file(phase9w_path),
        "default_off_config_readback": evidence_file(proof_root / "default_off_config_readback.json"),
        "disabled_hook_readback_summary": evidence_file(proof_root / "disabled_hook_readback_summary.json"),
        "executor_input_readback": evidence_file(proof_root / "executor_input_readback.json"),
        "entered_timer_path_dry_load_harness": True,
        "entered_live_timer_path": False,
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "supervisor_run_invoked": False,
        "remote_sync_performed": False,
        "candidate_execution_enabled": False,
        "execution_target_source": "baseline_only",
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    write_json(proof_root / "dry_load_execution_manifest.json", dry_load_manifest)

    supervisor_sha_after = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    live_config_sha_after = tree_sha256(live_config_dir)
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9x_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "local_proof_artifacts_default_off_timer_path_dry_load_only",
        "live_supervisor": evidence_file(supervisor_path),
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "entered_timer_path_dry_load_harness": True,
        "entered_live_timer_path": False,
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "ran_supervisor": False,
        "remote_control_plane_touched": False,
        "candidate_execution_enabled": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }
    write_json(proof_root / "control_boundary_readback.json", control)

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "dry_load_execution_manifest": str(proof_root / "dry_load_execution_manifest.json"),
        "default_off_config_readback": str(proof_root / "default_off_config_readback.json"),
        "disabled_hook_readback_summary": str(proof_root / "disabled_hook_readback_summary.json"),
        "executor_input_readback": str(proof_root / "executor_input_readback.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "baseline_target_plan": str(plan_paths["baseline"]),
        "executor_input_plan": str(plan_paths["executor"]),
        "candidate_shadow_plan": str(plan_paths["candidate"]),
    }
    output_paths_under_proof = all(
        output_under_proof_artifacts(resolve_path(path))
        for key, path in output_files.items()
        if key not in {"summary", "owner_decision_record"}
    )
    hook_summary_ready = (
        hook_summary.get("status") == "ready"
        and hook_summary.get("hook_enabled") is False
        and hook_summary.get("executor_consumes_baseline_only") is True
        and hook_summary.get("candidate_artifacts_written_count") == 0
        and hook_summary.get("candidate_plan_referenced_by_executor") is False
        and zero_orders_fills(hook_summary)
        and no_live_mutation(hook_summary)
    )
    gates = {
        **pre_gates,
        "dry_load_outputs_under_proof_artifacts": output_paths_under_proof,
        "dry_load_mode_not_live_timer_service": default_off_config_readback.get("dry_load_mode")
        == "default_off_timer_path_dry_load_harness_not_live_timer_service",
        "default_off_config_loaded": default_off_config_readback.get("hook_config_enabled") is False,
        "entered_timer_path_dry_load_harness": default_off_config_readback.get("entered_timer_path_dry_load_harness")
        is True,
        "entered_live_timer_path_false": default_off_config_readback.get("entered_live_timer_path") is False,
        "candidate_execution_disabled": default_off_config_readback.get("candidate_execution_enabled") is False,
        "artifact_sink_proof_artifacts_only": default_off_config_readback.get("artifact_sink") == "proof_artifacts_only",
        "candidate_order_authority_disabled": default_off_config_readback.get("candidate_order_authority") == "disabled",
        "candidate_live_order_submission_authorized_false": default_off_config_readback.get(
            "candidate_live_order_submission_authorized"
        )
        is False,
        "execution_target_source_baseline_only": default_off_config_readback.get("execution_target_source")
        == "baseline_only",
        "disabled_hook_readback_ready": hook_summary_ready,
        "disabled_hook_writes_zero_candidate_artifacts": hook_summary.get("candidate_artifacts_written_count") == 0,
        "baseline_target_plan_byte_for_byte_unchanged": hook_summary.get(
            "baseline_target_plan_byte_for_byte_unchanged"
        )
        is True,
        "executor_input_hash_unchanged": hook_summary.get("executor_input_plan_hash_unchanged") is True,
        "executor_input_hash_equals_baseline": executor_input_hash_equals_baseline,
        "executor_consumes_baseline_only": hook_summary.get("executor_consumes_baseline_only") is True,
        "candidate_shadow_hash_differs_from_executor": candidate_shadow_hash_differs_from_executor,
        "candidate_plan_not_referenced_by_executor": executor_input_readback.get("candidate_plan_referenced_by_executor")
        is False,
        "target_plan_not_replaced": executor_input_readback.get("target_plan_replaced") is False,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "live_timer_service_not_enabled_or_invoked": default_off_config_readback.get(
            "live_timer_service_enabled_or_invoked"
        )
        is False,
        "supervisor_not_run_for_execution": default_off_config_readback.get("supervisor_run_for_execution") is False,
        "no_remote_sync_in_p9x": default_off_config_readback.get("remote_sync_performed") is False,
        "no_live_timer_path_load_in_p9x": control.get("live_timer_path_loaded") is False,
        "no_executor_input_mutation_in_p9x": control.get("executor_input_mutated") is False,
        "no_target_plan_replacement_in_p9x": control.get("target_plan_replaced") is False,
        "no_live_mutation_in_p9x": no_live_mutation(control),
        "zero_orders_fills_in_p9x": zero_orders_fills(control),
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    ready = status == "ready"
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": status,
        "blockers": blockers,
        "owner_decision": decision,
        "source_evidence": {
            "phase9w_summary": evidence_file(phase9w_path),
            "phase9w_dry_load_execution_owner_gate": evidence_file(phase9w_gate_path),
            "phase9w_non_authorization_matrix": evidence_file(phase9w_matrix_path),
            "hook_module": evidence_file(hook_path),
            "live_supervisor": evidence_file(supervisor_path),
            "live_config_dir": {"path": str(live_config_dir), "exists": live_config_dir.exists(), "sha256": live_config_sha_before},
        },
        "default_off_timer_path_dry_load_ready": ready,
        "default_off_timer_path_dry_load_execution_authorized": decision.get(
            "default_off_timer_path_dry_load_execution_approved"
        )
        is True,
        "default_off_timer_path_dry_load_executed": True,
        "dry_load_mode": "default_off_timer_path_dry_load_harness_not_live_timer_service",
        "dry_load_outputs_under_proof_artifacts": output_paths_under_proof,
        "entered_timer_path_dry_load_harness": True,
        "entered_live_timer_path": False,
        "default_off_config_loaded": default_off_config_readback.get("hook_config_enabled") is False,
        "default_off_hook_enabled": False,
        "candidate_execution_enabled": False,
        "disabled_hook_readback_ready": hook_summary_ready,
        "disabled_hook_candidate_artifacts_written_count": int(hook_summary.get("candidate_artifacts_written_count") or 0),
        "baseline_target_plan_byte_for_byte_unchanged": hook_summary.get("baseline_target_plan_byte_for_byte_unchanged"),
        "executor_input_hash_unchanged": hook_summary.get("executor_input_plan_hash_unchanged"),
        "executor_input_hash_equals_baseline": executor_input_hash_equals_baseline,
        "executor_consumes_baseline_only": hook_summary.get("executor_consumes_baseline_only"),
        "candidate_shadow_hash_differs_from_executor": candidate_shadow_hash_differs_from_executor,
        "candidate_plan_referenced_by_executor": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "eligible_for_live_timer_path_load": False,
        "eligible_for_live_order_submission": False,
        "eligible_for_stage_governance_change": False,
        "timer_hook_implementation_authorized": False,
        "hook_deployment_authorized": False,
        "timer_path_load_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "remote_sync_authorized": False,
        "supervisor_run_authorized": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "excluded",
        "candidate_artifact_sink": "proof_artifacts_only",
        "live_supervisor_loads_candidate_hook": supervisor_loads,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "live_timer_path_loaded": False,
        "live_timer_service_enabled_or_invoked": False,
        "ran_supervisor": False,
        "timer_path_invoked": False,
        "remote_execution_performed": False,
        "remote_control_plane_touched": False,
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
        "recommended_next_gate": "P9Y_owner_review_after_p9x_default_off_dry_load_if_separately_requested",
        "proof_root": str(proof_root),
        "gates": gates,
        "output_files": output_files,
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if ready else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9x(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
