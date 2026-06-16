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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9by_live_order_gate_review_package import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    CONTRACT_VERSION as P9BY_CONTRACT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_OUTPUT_PARENT as P9BY_PARENT,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    P9BZ_GATE,
    P9BZ_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9bz_review_p9by_live_order_gate_package.v1"
)
APPROVE_P9BZ_DECISION = (
    "approve_p9bz_review_p9by_live_order_gate_package_only_no_order_no_execution"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9bz_review_p9by_package"
P9CA_GATE = "P9CA_define_fresh_remote_proof_collection_scope_only_if_separately_requested"
P9CA_SCOPE = (
    "define_fresh_remote_proof_collection_scope_only_no_remote_no_order_no_execution"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review retained P9BY live-order gate review package evidence. P9BZ "
            "is review-only: it does not collect fresh proofs, approve live "
            "orders, run supervisor/timer/remote paths, mutate executor input or "
            "target plans, execute the candidate, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9by-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BZ_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9bz_review_p9by_live_order_gate_package_only_if_separately_requested",
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


def latest_p9by_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9by_summary).strip():
        return resolve_path(args.phase9by_summary)
    return latest_match(P9BY_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def p9by_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9BY_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9by_live_order_gate_review_package_prepared") is True
        and summary.get("p9bx_sufficient_for_review_package") is True
        and summary.get("eligible_for_future_p9bz_package_review") is True
        and summary.get("eligible_for_future_fresh_remote_proof_collection") is False
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("fresh_proofs_collected_in_p9by") is False
        and summary.get("fresh_remote_account_read_performed") is False
        and summary.get("fresh_order_book_read_performed") is False
        and summary.get("exchange_filter_read_performed") is False
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("allowed_next_gate") == P9BZ_GATE
        and summary.get("allowed_next_gate_scope") == P9BZ_SCOPE
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
        and int(summary.get("required_fresh_proof_count") or 0) == 12
        and summary.get("only_distance_to_high_60_contribution_changed") is True
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "fill_count")
    )


def canary_terms_ready(canary: dict[str, Any]) -> bool:
    return (
        canary.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9by_canary_order_terms.v1"
        and canary.get("package_only") is True
        and canary.get("symbol") == CANARY_SYMBOL
        and canary.get("side") == CANARY_SIDE
        and float(canary.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(canary.get("max_notional_usdt") or 0) == DEFAULT_MAX_NOTIONAL_USDT
        and int(canary.get("max_orders_per_cycle") or 0) == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(canary.get("max_symbols_per_cycle") or 0) == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and canary.get("order_type") == DEFAULT_ORDER_TYPE
        and canary.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and canary.get("market_orders_allowed") is False
        and canary.get("post_only_required") is True
        and canary.get("maker_only_required") is True
        and canary.get("limit_order_must_not_cross_spread") is True
        and canary.get("candidate_delta_source") == "distance_to_high_60_contribution_only"
        and canary.get("would_submit_order") is False
    )


def fresh_plan_ready(plan: dict[str, Any]) -> bool:
    proof_rows = list(plan.get("proofs") or [])
    proof_by_id = {str(item.get("proof_id")): item for item in proof_rows}
    required = {
        "fresh_remote_account_read": 60,
        "pre_position_fingerprint": 60,
        "pre_open_order_fingerprint": 60,
        "pre_fill_trade_fingerprint": 60,
        "fresh_order_book": 10,
        "exchange_filter_readback": 60,
        "p9bu_terms_operator_acceptance": 300,
        "candidate_target_plan_hash_binding": 60,
        "baseline_candidate_plan_diff": 60,
        "kill_switch_readback": 60,
        "rollback_command_readback": 60,
        "final_owner_live_order_gate_approval": 300,
    }
    return (
        plan.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9by_fresh_proof_collection_plan.v1"
        and plan.get("package_only") is True
        and plan.get("fresh_proofs_collected_in_p9by") is False
        and plan.get("remote_account_read_performed") is False
        and plan.get("order_book_read_performed") is False
        and plan.get("exchange_filter_read_performed") is False
        and set(proof_by_id) == set(required)
        and all(
            int(dict(proof_by_id[key]).get("max_age_seconds") or 0) == max_age
            and dict(proof_by_id[key]).get("required") is True
            and dict(proof_by_id[key]).get("collection_status_in_p9by") == "not_collected"
            for key, max_age in required.items()
        )
    )


def approval_checklist_ready(checklist: dict[str, Any]) -> bool:
    items = list(checklist.get("approval_items") or [])
    required_items = {
        "all_required_fresh_proofs_present_and_unexpired",
        "candidate_target_plan_hash_bound_to_executor_input",
        "baseline_candidate_diff_dth60_only",
        "post_only_limit_price_does_not_cross_spread",
        "kill_switch_and_rollback_readback_available",
        "final_owner_live_order_gate_approval",
    }
    item_by_name = {str(item.get("item")): item for item in items}
    return (
        checklist.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9by_approval_checklist.v1"
        and checklist.get("package_only") is True
        and set(item_by_name) == required_items
        and all(
            dict(item_by_name[name]).get("required_for_live_order_gate") is True
            and dict(item_by_name[name]).get("satisfied_in_p9by") is False
            for name in required_items
        )
        and len(checklist.get("rollback_conditions") or []) >= 6
    )


def review_package_ready(package: dict[str, Any], summary: dict[str, Any]) -> bool:
    return (
        package.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9by_review_package.v1"
        and package.get("package_only") is True
        and package.get("future_gate_name") == "candidate_live_order_gate"
        and package.get("package_decision") == "prepared_for_future_review_only"
        and canary_terms_ready(dict(package.get("canary_order_terms") or {}))
        and fresh_plan_ready(dict(package.get("fresh_proof_collection_plan") or {}))
        and approval_checklist_ready(dict(package.get("approval_checklist") or {}))
        and "single canary order submission under exact P9BU terms"
        in list(package.get("future_gate_may_discuss") or [])
        and "final owner live-order gate approval"
        in list(package.get("future_gate_may_not_skip") or [])
        and package.get("baseline_target_plan_sha256")
        == summary.get("baseline_target_plan_sha256")
        and package.get("candidate_target_plan_sha256")
        == summary.get("candidate_target_plan_sha256")
        and package.get("only_distance_to_high_60_contribution_changed") is True
        and package.get("fresh_proofs_collected_in_p9by") is False
        and package.get("live_order_gate_approved") is False
        and package.get("live_order_submission_authorized") is False
        and package.get("candidate_execution_authorized") is False
        and int_zero(package, "orders_submitted")
        and int_zero(package, "fill_count")
    )


def p9by_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9by_non_authorization.v1"
        and authorizations.get("prepare_live_order_gate_review_package") is True
        and authorizations.get("review_live_order_gate_review_package") is True
        and authorizations.get("fresh_remote_proof_collection") is False
        and authorizations.get("live_order_gate_approval") is False
        and authorizations.get("actual_candidate_executor_target_path_entry") is False
        and authorizations.get("candidate_execution") is False
        and authorizations.get("live_order_submission") is False
        and authorizations.get("actual_target_plan_replacement") is False
        and authorizations.get("actual_executor_input_mutation") is False
        and authorizations.get("supervisor_invocation") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("remote_execution") is False
    )


def p9by_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9by_control_boundary.v1"
        and control.get("scope") == "live_order_gate_review_package_preparation_only"
        and control.get("fresh_remote_account_read_performed") is False
        and control.get("fresh_order_book_read_performed") is False
        and control.get("exchange_filter_read_performed") is False
        and control.get("entered_timer_path") is False
        and control.get("ran_supervisor") is False
        and control.get("remote_sync_performed") is False
        and control.get("remote_execution_performed") is False
        and control.get("candidate_execution_performed") is False
        and control.get("candidate_entered_actual_executor_target_plan_path") is False
        and control.get("live_order_submission_performed") is False
        and control.get("target_plan_replaced") is False
        and control.get("executor_input_changed") is False
        and int_zero(control, "orders_submitted")
        and int_zero(control, "fill_count")
        and int_zero(control, "trade_count")
    )


def build_p9bz_review_p9by_live_order_gate_package(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9bz" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9by_summary_path = latest_p9by_summary(args)
    p9by = load_optional(p9by_summary_path)
    package_path = source_output_path(p9by, "live_order_gate_review_package")
    canary_path = source_output_path(p9by, "canary_order_terms")
    fresh_plan_path = source_output_path(p9by, "fresh_proof_collection_plan")
    approval_path = source_output_path(p9by, "approval_checklist")
    matrix_path = source_output_path(p9by, "non_authorization")
    control_path = source_output_path(p9by, "control_boundary_readback")
    review_package = load_optional(package_path)
    canary = load_optional(canary_path)
    fresh_plan = load_optional(fresh_plan_path)
    approval = load_optional(approval_path)
    p9by_matrix = load_optional(matrix_path)
    p9by_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9BZ_DECISION
    checks = {
        "owner_decision_p9bz_review_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9by_summary_exists": bool(p9by),
        "p9by_summary_ready_for_package_review": p9by_summary_ready(p9by),
        "review_package_ready": review_package_ready(review_package, p9by),
        "canary_terms_ready": canary_terms_ready(canary),
        "fresh_proof_collection_plan_ready": fresh_plan_ready(fresh_plan),
        "approval_checklist_ready": approval_checklist_ready(approval),
        "p9by_non_authorization_ready": p9by_non_authorization_ready(p9by_matrix),
        "p9by_control_boundary_ready": p9by_control_ready(p9by_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bz_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "review_p9by_package_sufficiency_only_no_order_no_execution",
        "recorded_at_utc": iso_z(now),
        "package_review_approved": owner_decision_ok,
        "fresh_proof_collection_scope_definition_approved": False,
        "fresh_proof_collection_approved": False,
        "live_order_gate_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    review = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bz_sufficiency_review.v1",
        "run_id": run_id,
        "status": "ready" if ready else "blocked",
        "review_scope": "p9by_package_sufficiency_before_any_fresh_remote_proof_collection",
        "checks": checks,
        "blockers": blockers,
        "p9by_package_sufficient_for_fresh_remote_proof_collection_scope_definition": ready,
        "fresh_remote_proof_collection_scope_defined_in_p9bz": False,
        "fresh_remote_proof_collection_performed": False,
        "live_order_gate_approved": False,
    }
    prerequisites = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bz_future_gate_prerequisites.v1",
        "run_id": run_id,
        "allowed_next_gate": P9CA_GATE,
        "allowed_next_gate_scope": P9CA_SCOPE,
        "required_before_any_fresh_remote_proof_collection": [
            "separately requested P9CA scope definition",
            "target runner identity and read-only command boundary",
            "account-read, position, open-order, fill/trade, order-book, and exchange-filter proof collection plan",
            "no-order/no-cancel/no-trade delta acceptance contract",
            "explicit owner approval for proof collection only",
        ],
        "required_before_any_future_live_order_submission": [
            "fresh proofs collected and retained",
            "fresh no-order candidate executor input hash binding",
            "post-only order price proof from fresh order book",
            "kill switch and rollback readback",
            "final owner live-order gate approval",
        ],
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bz_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "review_p9by_live_order_gate_review_package": ready,
            "define_fresh_remote_proof_collection_scope": False,
            "fresh_remote_proof_collection": False,
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
            "remote_sync": False,
            "remote_execution": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bz_control_boundary.v1",
        "run_id": run_id,
        "scope": "p9by_package_review_only",
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
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
    review_path = proof_root / "sufficiency_review.json"
    prereq_path = proof_root / "future_gate_prerequisites.json"
    non_auth_path = proof_root / "non_authorization.json"
    control_path_out = proof_root / "control.json"
    summary_path = root / "summary.json"
    report_path = root / "p9bz_review_p9by_package.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "sufficiency_review": str(review_path),
        "future_gate_prerequisites": str(prereq_path),
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
        "p9bz_review_p9by_live_order_gate_package_ready": ready,
        "p9by_package_sufficient_for_fresh_remote_proof_collection_scope_definition": ready,
        "eligible_for_future_p9ca_scope_definition": ready,
        "eligible_for_future_fresh_remote_proof_collection": False,
        "eligible_for_future_live_order_submission": False,
        "fresh_remote_proof_collection_scope_defined_in_p9bz": False,
        "fresh_proofs_collected_in_p9bz": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
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
        "allowed_next_gate": P9CA_GATE,
        "allowed_next_gate_scope": P9CA_SCOPE,
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
        "required_fresh_proof_count": len(list(fresh_plan.get("proofs") or [])),
        "source_p9by_summary_sha256": evidence_file(p9by_summary_path).get("sha256", ""),
        "baseline_target_plan_sha256": p9by.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9by.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9by.get(
            "only_distance_to_high_60_contribution_changed"
        ),
        "source_evidence": {
            "phase9by_summary": evidence_file(p9by_summary_path),
            "phase9by_review_package": evidence_file(package_path),
            "phase9by_canary_order_terms": evidence_file(canary_path),
            "phase9by_fresh_proof_collection_plan": evidence_file(fresh_plan_path),
            "phase9by_approval_checklist": evidence_file(approval_path),
            "phase9by_non_authorization": evidence_file(matrix_path),
            "phase9by_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(review_path, review)
    write_json(prereq_path, prerequisites)
    write_json(non_auth_path, non_authorization)
    write_json(control_path_out, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary), encoding="utf-8")

    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9BZ Review P9BY Live-Order Gate Package",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9BZ reviews the retained P9BY live-order gate review package only. It does not define fresh remote proof collection scope, collect fresh proofs, approve live orders, execute the candidate, replace target plans, mutate executor input, invoke supervisor/timer/remote paths, or submit orders.",
        "",
        "## Review Boundary",
        "",
        "```text",
        f"p9bz_review_p9by_live_order_gate_package_ready = {str(bool(summary['p9bz_review_p9by_live_order_gate_package_ready'])).lower()}",
        f"p9by_package_sufficient_for_fresh_remote_proof_collection_scope_definition = {str(bool(summary['p9by_package_sufficient_for_fresh_remote_proof_collection_scope_definition'])).lower()}",
        "fresh_remote_proof_collection_scope_defined_in_p9bz = false",
        "fresh_proofs_collected_in_p9bz = false",
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
        "```",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p9bz_review_p9by_live_order_gate_package(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
