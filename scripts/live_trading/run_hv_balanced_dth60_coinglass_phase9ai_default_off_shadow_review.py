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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ah_owner_gate_default_off_shadow_review import (  # noqa: E402
    CONTRACT_VERSION as P9AH_CONTRACT,
    P9AI_GATE,
    p9aa_shadow_cycle_ready,
    p9ag_ready_for_p9ah,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    current_supervisor_loads_hook,
    evidence_file,
    file_sha256,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    HOOK_MODULE,
    LIVE_CONFIG_DIR,
    PROJECT_PROFILE,
    SUPERVISOR_PATH,
    tree_sha256,
)


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9ai_default_off_observe_only_shadow_review.v1"
APPROVE_P9AI_DECISION = "approve_p9ai_default_off_observe_only_live_supervisor_shadow_review_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ai_default_off_observe_only_shadow_review"
PHASE9AH_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ah_default_off_shadow_review_owner_gate"
P9AJ_GATE = "P9AJ_define_next_gate_after_default_off_shadow_review_only_if_separately_requested"
HOOK_CONTRACT = "hv_balanced_dth60_observe_only_shadow_hook.v1"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute P9AI as a retained-evidence default-off observe-only "
            "live-supervisor shadow review. It reviews retained P9AG/P9AA "
            "cycle hook evidence and writes a proof-only review packet. It "
            "does not remote sync, load timer paths, invoke the supervisor, "
            "mutate executor input, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ah-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AI_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:request_p9ai_default_off_observe_only_shadow_review",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = args.owner_decision == APPROVE_P9AI_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ai_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "execute_default_off_observe_only_live_supervisor_shadow_review_only",
        "decision_effect": "execute_p9ai_retained_evidence_shadow_review" if approved else "none",
        "p9ai_shadow_review_approved": approved,
        "review_mode": "retained_evidence_review_only_not_timer_path",
        "default_off_required": True,
        "observe_only_required": True,
        "baseline_only_executor_required": True,
        "candidate_shadow_artifact_only_required": True,
        "orders_and_fills_must_remain_zero": True,
        "remote_sync_approved": False,
        "remote_execution_approved": False,
        "timer_path_load_approved": False,
        "supervisor_invocation_approved": False,
        "candidate_execution_approved": False,
        "candidate_live_order_submission_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "production_timer_service_load_approved": False,
        "repo_stage_change_approved": False,
    }


def proof_artifacts_path(path_text: str) -> bool:
    return "proof_artifacts" in str(path_text).replace("\\", "/").lower().split("/")


def evidence_obj_ready(item: Any) -> bool:
    payload = dict(item or {})
    return payload.get("exists") is True and bool(payload.get("sha256"))


def p9ah_ready_for_p9ai(summary: dict[str, Any]) -> bool:
    gates = dict(summary.get("gates") or {})
    return (
        summary.get("contract_version") == P9AH_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9ah_default_off_shadow_review_owner_gate_ready") is True
        and summary.get("eligible_for_future_default_off_observe_only_live_supervisor_shadow_review") is True
        and summary.get("allowed_next_gate") == P9AI_GATE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("default_off_live_supervisor_shadow_review_authorized") is False
        and summary.get("p9ai_shadow_review_execution_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("remote_execution_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
        and all(
            gates.get(key) is True
            for key in (
                "owner_decision_p9ah_review_only",
                "project_stage_boundary_preserved",
                "p9ag_summary_ready",
                "p9ag_position_reference_fixture_pit_safe",
                "p9ag_three_fresh_shadow_cycles",
                "p9ag_remote_sync_proof_harness_only",
                "current_live_supervisor_still_not_loading_hook",
                "p9ai_must_be_separately_requested",
                "p9ai_not_executed_in_p9ah",
                "remote_sync_not_authorized_in_p9ah",
                "remote_execution_not_authorized_in_p9ah",
                "timer_path_load_not_authorized_in_p9ah",
                "candidate_execution_forbidden",
                "live_order_submission_forbidden",
                "target_plan_replacement_forbidden",
                "executor_input_mutation_forbidden",
                "production_timer_service_load_forbidden",
                "zero_orders_fills_in_p9ah",
            )
        )
    )


def hook_summary_review(row: dict[str, Any]) -> dict[str, Any]:
    hook = dict(row.get("hook_summary") or {})
    gates = dict(hook.get("gates") or {})
    candidate_paths = [str(item) for item in list(hook.get("candidate_artifact_paths") or [])]
    baseline_before = str(hook.get("baseline_target_plan_sha256_before_hook") or "")
    baseline_after = str(hook.get("baseline_target_plan_sha256_after_hook") or "")
    executor_before = str(hook.get("executor_input_plan_sha256_before_hook") or "")
    executor_after = str(hook.get("executor_input_plan_sha256_after_hook") or "")
    candidate_sha = str(hook.get("candidate_shadow_plan_sha256") or "")
    required_hook_gates = (
        "mode_observe_only",
        "artifact_sink_proof_artifacts_only",
        "candidate_order_authority_disabled",
        "candidate_live_order_submission_authorized_false",
        "candidate_overlay_execution_path_excluded",
        "execution_target_source_baseline_only",
        "baseline_target_plan_exists",
        "baseline_target_plan_byte_for_byte_unchanged",
        "executor_input_plan_exists",
        "executor_input_plan_hash_equals_baseline",
        "executor_input_plan_hash_unchanged",
        "executor_consumes_baseline_only",
        "candidate_shadow_plan_exists",
        "candidate_shadow_artifact_written",
        "candidate_artifacts_under_proof_artifacts_only",
        "candidate_orders_submitted_zero",
        "candidate_fill_count_zero",
        "enabled_hook_output_root_under_proof_artifacts",
    )
    ready = (
        row.get("cycle_ready") is True
        and int(row.get("supervisor_exit_code") or 0) == 0
        and hook.get("contract_version") == HOOK_CONTRACT
        and hook.get("status") == "ready"
        and not hook.get("blockers")
        and hook.get("hook_enabled") is True
        and hook.get("mode") == "observe_only"
        and hook.get("artifact_sink") == "proof_artifacts_only"
        and hook.get("applied_to_live") is False
        and hook.get("deployed_hook") is False
        and hook.get("wrote_hook_config") is False
        and hook.get("ran_supervisor") is False
        and hook.get("timer_path_invoked") is False
        and hook.get("candidate_order_authority") == "disabled"
        and hook.get("candidate_live_order_submission_authorized") is False
        and hook.get("candidate_overlay_execution_path") == "excluded"
        and hook.get("execution_target_source") == "baseline_only"
        and hook.get("exchange_order_submission") == "disabled"
        and hook.get("mainnet_order_submission_authorized") is False
        and evidence_obj_ready(hook.get("baseline_target_plan"))
        and evidence_obj_ready(hook.get("executor_input_plan"))
        and evidence_obj_ready(hook.get("candidate_source_plan"))
        and hook.get("baseline_target_plan_byte_for_byte_unchanged") is True
        and bool(baseline_before)
        and baseline_before == baseline_after
        and bool(executor_before)
        and executor_before == executor_after
        and executor_after == baseline_after
        and hook.get("executor_input_plan_hash_equals_baseline") is True
        and hook.get("executor_input_plan_hash_unchanged") is True
        and hook.get("executor_consumes_baseline_only") is True
        and hook.get("candidate_plan_referenced_by_executor") is False
        and bool(candidate_sha)
        and candidate_sha != executor_after
        and hook.get("candidate_artifacts_under_proof_artifacts_only") is True
        and int(hook.get("candidate_artifacts_written_count") or 0) > 0
        and candidate_paths
        and all(proof_artifacts_path(path) for path in candidate_paths)
        and int(hook.get("candidate_orders_submitted") or 0) == 0
        and int(hook.get("candidate_fill_count") or 0) == 0
        and int(hook.get("orders_submitted") or 0) == 0
        and int(hook.get("fill_count") or 0) == 0
        and hook.get("live_config_changed") is False
        and hook.get("operator_state_changed") is False
        and hook.get("timer_state_changed") is False
        and all(gates.get(key) is True for key in required_hook_gates)
    )
    return {
        "cycle_index": row.get("cycle_index"),
        "cycle_ready": row.get("cycle_ready") is True,
        "supervisor_exit_code": int(row.get("supervisor_exit_code") or 0),
        "hook_run_id": hook.get("run_id"),
        "hook_status": hook.get("status"),
        "ready": ready,
        "hook_enabled": hook.get("hook_enabled") is True,
        "mode": hook.get("mode"),
        "artifact_sink": hook.get("artifact_sink"),
        "proof_root": hook.get("proof_root"),
        "proof_root_under_proof_artifacts": proof_artifacts_path(str(hook.get("proof_root") or "")),
        "baseline_target_plan_sha256_before_hook": baseline_before,
        "baseline_target_plan_sha256_after_hook": baseline_after,
        "executor_input_plan_sha256_before_hook": executor_before,
        "executor_input_plan_sha256_after_hook": executor_after,
        "candidate_shadow_plan_sha256": candidate_sha,
        "executor_consumes_baseline_only": hook.get("executor_consumes_baseline_only") is True,
        "executor_input_plan_hash_equals_baseline": hook.get("executor_input_plan_hash_equals_baseline") is True,
        "baseline_target_plan_byte_for_byte_unchanged": hook.get("baseline_target_plan_byte_for_byte_unchanged") is True,
        "candidate_plan_referenced_by_executor": hook.get("candidate_plan_referenced_by_executor") is True,
        "candidate_artifacts_under_proof_artifacts_only": hook.get("candidate_artifacts_under_proof_artifacts_only") is True,
        "candidate_artifacts_written_count": int(hook.get("candidate_artifacts_written_count") or 0),
        "candidate_order_authority": hook.get("candidate_order_authority"),
        "candidate_overlay_execution_path": hook.get("candidate_overlay_execution_path"),
        "candidate_live_order_submission_authorized": hook.get("candidate_live_order_submission_authorized") is True,
        "orders_submitted": int(hook.get("orders_submitted") or 0),
        "fill_count": int(hook.get("fill_count") or 0),
        "candidate_orders_submitted": int(hook.get("candidate_orders_submitted") or 0),
        "candidate_fill_count": int(hook.get("candidate_fill_count") or 0),
        "applied_to_live": hook.get("applied_to_live") is True,
        "deployed_hook": hook.get("deployed_hook") is True,
        "wrote_hook_config": hook.get("wrote_hook_config") is True,
        "ran_supervisor": hook.get("ran_supervisor") is True,
        "timer_path_invoked": hook.get("timer_path_invoked") is True,
        "live_config_changed": hook.get("live_config_changed") is True,
        "operator_state_changed": hook.get("operator_state_changed") is True,
        "timer_state_changed": hook.get("timer_state_changed") is True,
    }


def build_shadow_review_packet(run_id: str, p9aa_summary: dict[str, Any]) -> dict[str, Any]:
    cycle_rows = [dict(row or {}) for row in list(p9aa_summary.get("cycle_rows") or [])]
    reviewed_cycles = [hook_summary_review(row) for row in cycle_rows]
    all_ready = bool(reviewed_cycles) and all(row.get("ready") is True for row in reviewed_cycles)
    unique_executor_hashes = sorted(
        {
            str(row.get("executor_input_plan_sha256_after_hook") or "")
            for row in reviewed_cycles
            if row.get("executor_input_plan_sha256_after_hook")
        }
    )
    unique_candidate_hashes = sorted(
        {
            str(row.get("candidate_shadow_plan_sha256") or "")
            for row in reviewed_cycles
            if row.get("candidate_shadow_plan_sha256")
        }
    )
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ai_shadow_review_packet.v1",
        "run_id": run_id,
        "review_mode": "retained_p9aa_cycle_hook_summary_review_only",
        "source_p9aa_run_id": p9aa_summary.get("run_id"),
        "reviewed_cycle_count": len(reviewed_cycles),
        "all_cycle_reviews_ready": all_ready,
        "unique_executor_input_hashes_after_hook": unique_executor_hashes,
        "unique_candidate_shadow_hashes": unique_candidate_hashes,
        "executor_hashes_distinct_from_candidate_hashes": set(unique_executor_hashes).isdisjoint(unique_candidate_hashes),
        "reviewed_cycles": reviewed_cycles,
        "authorizations": {
            "remote_sync": False,
            "remote_execution": False,
            "timer_path_load": False,
            "supervisor_invocation": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "production_timer_service_load": False,
        },
    }


def build_phase9ai(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = root / "proof_artifacts" / "p9ai" / run_id

    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    p9ah_path = (
        resolve_path(args.phase9ah_summary)
        if str(args.phase9ah_summary).strip()
        else latest_match(PHASE9AH_PARENT, "*/summary.json")
    )
    p9ah_summary = load_optional(p9ah_path)
    source = dict(p9ah_summary.get("source_evidence") or {})
    p9ag_path = resolve_path(dict(source.get("phase9ag_summary") or {}).get("path", ""))
    p9aa_path = resolve_path(dict(source.get("phase9ag_remote_p9aa_summary") or {}).get("path", ""))
    sync_manifest_path = resolve_path(dict(source.get("phase9ag_remote_sync_manifest") or {}).get("path", ""))
    p9ag_summary = load_optional(p9ag_path)
    p9aa_summary = load_optional(p9aa_path)
    sync_manifest = load_optional(sync_manifest_path)
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)

    decision = owner_decision_record(args, generated_at)
    packet = build_shadow_review_packet(run_id, p9aa_summary)
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "shadow_review_packet.json", packet)
    write_json(proof_root / "cycle_shadow_review_rows.json", {"run_id": run_id, "rows": packet["reviewed_cycles"]})

    supervisor_loads_hook = current_supervisor_loads_hook(supervisor_path)
    reviewed_cycles = list(packet.get("reviewed_cycles") or [])
    gates = {
        "owner_decision_p9ai_shadow_review_only": args.owner_decision == APPROVE_P9AI_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9ah_owner_gate_ready": p9ah_ready_for_p9ai(p9ah_summary),
        "p9ag_summary_revalidated": p9ag_ready_for_p9ah(
            p9ag_summary,
            p9aa_summary=p9aa_summary,
            sync_manifest=sync_manifest,
        ),
        "p9aa_shadow_cycles_ready": p9aa_shadow_cycle_ready(p9ag_summary, p9aa_summary),
        "shadow_review_packet_under_proof_artifacts": proof_artifacts_path(str(proof_root / "shadow_review_packet.json")),
        "reviewed_at_least_three_cycles": len(reviewed_cycles) >= 3,
        "all_cycle_reviews_ready": packet.get("all_cycle_reviews_ready") is True,
        "executor_hashes_distinct_from_candidate_hashes": packet.get("executor_hashes_distinct_from_candidate_hashes") is True,
        "all_hook_status_ready": bool(reviewed_cycles)
        and all(row.get("hook_status") == "ready" for row in reviewed_cycles),
        "all_hook_enabled_observe_only": bool(reviewed_cycles)
        and all(row.get("hook_enabled") is True and row.get("mode") == "observe_only" for row in reviewed_cycles),
        "all_baseline_target_plan_byte_for_byte_unchanged": bool(reviewed_cycles)
        and all(row.get("baseline_target_plan_byte_for_byte_unchanged") is True for row in reviewed_cycles),
        "all_executor_consumes_baseline_only": bool(reviewed_cycles)
        and all(row.get("executor_consumes_baseline_only") is True for row in reviewed_cycles),
        "all_executor_input_plan_hash_equals_baseline": bool(reviewed_cycles)
        and all(row.get("executor_input_plan_hash_equals_baseline") is True for row in reviewed_cycles),
        "all_candidate_plan_not_referenced_by_executor": bool(reviewed_cycles)
        and all(row.get("candidate_plan_referenced_by_executor") is False for row in reviewed_cycles),
        "all_candidate_artifacts_under_proof_artifacts_only": bool(reviewed_cycles)
        and all(row.get("candidate_artifacts_under_proof_artifacts_only") is True for row in reviewed_cycles),
        "all_candidate_artifacts_written": bool(reviewed_cycles)
        and all(int(row.get("candidate_artifacts_written_count") or 0) > 0 for row in reviewed_cycles),
        "all_candidate_order_authority_disabled": bool(reviewed_cycles)
        and all(row.get("candidate_order_authority") == "disabled" for row in reviewed_cycles),
        "all_candidate_overlay_execution_path_excluded": bool(reviewed_cycles)
        and all(row.get("candidate_overlay_execution_path") == "excluded" for row in reviewed_cycles),
        "all_candidate_orders_fills_zero": bool(reviewed_cycles)
        and all(
            int(row.get("candidate_orders_submitted") or 0) == 0 and int(row.get("candidate_fill_count") or 0) == 0
            for row in reviewed_cycles
        ),
        "all_hook_orders_fills_zero": bool(reviewed_cycles)
        and all(int(row.get("orders_submitted") or 0) == 0 and int(row.get("fill_count") or 0) == 0 for row in reviewed_cycles),
        "all_no_live_mutation": bool(reviewed_cycles)
        and all(
            row.get("applied_to_live") is False
            and row.get("deployed_hook") is False
            and row.get("wrote_hook_config") is False
            and row.get("ran_supervisor") is False
            and row.get("timer_path_invoked") is False
            and row.get("live_config_changed") is False
            and row.get("operator_state_changed") is False
            and row.get("timer_state_changed") is False
            for row in reviewed_cycles
        ),
        "current_live_supervisor_still_not_loading_hook": supervisor_loads_hook is False,
        "no_remote_sync_in_p9ai": True,
        "no_remote_execution_in_p9ai": True,
        "no_timer_path_load_in_p9ai": True,
        "no_supervisor_invocation_in_p9ai": True,
        "no_live_config_operator_timer_mutation_in_p9ai": True,
        "zero_orders_fills_in_p9ai": True,
    }
    blockers = [key for key, value in gates.items() if not value]
    status = "ready" if not blockers else "blocked"

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "status": status,
        "blockers": blockers,
        "owner_decision": decision,
        "p9ai_default_off_observe_only_shadow_review_ready": status == "ready",
        "review_mode": "retained_evidence_review_only_not_timer_path",
        "default_off_observe_only_live_supervisor_shadow_review_completed": status == "ready",
        "eligible_for_future_owner_gate_discussion": status == "ready",
        "allowed_next_gate": P9AJ_GATE if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "p9ai_shadow_review_authorized": args.owner_decision == APPROVE_P9AI_DECISION,
        "p9ai_shadow_review_performed": True,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
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
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "live_supervisor_hook_loaded": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "reviewed_cycle_count": len(reviewed_cycles),
        "source_evidence": {
            "project_profile": evidence_file(project_profile_path),
            "phase9ah_summary": evidence_file(p9ah_path),
            "phase9ag_summary": evidence_file(p9ag_path),
            "phase9ag_remote_p9aa_summary": evidence_file(p9aa_path),
            "phase9ag_remote_sync_manifest": evidence_file(sync_manifest_path),
            "hook_module": evidence_file(hook_path),
            "live_supervisor": evidence_file(supervisor_path),
            "live_config_dir": {
                "path": str(live_config_dir),
                "exists": live_config_dir.exists(),
                "sha256": tree_sha256(live_config_dir),
            },
            "hook_module_sha256": file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else "",
            "live_supervisor_sha256": file_sha256(supervisor_path)
            if supervisor_path.exists() and supervisor_path.is_file()
            else "",
        },
        "reviewed_shadow_facts": {
            "source_p9aa_run_id": p9aa_summary.get("run_id"),
            "source_p9ag_run_id": p9ag_summary.get("run_id"),
            "reviewed_cycle_count": len(reviewed_cycles),
            "completed_shadow_cycles": p9aa_summary.get("completed_shadow_cycles"),
            "fresh_proof_each_cycle": p9aa_summary.get("fresh_proof_each_cycle"),
            "same_risk_no_order_config_each_cycle": p9aa_summary.get("same_risk_no_order_config_each_cycle"),
            "execution_target_source": p9aa_summary.get("execution_target_source"),
            "candidate_order_authority": p9aa_summary.get("candidate_order_authority"),
            "candidate_overlay_execution_path": p9aa_summary.get("candidate_overlay_execution_path"),
            "systemd_timer_service_invoked": p9aa_summary.get("systemd_timer_service_invoked"),
            "production_timer_service_loaded_or_modified": p9aa_summary.get("production_timer_service_loaded_or_modified"),
            "live_config_changed": p9aa_summary.get("live_config_changed"),
            "operator_state_changed_outside_generated_p9aa_state": p9aa_summary.get(
                "operator_state_changed_outside_generated_p9aa_state"
            ),
            "timer_state_changed": p9aa_summary.get("timer_state_changed"),
            "orders_submitted": p9aa_summary.get("orders_submitted"),
            "fill_count": p9aa_summary.get("fill_count"),
            "unique_executor_input_hashes_after_hook": packet.get("unique_executor_input_hashes_after_hook"),
            "unique_candidate_shadow_hashes": packet.get("unique_candidate_shadow_hashes"),
        },
        "proof_root": str(proof_root),
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "shadow_review_packet": str(proof_root / "shadow_review_packet.json"),
            "cycle_shadow_review_rows": str(proof_root / "cycle_shadow_review_rows.json"),
        },
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9ai(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
