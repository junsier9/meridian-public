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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cr_prepare_final_owner_live_order_gate_review_package_after_p9co import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    EXPECTED_FINAL_EVIDENCE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cs_review_p9cr_final_owner_live_order_gate_review_package_after_p9co import (  # noqa: E402
    CONTRACT_VERSION as P9CS_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CS_PARENT,
    P9CT_GATE,
    P9CT_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9ct_define_final_owner_live_order_gate_decision_scope_after_p9cs.v1"
)
APPROVE_P9CT_DECISION = (
    "approve_p9ct_define_final_owner_live_order_gate_decision_scope_after_p9cs_only_no_order_no_candidate_no_executor_or_timer_change"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9ct_final_owner_live_order_gate_decision_scope_after_p9cs"
)
P9CU_GATE = (
    "P9CU_prepare_final_owner_live_order_decision_review_package_after_p9ct_only_if_separately_requested"
)
P9CU_SCOPE = (
    "prepare_final_owner_live_order_decision_review_package_after_p9ct_no_order_no_candidate_no_executor_or_timer_change"
)

APPROVAL_GAPS = {
    "all_required_final_gate_evidence_present_and_unexpired",
    "candidate_target_plan_hash_bound_to_executor_input",
    "candidate_delta_limited_to_distance_to_high_60",
    "post_only_limit_price_does_not_cross_spread",
    "kill_switch_and_rollback_readback_available",
    "explicit_final_owner_live_order_decision",
    "post_order_observation_and_rollback_plan_bound",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Define the P9CT final owner live-order gate decision scope after "
            "retained P9CS review. P9CT is scope-definition-only: it does not "
            "SSH, read Binance, collect fresh proofs, call order-test "
            "endpoints, run supervisor or timer paths, execute the candidate, "
            "mutate executor input or target plans, remote sync, cancel "
            "orders, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cs-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CT_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9ct_define_final_owner_live_order_gate_decision_scope_after_p9cs_only_if_separately_requested"
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


def latest_p9cs_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cs_summary).strip():
        return resolve_path(args.phase9cs_summary)
    return latest_match(P9CS_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9cs_summary_ready(summary: dict[str, Any]) -> bool:
    checks = dict(summary.get("checks") or {})
    return (
        summary.get("contract_version") == P9CS_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get(
            "p9cs_review_p9cr_final_owner_live_order_gate_review_package_after_p9co_ready"
        )
        is True
        and summary.get("p9cr_package_sufficient_for_p9cs_review") is True
        and summary.get("p9cr_package_sufficient_for_future_p9ct_scope_definition")
        is True
        and summary.get("p9cr_package_sufficient_for_live_order_submission")
        is False
        and summary.get("p9cr_package_sufficient_for_candidate_execution") is False
        and summary.get("p9cr_package_sufficient_for_candidate_executor_path_entry")
        is False
        and summary.get("p9cr_satisfies_final_owner_live_order_gate") is False
        and summary.get("final_owner_live_order_gate_approval_collected") is False
        and summary.get("final_gate_evidence_collected_in_p9cr") is False
        and summary.get("fresh_proofs_collected_in_p9cr") is False
        and summary.get("final_gate_actionable_items_satisfied") is False
        and int(summary.get("remaining_evidence_gap_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE)
        and int(summary.get("remaining_approval_gap_count") or 0)
        == len(APPROVAL_GAPS)
        and summary.get("eligible_for_future_p9ct_scope_definition") is True
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and summary.get("eligible_for_future_candidate_executor_path_entry") is False
        and summary.get("fresh_remote_proof_collection_performed_in_p9cs") is False
        and summary.get("fresh_remote_account_read_performed") is False
        and summary.get("fresh_order_book_read_performed") is False
        and summary.get("exchange_filter_read_performed") is False
        and summary.get("order_test_endpoint_called") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("remote_sync_performed") is False
        and int_zero(summary, "remote_files_written")
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_enter_executor_target_plan_path_authorized")
        is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and summary.get("canary_symbol") == CANARY_SYMBOL
        and summary.get("canary_side") == CANARY_SIDE
        and float(summary.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(summary.get("max_notional_usdt") or 0) == DEFAULT_MAX_NOTIONAL_USDT
        and int(summary.get("max_orders_per_cycle") or 0)
        == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(summary.get("max_symbols_per_cycle") or 0)
        == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and summary.get("order_type") == DEFAULT_ORDER_TYPE
        and summary.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and summary.get("market_orders_allowed") is False
        and bool(summary.get("baseline_target_plan_sha256"))
        and bool(summary.get("candidate_target_plan_sha256"))
        and summary.get("baseline_target_plan_sha256")
        != summary.get("candidate_target_plan_sha256")
        and summary.get("only_distance_to_high_60_contribution_changed") is True
        and summary.get("allowed_next_gate") == P9CT_GATE
        and summary.get("allowed_next_gate_scope") == P9CT_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def p9cs_sufficiency_review_ready(review: dict[str, Any]) -> bool:
    checks = dict(review.get("checks") or {})
    return (
        review.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cs_p9cr_sufficiency_review.v1"
        and review.get("review_only") is True
        and review.get("p9cr_package_sufficient_for_p9cs_review") is True
        and review.get("p9cr_package_sufficient_for_future_p9ct_scope_definition")
        is True
        and review.get("p9cr_package_sufficient_for_live_order_submission") is False
        and review.get("p9cr_package_sufficient_for_candidate_execution") is False
        and review.get("p9cr_package_sufficient_for_candidate_executor_path_entry")
        is False
        and review.get("p9cr_satisfies_final_owner_live_order_gate") is False
        and review.get("final_owner_live_order_gate_approval_collected") is False
        and review.get("final_gate_evidence_collected_in_p9cr") is False
        and review.get("fresh_proofs_collected_in_p9cr") is False
        and review.get("final_gate_actionable_items_satisfied") is False
        and review.get("eligible_for_future_p9ct_scope_definition") is True
        and review.get("future_gate") == P9CT_GATE
        and review.get("future_gate_scope") == P9CT_SCOPE
        and review.get("future_gate_must_be_separately_requested") is True
        and int(review.get("remaining_evidence_gap_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE)
        and int(review.get("remaining_approval_gap_count") or 0) == len(APPROVAL_GAPS)
        and int_zero(review, "orders_submitted")
        and int_zero(review, "orders_canceled")
        and int_zero(review, "fill_count")
        and int_zero(review, "trade_count")
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def p9cs_gap_matrix_ready(matrix: dict[str, Any]) -> bool:
    evidence_rows = [dict(row) for row in list(matrix.get("evidence_rows") or [])]
    approval_rows = [dict(row) for row in list(matrix.get("approval_rows") or [])]
    evidence_ids = {str(row.get("evidence_id")) for row in evidence_rows}
    approval_by_item = {str(row.get("item")): row for row in approval_rows}
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cs_final_gate_gap_matrix.v1"
        and matrix.get("run_scope") == "review_p9cr_package_only"
        and matrix.get("p9cr_package_sufficient_for_p9cs_review") is True
        and matrix.get("p9cr_package_sufficient_for_future_p9ct_scope_definition")
        is True
        and matrix.get("p9cr_package_sufficient_for_live_order_submission") is False
        and matrix.get("p9cr_satisfies_final_owner_live_order_gate") is False
        and evidence_ids == set(EXPECTED_FINAL_EVIDENCE)
        and all(row.get("required") is True for row in evidence_rows)
        and all(row.get("satisfied_for_final_live_order_gate") is False for row in evidence_rows)
        and all(
            row.get("status_in_p9cr") == "packaged_only_not_final_approved"
            and row.get("collection_status_in_p9cr") == "not_collected"
            and row.get("freshness_status_in_p9cr") == "not_evaluated_for_final_gate"
            for row in evidence_rows
        )
        and set(approval_by_item)
        == APPROVAL_GAPS | {"p9co_account_blocker_cleared_and_canTrade_v2_true"}
        and approval_by_item["p9co_account_blocker_cleared_and_canTrade_v2_true"].get(
            "satisfied_in_p9cr"
        )
        is True
        and approval_by_item["p9co_account_blocker_cleared_and_canTrade_v2_true"].get(
            "remaining_gap_for_final_live_order_gate"
        )
        is False
        and all(
            approval_by_item[item].get("satisfied_in_p9cr") is False
            and approval_by_item[item].get("remaining_gap_for_final_live_order_gate")
            is True
            for item in APPROVAL_GAPS
        )
        and int(matrix.get("remaining_evidence_gap_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE)
        and int(matrix.get("remaining_approval_gap_count") or 0) == len(APPROVAL_GAPS)
    )


def p9cs_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cs_non_authorization.v1"
        and authorizations.get("review_p9cr_final_owner_live_order_gate_review_package")
        is True
        and authorizations.get("allow_future_p9ct_scope_definition_request") is True
        and authorizations.get("define_p9ct_scope_in_p9cs") is False
        and authorizations.get("fresh_remote_proof_collection") is False
        and authorizations.get("fresh_remote_account_read") is False
        and authorizations.get("fresh_order_book_read") is False
        and authorizations.get("exchange_filter_read") is False
        and authorizations.get("order_test_endpoint") is False
        and authorizations.get("remote_execution") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("final_owner_live_order_gate_approval") is False
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


def p9cs_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cs_control_boundary.v1"
        and control.get("scope")
        == "p9cr_retained_final_owner_live_order_gate_review_package_review_only"
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


def build_required_decision_evidence_contract() -> dict[str, Any]:
    rows = []
    for evidence_id, max_age in EXPECTED_FINAL_EVIDENCE.items():
        rows.append(
            {
                "evidence_id": evidence_id,
                "required": True,
                "max_age_seconds": max_age,
                "required_before": (
                    "any_order_submission"
                    if evidence_id
                    in {
                        "explicit_final_owner_live_order_decision",
                        "post_order_observation_and_rollback_plan",
                    }
                    else (
                        "any_candidate_executor_path_entry"
                        if evidence_id == "pre_order_control_boundary_readback"
                        else "final_owner_live_order_gate_approval"
                    )
                ),
                "must_be_retained": True,
                "status_in_p9ct": "defined_not_collected",
                "collection_status_in_p9ct": "not_collected",
                "freshness_status_in_p9ct": "not_evaluated",
                "future_gate_requirement": "must_be_freshly_collected_or_revalidated_before_final_owner_decision",
            }
        )
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ct_required_final_decision_evidence.v1",
        "scope_definition_only": True,
        "final_owner_gate_required_before_any_order_submission": True,
        "final_owner_gate_required_before_candidate_executor_path_entry": True,
        "p9ct_satisfies_final_owner_live_order_gate": False,
        "fresh_remote_proof_collection_performed_in_p9ct": False,
        "evidence": rows,
    }


def build_decision_scope(
    *,
    run_id: str,
    p9cs_summary_path: Path,
    p9cs: dict[str, Any],
    evidence_contract: dict[str, Any],
) -> dict[str, Any]:
    canary_terms = {
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
    }
    candidate_path_terms = {
        "candidate_may_enter_executor_target_plan_path_only_in_future_final_decision_gate": True,
        "candidate_execution_may_be_authorized_only_in_future_final_decision_gate": True,
        "target_plan_replacement_may_be_authorized_only_in_future_final_decision_gate": True,
        "executor_input_mutation_may_be_authorized_only_in_future_final_decision_gate": True,
        "must_bind_candidate_target_plan_hash": True,
        "baseline_target_plan_sha256": p9cs.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9cs.get("candidate_target_plan_sha256"),
        "must_preserve_same_timestamp_same_risk_inputs": True,
        "only_allowed_strategy_delta": "distance_to_high_60_contribution",
        "actual_candidate_executor_path_entry_authorized_in_p9ct": False,
        "actual_target_plan_replacement_authorized_in_p9ct": False,
        "actual_executor_input_mutation_authorized_in_p9ct": False,
    }
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ct_final_owner_live_order_gate_decision_scope.v1",
        "run_id": run_id,
        "scope_definition_only": True,
        "source_p9cs_summary": evidence_file(p9cs_summary_path),
        "scope_basis": "retained_p9cs_review_of_p9cr_final_owner_live_order_gate_review_package",
        "future_decision_gate_name": "final_owner_live_order_gate_decision_after_p9cs",
        "decision_scope_status": "defined_for_future_owner_gate_only",
        "final_owner_gate_may_decide": [
            "whether to approve candidate entry into the executor target-plan path",
            "whether to approve replacing the baseline executor input with the retained candidate target-plan hash",
            "whether to approve submitting one maker-only post-only canary order under exact risk terms",
            "whether post-order observation and rollback terms are sufficient for the canary",
        ],
        "final_owner_gate_may_not_skip": [
            "freshness evaluation for every required final-decision evidence row",
            "PIT-safe account permission decision from /fapi/v2/account.canTrade",
            "fresh pre-order position, balance, open-order, order-history, and trade-history fingerprints",
            "fresh order book and exchange filters proving post-only limit price does not cross spread",
            "baseline/candidate same-risk target-plan binding",
            "distance_to_high_60-only contribution delta proof",
            "kill switch and rollback readback on the target runner",
            "explicit final owner approval naming candidate path, target-plan hashes, order terms, and rollback terms",
            "pre-order control-boundary readback proving timer/supervisor/operator state is unchanged unless separately approved",
            "post-order observation and rollback plan retained before any order submission",
        ],
        "candidate_path_terms": candidate_path_terms,
        "exact_canary_terms": canary_terms,
        "required_decision_evidence_contract": evidence_contract,
        "rollback_conditions": [
            "any required final-decision evidence is missing, stale, future-timestamped, or hash-mismatched",
            "/fapi/v2/account.canTrade is false or missing",
            "/fapi/v3/account.canTrade is used for permission decisions",
            "candidate target-plan hash differs from the final no-order approved hash",
            "candidate delta affects anything outside distance_to_high_60 contribution",
            "order book no longer supports maker-only post-only execution",
            "exchange filters reject the canary order terms",
            "open-order, fill, trade, balance, or position delta is unexplained",
            "kill switch, rollback, supervisor, timer, operator, exchange, or provider health readback reports an exception",
        ],
        "out_of_scope_for_p9ct": [
            "fresh remote proof collection",
            "fresh remote account reads",
            "fresh order book or exchange filter reads",
            "order-test endpoint calls",
            "actual order placement",
            "candidate execution",
            "actual target-plan replacement",
            "executor-input mutation",
            "timer or service mutation",
            "supervisor invocation",
            "remote execution",
            "remote sync",
            "Stage 4 automation approval",
        ],
        "p9ct_satisfies_final_owner_live_order_gate": False,
        "final_owner_live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
    }


def build_phase9ct(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9ct" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cs_path = latest_p9cs_summary(args)
    p9cs = load_optional(p9cs_path)
    sufficiency_path = source_output_path(p9cs, "p9cr_sufficiency_review")
    gap_path = source_output_path(p9cs, "final_gate_gap_matrix")
    non_auth_path = source_output_path(p9cs, "non_authorization")
    control_path = source_output_path(p9cs, "control_boundary_readback")
    sufficiency = load_optional(sufficiency_path)
    gap_matrix = load_optional(gap_path)
    p9cs_non_auth = load_optional(non_auth_path)
    p9cs_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CT_DECISION

    checks = {
        "owner_decision_p9ct_scope_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cs_summary_exists": bool(p9cs),
        "p9cs_summary_ready_for_p9ct_scope_definition": p9cs_summary_ready(p9cs),
        "p9cs_sufficiency_review_ready": p9cs_sufficiency_review_ready(sufficiency),
        "p9cs_gap_matrix_ready": p9cs_gap_matrix_ready(gap_matrix),
        "p9cs_non_authorization_ready": p9cs_non_authorization_ready(p9cs_non_auth),
        "p9cs_control_boundary_ready": p9cs_control_ready(p9cs_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    evidence_contract = build_required_decision_evidence_contract()
    decision_scope = build_decision_scope(
        run_id=run_id,
        p9cs_summary_path=p9cs_path,
        p9cs=p9cs,
        evidence_contract=evidence_contract,
    )
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ct_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "define_final_owner_live_order_gate_decision_scope_after_p9cs_only_no_order_no_candidate_no_executor_or_timer_change",
        "recorded_at_utc": iso_z(now),
        "p9ct_scope_definition_approved": owner_decision_ok,
        "future_p9cu_package_preparation_request_allowed_if_scope_ready": ready,
        "fresh_remote_proof_collection_approved": False,
        "remote_execution_approved": False,
        "final_owner_live_order_gate_approved": False,
        "candidate_executor_path_entry_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9ct_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "define_final_owner_live_order_gate_decision_scope": ready,
            "allow_future_p9cu_package_preparation_request": ready,
            "prepare_p9cu_package_in_p9ct": False,
            "fresh_remote_proof_collection": False,
            "fresh_remote_account_read": False,
            "fresh_order_book_read": False,
            "exchange_filter_read": False,
            "order_test_endpoint": False,
            "remote_execution": False,
            "remote_sync": False,
            "final_owner_live_order_gate_approval": False,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9ct_control_boundary.v1",
        "run_id": run_id,
        "scope": "final_owner_live_order_gate_decision_scope_definition_only",
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
    scope_path = proof_root / "final_owner_live_order_gate_decision_scope.json"
    evidence_path = proof_root / "required_final_decision_evidence.json"
    non_auth_out_path = proof_root / "non_authorization.json"
    control_out_path = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9ct_final_owner_live_order_gate_decision_scope.md"
    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "final_owner_live_order_gate_decision_scope": str(scope_path),
        "required_final_decision_evidence": str(evidence_path),
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
        "p9ct_final_owner_live_order_gate_decision_scope_defined": ready,
        "p9cs_sufficient_for_p9ct_scope_definition": ready,
        "decision_scope_defined_after_p9cs": ready,
        "p9cr_package_sufficient_for_p9cs_review": p9cs.get(
            "p9cr_package_sufficient_for_p9cs_review"
        )
        is True,
        "p9cr_package_sufficient_for_future_p9ct_scope_definition": p9cs.get(
            "p9cr_package_sufficient_for_future_p9ct_scope_definition"
        )
        is True,
        "required_final_decision_evidence_count": len(evidence_contract["evidence"]),
        "remaining_evidence_gap_count_from_p9cs": p9cs.get(
            "remaining_evidence_gap_count"
        ),
        "remaining_approval_gap_count_from_p9cs": p9cs.get(
            "remaining_approval_gap_count"
        ),
        "final_decision_evidence_collected_in_p9ct": False,
        "fresh_proofs_collected_in_p9ct": False,
        "fresh_remote_proof_collection_approved_in_p9ct": False,
        "final_owner_live_order_gate_approval_collected": False,
        "p9ct_satisfies_final_owner_live_order_gate": False,
        "eligible_for_future_p9cu_package_preparation": ready,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "eligible_for_future_candidate_executor_path_entry": False,
        "fresh_remote_proof_collection_performed_in_p9ct": False,
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
        "canary_symbol": CANARY_SYMBOL,
        "canary_side": CANARY_SIDE,
        "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
        "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "market_orders_allowed": False,
        "baseline_target_plan_sha256": p9cs.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9cs.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9cs.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
        "source_p9cs_summary_sha256": evidence_file(p9cs_path).get("sha256", ""),
        "source_p9cs_sufficiency_review_sha256": evidence_file(sufficiency_path).get(
            "sha256", ""
        ),
        "source_p9cs_gap_matrix_sha256": evidence_file(gap_path).get("sha256", ""),
        "source_p9cs_non_authorization_sha256": evidence_file(non_auth_path).get(
            "sha256", ""
        ),
        "source_p9cs_control_boundary_sha256": evidence_file(control_path).get(
            "sha256", ""
        ),
        "allowed_next_gate": P9CU_GATE,
        "allowed_next_gate_scope": P9CU_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9cs_summary": evidence_file(p9cs_path),
            "phase9cs_p9cr_sufficiency_review": evidence_file(sufficiency_path),
            "phase9cs_final_gate_gap_matrix": evidence_file(gap_path),
            "phase9cs_non_authorization": evidence_file(non_auth_path),
            "phase9cs_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(scope_path, decision_scope)
    write_json(evidence_path, evidence_contract)
    write_json(non_auth_out_path, non_authorization)
    write_json(control_out_path, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CT Final Owner Live-Order Gate Decision Scope",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CT defines the future final owner live-order decision scope only. It does not SSH, read Binance, collect fresh proofs, call order-test endpoints, invoke supervisor/timer paths, execute the candidate, replace target plans, mutate executor input, remote sync, cancel orders, or submit orders.",
        "",
        "## Scope Result",
        "",
        "```text",
        "p9ct_final_owner_live_order_gate_decision_scope_defined = "
        f"{str(bool(summary['p9ct_final_owner_live_order_gate_decision_scope_defined'])).lower()}",
        "p9cs_sufficient_for_p9ct_scope_definition = "
        f"{str(bool(summary['p9cs_sufficient_for_p9ct_scope_definition'])).lower()}",
        "p9ct_satisfies_final_owner_live_order_gate = false",
        "final_owner_live_order_gate_approval_collected = false",
        "final_decision_evidence_collected_in_p9ct = false",
        "fresh_proofs_collected_in_p9ct = false",
        f"required_final_decision_evidence_count = {summary['required_final_decision_evidence_count']}",
        f"remaining_evidence_gap_count_from_p9cs = {summary['remaining_evidence_gap_count_from_p9cs']}",
        f"remaining_approval_gap_count_from_p9cs = {summary['remaining_approval_gap_count_from_p9cs']}",
        "```",
        "",
        "## Candidate And Canary Terms",
        "",
        "```text",
        f"baseline_target_plan_sha256 = {summary['baseline_target_plan_sha256']}",
        f"candidate_target_plan_sha256 = {summary['candidate_target_plan_sha256']}",
        "only_distance_to_high_60_contribution_changed = true",
        f"symbol = {summary['canary_symbol']}",
        f"side = {summary['canary_side']}",
        f"risk_ceiling_usdt = {summary['risk_ceiling_usdt']}",
        f"max_notional_usdt = {summary['max_notional_usdt']}",
        f"max_orders_per_cycle = {summary['max_orders_per_cycle']}",
        f"max_symbols_per_cycle = {summary['max_symbols_per_cycle']}",
        f"order_type = {summary['order_type']}",
        f"time_in_force = {summary['time_in_force']}",
        "market_orders_allowed = false",
        "```",
        "",
        "## No-Order Boundary",
        "",
        "```text",
        "fresh_remote_proof_collection_performed_in_p9ct = false",
        "fresh_remote_account_read_performed = false",
        "fresh_order_book_read_performed = false",
        "exchange_filter_read_performed = false",
        "order_test_endpoint_called = false",
        "remote_execution_performed = false",
        "remote_sync_performed = false",
        "remote_files_written = 0",
        "live_order_gate_approved = false",
        "live_order_submission_authorized = false",
        "candidate_enter_executor_target_plan_path_authorized = false",
        "candidate_execution_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
        "timer_path_load_authorized = false",
        "supervisor_invocation_authorized = false",
        "orders_submitted = 0",
        "orders_canceled = 0",
        "fill_count = 0",
        "trade_count = 0",
        "```",
        "",
        "## Allowed Next Gate",
        "",
        "```text",
        str(summary["allowed_next_gate"]),
        str(summary["allowed_next_gate_scope"]),
        "allowed_next_gate_must_be_separately_requested = true",
        "```",
    ]
    if summary.get("blockers"):
        lines.extend(["", "## Blockers", "", *[f"- {item}" for item in summary["blockers"]]])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9ct(parse_args(argv))
    print(
        "p9ct_final_owner_live_order_gate_decision_scope_defined="
        + str(
            bool(summary["p9ct_final_owner_live_order_gate_decision_scope_defined"])
        ).lower()
    )
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
