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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cb_fresh_remote_proof_collection_review_package import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    TARGET_DEPLOY_ROOT_HINT,
    TARGET_RUNNER_IDENTITY_HINT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ce_read_only_fresh_remote_proof_collection import (  # noqa: E402
    CONTRACT_VERSION as P9CE_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CE_PARENT,
    P9CF_GATE,
    P9CF_SCOPE,
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


CONTRACT_VERSION = (
    "hv_balanced_dth60_coinglass_phase9cf_review_p9ce_read_only_fresh_remote_proof_collection.v1"
)
APPROVE_P9CF_DECISION = (
    "approve_p9cf_review_p9ce_read_only_fresh_remote_proof_collection_only_no_remote_no_order_no_execution"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9cf_review_p9ce_read_only_fresh_remote_proof_collection"
)
P9CG_GATE = (
    "P9CG_define_live_order_readiness_blocker_resolution_scope_only_if_separately_requested"
)
P9CG_SCOPE = (
    "define_scope_to_resolve_or_formally_accept_p9ce_account_can_trade_blocker_before_any_live_order_gate"
)
LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE = "account_can_trade_false_or_missing"

EXPECTED_P9CE_ARTIFACT_KEYS = {
    "baseline_candidate_plan_diff",
    "candidate_target_plan_hash_binding",
    "control_boundary_readback",
    "exchange_filter_readback",
    "fresh_order_book",
    "fresh_remote_account_read",
    "kill_switch_readback",
    "non_authorization",
    "p9bu_terms_operator_acceptance",
    "post_fill_trade_fingerprint",
    "post_open_order_fingerprint",
    "post_position_fingerprint",
    "pre_fill_trade_fingerprint",
    "pre_open_order_fingerprint",
    "pre_position_fingerprint",
    "proof_collection_delta_acceptance",
    "remote_runner_identity_readback",
    "rollback_command_readback",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review retained P9CE read-only fresh remote proof collection "
            "evidence. P9CF is local review-only: it does not SSH, read the "
            "account, read the order book, read exchange filters, collect fresh "
            "proofs, run supervisor/timer/remote paths, mutate executor input "
            "or target plans, execute the candidate, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9ce-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CF_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9cf_review_p9ce_read_only_fresh_remote_proof_collection_only_if_separately_requested"
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


def latest_p9ce_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9ce_summary).strip():
        return resolve_path(args.phase9ce_summary)
    return latest_match(P9CE_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def int_equals(payload: dict[str, Any], key: str, expected: int) -> bool:
    try:
        return int(payload.get(key)) == expected
    except (TypeError, ValueError):
        return False


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def p9ce_live_order_blockers(summary: dict[str, Any]) -> list[str]:
    blockers = sorted(
        {
            str(item)
            for item in list(summary.get("future_live_order_readiness_blockers") or [])
            if str(item).strip()
        }
    )
    if (
        summary.get("account_can_trade_pre") is not True
        or summary.get("account_can_trade_post") is not True
    ) and LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE not in blockers:
        blockers.append(LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE)
    return sorted(set(blockers))


def p9ce_summary_ready(summary: dict[str, Any]) -> bool:
    live_blockers = p9ce_live_order_blockers(summary)
    return (
        summary.get("contract_version") == P9CE_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9ce_read_only_fresh_remote_proof_collection_ready")
        is True
        and summary.get("fresh_remote_proof_collection_performed_in_p9ce") is True
        and summary.get("fresh_remote_account_read_performed") is True
        and summary.get("fresh_order_book_read_performed") is True
        and summary.get("exchange_filter_read_performed") is True
        and summary.get("target_runner_identity_hint") == TARGET_RUNNER_IDENTITY_HINT
        and summary.get("target_deploy_root_hint") == TARGET_DEPLOY_ROOT_HINT
        and summary.get("target_runner_identity_proven_in_p9ce") is True
        and summary.get("target_deploy_root_proven_in_p9ce") is True
        and summary.get("remote_execution_performed") is True
        and summary.get("remote_execution_scope") == "stdout_read_only_collector_only"
        and int_equals(summary, "remote_files_written", 0)
        and summary.get("remote_sync_performed") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("production_timer_service_load_authorized") is False
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("position_fingerprint_stable") is True
        and summary.get("open_order_fingerprint_stable") is True
        and summary.get("balance_fingerprint_stable") is True
        and summary.get("fill_trade_fingerprint_stable") is True
        and summary.get("order_cancel_fill_trade_delta_zero") is True
        and summary.get("remote_control_boundary_unchanged") is True
        and int_equals(summary, "open_order_count_pre", 0)
        and int_equals(summary, "open_order_count_post", 0)
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and summary.get("canary_symbol") == CANARY_SYMBOL
        and summary.get("canary_side") == CANARY_SIDE
        and float(summary.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(summary.get("max_notional_usdt") or 0)
        == DEFAULT_MAX_NOTIONAL_USDT
        and int(summary.get("max_orders_per_cycle") or 0)
        == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(summary.get("max_symbols_per_cycle") or 0)
        == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and summary.get("order_type") == DEFAULT_ORDER_TYPE
        and summary.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and summary.get("market_orders_allowed") is False
        and summary.get("only_distance_to_high_60_contribution_changed") is True
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE in live_blockers
        and summary.get("allowed_next_gate") == P9CF_GATE
        and summary.get("allowed_next_gate_scope") == P9CF_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def proof_manifest_ready(manifest: dict[str, Any]) -> bool:
    artifacts = dict(manifest.get("artifacts") or {})
    return (
        manifest.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ce_proof_manifest.v1"
        and int(manifest.get("artifact_count") or 0) == len(EXPECTED_P9CE_ARTIFACT_KEYS)
        and set(artifacts) == EXPECTED_P9CE_ARTIFACT_KEYS
        and all(
            dict(entry).get("exists") is True and bool(dict(entry).get("sha256"))
            for entry in artifacts.values()
        )
        and dict(manifest.get("self") or {}).get("exists") is True
        and bool(dict(manifest.get("self") or {}).get("sha256"))
    )


def delta_ready(delta: dict[str, Any]) -> bool:
    return (
        delta.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ce_delta_acceptance.v1"
        and delta.get("position_fingerprint_stable") is True
        and delta.get("open_order_fingerprint_stable") is True
        and delta.get("balance_fingerprint_stable") is True
        and delta.get("fill_trade_fingerprint_stable") is True
        and delta.get("position_delta_zero_or_stable") is True
        and delta.get("balance_delta_zero_or_stable") is True
        and delta.get("order_cancel_fill_trade_delta_zero") is True
        and int_equals(delta, "open_order_count_pre", 0)
        and int_equals(delta, "open_order_count_post", 0)
        and delta.get("order_history_hash_pre") == delta.get("order_history_hash_post")
        and delta.get("trade_history_hash_pre") == delta.get("trade_history_hash_post")
        and int_zero(delta, "orders_submitted")
        and int_zero(delta, "orders_canceled")
        and int_zero(delta, "fill_count")
        and int_zero(delta, "trade_count")
    )


def control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ce_control_boundary.v1"
        and control.get("scope") == "read_only_fresh_remote_proof_collection_stdout_only"
        and control.get("ssh_invoked") is True
        and control.get("remote_network_connection_performed") is True
        and int_equals(control, "remote_files_written", 0)
        and control.get("remote_sync_performed") is False
        and control.get("fresh_remote_account_read_performed") is True
        and control.get("fresh_order_book_read_performed") is True
        and control.get("exchange_filter_read_performed") is True
        and control.get("entered_timer_path") is False
        and control.get("ran_supervisor") is False
        and control.get("candidate_execution_performed") is False
        and control.get("candidate_entered_actual_executor_target_plan_path") is False
        and control.get("live_order_submission_performed") is False
        and control.get("target_plan_replaced") is False
        and control.get("executor_input_changed") is False
        and control.get("live_config_changed") is False
        and control.get("operator_state_changed") is False
        and control.get("timer_state_changed") is False
        and int_zero(control, "orders_submitted")
        and int_zero(control, "orders_canceled")
        and int_zero(control, "fill_count")
        and int_zero(control, "trade_count")
    )


def non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ce_non_authorization.v1"
        and authorizations.get("p9ce_read_only_fresh_remote_proof_collection") is True
        and authorizations.get("remote_stdout_read_only_collection") is True
        and authorizations.get("remote_files_written") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("supervisor_invocation") is False
        and authorizations.get("timer_path_load") is False
        and authorizations.get("production_timer_service_load") is False
        and authorizations.get("candidate_execution") is False
        and authorizations.get("live_order_submission") is False
        and authorizations.get("target_plan_replacement") is False
        and authorizations.get("executor_input_mutation") is False
        and authorizations.get("live_config_mutation") is False
        and authorizations.get("operator_state_mutation") is False
        and authorizations.get("timer_or_service_mutation") is False
        and authorizations.get("stage_governance_change") is False
    )


def fresh_account_ready(account: dict[str, Any]) -> bool:
    pre = dict(account.get("pre") or {})
    post = dict(account.get("post") or {})
    side_effects = dict(account.get("side_effects") or {})
    future_blockers = sorted(
        {
            str(item)
            for item in (
                list(pre.get("future_live_order_readiness_blockers") or [])
                + list(post.get("future_live_order_readiness_blockers") or [])
            )
            if str(item).strip()
        }
    )
    return (
        account.get("status") == "ready"
        and pre.get("account_readable") is True
        and post.get("account_readable") is True
        and pre.get("position_mode") == "one_way"
        and post.get("position_mode") == "one_way"
        and int_equals(pre, "open_order_count", 0)
        and int_equals(post, "open_order_count", 0)
        and pre.get("egress_ip") == TARGET_RUNNER_IDENTITY_HINT.split("@")[-1]
        and post.get("egress_ip") == TARGET_RUNNER_IDENTITY_HINT.split("@")[-1]
        and LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE in future_blockers
        and pre.get("can_trade") is False
        and post.get("can_trade") is False
        and side_effects.get("only_http_get_endpoints") is True
        and int_equals(side_effects, "remote_files_written", 0)
        and side_effects.get("remote_sync_performed") is False
        and side_effects.get("supervisor_invoked") is False
        and side_effects.get("timer_path_invoked") is False
        and side_effects.get("candidate_executed") is False
        and side_effects.get("executor_input_mutated") is False
        and side_effects.get("target_plan_replaced") is False
        and int_equals(side_effects, "orders_submitted", 0)
        and int_equals(side_effects, "orders_canceled", 0)
        and int_equals(side_effects, "order_test_calls", 0)
    )


def order_book_ready(book: dict[str, Any]) -> bool:
    return (
        book.get("status") == "ready"
        and book.get("symbol") == CANARY_SYMBOL
        and book.get("endpoint") == "/fapi/v1/depth"
        and book.get("method") == "GET"
        and bool(book.get("book_hash"))
    )


def exchange_filter_ready(filters: dict[str, Any]) -> bool:
    return (
        filters.get("status") == "ready"
        and filters.get("endpoint") == "/fapi/v1/exchangeInfo"
        and filters.get("method") == "GET"
        and bool(filters.get("filters_hash"))
        and int(filters.get("symbol_count") or 0) > 0
    )


def p9bu_terms_ready(terms: dict[str, Any]) -> bool:
    return (
        terms.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ce_p9bu_terms_operator_acceptance.v1"
        and float(terms.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(terms.get("max_notional_usdt") or 0) == DEFAULT_MAX_NOTIONAL_USDT
        and int(terms.get("max_orders_per_cycle") or 0)
        == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(terms.get("max_symbols_per_cycle") or 0)
        == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and terms.get("order_type") == DEFAULT_ORDER_TYPE
        and terms.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and terms.get("market_orders_allowed") is False
        and terms.get("final_owner_live_order_gate_approval") is False
        and terms.get("live_order_gate_approved") is False
        and terms.get("candidate_execution_authorized") is False
        and terms.get("target_plan_replacement_authorized") is False
        and terms.get("executor_input_mutation_authorized") is False
    )


def hash_binding_ready(binding: dict[str, Any]) -> bool:
    return (
        binding.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ce_target_plan_hash_binding.v1"
        and bool(binding.get("baseline_target_plan_sha256"))
        and bool(binding.get("candidate_target_plan_sha256"))
        and binding.get("candidate_not_in_executor_path") is True
        and binding.get("executor_input_remains_baseline_only") is True
        and binding.get("target_plan_replacement_performed") is False
    )


def plan_diff_ready(diff: dict[str, Any]) -> bool:
    return (
        diff.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ce_baseline_candidate_plan_diff.v1"
        and bool(diff.get("baseline_target_plan_sha256"))
        and bool(diff.get("candidate_target_plan_sha256"))
        and diff.get("only_distance_to_high_60_contribution_changed") is True
        and diff.get("executor_consumes_baseline_only") is True
        and diff.get("candidate_shadow_only") is True
    )


def kill_switch_ready(kill_switch: dict[str, Any]) -> bool:
    return (
        kill_switch.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ce_kill_switch_readback.v1"
        and kill_switch.get("remote_control_boundary_unchanged") is True
        and kill_switch.get("kill_switch_or_operator_state_mutated_by_p9ce") is False
    )


def rollback_ready(rollback: dict[str, Any]) -> bool:
    return (
        rollback.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9ce_rollback_command_readback.v1"
        and rollback.get("remote_sync_performed") is False
        and int_equals(rollback, "remote_files_written", 0)
        and rollback.get("supervisor_invoked") is False
        and rollback.get("timer_path_invoked") is False
        and rollback.get("candidate_executed") is False
        and rollback.get("executor_input_mutated") is False
        and rollback.get("target_plan_replaced") is False
    )


def build_phase9cf_review_p9ce_read_only_fresh_remote_proof_collection(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cf" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9ce_summary_path = latest_p9ce_summary(args)
    p9ce = load_optional(p9ce_summary_path)
    manifest_path = source_output_path(p9ce, "proof_artifact_manifest")
    delta_path = source_output_path(p9ce, "proof_collection_delta_acceptance")
    control_path = source_output_path(p9ce, "control_boundary_readback")
    matrix_path = source_output_path(p9ce, "non_authorization")
    account_path = source_output_path(p9ce, "fresh_remote_account_read")
    book_path = source_output_path(p9ce, "fresh_order_book")
    filters_path = source_output_path(p9ce, "exchange_filter_readback")
    p9bu_path = source_output_path(p9ce, "p9bu_terms_operator_acceptance")
    binding_path = source_output_path(p9ce, "candidate_target_plan_hash_binding")
    diff_path = source_output_path(p9ce, "baseline_candidate_plan_diff")
    kill_switch_path = source_output_path(p9ce, "kill_switch_readback")
    rollback_path = source_output_path(p9ce, "rollback_command_readback")
    command_records_path = source_output_path(p9ce, "command_records")
    pre_snapshot_path = source_output_path(p9ce, "pre_control_snapshot")
    post_snapshot_path = source_output_path(p9ce, "post_control_snapshot")

    manifest = load_optional(manifest_path)
    delta = load_optional(delta_path)
    p9ce_control = load_optional(control_path)
    p9ce_matrix = load_optional(matrix_path)
    account = load_optional(account_path)
    book = load_optional(book_path)
    filters = load_optional(filters_path)
    p9bu = load_optional(p9bu_path)
    binding = load_optional(binding_path)
    diff = load_optional(diff_path)
    kill_switch = load_optional(kill_switch_path)
    rollback = load_optional(rollback_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    live_order_blockers = p9ce_live_order_blockers(p9ce)
    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CF_DECISION
    checks = {
        "owner_decision_p9cf_review_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9ce_summary_exists": bool(p9ce),
        "p9ce_summary_ready_for_retained_review": p9ce_summary_ready(p9ce),
        "p9ce_proof_manifest_ready": proof_manifest_ready(manifest),
        "p9ce_delta_acceptance_ready": delta_ready(delta),
        "p9ce_control_boundary_ready": control_ready(p9ce_control),
        "p9ce_non_authorization_ready": non_authorization_ready(p9ce_matrix),
        "p9ce_fresh_account_read_ready_with_live_order_blocker": fresh_account_ready(
            account
        ),
        "p9ce_order_book_read_ready": order_book_ready(book),
        "p9ce_exchange_filter_read_ready": exchange_filter_ready(filters),
        "p9ce_p9bu_terms_operator_acceptance_ready": p9bu_terms_ready(p9bu),
        "p9ce_candidate_target_plan_hash_binding_ready": hash_binding_ready(binding),
        "p9ce_baseline_candidate_plan_diff_ready": plan_diff_ready(diff),
        "p9ce_kill_switch_readback_ready": kill_switch_ready(kill_switch),
        "p9ce_rollback_readback_ready": rollback_ready(rollback),
        "p9ce_live_order_readiness_blocker_retained": LIVE_ORDER_BLOCKER_ACCOUNT_CAN_TRADE
        in live_order_blockers,
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers
    p9ce_sufficient_for_read_only_collection_review = ready
    p9ce_sufficient_for_live_order_gate = False

    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cf_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "review_p9ce_retained_read_only_collection_only_no_remote_no_order_no_execution",
        "recorded_at_utc": iso_z(now),
        "p9cf_review_approved": owner_decision_ok,
        "fresh_remote_proof_collection_approved": False,
        "fresh_remote_account_read_approved": False,
        "remote_execution_approved": False,
        "live_order_gate_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    review = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cf_sufficiency_review.v1",
        "run_id": run_id,
        "status": "ready" if ready else "blocked",
        "review_scope": "p9ce_retained_read_only_fresh_remote_proof_collection_before_any_live_order_or_executor_path_change",
        "checks": checks,
        "blockers": blockers,
        "p9ce_sufficient_for_read_only_collection_review": p9ce_sufficient_for_read_only_collection_review,
        "p9ce_sufficient_for_live_order_gate": p9ce_sufficient_for_live_order_gate,
        "live_order_readiness_blockers": live_order_blockers,
        "read_only_collection_review_conclusion": (
            "p9ce_retained_proof_sufficient_for_read_only_collection_review"
            if ready
            else "p9ce_retained_proof_not_sufficient_for_read_only_collection_review"
        ),
        "live_order_gate_conclusion": "blocked_until_account_can_trade_false_or_missing_is_resolved_or_formally_accepted_by_later_gate",
        "fresh_remote_collection_performed_in_p9cf": False,
        "live_order_gate_approved_in_p9cf": False,
    }
    prerequisites = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cf_future_gate_prerequisites.v1",
        "run_id": run_id,
        "allowed_next_gate": P9CG_GATE,
        "allowed_next_gate_scope": P9CG_SCOPE,
        "required_before_any_future_live_order_gate": [
            "separately requested P9CG blocker-resolution scope gate",
            "resolve or formally owner-accept account_can_trade_false_or_missing",
            "new fresh remote account-read after the blocker-resolution decision",
            "new pre/post position fingerprint and zero order/cancel/fill/trade delta proof",
            "new baseline-only executor and candidate-shadow-only hash binding proof",
            "explicit live-order gate with risk/order terms before any order path mutation",
        ],
        "p9cf_may_not_be_used_as_live_order_approval": True,
        "live_order_gate_ready_after_p9cf": False,
        "candidate_executor_path_ready_after_p9cf": False,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cf_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "review_p9ce_read_only_fresh_remote_proof_collection": ready,
            "allow_future_p9cg_blocker_resolution_scope_gate": ready,
            "fresh_remote_proof_collection": False,
            "fresh_remote_account_read": False,
            "fresh_order_book_read": False,
            "exchange_filter_read": False,
            "remote_execution": False,
            "remote_sync": False,
            "live_order_gate_approval": False,
            "actual_candidate_executor_target_path_entry": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "actual_target_plan_replacement": False,
            "actual_executor_input_mutation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_or_service_mutation": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
            "supervisor_invocation": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cf_control_boundary.v1",
        "run_id": run_id,
        "scope": "p9ce_retained_evidence_review_only",
        "ssh_invoked": False,
        "remote_network_connection_performed": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "fresh_proofs_collected": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "candidate_entered_actual_executor_target_plan_path": False,
        "live_order_submission_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }

    owner_path = root / "owner_decision_record.json"
    review_path = proof_root / "sufficiency_review.json"
    prereq_path = proof_root / "future_gate_prerequisites.json"
    non_auth_path = proof_root / "non_authorization.json"
    control_path_out = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9cf_review_p9ce_read_only_collection.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "sufficiency_review": str(review_path),
        "future_gate_prerequisites": str(prereq_path),
        "non_authorization": str(non_auth_path),
        "control_boundary_readback": str(control_path_out),
        "report": str(report_path),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "p9cf_review_p9ce_read_only_fresh_remote_proof_collection_ready": ready,
        "p9ce_sufficient_for_read_only_collection_review": p9ce_sufficient_for_read_only_collection_review,
        "p9ce_sufficient_for_live_order_gate": p9ce_sufficient_for_live_order_gate,
        "eligible_for_future_p9cg_live_order_readiness_blocker_scope_gate": ready,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "live_order_readiness_blockers": live_order_blockers,
        "fresh_remote_proof_collection_performed_in_p9cf": False,
        "fresh_proofs_collected_in_p9cf": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "target_runner_identity_hint": TARGET_RUNNER_IDENTITY_HINT,
        "target_deploy_root_hint": TARGET_DEPLOY_ROOT_HINT,
        "target_runner_identity_proven_in_p9cf": False,
        "target_deploy_root_proven_in_p9cf": False,
        "target_runner_identity_proven_in_source_p9ce": p9ce.get(
            "target_runner_identity_proven_in_p9ce"
        )
        is True,
        "target_deploy_root_proven_in_source_p9ce": p9ce.get(
            "target_deploy_root_proven_in_p9ce"
        )
        is True,
        "source_p9ce_remote_execution_scope": p9ce.get("remote_execution_scope"),
        "source_p9ce_remote_files_written": p9ce.get("remote_files_written"),
        "source_p9ce_remote_sync_performed": p9ce.get("remote_sync_performed"),
        "source_p9ce_open_position_count_pre": p9ce.get("open_position_count_pre"),
        "source_p9ce_open_position_count_post": p9ce.get("open_position_count_post"),
        "source_p9ce_open_order_count_pre": p9ce.get("open_order_count_pre"),
        "source_p9ce_open_order_count_post": p9ce.get("open_order_count_post"),
        "source_p9ce_account_can_trade_pre": p9ce.get("account_can_trade_pre"),
        "source_p9ce_account_can_trade_post": p9ce.get("account_can_trade_post"),
        "source_p9ce_order_cancel_fill_trade_delta_zero": p9ce.get(
            "order_cancel_fill_trade_delta_zero"
        ),
        "source_p9ce_remote_control_boundary_unchanged": p9ce.get(
            "remote_control_boundary_unchanged"
        ),
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "timer_or_service_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "production_timer_service_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "canary_symbol": CANARY_SYMBOL,
        "canary_side": CANARY_SIDE,
        "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
        "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "market_orders_allowed": False,
        "baseline_target_plan_sha256": p9ce.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9ce.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9ce.get(
            "only_distance_to_high_60_contribution_changed"
        ),
        "allowed_next_gate": P9CG_GATE,
        "allowed_next_gate_scope": P9CG_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9ce_summary": evidence_file(p9ce_summary_path),
            "phase9ce_proof_manifest": evidence_file(manifest_path),
            "phase9ce_delta_acceptance": evidence_file(delta_path),
            "phase9ce_control_boundary": evidence_file(control_path),
            "phase9ce_non_authorization": evidence_file(matrix_path),
            "phase9ce_fresh_remote_account_read": evidence_file(account_path),
            "phase9ce_fresh_order_book": evidence_file(book_path),
            "phase9ce_exchange_filter_readback": evidence_file(filters_path),
            "phase9ce_p9bu_terms_operator_acceptance": evidence_file(p9bu_path),
            "phase9ce_candidate_target_plan_hash_binding": evidence_file(
                binding_path
            ),
            "phase9ce_baseline_candidate_plan_diff": evidence_file(diff_path),
            "phase9ce_kill_switch_readback": evidence_file(kill_switch_path),
            "phase9ce_rollback_command_readback": evidence_file(rollback_path),
            "phase9ce_command_records": evidence_file(command_records_path),
            "phase9ce_pre_control_snapshot": evidence_file(pre_snapshot_path),
            "phase9ce_post_control_snapshot": evidence_file(post_snapshot_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(review_path, review)
    write_json(prereq_path, prerequisites)
    write_json(non_auth_path, non_authorization)
    write_json(control_path_out, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def build_phase9cf(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    return build_phase9cf_review_p9ce_read_only_fresh_remote_proof_collection(
        args,
        now_fn=now_fn,
    )


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CF Review P9CE Read-Only Fresh Remote Proof Collection",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CF reviews retained P9CE evidence only. It does not SSH, read the account, read the order book, collect fresh proofs, run supervisor or timer paths, mutate config/operator/timer/executor state, execute the candidate, replace target plans, cancel orders, or submit orders.",
        "",
        "## Review Result",
        "",
        "```text",
        "p9cf_review_p9ce_read_only_fresh_remote_proof_collection_ready = "
        f"{str(bool(summary['p9cf_review_p9ce_read_only_fresh_remote_proof_collection_ready'])).lower()}",
        "p9ce_sufficient_for_read_only_collection_review = "
        f"{str(bool(summary['p9ce_sufficient_for_read_only_collection_review'])).lower()}",
        "p9ce_sufficient_for_live_order_gate = false",
        "eligible_for_future_live_order_submission = false",
        "eligible_for_future_candidate_execution = false",
        "fresh_remote_account_read_performed = false",
        "fresh_order_book_read_performed = false",
        "exchange_filter_read_performed = false",
        "remote_execution_authorized = false",
        "live_order_submission_authorized = false",
        "candidate_execution_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
        "orders_submitted = 0",
        "orders_canceled = 0",
        "fill_count = 0",
        "trade_count = 0",
        "```",
        "",
        "## Source P9CE Evidence",
        "",
        "```text",
        f"source_p9ce_remote_execution_scope = {summary['source_p9ce_remote_execution_scope']}",
        f"source_p9ce_remote_files_written = {summary['source_p9ce_remote_files_written']}",
        "source_p9ce_remote_sync_performed = "
        f"{str(bool(summary['source_p9ce_remote_sync_performed'])).lower()}",
        f"source_p9ce_open_position_count_pre = {summary['source_p9ce_open_position_count_pre']}",
        f"source_p9ce_open_position_count_post = {summary['source_p9ce_open_position_count_post']}",
        f"source_p9ce_open_order_count_pre = {summary['source_p9ce_open_order_count_pre']}",
        f"source_p9ce_open_order_count_post = {summary['source_p9ce_open_order_count_post']}",
        "source_p9ce_account_can_trade_pre = "
        f"{str(bool(summary['source_p9ce_account_can_trade_pre'])).lower()}",
        "source_p9ce_account_can_trade_post = "
        f"{str(bool(summary['source_p9ce_account_can_trade_post'])).lower()}",
        "source_p9ce_order_cancel_fill_trade_delta_zero = "
        f"{str(bool(summary['source_p9ce_order_cancel_fill_trade_delta_zero'])).lower()}",
        "source_p9ce_remote_control_boundary_unchanged = "
        f"{str(bool(summary['source_p9ce_remote_control_boundary_unchanged'])).lower()}",
        "```",
        "",
        "## Live-Order Readiness Blockers",
        "",
        "```text",
        "live_order_readiness_blockers = "
        + ", ".join(summary["live_order_readiness_blockers"]),
        "```",
        "",
        "## Allowed Next Gate",
        "",
        "```text",
        str(summary["allowed_next_gate"]),
        str(summary["allowed_next_gate_scope"]),
        "allowed_next_gate_must_be_separately_requested = true",
        "```",
        "",
        "P9CF confirms the retained P9CE proof is sufficient for read-only collection review, but it is not sufficient for live-order discussion because the P9CE account read retained `account_can_trade=false`.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9cf(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    print(
        "p9ce_sufficient_for_read_only_collection_review="
        + str(bool(summary["p9ce_sufficient_for_read_only_collection_review"])).lower()
    )
    print("p9ce_sufficient_for_live_order_gate=false")
    print(
        "live_order_readiness_blockers="
        + ",".join(str(item) for item in summary["live_order_readiness_blockers"])
    )
    print("orders_submitted=0")
    print("fill_count=0")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
