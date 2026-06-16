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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9df_define_limited_live_delta_candidate_executor_path_canary_discussion_scope import (  # noqa: E402
    CONTRACT_VERSION as P9DF_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9DF_PARENT,
    P9DG_GATE,
    P9DG_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9dg_limited_live_delta_candidate_executor_path_"
    "canary_proposal_package.v1"
)
APPROVE_P9DG_DECISION = (
    "approve_p9dg_prepare_limited_live_delta_candidate_executor_path_canary_proposal_package_only"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9dg_limited_live_delta_candidate_executor_path_canary_proposal_package"
)
P9DH_GATE = (
    "P9DH_review_limited_live_delta_candidate_executor_path_canary_proposal_package_only_if_separately_requested"
)
P9DH_SCOPE = (
    "review_p9dg_single_cycle_limited_live_delta_candidate_executor_path_canary_proposal_no_execution"
)

DEFAULT_MAX_NOTIONAL_PER_ORDER_USDT = 75.0
DEFAULT_MAX_GROSS_TURNOVER_USDT = 150.0
DEFAULT_MAX_ORDERS_TOTAL = 2
DEFAULT_MAX_SYMBOLS_TOTAL = 1
DEFAULT_ORDER_TYPE = "limit_ioc"
DEFAULT_TIME_IN_FORCE = "IOC"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the P9DG proposal package for a future single-cycle limited "
            "live_delta / candidate executor-path canary. P9DG writes proposal "
            "artifacts only; it does not SSH, call Binance, execute candidate "
            "logic, replace target plans, mutate executor input, load timer or "
            "supervisor paths, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9df-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9DG_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9dg_prepare_limited_live_delta_candidate_executor_path_"
            "canary_proposal_package_only"
        ),
    )
    parser.add_argument(
        "--max-notional-per-order-usdt",
        type=float,
        default=DEFAULT_MAX_NOTIONAL_PER_ORDER_USDT,
    )
    parser.add_argument(
        "--max-gross-turnover-usdt",
        type=float,
        default=DEFAULT_MAX_GROSS_TURNOVER_USDT,
    )
    parser.add_argument("--max-orders-total", type=int, default=DEFAULT_MAX_ORDERS_TOTAL)
    parser.add_argument("--max-symbols-total", type=int, default=DEFAULT_MAX_SYMBOLS_TOTAL)
    parser.add_argument("--order-type", default=DEFAULT_ORDER_TYPE)
    parser.add_argument("--time-in-force", default=DEFAULT_TIME_IN_FORCE)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_p9df_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9df_summary).strip():
        return resolve_path(args.phase9df_summary)
    return latest_match(P9DF_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9df_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9DF_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get(
            "p9df_limited_live_delta_candidate_executor_path_canary_discussion_scope_ready"
        )
        is True
        and summary.get("p9de_sufficient_for_p9df_scope_definition") is True
        and summary.get("scope_definition_only") is True
        and summary.get("scope_label")
        == "single_cycle_limited_live_delta_candidate_executor_path_canary_discussion"
        and summary.get("allowed_scope_after_p9df") == "proposal_package_preparation_only"
        and summary.get("eligible_for_future_p9dg_proposal_package_gate") is True
        and int(summary.get("max_cycles_discussion_scope") or 0) == 1
        and summary.get("default_order_state") == "disabled_until_separate_execution_gate"
        and summary.get("continuous_automated_order_flow_allowed") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_executor_path_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("remote_sync_performed") is False
        and int_zero(summary, "remote_files_written")
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and summary.get("allowed_next_gate") == P9DG_GATE
        and summary.get("allowed_next_gate_scope") == P9DG_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def p9df_scope_ready(scope: dict[str, Any]) -> bool:
    hard_limits = dict(scope.get("hard_limits_for_discussion") or {})
    must_define = set(scope.get("must_define_before_any_future_execution_gate") or [])
    not_authorized = set(scope.get("not_authorized_by_this_scope") or [])
    return (
        scope.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9df_limited_live_delta_candidate_executor_path_canary_discussion_scope.v1"
        and scope.get("scope_only") is True
        and scope.get("scope_label")
        == "single_cycle_limited_live_delta_candidate_executor_path_canary_discussion"
        and int(hard_limits.get("max_cycles") or 0) == 1
        and hard_limits.get("continuous_automated_order_flow") is False
        and hard_limits.get("default_order_state") == "disabled_until_separate_execution_gate"
        and hard_limits.get("default_candidate_execution") == "not_executed"
        and hard_limits.get("default_target_plan_replacement") == "not_replaced"
        and hard_limits.get("default_executor_input_mutation") == "not_mutated"
        and hard_limits.get("must_remain_stage_3_human_approved_execution") is True
        and "max notional per order and gross turnover" in must_define
        and "allowed order types and time-in-force" in must_define
        and "candidate target plan hash binding" in must_define
        and "baseline fallback and rollback conditions" in must_define
        and "live order submission" in not_authorized
        and "candidate executor-path execution" in not_authorized
        and "actual target-plan replacement" in not_authorized
        and "executor input mutation" in not_authorized
        and "continuous automated order flow" in not_authorized
        and scope.get("allowed_next_gate") == P9DG_GATE
        and scope.get("allowed_next_gate_scope") == P9DG_SCOPE
        and scope.get("allowed_next_gate_must_be_separately_requested") is True
    )


def p9df_non_authorization_ready(non_auth: dict[str, Any]) -> bool:
    authorizations = dict(non_auth.get("authorizations") or {})
    return (
        non_auth.get("contract_version") == "hv_balanced_dth60_coinglass_phase9df_non_authorization.v1"
        and authorizations.get("define_discussion_scope") is True
        and authorizations.get("future_p9dg_proposal_package_request_allowed") is True
        and authorizations.get("live_order_submission_in_p9df") is False
        and authorizations.get("candidate_executor_path_execution_in_p9df") is False
        and authorizations.get("candidate_target_plan_replacement_in_p9df") is False
        and authorizations.get("executor_input_mutation_in_p9df") is False
        and authorizations.get("timer_path_load_in_p9df") is False
        and authorizations.get("supervisor_invocation_in_p9df") is False
        and authorizations.get("remote_execution_in_p9df") is False
        and authorizations.get("remote_sync_in_p9df") is False
        and authorizations.get("remote_file_write_in_p9df") is False
        and authorizations.get("continuous_automated_order_flow") is False
        and authorizations.get("stage_governance_change") is False
    )


def p9df_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version") == "hv_balanced_dth60_coinglass_phase9df_control_boundary.v1"
        and control.get("scope") == "scope_definition_only"
        and control.get("ssh_invoked") is False
        and control.get("remote_network_connection_performed") is False
        and control.get("fresh_remote_account_read_performed") is False
        and control.get("fresh_order_book_read_performed") is False
        and control.get("exchange_filter_read_performed") is False
        and control.get("order_test_endpoint_called") is False
        and control.get("live_order_submission_performed") is False
        and control.get("candidate_execution_performed") is False
        and control.get("target_plan_replaced") is False
        and control.get("executor_input_changed") is False
        and control.get("entered_timer_path") is False
        and control.get("ran_supervisor") is False
        and control.get("timer_path_loaded") is False
        and control.get("remote_sync_performed") is False
        and int_zero(control, "remote_files_written")
        and int_zero(control, "orders_submitted")
        and int_zero(control, "orders_canceled")
        and int_zero(control, "fill_count")
        and int_zero(control, "trade_count")
    )


def proposal_terms(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dg_risk_order_terms.v1",
        "scope": "future_single_cycle_candidate_executor_path_canary_terms_proposal_only",
        "max_cycles_total": 1,
        "max_symbols_total": int(args.max_symbols_total),
        "max_orders_total": int(args.max_orders_total),
        "max_notional_per_order_usdt": float(args.max_notional_per_order_usdt),
        "max_gross_turnover_usdt": float(args.max_gross_turnover_usdt),
        "max_candidate_position_delta_abs_usdt": float(args.max_notional_per_order_usdt),
        "order_type": str(args.order_type or "").strip().lower(),
        "time_in_force": str(args.time_in_force or "").strip().upper(),
        "market_orders_allowed": False,
        "post_only_required": False,
        "maker_only_required": False,
        "taker_execution_allowed": True,
        "emergency_market_fallback_allowed": False,
        "reduce_only_required_for_risk_reducing_orders": True,
        "candidate_delta_source": "distance_to_high_60_contribution_only",
        "candidate_overlay_components": [
            "coinglass_top_trader_crowded_branch",
            "binance_shock_branch",
        ],
        "symbol_selection_rule": (
            "future gate must bind exactly one symbol from a fresh same-risk "
            "baseline-vs-candidate paired plan; if no eligible symbol passes "
            "filters and notional caps, the canary is no-order"
        ),
        "freshness_requirements": {
            "candidate_artifact_max_age_seconds": 60,
            "baseline_plan_max_age_seconds": 60,
            "account_read_max_age_seconds": 30,
            "position_fingerprint_max_age_seconds": 30,
            "open_order_fingerprint_max_age_seconds": 30,
            "order_fill_trade_fingerprint_max_age_seconds": 30,
            "order_book_max_age_seconds": 10,
            "exchange_filter_max_age_seconds": 300,
        },
        "pre_submit_hard_checks": [
            "fresh /fapi/v2/account.canTrade must be true",
            "fresh /fapi/v3/account may be read but must not source canTrade",
            "fresh pre position fingerprint captured",
            "fresh pre open-order fingerprint captured",
            "fresh pre order/fill/trade fingerprint captured",
            "fresh order book and exchange filters prove order can satisfy minQty and minNotional",
            "computed order notional must be <= max_notional_per_order_usdt",
            "gross turnover upper bound must be <= max_gross_turnover_usdt",
            "candidate plan hash binding must pass before executor input may be replaced",
            "kill switch readback must be available before any future submitter can run",
        ],
    }


def terms_ready(terms: dict[str, Any]) -> dict[str, bool]:
    return {
        "terms_max_cycles_one": int(terms.get("max_cycles_total") or 0) == 1,
        "terms_max_symbols_one": int(terms.get("max_symbols_total") or 0) == 1,
        "terms_max_orders_positive_bounded": 0 < int(terms.get("max_orders_total") or 0) <= 2,
        "terms_max_notional_positive": float(terms.get("max_notional_per_order_usdt") or 0) > 0,
        "terms_max_notional_bounded": float(terms.get("max_notional_per_order_usdt") or 0)
        <= DEFAULT_MAX_NOTIONAL_PER_ORDER_USDT,
        "terms_gross_turnover_bounded": float(terms.get("max_gross_turnover_usdt") or 0)
        <= DEFAULT_MAX_GROSS_TURNOVER_USDT,
        "terms_gross_turnover_covers_orders": float(terms.get("max_gross_turnover_usdt") or 0)
        >= float(terms.get("max_notional_per_order_usdt") or 0)
        * int(terms.get("max_orders_total") or 0),
        "terms_order_type_limit_ioc": terms.get("order_type") == DEFAULT_ORDER_TYPE
        and terms.get("time_in_force") == DEFAULT_TIME_IN_FORCE,
        "terms_market_orders_forbidden": terms.get("market_orders_allowed") is False,
        "terms_no_emergency_market_fallback": terms.get("emergency_market_fallback_allowed")
        is False,
        "terms_candidate_delta_source_dth60_only": (
            terms.get("candidate_delta_source") == "distance_to_high_60_contribution_only"
        ),
    }


def candidate_plan_hash_binding_contract(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dg_candidate_plan_hash_binding.v1",
        "run_id": run_id,
        "binding_scope": "future_single_cycle_canary_only",
        "required_hashes_before_future_execution": [
            "baseline_target_plan_sha256",
            "candidate_target_plan_sha256",
            "same_risk_input_sha256",
            "candidate_overlay_contribution_sha256",
            "distance_to_high_60_contribution_delta_sha256",
            "slice_metrics_sha256",
            "executor_input_plan_sha256_before_replacement",
            "executor_input_plan_sha256_after_replacement",
        ],
        "same_context_requirements": {
            "same_timestamp": True,
            "same_risk_inputs": True,
            "same_universe": True,
            "same_exchange_filters_snapshot_or_fresher_pre_submit_filter_read": True,
            "overlay_may_change_only": "distance_to_high_60_contribution",
        },
        "binding_rules": [
            "baseline target plan must be generated and hashed first",
            "candidate target plan must be generated from the same timestamp and same risk inputs",
            "candidate plan hash must differ from baseline only through distance_to_high_60 contribution",
            "future executor input replacement may proceed only if executor_input_plan_sha256_after_replacement equals candidate_target_plan_sha256",
            "future order submitter may proceed only if candidate_target_plan_sha256 equals the owner-approved canary plan hash",
            "any stale, missing, or mismatched hash forces baseline fallback and zero order submission",
        ],
        "stale_after_seconds": 60,
        "p9dg_authorizes_actual_hash_binding": False,
        "future_gate_must_collect_fresh_hashes": True,
    }


def baseline_fallback_and_kill_switch_contract(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dg_baseline_fallback_kill_switch.v1",
        "run_id": run_id,
        "baseline_fallback_policy": {
            "fallback_trigger_before_submit": [
                "missing or stale candidate plan artifact",
                "candidate plan hash mismatch",
                "executor input hash mismatch",
                "candidate delta outside distance_to_high_60 contribution",
                "fresh account, position, open-order, order/fill/trade, book, or filter proof missing",
                "order notional or gross turnover exceeds proposal terms",
                "timer/supervisor/control-boundary invariant mismatch",
            ],
            "fallback_action_before_submit": [
                "keep executor input baseline-only",
                "write no-order proof artifact",
                "submit zero candidate orders",
                "require owner review before any retry",
            ],
            "fallback_trigger_after_any_future_fill": [
                "unexpected open order remains",
                "unexpected order/cancel/fill/trade delta",
                "post position fingerprint differs from expected candidate canary plan",
                "provider, exchange, risk, or supervisor exception",
                "candidate canary realized plus unrealized drawdown exceeds 5 USDT",
            ],
            "fallback_action_after_any_future_fill": [
                "cancel candidate-scope open orders",
                "freeze further candidate cycles",
                "restore executor_target_source=baseline_only",
                "set candidate_overlay_enabled=false",
                "set live_delta_armed=false before any further candidate order gate",
                "require separate owner-approved reduce-only rollback if position must be reverted",
            ],
        },
        "kill_switch": {
            "required": True,
            "operator_action": (
                "set candidate_overlay_enabled=false; set executor_target_source=baseline_only; "
                "set live_delta_armed=false; cancel candidate-scope open orders; block candidate "
                "canary gate until owner review"
            ),
            "must_be_readable_before_submit": True,
            "must_be_rechecked_after_cycle": True,
        },
        "p9dg_executes_kill_switch": False,
        "p9dg_changes_operator_state": False,
    }


def post_run_reconciliation_contract(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dg_post_run_reconciliation.v1",
        "run_id": run_id,
        "required_post_run_readbacks": [
            "post account read using /fapi/v2/account.canTrade for canTrade",
            "post position fingerprint",
            "post open-order fingerprint",
            "post order/cancel/fill/trade delta fingerprint",
            "post executor input hash",
            "post target-plan source readback",
            "post timer/supervisor/operator/control-boundary readback",
        ],
        "acceptance_conditions_for_future_execution_gate": {
            "completed_cycles_exactly": 1,
            "candidate_symbols_at_most": 1,
            "orders_submitted_at_most": DEFAULT_MAX_ORDERS_TOTAL,
            "gross_turnover_usdt_at_most": DEFAULT_MAX_GROSS_TURNOVER_USDT,
            "open_candidate_orders_after_cycle": 0,
            "all_order_cancel_fill_trade_deltas_explained_by_candidate_plan": True,
            "post_position_matches_expected_candidate_canary_plan": True,
            "executor_input_hash_matches_expected_post_cycle_source": True,
            "candidate_overlay_disabled_or_frozen_after_cycle_until_owner_review": True,
            "no_second_cycle_without_separate_owner_gate": True,
        },
        "failure_conditions": [
            "unexplained order, cancel, fill, or trade delta",
            "open order remains after cycle",
            "post position mismatch",
            "executor input remains candidate when fallback should be baseline",
            "timer/supervisor/operator/control-boundary changed outside proposal",
            "second cycle attempted",
        ],
        "p9dg_performs_post_run_reconciliation": False,
        "future_gate_must_perform_post_run_reconciliation": True,
    }


def owner_decision_record(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9DG_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dg_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "prepare_single_cycle_limited_candidate_executor_path_canary_proposal_package_only",
        "recorded_at_utc": iso_z(now),
        "p9dg_proposal_package_preparation_approved": approved,
        "future_p9dh_review_may_be_requested": approved,
        "live_order_submission_approved": False,
        "candidate_executor_path_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "timer_path_load_approved": False,
        "supervisor_invocation_approved": False,
        "continuous_automated_order_flow_approved": False,
    }


def proposal_package(
    *,
    run_id: str,
    now: datetime,
    args: argparse.Namespace,
    terms: dict[str, Any],
    hash_binding: dict[str, Any],
    fallback: dict[str, Any],
    reconciliation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dg_proposal_package.v1",
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "owner": args.owner,
        "proposal_status": "prepared_for_future_review_only",
        "proposal_scope": "single_cycle_limited_live_delta_candidate_executor_path_canary",
        "max_notional": {
            "per_order_usdt": terms["max_notional_per_order_usdt"],
            "gross_turnover_usdt": terms["max_gross_turnover_usdt"],
            "candidate_position_delta_abs_usdt": terms["max_candidate_position_delta_abs_usdt"],
        },
        "order_type": {
            "type": terms["order_type"],
            "time_in_force": terms["time_in_force"],
            "market_orders_allowed": terms["market_orders_allowed"],
            "emergency_market_fallback_allowed": terms[
                "emergency_market_fallback_allowed"
            ],
        },
        "candidate_plan_hash_binding": hash_binding,
        "baseline_fallback_and_kill_switch": fallback,
        "post_run_reconciliation": reconciliation,
        "future_execution_gate_required": True,
        "future_review_gate": P9DH_GATE,
        "p9dg_authorizes_execution": False,
        "p9dg_authorizes_live_order": False,
        "p9dg_authorizes_target_plan_replacement": False,
        "p9dg_authorizes_executor_input_mutation": False,
        "p9dg_authorizes_timer_or_supervisor_load": False,
        "p9dg_authorizes_continuous_automation": False,
    }


def build_phase9dg(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9dg" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9df_path = latest_p9df_summary(args)
    p9df = load_optional(p9df_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    scope_path = source_output_path(p9df, "discussion_scope")
    non_auth_path = source_output_path(p9df, "non_authorization")
    control_path = source_output_path(p9df, "control_boundary_readback")
    scope = load_optional(scope_path)
    p9df_non_auth = load_optional(non_auth_path)
    p9df_control = load_optional(control_path)
    terms = proposal_terms(args)
    hash_binding = candidate_plan_hash_binding_contract(run_id)
    fallback = baseline_fallback_and_kill_switch_contract(run_id)
    reconciliation = post_run_reconciliation_contract(run_id)
    owner_record = owner_decision_record(args, started_at)
    term_checks = terms_ready(terms)

    gates = {
        "owner_decision_p9dg_proposal_package_recorded": str(args.owner_decision)
        == APPROVE_P9DG_DECISION,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9df_summary_exists": bool(p9df),
        "p9df_summary_ready_for_p9dg": p9df_summary_ready(p9df),
        "p9df_discussion_scope_ready": p9df_scope_ready(scope),
        "p9df_non_authorization_ready": p9df_non_authorization_ready(p9df_non_auth),
        "p9df_control_boundary_ready": p9df_control_ready(p9df_control),
        **term_checks,
        "proposal_hash_binding_defines_required_hashes": len(
            hash_binding["required_hashes_before_future_execution"]
        )
        >= 6,
        "proposal_hash_binding_requires_same_context": all(
            bool(value)
            for key, value in hash_binding["same_context_requirements"].items()
            if key != "overlay_may_change_only"
        )
        and hash_binding["same_context_requirements"]["overlay_may_change_only"]
        == "distance_to_high_60_contribution",
        "proposal_baseline_fallback_defined": bool(
            fallback["baseline_fallback_policy"]["fallback_trigger_before_submit"]
        )
        and bool(fallback["baseline_fallback_policy"]["fallback_action_before_submit"]),
        "proposal_kill_switch_defined": fallback["kill_switch"]["required"] is True
        and bool(fallback["kill_switch"]["operator_action"]),
        "proposal_post_run_reconciliation_defined": reconciliation[
            "future_gate_must_perform_post_run_reconciliation"
        ]
        is True
        and reconciliation["acceptance_conditions_for_future_execution_gate"][
            "completed_cycles_exactly"
        ]
        == 1,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"
    ready = status == "ready"

    package = proposal_package(
        run_id=run_id,
        now=started_at,
        args=args,
        terms=terms,
        hash_binding=hash_binding,
        fallback=fallback,
        reconciliation=reconciliation,
    )
    non_auth = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dg_non_authorization.v1",
        "authorizations": {
            "prepare_proposal_package": ready,
            "future_p9dh_review_request_allowed": ready,
            "live_order_submission_in_p9dg": False,
            "candidate_executor_path_execution_in_p9dg": False,
            "actual_target_plan_replacement_in_p9dg": False,
            "executor_input_mutation_in_p9dg": False,
            "timer_path_load_in_p9dg": False,
            "supervisor_invocation_in_p9dg": False,
            "remote_execution_in_p9dg": False,
            "remote_sync_in_p9dg": False,
            "remote_file_write_in_p9dg": False,
            "continuous_automated_order_flow": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dg_control_boundary.v1",
        "scope": "proposal_package_preparation_only",
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
        "proposal_package": proof_root / "proposal_package.json",
        "risk_order_terms": proof_root / "risk_order_terms.json",
        "candidate_plan_hash_binding": proof_root / "candidate_plan_hash_binding.json",
        "baseline_fallback_kill_switch": proof_root / "baseline_fallback_kill_switch.json",
        "post_run_reconciliation": proof_root / "post_run_reconciliation.json",
        "non_authorization": proof_root / "non_authorization.json",
        "control_boundary_readback": proof_root / "control_boundary_readback.json",
        "owner_decision_record": root / "owner_decision_record.json",
    }
    write_json(proof_files["proposal_package"], package)
    write_json(proof_files["risk_order_terms"], terms)
    write_json(proof_files["candidate_plan_hash_binding"], hash_binding)
    write_json(proof_files["baseline_fallback_kill_switch"], fallback)
    write_json(proof_files["post_run_reconciliation"], reconciliation)
    write_json(proof_files["non_authorization"], non_auth)
    write_json(proof_files["control_boundary_readback"], control)
    write_json(proof_files["owner_decision_record"], owner_record)
    manifest_path = proof_root / "proof_artifact_manifest.json"
    manifest = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dg_proof_artifact_manifest.v1",
        "artifact_count": len(proof_files),
        "artifacts": {key: evidence_file(path) for key, path in sorted(proof_files.items())},
    }
    write_json(manifest_path, manifest)
    manifest["self"] = evidence_file(manifest_path)
    write_json(manifest_path, manifest)

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "status": status,
        "blockers": blockers,
        "p9dg_limited_live_delta_candidate_executor_path_canary_proposal_package_ready": ready,
        "p9df_sufficient_for_p9dg_proposal_package": p9df_summary_ready(p9df)
        and p9df_scope_ready(scope)
        and p9df_non_authorization_ready(p9df_non_auth)
        and p9df_control_ready(p9df_control),
        "proposal_package_prepared": ready,
        "proposal_package_only": True,
        "proposal_scope": "single_cycle_limited_live_delta_candidate_executor_path_canary",
        "max_cycles_total": terms["max_cycles_total"],
        "max_symbols_total": terms["max_symbols_total"],
        "max_orders_total": terms["max_orders_total"],
        "max_notional_per_order_usdt": terms["max_notional_per_order_usdt"],
        "max_gross_turnover_usdt": terms["max_gross_turnover_usdt"],
        "order_type": terms["order_type"],
        "time_in_force": terms["time_in_force"],
        "market_orders_allowed": False,
        "emergency_market_fallback_allowed": False,
        "candidate_plan_hash_binding_defined": True,
        "baseline_fallback_defined": True,
        "kill_switch_defined": True,
        "post_run_reconciliation_defined": True,
        "future_execution_gate_required": True,
        "eligible_for_future_p9dh_review_gate": ready,
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
        "source_evidence": {
            "phase9df_summary": evidence_file(p9df_path),
            "phase9df_discussion_scope": evidence_file(scope_path),
            "phase9df_non_authorization": evidence_file(non_auth_path),
            "phase9df_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "gates": gates,
        "allowed_next_gate": P9DH_GATE,
        "allowed_next_gate_scope": P9DH_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "output_files": {
            "summary": str(root / "summary.json"),
            "report": str(root / "p9dg_limited_live_delta_candidate_executor_path_canary_proposal_package.md"),
            "proof_artifact_manifest": str(manifest_path),
            **{key: str(path) for key, path in proof_files.items()},
        },
    }
    write_json(root / "summary.json", summary)
    (root / "p9dg_limited_live_delta_candidate_executor_path_canary_proposal_package.md").write_text(
        render_markdown(summary), encoding="utf-8"
    )
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9DG Candidate Executor-Path Canary Proposal Package",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9DG prepares a proposal package only. It does not execute, load, submit orders, replace target plans, or mutate executor input.",
        "",
        "## Proposed Terms",
        "",
        "```text",
        f"max_cycles_total = {summary['max_cycles_total']}",
        f"max_symbols_total = {summary['max_symbols_total']}",
        f"max_orders_total = {summary['max_orders_total']}",
        f"max_notional_per_order_usdt = {summary['max_notional_per_order_usdt']}",
        f"max_gross_turnover_usdt = {summary['max_gross_turnover_usdt']}",
        f"order_type = {summary['order_type']}",
        f"time_in_force = {summary['time_in_force']}",
        "market_orders_allowed = false",
        "emergency_market_fallback_allowed = false",
        "candidate_plan_hash_binding_defined = true",
        "baseline_fallback_defined = true",
        "kill_switch_defined = true",
        "post_run_reconciliation_defined = true",
        "```",
        "",
        "## Non-Authorization",
        "",
        "```text",
        "live_order_submission_authorized = false",
        "candidate_executor_path_execution_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
        "timer_path_load_authorized = false",
        "supervisor_invocation_authorized = false",
        "continuous_automated_order_flow_authorized = false",
        "orders_submitted = 0",
        "fill_count = 0",
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
    summary, exit_code = build_phase9dg(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
