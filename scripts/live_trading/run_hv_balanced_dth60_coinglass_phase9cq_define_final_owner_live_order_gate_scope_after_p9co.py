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
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    EXPECTED_PROOFS,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cp_review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection import (  # noqa: E402
    CONTRACT_VERSION as P9CP_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CP_PARENT,
    P9CQ_GATE,
    P9CQ_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9cq_define_final_owner_live_order_gate_scope_after_p9co.v1"
)
APPROVE_P9CQ_DECISION = (
    "approve_p9cq_define_final_owner_live_order_gate_scope_after_p9co_only_no_order_no_candidate_no_executor_or_timer_change"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9cq_final_owner_live_order_gate_scope_after_p9co"
)
P9CR_GATE = (
    "P9CR_prepare_final_owner_live_order_gate_review_package_after_p9co_only_if_separately_requested"
)
P9CR_SCOPE = (
    "prepare_final_owner_live_order_gate_review_package_after_p9cq_scope_only_no_order_no_candidate_no_executor_or_timer_change"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Define P9CQ final owner live-order gate scope after P9CO/P9CP. "
            "P9CQ is scope-definition-only: it does not SSH, read Binance, "
            "collect fresh proofs, call order-test endpoints, run supervisor or "
            "timer paths, execute the candidate, mutate executor input or target "
            "plans, remote sync, cancel orders, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cp-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CQ_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9cq_define_final_owner_live_order_gate_scope_after_p9co_only_if_separately_requested"
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


def latest_p9cp_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cp_summary).strip():
        return resolve_path(args.phase9cp_summary)
    return latest_match(P9CP_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9cp_summary_ready(summary: dict[str, Any]) -> bool:
    checks = dict(summary.get("checks") or {})
    return (
        summary.get("contract_version") == P9CP_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get(
            "p9cp_review_p9co_post_account_blocker_read_only_fresh_remote_proof_collection_ready"
        )
        is True
        and summary.get("p9co_retained_evidence_sufficient_for_p9cp_review") is True
        and summary.get("p9co_read_only_fresh_proofs_sufficient_for_next_scope_gate")
        is True
        and summary.get("p9co_sufficient_for_live_order_submission") is False
        and summary.get("p9co_sufficient_for_candidate_execution") is False
        and summary.get("account_blocker_cleared_by_p9co") is True
        and summary.get("read_only_fresh_proofs_ready") is True
        and summary.get("final_owner_live_order_gate_approval_collected") is False
        and summary.get("final_owner_live_order_gate_approval_required_next") is True
        and summary.get("eligible_for_future_p9cq_scope_definition") is True
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_enter_executor_target_plan_path_authorized")
        is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("remote_execution_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("fresh_remote_proof_collection_performed_in_p9cp") is False
        and summary.get("fresh_remote_account_read_performed") is False
        and summary.get("fresh_order_book_read_performed") is False
        and summary.get("exchange_filter_read_performed") is False
        and summary.get("order_test_endpoint_called") is False
        and summary.get("remote_execution_performed") is False
        and summary.get("remote_sync_performed") is False
        and int_zero(summary, "remote_files_written")
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and summary.get("source_p9co_can_trade_pre") is True
        and summary.get("source_p9co_can_trade_post") is True
        and summary.get("source_p9co_open_order_count_pre") == 0
        and summary.get("source_p9co_open_order_count_post") == 0
        and summary.get("source_p9co_order_cancel_fill_trade_delta_zero") is True
        and summary.get("source_p9co_remote_control_boundary_unchanged") is True
        and summary.get("source_p9co_only_distance_to_high_60_contribution_changed")
        is True
        and bool(summary.get("source_p9co_baseline_target_plan_sha256"))
        and bool(summary.get("source_p9co_candidate_target_plan_sha256"))
        and summary.get("source_p9co_baseline_target_plan_sha256")
        != summary.get("source_p9co_candidate_target_plan_sha256")
        and summary.get("allowed_next_gate") == P9CQ_GATE
        and summary.get("allowed_next_gate_scope") == P9CQ_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def p9cp_sufficiency_ready(review: dict[str, Any]) -> bool:
    checks = dict(review.get("checks") or {})
    return (
        review.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cp_p9co_sufficiency_review.v1"
        and review.get("review_only") is True
        and review.get("p9co_retained_evidence_sufficient_for_p9cp_review") is True
        and review.get("p9co_read_only_fresh_proofs_sufficient_for_next_scope_gate")
        is True
        and review.get("p9co_sufficient_for_live_order_submission") is False
        and review.get("p9co_sufficient_for_candidate_execution") is False
        and review.get("final_owner_live_order_gate_approval_collected") is False
        and review.get("final_owner_live_order_gate_approval_required_next") is True
        and review.get("eligible_for_future_p9cq_scope_definition") is True
        and review.get("future_gate") == P9CQ_GATE
        and review.get("future_gate_scope") == P9CQ_SCOPE
        and review.get("future_gate_must_be_separately_requested") is True
        and review.get("read_only_fresh_proofs_ready") is True
        and review.get("account_blocker_cleared_by_p9co") is True
        and list(review.get("live_order_readiness_blockers_after_p9co") or []) == []
        and int_zero(review, "orders_submitted")
        and int_zero(review, "orders_canceled")
        and int_zero(review, "fill_count")
        and int_zero(review, "trade_count")
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def p9cp_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cp_non_authorization.v1"
        and authorizations.get("review_p9co_retained_evidence") is True
        and authorizations.get("allow_future_p9cq_scope_definition_request") is True
        and authorizations.get("define_p9cq_scope_in_p9cp") is False
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


def p9cp_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cp_control_boundary.v1"
        and control.get("scope") == "p9co_retained_evidence_review_only"
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


def required_final_gate_evidence() -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": proof_id,
            "max_age_seconds": max_age,
            "required_before": "final_owner_live_order_gate_approval",
            "must_be_retained": True,
        }
        for proof_id, max_age in EXPECTED_PROOFS.items()
    ] + [
        {
            "evidence_id": "explicit_final_owner_live_order_decision",
            "max_age_seconds": 300,
            "required_before": "any_order_submission",
            "must_be_retained": True,
        },
        {
            "evidence_id": "pre_order_control_boundary_readback",
            "max_age_seconds": 60,
            "required_before": "any_candidate_executor_path_entry",
            "must_be_retained": True,
        },
        {
            "evidence_id": "post_order_observation_and_rollback_plan",
            "max_age_seconds": 300,
            "required_before": "any_order_submission",
            "must_be_retained": True,
        },
    ]


def build_final_owner_scope(p9cp: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": (
            "hv_balanced_dth60_coinglass_phase9cq_final_owner_live_order_gate_scope.v1"
        ),
        "scope_definition_only": True,
        "scope_basis": "retained_p9cp_review_of_p9co_read_only_fresh_remote_proofs",
        "source_p9co_baseline_target_plan_sha256": p9cp.get(
            "source_p9co_baseline_target_plan_sha256"
        ),
        "source_p9co_candidate_target_plan_sha256": p9cp.get(
            "source_p9co_candidate_target_plan_sha256"
        ),
        "final_owner_gate_name": "final_owner_live_order_gate_after_p9co",
        "final_owner_gate_may_discuss": [
            "whether to approve candidate entry into the executor target-plan path",
            "whether to approve replacing the baseline executor input with the retained candidate target-plan hash",
            "whether to submit one maker-only post-only canary order under exact risk terms",
            "what post-order observation window and rollback triggers must bind the canary",
        ],
        "final_owner_gate_may_not_skip": [
            "freshness evaluation for every required final-gate evidence row",
            "PIT-safe account permission decision from /fapi/v2/account.canTrade",
            "baseline/candidate same-risk target-plan binding",
            "distance_to_high_60-only contribution delta proof",
            "kill switch and rollback readback on the target runner",
            "explicit final owner approval naming candidate path, order terms, and rollback terms",
        ],
        "exact_canary_terms": {
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
        "candidate_path_terms": {
            "candidate_may_enter_executor_target_plan_path_only_in_final_gate": True,
            "candidate_execution_may_be_authorized_only_in_final_gate": True,
            "target_plan_replacement_may_be_authorized_only_in_final_gate": True,
            "executor_input_mutation_may_be_authorized_only_in_final_gate": True,
            "must_bind_candidate_target_plan_hash": True,
            "must_preserve_same_timestamp_same_risk_inputs": True,
            "only_allowed_strategy_delta": "distance_to_high_60_contribution",
        },
        "kill_switch_terms": [
            "disable candidate executor path",
            "restore baseline target-plan hash",
            "cancel only the canary order if still open and explicitly approved",
            "re-read account, order, fill, trade, position, and balance fingerprints",
        ],
        "rollback_conditions": [
            "any required final-gate evidence is missing, stale, or hash-mismatched",
            "/fapi/v2/account.canTrade is false or missing",
            "/fapi/v3/account.canTrade is used for permission decisions",
            "candidate target-plan hash differs from the final no-order approved hash",
            "candidate delta affects anything outside distance_to_high_60 contribution",
            "order book no longer supports maker-only post-only execution",
            "exchange filters reject the canary order terms",
            "open-order, fill, trade, balance, or position delta is unexplained",
            "supervisor, timer, operator, exchange, or provider health readback reports an exception",
        ],
        "out_of_scope_for_p9cq": [
            "fresh remote proof collection",
            "order-test endpoint calls",
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


def build_phase9cq(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cq" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cp_path = latest_p9cp_summary(args)
    p9cp = load_optional(p9cp_path)
    sufficiency_path = source_output_path(p9cp, "p9co_sufficiency_review")
    non_auth_path = source_output_path(p9cp, "non_authorization")
    control_path = source_output_path(p9cp, "control_boundary_readback")
    sufficiency = load_optional(sufficiency_path)
    p9cp_non_auth = load_optional(non_auth_path)
    p9cp_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CQ_DECISION
    checks = {
        "owner_decision_p9cq_scope_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cp_summary_exists": bool(p9cp),
        "p9cp_summary_ready_for_p9cq_scope_definition": p9cp_summary_ready(p9cp),
        "p9cp_sufficiency_review_ready": p9cp_sufficiency_ready(sufficiency),
        "p9cp_non_authorization_ready": p9cp_non_authorization_ready(p9cp_non_auth),
        "p9cp_control_boundary_ready": p9cp_control_ready(p9cp_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    final_scope = build_final_owner_scope(p9cp)
    required_evidence = {
        "contract_version": (
            "hv_balanced_dth60_coinglass_phase9cq_required_final_gate_evidence.v1"
        ),
        "scope_definition_only": True,
        "evidence": required_final_gate_evidence(),
        "final_owner_gate_required_before_any_order_submission": True,
        "p9cq_satisfies_final_owner_live_order_gate": False,
        "fresh_remote_proof_collection_performed_in_p9cq": False,
    }
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cq_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": (
            "define_final_owner_live_order_gate_scope_after_p9co_only_no_order_no_candidate_no_executor_or_timer_change"
        ),
        "recorded_at_utc": iso_z(now),
        "scope_definition_approved": owner_decision_ok,
        "final_owner_live_order_gate_approved": False,
        "candidate_executor_path_entry_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cq_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "define_final_owner_live_order_gate_scope": ready,
            "prepare_future_p9cr_review_package": ready,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9cq_control_boundary.v1",
        "run_id": run_id,
        "scope": "final_owner_live_order_gate_scope_definition_only",
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
    scope_path = proof_root / "final_owner_live_order_gate_scope.json"
    required_evidence_path = proof_root / "required_final_gate_evidence.json"
    non_auth_out_path = proof_root / "non_authorization.json"
    control_out_path = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9cq_final_owner_live_order_gate_scope.md"
    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "final_owner_live_order_gate_scope": str(scope_path),
        "required_final_gate_evidence": str(required_evidence_path),
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
        "p9cq_final_owner_live_order_gate_scope_defined": ready,
        "p9cp_sufficient_for_p9cq_scope_definition": p9cp_summary_ready(p9cp),
        "p9co_retained_read_only_fresh_proofs_ready": p9cp.get(
            "p9co_read_only_fresh_proofs_sufficient_for_next_scope_gate"
        )
        is True,
        "account_blocker_cleared_by_p9co": p9cp.get("account_blocker_cleared_by_p9co")
        is True,
        "final_owner_live_order_gate_scope_defined_after_p9co": ready,
        "required_final_gate_evidence_count": len(required_evidence["evidence"]),
        "final_owner_live_order_gate_approval_collected": False,
        "final_owner_live_order_gate_approval_required_next": True,
        "p9cq_satisfies_final_owner_live_order_gate": False,
        "eligible_for_future_p9cr_review_package": ready,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "eligible_for_future_candidate_executor_path_entry": False,
        "fresh_remote_proof_collection_performed_in_p9cq": False,
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
        "allowed_next_gate": P9CR_GATE,
        "allowed_next_gate_scope": P9CR_SCOPE,
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
        "source_p9cp_summary_sha256": evidence_file(p9cp_path).get("sha256", ""),
        "source_p9cp_sufficiency_review_sha256": evidence_file(
            sufficiency_path
        ).get("sha256", ""),
        "source_p9cp_non_authorization_sha256": evidence_file(non_auth_path).get(
            "sha256", ""
        ),
        "source_p9cp_control_boundary_sha256": evidence_file(control_path).get(
            "sha256", ""
        ),
        "source_p9co_baseline_target_plan_sha256": p9cp.get(
            "source_p9co_baseline_target_plan_sha256"
        ),
        "source_p9co_candidate_target_plan_sha256": p9cp.get(
            "source_p9co_candidate_target_plan_sha256"
        ),
        "source_p9co_can_trade_pre": p9cp.get("source_p9co_can_trade_pre"),
        "source_p9co_can_trade_post": p9cp.get("source_p9co_can_trade_post"),
        "source_p9co_open_position_count_pre": p9cp.get(
            "source_p9co_open_position_count_pre"
        ),
        "source_p9co_open_position_count_post": p9cp.get(
            "source_p9co_open_position_count_post"
        ),
        "source_p9co_open_order_count_pre": p9cp.get("source_p9co_open_order_count_pre"),
        "source_p9co_open_order_count_post": p9cp.get(
            "source_p9co_open_order_count_post"
        ),
        "source_p9co_order_cancel_fill_trade_delta_zero": p9cp.get(
            "source_p9co_order_cancel_fill_trade_delta_zero"
        ),
        "source_p9co_remote_control_boundary_unchanged": p9cp.get(
            "source_p9co_remote_control_boundary_unchanged"
        ),
        "source_p9co_only_distance_to_high_60_contribution_changed": p9cp.get(
            "source_p9co_only_distance_to_high_60_contribution_changed"
        ),
        "source_evidence": {
            "phase9cp_summary": evidence_file(p9cp_path),
            "phase9cp_p9co_sufficiency_review": evidence_file(sufficiency_path),
            "phase9cp_non_authorization": evidence_file(non_auth_path),
            "phase9cp_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(scope_path, final_scope)
    write_json(required_evidence_path, required_evidence)
    write_json(non_auth_out_path, non_authorization)
    write_json(control_out_path, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary, final_scope, required_evidence), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(
    summary: dict[str, Any],
    scope: dict[str, Any],
    required_evidence: dict[str, Any],
) -> str:
    canary = dict(scope.get("exact_canary_terms") or {})
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CQ Final Owner Live-Order Gate Scope",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CQ defines the final owner live-order gate scope after retained P9CO/P9CP proof. It does not approve live orders, execute the candidate, replace target plans, mutate executor input, collect fresh remote proofs, invoke supervisor/timer paths, remote sync, cancel orders, or submit orders.",
        "",
        "## Scope Result",
        "",
        "```text",
        "p9cq_final_owner_live_order_gate_scope_defined = "
        f"{str(bool(summary['p9cq_final_owner_live_order_gate_scope_defined'])).lower()}",
        "p9cq_satisfies_final_owner_live_order_gate = false",
        "live_order_gate_approved = false",
        "live_order_submission_authorized = false",
        "candidate_enter_executor_target_plan_path_authorized = false",
        "candidate_execution_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Exact Canary Terms For Future Discussion",
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
        "## Required Final-Gate Evidence",
        "",
    ]
    for row in list(required_evidence.get("evidence") or []):
        lines.append(
            f"- `{row['evidence_id']}` max_age_seconds={row['max_age_seconds']}"
        )
    lines.extend(["", "## Out Of Scope", ""])
    for item in list(scope.get("out_of_scope_for_p9cq") or []):
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
    summary, exit_code = build_phase9cq(parse_args(argv))
    print(
        "p9cq_final_owner_live_order_gate_scope_defined="
        + str(bool(summary["p9cq_final_owner_live_order_gate_scope_defined"])).lower()
    )
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
