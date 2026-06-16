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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ae_nonflat_readback_owner_gate import (  # noqa: E402
    CONTRACT_VERSION as P9AE_CONTRACT,
    P9AF_GATE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9af_nonflat_execution_owner_gate.v1"
APPROVE_P9AF_DECISION = "approve_p9af_discuss_actual_nonflat_remote_no_order_execution_only"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9af_nonflat_execution_owner_gate"
PHASE9AE_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9ae_nonflat_readback_owner_gate"
P9AG_GATE = "P9AG_execute_nonflat_remote_runner_no_order_p9aa_readback_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P9AF is an owner gate that discusses actual non-flat remote "
            "no-order readback execution. It does not execute it; any execution "
            "requires a future separate P9AG request."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ae-summary", default="")
    parser.add_argument("--hook-module", default=HOOK_MODULE)
    parser.add_argument("--supervisor", default=SUPERVISOR_PATH)
    parser.add_argument("--live-config-dir", default=LIVE_CONFIG_DIR)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9AF_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:request_p9af_discuss_actual_nonflat_execution")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def owner_decision_record(args: argparse.Namespace, generated_at: datetime) -> dict[str, Any]:
    approved = args.owner_decision == APPROVE_P9AF_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9af_owner_decision.v1",
        "recorded_at_utc": iso_z(generated_at),
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "discuss_actual_nonflat_remote_no_order_readback_execution_only",
        "decision_effect": "open_p9af_execution_decision_gate" if approved else "none",
        "p9af_owner_gate_approved": approved,
        "review_scope_discusses_actual_execution": True,
        "future_p9ag_execution_gate_may_be_separately_requested": approved,
        "p9ag_execution_approved": False,
        "remote_sync_approved": False,
        "remote_execution_approved": False,
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


def load_p9ae_discussion_matrix(summary: dict[str, Any]) -> dict[str, Any]:
    output_files = dict(summary.get("output_files") or {})
    return load_optional(resolve_path(output_files.get("execution_discussion_matrix", "")))


def p9ae_ready_for_p9af(summary: dict[str, Any]) -> bool:
    matrix = load_p9ae_discussion_matrix(summary)
    authorizations = dict(matrix.get("current_gate_authorizations") or {})
    gates = dict(summary.get("gates") or {})
    return (
        summary.get("contract_version") == P9AE_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9ae_nonflat_readback_owner_gate_ready") is True
        and summary.get("review_scope_only_discusses_execution") is True
        and summary.get("eligible_for_future_p9af_nonflat_readback_execution_gate") is True
        and summary.get("allowed_next_gate") == P9AF_GATE
        and summary.get("nonflat_remote_no_order_readback_execution_authorized") is False
        and summary.get("p9af_execution_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("remote_execution_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("production_timer_service_load_authorized") is False
        and summary.get("remote_sync_performed") is False
        and summary.get("remote_execution_performed") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
        and matrix.get("allowed_next_gate") == P9AF_GATE
        and matrix.get("p9af_must_follow_p9ad_contract") is True
        and matrix.get("p9af_must_reprove_fresh_remote_account_read") is True
        and matrix.get("p9af_must_reprove_position_fingerprint_stability") is True
        and matrix.get("p9af_must_reprove_baseline_only_executor_input") is True
        and matrix.get("p9af_must_reprove_candidate_shadow_only") is True
        and matrix.get("p9af_must_reprove_zero_order_fill_trade_deltas") is True
        and matrix.get("p9af_must_reprove_remote_control_boundary_unchanged") is True
        and authorizations.get("p9af_execution") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("remote_execution") is False
        and authorizations.get("candidate_execution") is False
        and authorizations.get("live_order_submission") is False
        and gates.get("p9ad_nonflat_contract_ready") is True
        and gates.get("p9af_execution_not_authorized_in_p9ae") is True
        and gates.get("remote_sync_not_authorized_in_p9ae") is True
        and gates.get("remote_execution_not_authorized_in_p9ae") is True
    )


def execution_decision_matrix(run_id: str, p9ae_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9af_execution_decision_matrix.v1",
        "run_id": run_id,
        "review_question": "whether actual non-flat remote no-order three-cycle readback may be executed in a future gate",
        "decision": "eligible_for_future_p9ag_execution_gate_only",
        "source_p9ae_run_id": p9ae_summary.get("run_id"),
        "allowed_next_gate": P9AG_GATE,
        "allowed_next_gate_must_be_separately_requested": True,
        "p9ag_must_follow_p9ad_and_p9ae_contracts": True,
        "p9ag_required_sequence": [
            "fresh_remote_account_read_pre",
            "pre_remote_control_snapshot",
            "pre_position_fingerprint",
            "narrow_proof_harness_sync_if_needed",
            "remote_no_order_p9aa_cycle_1",
            "remote_no_order_p9aa_cycle_2",
            "remote_no_order_p9aa_cycle_3",
            "post_position_fingerprint",
            "fresh_remote_account_read_post",
            "post_remote_control_snapshot",
            "local_readback_retention",
        ],
        "p9ag_acceptance_requirements": {
            "fresh_remote_account_read_same_run": True,
            "position_fingerprint_stability": True,
            "zero_open_orders_pre_and_post": True,
            "orders_submitted_delta": 0,
            "orders_canceled_delta": 0,
            "fills_delta": 0,
            "account_trade_delta": 0,
            "completed_shadow_cycles_at_least": 3,
            "fresh_proof_each_cycle": True,
            "same_risk_inputs_each_cycle": True,
            "baseline_only_executor_input": True,
            "candidate_shadow_artifact_only": True,
            "candidate_plan_not_referenced_by_executor": True,
            "target_plan_replaced": False,
            "executor_input_mutated": False,
            "remote_control_boundary_unchanged": True,
            "production_timer_service_loaded_or_modified": False,
        },
        "current_gate_authorizations": {
            "p9ag_execution": False,
            "remote_sync": False,
            "remote_execution": False,
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


def build_phase9af(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    generated_at = now_fn()
    run_id = generated_at.strftime("%Y%m%dT%H%M%SZ")
    root = resolve_path(args.output_root) if str(args.output_root).strip() else resolve_path(DEFAULT_OUTPUT_PARENT) / run_id
    proof_root = root / "proof_artifacts" / "p9af" / run_id

    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    phase9ae_path = (
        resolve_path(args.phase9ae_summary)
        if str(args.phase9ae_summary).strip()
        else latest_match(PHASE9AE_PARENT, "*/summary.json")
    )
    p9ae = load_optional(phase9ae_path)
    hook_path = resolve_path(args.hook_module)
    supervisor_path = resolve_path(args.supervisor)
    live_config_dir = resolve_path(args.live_config_dir)

    decision = owner_decision_record(args, generated_at)
    matrix = execution_decision_matrix(run_id, p9ae)
    write_json(root / "owner_decision_record.json", decision)
    write_json(proof_root / "execution_decision_matrix.json", matrix)

    supervisor_loads_hook = current_supervisor_loads_hook(supervisor_path)
    gates = {
        "owner_decision_p9af_execution_discussion_only": args.owner_decision == APPROVE_P9AF_DECISION,
        "project_stage_boundary_preserved": project_profile.get("current_stage") == "stage_1_research_readiness_only",
        "p9ae_owner_gate_ready": p9ae_ready_for_p9af(p9ae),
        "review_scope_discusses_actual_execution": True,
        "eligible_for_future_p9ag_execution_gate": True,
        "future_p9ag_must_follow_p9ad_and_p9ae_contracts": True,
        "future_p9ag_must_reprove_fresh_account_read": True,
        "future_p9ag_must_reprove_position_fingerprint_stability": True,
        "future_p9ag_must_reprove_zero_order_fill_trade_deltas": True,
        "future_p9ag_must_reprove_baseline_only_executor": True,
        "future_p9ag_must_reprove_candidate_shadow_only": True,
        "future_p9ag_must_reprove_remote_control_boundary_unchanged": True,
        "p9ag_execution_not_authorized_in_p9af": True,
        "remote_sync_not_authorized_in_p9af": True,
        "remote_execution_not_authorized_in_p9af": True,
        "candidate_execution_forbidden": True,
        "live_order_submission_forbidden": True,
        "target_plan_replacement_forbidden": True,
        "executor_input_mutation_forbidden": True,
        "live_config_operator_timer_mutation_forbidden": True,
        "production_timer_service_load_forbidden": True,
        "current_live_supervisor_still_not_loading_hook": supervisor_loads_hook is False,
        "no_remote_sync_in_p9af": True,
        "no_remote_execution_in_p9af": True,
        "zero_orders_fills_in_p9af": True,
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
        "p9af_nonflat_execution_owner_gate_ready": status == "ready",
        "review_scope_discusses_actual_execution": True,
        "eligible_for_future_p9ag_nonflat_readback_execution_gate": status == "ready",
        "allowed_next_gate": P9AG_GATE if status == "ready" else "",
        "allowed_next_gate_must_be_separately_requested": True,
        "nonflat_remote_no_order_readback_execution_authorized": False,
        "p9ag_execution_authorized": False,
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
        "future_p9ag_requirements": {
            "must_follow_p9ad_and_p9ae_contracts": True,
            "fresh_remote_account_read_same_run": True,
            "pre_and_post_position_fingerprints": True,
            "position_fingerprint_stability": True,
            "zero_order_fill_trade_deltas": True,
            "completed_shadow_cycles_at_least": 3,
            "baseline_only_executor_input": True,
            "candidate_shadow_artifact_only": True,
            "remote_control_boundary_unchanged": True,
            "production_timer_service_loaded_or_modified": False,
        },
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "source_evidence": {
            "project_profile": evidence_file(project_profile_path),
            "phase9ae_summary": evidence_file(phase9ae_path),
            "phase9ae_execution_discussion_matrix": evidence_file(
                resolve_path(dict(p9ae.get("output_files") or {}).get("execution_discussion_matrix", ""))
            ),
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
        "proof_root": str(proof_root),
        "gates": gates,
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision_record": str(root / "owner_decision_record.json"),
            "execution_decision_matrix": str(proof_root / "execution_decision_matrix.json"),
        },
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9af(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
