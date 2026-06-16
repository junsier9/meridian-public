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
    CONTRACT_VERSION as P9CR_CONTRACT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_OUTPUT_PARENT as P9CR_PARENT,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    EXPECTED_FINAL_EVIDENCE,
    P9CS_GATE,
    P9CS_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9cs_review_p9cr_final_owner_live_order_gate_review_package_after_p9co.v1"
)
APPROVE_P9CS_DECISION = (
    "approve_p9cs_review_p9cr_final_owner_live_order_gate_review_package_after_p9co_only_no_order_no_candidate_no_executor_or_timer_change"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9cs_review_p9cr_final_owner_live_order_gate_review_package_after_p9co"
)
P9CT_GATE = (
    "P9CT_define_final_owner_live_order_gate_decision_scope_after_p9cs_only_if_separately_requested"
)
P9CT_SCOPE = (
    "define_final_owner_live_order_gate_decision_scope_after_p9cs_no_order_no_candidate_no_executor_or_timer_change"
)

APPROVAL_ITEM_EXPECTATIONS = {
    "p9co_account_blocker_cleared_and_canTrade_v2_true": True,
    "all_required_final_gate_evidence_present_and_unexpired": False,
    "candidate_target_plan_hash_bound_to_executor_input": False,
    "candidate_delta_limited_to_distance_to_high_60": False,
    "post_only_limit_price_does_not_cross_spread": False,
    "kill_switch_and_rollback_readback_available": False,
    "explicit_final_owner_live_order_decision": False,
    "post_order_observation_and_rollback_plan_bound": False,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review retained P9CR final owner live-order gate review package "
            "evidence. P9CS is local retained-evidence review only: it does "
            "not SSH, read Binance, collect fresh proofs, call order-test "
            "endpoints, run supervisor or timer paths, execute the candidate, "
            "mutate executor input or target plans, remote sync, cancel "
            "orders, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cr-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CS_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9cs_review_p9cr_final_owner_live_order_gate_review_package_after_p9co_only_if_separately_requested"
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


def latest_p9cr_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cr_summary).strip():
        return resolve_path(args.phase9cr_summary)
    return latest_match(P9CR_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9cr_summary_ready(summary: dict[str, Any]) -> bool:
    checks = dict(summary.get("checks") or {})
    return (
        summary.get("contract_version") == P9CR_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9cr_final_owner_live_order_gate_review_package_prepared")
        is True
        and summary.get("p9cq_sufficient_for_p9cr_review_package") is True
        and summary.get("review_package_prepared_after_p9co") is True
        and int(summary.get("required_final_gate_evidence_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE)
        and summary.get("final_gate_evidence_collected_in_p9cr") is False
        and summary.get("fresh_proofs_collected_in_p9cr") is False
        and summary.get("fresh_remote_proof_collection_approved_in_p9cr") is False
        and summary.get("final_owner_live_order_gate_approval_collected") is False
        and summary.get("p9cr_satisfies_final_owner_live_order_gate") is False
        and summary.get("eligible_for_future_p9cs_package_review") is True
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and summary.get("eligible_for_future_candidate_executor_path_entry") is False
        and summary.get("fresh_remote_proof_collection_performed_in_p9cr") is False
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
        and bool(summary.get("source_p9co_baseline_target_plan_sha256"))
        and bool(summary.get("source_p9co_candidate_target_plan_sha256"))
        and summary.get("source_p9co_baseline_target_plan_sha256")
        != summary.get("source_p9co_candidate_target_plan_sha256")
        and summary.get("source_p9co_only_distance_to_high_60_contribution_changed")
        is True
        and summary.get("source_p9co_can_trade_pre") is True
        and summary.get("source_p9co_can_trade_post") is True
        and summary.get("source_p9co_open_order_count_pre") == 0
        and summary.get("source_p9co_open_order_count_post") == 0
        and summary.get("source_p9co_order_cancel_fill_trade_delta_zero") is True
        and summary.get("source_p9co_remote_control_boundary_unchanged") is True
        and summary.get("allowed_next_gate") == P9CS_GATE
        and summary.get("allowed_next_gate_scope") == P9CS_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def canary_terms_ready(canary: dict[str, Any]) -> bool:
    return (
        canary.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cr_canary_order_terms.v1"
        and canary.get("package_only") is True
        and canary.get("symbol") == CANARY_SYMBOL
        and canary.get("side") == CANARY_SIDE
        and float(canary.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(canary.get("max_notional_usdt") or 0) == DEFAULT_MAX_NOTIONAL_USDT
        and int(canary.get("max_orders_per_cycle") or 0)
        == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(canary.get("max_symbols_per_cycle") or 0)
        == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and canary.get("order_type") == DEFAULT_ORDER_TYPE
        and canary.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and canary.get("market_orders_allowed") is False
        and canary.get("post_only_required") is True
        and canary.get("maker_only_required") is True
        and canary.get("limit_order_must_not_cross_spread") is True
        and canary.get("candidate_delta_source")
        == "distance_to_high_60_contribution_only"
        and canary.get("would_submit_order") is False
    )


def final_gate_evidence_plan_ready(plan: dict[str, Any]) -> bool:
    rows = [dict(row) for row in list(plan.get("evidence") or [])]
    by_id = {str(row.get("evidence_id")): row for row in rows}
    return (
        plan.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cr_final_gate_evidence_plan.v1"
        and plan.get("package_only") is True
        and plan.get("final_owner_gate_required_before_any_order_submission") is True
        and plan.get("p9cr_satisfies_final_owner_live_order_gate") is False
        and plan.get("fresh_remote_proof_collection_performed_in_p9cr") is False
        and set(by_id) == set(EXPECTED_FINAL_EVIDENCE)
        and all(
            by_id[key].get("required") is True
            and int(by_id[key].get("max_age_seconds") or 0) == max_age
            and by_id[key].get("must_be_retained") is True
            and by_id[key].get("status_in_p9cr")
            == "packaged_only_not_final_approved"
            and by_id[key].get("collection_status_in_p9cr") == "not_collected"
            and by_id[key].get("freshness_status_in_p9cr")
            == "not_evaluated_for_final_gate"
            for key, max_age in EXPECTED_FINAL_EVIDENCE.items()
        )
    )


def approval_checklist_ready(checklist: dict[str, Any]) -> bool:
    rows = [dict(row) for row in list(checklist.get("approval_items") or [])]
    by_item = {str(row.get("item")): row for row in rows}
    return (
        checklist.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cr_approval_checklist.v1"
        and checklist.get("package_only") is True
        and set(by_item) == set(APPROVAL_ITEM_EXPECTATIONS)
        and all(
            by_item[item].get("required_for_final_owner_live_order_gate") is True
            and by_item[item].get("satisfied_in_p9cr") is expected
            for item, expected in APPROVAL_ITEM_EXPECTATIONS.items()
        )
        and len(checklist.get("rollback_conditions") or []) >= 8
    )


def candidate_path_terms_ready(terms: dict[str, Any]) -> bool:
    return (
        terms.get("candidate_may_enter_executor_target_plan_path_only_in_final_gate")
        is True
        and terms.get("candidate_execution_may_be_authorized_only_in_final_gate")
        is True
        and terms.get("target_plan_replacement_may_be_authorized_only_in_final_gate")
        is True
        and terms.get("executor_input_mutation_may_be_authorized_only_in_final_gate")
        is True
        and terms.get("must_bind_candidate_target_plan_hash") is True
        and terms.get("must_preserve_same_timestamp_same_risk_inputs") is True
        and terms.get("only_allowed_strategy_delta")
        == "distance_to_high_60_contribution"
    )


def p9cr_review_package_ready(
    package: dict[str, Any],
    *,
    summary: dict[str, Any],
) -> bool:
    canary = dict(package.get("canary_order_terms") or {})
    evidence_plan = dict(package.get("final_gate_evidence_plan") or {})
    checklist = dict(package.get("approval_checklist") or {})
    return (
        package.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cr_review_package.v1"
        and package.get("package_only") is True
        and package.get("package_decision") == "prepared_for_future_review_only"
        and package.get("future_gate_name") == "final_owner_live_order_gate_after_p9co"
        and canary_terms_ready(canary)
        and final_gate_evidence_plan_ready(evidence_plan)
        and approval_checklist_ready(checklist)
        and candidate_path_terms_ready(dict(package.get("candidate_path_terms") or {}))
        and bool(package.get("baseline_target_plan_sha256"))
        and bool(package.get("candidate_target_plan_sha256"))
        and package.get("baseline_target_plan_sha256")
        == summary.get("source_p9co_baseline_target_plan_sha256")
        and package.get("candidate_target_plan_sha256")
        == summary.get("source_p9co_candidate_target_plan_sha256")
        and package.get("baseline_target_plan_sha256")
        != package.get("candidate_target_plan_sha256")
        and package.get("only_distance_to_high_60_contribution_changed") is True
        and package.get("p9cr_satisfies_final_owner_live_order_gate") is False
        and package.get("final_owner_live_order_gate_approved") is False
        and package.get("live_order_submission_authorized") is False
        and package.get("candidate_enter_executor_target_plan_path_authorized") is False
        and package.get("candidate_execution_authorized") is False
        and package.get("target_plan_replacement_authorized") is False
        and package.get("executor_input_mutation_authorized") is False
        and int_zero(package, "orders_submitted")
        and int_zero(package, "orders_canceled")
        and int_zero(package, "fill_count")
        and int_zero(package, "trade_count")
        and "whether to approve candidate entry into the executor target-plan path"
        in list(package.get("future_gate_may_discuss") or [])
        and "whether to submit one maker-only post-only canary order under exact risk terms"
        in list(package.get("future_gate_may_discuss") or [])
        and "PIT-safe account permission decision from /fapi/v2/account.canTrade"
        in list(package.get("future_gate_may_not_skip") or [])
        and "explicit final owner approval naming candidate path, order terms, and rollback terms"
        in list(package.get("future_gate_may_not_skip") or [])
    )


def p9cr_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cr_non_authorization.v1"
        and authorizations.get("prepare_final_owner_live_order_gate_review_package")
        is True
        and authorizations.get("review_p9cr_package") is True
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


def p9cr_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cr_control_boundary.v1"
        and control.get("scope") == "final_owner_live_order_gate_review_package_preparation_only"
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


def build_gap_matrix(
    *,
    package: dict[str, Any],
    ready: bool,
) -> dict[str, Any]:
    evidence_plan = dict(package.get("final_gate_evidence_plan") or {})
    checklist = dict(package.get("approval_checklist") or {})
    evidence_rows = []
    for row in list(evidence_plan.get("evidence") or []):
        item = dict(row)
        evidence_rows.append(
            {
                "evidence_id": item.get("evidence_id"),
                "required": item.get("required") is True,
                "status_in_p9cr": item.get("status_in_p9cr"),
                "collection_status_in_p9cr": item.get("collection_status_in_p9cr"),
                "freshness_status_in_p9cr": item.get("freshness_status_in_p9cr"),
                "satisfied_for_final_live_order_gate": False,
            }
        )
    approval_rows = []
    for row in list(checklist.get("approval_items") or []):
        item = dict(row)
        approval_rows.append(
            {
                "item": item.get("item"),
                "required_for_final_owner_live_order_gate": item.get(
                    "required_for_final_owner_live_order_gate"
                )
                is True,
                "satisfied_in_p9cr": item.get("satisfied_in_p9cr") is True,
                "remaining_gap_for_final_live_order_gate": item.get("satisfied_in_p9cr")
                is not True,
            }
        )
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cs_final_gate_gap_matrix.v1",
        "run_scope": "review_p9cr_package_only",
        "p9cr_package_sufficient_for_p9cs_review": ready,
        "p9cr_package_sufficient_for_future_p9ct_scope_definition": ready,
        "p9cr_package_sufficient_for_live_order_submission": False,
        "p9cr_satisfies_final_owner_live_order_gate": False,
        "evidence_rows": evidence_rows,
        "approval_rows": approval_rows,
        "remaining_evidence_gap_count": len(
            [row for row in evidence_rows if not row["satisfied_for_final_live_order_gate"]]
        ),
        "remaining_approval_gap_count": len(
            [row for row in approval_rows if row["remaining_gap_for_final_live_order_gate"]]
        ),
    }


def build_sufficiency_review(
    *,
    checks: dict[str, bool],
    ready: bool,
    p9cr: dict[str, Any],
    package: dict[str, Any],
    gap_matrix: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cs_p9cr_sufficiency_review.v1",
        "review_only": True,
        "p9cr_package_sufficient_for_p9cs_review": ready,
        "p9cr_package_sufficient_for_future_p9ct_scope_definition": ready,
        "p9cr_package_sufficient_for_live_order_submission": False,
        "p9cr_package_sufficient_for_candidate_execution": False,
        "p9cr_package_sufficient_for_candidate_executor_path_entry": False,
        "p9cr_satisfies_final_owner_live_order_gate": False,
        "final_owner_live_order_gate_approval_collected": False,
        "final_gate_evidence_collected_in_p9cr": False,
        "fresh_proofs_collected_in_p9cr": False,
        "final_gate_actionable_items_satisfied": False,
        "eligible_for_future_p9ct_scope_definition": ready,
        "future_gate": P9CT_GATE,
        "future_gate_scope": P9CT_SCOPE,
        "future_gate_must_be_separately_requested": True,
        "canary_symbol": CANARY_SYMBOL,
        "canary_side": CANARY_SIDE,
        "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "market_orders_allowed": False,
        "baseline_target_plan_sha256": package.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": package.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": package.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
        "source_p9cr_summary_sha256": p9cr.get("source_p9cq_summary_sha256"),
        "remaining_evidence_gap_count": gap_matrix["remaining_evidence_gap_count"],
        "remaining_approval_gap_count": gap_matrix["remaining_approval_gap_count"],
        "checks": checks,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def build_phase9cs(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cs" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cr_path = latest_p9cr_summary(args)
    p9cr = load_optional(p9cr_path)
    package_path = source_output_path(p9cr, "final_owner_live_order_gate_review_package")
    canary_path = source_output_path(p9cr, "canary_order_terms")
    evidence_plan_path = source_output_path(p9cr, "final_gate_evidence_plan")
    approval_path = source_output_path(p9cr, "approval_checklist")
    non_auth_path = source_output_path(p9cr, "non_authorization")
    control_path = source_output_path(p9cr, "control_boundary_readback")
    package = load_optional(package_path)
    canary = load_optional(canary_path)
    evidence_plan = load_optional(evidence_plan_path)
    approval = load_optional(approval_path)
    p9cr_non_auth = load_optional(non_auth_path)
    p9cr_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CS_DECISION

    checks = {
        "owner_decision_p9cs_review_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cr_summary_exists": bool(p9cr),
        "p9cr_summary_ready_for_p9cs_review": p9cr_summary_ready(p9cr),
        "p9cr_review_package_ready": p9cr_review_package_ready(
            package,
            summary=p9cr,
        ),
        "p9cr_canary_terms_file_ready": canary_terms_ready(canary),
        "p9cr_canary_terms_file_matches_package": canary
        == dict(package.get("canary_order_terms") or {}),
        "p9cr_final_gate_evidence_plan_file_ready": final_gate_evidence_plan_ready(
            evidence_plan
        ),
        "p9cr_final_gate_evidence_plan_file_matches_package": evidence_plan
        == dict(package.get("final_gate_evidence_plan") or {}),
        "p9cr_approval_checklist_file_ready": approval_checklist_ready(approval),
        "p9cr_approval_checklist_file_matches_package": approval
        == dict(package.get("approval_checklist") or {}),
        "p9cr_non_authorization_ready": p9cr_non_authorization_ready(p9cr_non_auth),
        "p9cr_control_boundary_ready": p9cr_control_ready(p9cr_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    gap_matrix = build_gap_matrix(package=package, ready=ready)
    sufficiency = build_sufficiency_review(
        checks=checks,
        ready=ready,
        p9cr=p9cr,
        package=package,
        gap_matrix=gap_matrix,
    )
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cs_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "review_p9cr_final_owner_live_order_gate_review_package_only_no_order_no_candidate_no_executor_or_timer_change",
        "recorded_at_utc": iso_z(now),
        "p9cs_review_p9cr_package_approved": owner_decision_ok,
        "future_p9ct_scope_definition_request_allowed_if_review_ready": ready,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9cs_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "review_p9cr_final_owner_live_order_gate_review_package": ready,
            "allow_future_p9ct_scope_definition_request": ready,
            "define_p9ct_scope_in_p9cs": False,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9cs_control_boundary.v1",
        "run_id": run_id,
        "scope": "p9cr_retained_final_owner_live_order_gate_review_package_review_only",
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
    review_path = proof_root / "p9cr_sufficiency_review.json"
    gap_path = proof_root / "final_gate_gap_matrix.json"
    non_auth_out_path = proof_root / "non_authorization.json"
    control_out_path = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9cs_review_p9cr.md"
    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "p9cr_sufficiency_review": str(review_path),
        "final_gate_gap_matrix": str(gap_path),
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
        "p9cs_review_p9cr_final_owner_live_order_gate_review_package_after_p9co_ready": ready,
        "p9cr_package_sufficient_for_p9cs_review": ready,
        "p9cr_package_sufficient_for_future_p9ct_scope_definition": ready,
        "p9cr_package_sufficient_for_live_order_submission": False,
        "p9cr_package_sufficient_for_candidate_execution": False,
        "p9cr_package_sufficient_for_candidate_executor_path_entry": False,
        "p9cr_satisfies_final_owner_live_order_gate": False,
        "final_owner_live_order_gate_approval_collected": False,
        "final_gate_evidence_collected_in_p9cr": False,
        "fresh_proofs_collected_in_p9cr": False,
        "fresh_remote_proof_collection_approved_in_p9cs": False,
        "final_gate_actionable_items_satisfied": False,
        "eligible_for_future_p9ct_scope_definition": ready,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "eligible_for_future_candidate_executor_path_entry": False,
        "fresh_remote_proof_collection_performed_in_p9cs": False,
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
        "remaining_evidence_gap_count": gap_matrix["remaining_evidence_gap_count"],
        "remaining_approval_gap_count": gap_matrix["remaining_approval_gap_count"],
        "source_p9cr_summary_sha256": evidence_file(p9cr_path).get("sha256", ""),
        "source_p9cr_review_package_sha256": evidence_file(package_path).get(
            "sha256", ""
        ),
        "source_p9cr_canary_order_terms_sha256": evidence_file(canary_path).get(
            "sha256", ""
        ),
        "source_p9cr_final_gate_evidence_plan_sha256": evidence_file(
            evidence_plan_path
        ).get("sha256", ""),
        "source_p9cr_approval_checklist_sha256": evidence_file(approval_path).get(
            "sha256", ""
        ),
        "source_p9cr_non_authorization_sha256": evidence_file(non_auth_path).get(
            "sha256", ""
        ),
        "source_p9cr_control_boundary_sha256": evidence_file(control_path).get(
            "sha256", ""
        ),
        "baseline_target_plan_sha256": package.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": package.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": package.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
        "allowed_next_gate": P9CT_GATE,
        "allowed_next_gate_scope": P9CT_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9cr_summary": evidence_file(p9cr_path),
            "phase9cr_final_owner_live_order_gate_review_package": evidence_file(
                package_path
            ),
            "phase9cr_canary_order_terms": evidence_file(canary_path),
            "phase9cr_final_gate_evidence_plan": evidence_file(evidence_plan_path),
            "phase9cr_approval_checklist": evidence_file(approval_path),
            "phase9cr_non_authorization": evidence_file(non_auth_path),
            "phase9cr_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(review_path, sufficiency)
    write_json(gap_path, gap_matrix)
    write_json(non_auth_out_path, non_authorization)
    write_json(control_out_path, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CS Review P9CR Final Owner Live-Order Gate Review Package",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CS reviews retained P9CR package evidence only. It does not SSH, read Binance, collect fresh proofs, call order-test endpoints, invoke supervisor/timer paths, execute the candidate, replace target plans, mutate executor input, remote sync, cancel orders, or submit orders.",
        "",
        "## Review Result",
        "",
        "```text",
        "p9cr_package_sufficient_for_p9cs_review = "
        f"{str(bool(summary['p9cr_package_sufficient_for_p9cs_review'])).lower()}",
        "p9cr_package_sufficient_for_future_p9ct_scope_definition = "
        f"{str(bool(summary['p9cr_package_sufficient_for_future_p9ct_scope_definition'])).lower()}",
        "p9cr_package_sufficient_for_live_order_submission = false",
        "p9cr_satisfies_final_owner_live_order_gate = false",
        "final_owner_live_order_gate_approval_collected = false",
        "final_gate_evidence_collected_in_p9cr = false",
        "final_gate_actionable_items_satisfied = false",
        f"remaining_evidence_gap_count = {summary['remaining_evidence_gap_count']}",
        f"remaining_approval_gap_count = {summary['remaining_approval_gap_count']}",
        "```",
        "",
        "## Canary Terms Reviewed",
        "",
        "```text",
        f"symbol = {summary['canary_symbol']}",
        f"side = {summary['canary_side']}",
        f"risk_ceiling_usdt = {summary['risk_ceiling_usdt']}",
        f"max_notional_usdt = {summary['max_notional_usdt']}",
        f"max_orders_per_cycle = {summary['max_orders_per_cycle']}",
        f"max_symbols_per_cycle = {summary['max_symbols_per_cycle']}",
        f"order_type = {summary['order_type']}",
        f"time_in_force = {summary['time_in_force']}",
        "market_orders_allowed = false",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## No-Order Boundary",
        "",
        "```text",
        "fresh_remote_proof_collection_performed_in_p9cs = false",
        "fresh_remote_account_read_performed = false",
        "order_test_endpoint_called = false",
        "remote_execution_performed = false",
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
    summary, exit_code = build_phase9cs(parse_args(argv))
    print(
        "p9cs_review_p9cr_ready="
        + str(
            bool(
                summary[
                    "p9cs_review_p9cr_final_owner_live_order_gate_review_package_after_p9co_ready"
                ]
            )
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
