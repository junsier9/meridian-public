from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.live_trading.run_hv_balanced_12factor_p10i_execute_single_cycle_live_delta_canary import (  # noqa: E402
    CANARY_SYMBOL,
    CONTRACT_VERSION as P10I_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P10I_PARENT,
    MAX_NOTIONAL_USDT,
    ORDER_TYPE,
    P10J_GATE,
    P10J_SCOPE,
    REMOTE_SUBMITTER_CONTRACT,
    TIME_IN_FORCE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    PROJECT_PROFILE,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10j_review_p10i_single_cycle_live_delta_canary.v1"
APPROVE_P10J_DECISION = (
    "approve_p10j_review_p10i_retained_evidence_for_limited_live_delta_candidate_executor_path_discussion_only"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/proof_artifacts/p10j_review_p10i_single_cycle_live_delta_canary"
P10K_GATE = "P10K_define_limited_live_delta_candidate_executor_path_discussion_scope_only_if_separately_requested"
P10K_SCOPE = (
    "define_scope_only_for_limited_live_delta_candidate_executor_path_discussion_after_p10i_no_execution_no_continuous_automation"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P10J review-only gate: review retained P10I single-cycle live_delta "
            "canary evidence. This does not SSH, call Binance, submit/cancel "
            "orders, mutate timer/supervisor/executor paths, or authorize "
            "continuous automated order flow."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--p10i-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P10J_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p10j_review_p10i_single_cycle_live_delta_canary_"
            "only_if_separately_requested"
        ),
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


def latest_p10i_summary(args: argparse.Namespace) -> Path:
    if str(args.p10i_summary).strip():
        return resolve_path(args.p10i_summary)
    return latest_match(P10I_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def decimal_value(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p10i_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P10I_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10i_single_cycle_live_delta_canary_ready") is True
        and summary.get("p10h_sufficient_for_p10i_execution") is True
        and summary.get("p10g_hash_bound_to_p10h") is True
        and summary.get("candidate_delta_binding_ready") is True
        and summary.get("candidate_delta_side") in {"BUY", "SELL"}
        and summary.get("canary_symbol") == CANARY_SYMBOL
        and summary.get("canary_side") == summary.get("candidate_delta_side")
        and decimal_value(summary.get("canary_capped_notional_usdt")) == MAX_NOTIONAL_USDT
        and decimal_value(summary.get("canary_notional_usdt")) <= MAX_NOTIONAL_USDT
        and decimal_value(summary.get("canary_notional_usdt")) > 0
        and decimal_value(summary.get("canary_quantity")) > 0
        and summary.get("fresh_pre_submit_readback_performed") is True
        and summary.get("fresh_remote_account_read_performed") is True
        and summary.get("fresh_order_book_read_performed") is True
        and summary.get("exchange_filter_read_performed") is True
        and summary.get("pit_safe_v2v3_account_proof_ready") is True
        and summary.get("can_trade_decision_source") == "/fapi/v2/account.canTrade"
        and summary.get("can_trade_pre") is True
        and summary.get("can_trade_post") is True
        and summary.get("canary_order_plan_ready") is True
        and summary.get("order_type") == ORDER_TYPE
        and summary.get("time_in_force") == TIME_IN_FORCE
        and summary.get("market_orders_allowed") is False
        and summary.get("post_only_required") is True
        and summary.get("maker_only_required") is True
        and summary.get("limit_order_must_not_cross_spread") is True
        and summary.get("live_order_submission_authorized") is True
        and summary.get("live_order_submission_performed") is True
        and summary.get("actual_live_order_submission_performed") is True
        and int(summary.get("orders_submitted") or 0) == 1
        and int(summary.get("orders_canceled") or 0) == 1
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and summary.get("remote_control_boundary_unchanged") is True
        and summary.get("actual_target_plan_replacement_performed") is False
        and summary.get("actual_executor_input_mutation_performed") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("continuous_automation_enabled") is False
        and summary.get("remote_sync_performed") is False
        and int_zero(summary, "remote_files_written")
        and summary.get("allowed_next_gate") == P10J_GATE
        and summary.get("allowed_next_gate_scope") == P10J_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def p10i_plan_ready(plan: dict[str, Any], summary: dict[str, Any]) -> bool:
    return (
        plan.get("contract_version") == "hv_balanced_12factor_p10i_canary_order_plan.v1"
        and plan.get("status") == "ready"
        and not plan.get("blockers")
        and plan.get("symbol") == CANARY_SYMBOL
        and plan.get("side") == summary.get("candidate_delta_side")
        and decimal_value(plan.get("quantity")) > 0
        and decimal_value(plan.get("notional_usdt")) > 0
        and decimal_value(plan.get("notional_usdt")) <= MAX_NOTIONAL_USDT
        and decimal_value(plan.get("notional_usdt")) >= decimal_value(plan.get("minimum_executable_notional_usdt"))
        and plan.get("order_type") == ORDER_TYPE
        and plan.get("time_in_force") == TIME_IN_FORCE
        and plan.get("market_orders_allowed") is False
        and plan.get("post_only_required") is True
        and plan.get("maker_only_required") is True
        and plan.get("limit_order_must_not_cross_spread") is True
    )


def p10i_submission_ready(submission: dict[str, Any], summary: dict[str, Any]) -> bool:
    submit_payload = dict(dict(submission.get("order_submission") or {}).get("payload") or {})
    query_payload = dict(dict(submission.get("order_query") or {}).get("payload") or {})
    cancel_payload = dict(dict(submission.get("order_cancel") or {}).get("payload") or {})
    side_effects = dict(submission.get("side_effects") or {})
    post_open_orders = dict(dict(submission.get("post_submit_readback") or {}).get("open_orders") or {})
    methods = set(str(item).upper() for item in list(side_effects.get("http_methods_used") or []))
    return (
        submission.get("contract_version") == REMOTE_SUBMITTER_CONTRACT
        and submission.get("status") == "ready"
        and not submission.get("blockers")
        and int(submission.get("orders_submitted") or 0) == 1
        and int(submission.get("orders_canceled") or 0) == 1
        and int_zero(submission, "fill_count")
        and int_zero(submission, "trade_count")
        and submit_payload.get("symbol") == CANARY_SYMBOL
        and submit_payload.get("side") == summary.get("candidate_delta_side")
        and submit_payload.get("type") == "LIMIT"
        and submit_payload.get("timeInForce") == TIME_IN_FORCE
        and decimal_value(submit_payload.get("origQty")) > 0
        and decimal_value(submit_payload.get("executedQty")) == Decimal("0")
        and submit_payload.get("status") == "NEW"
        and query_payload.get("status") == "NEW"
        and decimal_value(query_payload.get("executedQty")) == Decimal("0")
        and cancel_payload.get("status") == "CANCELED"
        and decimal_value(cancel_payload.get("executedQty")) == Decimal("0")
        and isinstance(post_open_orders.get("payload"), list)
        and len(post_open_orders.get("payload") or []) == 0
        and {"GET", "POST", "DELETE"}.issubset(methods)
        and side_effects.get("remote_files_written") == 0
        and side_effects.get("remote_sync_performed") is False
        and side_effects.get("supervisor_invoked") is False
        and side_effects.get("timer_path_invoked") is False
        and side_effects.get("candidate_executed") is False
        and side_effects.get("executor_input_mutated") is False
        and side_effects.get("target_plan_replaced") is False
        and side_effects.get("continuous_automation_enabled") is False
    )


def p10i_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version") == "hv_balanced_12factor_p10i_control_boundary.v1"
        and control.get("scope") == "single_cycle_live_delta_canary_only"
        and control.get("ssh_invoked") is True
        and control.get("remote_network_connection_performed") is True
        and control.get("fresh_remote_account_read_performed") is True
        and control.get("fresh_order_book_read_performed") is True
        and control.get("exchange_filter_read_performed") is True
        and control.get("live_order_submission_performed") is True
        and int(control.get("orders_submitted") or 0) == 1
        and int(control.get("orders_canceled") or 0) == 1
        and int_zero(control, "fill_count")
        and int_zero(control, "trade_count")
        and control.get("entered_timer_path") is False
        and control.get("ran_supervisor") is False
        and control.get("timer_path_loaded") is False
        and control.get("target_plan_replaced") is False
        and control.get("executor_input_changed") is False
        and control.get("continuous_automation_enabled") is False
        and control.get("live_config_changed") is False
        and control.get("operator_state_changed") is False
        and control.get("timer_state_changed") is False
        and int_zero(control, "remote_files_written")
        and control.get("remote_sync_performed") is False
    )


def p10i_delta_acceptance_ready(
    account_delta: dict[str, Any],
    account_history: dict[str, Any],
    market_delta: dict[str, Any],
    identity: dict[str, Any],
) -> bool:
    return (
        account_delta.get("position_fingerprint_stable") is True
        and account_delta.get("open_order_fingerprint_stable") is True
        and account_delta.get("balance_fingerprint_stable") is True
        and account_delta.get("open_order_count_zero_pre_post") is True
        and int_zero(account_delta, "orders_submitted")
        and int_zero(account_delta, "orders_canceled")
        and int_zero(account_delta, "fill_count")
        and int_zero(account_delta, "trade_count")
        and account_history.get("order_cancel_fill_trade_delta_zero") is True
        and market_delta.get("position_fingerprint_stable") is True
        and market_delta.get("open_order_fingerprint_stable") is True
        and market_delta.get("balance_fingerprint_stable") is True
        and market_delta.get("fill_trade_fingerprint_stable") is True
        and market_delta.get("order_cancel_fill_trade_delta_zero") is True
        and identity.get("account_collector_identity_ready") is True
        and identity.get("market_collector_identity_ready") is True
    )


def p10i_command_sequence_ready(command_records: dict[str, Any]) -> bool:
    labels = [
        str(row.get("label"))
        for row in list(command_records.get("commands") or [])
        if isinstance(row, dict)
    ]
    return labels == [
        "pre_control_snapshot",
        "remote_stdout_pit_safe_v2v3_account_collector",
        "remote_stdout_market_and_fingerprint_collector",
        "remote_single_cycle_live_delta_canary_order_submitter",
        "post_control_snapshot",
    ]


def owner_decision_record(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P10J_DECISION
    return {
        "contract_version": "hv_balanced_12factor_p10j_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": (
            "review_p10i_retained_evidence_for_limited_live_delta_candidate_"
            "executor_path_discussion_only"
        ),
        "recorded_at_utc": iso_z(now),
        "p10j_review_approved": approved,
        "limited_live_delta_candidate_executor_path_discussion_allowed": approved,
        "live_order_submission_approved": False,
        "candidate_executor_path_execution_approved": False,
        "continuous_automated_order_flow_approved": False,
        "timer_path_load_approved": False,
        "supervisor_invocation_approved": False,
    }


def build_p10j(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof"
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p10i_path = latest_p10i_summary(args)
    p10i = load_optional(p10i_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    plan_path = source_output_path(p10i, "canary_order_plan")
    submission_path = source_output_path(p10i, "remote_single_cycle_live_delta_canary_order_submission")
    control_path = source_output_path(p10i, "control_boundary_readback")
    account_delta_path = source_output_path(p10i, "account_delta_acceptance")
    account_history_path = source_output_path(p10i, "account_history_delta_acceptance")
    market_delta_path = source_output_path(p10i, "market_proof_collection_delta_acceptance")
    identity_path = source_output_path(p10i, "remote_runner_identity_readback")
    command_records_path = source_output_path(p10i, "command_records")
    manifest_path = source_output_path(p10i, "proof_artifact_manifest")
    candidate_delta_path = source_output_path(p10i, "candidate_delta_binding")

    plan = load_optional(plan_path)
    submission = load_optional(submission_path)
    control = load_optional(control_path)
    account_delta = load_optional(account_delta_path)
    account_history = load_optional(account_history_path)
    market_delta = load_optional(market_delta_path)
    identity = load_optional(identity_path)
    command_records = load_optional(command_records_path)
    manifest = load_optional(manifest_path)
    candidate_delta = load_optional(candidate_delta_path)
    owner_record = owner_decision_record(args, started_at)

    gates = {
        "owner_decision_p10j_review_recorded": str(args.owner_decision) == APPROVE_P10J_DECISION,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p10i_summary_exists": bool(p10i),
        "p10i_summary_ready_for_review": p10i_summary_ready(p10i),
        "p10i_candidate_delta_binding_ready": candidate_delta.get("status") == "ready"
        and candidate_delta.get("side") == p10i.get("candidate_delta_side")
        and candidate_delta.get("side_source") == "P10G.target_plan_diff.target_notional_delta_usdt"
        and decimal_value(candidate_delta.get("canary_notional_usdt")) == MAX_NOTIONAL_USDT,
        "p10i_canary_order_plan_ready": p10i_plan_ready(plan, p10i),
        "p10i_remote_submission_ready": p10i_submission_ready(submission, p10i),
        "p10i_control_boundary_ready": p10i_control_ready(control),
        "p10i_delta_acceptance_ready": p10i_delta_acceptance_ready(
            account_delta,
            account_history,
            market_delta,
            identity,
        ),
        "p10i_command_sequence_expected": p10i_command_sequence_ready(command_records),
        "p10i_manifest_complete_enough": int(manifest.get("artifact_count") or 0) >= 13
        and bool(dict(manifest.get("self") or {}).get("sha256")),
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"
    sufficient_for_discussion = status == "ready"

    review = {
        "contract_version": "hv_balanced_12factor_p10j_p10i_retained_evidence_review.v1",
        "review_only": True,
        "p10i_retained_evidence_sufficient_for_p10j_review": sufficient_for_discussion,
        "p10i_sufficient_for_limited_live_delta_candidate_executor_path_discussion": sufficient_for_discussion,
        "p10i_sufficient_for_live_order_submission_without_new_gate": False,
        "p10i_sufficient_for_candidate_executor_path_execution_without_new_gate": False,
        "p10i_sufficient_for_continuous_automated_order_flow": False,
        "positive_findings": [
            "single bounded P10G/P10H-hash-bound live_delta canary submitted exactly once",
            "BTCUSDT post-only GTX order accepted as NEW then canceled",
            "executed quantity stayed zero and no trade/fill was recorded",
            "post-run open orders returned to zero",
            "remote control boundary stayed unchanged",
            "timer/supervisor/executor target-plan paths were not touched",
        ],
        "required_next_discussion_constraints": {
            "scope_type": "discussion_and_scope_definition_only",
            "max_cycles_to_discuss": 1,
            "candidate_path_mode": "limited_single_cycle_canary_discussion_only",
            "default_order_state": "disabled_until_separate_execution_gate",
            "continuous_automated_order_flow": "not_allowed",
            "must_define_candidate_plan_hash_binding": True,
            "must_define_exact_executor_target_plan_replacement_semantics": True,
            "must_define_baseline_fallback": True,
            "must_define_kill_switch": True,
            "must_define_max_notional_and_symbol_universe": True,
            "must_define_post_run_reconciliation": True,
        },
        "checks": gates,
    }
    non_auth = {
        "contract_version": "hv_balanced_12factor_p10j_non_authorization.v1",
        "authorizations": {
            "review_p10i_retained_evidence": str(args.owner_decision) == APPROVE_P10J_DECISION,
            "allow_future_limited_live_delta_candidate_executor_path_discussion_scope_gate": sufficient_for_discussion,
            "live_order_submission_in_p10j": False,
            "candidate_executor_path_execution_in_p10j": False,
            "candidate_target_plan_replacement_in_p10j": False,
            "executor_input_mutation_in_p10j": False,
            "timer_path_load_in_p10j": False,
            "supervisor_invocation_in_p10j": False,
            "remote_execution_in_p10j": False,
            "remote_sync_in_p10j": False,
            "remote_file_write_in_p10j": False,
            "continuous_automated_order_flow": False,
            "stage_governance_change": False,
        },
    }
    control_review = {
        "contract_version": "hv_balanced_12factor_p10j_control_boundary.v1",
        "scope": "retained_evidence_review_only",
        "ssh_invoked": False,
        "remote_network_connection_performed": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "live_order_submission_performed": False,
        "candidate_execution_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "timer_path_loaded": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }

    proof_files = {
        "p10i_retained_evidence_review": proof_root / "p10i_retained_evidence_review.json",
        "non_authorization": proof_root / "non_authorization.json",
        "control_boundary_readback": proof_root / "control_boundary_readback.json",
        "owner_decision_record": root / "owner_decision_record.json",
    }
    write_json(proof_files["p10i_retained_evidence_review"], review)
    write_json(proof_files["non_authorization"], non_auth)
    write_json(proof_files["control_boundary_readback"], control_review)
    write_json(proof_files["owner_decision_record"], owner_record)
    review_manifest_path = proof_root / "proof_artifact_manifest.json"
    review_manifest = {
        "contract_version": "hv_balanced_12factor_p10j_proof_artifact_manifest.v1",
        "artifact_count": len(proof_files),
        "artifacts": {key: evidence_file(path) for key, path in sorted(proof_files.items())},
    }
    write_json(review_manifest_path, review_manifest)
    review_manifest["self"] = evidence_file(review_manifest_path)
    write_json(review_manifest_path, review_manifest)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "blockers": blockers,
        "p10j_review_p10i_single_cycle_live_delta_canary_ready": status == "ready",
        "p10i_retained_evidence_sufficient_for_p10j_review": sufficient_for_discussion,
        "p10i_sufficient_for_limited_live_delta_candidate_executor_path_discussion": sufficient_for_discussion,
        "p10i_sufficient_for_live_order_submission_without_new_gate": False,
        "p10i_sufficient_for_candidate_executor_path_execution_without_new_gate": False,
        "p10i_sufficient_for_continuous_automated_order_flow": False,
        "allowed_scope_after_p10j": "discussion_and_scope_definition_only",
        "eligible_for_future_p10k_scope_definition_gate": sufficient_for_discussion,
        "live_order_submission_authorized": False,
        "candidate_executor_path_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automated_order_flow_authorized": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "p10i_candidate_delta_side": p10i.get("candidate_delta_side"),
        "p10i_candidate_delta_notional_usdt": p10i.get("candidate_delta_notional_usdt"),
        "p10i_canary_notional_usdt": p10i.get("canary_notional_usdt"),
        "p10i_canary_quantity": p10i.get("canary_quantity"),
        "p10i_orders_submitted": p10i.get("orders_submitted"),
        "p10i_orders_canceled": p10i.get("orders_canceled"),
        "p10i_fill_count": p10i.get("fill_count"),
        "p10i_trade_count": p10i.get("trade_count"),
        "p10i_remote_control_boundary_unchanged": p10i.get("remote_control_boundary_unchanged"),
        "source_evidence": {
            "p10i_summary": evidence_file(p10i_path),
            "p10i_candidate_delta_binding": evidence_file(candidate_delta_path),
            "p10i_canary_order_plan": evidence_file(plan_path),
            "p10i_remote_single_cycle_live_delta_canary_order_submission": evidence_file(submission_path),
            "p10i_control_boundary_readback": evidence_file(control_path),
            "p10i_account_delta_acceptance": evidence_file(account_delta_path),
            "p10i_account_history_delta_acceptance": evidence_file(account_history_path),
            "p10i_market_proof_collection_delta_acceptance": evidence_file(market_delta_path),
            "p10i_remote_runner_identity_readback": evidence_file(identity_path),
            "p10i_command_records": evidence_file(command_records_path),
            "p10i_proof_artifact_manifest": evidence_file(manifest_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "gates": gates,
        "allowed_next_gate": P10K_GATE,
        "allowed_next_gate_scope": P10K_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "output_files": {
            "summary": str(root / "summary.json"),
            "report": str(root / "p10j_review_p10i_single_cycle_live_delta_canary.md"),
            "proof_artifact_manifest": str(review_manifest_path),
            **{key: str(path) for key, path in proof_files.items()},
        },
    }
    write_json(root / "summary.json", summary)
    (root / "p10j_review_p10i_single_cycle_live_delta_canary.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    return summary, 0 if status == "ready" else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced 12-Factor P10J P10I Single-Cycle Canary Review",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P10J is retained-evidence review only. It decides whether P10I is sufficient for a limited live_delta / candidate executor-path discussion, not for execution or continuous automation.",
        "",
        "```text",
        "sufficient_for_limited_discussion = "
        f"{str(bool(summary['p10i_sufficient_for_limited_live_delta_candidate_executor_path_discussion'])).lower()}",
        "sufficient_for_live_order_submission_without_new_gate = false",
        "sufficient_for_candidate_executor_path_execution_without_new_gate = false",
        "sufficient_for_continuous_automated_order_flow = false",
        f"p10i_candidate_delta_side = {summary['p10i_candidate_delta_side']}",
        f"p10i_canary_quantity = {summary['p10i_canary_quantity']}",
        f"p10i_orders_submitted = {summary['p10i_orders_submitted']}",
        f"p10i_orders_canceled = {summary['p10i_orders_canceled']}",
        f"p10i_fill_count = {summary['p10i_fill_count']}",
        "live_order_submission_authorized = false",
        "candidate_executor_path_execution_authorized = false",
        "continuous_automated_order_flow_authorized = false",
        "```",
        "",
        "## Blockers",
        "",
    ]
    blockers = list(summary.get("blockers") or [])
    lines.extend([f"- `{item}`" for item in blockers] if blockers else ["- none"])
    lines.extend(["", "## Allowed Next Gate", "", "```text", str(summary["allowed_next_gate"]), "```", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p10j(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
