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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9dg_prepare_limited_live_delta_candidate_executor_path_canary_proposal_package import (  # noqa: E402
    CONTRACT_VERSION as P9DG_CONTRACT,
    DEFAULT_MAX_GROSS_TURNOVER_USDT,
    DEFAULT_MAX_NOTIONAL_PER_ORDER_USDT,
    DEFAULT_ORDER_TYPE,
    DEFAULT_OUTPUT_PARENT as P9DG_PARENT,
    DEFAULT_TIME_IN_FORCE,
    P9DH_GATE,
    P9DH_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9dh_review_limited_live_delta_candidate_"
    "executor_path_canary_proposal_package.v1"
)
APPROVE_P9DH_DECISION = (
    "approve_p9dh_review_limited_live_delta_candidate_executor_path_canary_"
    "proposal_package_only"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9dh_review_limited_live_delta_candidate_executor_path_"
    "canary_proposal_package"
)
P9DI_GATE = (
    "P9DI_allow_single_cycle_limited_live_delta_candidate_executor_path_canary_"
    "execution_owner_gate_only_if_separately_requested"
)
P9DI_SCOPE = (
    "decide_whether_to_allow_single_cycle_limited_live_delta_candidate_executor_"
    "path_canary_execution_under_p9dg_terms"
)

REQUIRED_HASHES = {
    "baseline_target_plan_sha256",
    "candidate_target_plan_sha256",
    "same_risk_input_sha256",
    "candidate_overlay_contribution_sha256",
    "distance_to_high_60_contribution_delta_sha256",
    "slice_metrics_sha256",
    "executor_input_plan_sha256_before_replacement",
    "executor_input_plan_sha256_after_replacement",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review the retained P9DG proposal package for a future single-cycle "
            "limited live_delta / candidate executor-path canary. P9DH is "
            "review-only: it does not SSH, call Binance, execute candidate "
            "logic, replace target plans, mutate executor input, load timer or "
            "supervisor paths, remote sync, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9dg-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9DH_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9dh_review_limited_live_delta_candidate_executor_path_"
            "canary_proposal_package_only"
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


def latest_p9dg_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9dg_summary).strip():
        return resolve_path(args.phase9dg_summary)
    return latest_match(P9DG_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def int_value(payload: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        value = payload.get(key)
        return default if value is None else int(value)
    except (TypeError, ValueError):
        return default


def p9dg_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9DG_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get(
            "p9dg_limited_live_delta_candidate_executor_path_canary_proposal_package_ready"
        )
        is True
        and summary.get("p9df_sufficient_for_p9dg_proposal_package") is True
        and summary.get("proposal_package_prepared") is True
        and summary.get("proposal_package_only") is True
        and summary.get("proposal_scope")
        == "single_cycle_limited_live_delta_candidate_executor_path_canary"
        and int(summary.get("max_cycles_total") or 0) == 1
        and int(summary.get("max_symbols_total") or 0) == 1
        and int(summary.get("max_orders_total") or 0) <= 2
        and float(summary.get("max_notional_per_order_usdt") or 0)
        <= DEFAULT_MAX_NOTIONAL_PER_ORDER_USDT
        and float(summary.get("max_gross_turnover_usdt") or 0)
        <= DEFAULT_MAX_GROSS_TURNOVER_USDT
        and summary.get("order_type") == DEFAULT_ORDER_TYPE
        and summary.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and summary.get("market_orders_allowed") is False
        and summary.get("emergency_market_fallback_allowed") is False
        and summary.get("candidate_plan_hash_binding_defined") is True
        and summary.get("baseline_fallback_defined") is True
        and summary.get("kill_switch_defined") is True
        and summary.get("post_run_reconciliation_defined") is True
        and summary.get("future_execution_gate_required") is True
        and summary.get("eligible_for_future_p9dh_review_gate") is True
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_executor_path_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("continuous_automated_order_flow_authorized") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("remote_sync_performed") is False
        and int_zero(summary, "remote_files_written")
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and summary.get("allowed_next_gate") == P9DH_GATE
        and summary.get("allowed_next_gate_scope") == P9DH_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def risk_order_terms_ready(terms: dict[str, Any]) -> bool:
    return (
        terms.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9dg_risk_order_terms.v1"
        and terms.get("scope")
        == "future_single_cycle_candidate_executor_path_canary_terms_proposal_only"
        and int(terms.get("max_cycles_total") or 0) == 1
        and int(terms.get("max_symbols_total") or 0) == 1
        and 0 < int(terms.get("max_orders_total") or 0) <= 2
        and float(terms.get("max_notional_per_order_usdt") or 0)
        <= DEFAULT_MAX_NOTIONAL_PER_ORDER_USDT
        and float(terms.get("max_gross_turnover_usdt") or 0)
        <= DEFAULT_MAX_GROSS_TURNOVER_USDT
        and float(terms.get("max_gross_turnover_usdt") or 0)
        >= float(terms.get("max_notional_per_order_usdt") or 0)
        * int(terms.get("max_orders_total") or 0)
        and terms.get("order_type") == DEFAULT_ORDER_TYPE
        and terms.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and terms.get("market_orders_allowed") is False
        and terms.get("emergency_market_fallback_allowed") is False
        and terms.get("reduce_only_required_for_risk_reducing_orders") is True
        and terms.get("candidate_delta_source")
        == "distance_to_high_60_contribution_only"
        and "coinglass_top_trader_crowded_branch"
        in list(terms.get("candidate_overlay_components") or [])
        and "binance_shock_branch"
        in list(terms.get("candidate_overlay_components") or [])
    )


def hash_binding_ready(binding: dict[str, Any]) -> bool:
    same_context = dict(binding.get("same_context_requirements") or {})
    return (
        binding.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9dg_candidate_plan_hash_binding.v1"
        and binding.get("binding_scope") == "future_single_cycle_canary_only"
        and set(binding.get("required_hashes_before_future_execution") or [])
        >= REQUIRED_HASHES
        and same_context.get("same_timestamp") is True
        and same_context.get("same_risk_inputs") is True
        and same_context.get("same_universe") is True
        and same_context.get(
            "same_exchange_filters_snapshot_or_fresher_pre_submit_filter_read"
        )
        is True
        and same_context.get("overlay_may_change_only")
        == "distance_to_high_60_contribution"
        and int(binding.get("stale_after_seconds") or 0) <= 60
        and binding.get("p9dg_authorizes_actual_hash_binding") is False
        and binding.get("future_gate_must_collect_fresh_hashes") is True
    )


def fallback_kill_switch_ready(fallback: dict[str, Any]) -> bool:
    policy = dict(fallback.get("baseline_fallback_policy") or {})
    kill_switch = dict(fallback.get("kill_switch") or {})
    before_actions = set(policy.get("fallback_action_before_submit") or [])
    after_actions = set(policy.get("fallback_action_after_any_future_fill") or [])
    operator_action = str(kill_switch.get("operator_action") or "")
    return (
        fallback.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9dg_baseline_fallback_kill_switch.v1"
        and "keep executor input baseline-only" in before_actions
        and "write no-order proof artifact" in before_actions
        and "submit zero candidate orders" in before_actions
        and "restore executor_target_source=baseline_only" in after_actions
        and "set candidate_overlay_enabled=false" in after_actions
        and "set live_delta_armed=false before any further candidate order gate"
        in after_actions
        and kill_switch.get("required") is True
        and "candidate_overlay_enabled=false" in operator_action
        and "executor_target_source=baseline_only" in operator_action
        and "live_delta_armed=false" in operator_action
        and kill_switch.get("must_be_readable_before_submit") is True
        and kill_switch.get("must_be_rechecked_after_cycle") is True
        and fallback.get("p9dg_executes_kill_switch") is False
        and fallback.get("p9dg_changes_operator_state") is False
    )


def reconciliation_ready(reconciliation: dict[str, Any]) -> bool:
    conditions = dict(
        reconciliation.get("acceptance_conditions_for_future_execution_gate") or {}
    )
    readbacks = set(reconciliation.get("required_post_run_readbacks") or [])
    return (
        reconciliation.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9dg_post_run_reconciliation.v1"
        and "post account read using /fapi/v2/account.canTrade for canTrade" in readbacks
        and "post position fingerprint" in readbacks
        and "post open-order fingerprint" in readbacks
        and "post order/cancel/fill/trade delta fingerprint" in readbacks
        and "post executor input hash" in readbacks
        and "post target-plan source readback" in readbacks
        and int(conditions.get("completed_cycles_exactly") or 0) == 1
        and int(conditions.get("candidate_symbols_at_most") or 0) == 1
        and int(conditions.get("orders_submitted_at_most") or 0) <= 2
        and float(conditions.get("gross_turnover_usdt_at_most") or 0)
        <= DEFAULT_MAX_GROSS_TURNOVER_USDT
        and int_value(conditions, "open_candidate_orders_after_cycle", -1) == 0
        and conditions.get("all_order_cancel_fill_trade_deltas_explained_by_candidate_plan")
        is True
        and conditions.get("post_position_matches_expected_candidate_canary_plan") is True
        and conditions.get("executor_input_hash_matches_expected_post_cycle_source") is True
        and conditions.get("candidate_overlay_disabled_or_frozen_after_cycle_until_owner_review")
        is True
        and conditions.get("no_second_cycle_without_separate_owner_gate") is True
        and reconciliation.get("p9dg_performs_post_run_reconciliation") is False
        and reconciliation.get("future_gate_must_perform_post_run_reconciliation") is True
    )


def proposal_package_ready(package: dict[str, Any]) -> bool:
    max_notional = dict(package.get("max_notional") or {})
    order_type = dict(package.get("order_type") or {})
    return (
        package.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9dg_proposal_package.v1"
        and package.get("proposal_status") == "prepared_for_future_review_only"
        and package.get("proposal_scope")
        == "single_cycle_limited_live_delta_candidate_executor_path_canary"
        and float(max_notional.get("per_order_usdt") or 0)
        <= DEFAULT_MAX_NOTIONAL_PER_ORDER_USDT
        and float(max_notional.get("gross_turnover_usdt") or 0)
        <= DEFAULT_MAX_GROSS_TURNOVER_USDT
        and order_type.get("type") == DEFAULT_ORDER_TYPE
        and order_type.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and order_type.get("market_orders_allowed") is False
        and order_type.get("emergency_market_fallback_allowed") is False
        and hash_binding_ready(dict(package.get("candidate_plan_hash_binding") or {}))
        and fallback_kill_switch_ready(
            dict(package.get("baseline_fallback_and_kill_switch") or {})
        )
        and reconciliation_ready(dict(package.get("post_run_reconciliation") or {}))
        and package.get("future_execution_gate_required") is True
        and package.get("future_review_gate") == P9DH_GATE
        and package.get("p9dg_authorizes_execution") is False
        and package.get("p9dg_authorizes_live_order") is False
        and package.get("p9dg_authorizes_target_plan_replacement") is False
        and package.get("p9dg_authorizes_executor_input_mutation") is False
        and package.get("p9dg_authorizes_timer_or_supervisor_load") is False
        and package.get("p9dg_authorizes_continuous_automation") is False
    )


def non_authorization_ready(non_auth: dict[str, Any]) -> bool:
    authorizations = dict(non_auth.get("authorizations") or {})
    return (
        non_auth.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9dg_non_authorization.v1"
        and authorizations.get("prepare_proposal_package") is True
        and authorizations.get("future_p9dh_review_request_allowed") is True
        and authorizations.get("live_order_submission_in_p9dg") is False
        and authorizations.get("candidate_executor_path_execution_in_p9dg") is False
        and authorizations.get("actual_target_plan_replacement_in_p9dg") is False
        and authorizations.get("executor_input_mutation_in_p9dg") is False
        and authorizations.get("timer_path_load_in_p9dg") is False
        and authorizations.get("supervisor_invocation_in_p9dg") is False
        and authorizations.get("remote_execution_in_p9dg") is False
        and authorizations.get("remote_sync_in_p9dg") is False
        and authorizations.get("remote_file_write_in_p9dg") is False
        and authorizations.get("continuous_automated_order_flow") is False
        and authorizations.get("stage_governance_change") is False
    )


def control_boundary_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9dg_control_boundary.v1"
        and control.get("scope") == "proposal_package_preparation_only"
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


def owner_decision_record(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    approved = str(args.owner_decision) == APPROVE_P9DH_DECISION
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dh_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "review_p9dg_candidate_executor_path_canary_proposal_package_only",
        "recorded_at_utc": iso_z(now),
        "p9dh_review_approved": approved,
        "future_p9di_execution_owner_gate_may_be_requested": approved,
        "live_order_submission_approved": False,
        "candidate_executor_path_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "timer_path_load_approved": False,
        "supervisor_invocation_approved": False,
        "continuous_automated_order_flow_approved": False,
    }


def proposal_review(
    *,
    run_id: str,
    now: datetime,
    p9dg_summary: dict[str, Any],
    terms: dict[str, Any],
    package: dict[str, Any],
    hash_binding: dict[str, Any],
    fallback: dict[str, Any],
    reconciliation: dict[str, Any],
    ready: bool,
    gates: dict[str, bool],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dh_proposal_package_review.v1",
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "review_status": "ready" if ready else "blocked",
        "review_scope": "p9dg_candidate_executor_path_canary_proposal_package_review_only",
        "p9dg_run_id": p9dg_summary.get("run_id"),
        "p9dg_terms_reviewed": {
            "max_cycles_total": terms.get("max_cycles_total"),
            "max_symbols_total": terms.get("max_symbols_total"),
            "max_orders_total": terms.get("max_orders_total"),
            "max_notional_per_order_usdt": terms.get("max_notional_per_order_usdt"),
            "max_gross_turnover_usdt": terms.get("max_gross_turnover_usdt"),
            "order_type": terms.get("order_type"),
            "time_in_force": terms.get("time_in_force"),
            "market_orders_allowed": terms.get("market_orders_allowed"),
            "emergency_market_fallback_allowed": terms.get(
                "emergency_market_fallback_allowed"
            ),
            "candidate_delta_source": terms.get("candidate_delta_source"),
        },
        "candidate_plan_hash_binding_reviewed": {
            "required_hashes": sorted(hash_binding.get("required_hashes_before_future_execution") or []),
            "same_context_requirements": hash_binding.get("same_context_requirements"),
            "stale_after_seconds": hash_binding.get("stale_after_seconds"),
            "future_gate_must_collect_fresh_hashes": hash_binding.get(
                "future_gate_must_collect_fresh_hashes"
            ),
            "p9dg_authorizes_actual_hash_binding": hash_binding.get(
                "p9dg_authorizes_actual_hash_binding"
            ),
        },
        "fallback_kill_switch_reviewed": {
            "baseline_fallback_policy": fallback.get("baseline_fallback_policy"),
            "kill_switch": fallback.get("kill_switch"),
            "p9dg_executes_kill_switch": fallback.get("p9dg_executes_kill_switch"),
            "p9dg_changes_operator_state": fallback.get("p9dg_changes_operator_state"),
        },
        "post_run_reconciliation_reviewed": reconciliation.get(
            "acceptance_conditions_for_future_execution_gate"
        ),
        "p9dg_proposal_package_sufficient_for_future_execution_owner_gate_discussion": ready,
        "p9dg_proposal_package_sufficient_for_live_order_submission": False,
        "p9dg_proposal_package_sufficient_for_candidate_execution": False,
        "p9dh_authorizes_execution": False,
        "p9dh_authorizes_live_order": False,
        "p9dh_authorizes_target_plan_replacement": False,
        "p9dh_authorizes_executor_input_mutation": False,
        "gates": gates,
        "source_package_contract_version": package.get("contract_version"),
    }


def execution_owner_gate_readiness(
    *, run_id: str, now: datetime, ready: bool
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dh_execution_owner_gate_readiness.v1",
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "eligible_for_future_p9di_execution_owner_gate_discussion": ready,
        "eligible_for_live_order_submission": False,
        "eligible_for_candidate_execution": False,
        "future_gate": P9DI_GATE,
        "future_gate_scope": P9DI_SCOPE,
        "future_gate_must_be_separately_requested": True,
        "future_gate_required_fresh_inputs": [
            "retained P9DH summary and proposal review",
            "fresh /fapi/v2/account.canTrade readback",
            "fresh pre position fingerprint",
            "fresh pre open-order fingerprint",
            "fresh pre order/cancel/fill/trade fingerprint",
            "fresh order book and exchange filter readback",
            "fresh same-risk paired baseline and candidate target plans",
            "fresh candidate plan hash binding using the P9DG required hash set",
            "fresh executor input hash before any replacement",
            "fresh kill switch readback",
            "explicit owner approval for a single execution cycle under P9DG terms",
        ],
        "future_gate_terms_locked_by_review": {
            "max_cycles_total": 1,
            "max_symbols_total": 1,
            "max_orders_total": 2,
            "max_notional_per_order_usdt": DEFAULT_MAX_NOTIONAL_PER_ORDER_USDT,
            "max_gross_turnover_usdt": DEFAULT_MAX_GROSS_TURNOVER_USDT,
            "order_type": DEFAULT_ORDER_TYPE,
            "time_in_force": DEFAULT_TIME_IN_FORCE,
            "market_orders_allowed": False,
            "emergency_market_fallback_allowed": False,
            "candidate_delta_source": "distance_to_high_60_contribution_only",
        },
        "p9dh_authorizes_execution": False,
        "p9dh_authorizes_live_order": False,
        "p9dh_authorizes_candidate_execution": False,
        "p9dh_authorizes_target_plan_replacement": False,
        "p9dh_authorizes_executor_input_mutation": False,
    }


def build_phase9dh(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    started_at = now_fn()
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9dh" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9dg_path = latest_p9dg_summary(args)
    p9dg = load_optional(p9dg_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    package_path = source_output_path(p9dg, "proposal_package")
    terms_path = source_output_path(p9dg, "risk_order_terms")
    hash_binding_path = source_output_path(p9dg, "candidate_plan_hash_binding")
    fallback_path = source_output_path(p9dg, "baseline_fallback_kill_switch")
    reconciliation_path = source_output_path(p9dg, "post_run_reconciliation")
    non_auth_path = source_output_path(p9dg, "non_authorization")
    control_path = source_output_path(p9dg, "control_boundary_readback")

    package = load_optional(package_path)
    terms = load_optional(terms_path)
    hash_binding = load_optional(hash_binding_path)
    fallback = load_optional(fallback_path)
    reconciliation = load_optional(reconciliation_path)
    non_auth = load_optional(non_auth_path)
    control = load_optional(control_path)
    owner_record = owner_decision_record(args, started_at)

    gates = {
        "owner_decision_p9dh_review_recorded": str(args.owner_decision)
        == APPROVE_P9DH_DECISION,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9dg_summary_exists": bool(p9dg),
        "p9dg_summary_ready_for_p9dh": p9dg_summary_ready(p9dg),
        "p9dg_proposal_package_ready": proposal_package_ready(package),
        "p9dg_risk_order_terms_ready": risk_order_terms_ready(terms),
        "p9dg_candidate_plan_hash_binding_ready": hash_binding_ready(hash_binding),
        "p9dg_baseline_fallback_kill_switch_ready": fallback_kill_switch_ready(fallback),
        "p9dg_post_run_reconciliation_ready": reconciliation_ready(reconciliation),
        "p9dg_non_authorization_ready": non_authorization_ready(non_auth),
        "p9dg_control_boundary_ready": control_boundary_ready(control),
        "review_keeps_live_order_submission_disabled": True,
        "review_keeps_candidate_execution_disabled": True,
        "review_keeps_timer_supervisor_disabled": True,
        "review_zero_orders_fills": True,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"
    ready = status == "ready"

    review = proposal_review(
        run_id=run_id,
        now=started_at,
        p9dg_summary=p9dg,
        terms=terms,
        package=package,
        hash_binding=hash_binding,
        fallback=fallback,
        reconciliation=reconciliation,
        ready=ready,
        gates=gates,
    )
    readiness = execution_owner_gate_readiness(run_id=run_id, now=started_at, ready=ready)
    non_auth_out = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dh_non_authorization.v1",
        "authorizations": {
            "review_p9dg_proposal_package": ready,
            "future_p9di_execution_owner_gate_request_allowed": ready,
            "live_order_submission_in_p9dh": False,
            "candidate_executor_path_execution_in_p9dh": False,
            "actual_target_plan_replacement_in_p9dh": False,
            "executor_input_mutation_in_p9dh": False,
            "timer_path_load_in_p9dh": False,
            "supervisor_invocation_in_p9dh": False,
            "remote_execution_in_p9dh": False,
            "remote_sync_in_p9dh": False,
            "remote_file_write_in_p9dh": False,
            "continuous_automated_order_flow": False,
            "stage_governance_change": False,
        },
    }
    control_out = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dh_control_boundary.v1",
        "scope": "proposal_package_review_only",
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
        "proposal_package_review": proof_root / "proposal_package_review.json",
        "execution_owner_gate_readiness": proof_root / "execution_owner_gate_readiness.json",
        "non_authorization": proof_root / "non_authorization.json",
        "control_boundary_readback": proof_root / "control_boundary_readback.json",
        "owner_decision_record": root / "owner_decision_record.json",
    }
    write_json(proof_files["proposal_package_review"], review)
    write_json(proof_files["execution_owner_gate_readiness"], readiness)
    write_json(proof_files["non_authorization"], non_auth_out)
    write_json(proof_files["control_boundary_readback"], control_out)
    write_json(proof_files["owner_decision_record"], owner_record)
    manifest_path = proof_root / "proof_artifact_manifest.json"
    manifest = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9dh_proof_artifact_manifest.v1",
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
        "p9dh_review_limited_live_delta_candidate_executor_path_canary_proposal_package_ready": ready,
        "p9dg_retained_proposal_sufficient_for_p9dh_review": p9dg_summary_ready(p9dg)
        and proposal_package_ready(package)
        and risk_order_terms_ready(terms)
        and hash_binding_ready(hash_binding)
        and fallback_kill_switch_ready(fallback)
        and reconciliation_ready(reconciliation)
        and non_authorization_ready(non_auth)
        and control_boundary_ready(control),
        "proposal_package_review_only": True,
        "p9dg_proposal_package_sufficient_for_future_execution_owner_gate_discussion": ready,
        "proposal_package_sufficient_for_live_order_submission": False,
        "proposal_package_sufficient_for_candidate_execution": False,
        "eligible_for_future_p9di_execution_owner_gate": ready,
        "future_execution_gate_required": True,
        "max_cycles_total": 1,
        "max_symbols_total": 1,
        "max_orders_total": 2,
        "max_notional_per_order_usdt": DEFAULT_MAX_NOTIONAL_PER_ORDER_USDT,
        "max_gross_turnover_usdt": DEFAULT_MAX_GROSS_TURNOVER_USDT,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "market_orders_allowed": False,
        "emergency_market_fallback_allowed": False,
        "candidate_delta_source": "distance_to_high_60_contribution_only",
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
            "phase9dg_summary": evidence_file(p9dg_path),
            "phase9dg_proposal_package": evidence_file(package_path),
            "phase9dg_risk_order_terms": evidence_file(terms_path),
            "phase9dg_candidate_plan_hash_binding": evidence_file(hash_binding_path),
            "phase9dg_baseline_fallback_kill_switch": evidence_file(fallback_path),
            "phase9dg_post_run_reconciliation": evidence_file(reconciliation_path),
            "phase9dg_non_authorization": evidence_file(non_auth_path),
            "phase9dg_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "gates": gates,
        "allowed_next_gate": P9DI_GATE,
        "allowed_next_gate_scope": P9DI_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "output_files": {
            "summary": str(root / "summary.json"),
            "report": str(root / "p9dh_review_limited_live_delta_candidate_executor_path_canary_proposal_package.md"),
            "proof_artifact_manifest": str(manifest_path),
            **{key: str(path) for key, path in proof_files.items()},
        },
    }
    write_json(root / "summary.json", summary)
    (
        root
        / "p9dh_review_limited_live_delta_candidate_executor_path_canary_proposal_package.md"
    ).write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9DH Proposal Package Review",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9DH reviews the retained P9DG proposal package only. It does not execute, load, submit orders, replace target plans, or mutate executor input.",
        "",
        "## Review Verdict",
        "",
        "```text",
        (
            "p9dg_proposal_package_sufficient_for_future_execution_owner_gate_discussion = "
            f"{str(summary['p9dg_proposal_package_sufficient_for_future_execution_owner_gate_discussion']).lower()}"
        ),
        "proposal_package_sufficient_for_live_order_submission = false",
        "proposal_package_sufficient_for_candidate_execution = false",
        f"eligible_for_future_p9di_execution_owner_gate = {str(summary['eligible_for_future_p9di_execution_owner_gate']).lower()}",
        "```",
        "",
        "## Reviewed Terms",
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
        "candidate_delta_source = distance_to_high_60_contribution_only",
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
    summary, exit_code = build_phase9dh(parse_args(argv))
    print(f"status={summary['status']} run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
