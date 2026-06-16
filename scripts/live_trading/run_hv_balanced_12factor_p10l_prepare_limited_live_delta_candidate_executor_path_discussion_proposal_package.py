from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.live_trading.run_hv_balanced_12factor_p10k_define_limited_live_delta_candidate_executor_path_discussion_scope import (  # noqa: E402
    CONTRACT_VERSION as P10K_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P10K_PARENT,
    P10L_GATE,
    P10L_SCOPE,
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
    "hv_balanced_12factor_p10l_prepare_limited_live_delta_candidate_executor_path_"
    "discussion_proposal_package.v1"
)
APPROVE_P10L_DECISION = (
    "approve_p10l_prepare_limited_live_delta_candidate_executor_path_discussion_"
    "proposal_package_only"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/proof_artifacts/"
    "p10l_limited_live_delta_candidate_executor_path_discussion_proposal_package"
)
P10M_GATE = (
    "P10M_review_p10l_limited_live_delta_candidate_executor_path_discussion_"
    "proposal_package_only_if_separately_requested"
)
P10M_SCOPE = (
    "review_p10l_limited_live_delta_candidate_executor_path_discussion_proposal_"
    "package_no_execution_no_live_order_no_continuous_automation"
)

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_MAX_NOTIONAL_USDT = 75.0
DEFAULT_MAX_GROSS_TURNOVER_USDT = 150.0
DEFAULT_MAX_CANDIDATE_ENTRY_ORDERS = 1
DEFAULT_MAX_REDUCE_ONLY_ROLLBACK_ORDERS = 1
DEFAULT_ORDER_TYPE = "post_only_limit"
DEFAULT_TIME_IN_FORCE = "GTX"

RESEARCH_SCORER_REQUIRED_FEATURES: tuple[str, ...] = (
    "intraday_realized_vol_4h_to_1d_smooth_60",
    "realized_volatility_5",
    "distance_to_high_60",
    "distance_to_high_5",
    "coinglass_top_trader_long_pct_smooth_5",
    "liquidity_stress_qv_iv",
    "momentum_decay_5_20",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "quality_funding_oi",
    "downside_upside_vol_ratio_30",
    "funding_basis_residual_implied_repo_30",
    "settlement_cycle_premium_60d",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the P10L proposal package for a future limited live_delta / "
            "candidate executor-path discussion. P10L writes retained proposal "
            "artifacts only; it does not SSH, call Binance, run candidate logic, "
            "replace target plans, mutate executor input, load timer/supervisor "
            "paths, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--p10k-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P10L_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p10l_prepare_limited_live_delta_candidate_executor_path_"
            "discussion_proposal_package_only_if_separately_requested"
        ),
    )
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--max-notional-usdt", type=float, default=DEFAULT_MAX_NOTIONAL_USDT)
    parser.add_argument(
        "--max-gross-turnover-usdt",
        type=float,
        default=DEFAULT_MAX_GROSS_TURNOVER_USDT,
    )
    parser.add_argument(
        "--max-candidate-entry-orders",
        type=int,
        default=DEFAULT_MAX_CANDIDATE_ENTRY_ORDERS,
    )
    parser.add_argument(
        "--max-reduce-only-rollback-orders",
        type=int,
        default=DEFAULT_MAX_REDUCE_ONLY_ROLLBACK_ORDERS,
    )
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


def latest_p10k_summary(args: argparse.Namespace) -> Path:
    if str(args.p10k_summary).strip():
        return resolve_path(args.p10k_summary)
    return latest_match(P10K_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p10k_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P10K_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10k_limited_live_delta_candidate_executor_path_discussion_scope_ready")
        is True
        and summary.get("p10j_sufficient_for_p10k_scope_definition") is True
        and summary.get("scope_definition_only") is True
        and summary.get("scope_label") == "limited_live_delta_candidate_executor_path_discussion_after_p10i"
        and summary.get("allowed_scope_after_p10k") == "proposal_package_preparation_only"
        and summary.get("eligible_for_future_p10l_proposal_package_gate") is True
        and int(summary.get("max_cycles_discussion_scope") or 0) == 1
        and int(summary.get("max_symbols_discussion_scope") or 0) == 1
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
        and summary.get("allowed_next_gate") == P10L_GATE
        and summary.get("allowed_next_gate_scope") == P10L_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def p10k_scope_ready(scope: dict[str, Any]) -> bool:
    hard_limits = dict(scope.get("hard_limits_for_discussion") or {})
    must_define = set(scope.get("must_define_before_any_future_execution_gate") or [])
    not_authorized = set(scope.get("not_authorized_by_this_scope") or [])
    return (
        scope.get("contract_version")
        == "hv_balanced_12factor_p10k_limited_live_delta_candidate_executor_path_discussion_scope.v1"
        and scope.get("scope_only") is True
        and scope.get("scope_label") == "limited_live_delta_candidate_executor_path_discussion_after_p10i"
        and int(hard_limits.get("max_cycles") or 0) == 1
        and int(hard_limits.get("max_symbols") or 0) == 1
        and hard_limits.get("continuous_automated_order_flow") is False
        and hard_limits.get("default_order_state") == "disabled_until_separate_execution_gate"
        and hard_limits.get("default_timer_path_state") == "not_loaded"
        and hard_limits.get("default_supervisor_invocation") == "not_invoked"
        and hard_limits.get("default_candidate_execution") == "not_executed"
        and hard_limits.get("default_target_plan_replacement") == "not_replaced"
        and hard_limits.get("default_executor_input_mutation") == "not_mutated"
        and hard_limits.get("default_remote_sync") == "not_performed"
        and int(hard_limits.get("default_remote_file_write") or 0) == 0
        and hard_limits.get("must_remain_stage_3_human_approved_execution") is True
        and "explicit owner approval for a specific execution-path canary" in must_define
        and "candidate plan hash must bind to retained P10G or a fresh rerun" in must_define
        and "executor input replacement must be exact, reversible, and one-cycle only" in must_define
        and "baseline fallback must trigger on any stale, missing, or mismatched proof" in must_define
        and "kill switch must force baseline-only with zero candidate orders" in must_define
        and "fresh remote account proof must use /fapi/v2/account.canTrade" in must_define
        and "live order submission" in not_authorized
        and "candidate executor-path execution" in not_authorized
        and "actual target-plan replacement" in not_authorized
        and "executor input mutation" in not_authorized
        and "timer path load" in not_authorized
        and "supervisor invocation" in not_authorized
        and "continuous automated order flow" in not_authorized
        and scope.get("allowed_next_gate") == P10L_GATE
        and scope.get("allowed_next_gate_scope") == P10L_SCOPE
        and scope.get("allowed_next_gate_must_be_separately_requested") is True
    )


def p10k_non_authorization_ready(non_auth: dict[str, Any]) -> bool:
    authorizations = dict(non_auth.get("authorizations") or {})
    return (
        non_auth.get("contract_version") == "hv_balanced_12factor_p10k_non_authorization.v1"
        and authorizations.get("define_discussion_scope") is True
        and authorizations.get("future_p10l_proposal_package_request_allowed") is True
        and authorizations.get("live_order_submission_in_p10k") is False
        and authorizations.get("candidate_executor_path_execution_in_p10k") is False
        and authorizations.get("candidate_target_plan_replacement_in_p10k") is False
        and authorizations.get("executor_input_mutation_in_p10k") is False
        and authorizations.get("timer_path_load_in_p10k") is False
        and authorizations.get("supervisor_invocation_in_p10k") is False
        and authorizations.get("remote_execution_in_p10k") is False
        and authorizations.get("remote_sync_in_p10k") is False
        and authorizations.get("remote_file_write_in_p10k") is False
        and authorizations.get("continuous_automated_order_flow") is False
        and authorizations.get("stage_governance_change") is False
    )


def p10k_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version") == "hv_balanced_12factor_p10k_control_boundary.v1"
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
    max_entry_orders = int(args.max_candidate_entry_orders)
    max_rollback_orders = int(args.max_reduce_only_rollback_orders)
    return {
        "contract_version": "hv_balanced_12factor_p10l_risk_order_terms_proposal.v1",
        "scope": "future_single_cycle_limited_candidate_executor_path_discussion_terms_proposal_only",
        "symbol": str(args.symbol or "").upper(),
        "symbol_universe": [str(args.symbol or "").upper()],
        "max_cycles_total": 1,
        "continuous_automation": False,
        "max_symbols_total": 1,
        "max_candidate_entry_orders_total": max_entry_orders,
        "max_reduce_only_rollback_orders_total": max_rollback_orders,
        "max_orders_total": max_entry_orders + max_rollback_orders,
        "max_notional_usdt": float(args.max_notional_usdt),
        "max_notional_per_candidate_entry_order_usdt": float(args.max_notional_usdt),
        "max_candidate_position_delta_abs_usdt": float(args.max_notional_usdt),
        "max_gross_turnover_usdt": float(args.max_gross_turnover_usdt),
        "order_type": str(args.order_type or "").strip().lower(),
        "time_in_force": str(args.time_in_force or "").strip().upper(),
        "maker_only_required": True,
        "post_only_required": True,
        "market_orders_allowed": False,
        "taker_execution_allowed": False,
        "emergency_market_fallback_allowed": False,
        "reduce_only_required_for_risk_reducing_orders": True,
        "candidate_delta_source": "12factor_scorer_candidate_target_plan",
        "candidate_scorer_source": "research_contract_12factor_shadow_scorer",
        "candidate_plan_hash_binding_source": "retained_p10g_or_fresh_p10g_rerun_required_before_execution",
        "baseline_fallback": "any stale, missing, mismatched, or over-limit proof keeps executor baseline-only",
        "kill_switch": "candidate_live_delta_enabled=false / executor_target_source=baseline_only",
        "rollback": "cancel open candidate order; reduce-only close only if filled; post-run reconciliation",
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
    }


def terms_ready(terms: dict[str, Any]) -> dict[str, bool]:
    max_notional = float(terms.get("max_notional_usdt") or 0.0)
    max_gross = float(terms.get("max_gross_turnover_usdt") or 0.0)
    max_orders = int(terms.get("max_orders_total") or 0)
    return {
        "terms_symbol_is_btcusdt": terms.get("symbol") == DEFAULT_SYMBOL,
        "terms_max_cycles_one": int(terms.get("max_cycles_total") or 0) == 1,
        "terms_continuous_automation_false": terms.get("continuous_automation") is False,
        "terms_max_symbols_one": int(terms.get("max_symbols_total") or 0) == 1,
        "terms_candidate_entry_orders_one": int(terms.get("max_candidate_entry_orders_total") or 0) == 1,
        "terms_rollback_orders_at_most_one": int(terms.get("max_reduce_only_rollback_orders_total") or 0)
        <= 1,
        "terms_total_orders_bounded": 1 <= max_orders <= 2,
        "terms_max_notional_is_75": abs(max_notional - DEFAULT_MAX_NOTIONAL_USDT) <= 1e-12,
        "terms_gross_turnover_bounded": max_gross <= DEFAULT_MAX_GROSS_TURNOVER_USDT,
        "terms_gross_turnover_covers_candidate_and_rollback": max_gross >= max_notional * max_orders,
        "terms_order_type_post_only_limit": terms.get("order_type") == DEFAULT_ORDER_TYPE,
        "terms_time_in_force_gtx": terms.get("time_in_force") == DEFAULT_TIME_IN_FORCE,
        "terms_maker_only_required": terms.get("maker_only_required") is True,
        "terms_post_only_required": terms.get("post_only_required") is True,
        "terms_market_orders_forbidden": terms.get("market_orders_allowed") is False,
        "terms_no_emergency_market_fallback": terms.get("emergency_market_fallback_allowed") is False,
        "terms_candidate_delta_source_is_12factor": terms.get("candidate_delta_source")
        == "12factor_scorer_candidate_target_plan",
        "terms_hash_binding_source_requires_p10g_or_fresh": terms.get("candidate_plan_hash_binding_source")
        == "retained_p10g_or_fresh_p10g_rerun_required_before_execution",
        "terms_baseline_fallback_explicit": "baseline" in str(terms.get("baseline_fallback") or ""),
        "terms_kill_switch_explicit": "candidate_live_delta_enabled=false"
        in str(terms.get("kill_switch") or ""),
        "terms_rollback_explicit": "reduce-only close only if filled" in str(terms.get("rollback") or ""),
    }


def research_scorer_contract(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_12factor_p10l_research_scorer_contract_proposal.v1",
        "run_id": run_id,
        "scorer_family": "xs_alpha_ontology_v5_h10d_rw_bridge_no_overlay",
        "target_horizon_bars": 10,
        "feature_contract": "research_h10d_12_factor_scorer_contract.v1",
        "required_feature_columns": list(RESEARCH_SCORER_REQUIRED_FEATURES),
        "required_feature_count": len(RESEARCH_SCORER_REQUIRED_FEATURES),
        "scoring_rule": (
            "train-window signed-IR factor weights; validation/live scorer uses frozen "
            "WFO window weights, percentile-rank raw score, and tanh transform"
        ),
        "portfolio_construction": {
            "target_engine": "multiphase_equal_sleeve",
            "phase_offsets_days": list(range(10)),
            "top_long_count": 3,
            "bottom_short_count": 3,
            "long_leverage": 0.5,
            "short_leverage": 0.5,
            "position_multiplier_overlay_id": None,
        },
        "required_research_to_live_parity_dimensions": [
            "WFO window id",
            "panel membership",
            "thresholds",
            "factor weight vector",
            "per-factor scorer input values",
            "raw score",
            "final score",
            "target weights",
            "slice metrics",
        ],
        "p10l_scores_live_features": False,
        "p10l_executes_scorer": False,
        "future_gate_must_bind_fresh_or_retained_scorer_artifacts": True,
    }


def candidate_plan_hash_binding_contract(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_12factor_p10l_candidate_plan_hash_binding_proposal.v1",
        "run_id": run_id,
        "binding_scope": "future_single_cycle_limited_candidate_executor_path_discussion_only",
        "required_hashes_before_future_execution": [
            "active_h10d_registry_sha256",
            "research_parent_manifest_sha256",
            "wfo_window_contract_sha256",
            "research_to_live_parity_summary_sha256",
            "live_feature_snapshot_sha256",
            "scorer_input_panel_sha256",
            "per_factor_values_sha256",
            "factor_weight_vector_sha256",
            "shadow_scorer_output_sha256",
            "baseline_target_plan_sha256",
            "candidate_target_plan_sha256",
            "target_plan_diff_sha256",
            "same_risk_input_sha256",
            "executor_input_plan_sha256_before_replacement",
            "executor_input_plan_sha256_after_replacement",
        ],
        "same_context_requirements": {
            "same_timestamp": True,
            "same_risk_inputs": True,
            "same_universe": True,
            "same_wfo_window": True,
            "same_panel_membership": True,
            "all_12_factor_inputs_match_research_contract": True,
            "same_exchange_filters_snapshot_or_fresher_pre_submit_filter_read": True,
            "p9_distance_to_high_60_only_delta_rule_not_sufficient_for_p10": True,
        },
        "binding_rules": [
            "baseline target plan must be generated and hashed first",
            "candidate target plan must bind to retained P10G or a fresh P10G rerun",
            "candidate target plan must derive from the 12-factor research-contract scorer",
            "executor input replacement may proceed only if the after-replacement hash equals the owner-approved candidate target plan hash",
            "any missing, stale, mismatched, or unreviewed hash forces baseline fallback and zero candidate order submission",
            "future review must prove P10G/P10H/P10I/P10J/P10K lineage or a fresh rerun lineage before any execution gate can be actionable",
        ],
        "stale_after_seconds": 60,
        "p10l_authorizes_actual_hash_binding": False,
        "future_gate_must_collect_or_reference_hashes": True,
    }


def executor_path_semantics_contract(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_12factor_p10l_executor_path_semantics_proposal.v1",
        "run_id": run_id,
        "semantics_scope": "future_discussion_only",
        "candidate_target_plan_replacement": {
            "max_cycles": 1,
            "replacement_mode_to_discuss": "single_cycle_exact_hash_bound_replacement",
            "executor_input_before": "baseline_target_plan",
            "executor_input_after_if_future_gate_approves": "candidate_target_plan",
            "revert_after_cycle": "baseline_target_plan",
            "actual_replacement_performed_in_p10l": False,
        },
        "baseline_fallback": {
            "trigger": [
                "candidate artifact missing or stale",
                "12-factor scorer parity mismatch",
                "candidate plan hash mismatch",
                "executor input hash mismatch",
                "fresh account, position, order, trade, book, or filter proof missing",
                "notional, symbol, order type, or time-in-force outside terms",
            ],
            "action": [
                "keep executor baseline-only",
                "write no-order proof artifact",
                "submit zero candidate orders",
                "require separate owner review before retry",
            ],
        },
        "p10l_replaces_target_plan": False,
        "p10l_mutates_executor_input": False,
        "future_execution_gate_required": True,
    }


def baseline_fallback_and_kill_switch_contract(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_12factor_p10l_baseline_fallback_kill_switch_proposal.v1",
        "run_id": run_id,
        "baseline_fallback_policy": {
            "fallback_trigger_before_submit": [
                "missing or stale retained P10G/fresh P10G candidate plan artifact",
                "candidate plan hash mismatch",
                "12-factor scorer contract mismatch",
                "WFO window, panel, threshold, or slice metric mismatch",
                "fresh account, position, open-order, fill, trade, book, or filter proof missing",
                "order notional, symbol, order type, or time-in-force exceeds proposal terms",
                "timer, supervisor, config, operator, or executor boundary invariant mismatch",
            ],
            "fallback_action_before_submit": [
                "keep executor input baseline-only",
                "write no-order retained artifact",
                "submit zero candidate orders",
                "require owner review before retry",
            ],
            "fallback_trigger_after_any_future_fill": [
                "unexpected open order remains",
                "unexpected order/cancel/fill/trade delta",
                "post position fingerprint differs from expected bounded candidate plan",
                "provider, exchange, risk, executor, timer, or supervisor exception",
                "candidate canary realized plus unrealized drawdown exceeds 5 USDT",
            ],
            "fallback_action_after_any_future_fill": [
                "cancel candidate-scope open orders",
                "freeze further candidate cycles",
                "restore executor_target_source=baseline_only",
                "set candidate_live_delta_enabled=false",
                "require separate owner-approved reduce-only rollback if position must be reverted",
            ],
        },
        "kill_switch": {
            "required": True,
            "operator_action": (
                "set candidate_live_delta_enabled=false; set executor_target_source=baseline_only; "
                "cancel candidate-scope open orders; block candidate executor-path gate until owner review"
            ),
            "must_be_readable_before_submit": True,
            "must_be_rechecked_after_cycle": True,
        },
        "p10l_executes_kill_switch": False,
        "p10l_changes_operator_state": False,
    }


def post_run_reconciliation_contract(run_id: str, terms: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_12factor_p10l_post_run_reconciliation_proposal.v1",
        "run_id": run_id,
        "required_post_run_readbacks": [
            "post account read using /fapi/v2/account.canTrade for canTrade",
            "post position fingerprint",
            "post open-order fingerprint",
            "post order/cancel/fill/trade delta fingerprint",
            "post executor input hash",
            "post target-plan source readback",
            "post timer/supervisor/operator/config/control-boundary readback",
        ],
        "acceptance_conditions_for_future_execution_gate": {
            "completed_cycles_exactly": 1,
            "candidate_symbols_at_most": 1,
            "orders_submitted_at_most": int(terms.get("max_orders_total") or 0),
            "candidate_entry_orders_at_most": int(
                terms.get("max_candidate_entry_orders_total") or 0
            ),
            "gross_turnover_usdt_at_most": float(terms.get("max_gross_turnover_usdt") or 0.0),
            "open_candidate_orders_after_cycle": 0,
            "all_order_cancel_fill_trade_deltas_explained_by_candidate_plan": True,
            "post_position_matches_expected_candidate_canary_plan_or_reconciled_reduce_only_close": True,
            "executor_input_hash_matches_expected_post_cycle_source": True,
            "candidate_path_disabled_or_frozen_after_cycle_until_owner_review": True,
            "no_second_cycle_without_separate_owner_gate": True,
        },
        "failure_conditions": [
            "unexplained order, cancel, fill, or trade delta",
            "open order remains after cycle",
            "post position mismatch",
            "executor input remains candidate when fallback should be baseline",
            "timer/supervisor/operator/config/control-boundary changed outside proposal",
            "second cycle attempted",
        ],
        "p10l_performs_post_run_reconciliation": False,
        "future_gate_must_perform_post_run_reconciliation": True,
    }


def owner_decision_record(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P10L_DECISION
    return {
        "contract_version": "hv_balanced_12factor_p10l_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "prepare_limited_live_delta_candidate_executor_path_discussion_proposal_package_only",
        "recorded_at_utc": iso_z(now),
        "p10l_proposal_package_preparation_approved": approved,
        "future_p10m_review_may_be_requested": approved,
        "live_order_submission_approved": False,
        "candidate_executor_path_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "timer_path_load_approved": False,
        "supervisor_invocation_approved": False,
        "remote_execution_approved": False,
        "remote_sync_approved": False,
        "continuous_automated_order_flow_approved": False,
    }


def proposal_package(
    *,
    run_id: str,
    now: datetime,
    args: argparse.Namespace,
    terms: dict[str, Any],
    scorer: dict[str, Any],
    hash_binding: dict[str, Any],
    executor_semantics: dict[str, Any],
    fallback: dict[str, Any],
    reconciliation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_12factor_p10l_proposal_package.v1",
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "owner": args.owner,
        "proposal_status": "prepared_for_future_review_only",
        "proposal_scope": "limited_live_delta_candidate_executor_path_discussion",
        "research_scorer_contract": scorer,
        "risk_order_terms": terms,
        "candidate_plan_hash_binding": hash_binding,
        "executor_path_semantics": executor_semantics,
        "baseline_fallback_and_kill_switch": fallback,
        "post_run_reconciliation": reconciliation,
        "future_review_gate": P10M_GATE,
        "future_execution_gate_required": True,
        "p10l_authorizes_execution": False,
        "p10l_authorizes_live_order": False,
        "p10l_authorizes_target_plan_replacement": False,
        "p10l_authorizes_executor_input_mutation": False,
        "p10l_authorizes_timer_or_supervisor_load": False,
        "p10l_authorizes_remote_execution": False,
        "p10l_authorizes_remote_sync": False,
        "p10l_authorizes_continuous_automation": False,
    }


def build_p10l(
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

    p10k_path = latest_p10k_summary(args)
    p10k = load_optional(p10k_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    scope_path = source_output_path(p10k, "discussion_scope")
    non_auth_path = source_output_path(p10k, "non_authorization")
    control_path = source_output_path(p10k, "control_boundary_readback")
    scope = load_optional(scope_path)
    p10k_non_auth = load_optional(non_auth_path)
    p10k_control = load_optional(control_path)

    terms = proposal_terms(args)
    scorer = research_scorer_contract(run_id)
    hash_binding = candidate_plan_hash_binding_contract(run_id)
    executor_semantics = executor_path_semantics_contract(run_id)
    fallback = baseline_fallback_and_kill_switch_contract(run_id)
    reconciliation = post_run_reconciliation_contract(run_id, terms)
    owner_record = owner_decision_record(args, started_at)
    term_checks = terms_ready(terms)

    gates = {
        "owner_decision_p10l_proposal_package_recorded": str(args.owner_decision)
        == APPROVE_P10L_DECISION,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p10k_summary_exists": bool(p10k),
        "p10k_summary_ready_for_p10l": p10k_summary_ready(p10k),
        "p10k_discussion_scope_ready": p10k_scope_ready(scope),
        "p10k_non_authorization_ready": p10k_non_authorization_ready(p10k_non_auth),
        "p10k_control_boundary_ready": p10k_control_ready(p10k_control),
        **term_checks,
        "research_scorer_contract_has_12_features": int(scorer.get("required_feature_count") or 0)
        == 12,
        "research_scorer_contract_lists_required_features": tuple(
            scorer.get("required_feature_columns") or []
        )
        == RESEARCH_SCORER_REQUIRED_FEATURES,
        "hash_binding_defines_required_12factor_hashes": all(
            item in hash_binding["required_hashes_before_future_execution"]
            for item in (
                "live_feature_snapshot_sha256",
                "per_factor_values_sha256",
                "factor_weight_vector_sha256",
                "candidate_target_plan_sha256",
                "executor_input_plan_sha256_after_replacement",
            )
        ),
        "hash_binding_requires_same_context": all(
            bool(value) for value in hash_binding["same_context_requirements"].values()
        ),
        "executor_path_semantics_defined": executor_semantics[
            "candidate_target_plan_replacement"
        ]["max_cycles"]
        == 1
        and executor_semantics["p10l_replaces_target_plan"] is False,
        "baseline_fallback_defined": bool(
            fallback["baseline_fallback_policy"]["fallback_trigger_before_submit"]
        )
        and bool(fallback["baseline_fallback_policy"]["fallback_action_before_submit"]),
        "kill_switch_defined": fallback["kill_switch"]["required"] is True
        and bool(fallback["kill_switch"]["operator_action"]),
        "post_run_reconciliation_defined": reconciliation[
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
    p10k_inputs_ready = (
        p10k_summary_ready(p10k)
        and p10k_scope_ready(scope)
        and p10k_non_authorization_ready(p10k_non_auth)
        and p10k_control_ready(p10k_control)
    )

    package = proposal_package(
        run_id=run_id,
        now=started_at,
        args=args,
        terms=terms,
        scorer=scorer,
        hash_binding=hash_binding,
        executor_semantics=executor_semantics,
        fallback=fallback,
        reconciliation=reconciliation,
    )
    non_auth = {
        "contract_version": "hv_balanced_12factor_p10l_non_authorization.v1",
        "authorizations": {
            "prepare_proposal_package": ready,
            "future_p10m_review_request_allowed": ready,
            "live_order_submission_in_p10l": False,
            "candidate_executor_path_execution_in_p10l": False,
            "actual_target_plan_replacement_in_p10l": False,
            "executor_input_mutation_in_p10l": False,
            "timer_path_load_in_p10l": False,
            "supervisor_invocation_in_p10l": False,
            "remote_execution_in_p10l": False,
            "remote_sync_in_p10l": False,
            "remote_file_write_in_p10l": False,
            "continuous_automated_order_flow": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_12factor_p10l_control_boundary.v1",
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
        "research_scorer_contract": proof_root / "research_scorer_contract.json",
        "candidate_plan_hash_binding": proof_root / "candidate_plan_hash_binding.json",
        "executor_path_semantics": proof_root / "executor_path_semantics.json",
        "baseline_fallback_kill_switch": proof_root / "baseline_fallback_kill_switch.json",
        "post_run_reconciliation": proof_root / "post_run_reconciliation.json",
        "non_authorization": proof_root / "non_authorization.json",
        "control_boundary_readback": proof_root / "control_boundary_readback.json",
        "owner_decision_record": root / "owner_decision_record.json",
    }
    write_json(proof_files["proposal_package"], package)
    write_json(proof_files["risk_order_terms"], terms)
    write_json(proof_files["research_scorer_contract"], scorer)
    write_json(proof_files["candidate_plan_hash_binding"], hash_binding)
    write_json(proof_files["executor_path_semantics"], executor_semantics)
    write_json(proof_files["baseline_fallback_kill_switch"], fallback)
    write_json(proof_files["post_run_reconciliation"], reconciliation)
    write_json(proof_files["non_authorization"], non_auth)
    write_json(proof_files["control_boundary_readback"], control)
    write_json(proof_files["owner_decision_record"], owner_record)

    manifest_path = proof_root / "proof_artifact_manifest.json"
    manifest = {
        "contract_version": "hv_balanced_12factor_p10l_proof_artifact_manifest.v1",
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
        "p10l_limited_live_delta_candidate_executor_path_discussion_proposal_package_ready": ready,
        "p10k_sufficient_for_p10l_proposal_package": p10k_inputs_ready,
        "proposal_package_prepared": ready,
        "proposal_package_only": True,
        "discussion_proposal_only": True,
        "proposal_scope": "limited_live_delta_candidate_executor_path_discussion",
        "research_scorer_required_feature_count": len(RESEARCH_SCORER_REQUIRED_FEATURES),
        "research_scorer_required_features": list(RESEARCH_SCORER_REQUIRED_FEATURES),
        "max_cycles_total": terms["max_cycles_total"],
        "symbol": terms["symbol"],
        "max_symbols_total": terms["max_symbols_total"],
        "max_orders_total": terms["max_orders_total"],
        "max_candidate_entry_orders_total": terms["max_candidate_entry_orders_total"],
        "max_reduce_only_rollback_orders_total": terms["max_reduce_only_rollback_orders_total"],
        "max_notional_usdt": terms["max_notional_usdt"],
        "max_gross_turnover_usdt": terms["max_gross_turnover_usdt"],
        "order_type": terms["order_type"],
        "time_in_force": terms["time_in_force"],
        "maker_only_required": True,
        "post_only_required": True,
        "market_orders_allowed": False,
        "emergency_market_fallback_allowed": False,
        "candidate_delta_source": terms["candidate_delta_source"],
        "candidate_plan_hash_binding_defined": True,
        "executor_path_semantics_defined": True,
        "baseline_fallback_defined": True,
        "kill_switch_defined": True,
        "post_run_reconciliation_defined": True,
        "future_execution_gate_required": True,
        "eligible_for_future_p10m_review_gate": ready,
        "eligible_for_future_live_order_submission": False,
        "live_order_submission_authorized": False,
        "candidate_executor_path_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_execution_authorized": False,
        "remote_sync_authorized": False,
        "continuous_automated_order_flow_authorized": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "source_evidence": {
            "p10k_summary": evidence_file(p10k_path),
            "p10k_discussion_scope": evidence_file(scope_path),
            "p10k_non_authorization": evidence_file(non_auth_path),
            "p10k_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "gates": gates,
        "allowed_next_gate": P10M_GATE,
        "allowed_next_gate_scope": P10M_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "output_files": {
            "summary": str(root / "summary.json"),
            "report": str(
                root
                / "p10l_limited_live_delta_candidate_executor_path_discussion_proposal_package.md"
            ),
            "proof_artifact_manifest": str(manifest_path),
            **{key: str(path) for key, path in proof_files.items()},
        },
    }
    write_json(root / "summary.json", summary)
    (
        root / "p10l_limited_live_delta_candidate_executor_path_discussion_proposal_package.md"
    ).write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced 12-Factor P10L Limited Executor-Path Discussion Proposal Package",
        "",
        f"`Status: {summary['status']}`",
        "",
        (
            "P10L prepares a proposal package only. It does not execute, load, submit "
            "orders, replace target plans, mutate executor input, or authorize "
            "continuous automated order flow."
        ),
        "",
        "## Proposed Boundaries",
        "",
        "```text",
        f"proposal_package_only = {str(bool(summary['proposal_package_only'])).lower()}",
        f"research_scorer_required_feature_count = {summary['research_scorer_required_feature_count']}",
        f"max_cycles_total = {summary['max_cycles_total']}",
        f"symbol = {summary['symbol']}",
        f"max_notional_usdt = {summary['max_notional_usdt']}",
        f"max_gross_turnover_usdt = {summary['max_gross_turnover_usdt']}",
        f"order_type = {summary['order_type']}",
        f"time_in_force = {summary['time_in_force']}",
        "maker_only_required = true",
        "post_only_required = true",
        "market_orders_allowed = false",
        f"candidate_delta_source = {summary['candidate_delta_source']}",
        "candidate_plan_hash_binding_defined = true",
        "executor_path_semantics_defined = true",
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
        "remote_execution_performed = false",
        "remote_sync_performed = false",
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
    summary, exit_code = build_p10l(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
