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
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cy_review_p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package import (  # noqa: E402
    CONTRACT_VERSION as P9CY_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CY_PARENT,
    P9CZ_GATE,
    P9CZ_SCOPE,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9cz_final_owner_live_order_decision_gate.v1"
APPROVE_P9CZ_DECISION = (
    "approve_p9cz_final_owner_live_order_decision_gate_candidate_path_and_single_post_only_canary_only"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9cz_final_owner_live_order_decision_gate"
P9DA_GATE = "P9DA_execute_single_post_only_canary_live_order_only_if_separately_requested"
P9DA_SCOPE = (
    "execute_one_btcusdt_buy_post_only_gtx_canary_after_fresh_pre_submit_readback_and_kill_switch_check"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect the P9CZ final owner live-order decision for candidate "
            "executor-path entry and one single post-only canary order under "
            "retained P9CY terms. P9CZ records approval only; it does not SSH, "
            "read Binance, call order-test endpoints, submit orders, execute "
            "the candidate, mutate executor input or target plans, remote sync, "
            "or invoke supervisor/timer paths."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cy-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CZ_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9cz_final_owner_live_order_decision_gate_only_if_separately_requested",
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


def latest_p9cy_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cy_summary).strip():
        return resolve_path(args.phase9cy_summary)
    return latest_match(P9CY_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9cy_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9CY_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get(
            "p9cy_review_p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_ready"
        )
        is True
        and summary.get("p9cx_retained_evidence_sufficient_for_p9cy_review") is True
        and summary.get(
            "p9cx_big_package_sufficient_for_final_live_order_decision_discussion"
        )
        is True
        and summary.get("p9cx_big_package_sufficient_for_live_order_submission")
        is False
        and summary.get("p9cx_big_package_sufficient_for_candidate_execution")
        is False
        and summary.get("p9cx_satisfies_final_owner_live_order_gate") is False
        and summary.get("final_owner_live_order_gate_approval_collected") is False
        and summary.get("explicit_final_owner_live_order_decision_collected") is False
        and int(summary.get("fresh_final_decision_evidence_total_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE)
        and int(summary.get("fresh_final_decision_evidence_read_only_or_plan_ready_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE) - 2
        and int(summary.get("fresh_final_decision_evidence_not_collected_by_design_count") or 0)
        == 2
        and set(summary.get("remaining_gap_ids_before_final_live_order_decision") or [])
        == {"final_owner_live_order_gate_approval", "explicit_final_owner_live_order_decision"}
        and summary.get("eligible_for_future_p9cz_final_owner_live_order_decision_gate")
        is True
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("eligible_for_future_candidate_execution") is False
        and summary.get("candidate_enter_executor_target_plan_path_authorized")
        is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("fresh_remote_proof_collection_performed_in_p9cy") is False
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
        and summary.get("allowed_next_gate") == P9CZ_GATE
        and summary.get("allowed_next_gate_scope") == P9CZ_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def p9cy_sufficiency_ready(review: dict[str, Any]) -> bool:
    checks = dict(review.get("checks") or {})
    return (
        review.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cy_p9cx_sufficiency_review.v1"
        and review.get("review_only") is True
        and review.get("p9cx_retained_evidence_sufficient_for_p9cy_review") is True
        and review.get(
            "p9cx_big_package_sufficient_for_final_live_order_decision_discussion"
        )
        is True
        and review.get("p9cx_big_package_sufficient_for_live_order_submission")
        is False
        and review.get("p9cx_big_package_sufficient_for_candidate_execution")
        is False
        and review.get("p9cx_satisfies_final_owner_live_order_gate") is False
        and review.get("final_owner_live_order_gate_approval_collected") is False
        and review.get("explicit_final_owner_live_order_decision_collected") is False
        and review.get("future_gate") == P9CZ_GATE
        and review.get("future_gate_scope") == P9CZ_SCOPE
        and review.get("future_gate_must_be_separately_requested") is True
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def p9cy_gap_matrix_ready(matrix: dict[str, Any]) -> bool:
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cy_final_decision_gap_matrix.v1"
        and matrix.get("review_only") is True
        and int(matrix.get("evidence_total_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE)
        and int(matrix.get("ready_or_plan_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE) - 2
        and int(matrix.get("remaining_gap_count") or 0) == 2
        and set(matrix.get("remaining_gap_ids") or [])
        == {"final_owner_live_order_gate_approval", "explicit_final_owner_live_order_decision"}
        and matrix.get(
            "p9cx_big_package_sufficient_for_final_live_order_decision_discussion"
        )
        is True
        and matrix.get("p9cx_satisfies_final_owner_live_order_gate") is False
    )


def p9cy_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cy_non_authorization.v1"
        and authorizations.get("review_p9cx_retained_big_package") is True
        and authorizations.get(
            "allow_future_p9cz_final_owner_live_order_decision_gate_request"
        )
        is True
        and authorizations.get("collect_final_owner_live_order_decision_in_p9cy")
        is False
        and authorizations.get("final_owner_live_order_gate_approval") is False
        and authorizations.get("fresh_remote_proof_collection") is False
        and authorizations.get("fresh_remote_account_read") is False
        and authorizations.get("fresh_order_book_read") is False
        and authorizations.get("exchange_filter_read") is False
        and authorizations.get("order_test_endpoint") is False
        and authorizations.get("remote_execution") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("remote_file_write") is False
        and authorizations.get("actual_candidate_executor_target_path_entry") is False
        and authorizations.get("candidate_execution") is False
        and authorizations.get("live_order_submission") is False
        and authorizations.get("actual_target_plan_replacement") is False
        and authorizations.get("actual_executor_input_mutation") is False
        and authorizations.get("timer_path_load") is False
        and authorizations.get("production_timer_service_load") is False
        and authorizations.get("supervisor_invocation") is False
        and authorizations.get("stage_governance_change") is False
    )


def p9cy_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cy_control_boundary.v1"
        and control.get("scope") == "review_p9cx_retained_big_package_only"
        and control.get("ssh_invoked") is False
        and control.get("fresh_remote_proof_collection_performed_in_p9cy") is False
        and control.get("fresh_remote_account_read_performed") is False
        and control.get("fresh_order_book_read_performed") is False
        and control.get("exchange_filter_read_performed") is False
        and control.get("order_test_endpoint_called") is False
        and control.get("entered_timer_path") is False
        and control.get("ran_supervisor") is False
        and control.get("remote_sync_performed") is False
        and control.get("remote_execution_performed") is False
        and int_zero(control, "remote_files_written")
        and control.get("candidate_execution_performed") is False
        and control.get("candidate_entered_actual_executor_target_plan_path") is False
        and control.get("live_order_submission_performed") is False
        and control.get("target_plan_replaced") is False
        and control.get("executor_input_changed") is False
        and int_zero(control, "orders_submitted")
        and int_zero(control, "orders_canceled")
        and int_zero(control, "fill_count")
        and int_zero(control, "trade_count")
    )


def build_approved_terms(p9cy: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cz_approved_single_canary_terms.v1",
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
        "reduce_only_required_for_rollback_exits": True,
        "candidate_delta_source": "distance_to_high_60_contribution_only",
        "baseline_target_plan_sha256": p9cy.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9cy.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9cy.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
    }


def build_pre_submit_requirements(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cz_pre_submit_requirements_for_p9da.v1",
        "run_id": run_id,
        "required_before_any_future_order_submission": [
            "fresh pre-submit account read using /fapi/v2/account.canTrade",
            "fresh pre-submit position and open-order fingerprint",
            "fresh pre-submit order/fill/trade delta fingerprint",
            "fresh order book and exchange filter readback",
            "post-only GTX limit price must not cross spread",
            "kill switch readable and rollback path documented",
            "candidate target plan hash must match approved P9CZ candidate hash",
            "executor input replacement must be scoped to one canary cycle only",
        ],
        "fresh_pre_submit_readback_max_age_seconds": 30,
        "candidate_artifact_stale_after_seconds": 60,
        "order_lifetime_seconds": 60,
        "cancel_if_not_maker_or_unexpected_delta": True,
    }


def build_phase9cz(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cz" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cy_path = latest_p9cy_summary(args)
    p9cy = load_optional(p9cy_path)
    review_path = source_output_path(p9cy, "p9cx_sufficiency_review")
    gap_path = source_output_path(p9cy, "final_decision_gap_matrix")
    non_auth_path = source_output_path(p9cy, "non_authorization")
    control_path = source_output_path(p9cy, "control_boundary_readback")
    review = load_optional(review_path)
    gap = load_optional(gap_path)
    p9cy_non_auth = load_optional(non_auth_path)
    p9cy_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CZ_DECISION

    checks = {
        "owner_decision_p9cz_final_live_order_decision_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cy_summary_exists": bool(p9cy),
        "p9cy_summary_ready_for_p9cz": p9cy_summary_ready(p9cy),
        "p9cy_sufficiency_review_ready": p9cy_sufficiency_ready(review),
        "p9cy_gap_matrix_ready": p9cy_gap_matrix_ready(gap),
        "p9cy_non_authorization_ready": p9cy_non_authorization_ready(p9cy_non_auth),
        "p9cy_control_boundary_ready": p9cy_control_ready(p9cy_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    approved_terms = build_approved_terms(p9cy)
    pre_submit = build_pre_submit_requirements(run_id)
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cz_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "approve_candidate_executor_path_and_single_post_only_canary_under_retained_p9cy_terms",
        "recorded_at_utc": iso_z(now),
        "final_owner_live_order_gate_approval_collected": owner_decision_ok,
        "explicit_final_owner_live_order_decision_collected": owner_decision_ok,
        "approved_only_if_p9cy_ready": ready,
        "actual_order_submission_performed": False,
    }
    final_decision = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cz_final_owner_live_order_decision.v1",
        "run_id": run_id,
        "decision_status": "approved" if ready else "blocked",
        "final_owner_live_order_gate_approval_collected": ready,
        "explicit_final_owner_live_order_decision_collected": ready,
        "candidate_enter_executor_target_plan_path_authorized_for_future_p9da": ready,
        "target_plan_replacement_authorized_for_future_p9da": ready,
        "candidate_execution_authorized_for_future_single_canary": ready,
        "live_order_submission_authorized_for_future_single_canary": ready,
        "actual_candidate_executor_target_path_entry_performed": False,
        "actual_target_plan_replacement_performed": False,
        "actual_executor_input_mutation_performed": False,
        "actual_order_submission_performed": False,
        "approved_terms": approved_terms,
        "pre_submit_requirements_for_p9da": pre_submit,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cz_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "final_owner_live_order_gate_approval_recorded": ready,
            "future_p9da_single_post_only_canary_request_allowed": ready,
            "actual_candidate_executor_target_path_entry_in_p9cz": False,
            "actual_target_plan_replacement_in_p9cz": False,
            "actual_executor_input_mutation_in_p9cz": False,
            "candidate_execution_in_p9cz": False,
            "live_order_submission_in_p9cz": False,
            "order_test_endpoint": False,
            "remote_execution": False,
            "remote_sync": False,
            "remote_file_write": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
            "supervisor_invocation": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cz_control_boundary.v1",
        "run_id": run_id,
        "scope": "final_owner_live_order_decision_record_only",
        "ssh_invoked": False,
        "fresh_remote_proof_collection_performed_in_p9cz": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "remote_files_written": 0,
        "candidate_execution_performed": False,
        "candidate_entered_actual_executor_target_plan_path": False,
        "live_order_submission_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "final_owner_live_order_decision": str(
            proof_root / "final_owner_live_order_decision.json"
        ),
        "approved_single_canary_terms": str(
            proof_root / "approved_single_canary_terms.json"
        ),
        "pre_submit_requirements_for_p9da": str(
            proof_root / "pre_submit_requirements_for_p9da.json"
        ),
        "non_authorization": str(proof_root / "non_authorization.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "p9cz_final_owner_live_order_decision_gate.md"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "p9cz_final_owner_live_order_decision_gate_ready": ready,
        "p9cy_sufficient_for_p9cz_final_decision": ready,
        "final_owner_live_order_gate_approval_collected": ready,
        "explicit_final_owner_live_order_decision_collected": ready,
        "p9cz_satisfies_final_owner_live_order_decision_gate": ready,
        "candidate_enter_executor_target_plan_path_authorized": ready,
        "target_plan_replacement_authorized": ready,
        "candidate_execution_authorized": ready,
        "live_order_submission_authorized": ready,
        "authorization_scope": "future_p9da_single_post_only_canary_only",
        "actual_candidate_executor_target_path_entry_performed": False,
        "actual_target_plan_replacement_performed": False,
        "actual_executor_input_mutation_performed": False,
        "actual_candidate_execution_performed": False,
        "actual_live_order_submission_performed": False,
        "eligible_for_future_p9da_single_post_only_canary_execution": ready,
        "fresh_pre_submit_readback_required_before_p9da": True,
        "fresh_remote_proof_collection_performed_in_p9cz": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
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
        "post_only_required": True,
        "maker_only_required": True,
        "limit_order_must_not_cross_spread": True,
        "baseline_target_plan_sha256": p9cy.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9cy.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9cy.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
        "allowed_next_gate": P9DA_GATE,
        "allowed_next_gate_scope": P9DA_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9cy_summary": evidence_file(p9cy_path),
            "phase9cy_p9cx_sufficiency_review": evidence_file(review_path),
            "phase9cy_final_decision_gap_matrix": evidence_file(gap_path),
            "phase9cy_non_authorization": evidence_file(non_auth_path),
            "phase9cy_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(Path(output_files["owner_decision_record"]), owner_record)
    write_json(Path(output_files["final_owner_live_order_decision"]), final_decision)
    write_json(Path(output_files["approved_single_canary_terms"]), approved_terms)
    write_json(Path(output_files["pre_submit_requirements_for_p9da"]), pre_submit)
    write_json(Path(output_files["non_authorization"]), non_authorization)
    write_json(Path(output_files["control_boundary_readback"]), control)
    write_json(Path(output_files["summary"]), summary)
    Path(output_files["report"]).write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CZ Final Owner Live-Order Decision Gate",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CZ records the final owner decision for candidate executor-path entry and one future single post-only canary order. It is a decision-record gate only: no order is submitted, no candidate is executed, no target plan is replaced, no executor input is mutated, and no timer/supervisor path is invoked in P9CZ.",
        "",
        "## Decision",
        "",
        "```text",
        f"final_owner_live_order_gate_approval_collected = {str(bool(summary['final_owner_live_order_gate_approval_collected'])).lower()}",
        f"explicit_final_owner_live_order_decision_collected = {str(bool(summary['explicit_final_owner_live_order_decision_collected'])).lower()}",
        f"candidate_enter_executor_target_plan_path_authorized = {str(bool(summary['candidate_enter_executor_target_plan_path_authorized'])).lower()}",
        f"target_plan_replacement_authorized = {str(bool(summary['target_plan_replacement_authorized'])).lower()}",
        f"live_order_submission_authorized = {str(bool(summary['live_order_submission_authorized'])).lower()}",
        "authorization_scope = future_p9da_single_post_only_canary_only",
        "actual_live_order_submission_performed = false",
        "actual_executor_input_mutation_performed = false",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Approved Canary Terms",
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
        "post_only_required = true",
        "maker_only_required = true",
        "limit_order_must_not_cross_spread = true",
        "```",
        "",
        "## Next Gate",
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
    summary, exit_code = build_phase9cz(parse_args(argv))
    print(
        "p9cz_final_owner_live_order_decision_gate_ready="
        + str(bool(summary["p9cz_final_owner_live_order_decision_gate_ready"])).lower()
    )
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
