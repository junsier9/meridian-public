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

from scripts.live_trading.hv_balanced_binance_usdm_pit_safe_account_proof_builder import (  # noqa: E402
    ACCOUNT_CONFIG_ENDPOINT,
    ACCOUNT_V2_ENDPOINT,
    ACCOUNT_V3_ENDPOINT,
    API_RESTRICTIONS_ENDPOINT,
    CAN_TRADE_SOURCE,
    OPEN_ORDERS_ENDPOINT,
    POSITION_MODE_ENDPOINT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9ac_remote_runner_p9aa_readback import (  # noqa: E402
    DEFAULT_EXPECTED_EGRESS_IP,
    DEFAULT_REMOTE_CONFIG,
    DEFAULT_REMOTE_HOST,
    DEFAULT_REMOTE_REPO,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bu_executor_target_plan_preapproval_terms_review import (  # noqa: E402
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bx_live_order_gate_scope_definition import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3 import (  # noqa: E402
    CONTRACT_VERSION as P9CJ_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CJ_PARENT,
    P9CK_GATE,
    P9CK_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9ck_define_post_account_blocker_live_order_readiness_scope.v1"
)
APPROVE_P9CK_DECISION = (
    "approve_p9ck_define_post_account_blocker_live_order_readiness_scope_only_no_order_no_candidate_no_executor_or_timer_change"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9ck_post_account_blocker_live_order_readiness_scope"
)
P9CL_GATE = (
    "P9CL_prepare_post_account_blocker_live_order_readiness_review_package_only_if_separately_requested"
)
P9CL_SCOPE = (
    "prepare_post_account_blocker_live_order_readiness_review_package_from_p9ck_scope_only_no_order_no_remote_no_execution"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Define P9CK post-account-blocker live-order readiness scope only. "
            "P9CK consumes retained P9CJ evidence and writes a proof-only scope "
            "package. It does not SSH, read Binance, collect fresh proofs, run "
            "supervisor/timer paths, execute the candidate, mutate executor input "
            "or target plans, remote sync, cancel orders, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cj-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CK_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9ck_define_post_account_blocker_live_order_readiness_scope_only_if_separately_requested"
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


def latest_p9cj_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cj_summary).strip():
        return resolve_path(args.phase9cj_summary)
    return latest_match(P9CJ_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9cj_summary_ready(summary: dict[str, Any]) -> bool:
    checks = dict(summary.get("checks") or {})
    return (
        summary.get("contract_version") == P9CJ_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9cj_review_p9ci_pit_safe_read_only_account_proof_v2v3_ready")
        is True
        and summary.get("p9ci_sufficient_for_p9cj_review") is True
        and summary.get("p9ci_sufficient_to_clear_account_can_trade_blocker") is True
        and summary.get("account_can_trade_blocker_cleared_by_p9cj_review") is True
        and summary.get("p9ce_false_or_missing_reclassified_as_endpoint_schema_gap")
        is True
        and list(summary.get("live_order_readiness_blockers_after_account_review") or [])
        == []
        and list(summary.get("remaining_account_permission_blockers") or []) == []
        and summary.get("eligible_for_future_p9ck_scope_gate") is True
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and summary.get("eligible_for_future_candidate_executor_path_entry") is False
        and summary.get("fresh_remote_account_read_performed_in_p9cj") is False
        and summary.get("fresh_remote_account_read_performed") is False
        and summary.get("fresh_order_book_read_performed") is False
        and summary.get("exchange_filter_read_performed") is False
        and summary.get("order_test_endpoint_called") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("remote_sync_performed") is False
        and int_zero(summary, "remote_files_written")
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("source_p9ci_can_trade_decision_source") == CAN_TRADE_SOURCE
        and summary.get("source_p9ci_can_trade_pre") is True
        and summary.get("source_p9ci_can_trade_post") is True
        and summary.get("source_p9ci_account_v2_has_canTrade_pre") is True
        and summary.get("source_p9ci_account_v2_has_canTrade_post") is True
        and summary.get("source_p9ci_account_v3_canTrade_ignored_for_permission_decision")
        is True
        and list(summary.get("source_p9ci_live_order_readiness_blockers") or []) == []
        and summary.get("source_p9ci_position_fingerprint_stable") is True
        and summary.get("source_p9ci_open_order_fingerprint_stable") is True
        and summary.get("source_p9ci_balance_fingerprint_stable") is True
        and summary.get("source_p9ci_order_cancel_fill_trade_delta_zero") is True
        and summary.get("source_p9ci_remote_control_boundary_unchanged") is True
        and int_zero(summary, "retained_p9ci_payload_key_count")
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and summary.get("allowed_next_gate") == P9CK_GATE
        and summary.get("allowed_next_gate_scope") == P9CK_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def p9cj_clearance_ready(clearance: dict[str, Any]) -> bool:
    return (
        clearance.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cj_account_blocker_clearance_decision.v1"
        and clearance.get("status") == "ready"
        and clearance.get("prior_blocker") == "account_can_trade_false_or_missing"
        and clearance.get("can_trade_decision_source") == CAN_TRADE_SOURCE
        and clearance.get("source_p9ci_can_trade_pre") is True
        and clearance.get("source_p9ci_can_trade_post") is True
        and clearance.get("source_p9ci_account_v2_has_canTrade_pre") is True
        and clearance.get("source_p9ci_account_v2_has_canTrade_post") is True
        and clearance.get("source_p9ci_account_v3_canTrade_ignored_for_permission_decision")
        is True
        and list(clearance.get("source_p9ci_live_order_readiness_blockers") or []) == []
        and clearance.get("source_p9ci_eligible_to_clear_p9cf_account_can_trade_blocker")
        is True
        and clearance.get("p9ce_false_or_missing_reclassified_as_endpoint_schema_gap")
        is True
        and clearance.get("account_can_trade_blocker_cleared_by_p9cj_review") is True
        and list(clearance.get("remaining_account_permission_blockers") or []) == []
        and list(clearance.get("live_order_readiness_blockers_after_account_review") or [])
        == []
        and clearance.get("clears_live_order_gate") is False
        and clearance.get("approves_live_order_submission") is False
        and clearance.get("approves_candidate_execution") is False
        and clearance.get("approves_target_plan_replacement") is False
        and clearance.get("approves_executor_input_mutation") is False
    )


def p9cj_sufficiency_ready(review: dict[str, Any]) -> bool:
    return (
        review.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cj_sufficiency_review.v1"
        and review.get("status") == "ready"
        and not review.get("blockers")
        and review.get("p9ci_sufficient_for_p9cj_review") is True
        and review.get("p9ci_sufficient_to_clear_account_can_trade_blocker") is True
        and review.get("account_blocker_clearance_conclusion")
        == "clear_account_can_trade_false_or_missing_as_endpoint_schema_gap"
        and review.get("live_order_gate_conclusion") == "not_approved_by_p9cj_review"
        and review.get("fresh_remote_account_read_performed_in_p9cj") is False
        and review.get("remote_execution_performed_in_p9cj") is False
        and int_zero(review, "retained_p9ci_payload_key_count")
    )


def p9cj_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cj_non_authorization.v1"
        and authorizations.get("review_p9ci_retained_pit_safe_account_proof") is True
        and authorizations.get("clear_account_can_trade_blocker_for_future_discussion")
        is True
        and authorizations.get("fresh_remote_account_read") is False
        and authorizations.get("fresh_order_book_read") is False
        and authorizations.get("exchange_filter_read") is False
        and authorizations.get("order_test_endpoint") is False
        and authorizations.get("remote_execution") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("live_order_gate_approval") is False
        and authorizations.get("actual_candidate_executor_target_path_entry") is False
        and authorizations.get("candidate_execution") is False
        and authorizations.get("live_order_submission") is False
        and authorizations.get("actual_target_plan_replacement") is False
        and authorizations.get("actual_executor_input_mutation") is False
        and authorizations.get("live_config_mutation") is False
        and authorizations.get("operator_state_mutation") is False
        and authorizations.get("timer_or_service_mutation") is False
        and authorizations.get("timer_path_load") is False
        and authorizations.get("production_timer_service_load") is False
        and authorizations.get("supervisor_invocation") is False
        and authorizations.get("stage_governance_change") is False
    )


def p9cj_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cj_control_boundary.v1"
        and control.get("scope") == "p9ci_retained_evidence_review_only"
        and control.get("ssh_invoked") is False
        and control.get("remote_network_connection_performed") is False
        and control.get("fresh_remote_account_read_performed") is False
        and control.get("fresh_order_book_read_performed") is False
        and control.get("exchange_filter_read_performed") is False
        and control.get("order_test_endpoint_called") is False
        and control.get("fresh_proofs_collected") is False
        and control.get("entered_timer_path") is False
        and control.get("ran_supervisor") is False
        and control.get("remote_sync_performed") is False
        and control.get("remote_execution_performed") is False
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


def required_fresh_proofs() -> list[dict[str, Any]]:
    return [
        {
            "proof_id": "pit_safe_v2v3_account_proof",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "must_be_from_target_runner": True,
            "required_endpoints": [
                ACCOUNT_V2_ENDPOINT,
                ACCOUNT_V3_ENDPOINT,
                ACCOUNT_CONFIG_ENDPOINT,
                POSITION_MODE_ENDPOINT,
                OPEN_ORDERS_ENDPOINT,
                API_RESTRICTIONS_ENDPOINT,
            ],
            "acceptance": [
                "canTrade decision source must equal /fapi/v2/account.canTrade",
                "can_trade_pre and can_trade_post must both be true",
                "/fapi/v3/account.canTrade must be ignored for permission decisions",
                "withdrawal permission must remain disabled",
                f"egress IP must equal {DEFAULT_EXPECTED_EGRESS_IP}",
            ],
        },
        {
            "proof_id": "fresh_position_open_order_balance_fingerprints",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "acceptance": [
                "position fingerprint stable or explicitly explained",
                "open-order fingerprint stable",
                "open-order count remains zero before final order discussion",
                "balance fingerprint stable or explicitly explained",
            ],
        },
        {
            "proof_id": "fresh_order_trade_history_delta",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "acceptance": [
                "order history fingerprint stable",
                "trade history fingerprint stable",
                "order/cancel/fill/trade delta equals zero before final live-order gate",
            ],
        },
        {
            "proof_id": "fresh_order_book_and_exchange_filters",
            "max_age_seconds": 10,
            "required_before": "future_live_order_gate_approval",
            "acceptance": [
                "fresh book supports maker-only post-only limit placement",
                "exchange filters bind tick size, step size, min notional, and precision",
                "order size remains within max_notional_usdt and exchange filters",
            ],
        },
        {
            "proof_id": "same_risk_paired_target_plan_binding",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "acceptance": [
                "baseline and candidate generated at the same timestamp",
                "baseline and candidate use identical risk inputs",
                "candidate target-plan hash is retained",
                "executor remains baseline-only until a separate live-order gate",
            ],
        },
        {
            "proof_id": "distance_to_high_60_only_delta",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "acceptance": [
                "only distance_to_high_60 contribution may differ",
                "non-target contribution deltas must equal zero",
                "changed symbol count must stay within future gate terms",
            ],
        },
        {
            "proof_id": "no_order_candidate_target_plan_replacement_dry_run",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "acceptance": [
                "simulated replacement may point to candidate hash",
                "actual executor input remains baseline-only",
                "actual target plan is not replaced",
                "orders_submitted, orders_canceled, fill_count, and trade_count remain zero",
            ],
        },
        {
            "proof_id": "kill_switch_and_rollback_readback",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "acceptance": [
                "kill switch readback available on target runner",
                "rollback command readback available",
                "timer/supervisor/operator/live config boundaries unchanged",
            ],
        },
        {
            "proof_id": "final_owner_live_order_gate_approval",
            "max_age_seconds": 300,
            "required_before": "any_order_submission",
            "acceptance": [
                "separate owner gate names exact risk/order terms",
                "separate owner gate authorizes candidate executor path entry if needed",
                "separate owner gate authorizes one canary order only if all fresh proofs pass",
            ],
        },
    ]


def build_scope_definition() -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ck_post_account_blocker_live_order_readiness_scope.v1",
        "scope_definition_only": True,
        "account_blocker_status": "cleared_by_p9cj_retained_review",
        "future_gate_name": "post_account_blocker_live_order_readiness_review",
        "future_gate_may_discuss": [
            "whether a post-account-blocker review package is complete",
            "whether to request fresh read-only remote proof collection in a later separate gate",
            "whether final live-order gate prerequisites can be enumerated after fresh proofs",
        ],
        "future_gate_may_not_skip": [
            "new PIT-safe v2/v3 account proof after P9CJ",
            "fresh order-book and exchange-filter proof",
            "same-risk paired target-plan binding",
            "no-order candidate target-plan replacement dry-run",
            "kill switch and rollback readback",
            "separate final owner live-order gate",
        ],
        "canary_terms": {
            "symbol": CANARY_SYMBOL,
            "side": CANARY_SIDE,
            "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
            "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
            "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
            "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
            "order_type": DEFAULT_ORDER_TYPE,
            "time_in_force": DEFAULT_TIME_IN_FORCE,
            "market_orders_allowed": False,
            "post_only_required": True,
            "maker_only_required": True,
            "limit_order_must_not_cross_spread": True,
            "candidate_delta_source": "distance_to_high_60_contribution_only",
        },
        "target_runner": {
            "remote_host": DEFAULT_REMOTE_HOST,
            "remote_repo": DEFAULT_REMOTE_REPO,
            "remote_config": DEFAULT_REMOTE_CONFIG,
            "expected_egress_ip": DEFAULT_EXPECTED_EGRESS_IP,
        },
        "rollback_conditions": [
            "any required fresh proof is missing, stale, or hash-mismatched",
            "future v2 account canTrade is false or missing",
            "v3 account canTrade is used for permission decisions",
            "candidate target-plan hash differs from the no-order approved hash",
            "executor input is not explicitly baseline-only before final gate",
            "candidate delta affects anything outside distance_to_high_60 contribution",
            "open-order, fill, trade, balance, or position delta is unexplained",
            "order book no longer supports maker-only post-only execution",
            "exchange filters reject the canary order terms",
            "supervisor, timer, operator, exchange, or provider health readback reports an exception",
        ],
        "out_of_scope_for_p9ck": [
            "fresh remote proof collection",
            "actual order placement",
            "candidate execution",
            "actual target-plan replacement",
            "executor-input mutation",
            "live config mutation",
            "operator-state mutation",
            "timer or service mutation",
            "supervisor invocation",
            "remote sync",
            "remote execution",
            "stage change",
        ],
    }


def build_phase9ck_define_post_account_blocker_live_order_readiness_scope(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9ck" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cj_summary_path = latest_p9cj_summary(args)
    p9cj = load_optional(p9cj_summary_path)
    clearance_path = source_output_path(p9cj, "account_blocker_clearance_decision")
    review_path = source_output_path(p9cj, "p9ci_sufficiency_review")
    non_auth_path = source_output_path(p9cj, "non_authorization")
    control_path = source_output_path(p9cj, "control_boundary_readback")
    clearance = load_optional(clearance_path)
    review = load_optional(review_path)
    p9cj_non_auth = load_optional(non_auth_path)
    p9cj_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CK_DECISION
    checks = {
        "owner_decision_p9ck_scope_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cj_summary_exists": bool(p9cj),
        "p9cj_summary_ready_for_post_account_blocker_scope": p9cj_summary_ready(p9cj),
        "p9cj_account_blocker_clearance_ready": p9cj_clearance_ready(clearance),
        "p9cj_sufficiency_review_ready": p9cj_sufficiency_ready(review),
        "p9cj_non_authorization_ready": p9cj_non_authorization_ready(p9cj_non_auth),
        "p9cj_control_boundary_ready": p9cj_control_ready(p9cj_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    scope = build_scope_definition()
    fresh_proofs = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ck_required_fresh_proofs.v1",
        "scope_definition_only": True,
        "proofs": required_fresh_proofs(),
        "fresh_proofs_required_before_any_future_order_submission": True,
        "p9ck_satisfies_fresh_proofs": False,
        "fresh_remote_proof_collection_performed_in_p9ck": False,
    }
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ck_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "define_post_account_blocker_live_order_readiness_scope_only_no_order_no_candidate_no_executor_or_timer_change",
        "recorded_at_utc": iso_z(now),
        "scope_definition_approved": owner_decision_ok,
        "fresh_remote_proof_collection_approved": False,
        "remote_execution_approved": False,
        "live_order_gate_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ck_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "define_post_account_blocker_live_order_readiness_scope": ready,
            "prepare_future_p9cl_review_package": ready,
            "fresh_remote_proof_collection": False,
            "fresh_remote_account_read": False,
            "fresh_order_book_read": False,
            "exchange_filter_read": False,
            "order_test_endpoint": False,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9ck_control_boundary.v1",
        "run_id": run_id,
        "scope": "post_account_blocker_live_order_readiness_scope_definition_only",
        "ssh_invoked": False,
        "remote_network_connection_performed": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
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
    scope_path = proof_root / "post_account_blocker_live_order_readiness_scope.json"
    proofs_path = proof_root / "required_fresh_proofs.json"
    non_auth_out_path = proof_root / "non_authorization.json"
    control_out_path = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9ck_post_account_blocker_live_order_readiness_scope.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "post_account_blocker_live_order_readiness_scope": str(scope_path),
        "required_fresh_proofs": str(proofs_path),
        "non_authorization": str(non_auth_out_path),
        "control_boundary_readback": str(control_out_path),
        "report": str(report_path),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "p9ck_post_account_blocker_live_order_readiness_scope_defined": ready,
        "p9cj_sufficient_for_p9ck_scope_definition": p9cj_summary_ready(p9cj),
        "account_blocker_cleared_before_p9ck": p9cj.get(
            "account_can_trade_blocker_cleared_by_p9cj_review"
        )
        is True,
        "live_order_readiness_scope_defined_after_account_blocker_clearance": ready,
        "required_fresh_proof_count": len(fresh_proofs["proofs"]),
        "fresh_proofs_required_before_any_future_order_submission": True,
        "fresh_proofs_satisfied_by_p9ck": False,
        "eligible_for_future_p9cl_review_package": ready,
        "eligible_for_future_fresh_remote_proof_collection": False,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "eligible_for_future_candidate_executor_path_entry": False,
        "fresh_remote_proof_collection_performed_in_p9ck": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
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
        "allowed_next_gate": P9CL_GATE,
        "allowed_next_gate_scope": P9CL_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "canary_symbol": CANARY_SYMBOL,
        "canary_side": CANARY_SIDE,
        "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
        "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "market_orders_allowed": False,
        "target_runner_remote_host": DEFAULT_REMOTE_HOST,
        "target_runner_remote_repo": DEFAULT_REMOTE_REPO,
        "target_runner_remote_config": DEFAULT_REMOTE_CONFIG,
        "target_runner_expected_egress_ip": DEFAULT_EXPECTED_EGRESS_IP,
        "source_p9cj_account_blocker_cleared": p9cj.get(
            "account_can_trade_blocker_cleared_by_p9cj_review"
        ),
        "source_p9cj_live_order_readiness_blockers_after_account_review": p9cj.get(
            "live_order_readiness_blockers_after_account_review"
        ),
        "source_p9cj_remaining_account_permission_blockers": p9cj.get(
            "remaining_account_permission_blockers"
        ),
        "source_p9cj_can_trade_decision_source": p9cj.get(
            "source_p9ci_can_trade_decision_source"
        ),
        "source_p9cj_can_trade_pre": p9cj.get("source_p9ci_can_trade_pre"),
        "source_p9cj_can_trade_post": p9cj.get("source_p9ci_can_trade_post"),
        "source_p9cj_open_position_count_pre": p9cj.get(
            "source_p9ci_open_position_count_pre"
        ),
        "source_p9cj_open_position_count_post": p9cj.get(
            "source_p9ci_open_position_count_post"
        ),
        "source_p9cj_open_order_count_pre": p9cj.get(
            "source_p9ci_open_order_count_pre"
        ),
        "source_p9cj_open_order_count_post": p9cj.get(
            "source_p9ci_open_order_count_post"
        ),
        "source_p9cj_order_cancel_fill_trade_delta_zero": p9cj.get(
            "source_p9ci_order_cancel_fill_trade_delta_zero"
        ),
        "source_p9cj_remote_control_boundary_unchanged": p9cj.get(
            "source_p9ci_remote_control_boundary_unchanged"
        ),
        "source_evidence": {
            "phase9cj_summary": evidence_file(p9cj_summary_path),
            "phase9cj_account_blocker_clearance": evidence_file(clearance_path),
            "phase9cj_sufficiency_review": evidence_file(review_path),
            "phase9cj_non_authorization": evidence_file(non_auth_path),
            "phase9cj_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(scope_path, scope)
    write_json(proofs_path, fresh_proofs)
    write_json(non_auth_out_path, non_authorization)
    write_json(control_out_path, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary, scope, fresh_proofs), encoding="utf-8")
    return summary, 0 if ready else 2


def build_phase9ck(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    return build_phase9ck_define_post_account_blocker_live_order_readiness_scope(
        args,
        now_fn=now_fn,
    )


def render_markdown(
    summary: dict[str, Any],
    scope: dict[str, Any],
    fresh_proofs: dict[str, Any],
) -> str:
    canary = dict(scope.get("canary_terms") or {})
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CK Post-Account-Blocker Live-Order Readiness Scope",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CK defines the post-account-blocker live-order readiness scope only. It does not collect fresh proofs, SSH, read Binance, run supervisor or timer paths, execute the candidate, replace target plans, mutate executor input, cancel orders, or submit orders.",
        "",
        "## Scope Result",
        "",
        "```text",
        "p9ck_post_account_blocker_live_order_readiness_scope_defined = "
        f"{str(bool(summary['p9ck_post_account_blocker_live_order_readiness_scope_defined'])).lower()}",
        "account_blocker_cleared_before_p9ck = "
        f"{str(bool(summary['account_blocker_cleared_before_p9ck'])).lower()}",
        "fresh_proofs_satisfied_by_p9ck = false",
        "eligible_for_future_live_order_submission = false",
        "live_order_gate_approved = false",
        "live_order_submission_authorized = false",
        "candidate_execution_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Canary Discussion Boundary",
        "",
        "```text",
        f"symbol = {canary.get('symbol')}",
        f"side = {canary.get('side')}",
        f"risk_ceiling_usdt = {canary.get('risk_ceiling_usdt')}",
        f"max_notional_usdt = {canary.get('max_notional_usdt')}",
        f"max_orders_per_cycle = {canary.get('max_orders_per_cycle')}",
        f"max_symbols_per_cycle = {canary.get('max_symbols_per_cycle')}",
        f"order_type = {canary.get('order_type')}",
        f"time_in_force = {canary.get('time_in_force')}",
        "market_orders_allowed = false",
        "post_only_required = true",
        "maker_only_required = true",
        "```",
        "",
        "## Required Fresh Proofs",
        "",
    ]
    for proof in list(fresh_proofs.get("proofs") or []):
        lines.append(
            f"- `{proof['proof_id']}` max_age_seconds={proof['max_age_seconds']}"
        )
    lines.extend(["", "## Out Of Scope", ""])
    for item in list(scope.get("out_of_scope_for_p9ck") or []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Allowed Next Gate",
            "",
            "```text",
            str(summary["allowed_next_gate"]),
            str(summary["allowed_next_gate_scope"]),
            "allowed_next_gate_must_be_separately_requested = true",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9ck(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
