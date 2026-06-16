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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cl_post_account_blocker_live_order_readiness_review_package import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    CONTRACT_VERSION as P9CL_CONTRACT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_OUTPUT_PARENT as P9CL_PARENT,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    EXPECTED_PROOFS,
    P9CM_GATE,
    P9CM_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package.v1"
)
APPROVE_P9CM_DECISION = (
    "approve_p9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package_only_no_remote_no_order_no_execution"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package"
)
P9CN_GATE = (
    "P9CN_allow_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_only_if_separately_requested"
)
P9CN_SCOPE = (
    "allow_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_discussion_only_no_remote_no_order_no_execution"
)
EXPECTED_APPROVAL_ITEMS = {
    "account_blocker_cleared_by_p9cj": True,
    "all_required_fresh_proofs_present_and_unexpired": False,
    "fresh_v2_account_canTrade_true": False,
    "same_risk_candidate_target_plan_hash_bound": False,
    "distance_to_high_60_only_delta": False,
    "no_order_replacement_dry_run_passed": False,
    "post_only_limit_price_does_not_cross_spread": False,
    "kill_switch_and_rollback_readback_available": False,
    "final_owner_live_order_gate_approval": False,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review the retained P9CL post-account-blocker live-order readiness "
            "review package. P9CM is review-only: it does not SSH, read Binance, "
            "collect fresh proofs, run supervisor or timer paths, execute the "
            "candidate, mutate executor input or target plans, remote sync, cancel "
            "orders, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cl-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CM_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package_only_if_separately_requested"
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


def latest_p9cl_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cl_summary).strip():
        return resolve_path(args.phase9cl_summary)
    return latest_match(P9CL_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def canary_terms_ready(canary: dict[str, Any]) -> bool:
    return (
        canary.get("symbol") == CANARY_SYMBOL
        and canary.get("side") == CANARY_SIDE
        and float(canary.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(canary.get("max_notional_usdt") or 0) == DEFAULT_MAX_NOTIONAL_USDT
        and int(canary.get("max_orders_per_cycle") or 0) == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(canary.get("max_symbols_per_cycle") or 0)
        == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and canary.get("order_type") == DEFAULT_ORDER_TYPE
        and canary.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and canary.get("market_orders_allowed") is False
        and canary.get("post_only_required") is True
        and canary.get("maker_only_required") is True
        and canary.get("candidate_delta_source") == "distance_to_high_60_contribution_only"
        and canary.get("would_submit_order") is False
    )


def p9cl_summary_ready(summary: dict[str, Any]) -> bool:
    checks = dict(summary.get("checks") or {})
    return (
        summary.get("contract_version") == P9CL_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9cl_post_account_blocker_live_order_readiness_review_package_prepared")
        is True
        and summary.get("p9ck_sufficient_for_p9cl_review_package") is True
        and summary.get("account_blocker_cleared_before_p9cl") is True
        and summary.get("review_package_prepared_after_account_blocker_clearance") is True
        and int(summary.get("required_fresh_proof_count") or 0) == len(EXPECTED_PROOFS)
        and summary.get("fresh_proofs_collected_in_p9cl") is False
        and summary.get("fresh_proofs_satisfied_by_p9cl") is False
        and summary.get("fresh_remote_proof_collection_approved_in_p9cl") is False
        and summary.get("eligible_for_future_p9cm_package_review") is True
        and summary.get("eligible_for_future_fresh_remote_proof_collection") is False
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and summary.get("eligible_for_future_candidate_executor_path_entry") is False
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
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and summary.get("allowed_next_gate") == P9CM_GATE
        and summary.get("allowed_next_gate_scope") == P9CM_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("source_p9ck_account_blocker_cleared") is True
        and summary.get("source_p9ck_fresh_proofs_satisfied") is False
        and summary.get("source_p9ck_eligible_for_future_fresh_remote_proof_collection")
        is False
        and canary_terms_ready(
            {
                "symbol": summary.get("canary_symbol"),
                "side": summary.get("canary_side"),
                "risk_ceiling_usdt": summary.get("risk_ceiling_usdt"),
                "max_notional_usdt": summary.get("max_notional_usdt"),
                "max_orders_per_cycle": summary.get("max_orders_per_cycle"),
                "max_symbols_per_cycle": summary.get("max_symbols_per_cycle"),
                "order_type": summary.get("order_type"),
                "time_in_force": summary.get("time_in_force"),
                "market_orders_allowed": summary.get("market_orders_allowed"),
                "post_only_required": True,
                "maker_only_required": True,
                "candidate_delta_source": "distance_to_high_60_contribution_only",
                "would_submit_order": False,
            }
        )
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def p9cl_fresh_plan_ready(plan: dict[str, Any]) -> bool:
    proof_rows = list(plan.get("proofs") or [])
    proof_by_id = {str(row.get("proof_id")): dict(row) for row in proof_rows}
    return (
        plan.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cl_fresh_proof_collection_plan.v1"
        and plan.get("package_only") is True
        and plan.get("fresh_proofs_collected_in_p9cl") is False
        and plan.get("remote_account_read_performed") is False
        and plan.get("order_book_read_performed") is False
        and plan.get("exchange_filter_read_performed") is False
        and plan.get("future_collection_requires_separate_owner_gate") is True
        and set(proof_by_id) == set(EXPECTED_PROOFS)
        and all(
            proof_by_id[key].get("required") is True
            and int(proof_by_id[key].get("max_age_seconds") or 0) == max_age
            and proof_by_id[key].get("required_before")
            in {"future_live_order_gate_approval", "any_order_submission"}
            and bool(proof_by_id[key].get("acceptance"))
            and proof_by_id[key].get("collection_status_in_p9cl") == "not_collected"
            and proof_by_id[key].get("future_collection_requires_separate_owner_gate")
            is True
            for key, max_age in EXPECTED_PROOFS.items()
        )
    )


def p9cl_approval_checklist_ready(checklist: dict[str, Any]) -> bool:
    rows = {
        str(row.get("item")): dict(row)
        for row in list(checklist.get("approval_items") or [])
    }
    return (
        checklist.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cl_approval_checklist.v1"
        and checklist.get("package_only") is True
        and set(rows) == set(EXPECTED_APPROVAL_ITEMS)
        and all(
            rows[item].get("required_for_live_order_gate") is True
            and rows[item].get("satisfied_in_p9cl") is expected
            for item, expected in EXPECTED_APPROVAL_ITEMS.items()
        )
        and len(checklist.get("rollback_conditions") or []) >= 8
    )


def p9cl_package_ready(package: dict[str, Any]) -> bool:
    return (
        package.get("contract_version") == "hv_balanced_dth60_coinglass_phase9cl_review_package.v1"
        and package.get("package_only") is True
        and package.get("package_decision") == "prepared_for_future_review_only"
        and package.get("account_blocker_status") == "cleared_by_p9cj_retained_review"
        and package.get("future_gate_name") == "post_account_blocker_live_order_readiness_review"
        and package.get("required_fresh_proof_count") == len(EXPECTED_PROOFS)
        and package.get("fresh_proofs_collected_in_p9cl") is False
        and package.get("fresh_proofs_satisfied_by_p9cl") is False
        and package.get("fresh_remote_proof_collection_approved_in_p9cl") is False
        and package.get("live_order_gate_approved") is False
        and package.get("live_order_submission_authorized") is False
        and package.get("candidate_execution_authorized") is False
        and package.get("target_plan_replacement_authorized") is False
        and package.get("executor_input_mutation_authorized") is False
        and int_zero(package, "orders_submitted")
        and int_zero(package, "orders_canceled")
        and int_zero(package, "fill_count")
        and int_zero(package, "trade_count")
        and package.get("source_p9ck_account_blocker_cleared") is True
        and "whether to request fresh read-only remote proof collection in a later separate gate"
        in list(package.get("future_gate_may_discuss") or [])
        and "new PIT-safe v2/v3 account proof after P9CJ"
        in list(package.get("future_gate_may_not_skip") or [])
        and "separate final owner live-order gate"
        in list(package.get("future_gate_may_not_skip") or [])
        and canary_terms_ready(dict(package.get("canary_order_terms") or {}))
        and p9cl_fresh_plan_ready(dict(package.get("fresh_proof_collection_plan") or {}))
        and p9cl_approval_checklist_ready(dict(package.get("approval_checklist") or {}))
    )


def p9cl_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9cl_non_authorization.v1"
        and authorizations.get("prepare_post_account_blocker_live_order_readiness_review_package")
        is True
        and authorizations.get("review_p9cl_package") is True
        and authorizations.get("fresh_remote_proof_collection") is False
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


def p9cl_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version") == "hv_balanced_dth60_coinglass_phase9cl_control_boundary.v1"
        and control.get("scope")
        == "post_account_blocker_live_order_readiness_review_package_preparation_only"
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


def build_sufficiency_review(
    *,
    run_id: str,
    p9cl_summary_path: Path,
    p9cl_summary: dict[str, Any],
    package: dict[str, Any],
    checks: dict[str, bool],
) -> dict[str, Any]:
    ready = all(checks.values())
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cm_p9cl_package_sufficiency_review.v1",
        "run_id": run_id,
        "review_only": True,
        "source_p9cl_summary": evidence_file(p9cl_summary_path),
        "source_p9cl_package_decision": package.get("package_decision"),
        "p9cl_package_sufficient_for_future_p9cn_owner_gate": ready,
        "p9cl_package_sufficient_for_fresh_remote_proof_collection": False,
        "p9cl_package_sufficient_for_live_order_submission": False,
        "fresh_proof_collection_plan_present": p9cl_fresh_plan_ready(
            dict(package.get("fresh_proof_collection_plan") or {})
        ),
        "required_fresh_proof_count": int(p9cl_summary.get("required_fresh_proof_count") or 0),
        "fresh_proofs_collected_in_p9cm": False,
        "fresh_remote_proof_collection_approved_in_p9cm": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "checks": checks,
    }


def build_future_owner_gate_readiness(package: dict[str, Any]) -> dict[str, Any]:
    fresh_plan = dict(package.get("fresh_proof_collection_plan") or {})
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cm_future_p9cn_owner_gate_readiness.v1",
        "review_only": True,
        "future_gate": P9CN_GATE,
        "future_gate_scope": P9CN_SCOPE,
        "future_gate_must_be_separately_requested": True,
        "future_gate_may_only_discuss": [
            "whether to allow read-only fresh remote proof collection",
            "whether the P9CL/P9CM package is sufficient for that owner-gate discussion",
            "which retained P9CL proof rows must be collected fresh in a later execution gate",
        ],
        "future_gate_may_not_approve": [
            "fresh remote proof collection execution",
            "live order gate approval",
            "live order submission",
            "candidate execution",
            "target-plan replacement",
            "executor-input mutation",
            "timer or supervisor invocation",
        ],
        "required_proofs_to_discuss_later": list(fresh_plan.get("proofs") or []),
        "fresh_proofs_collected_in_p9cm": False,
        "fresh_remote_proof_collection_approved_in_p9cm": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
    }


def build_phase9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cm" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cl_summary_path = latest_p9cl_summary(args)
    p9cl = load_optional(p9cl_summary_path)
    package_path = source_output_path(
        p9cl,
        "post_account_blocker_live_order_readiness_review_package",
    )
    canary_path = source_output_path(p9cl, "canary_order_terms")
    fresh_plan_path = source_output_path(p9cl, "fresh_proof_collection_plan")
    approval_path = source_output_path(p9cl, "approval_checklist")
    matrix_path = source_output_path(p9cl, "non_authorization")
    control_path = source_output_path(p9cl, "control_boundary_readback")
    package = load_optional(package_path)
    canary = load_optional(canary_path)
    fresh_plan = load_optional(fresh_plan_path)
    approval = load_optional(approval_path)
    p9cl_matrix = load_optional(matrix_path)
    p9cl_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CM_DECISION
    embedded_package = dict(package)
    if embedded_package:
        embedded_package["canary_order_terms"] = dict(
            embedded_package.get("canary_order_terms") or canary
        )
        embedded_package["fresh_proof_collection_plan"] = dict(
            embedded_package.get("fresh_proof_collection_plan") or fresh_plan
        )
        embedded_package["approval_checklist"] = dict(
            embedded_package.get("approval_checklist") or approval
        )
    checks = {
        "owner_decision_p9cm_review_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cl_summary_exists": bool(p9cl),
        "p9cl_summary_ready_for_p9cm_review": p9cl_summary_ready(p9cl),
        "p9cl_review_package_ready": p9cl_package_ready(embedded_package),
        "p9cl_canary_terms_ready": canary_terms_ready(canary),
        "p9cl_fresh_proof_plan_ready": p9cl_fresh_plan_ready(fresh_plan),
        "p9cl_approval_checklist_ready": p9cl_approval_checklist_ready(approval),
        "p9cl_non_authorization_ready": p9cl_non_authorization_ready(p9cl_matrix),
        "p9cl_control_boundary_ready": p9cl_control_ready(p9cl_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    sufficiency_review = build_sufficiency_review(
        run_id=run_id,
        p9cl_summary_path=p9cl_summary_path,
        p9cl_summary=p9cl,
        package=embedded_package,
        checks=checks,
    )
    future_gate_readiness = build_future_owner_gate_readiness(embedded_package)
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cm_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "review_p9cl_post_account_blocker_live_order_readiness_review_package_only_no_remote_no_order_no_execution",
        "recorded_at_utc": iso_z(now),
        "p9cl_package_review_approved": owner_decision_ok,
        "fresh_remote_proof_collection_approved": False,
        "remote_execution_approved": False,
        "live_order_gate_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cm_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "review_p9cl_package_sufficiency": ready,
            "allow_future_p9cn_owner_gate_request": ready,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9cm_control_boundary.v1",
        "run_id": run_id,
        "scope": "p9cl_package_sufficiency_review_only",
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
    review_path = proof_root / "p9cl_package_sufficiency_review.json"
    future_gate_path = proof_root / "future_p9cn_owner_gate_readiness.json"
    non_auth_path = proof_root / "non_authorization.json"
    control_path_out = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9cm_review_p9cl_post_account_blocker_package.md"
    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "p9cl_package_sufficiency_review": str(review_path),
        "future_p9cn_owner_gate_readiness": str(future_gate_path),
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
        "p9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package_ready": ready,
        "p9cl_package_sufficient_for_p9cm_review": p9cl_summary_ready(p9cl),
        "p9cl_package_sufficient_for_future_p9cn_owner_gate": ready,
        "p9cl_package_sufficient_for_fresh_remote_proof_collection": False,
        "p9cl_package_sufficient_for_live_order_submission": False,
        "account_blocker_cleared_before_p9cm": p9cl.get(
            "account_blocker_cleared_before_p9cl"
        )
        is True,
        "required_fresh_proof_count": int(p9cl.get("required_fresh_proof_count") or 0),
        "fresh_proofs_collected_in_p9cm": False,
        "fresh_proofs_satisfied_by_p9cm": False,
        "fresh_remote_proof_collection_approved_in_p9cm": False,
        "eligible_for_future_p9cn_owner_gate": ready,
        "eligible_for_future_fresh_remote_proof_collection": False,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "eligible_for_future_candidate_executor_path_entry": False,
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
        "allowed_next_gate": P9CN_GATE,
        "allowed_next_gate_scope": P9CN_SCOPE,
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
        "source_p9cl_summary_sha256": evidence_file(p9cl_summary_path).get("sha256", ""),
        "source_p9cl_package_sha256": evidence_file(package_path).get("sha256", ""),
        "source_p9cl_fresh_plan_sha256": evidence_file(fresh_plan_path).get("sha256", ""),
        "source_p9cl_fresh_proofs_collected": p9cl.get("fresh_proofs_collected_in_p9cl"),
        "source_p9cl_fresh_remote_proof_collection_approved": p9cl.get(
            "fresh_remote_proof_collection_approved_in_p9cl"
        ),
        "source_evidence": {
            "phase9cl_summary": evidence_file(p9cl_summary_path),
            "phase9cl_review_package": evidence_file(package_path),
            "phase9cl_canary_order_terms": evidence_file(canary_path),
            "phase9cl_fresh_proof_collection_plan": evidence_file(fresh_plan_path),
            "phase9cl_approval_checklist": evidence_file(approval_path),
            "phase9cl_non_authorization": evidence_file(matrix_path),
            "phase9cl_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(review_path, sufficiency_review)
    write_json(future_gate_path, future_gate_readiness)
    write_json(non_auth_path, non_authorization)
    write_json(control_path_out, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def build_phase9cm(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    return build_phase9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package(
        args,
        now_fn=now_fn,
    )


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CM Review P9CL Post-Account-Blocker Package",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CM reviews retained P9CL package sufficiency only. It does not collect fresh proofs, approve fresh remote proof collection, approve live orders, execute the candidate, replace target plans, mutate executor input, invoke supervisor/timer/remote paths, or submit orders.",
        "",
        "## Review Boundary",
        "",
        "```text",
        "p9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package_ready = "
        f"{str(bool(summary['p9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package_ready'])).lower()}",
        "p9cl_package_sufficient_for_future_p9cn_owner_gate = "
        f"{str(bool(summary['p9cl_package_sufficient_for_future_p9cn_owner_gate'])).lower()}",
        "fresh_proofs_collected_in_p9cm = false",
        "fresh_remote_proof_collection_approved_in_p9cm = false",
        "eligible_for_future_fresh_remote_proof_collection = false",
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
        "## Allowed Next Gate",
        "",
        "```text",
        str(summary["allowed_next_gate"]),
        str(summary["allowed_next_gate_scope"]),
        "allowed_next_gate_must_be_separately_requested = true",
        "```",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9cm(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
