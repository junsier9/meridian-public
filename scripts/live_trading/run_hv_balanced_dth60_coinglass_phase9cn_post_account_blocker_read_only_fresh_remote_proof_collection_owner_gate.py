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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    CONTRACT_VERSION as P9CM_CONTRACT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_OUTPUT_PARENT as P9CM_PARENT,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    EXPECTED_PROOFS,
    P9CN_GATE,
    P9CN_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9cn_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate.v1"
)
APPROVE_P9CN_DECISION = (
    "approve_p9cn_allow_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_only_no_collection_no_order_no_execution"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9cn_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate"
)
P9CO_GATE = (
    "P9CO_execute_post_account_blocker_read_only_fresh_remote_proof_collection_only_if_separately_requested"
)
P9CO_SCOPE = (
    "execute_post_account_blocker_read_only_fresh_remote_proof_collection_no_order_no_candidate_no_timer_no_supervisor"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the P9CN owner gate for allowing a later, separately requested "
            "post-account-blocker read-only fresh remote proof collection execution "
            "gate. P9CN is owner-gate-only: it does not SSH, read Binance, collect "
            "fresh proofs, call order-test endpoints, run supervisor/timer paths, "
            "mutate executor input or target plans, execute the candidate, cancel "
            "orders, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cm-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CN_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9cn_allow_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_only_if_separately_requested"
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


def latest_p9cm_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cm_summary).strip():
        return resolve_path(args.phase9cm_summary)
    return latest_match(P9CM_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9cm_summary_ready(summary: dict[str, Any]) -> bool:
    checks = dict(summary.get("checks") or {})
    return (
        summary.get("contract_version") == P9CM_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get(
            "p9cm_review_p9cl_post_account_blocker_live_order_readiness_review_package_ready"
        )
        is True
        and summary.get("p9cl_package_sufficient_for_p9cm_review") is True
        and summary.get("p9cl_package_sufficient_for_future_p9cn_owner_gate") is True
        and summary.get("p9cl_package_sufficient_for_fresh_remote_proof_collection")
        is False
        and summary.get("p9cl_package_sufficient_for_live_order_submission") is False
        and summary.get("account_blocker_cleared_before_p9cm") is True
        and int(summary.get("required_fresh_proof_count") or 0) == len(EXPECTED_PROOFS)
        and summary.get("fresh_proofs_collected_in_p9cm") is False
        and summary.get("fresh_proofs_satisfied_by_p9cm") is False
        and summary.get("fresh_remote_proof_collection_approved_in_p9cm") is False
        and summary.get("eligible_for_future_p9cn_owner_gate") is True
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
        and summary.get("allowed_next_gate") == P9CN_GATE
        and summary.get("allowed_next_gate_scope") == P9CN_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("canary_symbol") == CANARY_SYMBOL
        and summary.get("canary_side") == CANARY_SIDE
        and float(summary.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(summary.get("max_notional_usdt") or 0) == DEFAULT_MAX_NOTIONAL_USDT
        and int(summary.get("max_orders_per_cycle") or 0) == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(summary.get("max_symbols_per_cycle") or 0) == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and summary.get("order_type") == DEFAULT_ORDER_TYPE
        and summary.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and summary.get("market_orders_allowed") is False
        and summary.get("source_p9cl_fresh_proofs_collected") is False
        and summary.get("source_p9cl_fresh_remote_proof_collection_approved") is False
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def p9cm_sufficiency_review_ready(review: dict[str, Any]) -> bool:
    checks = dict(review.get("checks") or {})
    return (
        review.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cm_p9cl_package_sufficiency_review.v1"
        and review.get("review_only") is True
        and review.get("p9cl_package_sufficient_for_future_p9cn_owner_gate") is True
        and review.get("p9cl_package_sufficient_for_fresh_remote_proof_collection")
        is False
        and review.get("p9cl_package_sufficient_for_live_order_submission") is False
        and review.get("fresh_proof_collection_plan_present") is True
        and int(review.get("required_fresh_proof_count") or 0) == len(EXPECTED_PROOFS)
        and review.get("fresh_proofs_collected_in_p9cm") is False
        and review.get("fresh_remote_proof_collection_approved_in_p9cm") is False
        and review.get("live_order_gate_approved") is False
        and review.get("live_order_submission_authorized") is False
        and review.get("candidate_execution_authorized") is False
        and review.get("target_plan_replacement_authorized") is False
        and review.get("executor_input_mutation_authorized") is False
        and int_zero(review, "orders_submitted")
        and int_zero(review, "orders_canceled")
        and int_zero(review, "fill_count")
        and int_zero(review, "trade_count")
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def proof_rows_ready(rows: list[Any]) -> bool:
    proof_by_id = {str(row.get("proof_id")): dict(row) for row in rows if isinstance(row, dict)}
    return (
        set(proof_by_id) == set(EXPECTED_PROOFS)
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


def future_p9cn_readiness_ready(readiness: dict[str, Any]) -> bool:
    may_discuss = set(str(item) for item in list(readiness.get("future_gate_may_only_discuss") or []))
    may_not = set(str(item) for item in list(readiness.get("future_gate_may_not_approve") or []))
    return (
        readiness.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cm_future_p9cn_owner_gate_readiness.v1"
        and readiness.get("review_only") is True
        and readiness.get("future_gate") == P9CN_GATE
        and readiness.get("future_gate_scope") == P9CN_SCOPE
        and readiness.get("future_gate_must_be_separately_requested") is True
        and "whether to allow read-only fresh remote proof collection" in may_discuss
        and "fresh remote proof collection execution" in may_not
        and "live order submission" in may_not
        and "candidate execution" in may_not
        and "target-plan replacement" in may_not
        and "executor-input mutation" in may_not
        and "timer or supervisor invocation" in may_not
        and proof_rows_ready(list(readiness.get("required_proofs_to_discuss_later") or []))
        and readiness.get("fresh_proofs_collected_in_p9cm") is False
        and readiness.get("fresh_remote_proof_collection_approved_in_p9cm") is False
        and readiness.get("live_order_gate_approved") is False
        and readiness.get("live_order_submission_authorized") is False
    )


def p9cm_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version") == "hv_balanced_dth60_coinglass_phase9cm_non_authorization.v1"
        and authorizations.get("review_p9cl_package_sufficiency") is True
        and authorizations.get("allow_future_p9cn_owner_gate_request") is True
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


def p9cm_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version") == "hv_balanced_dth60_coinglass_phase9cm_control_boundary.v1"
        and control.get("scope") == "p9cl_package_sufficiency_review_only"
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


def build_owner_gate(
    *,
    run_id: str,
    p9cm_summary_path: Path,
    p9cm_summary: dict[str, Any],
    readiness: dict[str, Any],
    ready: bool,
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cn_owner_gate.v1",
        "run_id": run_id,
        "owner_gate_only": True,
        "source_p9cm_summary": evidence_file(p9cm_summary_path),
        "owner_gate_decision": "allow_future_p9co_execution_gate_request_only",
        "p9cm_sufficient_for_p9cn_owner_gate": ready,
        "post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_approved_in_p9cn": ready,
        "eligible_for_future_p9co_execution_gate_request": ready,
        "eligible_for_future_fresh_remote_proof_collection_without_separate_request": False,
        "fresh_remote_proof_collection_execution_approved_in_p9cn": False,
        "fresh_remote_proof_collection_performed_in_p9cn": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "future_gate": P9CO_GATE,
        "future_gate_scope": P9CO_SCOPE,
        "future_gate_must_be_separately_requested": True,
        "required_proofs_to_collect_later": list(
            readiness.get("required_proofs_to_discuss_later") or []
        ),
        "canary_symbol": p9cm_summary.get("canary_symbol"),
        "canary_side": p9cm_summary.get("canary_side"),
        "risk_ceiling_usdt": p9cm_summary.get("risk_ceiling_usdt"),
        "max_notional_usdt": p9cm_summary.get("max_notional_usdt"),
        "max_orders_per_cycle": p9cm_summary.get("max_orders_per_cycle"),
        "max_symbols_per_cycle": p9cm_summary.get("max_symbols_per_cycle"),
        "order_type": p9cm_summary.get("order_type"),
        "time_in_force": p9cm_summary.get("time_in_force"),
        "market_orders_allowed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def build_future_execution_scope(readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cn_future_p9co_execution_gate_scope.v1",
        "owner_gate_only": True,
        "future_gate": P9CO_GATE,
        "future_gate_scope": P9CO_SCOPE,
        "future_gate_must_be_separately_requested": True,
        "future_gate_may_execute_only": [
            "read-only fresh remote proof collection",
            "PIT-safe v2/v3 account proof",
            "fresh position, open-order, balance, order, trade, book, and filter reads",
            "no-order same-risk paired target-plan and distance_to_high_60 contribution checks",
            "kill-switch and rollback readbacks",
        ],
        "future_gate_may_not_execute": [
            "live order submission",
            "order-test endpoint call",
            "candidate execution",
            "target-plan replacement",
            "executor-input mutation",
            "timer path load",
            "supervisor invocation",
            "remote sync",
            "live config, operator state, or timer mutation",
        ],
        "required_proofs": list(readiness.get("required_proofs_to_discuss_later") or []),
        "fresh_remote_proof_collection_performed_in_p9cn": False,
        "fresh_remote_proof_collection_execution_approved_in_p9cn": False,
        "live_order_submission_authorized": False,
    }


def build_phase9cn_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cn" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cm_summary_path = latest_p9cm_summary(args)
    p9cm = load_optional(p9cm_summary_path)
    review_path_in = source_output_path(p9cm, "p9cl_package_sufficiency_review")
    readiness_path_in = source_output_path(p9cm, "future_p9cn_owner_gate_readiness")
    matrix_path = source_output_path(p9cm, "non_authorization")
    control_path = source_output_path(p9cm, "control_boundary_readback")
    review = load_optional(review_path_in)
    readiness = load_optional(readiness_path_in)
    p9cm_matrix = load_optional(matrix_path)
    p9cm_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CN_DECISION
    checks = {
        "owner_decision_p9cn_owner_gate_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cm_summary_exists": bool(p9cm),
        "p9cm_summary_ready_for_p9cn_owner_gate": p9cm_summary_ready(p9cm),
        "p9cm_sufficiency_review_ready": p9cm_sufficiency_review_ready(review),
        "p9cm_future_p9cn_readiness_ready": future_p9cn_readiness_ready(readiness),
        "p9cm_non_authorization_ready": p9cm_non_authorization_ready(p9cm_matrix),
        "p9cm_control_boundary_ready": p9cm_control_ready(p9cm_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    owner_gate = build_owner_gate(
        run_id=run_id,
        p9cm_summary_path=p9cm_summary_path,
        p9cm_summary=p9cm,
        readiness=readiness,
        ready=ready,
    )
    future_scope = build_future_execution_scope(readiness)
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cn_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "allow_future_post_account_blocker_read_only_fresh_remote_proof_collection_execution_gate_request_only_no_collection_no_order_no_execution",
        "recorded_at_utc": iso_z(now),
        "future_p9co_execution_gate_request_approved": owner_decision_ok,
        "fresh_remote_proof_collection_execution_approved": False,
        "remote_execution_approved": False,
        "live_order_gate_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cn_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "allow_future_p9co_execution_gate_request": ready,
            "fresh_remote_proof_collection_execution": False,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9cn_control_boundary.v1",
        "run_id": run_id,
        "scope": "post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_only",
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
    owner_gate_path = proof_root / "read_only_fresh_remote_proof_collection_owner_gate.json"
    future_scope_path = proof_root / "future_p9co_execution_gate_scope.json"
    non_auth_path = proof_root / "non_authorization.json"
    control_path_out = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9cn_read_only_fresh_remote_proof_collection_owner_gate.md"
    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "read_only_fresh_remote_proof_collection_owner_gate": str(owner_gate_path),
        "future_p9co_execution_gate_scope": str(future_scope_path),
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
        "p9cn_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_ready": ready,
        "p9cm_sufficient_for_p9cn_owner_gate": p9cm_summary_ready(p9cm),
        "post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_approved_in_p9cn": ready,
        "eligible_for_future_p9co_execution_gate_request": ready,
        "eligible_for_future_fresh_remote_proof_collection_without_separate_request": False,
        "fresh_remote_proof_collection_execution_approved_in_p9cn": False,
        "fresh_remote_proof_collection_performed_in_p9cn": False,
        "fresh_proofs_collected_in_p9cn": False,
        "fresh_proofs_satisfied_by_p9cn": False,
        "eligible_for_future_fresh_remote_proof_collection": False,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "eligible_for_future_candidate_executor_path_entry": False,
        "required_fresh_proof_count": len(
            list(readiness.get("required_proofs_to_discuss_later") or [])
        ),
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
        "allowed_next_gate": P9CO_GATE,
        "allowed_next_gate_scope": P9CO_SCOPE,
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
        "source_p9cm_summary_sha256": evidence_file(p9cm_summary_path).get("sha256", ""),
        "source_p9cm_fresh_remote_proof_collection_approved": p9cm.get(
            "fresh_remote_proof_collection_approved_in_p9cm"
        ),
        "source_p9cm_fresh_proofs_collected": p9cm.get("fresh_proofs_collected_in_p9cm"),
        "source_evidence": {
            "phase9cm_summary": evidence_file(p9cm_summary_path),
            "phase9cm_p9cl_package_sufficiency_review": evidence_file(review_path_in),
            "phase9cm_future_p9cn_owner_gate_readiness": evidence_file(readiness_path_in),
            "phase9cm_non_authorization": evidence_file(matrix_path),
            "phase9cm_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(owner_gate_path, owner_gate)
    write_json(future_scope_path, future_scope)
    write_json(non_auth_path, non_authorization)
    write_json(control_path_out, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def build_phase9cn(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    return build_phase9cn_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate(
        args,
        now_fn=now_fn,
    )


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CN Read-Only Fresh Remote Proof Collection Owner Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CN is owner-gate-only. It allows only a future separately requested P9CO execution gate request and does not collect fresh proofs, approve proof-collection execution, approve live orders, execute the candidate, replace target plans, mutate executor input, invoke supervisor/timer/remote paths, or submit orders.",
        "",
        "## Owner Gate Boundary",
        "",
        "```text",
        "p9cn_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_ready = "
        f"{str(bool(summary['p9cn_post_account_blocker_read_only_fresh_remote_proof_collection_owner_gate_ready'])).lower()}",
        "eligible_for_future_p9co_execution_gate_request = "
        f"{str(bool(summary['eligible_for_future_p9co_execution_gate_request'])).lower()}",
        "fresh_remote_proof_collection_execution_approved_in_p9cn = false",
        "fresh_remote_proof_collection_performed_in_p9cn = false",
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
    summary, exit_code = build_phase9cn(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
