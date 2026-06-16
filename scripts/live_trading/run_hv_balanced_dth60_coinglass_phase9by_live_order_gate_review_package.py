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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bx_live_order_gate_scope_definition import (  # noqa: E402
    CANARY_SIDE,
    CANARY_SYMBOL,
    CONTRACT_VERSION as P9BX_CONTRACT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_OUTPUT_PARENT as P9BX_PARENT,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
    P9BY_GATE,
    P9BY_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9by_live_order_gate_review_package.v1"
)
APPROVE_P9BY_DECISION = (
    "approve_p9by_prepare_live_order_gate_review_package_only_no_order_no_execution"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9by_live_order_review_package"
P9BZ_GATE = "P9BZ_review_p9by_live_order_gate_package_only_if_separately_requested"
P9BZ_SCOPE = (
    "review_p9by_package_sufficiency_before_any_fresh_remote_proof_collection_no_order_no_execution"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the P9BY live-order gate review package from retained P9BX "
            "scope evidence. P9BY does not collect fresh proofs, approve live "
            "orders, run supervisor/timer/remote paths, mutate executor input or "
            "target plans, execute the candidate, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9bx-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BY_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9by_prepare_live_order_gate_review_package_only_if_separately_requested",
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


def latest_p9bx_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bx_summary).strip():
        return resolve_path(args.phase9bx_summary)
    return latest_match(P9BX_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def p9bx_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9BX_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9bx_live_order_gate_scope_defined") is True
        and summary.get("p9bw_sufficient_for_scope_definition") is True
        and summary.get("eligible_for_future_live_order_gate_review_package") is True
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("live_order_gate_approved") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("allowed_next_gate") == P9BY_GATE
        and summary.get("allowed_next_gate_scope") == P9BY_SCOPE
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
        and int(summary.get("changed_symbol_count") or 0) == 1
        and int(summary.get("order_intent_preview_count") or 0) == 1
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "fill_count")
    )


def p9bx_scope_ready(scope: dict[str, Any]) -> bool:
    canary = dict(scope.get("canary_terms") or {})
    return (
        scope.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bx_live_order_gate_scope.v1"
        and scope.get("scope_definition_only") is True
        and scope.get("future_gate_name") == "candidate_live_order_gate"
        and "single canary order submission under exact P9BU terms"
        in list(scope.get("future_gate_may_discuss") or [])
        and "final owner live-order gate approval"
        in list(scope.get("future_gate_may_not_skip") or [])
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
        and canary.get("candidate_delta_source") == "distance_to_high_60_contribution_only"
        and "actual order placement" in list(scope.get("out_of_scope_for_p9bx") or [])
        and "remote execution" in list(scope.get("out_of_scope_for_p9bx") or [])
        and len(scope.get("rollback_conditions") or []) >= 6
    )


def p9bx_required_proofs_ready(proofs: dict[str, Any]) -> bool:
    proof_rows = list(proofs.get("proofs") or [])
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
        proofs.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bx_required_fresh_proofs.v1"
        and proofs.get("scope_definition_only") is True
        and proofs.get("fresh_proofs_required_before_any_future_order_submission") is True
        and proofs.get("p9bx_satisfies_fresh_proofs") is False
        and set(proof_by_id) == set(required)
        and all(
            int(dict(proof_by_id[key]).get("max_age_seconds") or 0) == max_age
            for key, max_age in required.items()
        )
    )


def p9bx_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bx_non_authorization.v1"
        and authorizations.get("define_live_order_gate_scope") is True
        and authorizations.get("prepare_future_live_order_gate_review_package") is True
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


def p9bx_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bx_control_boundary.v1"
        and control.get("scope") == "live_order_gate_scope_definition_only"
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


def build_canary_order_terms(scope: dict[str, Any]) -> dict[str, Any]:
    canary = dict(scope.get("canary_terms") or {})
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9by_canary_order_terms.v1",
        "package_only": True,
        "symbol": canary.get("symbol"),
        "side": canary.get("side"),
        "risk_ceiling_usdt": canary.get("risk_ceiling_usdt"),
        "max_notional_usdt": canary.get("max_notional_usdt"),
        "max_orders_per_cycle": canary.get("max_orders_per_cycle"),
        "max_symbols_per_cycle": canary.get("max_symbols_per_cycle"),
        "order_type": canary.get("order_type"),
        "time_in_force": canary.get("time_in_force"),
        "market_orders_allowed": False,
        "post_only_required": True,
        "maker_only_required": True,
        "limit_order_must_not_cross_spread": True,
        "candidate_delta_source": "distance_to_high_60_contribution_only",
        "would_submit_order": False,
    }


def build_fresh_proof_collection_plan(proofs: dict[str, Any]) -> dict[str, Any]:
    plan_rows = []
    for item in list(proofs.get("proofs") or []):
        proof_id = str(item.get("proof_id"))
        plan_rows.append(
            {
                "proof_id": proof_id,
                "required": True,
                "max_age_seconds": int(item.get("max_age_seconds") or 0),
                "collection_status_in_p9by": "not_collected",
                "required_before": item.get("required_before"),
                "purpose": item.get("purpose"),
            }
        )
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9by_fresh_proof_collection_plan.v1",
        "package_only": True,
        "fresh_proofs_collected_in_p9by": False,
        "remote_account_read_performed": False,
        "order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "proofs": plan_rows,
    }


def build_approval_checklist(scope: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9by_approval_checklist.v1",
        "package_only": True,
        "approval_items": [
            {
                "item": "all_required_fresh_proofs_present_and_unexpired",
                "required_for_live_order_gate": True,
                "satisfied_in_p9by": False,
            },
            {
                "item": "candidate_target_plan_hash_bound_to_executor_input",
                "required_for_live_order_gate": True,
                "satisfied_in_p9by": False,
            },
            {
                "item": "baseline_candidate_diff_dth60_only",
                "required_for_live_order_gate": True,
                "satisfied_in_p9by": False,
            },
            {
                "item": "post_only_limit_price_does_not_cross_spread",
                "required_for_live_order_gate": True,
                "satisfied_in_p9by": False,
            },
            {
                "item": "kill_switch_and_rollback_readback_available",
                "required_for_live_order_gate": True,
                "satisfied_in_p9by": False,
            },
            {
                "item": "final_owner_live_order_gate_approval",
                "required_for_live_order_gate": True,
                "satisfied_in_p9by": False,
            },
        ],
        "rollback_conditions": list(scope.get("rollback_conditions") or []),
    }


def build_review_package(
    *,
    run_id: str,
    p9bx_summary_path: Path,
    p9bx_summary: dict[str, Any],
    scope: dict[str, Any],
    fresh_plan: dict[str, Any],
    canary_terms: dict[str, Any],
    approval_checklist: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9by_review_package.v1",
        "run_id": run_id,
        "package_only": True,
        "source_p9bx_summary": evidence_file(p9bx_summary_path),
        "future_gate_name": "candidate_live_order_gate",
        "package_decision": "prepared_for_future_review_only",
        "canary_order_terms": canary_terms,
        "fresh_proof_collection_plan": fresh_plan,
        "approval_checklist": approval_checklist,
        "future_gate_may_discuss": list(scope.get("future_gate_may_discuss") or []),
        "future_gate_may_not_skip": list(scope.get("future_gate_may_not_skip") or []),
        "baseline_target_plan_sha256": p9bx_summary.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9bx_summary.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9bx_summary.get(
            "only_distance_to_high_60_contribution_changed"
        ),
        "fresh_proofs_collected_in_p9by": False,
        "live_order_gate_approved": False,
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }


def build_p9by_live_order_gate_review_package(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9by" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9bx_summary_path = latest_p9bx_summary(args)
    p9bx = load_optional(p9bx_summary_path)
    scope_path = source_output_path(p9bx, "live_order_gate_scope")
    proofs_path = source_output_path(p9bx, "required_fresh_proofs")
    matrix_path = source_output_path(p9bx, "non_authorization")
    control_path = source_output_path(p9bx, "control_boundary_readback")
    scope = load_optional(scope_path)
    proofs = load_optional(proofs_path)
    p9bx_matrix = load_optional(matrix_path)
    p9bx_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9BY_DECISION
    checks = {
        "owner_decision_p9by_package_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9bx_summary_exists": bool(p9bx),
        "p9bx_summary_ready_for_review_package": p9bx_summary_ready(p9bx),
        "p9bx_scope_ready": p9bx_scope_ready(scope),
        "p9bx_required_fresh_proofs_ready": p9bx_required_proofs_ready(proofs),
        "p9bx_non_authorization_ready": p9bx_non_authorization_ready(p9bx_matrix),
        "p9bx_control_boundary_ready": p9bx_control_ready(p9bx_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    canary_terms = build_canary_order_terms(scope)
    fresh_plan = build_fresh_proof_collection_plan(proofs)
    approval_checklist = build_approval_checklist(scope)
    review_package = build_review_package(
        run_id=run_id,
        p9bx_summary_path=p9bx_summary_path,
        p9bx_summary=p9bx,
        scope=scope,
        fresh_plan=fresh_plan,
        canary_terms=canary_terms,
        approval_checklist=approval_checklist,
    )
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9by_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "prepare_live_order_gate_review_package_only_no_order_no_execution",
        "recorded_at_utc": iso_z(now),
        "review_package_preparation_approved": owner_decision_ok,
        "fresh_proof_collection_approved": False,
        "live_order_gate_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9by_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "prepare_live_order_gate_review_package": ready,
            "review_live_order_gate_review_package": ready,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9by_control_boundary.v1",
        "run_id": run_id,
        "scope": "live_order_gate_review_package_preparation_only",
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
    package_path = proof_root / "live_order_gate_review_package.json"
    canary_path = proof_root / "canary_order_terms.json"
    fresh_plan_path = proof_root / "fresh_proof_collection_plan.json"
    approval_path = proof_root / "approval_checklist.json"
    non_auth_path = proof_root / "non_authorization.json"
    control_path_out = proof_root / "control.json"
    summary_path = root / "summary.json"
    report_path = root / "p9by_live_order_gate_review_package.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "live_order_gate_review_package": str(package_path),
        "canary_order_terms": str(canary_path),
        "fresh_proof_collection_plan": str(fresh_plan_path),
        "approval_checklist": str(approval_path),
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
        "p9by_live_order_gate_review_package_prepared": ready,
        "p9bx_sufficient_for_review_package": p9bx_summary_ready(p9bx),
        "eligible_for_future_p9bz_package_review": ready,
        "eligible_for_future_fresh_remote_proof_collection": False,
        "eligible_for_future_live_order_submission": False,
        "fresh_proofs_collected_in_p9by": False,
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
        "allowed_next_gate": P9BZ_GATE,
        "allowed_next_gate_scope": P9BZ_SCOPE,
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
        "required_fresh_proof_count": len(fresh_plan["proofs"]),
        "source_p9bx_summary_sha256": evidence_file(p9bx_summary_path).get("sha256", ""),
        "baseline_target_plan_sha256": p9bx.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9bx.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9bx.get(
            "only_distance_to_high_60_contribution_changed"
        ),
        "source_evidence": {
            "phase9bx_summary": evidence_file(p9bx_summary_path),
            "phase9bx_live_order_gate_scope": evidence_file(scope_path),
            "phase9bx_required_fresh_proofs": evidence_file(proofs_path),
            "phase9bx_non_authorization": evidence_file(matrix_path),
            "phase9bx_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(package_path, review_package)
    write_json(canary_path, canary_terms)
    write_json(fresh_plan_path, fresh_plan)
    write_json(approval_path, approval_checklist)
    write_json(non_auth_path, non_authorization)
    write_json(control_path_out, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary, review_package), encoding="utf-8")

    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any], package: dict[str, Any]) -> str:
    canary = dict(package.get("canary_order_terms") or {})
    lines = [
        "# hv_balanced DTH60/CoinGlass P9BY Live-Order Gate Review Package",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9BY prepares the future live-order gate review package only. It does not collect fresh proofs, approve live orders, execute the candidate, replace target plans, mutate executor input, invoke supervisor/timer/remote paths, or submit orders.",
        "",
        "## Package Boundary",
        "",
        "```text",
        f"p9by_live_order_gate_review_package_prepared = {str(bool(summary['p9by_live_order_gate_review_package_prepared'])).lower()}",
        "fresh_proofs_collected_in_p9by = false",
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
        "## Canary Terms For Future Review",
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
        "would_submit_order = false",
        "```",
        "",
        "## Required Fresh Proofs To Collect Later",
        "",
    ]
    fresh_plan = dict(package.get("fresh_proof_collection_plan") or {})
    for proof in list(fresh_plan.get("proofs") or []):
        lines.append(
            f"- `{proof['proof_id']}` max_age_seconds={proof['max_age_seconds']} status={proof['collection_status_in_p9by']}"
        )
    lines.extend(
        [
            "",
            "## Allowed Next Gate",
            "",
            "```text",
            str(summary["allowed_next_gate"]),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p9by_live_order_gate_review_package(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
