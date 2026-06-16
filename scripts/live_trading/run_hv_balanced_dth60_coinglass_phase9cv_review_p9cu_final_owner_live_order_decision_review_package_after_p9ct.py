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
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cu_prepare_final_owner_live_order_decision_review_package_after_p9ct import (  # noqa: E402
    CONTRACT_VERSION as P9CU_CONTRACT,
    DECISION_CHECKLIST,
    DEFAULT_OUTPUT_PARENT as P9CU_PARENT,
    P9CV_GATE,
    P9CV_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9cv_review_p9cu_final_owner_live_order_decision_review_package_after_p9ct.v1"
)
APPROVE_P9CV_DECISION = (
    "approve_p9cv_review_p9cu_final_owner_live_order_decision_review_package_after_p9ct_only_no_order_no_candidate_no_executor_or_timer_change"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9cv_review_p9cu_final_owner_live_order_decision_review_package_after_p9ct"
)
P9CW_GATE = (
    "P9CW_define_final_owner_live_order_decision_gate_scope_after_p9cv_only_if_separately_requested"
)
P9CW_SCOPE = (
    "define_final_owner_live_order_decision_gate_scope_after_p9cv_no_order_no_candidate_no_executor_or_timer_change"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review retained P9CU final owner live-order decision review package "
            "evidence. P9CV is review-only: it does not SSH, read Binance, "
            "collect fresh proofs, call order-test endpoints, run supervisor or "
            "timer paths, execute the candidate, mutate executor input or target "
            "plans, remote sync, cancel orders, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cu-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CV_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9cv_review_p9cu_final_owner_live_order_decision_review_package_after_p9ct_only_if_separately_requested"
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


def latest_p9cu_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cu_summary).strip():
        return resolve_path(args.phase9cu_summary)
    return latest_match(P9CU_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9cu_summary_ready(summary: dict[str, Any]) -> bool:
    checks = dict(summary.get("checks") or {})
    return (
        summary.get("contract_version") == P9CU_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9cu_final_owner_live_order_decision_review_package_prepared")
        is True
        and summary.get("p9ct_sufficient_for_p9cu_package_preparation") is True
        and summary.get("decision_review_package_prepared_after_p9ct") is True
        and int(summary.get("required_final_decision_evidence_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE)
        and summary.get("final_decision_evidence_collected_in_p9cu") is False
        and summary.get("fresh_proofs_collected_in_p9cu") is False
        and summary.get("fresh_remote_proof_collection_approved_in_p9cu") is False
        and summary.get("final_owner_live_order_gate_approval_collected") is False
        and summary.get("p9cu_satisfies_final_owner_live_order_gate") is False
        and summary.get("eligible_for_future_p9cv_package_review") is True
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and summary.get("eligible_for_future_candidate_executor_path_entry") is False
        and summary.get("fresh_remote_proof_collection_performed_in_p9cu") is False
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
        and summary.get("final_owner_decision_template_only") is True
        and summary.get("final_owner_decision_collected_in_p9cu") is False
        and int(summary.get("decision_checklist_total_count") or 0)
        == len(DECISION_CHECKLIST)
        and int(summary.get("decision_checklist_satisfied_count") or 0) == 2
        and int(summary.get("decision_checklist_unsatisfied_count") or 0) == 8
        and summary.get("allowed_next_gate") == P9CV_GATE
        and summary.get("allowed_next_gate_scope") == P9CV_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def canary_terms_ready(terms: dict[str, Any]) -> bool:
    return (
        terms.get("symbol") == CANARY_SYMBOL
        and terms.get("side") == CANARY_SIDE
        and float(terms.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(terms.get("max_notional_usdt") or 0) == DEFAULT_MAX_NOTIONAL_USDT
        and int(terms.get("max_orders_per_cycle") or 0)
        == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(terms.get("max_symbols_per_cycle") or 0)
        == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and terms.get("order_type") == DEFAULT_ORDER_TYPE
        and terms.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and terms.get("market_orders_allowed") is False
        and terms.get("post_only_required") is True
        and terms.get("maker_only_required") is True
        and terms.get("limit_order_must_not_cross_spread") is True
        and terms.get("candidate_delta_source")
        == "distance_to_high_60_contribution_only"
    )


def candidate_path_terms_ready(
    terms: dict[str, Any],
    summary: dict[str, Any],
) -> bool:
    return (
        terms.get(
            "candidate_may_enter_executor_target_plan_path_only_in_future_final_decision_gate"
        )
        is True
        and terms.get(
            "candidate_execution_may_be_authorized_only_in_future_final_decision_gate"
        )
        is True
        and terms.get(
            "target_plan_replacement_may_be_authorized_only_in_future_final_decision_gate"
        )
        is True
        and terms.get(
            "executor_input_mutation_may_be_authorized_only_in_future_final_decision_gate"
        )
        is True
        and terms.get("must_bind_candidate_target_plan_hash") is True
        and terms.get("baseline_target_plan_sha256")
        == summary.get("baseline_target_plan_sha256")
        and terms.get("candidate_target_plan_sha256")
        == summary.get("candidate_target_plan_sha256")
        and terms.get("must_preserve_same_timestamp_same_risk_inputs") is True
        and terms.get("only_allowed_strategy_delta")
        == "distance_to_high_60_contribution"
        and terms.get("actual_candidate_executor_path_entry_authorized_in_p9ct")
        is False
        and terms.get("actual_target_plan_replacement_authorized_in_p9ct") is False
        and terms.get("actual_executor_input_mutation_authorized_in_p9ct") is False
    )


def evidence_package_ready(evidence: dict[str, Any]) -> bool:
    rows = [dict(row) for row in list(evidence.get("evidence") or [])]
    by_id = {str(row.get("evidence_id")): row for row in rows}
    return (
        evidence.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cu_required_final_decision_evidence_package.v1"
        and evidence.get("package_only") is True
        and evidence.get("final_owner_gate_required_before_any_order_submission")
        is True
        and evidence.get("final_owner_gate_required_before_candidate_executor_path_entry")
        is True
        and evidence.get("p9cu_satisfies_final_owner_live_order_gate") is False
        and evidence.get("fresh_remote_proof_collection_performed_in_p9cu") is False
        and set(by_id) == set(EXPECTED_FINAL_EVIDENCE)
        and all(
            by_id[key].get("required") is True
            and int(by_id[key].get("max_age_seconds") or 0) == max_age
            and by_id[key].get("must_be_retained") is True
            and by_id[key].get("source_status_in_p9ct") == "defined_not_collected"
            and by_id[key].get("status_in_p9cu")
            == "packaged_for_future_decision_not_collected"
            and by_id[key].get("collection_status_in_p9cu") == "not_collected"
            and by_id[key].get("freshness_status_in_p9cu") == "not_evaluated"
            and by_id[key].get("satisfied_for_final_decision") is False
            for key, max_age in EXPECTED_FINAL_EVIDENCE.items()
        )
    )


def decision_template_ready(template: dict[str, Any], summary: dict[str, Any]) -> bool:
    names = set(template.get("must_explicitly_name") or [])
    return (
        template.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cu_final_owner_decision_template.v1"
        and template.get("template_only") is True
        and template.get("future_decision_gate_name")
        == "final_owner_live_order_gate_decision_after_p9cs"
        and template.get("decision_status_in_p9cu") == "not_collected"
        and {
            "candidate_target_plan_sha256",
            "baseline_target_plan_sha256",
            "candidate_executor_target_plan_path_entry",
            "target_plan_replacement",
            "executor_input_mutation",
            "canary_order_terms",
            "risk_ceiling_usdt",
            "max_notional_usdt",
            "kill_switch_and_rollback_terms",
        }.issubset(names)
        and candidate_path_terms_ready(
            dict(template.get("candidate_path_terms") or {}),
            summary,
        )
        and canary_terms_ready(dict(template.get("canary_order_terms") or {}))
        and set(template.get("owner_must_choose_one") or [])
        == {
            "approve_exact_canary_live_order_under_bound_terms",
            "reject_or_defer_live_order_gate",
        }
        and template.get("approval_collected_in_p9cu") is False
        and template.get("live_order_submission_authorized") is False
        and template.get("candidate_execution_authorized") is False
        and template.get("target_plan_replacement_authorized") is False
        and template.get("executor_input_mutation_authorized") is False
    )


def decision_checklist_ready(checklist: dict[str, Any]) -> bool:
    rows = [dict(row) for row in list(checklist.get("approval_items") or [])]
    by_item = {str(row.get("item")): row for row in rows}
    return (
        checklist.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cu_final_decision_checklist.v1"
        and checklist.get("package_only") is True
        and set(by_item) == {item for item, _ in DECISION_CHECKLIST}
        and all(
            by_item[item].get("required_for_final_owner_live_order_gate") is True
            and by_item[item].get("satisfied_in_p9cu") is expected
            for item, expected in DECISION_CHECKLIST
        )
        and checklist.get("p9cu_satisfies_final_owner_live_order_gate") is False
    )


def p9cu_review_package_ready(
    package: dict[str, Any],
    *,
    summary: dict[str, Any],
) -> bool:
    return (
        package.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cu_final_owner_live_order_decision_review_package.v1"
        and package.get("package_only") is True
        and package.get("package_decision")
        == "prepared_for_future_owner_decision_review_only"
        and package.get("future_decision_gate_name")
        == "final_owner_live_order_gate_decision_after_p9cs"
        and package.get("final_owner_live_order_decision_collected") is False
        and evidence_package_ready(
            dict(package.get("required_final_decision_evidence_package") or {})
        )
        and decision_template_ready(
            dict(package.get("final_owner_decision_template") or {}),
            summary,
        )
        and decision_checklist_ready(
            dict(package.get("final_decision_checklist") or {})
        )
        and package.get("baseline_target_plan_sha256")
        == summary.get("baseline_target_plan_sha256")
        and package.get("candidate_target_plan_sha256")
        == summary.get("candidate_target_plan_sha256")
        and package.get("baseline_target_plan_sha256")
        != package.get("candidate_target_plan_sha256")
        and package.get("only_distance_to_high_60_contribution_changed") is True
        and package.get("p9cu_satisfies_final_owner_live_order_gate") is False
        and package.get("live_order_gate_approved") is False
        and package.get("live_order_submission_authorized") is False
        and package.get("candidate_enter_executor_target_plan_path_authorized") is False
        and package.get("candidate_execution_authorized") is False
        and package.get("target_plan_replacement_authorized") is False
        and package.get("executor_input_mutation_authorized") is False
        and int_zero(package, "orders_submitted")
        and int_zero(package, "orders_canceled")
        and int_zero(package, "fill_count")
        and int_zero(package, "trade_count")
    )


def p9cu_owner_record_ready(record: dict[str, Any]) -> bool:
    return (
        record.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cu_owner_decision.v1"
        and record.get("p9cu_package_preparation_approved") is True
        and record.get("future_p9cv_review_request_allowed_if_package_ready") is True
        and record.get("fresh_remote_proof_collection_approved") is False
        and record.get("remote_execution_approved") is False
        and record.get("final_owner_live_order_gate_approved") is False
        and record.get("candidate_executor_path_entry_approved") is False
        and record.get("candidate_execution_approved") is False
        and record.get("target_plan_replacement_approved") is False
        and record.get("executor_input_mutation_approved") is False
        and record.get("live_order_submission_approved") is False
    )


def p9cu_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cu_non_authorization.v1"
        and authorizations.get("prepare_final_owner_live_order_decision_review_package")
        is True
        and authorizations.get("allow_future_p9cv_package_review_request") is True
        and authorizations.get("review_p9cu_package_in_p9cu") is False
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


def p9cu_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cu_control_boundary.v1"
        and control.get("scope")
        == "final_owner_live_order_decision_review_package_preparation_only"
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
    evidence_package = dict(package.get("required_final_decision_evidence_package") or {})
    checklist = dict(package.get("final_decision_checklist") or {})
    evidence_rows = []
    for row in list(evidence_package.get("evidence") or []):
        item = dict(row)
        evidence_rows.append(
            {
                "evidence_id": item.get("evidence_id"),
                "required": item.get("required") is True,
                "source_status_in_p9ct": item.get("source_status_in_p9ct"),
                "status_in_p9cu": item.get("status_in_p9cu"),
                "collection_status_in_p9cu": item.get("collection_status_in_p9cu"),
                "freshness_status_in_p9cu": item.get("freshness_status_in_p9cu"),
                "satisfied_for_final_live_order_gate": item.get(
                    "satisfied_for_final_decision"
                )
                is True,
                "remaining_gap_for_final_live_order_gate": True,
            }
        )
    checklist_rows = []
    for row in list(checklist.get("approval_items") or []):
        item = dict(row)
        satisfied = item.get("satisfied_in_p9cu") is True
        checklist_rows.append(
            {
                "item": item.get("item"),
                "required_for_final_owner_live_order_gate": item.get(
                    "required_for_final_owner_live_order_gate"
                )
                is True,
                "satisfied_in_p9cu": satisfied,
                "remaining_gap_for_final_live_order_gate": not satisfied,
            }
        )
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cv_final_decision_gap_matrix.v1",
        "run_scope": "review_p9cu_package_only",
        "p9cu_package_sufficient_for_p9cv_review": ready,
        "p9cu_package_sufficient_for_future_p9cw_scope_definition": ready,
        "p9cu_package_sufficient_for_live_order_submission": False,
        "p9cu_satisfies_final_owner_live_order_gate": False,
        "evidence_rows": evidence_rows,
        "checklist_rows": checklist_rows,
        "remaining_evidence_gap_count": len(
            [
                row
                for row in evidence_rows
                if row["remaining_gap_for_final_live_order_gate"]
            ]
        ),
        "remaining_checklist_gap_count": len(
            [
                row
                for row in checklist_rows
                if row["remaining_gap_for_final_live_order_gate"]
            ]
        ),
    }


def build_sufficiency_review(
    *,
    checks: dict[str, bool],
    ready: bool,
    p9cu: dict[str, Any],
    package: dict[str, Any],
    gap_matrix: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cv_p9cu_sufficiency_review.v1",
        "review_only": True,
        "p9cu_package_sufficient_for_p9cv_review": ready,
        "p9cu_package_sufficient_for_future_p9cw_scope_definition": ready,
        "p9cu_package_sufficient_for_live_order_submission": False,
        "p9cu_package_sufficient_for_candidate_execution": False,
        "p9cu_package_sufficient_for_candidate_executor_path_entry": False,
        "p9cu_satisfies_final_owner_live_order_gate": False,
        "final_owner_live_order_gate_approval_collected": False,
        "final_decision_evidence_collected_in_p9cu": False,
        "fresh_proofs_collected_in_p9cu": False,
        "final_decision_actionable_items_satisfied": False,
        "eligible_for_future_p9cw_scope_definition": ready,
        "future_gate": P9CW_GATE,
        "future_gate_scope": P9CW_SCOPE,
        "future_gate_must_be_separately_requested": True,
        "canary_symbol": CANARY_SYMBOL,
        "canary_side": CANARY_SIDE,
        "risk_ceiling_usdt": DEFAULT_RISK_CEILING_USDT,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_orders_per_cycle": DEFAULT_MAX_ORDERS_PER_CYCLE,
        "max_symbols_per_cycle": DEFAULT_MAX_SYMBOLS_PER_CYCLE,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "market_orders_allowed": False,
        "baseline_target_plan_sha256": package.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": package.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": package.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
        "source_p9cu_summary_sha256": p9cu.get("source_p9ct_summary_sha256"),
        "remaining_evidence_gap_count": gap_matrix["remaining_evidence_gap_count"],
        "remaining_checklist_gap_count": gap_matrix["remaining_checklist_gap_count"],
        "checks": checks,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def build_phase9cv(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cv" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cu_path = latest_p9cu_summary(args)
    p9cu = load_optional(p9cu_path)
    owner_source_path = source_output_path(p9cu, "owner_decision_record")
    package_path = source_output_path(p9cu, "final_owner_live_order_decision_review_package")
    evidence_package_path = source_output_path(p9cu, "required_final_decision_evidence_package")
    template_path = source_output_path(p9cu, "final_owner_decision_template")
    checklist_path = source_output_path(p9cu, "final_decision_checklist")
    non_auth_path = source_output_path(p9cu, "non_authorization")
    control_path = source_output_path(p9cu, "control_boundary_readback")
    owner_source = load_optional(owner_source_path)
    package = load_optional(package_path)
    evidence_package = load_optional(evidence_package_path)
    template = load_optional(template_path)
    checklist = load_optional(checklist_path)
    p9cu_non_auth = load_optional(non_auth_path)
    p9cu_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CV_DECISION

    checks = {
        "owner_decision_p9cv_review_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cu_summary_exists": bool(p9cu),
        "p9cu_summary_ready_for_p9cv_review": p9cu_summary_ready(p9cu),
        "p9cu_owner_decision_record_ready": p9cu_owner_record_ready(owner_source),
        "p9cu_review_package_ready": p9cu_review_package_ready(
            package,
            summary=p9cu,
        ),
        "p9cu_required_final_decision_evidence_package_file_ready": evidence_package_ready(
            evidence_package
        ),
        "p9cu_required_final_decision_evidence_package_file_matches_package": evidence_package
        == dict(package.get("required_final_decision_evidence_package") or {}),
        "p9cu_final_owner_decision_template_file_ready": decision_template_ready(
            template,
            p9cu,
        ),
        "p9cu_final_owner_decision_template_file_matches_package": template
        == dict(package.get("final_owner_decision_template") or {}),
        "p9cu_final_decision_checklist_file_ready": decision_checklist_ready(checklist),
        "p9cu_final_decision_checklist_file_matches_package": checklist
        == dict(package.get("final_decision_checklist") or {}),
        "p9cu_non_authorization_ready": p9cu_non_authorization_ready(p9cu_non_auth),
        "p9cu_control_boundary_ready": p9cu_control_ready(p9cu_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    gap_matrix = build_gap_matrix(package=package, ready=ready)
    sufficiency = build_sufficiency_review(
        checks=checks,
        ready=ready,
        p9cu=p9cu,
        package=package,
        gap_matrix=gap_matrix,
    )
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cv_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "review_p9cu_final_owner_live_order_decision_review_package_after_p9ct_only_no_order_no_candidate_no_executor_or_timer_change",
        "recorded_at_utc": iso_z(now),
        "p9cv_review_p9cu_package_approved": owner_decision_ok,
        "future_p9cw_scope_definition_request_allowed_if_review_ready": ready,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9cv_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "review_p9cu_final_owner_live_order_decision_review_package": ready,
            "allow_future_p9cw_scope_definition_request": ready,
            "define_p9cw_scope_in_p9cv": False,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9cv_control_boundary.v1",
        "run_id": run_id,
        "scope": "p9cu_retained_final_owner_live_order_decision_review_package_review_only",
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
    review_path = proof_root / "p9cu_sufficiency_review.json"
    gap_path = proof_root / "final_decision_gap_matrix.json"
    non_auth_out_path = proof_root / "non_authorization.json"
    control_out_path = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9cv_review_p9cu.md"
    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "p9cu_sufficiency_review": str(review_path),
        "final_decision_gap_matrix": str(gap_path),
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
        "p9cv_review_p9cu_final_owner_live_order_decision_review_package_after_p9ct_ready": ready,
        "p9cu_package_sufficient_for_p9cv_review": ready,
        "p9cu_package_sufficient_for_future_p9cw_scope_definition": ready,
        "p9cu_package_sufficient_for_live_order_submission": False,
        "p9cu_package_sufficient_for_candidate_execution": False,
        "p9cu_package_sufficient_for_candidate_executor_path_entry": False,
        "p9cu_satisfies_final_owner_live_order_gate": False,
        "final_owner_live_order_gate_approval_collected": False,
        "final_owner_decision_collected_in_p9cu": False,
        "final_decision_evidence_collected_in_p9cu": False,
        "fresh_proofs_collected_in_p9cu": False,
        "fresh_remote_proof_collection_approved_in_p9cv": False,
        "final_decision_actionable_items_satisfied": False,
        "eligible_for_future_p9cw_scope_definition": ready,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "eligible_for_future_candidate_executor_path_entry": False,
        "fresh_remote_proof_collection_performed_in_p9cv": False,
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
        "baseline_target_plan_sha256": package.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": package.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": package.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
        "required_final_decision_evidence_count": len(
            list(
                dict(
                    package.get("required_final_decision_evidence_package") or {}
                ).get("evidence")
                or []
            )
        ),
        "remaining_evidence_gap_count": gap_matrix["remaining_evidence_gap_count"],
        "decision_checklist_total_count": len(DECISION_CHECKLIST),
        "decision_checklist_satisfied_count": len(
            [item for item, satisfied in DECISION_CHECKLIST if satisfied]
        ),
        "decision_checklist_unsatisfied_count": gap_matrix[
            "remaining_checklist_gap_count"
        ],
        "source_p9cu_summary_sha256": evidence_file(p9cu_path).get("sha256", ""),
        "source_p9cu_owner_decision_record_sha256": evidence_file(
            owner_source_path
        ).get("sha256", ""),
        "source_p9cu_review_package_sha256": evidence_file(package_path).get(
            "sha256", ""
        ),
        "source_p9cu_required_final_decision_evidence_package_sha256": evidence_file(
            evidence_package_path
        ).get("sha256", ""),
        "source_p9cu_final_owner_decision_template_sha256": evidence_file(
            template_path
        ).get("sha256", ""),
        "source_p9cu_final_decision_checklist_sha256": evidence_file(
            checklist_path
        ).get("sha256", ""),
        "source_p9cu_non_authorization_sha256": evidence_file(non_auth_path).get(
            "sha256", ""
        ),
        "source_p9cu_control_boundary_sha256": evidence_file(control_path).get(
            "sha256", ""
        ),
        "allowed_next_gate": P9CW_GATE,
        "allowed_next_gate_scope": P9CW_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9cu_summary": evidence_file(p9cu_path),
            "phase9cu_owner_decision_record": evidence_file(owner_source_path),
            "phase9cu_final_owner_live_order_decision_review_package": evidence_file(
                package_path
            ),
            "phase9cu_required_final_decision_evidence_package": evidence_file(
                evidence_package_path
            ),
            "phase9cu_final_owner_decision_template": evidence_file(template_path),
            "phase9cu_final_decision_checklist": evidence_file(checklist_path),
            "phase9cu_non_authorization": evidence_file(non_auth_path),
            "phase9cu_control_boundary": evidence_file(control_path),
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
        "# hv_balanced DTH60/CoinGlass P9CV Review P9CU Final Owner Live-Order Decision Review Package",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CV reviews retained P9CU package evidence only. It does not SSH, read Binance, collect fresh proofs, call order-test endpoints, invoke supervisor/timer paths, execute the candidate, replace target plans, mutate executor input, remote sync, cancel orders, or submit orders.",
        "",
        "## Review Result",
        "",
        "```text",
        "p9cu_package_sufficient_for_p9cv_review = "
        f"{str(bool(summary['p9cu_package_sufficient_for_p9cv_review'])).lower()}",
        "p9cu_package_sufficient_for_future_p9cw_scope_definition = "
        f"{str(bool(summary['p9cu_package_sufficient_for_future_p9cw_scope_definition'])).lower()}",
        "p9cu_package_sufficient_for_live_order_submission = false",
        "p9cu_satisfies_final_owner_live_order_gate = false",
        "final_owner_live_order_gate_approval_collected = false",
        "final_decision_evidence_collected_in_p9cu = false",
        "fresh_proofs_collected_in_p9cu = false",
        "final_decision_actionable_items_satisfied = false",
        f"remaining_evidence_gap_count = {summary['remaining_evidence_gap_count']}",
        f"decision_checklist_unsatisfied_count = {summary['decision_checklist_unsatisfied_count']}",
        "```",
        "",
        "## Candidate And Canary Terms Reviewed",
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
        "fresh_remote_proof_collection_performed_in_p9cv = false",
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
    summary, exit_code = build_phase9cv(parse_args(argv))
    print(
        "p9cv_review_p9cu_ready="
        + str(
            bool(
                summary[
                    "p9cv_review_p9cu_final_owner_live_order_decision_review_package_after_p9ct_ready"
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
