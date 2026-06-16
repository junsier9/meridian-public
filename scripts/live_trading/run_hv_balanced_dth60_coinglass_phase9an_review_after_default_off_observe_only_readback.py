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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9am_default_off_readback_execution import (  # noqa: E402
    P9AN_GATE,
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
    write_json,
    zero_orders_fills,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    HOOK_MODULE,
    LIVE_CONFIG_DIR,
    PROJECT_PROFILE,
    SUPERVISOR_PATH,
    source_output_path,
    tree_sha256,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9an_review_after_default_off_observe_only_readback.v1"
APPROVE_P9AN_DECISION = "approve_p9an_review_default_off_observe_only_readback_sufficiency_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9an_review_after_default_off_observe_only_readback"
PHASE9AM_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9am_default_off_readback_execution"
P9AO_GATE = "P9AO_allow_define_next_gate_scope_after_p9am_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build P9AN as a review-only owner gate after P9AM. P9AN checks "
            "whether the retained default-off / observe-only readback is "
            "sufficient for a separate next owner gate. It does not define "
            "that next scope, execute any next gate, load timer paths, invoke "
            "the supervisor, mutate live state, remote sync, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9am-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AN_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:allow_p9an_review_after_default_off_observe_only_readback_only",
    )
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


def proof_file_paths(p9am: dict[str, Any]) -> dict[str, Path]:
    return {
        "dry_load_execution_manifest": source_output_path(p9am, "dry_load_execution_manifest"),
        "default_off_config_readback": source_output_path(p9am, "default_off_config_readback"),
        "observe_only_shadow_readback_summary": source_output_path(p9am, "observe_only_shadow_readback_summary"),
        "executor_input_readback": source_output_path(p9am, "executor_input_readback"),
        "control_boundary_readback": source_output_path(p9am, "control_boundary_readback"),
        "baseline_target_plan": source_output_path(p9am, "baseline_target_plan"),
        "executor_input_plan": source_output_path(p9am, "executor_input_plan"),
        "candidate_shadow_plan": source_output_path(p9am, "candidate_shadow_plan"),
    }


def p9am_summary_ready(
    p9am: dict[str, Any],
    *,
    current_hook_sha256: str,
    current_supervisor_sha256: str,
    current_live_config_sha256: str,
    current_supervisor_loads_candidate_hook: bool,
) -> bool:
    source = dict(p9am.get("source_evidence") or {})
    hook = dict(source.get("hook_module") or {})
    supervisor = dict(source.get("live_supervisor") or {})
    live_config = dict(source.get("live_config_dir") or {})
    owner = dict(p9am.get("owner_decision") or {})
    gates = dict(p9am.get("gates") or {})
    required_false = (
        "eligible_for_timer_hook_implementation",
        "eligible_for_hook_deployment",
        "eligible_for_live_timer_path_load",
        "eligible_for_supervisor_invocation",
        "eligible_for_remote_sync",
        "eligible_for_live_order_submission",
        "eligible_for_stage_governance_change",
        "timer_hook_implementation_authorized",
        "hook_deployment_authorized",
        "timer_path_load_authorized",
        "supervisor_invocation_authorized",
        "remote_sync_authorized",
        "candidate_execution_authorized",
        "live_order_submission_authorized",
        "target_plan_replacement_authorized",
        "executor_input_mutation_authorized",
        "live_config_mutation_authorized",
        "operator_state_mutation_authorized",
        "timer_or_service_mutation_authorized",
        "candidate_live_order_submission_authorized",
        "live_supervisor_loads_candidate_hook",
        "live_timer_path_loaded",
        "live_timer_service_enabled_or_invoked",
        "entered_live_timer_path",
        "ran_supervisor",
        "timer_path_invoked",
        "remote_execution_performed",
        "remote_control_plane_touched",
        "candidate_execution_performed",
        "wrote_live_hook_config",
        "implemented_hook",
        "deployed_hook",
        "loaded_hook",
        "target_plan_replaced",
        "executor_input_changed",
    )
    required_gates = (
        "owner_decision_p9am_execute_readback_only",
        "project_stage_boundary_preserved",
        "p9al_readback_owner_gate_ready",
        "p9al_allows_p9am_only",
        "p9al_did_not_execute_readback",
        "current_live_supervisor_not_loading_hook",
        "current_hook_hash_matches_p9al_source",
        "current_supervisor_hash_matches_p9al_source",
        "current_live_config_hash_matches_p9al_source",
        "dry_load_output_root_under_proof_artifacts",
        "dry_load_outputs_under_proof_artifacts",
        "dry_load_mode_not_live_timer_service",
        "default_off_config_loaded",
        "observe_only_shadow_writer_enabled_in_proof_harness",
        "entered_timer_path_dry_load_harness",
        "entered_live_timer_path_false",
        "candidate_execution_not_authorized",
        "artifact_sink_proof_artifacts_only",
        "candidate_order_authority_disabled",
        "candidate_live_order_submission_authorized_false",
        "execution_target_source_baseline_only",
        "observe_only_shadow_readback_ready",
        "candidate_shadow_artifacts_written",
        "candidate_artifacts_under_proof_artifacts_only",
        "baseline_target_plan_byte_for_byte_unchanged",
        "executor_input_hash_unchanged",
        "executor_input_hash_equals_baseline",
        "executor_consumes_baseline_only",
        "candidate_shadow_hash_differs_from_executor",
        "candidate_plan_not_referenced_by_executor",
        "target_plan_not_replaced",
        "live_supervisor_source_unchanged",
        "live_config_dir_unchanged",
        "live_timer_service_not_enabled_or_invoked",
        "supervisor_not_run_for_execution",
        "no_remote_sync_in_p9am",
        "no_live_timer_path_load_in_p9am",
        "no_candidate_execution_in_p9am",
        "no_executor_input_mutation_in_p9am",
        "no_target_plan_replacement_in_p9am",
        "no_live_mutation_in_p9am",
        "zero_orders_fills_in_p9am",
    )
    return (
        p9am.get("contract_version") == "hv_balanced_dth60_coinglass_phase9am_default_off_readback_execution.v1"
        and p9am.get("status") == "ready"
        and not p9am.get("blockers")
        and p9am.get("dry_load_readback_scope")
        == "owner_gated_default_off_observe_only_timer_path_dry_load_readback_execution_only"
        and p9am.get("p9am_default_off_observe_only_readback_ready") is True
        and p9am.get("default_off_observe_only_readback_execution_authorized") is True
        and p9am.get("executed_default_off_observe_only_readback") is True
        and p9am.get("dry_load_readback_executed") is True
        and p9am.get("dry_load_mode")
        == "default_off_observe_only_timer_path_readback_harness_not_live_timer_service"
        and p9am.get("dry_load_outputs_under_proof_artifacts") is True
        and p9am.get("default_off_config_loaded") is True
        and p9am.get("default_off_hook_enabled") is False
        and p9am.get("observe_only_shadow_writer_enabled_in_proof_harness") is True
        and p9am.get("observe_only_shadow_readback_ready") is True
        and int(p9am.get("candidate_shadow_artifacts_written_count") or 0) > 0
        and p9am.get("candidate_artifacts_under_proof_artifacts_only") is True
        and p9am.get("baseline_target_plan_byte_for_byte_unchanged") is True
        and p9am.get("executor_input_hash_unchanged") is True
        and p9am.get("executor_input_hash_equals_baseline") is True
        and p9am.get("executor_consumes_baseline_only") is True
        and p9am.get("candidate_shadow_hash_differs_from_executor") is True
        and p9am.get("candidate_plan_referenced_by_executor") is False
        and p9am.get("eligible_for_owner_p9an_review") is True
        and p9am.get("recommended_next_gate") == P9AN_GATE
        and p9am.get("candidate_order_authority") == "disabled"
        and p9am.get("execution_target_source") == "baseline_only"
        and p9am.get("candidate_overlay_execution_path") == "excluded"
        and p9am.get("candidate_artifact_sink") == "proof_artifacts_only"
        and p9am.get("live_supervisor_source_unchanged") is True
        and p9am.get("live_config_dir_unchanged") is True
        and p9am.get("entered_timer_path_dry_load_harness") is True
        and no_live_mutation(p9am)
        and zero_orders_fills(p9am)
        and owner.get("decision") == "approve_p9am_execute_default_off_observe_only_timer_path_dry_load_readback_only"
        and owner.get("default_off_observe_only_readback_execution_approved") is True
        and owner.get("candidate_shadow_artifact_write_approved_under_proof_artifacts") is True
        and owner.get("candidate_execution_approved") is False
        and owner.get("candidate_live_order_submission_approved") is False
        and owner.get("timer_hook_implementation_approved") is False
        and owner.get("hook_deployment_approved") is False
        and owner.get("live_timer_path_load_approved") is False
        and owner.get("production_timer_service_load_approved") is False
        and owner.get("live_order_submission_approved") is False
        and owner.get("target_plan_replacement_approved") is False
        and owner.get("executor_input_mutation_approved") is False
        and owner.get("live_config_mutation_approved") is False
        and owner.get("operator_state_mutation_approved") is False
        and owner.get("timer_or_service_mutation_approved") is False
        and owner.get("remote_sync_approved") is False
        and owner.get("supervisor_invocation_approved") is False
        and owner.get("supervisor_run_approved") is False
        and owner.get("repo_stage_change_approved") is False
        and hook.get("sha256") == current_hook_sha256
        and supervisor.get("sha256") == current_supervisor_sha256
        and live_config.get("sha256") == current_live_config_sha256
        and current_supervisor_loads_candidate_hook is False
        and all(p9am.get(key) is False for key in required_false)
        and all(gates.get(key) is True for key in required_gates)
    )


def proof_payloads_ready(
    *,
    paths: dict[str, Path],
    dry_load_manifest: dict[str, Any],
    default_config: dict[str, Any],
    shadow_summary: dict[str, Any],
    executor_readback: dict[str, Any],
    control_readback: dict[str, Any],
) -> dict[str, bool]:
    output_files_exist = all(path.exists() and path.is_file() for path in paths.values())
    output_files_under_proof_artifacts = all(output_under_proof_artifacts(path) for path in paths.values())
    dry_load_manifest_ready = (
        dry_load_manifest.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9am_dry_load_execution_manifest.v1"
        and dry_load_manifest.get("executed_default_off_observe_only_readback") is True
        and dry_load_manifest.get("dry_load_readback_executed") is True
        and dry_load_manifest.get("dry_load_mode")
        == "default_off_observe_only_timer_path_readback_harness_not_live_timer_service"
        and dry_load_manifest.get("default_off_hook_enabled_in_live_config") is False
        and dry_load_manifest.get("observe_only_shadow_writer_enabled_in_proof_harness") is True
        and dry_load_manifest.get("entered_timer_path_dry_load_harness") is True
        and dry_load_manifest.get("entered_live_timer_path") is False
        and dry_load_manifest.get("live_timer_path_loaded") is False
        and dry_load_manifest.get("live_timer_service_enabled_or_invoked") is False
        and dry_load_manifest.get("supervisor_run_invoked") is False
        and dry_load_manifest.get("remote_sync_performed") is False
        and dry_load_manifest.get("candidate_execution_authorized") is False
        and dry_load_manifest.get("candidate_execution_performed") is False
        and dry_load_manifest.get("execution_target_source") == "baseline_only"
        and dry_load_manifest.get("candidate_order_authority") == "disabled"
        and dry_load_manifest.get("candidate_live_order_submission_authorized") is False
        and zero_orders_fills(dry_load_manifest)
    )
    default_config_ready = (
        default_config.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9am_default_off_config_readback.v1"
        and default_config.get("default_off_required") is True
        and default_config.get("hook_config_enabled_default") is False
        and default_config.get("observe_only_shadow_writer_enabled_in_proof_harness") is True
        and default_config.get("mode") == "observe_only"
        and default_config.get("artifact_sink") == "proof_artifacts_only"
        and default_config.get("candidate_execution_authorized") is False
        and default_config.get("candidate_order_authority") == "disabled"
        and default_config.get("candidate_live_order_submission_authorized") is False
        and default_config.get("candidate_overlay_execution_path") == "excluded"
        and default_config.get("execution_target_source") == "baseline_only"
        and default_config.get("proof_artifacts_only") is True
        and default_config.get("entered_timer_path_dry_load_harness") is True
        and default_config.get("entered_live_timer_path") is False
        and default_config.get("live_timer_service_enabled_or_invoked") is False
        and default_config.get("supervisor_run_for_execution") is False
        and default_config.get("remote_sync_performed") is False
        and zero_orders_fills(default_config)
    )
    shadow_summary_ready = (
        shadow_summary.get("contract_version") == "hv_balanced_dth60_observe_only_shadow_hook.v1"
        and shadow_summary.get("status") == "ready"
        and not shadow_summary.get("blockers")
        and shadow_summary.get("hook_enabled") is True
        and shadow_summary.get("artifact_sink") == "proof_artifacts_only"
        and shadow_summary.get("candidate_order_authority") == "disabled"
        and shadow_summary.get("candidate_live_order_submission_authorized") is False
        and shadow_summary.get("candidate_overlay_execution_path") == "excluded"
        and shadow_summary.get("execution_target_source") == "baseline_only"
        and int(shadow_summary.get("candidate_artifacts_written_count") or 0) > 0
        and shadow_summary.get("candidate_artifacts_under_proof_artifacts_only") is True
        and shadow_summary.get("baseline_target_plan_byte_for_byte_unchanged") is True
        and shadow_summary.get("executor_input_plan_hash_unchanged") is True
        and shadow_summary.get("executor_input_plan_hash_equals_baseline") is True
        and shadow_summary.get("executor_consumes_baseline_only") is True
        and shadow_summary.get("candidate_plan_referenced_by_executor") is False
        and shadow_summary.get("candidate_shadow_plan_sha256") not in {
            "",
            shadow_summary.get("executor_input_plan_sha256_after_hook"),
        }
        and shadow_summary.get("deployed_hook") is False
        and shadow_summary.get("ran_supervisor") is False
        and shadow_summary.get("timer_path_invoked") is False
        and no_live_mutation(shadow_summary)
        and zero_orders_fills(shadow_summary)
    )
    executor_hashes_match = (
        dict(executor_readback.get("baseline_target_plan") or {}).get("sha256")
        == dict(executor_readback.get("executor_input_plan") or {}).get("sha256")
    )
    candidate_hash_differs = (
        dict(executor_readback.get("candidate_shadow_source_plan") or {}).get("sha256")
        not in {
            "",
            dict(executor_readback.get("executor_input_plan") or {}).get("sha256"),
        }
    )
    candidate_artifact_paths = [Path(path) for path in executor_readback.get("candidate_shadow_artifact_paths") or []]
    candidate_artifact_paths_under_proof = bool(candidate_artifact_paths) and all(
        output_under_proof_artifacts(path) for path in candidate_artifact_paths
    )
    executor_readback_ready = (
        executor_readback.get("contract_version") == "hv_balanced_dth60_coinglass_phase9am_executor_input_readback.v1"
        and dict(executor_readback.get("baseline_target_plan") or {}).get("exists") is True
        and dict(executor_readback.get("executor_input_plan") or {}).get("exists") is True
        and dict(executor_readback.get("candidate_shadow_source_plan") or {}).get("exists") is True
        and executor_readback.get("executor_input_hash_equals_baseline") is True
        and executor_hashes_match
        and executor_readback.get("candidate_shadow_hash_differs_from_executor") is True
        and candidate_hash_differs
        and int(executor_readback.get("candidate_shadow_artifacts_written_count") or 0) > 0
        and candidate_artifact_paths_under_proof
        and executor_readback.get("candidate_plan_referenced_by_executor") is False
        and executor_readback.get("target_plan_replaced") is False
        and executor_readback.get("executor_input_changed") is False
        and zero_orders_fills(executor_readback)
    )
    control_readback_ready = (
        control_readback.get("contract_version") == "hv_balanced_dth60_coinglass_phase9am_control_boundary_readback.v1"
        and control_readback.get("scope") == "local_proof_artifacts_default_off_observe_only_readback_only"
        and control_readback.get("live_supervisor_source_unchanged") is True
        and control_readback.get("live_supervisor_loads_candidate_hook") is False
        and control_readback.get("live_config_dir_unchanged") is True
        and control_readback.get("entered_timer_path_dry_load_harness") is True
        and control_readback.get("entered_live_timer_path") is False
        and control_readback.get("live_timer_path_loaded") is False
        and control_readback.get("live_timer_service_enabled_or_invoked") is False
        and control_readback.get("ran_supervisor") is False
        and control_readback.get("remote_control_plane_touched") is False
        and control_readback.get("candidate_execution_authorized") is False
        and control_readback.get("candidate_execution_performed") is False
        and control_readback.get("executor_input_mutated") is False
        and control_readback.get("target_plan_replaced") is False
        and no_live_mutation(control_readback)
        and zero_orders_fills(control_readback)
    )
    return {
        "p9am_output_files_exist": output_files_exist,
        "p9am_output_files_under_proof_artifacts": output_files_under_proof_artifacts,
        "dry_load_manifest_ready": dry_load_manifest_ready,
        "default_off_config_readback_ready": default_config_ready,
        "observe_only_shadow_readback_summary_ready": shadow_summary_ready,
        "executor_input_readback_ready": executor_readback_ready,
        "control_boundary_readback_ready": control_readback_ready,
    }


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9AN_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9an_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": str(args.owner),
        "decision": str(args.owner_decision),
        "decision_source": str(args.owner_decision_source),
        "decision_question": "review_p9am_default_off_observe_only_readback_sufficiency_only",
        "decision_effect": (
            "p9am_sufficient_for_separate_next_owner_gate_discussion"
            if approved
            else "none"
        ),
        "review_default_off_observe_only_readback_sufficiency_approved": approved,
        "enter_separate_next_owner_gate_discussion_approved": approved,
        "define_next_gate_scope_in_p9an_approved": False,
        "execute_next_owner_gate_approved": False,
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
        "supervisor_invocation_approved": False,
        "supervisor_run_approved": False,
        "repo_stage_change_approved": False,
    }


def build_phase9an(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = (
        resolve_path(args.output_root)
        if str(args.output_root).strip()
        else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    )
    proof_root = output_root / "proof_artifacts" / "p9an" / run_id

    project_profile_path = resolve_path(args.project_profile)
    p9am_path = (
        resolve_path(args.phase9am_summary)
        if str(args.phase9am_summary).strip()
        else latest_match(PHASE9AM_PARENT, "*/summary.json")
    )
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)

    project_profile = load_optional(project_profile_path)
    p9am = load_optional(p9am_path)
    hook_sha = file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else ""
    supervisor_sha_before = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    live_config_sha_before = tree_sha256(live_config_dir)
    supervisor_loads_hook = current_supervisor_loads_hook(supervisor_path)
    decision = owner_decision_record(args, generated_at)

    p9am_paths = proof_file_paths(p9am)
    dry_load_manifest = load_optional(p9am_paths["dry_load_execution_manifest"])
    default_config = load_optional(p9am_paths["default_off_config_readback"])
    shadow_summary = load_optional(p9am_paths["observe_only_shadow_readback_summary"])
    executor_readback = load_optional(p9am_paths["executor_input_readback"])
    control_readback = load_optional(p9am_paths["control_boundary_readback"])
    proof_checks = proof_payloads_ready(
        paths=p9am_paths,
        dry_load_manifest=dry_load_manifest,
        default_config=default_config,
        shadow_summary=shadow_summary,
        executor_readback=executor_readback,
        control_readback=control_readback,
    )
    p9am_ok = p9am_summary_ready(
        p9am,
        current_hook_sha256=hook_sha,
        current_supervisor_sha256=supervisor_sha_before,
        current_live_config_sha256=live_config_sha_before,
        current_supervisor_loads_candidate_hook=supervisor_loads_hook,
    )
    source_evidence = {
        "project_profile": evidence_file(project_profile_path),
        "phase9am_summary": evidence_file(p9am_path),
        "hook_module": evidence_file(hook_path),
        "live_supervisor": evidence_file(supervisor_path),
        "live_config_dir": {
            "path": str(live_config_dir),
            "exists": live_config_dir.exists(),
            "sha256": live_config_sha_before,
        },
        "p9am_dry_load_execution_manifest": evidence_file(p9am_paths["dry_load_execution_manifest"]),
        "p9am_default_off_config_readback": evidence_file(p9am_paths["default_off_config_readback"]),
        "p9am_observe_only_shadow_readback_summary": evidence_file(
            p9am_paths["observe_only_shadow_readback_summary"]
        ),
        "p9am_executor_input_readback": evidence_file(p9am_paths["executor_input_readback"]),
        "p9am_control_boundary_readback": evidence_file(p9am_paths["control_boundary_readback"]),
    }
    minimum_proof = {
        "stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9am_summary_ready": p9am_ok,
        "p9am_default_off_observe_only_readback_executed": p9am.get("executed_default_off_observe_only_readback")
        is True,
        "p9am_readback_default_off": p9am.get("default_off_hook_enabled") is False,
        "p9am_readback_observe_only_shadow_writer": p9am.get(
            "observe_only_shadow_writer_enabled_in_proof_harness"
        )
        is True,
        "p9am_readback_not_live_timer_service": p9am.get("dry_load_mode")
        == "default_off_observe_only_timer_path_readback_harness_not_live_timer_service",
        "proof_files_exist": proof_checks["p9am_output_files_exist"],
        "proof_files_under_proof_artifacts": proof_checks["p9am_output_files_under_proof_artifacts"],
        "dry_load_manifest_ready": proof_checks["dry_load_manifest_ready"],
        "default_off_config_readback_ready": proof_checks["default_off_config_readback_ready"],
        "observe_only_shadow_readback_summary_ready": proof_checks["observe_only_shadow_readback_summary_ready"],
        "executor_input_readback_ready": proof_checks["executor_input_readback_ready"],
        "control_boundary_readback_ready": proof_checks["control_boundary_readback_ready"],
        "candidate_shadow_artifacts_written": int(p9am.get("candidate_shadow_artifacts_written_count") or 0) > 0,
        "candidate_artifacts_under_proof_artifacts_only": p9am.get("candidate_artifacts_under_proof_artifacts_only")
        is True,
        "baseline_executor_input_hash_unchanged": p9am.get("executor_input_hash_equals_baseline") is True,
        "executor_consumes_baseline_only": p9am.get("executor_consumes_baseline_only") is True,
        "candidate_shadow_hash_differs_from_executor": p9am.get("candidate_shadow_hash_differs_from_executor")
        is True,
        "candidate_plan_not_referenced_by_executor": p9am.get("candidate_plan_referenced_by_executor") is False,
        "target_plan_not_replaced": p9am.get("target_plan_replaced") is False,
        "live_supervisor_not_loading_hook": supervisor_loads_hook is False
        and p9am.get("live_supervisor_loads_candidate_hook") is False,
        "live_config_dir_unchanged": p9am.get("live_config_dir_unchanged") is True,
        "live_timer_path_not_loaded": p9am.get("live_timer_path_loaded") is False,
        "supervisor_not_run": p9am.get("ran_supervisor") is False,
        "remote_not_touched": p9am.get("remote_execution_performed") is False
        and p9am.get("remote_control_plane_touched") is False,
        "candidate_execution_not_performed": p9am.get("candidate_execution_performed") is False,
        "zero_orders_fills": zero_orders_fills(p9am),
        "no_live_mutation": no_live_mutation(p9am),
    }
    supervisor_sha_after = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    live_config_sha_after = tree_sha256(live_config_dir)
    control_boundary_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9an_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "p9am_default_off_observe_only_readback_sufficiency_review_only",
        "live_supervisor": source_evidence["live_supervisor"],
        "live_supervisor_sha256_before": supervisor_sha_before,
        "live_supervisor_sha256_after": supervisor_sha_after,
        "live_supervisor_source_unchanged": supervisor_sha_before == supervisor_sha_after,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_config_dir_sha256_before": live_config_sha_before,
        "live_config_dir_sha256_after": live_config_sha_after,
        "live_config_dir_unchanged": live_config_sha_before == live_config_sha_after,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "timer_service_enabled_or_invoked": False,
        "remote_control_plane_touched": False,
        "candidate_execution_performed": False,
        "executor_input_mutated": False,
        "target_plan_replaced": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "fills_observed": 0,
    }
    authorizations = {
        "p9an_review_default_off_observe_only_readback_sufficiency": str(args.owner_decision)
        == APPROVE_P9AN_DECISION,
        "enter_separate_next_owner_gate_discussion": str(args.owner_decision) == APPROVE_P9AN_DECISION,
        "define_next_gate_scope_in_p9an": False,
        "execute_next_owner_gate": False,
        "candidate_execution": False,
        "candidate_live_order_submission": False,
        "timer_hook_implementation": False,
        "hook_deployment": False,
        "timer_path_load": False,
        "production_timer_service_load": False,
        "live_order_submission": False,
        "target_plan_replacement": False,
        "executor_input_mutation": False,
        "live_config_mutation": False,
        "operator_state_mutation": False,
        "timer_or_service_mutation": False,
        "remote_sync": False,
        "supervisor_invocation": False,
        "supervisor_run": False,
        "stage_governance_change": False,
    }
    decision_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9an_review_decision_matrix.v1",
        "run_id": run_id,
        "review_question": "is_p9am_default_off_observe_only_readback_sufficient_to_enter_separate_next_owner_gate",
        "minimum_proof": minimum_proof,
        "authorizations": authorizations,
    }
    owner_review_packet = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9an_owner_review_packet.v1",
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "review_scope": "owner_gated_p9am_default_off_observe_only_readback_sufficiency_review_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "minimum_proof": minimum_proof,
        "review_result": {
            "p9am_default_off_observe_only_readback_sufficient_for_next_owner_gate": False,
            "next_owner_gate_execution_authorized": False,
            "define_next_gate_scope_in_p9an_authorized": False,
            "timer_path_load_authorized": False,
            "live_order_submission_authorized": False,
        },
    }
    gates = {
        "owner_decision_p9an_review_only": str(args.owner_decision) == APPROVE_P9AN_DECISION,
        **minimum_proof,
        "review_output_under_proof_artifacts": output_under_proof_artifacts(proof_root),
        "no_define_next_gate_scope_in_p9an": True,
        "no_timer_hook_implementation_in_p9an": True,
        "no_hook_deployment_in_p9an": True,
        "no_timer_path_load_in_p9an": True,
        "no_production_timer_service_load_in_p9an": True,
        "no_supervisor_run_in_p9an": True,
        "no_remote_execution_in_p9an": True,
        "no_candidate_execution_in_p9an": True,
        "no_executor_input_mutation_in_p9an": True,
        "no_target_plan_replacement_in_p9an": True,
        "no_live_mutation_in_p9an": True,
        "zero_orders_fills_in_p9an": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"
    sufficient = status == "ready"
    owner_review_packet["review_result"][
        "p9am_default_off_observe_only_readback_sufficient_for_next_owner_gate"
    ] = sufficient

    write_json(output_root / "owner_decision_record.json", decision)
    write_json(proof_root / "owner_review_packet.json", owner_review_packet)
    write_json(proof_root / "review_decision_matrix.json", decision_matrix)
    write_json(proof_root / "control_boundary_readback.json", control_boundary_readback)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "review_scope": "owner_gated_p9am_default_off_observe_only_readback_sufficiency_review_only",
        "owner_decision": decision,
        "source_evidence": source_evidence,
        "p9am_default_off_observe_only_readback_sufficient_for_next_owner_gate": sufficient,
        "eligible_for_next_owner_gate_discussion": sufficient,
        "allowed_next_gate": P9AO_GATE if sufficient else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "next_owner_gate_execution_authorized": False,
        "define_next_gate_scope_in_p9an_authorized": False,
        "eligible_for_timer_hook_implementation": False,
        "eligible_for_hook_deployment": False,
        "eligible_for_live_timer_path_load": False,
        "eligible_for_supervisor_invocation": False,
        "eligible_for_remote_sync": False,
        "eligible_for_live_order_submission": False,
        "eligible_for_stage_governance_change": False,
        "timer_hook_implementation_authorized": False,
        "hook_deployment_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "candidate_order_authority": "disabled",
        "candidate_live_order_submission_authorized": False,
        "execution_target_source": "baseline_only",
        "candidate_overlay_execution_path": "excluded",
        "candidate_artifact_sink": "proof_artifacts_only",
        "default_off_observe_only_readback_executed": minimum_proof[
            "p9am_default_off_observe_only_readback_executed"
        ],
        "default_off_observe_only_readback_proof_files_ready": all(proof_checks.values()),
        "default_off_readback_not_live_timer_service": minimum_proof["p9am_readback_not_live_timer_service"],
        "observe_only_shadow_readback_ready": minimum_proof["observe_only_shadow_readback_summary_ready"],
        "candidate_shadow_artifacts_written_count": int(p9am.get("candidate_shadow_artifacts_written_count") or 0),
        "candidate_artifacts_under_proof_artifacts_only": minimum_proof[
            "candidate_artifacts_under_proof_artifacts_only"
        ],
        "baseline_executor_input_hash_unchanged": minimum_proof["baseline_executor_input_hash_unchanged"],
        "executor_consumes_baseline_only": minimum_proof["executor_consumes_baseline_only"],
        "candidate_shadow_hash_differs_from_executor": minimum_proof["candidate_shadow_hash_differs_from_executor"],
        "candidate_plan_referenced_by_executor": False,
        "target_plan_replaced": False,
        "live_supervisor_loads_candidate_hook": supervisor_loads_hook,
        "live_supervisor_source_unchanged": control_boundary_readback["live_supervisor_source_unchanged"],
        "live_config_dir_unchanged": control_boundary_readback["live_config_dir_unchanged"],
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
        "executor_input_changed": False,
        "recommended_next_gate": P9AO_GATE if sufficient else "",
        "proof_root": str(proof_root),
        "minimum_proof": minimum_proof,
        "proof_checks": proof_checks,
        "gates": gates,
        "blockers": blockers,
        "output_files": {
            "summary": str(output_root / "summary.json"),
            "owner_decision_record": str(output_root / "owner_decision_record.json"),
            "owner_review_packet": str(proof_root / "owner_review_packet.json"),
            "review_decision_matrix": str(proof_root / "review_decision_matrix.json"),
            "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
            "report": str(output_root / "p9an_review_after_default_off_observe_only_readback.md"),
        },
    }
    write_json(output_root / "summary.json", summary)
    (output_root / "p9an_review_after_default_off_observe_only_readback.md").write_text(
        render_markdown(summary),
        encoding="utf-8",
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9AN Review After Default-Off Observe-Only Readback",
        "",
        f"`Status: {summary['status']}`",
        "",
        "## Boundary",
        "",
        "P9AN only reviews whether P9AM is sufficient to enter a separate next owner gate.",
        "",
        "```text",
        "review_scope = owner_gated_p9am_default_off_observe_only_readback_sufficiency_review_only",
        "p9am_default_off_observe_only_readback_sufficient_for_next_owner_gate = "
        f"{str(bool(summary['p9am_default_off_observe_only_readback_sufficient_for_next_owner_gate'])).lower()}",
        "eligible_for_next_owner_gate_discussion = "
        f"{str(bool(summary['eligible_for_next_owner_gate_discussion'])).lower()}",
        f"allowed_next_gate = {summary['allowed_next_gate']}",
        "next_owner_gate_execution_authorized = false",
        "define_next_gate_scope_in_p9an_authorized = false",
        "timer_path_load_authorized = false",
        "live_order_submission_authorized = false",
        "execution_target_source = baseline_only",
        "candidate_artifact_sink = proof_artifacts_only",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Minimum Proof",
        "",
        "```text",
    ]
    for key, value in dict(summary.get("minimum_proof") or {}).items():
        lines.append(f"{key} = {str(bool(value)).lower()}")
    lines.extend(["```", "", "## Gates", "", "```text"])
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
    summary, exit_code = build_phase9an(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
