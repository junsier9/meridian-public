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
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cv_review_p9cu_final_owner_live_order_decision_review_package_after_p9ct import (  # noqa: E402
    CONTRACT_VERSION as P9CV_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CV_PARENT,
    P9CW_GATE,
    P9CW_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9cw_define_final_owner_live_order_decision_gate_scope_after_p9cv.v1"
)
APPROVE_P9CW_DECISION = (
    "approve_p9cw_define_final_owner_live_order_decision_gate_scope_after_p9cv_only_no_order_no_candidate_no_executor_or_timer_change"
)
DEFAULT_OUTPUT_PARENT = (
    "artifacts/live_trading/p9cw_final_owner_live_order_decision_gate_scope_after_p9cv"
)
P9CX_GATE = (
    "P9CX_execute_fresh_proof_no_order_replacement_pre_order_control_big_package_only_if_separately_requested"
)
P9CX_SCOPE = (
    "execute_fresh_proof_collection_plus_no_order_candidate_replacement_dry_run_plus_pre_order_control_readback_no_order"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Define the P9CX big-package scope after retained P9CV review. "
            "P9CW is scope-definition-only: it does not SSH, read Binance, "
            "collect fresh proofs, call order-test endpoints, run supervisor or "
            "timer paths, execute the candidate, mutate executor input or target "
            "plans, remote sync, cancel orders, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cv-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CW_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9cw_define_final_owner_live_order_decision_gate_scope_after_p9cv_big_p9cx_package"
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


def latest_p9cv_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cv_summary).strip():
        return resolve_path(args.phase9cv_summary)
    return latest_match(P9CV_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9cv_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9CV_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get(
            "p9cv_review_p9cu_final_owner_live_order_decision_review_package_after_p9ct_ready"
        )
        is True
        and summary.get("p9cu_package_sufficient_for_p9cv_review") is True
        and summary.get("p9cu_package_sufficient_for_future_p9cw_scope_definition")
        is True
        and summary.get("p9cu_package_sufficient_for_live_order_submission") is False
        and summary.get("p9cu_package_sufficient_for_candidate_execution") is False
        and summary.get("p9cu_package_sufficient_for_candidate_executor_path_entry")
        is False
        and summary.get("p9cu_satisfies_final_owner_live_order_gate") is False
        and summary.get("final_owner_live_order_gate_approval_collected") is False
        and summary.get("final_owner_decision_collected_in_p9cu") is False
        and summary.get("final_decision_evidence_collected_in_p9cu") is False
        and summary.get("fresh_proofs_collected_in_p9cu") is False
        and int(summary.get("required_final_decision_evidence_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE)
        and int(summary.get("remaining_evidence_gap_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE)
        and int(summary.get("decision_checklist_unsatisfied_count") or 0) == 8
        and summary.get("eligible_for_future_p9cw_scope_definition") is True
        and summary.get("allowed_next_gate") == P9CW_GATE
        and summary.get("allowed_next_gate_scope") == P9CW_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
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
        and bool(summary.get("baseline_target_plan_sha256"))
        and bool(summary.get("candidate_target_plan_sha256"))
        and summary.get("baseline_target_plan_sha256")
        != summary.get("candidate_target_plan_sha256")
        and summary.get("only_distance_to_high_60_contribution_changed") is True
    )


def p9cv_sufficiency_ready(review: dict[str, Any]) -> bool:
    checks = dict(review.get("checks") or {})
    return (
        review.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cv_p9cu_sufficiency_review.v1"
        and review.get("review_only") is True
        and review.get("p9cu_package_sufficient_for_p9cv_review") is True
        and review.get("p9cu_package_sufficient_for_future_p9cw_scope_definition")
        is True
        and review.get("p9cu_package_sufficient_for_live_order_submission") is False
        and review.get("p9cu_satisfies_final_owner_live_order_gate") is False
        and review.get("final_owner_live_order_gate_approval_collected") is False
        and review.get("final_decision_evidence_collected_in_p9cu") is False
        and review.get("fresh_proofs_collected_in_p9cu") is False
        and review.get("final_decision_actionable_items_satisfied") is False
        and review.get("future_gate") == P9CW_GATE
        and review.get("future_gate_scope") == P9CW_SCOPE
        and review.get("future_gate_must_be_separately_requested") is True
        and bool(checks)
        and all(value is True for value in checks.values())
    )


def p9cv_gap_matrix_ready(matrix: dict[str, Any]) -> bool:
    evidence_rows = [dict(row) for row in list(matrix.get("evidence_rows") or [])]
    checklist_rows = [dict(row) for row in list(matrix.get("checklist_rows") or [])]
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cv_final_decision_gap_matrix.v1"
        and matrix.get("run_scope") == "review_p9cu_package_only"
        and matrix.get("p9cu_package_sufficient_for_p9cv_review") is True
        and matrix.get("p9cu_package_sufficient_for_future_p9cw_scope_definition")
        is True
        and matrix.get("p9cu_package_sufficient_for_live_order_submission") is False
        and matrix.get("p9cu_satisfies_final_owner_live_order_gate") is False
        and {str(row.get("evidence_id")) for row in evidence_rows}
        == set(EXPECTED_FINAL_EVIDENCE)
        and all(
            row.get("status_in_p9cu") == "packaged_for_future_decision_not_collected"
            and row.get("collection_status_in_p9cu") == "not_collected"
            and row.get("freshness_status_in_p9cu") == "not_evaluated"
            and row.get("remaining_gap_for_final_live_order_gate") is True
            for row in evidence_rows
        )
        and int(matrix.get("remaining_evidence_gap_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE)
        and len(checklist_rows) == 10
        and int(matrix.get("remaining_checklist_gap_count") or 0) == 8
    )


def p9cv_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cv_non_authorization.v1"
        and authorizations.get("review_p9cu_final_owner_live_order_decision_review_package")
        is True
        and authorizations.get("allow_future_p9cw_scope_definition_request") is True
        and authorizations.get("define_p9cw_scope_in_p9cv") is False
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
        and authorizations.get("timer_path_load") is False
        and authorizations.get("production_timer_service_load") is False
        and authorizations.get("supervisor_invocation") is False
    )


def p9cv_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cv_control_boundary.v1"
        and control.get("scope")
        == "p9cu_retained_final_owner_live_order_decision_review_package_review_only"
        and control.get("ssh_invoked") is False
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
        and int_zero(control, "orders_submitted")
        and int_zero(control, "orders_canceled")
        and int_zero(control, "fill_count")
        and int_zero(control, "trade_count")
    )


def build_p9cx_scope(p9cv: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cw_p9cx_big_package_scope.v1",
        "scope_definition_only": True,
        "future_gate": P9CX_GATE,
        "future_gate_scope": P9CX_SCOPE,
        "future_gate_must_be_separately_requested": True,
        "p9cx_big_package_components": [
            "fresh_proof_collection",
            "no_order_candidate_target_plan_replacement_dry_run",
            "pre_order_control_boundary_readback",
        ],
        "p9cx_may_execute_only": [
            "stdout-only read-only remote account and market proof collection",
            "PIT-safe /fapi/v2/account.canTrade permission proof",
            "fresh position balance open-order order-history and trade-history fingerprints",
            "fresh order book and exchange filter readbacks",
            "local proof_artifacts-only no-order candidate target-plan replacement dry-run",
            "pre-order control-boundary readback and post-readback comparison",
            "proof artifact manifest and hash binding",
        ],
        "p9cx_may_not_execute": [
            "live order submission",
            "order-test endpoint call",
            "candidate execution",
            "actual target-plan replacement",
            "actual executor-input mutation",
            "timer path load",
            "production timer-service load",
            "supervisor invocation",
            "remote sync",
            "remote file write",
            "live config operator state or timer mutation",
            "Stage 4 automation approval",
        ],
        "required_fresh_final_decision_evidence": [
            {"evidence_id": key, "max_age_seconds": max_age, "required": True}
            for key, max_age in EXPECTED_FINAL_EVIDENCE.items()
        ],
        "baseline_target_plan_sha256": p9cv.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9cv.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9cv.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
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
        },
        "p9cw_satisfies_final_owner_live_order_gate": False,
        "live_order_submission_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
    }


def build_phase9cw(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cw" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cv_path = latest_p9cv_summary(args)
    p9cv = load_optional(p9cv_path)
    review_path = source_output_path(p9cv, "p9cu_sufficiency_review")
    gap_path = source_output_path(p9cv, "final_decision_gap_matrix")
    non_auth_path = source_output_path(p9cv, "non_authorization")
    control_path = source_output_path(p9cv, "control_boundary_readback")
    review = load_optional(review_path)
    gap_matrix = load_optional(gap_path)
    p9cv_non_auth = load_optional(non_auth_path)
    p9cv_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CW_DECISION

    checks = {
        "owner_decision_p9cw_scope_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cv_summary_exists": bool(p9cv),
        "p9cv_summary_ready_for_p9cw_scope": p9cv_summary_ready(p9cv),
        "p9cv_sufficiency_review_ready": p9cv_sufficiency_ready(review),
        "p9cv_gap_matrix_ready": p9cv_gap_matrix_ready(gap_matrix),
        "p9cv_non_authorization_ready": p9cv_non_authorization_ready(p9cv_non_auth),
        "p9cv_control_boundary_ready": p9cv_control_ready(p9cv_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    scope = build_p9cx_scope(p9cv)
    evidence_manifest = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cw_p9cx_required_evidence_manifest.v1",
        "scope_definition_only": True,
        "evidence_count": len(EXPECTED_FINAL_EVIDENCE),
        "evidence": scope["required_fresh_final_decision_evidence"],
        "all_evidence_must_be_freshly_collected_inside_p9cx": True,
        "retained_p9cv_package_evidence_is_not_fresh_final_decision_evidence": True,
    }
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cw_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "define_p9cx_big_package_scope_after_p9cv_only_no_order_no_candidate_no_executor_or_timer_change",
        "recorded_at_utc": iso_z(now),
        "p9cw_scope_definition_approved": owner_decision_ok,
        "future_p9cx_execution_request_allowed_if_scope_ready": ready,
        "fresh_remote_proof_collection_approved_in_p9cw": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cw_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "define_p9cx_big_package_scope": ready,
            "allow_future_p9cx_execution_request": ready,
            "execute_p9cx_in_p9cw": False,
            "fresh_remote_proof_collection": False,
            "fresh_remote_account_read": False,
            "fresh_order_book_read": False,
            "exchange_filter_read": False,
            "order_test_endpoint": False,
            "remote_execution": False,
            "remote_sync": False,
            "remote_file_write": False,
            "final_owner_live_order_gate_approval": False,
            "actual_candidate_executor_target_path_entry": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "actual_target_plan_replacement": False,
            "actual_executor_input_mutation": False,
            "timer_path_load": False,
            "production_timer_service_load": False,
            "supervisor_invocation": False,
            "stage_governance_change": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cw_control_boundary.v1",
        "run_id": run_id,
        "scope": "define_p9cx_big_package_scope_only",
        "ssh_invoked": False,
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
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }

    output_files = {
        "summary": str(root / "summary.json"),
        "owner_decision_record": str(root / "owner_decision_record.json"),
        "p9cx_big_package_scope": str(proof_root / "p9cx_big_package_scope.json"),
        "required_evidence_manifest": str(proof_root / "required_evidence_manifest.json"),
        "non_authorization": str(proof_root / "non_authorization.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "p9cw_define_p9cx_big_package_scope.md"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "p9cw_final_owner_live_order_decision_gate_scope_defined": ready,
        "p9cv_sufficient_for_p9cw_scope_definition": ready,
        "p9cx_big_package_scope_defined": ready,
        "p9cx_fresh_proof_collection_in_scope": True,
        "p9cx_no_order_candidate_replacement_dry_run_in_scope": True,
        "p9cx_pre_order_control_readback_in_scope": True,
        "required_fresh_final_decision_evidence_count": len(EXPECTED_FINAL_EVIDENCE),
        "fresh_proofs_collected_in_p9cw": False,
        "fresh_remote_proof_collection_approved_in_p9cw": False,
        "p9cw_satisfies_final_owner_live_order_gate": False,
        "eligible_for_future_p9cx_big_package_execution": ready,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "live_order_submission_authorized": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
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
        "baseline_target_plan_sha256": p9cv.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9cv.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9cv.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
        "allowed_next_gate": P9CX_GATE,
        "allowed_next_gate_scope": P9CX_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9cv_summary": evidence_file(p9cv_path),
            "phase9cv_sufficiency_review": evidence_file(review_path),
            "phase9cv_gap_matrix": evidence_file(gap_path),
            "phase9cv_non_authorization": evidence_file(non_auth_path),
            "phase9cv_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(Path(output_files["owner_decision_record"]), owner_record)
    write_json(Path(output_files["p9cx_big_package_scope"]), scope)
    write_json(Path(output_files["required_evidence_manifest"]), evidence_manifest)
    write_json(Path(output_files["non_authorization"]), non_authorization)
    write_json(Path(output_files["control_boundary_readback"]), control)
    write_json(Path(output_files["summary"]), summary)
    Path(output_files["report"]).write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CW Define P9CX Big-Package Scope",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CW defines the P9CX big-package scope only. It does not collect fresh proofs, read Binance, invoke supervisor/timer paths, execute the candidate, mutate executor input, replace target plans, or submit orders.",
        "",
        "## Scope Result",
        "",
        "```text",
        f"p9cx_fresh_proof_collection_in_scope = {str(summary['p9cx_fresh_proof_collection_in_scope']).lower()}",
        f"p9cx_no_order_candidate_replacement_dry_run_in_scope = {str(summary['p9cx_no_order_candidate_replacement_dry_run_in_scope']).lower()}",
        f"p9cx_pre_order_control_readback_in_scope = {str(summary['p9cx_pre_order_control_readback_in_scope']).lower()}",
        "fresh_proofs_collected_in_p9cw = false",
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
    ]
    if summary.get("blockers"):
        lines.extend(["", "## Blockers", "", *[f"- {item}" for item in summary["blockers"]]])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_phase9cw(parse_args(argv))
    print(
        "p9cw_final_owner_live_order_decision_gate_scope_defined="
        + str(bool(summary["p9cw_final_owner_live_order_decision_gate_scope_defined"])).lower()
    )
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
