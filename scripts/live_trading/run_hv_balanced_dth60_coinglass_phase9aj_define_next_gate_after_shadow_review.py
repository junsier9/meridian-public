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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ai_default_off_shadow_review import (  # noqa: E402
    CONTRACT_VERSION as P9AI_CONTRACT,
    P9AJ_GATE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9aj_define_next_gate_after_shadow_review.v1"
APPROVE_P9AJ_DECISION = "approve_p9aj_define_next_gate_after_default_off_shadow_review_scope_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9aj_define_next_gate_after_shadow_review"
PHASE9AI_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ai_default_off_observe_only_shadow_review"
P9AK_GATE = (
    "P9AK_prepare_default_off_observe_only_hook_live_supervisor_timer_path_"
    "dry_load_readback_proposal_only_if_separately_requested"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P9AJ defines the next gate scope after the P9AI retained-evidence "
            "shadow review. It only decides whether a future P9AK may prepare "
            "a default-off observe-only hook live-supervisor/timer-path "
            "dry-load/readback proposal. It does not prepare the proposal, "
            "remote sync, load a timer path, invoke the supervisor, mutate "
            "live state, or authorize orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ai-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AJ_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:ask_if_p9ai_sufficient_for_default_off_timer_path_proposal",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = args.owner_decision == APPROVE_P9AJ_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aj_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "define_next_gate_scope_after_default_off_shadow_review_only",
        "decision_effect": "define_p9ak_proposal_preparation_scope" if approved else "none",
        "p9aj_define_scope_approved": approved,
        "p9ak_may_be_separately_requested": approved,
        "p9ak_proposal_preparation_approved": False,
        "proposal_body_write_approved": False,
        "dry_load_readback_execution_approved": False,
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


def bool_false(payload: dict[str, Any], key: str) -> bool:
    return payload.get(key) is False


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def packet_ready_for_p9aj(packet: dict[str, Any]) -> bool:
    authorizations = dict(packet.get("authorizations") or {})
    rows = [dict(row or {}) for row in list(packet.get("reviewed_cycles") or [])]
    auth_keys = (
        "remote_sync",
        "remote_execution",
        "timer_path_load",
        "supervisor_invocation",
        "candidate_execution",
        "live_order_submission",
        "target_plan_replacement",
        "executor_input_mutation",
        "live_config_mutation",
        "operator_state_mutation",
        "timer_or_service_mutation",
        "production_timer_service_load",
    )
    return (
        packet.get("contract_version") == "hv_balanced_dth60_coinglass_phase9ai_shadow_review_packet.v1"
        and packet.get("review_mode") == "retained_p9aa_cycle_hook_summary_review_only"
        and packet.get("all_cycle_reviews_ready") is True
        and int(packet.get("reviewed_cycle_count") or 0) >= 3
        and packet.get("executor_hashes_distinct_from_candidate_hashes") is True
        and all(authorizations.get(key) is False for key in auth_keys)
        and rows
        and all(row_ready_for_p9aj(row) for row in rows)
    )


def row_ready_for_p9aj(row: dict[str, Any]) -> bool:
    executor_hash = str(row.get("executor_input_plan_sha256_after_hook") or "")
    candidate_hash = str(row.get("candidate_shadow_plan_sha256") or "")
    return (
        row.get("ready") is True
        and row.get("cycle_ready") is True
        and int(row.get("supervisor_exit_code") or 0) == 0
        and row.get("hook_status") == "ready"
        and row.get("hook_enabled") is True
        and row.get("mode") == "observe_only"
        and row.get("artifact_sink") == "proof_artifacts_only"
        and row.get("proof_root_under_proof_artifacts") is True
        and proof_artifacts_path(str(row.get("proof_root") or ""))
        and row.get("baseline_target_plan_byte_for_byte_unchanged") is True
        and row.get("executor_consumes_baseline_only") is True
        and row.get("executor_input_plan_hash_equals_baseline") is True
        and row.get("candidate_plan_referenced_by_executor") is False
        and row.get("candidate_artifacts_under_proof_artifacts_only") is True
        and int(row.get("candidate_artifacts_written_count") or 0) > 0
        and row.get("candidate_order_authority") == "disabled"
        and row.get("candidate_overlay_execution_path") == "excluded"
        and row.get("candidate_live_order_submission_authorized") is False
        and bool(executor_hash)
        and bool(candidate_hash)
        and executor_hash != candidate_hash
        and int_zero(row, "orders_submitted")
        and int_zero(row, "fill_count")
        and int_zero(row, "candidate_orders_submitted")
        and int_zero(row, "candidate_fill_count")
        and row.get("applied_to_live") is False
        and row.get("deployed_hook") is False
        and row.get("wrote_hook_config") is False
        and row.get("ran_supervisor") is False
        and row.get("timer_path_invoked") is False
        and row.get("live_config_changed") is False
        and row.get("operator_state_changed") is False
        and row.get("timer_state_changed") is False
    )


def p9ai_ready_for_p9aj(summary: dict[str, Any], packet: dict[str, Any]) -> bool:
    gates = dict(summary.get("gates") or {})
    required_gates = (
        "owner_decision_p9ai_shadow_review_only",
        "project_stage_boundary_preserved",
        "p9ah_owner_gate_ready",
        "p9ag_summary_revalidated",
        "p9aa_shadow_cycles_ready",
        "shadow_review_packet_under_proof_artifacts",
        "reviewed_at_least_three_cycles",
        "all_cycle_reviews_ready",
        "executor_hashes_distinct_from_candidate_hashes",
        "all_hook_status_ready",
        "all_hook_enabled_observe_only",
        "all_baseline_target_plan_byte_for_byte_unchanged",
        "all_executor_consumes_baseline_only",
        "all_executor_input_plan_hash_equals_baseline",
        "all_candidate_plan_not_referenced_by_executor",
        "all_candidate_artifacts_under_proof_artifacts_only",
        "all_candidate_artifacts_written",
        "all_candidate_order_authority_disabled",
        "all_candidate_overlay_execution_path_excluded",
        "all_candidate_orders_fills_zero",
        "all_hook_orders_fills_zero",
        "all_no_live_mutation",
        "current_live_supervisor_still_not_loading_hook",
        "no_remote_sync_in_p9ai",
        "no_remote_execution_in_p9ai",
        "no_timer_path_load_in_p9ai",
        "no_supervisor_invocation_in_p9ai",
        "no_live_config_operator_timer_mutation_in_p9ai",
        "zero_orders_fills_in_p9ai",
    )
    return (
        summary.get("contract_version") == P9AI_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9ai_default_off_observe_only_shadow_review_ready") is True
        and summary.get("default_off_observe_only_live_supervisor_shadow_review_completed") is True
        and summary.get("eligible_for_future_owner_gate_discussion") is True
        and summary.get("allowed_next_gate") == P9AJ_GATE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("p9ai_shadow_review_authorized") is True
        and summary.get("p9ai_shadow_review_performed") is True
        and bool_false(summary, "remote_sync_authorized")
        and bool_false(summary, "remote_execution_authorized")
        and bool_false(summary, "timer_path_load_authorized")
        and bool_false(summary, "supervisor_invocation_authorized")
        and bool_false(summary, "candidate_execution_authorized")
        and bool_false(summary, "live_order_submission_authorized")
        and bool_false(summary, "target_plan_replacement_authorized")
        and bool_false(summary, "executor_input_mutation_authorized")
        and bool_false(summary, "live_config_mutation_authorized")
        and bool_false(summary, "operator_state_mutation_authorized")
        and bool_false(summary, "timer_or_service_mutation_authorized")
        and bool_false(summary, "production_timer_service_load_authorized")
        and bool_false(summary, "repo_stage_change_authorized")
        and bool_false(summary, "remote_sync_performed")
        and bool_false(summary, "remote_execution_performed")
        and bool_false(summary, "entered_timer_path")
        and bool_false(summary, "ran_supervisor")
        and bool_false(summary, "live_supervisor_hook_loaded")
        and int(summary.get("reviewed_cycle_count") or 0) >= 3
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "fill_count")
        and all(gates.get(key) is True for key in required_gates)
        and packet_ready_for_p9aj(packet)
    )


def next_gate_scope_definition(run_id: str, p9ai_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9aj_next_gate_scope_definition.v1",
        "run_id": run_id,
        "source_p9ai_run_id": p9ai_summary.get("run_id"),
        "decision": "p9ai_sufficient_for_future_p9ak_proposal_preparation_only",
        "allowed_next_gate": P9AK_GATE,
        "allowed_next_gate_must_be_separately_requested": True,
        "p9ak_scope": "prepare_default_off_observe_only_hook_live_supervisor_timer_path_dry_load_readback_proposal_only",
        "p9ak_may_prepare_proposal_body": True,
        "p9ak_may_execute_proposal": False,
        "p9ak_required_boundaries": {
            "proposal_only": True,
            "proof_artifacts_only": True,
            "default_off": True,
            "observe_only": True,
            "order_submission_disabled": True,
            "candidate_execution_disabled": True,
            "executor_consumes_baseline_only": True,
            "candidate_shadow_artifact_only": True,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "production_timer_service_load": False,
            "remote_sync": False,
            "remote_execution": False,
            "timer_path_load": False,
            "supervisor_invocation": False,
        },
        "future_dry_load_readback_execution_gate_required": True,
        "future_timer_path_load_gate_required": True,
        "current_gate_authorizations": {
            "p9ak_proposal_preparation": False,
            "proposal_body_write": False,
            "dry_load_readback_execution": False,
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
            "stage_governance_change": False,
        },
    }


def build_phase9aj(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = root / "proof_artifacts" / "p9aj" / run_id

    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    p9ai_path = (
        resolve_path(args.phase9ai_summary)
        if str(args.phase9ai_summary).strip()
        else latest_match(PHASE9AI_PARENT, "*/summary.json")
    )
    p9ai_summary = load_optional(p9ai_path)
    packet_path = resolve_path(dict(p9ai_summary.get("output_files") or {}).get("shadow_review_packet", ""))
    packet = load_optional(packet_path)
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)

    decision = owner_decision_record(args, generated_at)
    scope = next_gate_scope_definition(run_id, p9ai_summary)
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "next_gate_scope_definition.json", scope)

    source = dict(p9ai_summary.get("source_evidence") or {})
    current_hook_sha = file_sha256(hook_path) if hook_path.exists() and hook_path.is_file() else ""
    current_supervisor_sha = file_sha256(supervisor_path) if supervisor_path.exists() and supervisor_path.is_file() else ""
    supervisor_loads_hook = current_supervisor_loads_hook(supervisor_path)
    gates = {
        "owner_decision_p9aj_define_scope_only": args.owner_decision == APPROVE_P9AJ_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9ai_summary_ready": p9ai_ready_for_p9aj(p9ai_summary, packet),
        "p9ai_shadow_review_packet_ready": packet_ready_for_p9aj(packet),
        "next_gate_scope_definition_under_proof_artifacts": proof_artifacts_path(str(proof_root / "next_gate_scope_definition.json")),
        "p9aj_defines_scope_only": True,
        "p9aj_does_not_prepare_p9ak_proposal": True,
        "p9aj_does_not_write_proposal_body": True,
        "p9ak_must_be_separately_requested": True,
        "p9ak_must_remain_proposal_only": True,
        "p9ak_must_keep_default_off": True,
        "p9ak_must_keep_order_submission_disabled": True,
        "p9ak_must_keep_executor_baseline_only": True,
        "p9ak_must_keep_candidate_shadow_only": True,
        "p9ak_must_not_execute_dry_load": True,
        "p9ak_must_not_load_timer_path": True,
        "p9ak_must_not_invoke_supervisor": True,
        "current_live_supervisor_still_not_loading_hook": supervisor_loads_hook is False,
        "current_hook_hash_matches_p9ai_source": current_hook_sha == dict(source.get("hook_module") or {}).get("sha256"),
        "current_supervisor_hash_matches_p9ai_source": current_supervisor_sha
        == dict(source.get("live_supervisor") or {}).get("sha256"),
        "remote_sync_not_authorized_in_p9aj": True,
        "remote_execution_not_authorized_in_p9aj": True,
        "timer_path_load_not_authorized_in_p9aj": True,
        "supervisor_invocation_not_authorized_in_p9aj": True,
        "candidate_execution_forbidden": True,
        "live_order_submission_forbidden": True,
        "target_plan_replacement_forbidden": True,
        "executor_input_mutation_forbidden": True,
        "live_config_operator_timer_mutation_forbidden": True,
        "production_timer_service_load_forbidden": True,
        "zero_orders_fills_in_p9aj": True,
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
        "p9aj_define_next_gate_after_shadow_review_ready": status == "ready",
        "review_question": "is_p9ai_sufficient_to_prepare_default_off_observe_only_hook_timer_path_dry_load_readback_proposal",
        "p9ai_sufficient_for_future_p9ak_proposal_preparation": status == "ready",
        "allowed_next_gate": P9AK_GATE if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "p9ak_proposal_preparation_authorized": False,
        "prepared_p9ak_proposal": False,
        "wrote_p9ak_proposal_body": False,
        "dry_load_readback_execution_authorized": False,
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
        "source_evidence": {
            "project_profile": evidence_file(project_profile_path),
            "phase9ai_summary": evidence_file(p9ai_path),
            "phase9ai_shadow_review_packet": evidence_file(packet_path),
            "hook_module": evidence_file(hook_path),
            "live_supervisor": evidence_file(supervisor_path),
            "live_config_dir": {
                "path": str(live_config_dir),
                "exists": live_config_dir.exists(),
                "sha256": tree_sha256(live_config_dir),
            },
            "hook_module_sha256": current_hook_sha,
            "live_supervisor_sha256": current_supervisor_sha,
        },
        "reviewed_p9ai_facts": {
            "source_p9ai_run_id": p9ai_summary.get("run_id"),
            "reviewed_cycle_count": p9ai_summary.get("reviewed_cycle_count"),
            "all_cycle_reviews_ready": dict(p9ai_summary.get("gates") or {}).get("all_cycle_reviews_ready"),
            "all_executor_consumes_baseline_only": dict(p9ai_summary.get("gates") or {}).get(
                "all_executor_consumes_baseline_only"
            ),
            "all_candidate_plan_not_referenced_by_executor": dict(p9ai_summary.get("gates") or {}).get(
                "all_candidate_plan_not_referenced_by_executor"
            ),
            "all_candidate_artifacts_under_proof_artifacts_only": dict(p9ai_summary.get("gates") or {}).get(
                "all_candidate_artifacts_under_proof_artifacts_only"
            ),
            "all_no_live_mutation": dict(p9ai_summary.get("gates") or {}).get("all_no_live_mutation"),
            "orders_submitted": p9ai_summary.get("orders_submitted"),
            "fill_count": p9ai_summary.get("fill_count"),
        },
        "next_gate_scope": scope,
        "proof_root": str(proof_root),
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "next_gate_scope_definition": str(proof_root / "next_gate_scope_definition.json"),
        },
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9aj(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
