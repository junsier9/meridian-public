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
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9cx_execute_fresh_proof_no_order_replacement_pre_order_control_big_package import (  # noqa: E402
    CONTRACT_VERSION as P9CX_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9CX_PARENT,
    P9CY_GATE,
    P9CY_SCOPE,
    p9co_summary_ready_for_p9cx,
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
    "hv_balanced_dth60_coinglass_phase9cy_review_p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package.v1"
)
APPROVE_P9CY_DECISION = (
    "approve_p9cy_review_p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_only_no_order_no_candidate_no_executor_or_timer_change"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9cy_review_p9cx_big_package"
P9CZ_GATE = "P9CZ_final_owner_live_order_decision_gate_only_if_separately_requested"
P9CZ_SCOPE = (
    "collect_explicit_final_owner_live_order_decision_for_candidate_executor_path_and_single_post_only_canary_terms"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review retained P9CX big-package evidence only. P9CY decides whether "
            "the P9CX retained package is sufficient to enter a future final "
            "live-order decision gate. It does not SSH, read Binance, collect "
            "fresh proofs, call order-test endpoints, invoke supervisor/timer "
            "paths, execute the candidate, mutate executor input or target "
            "plans, remote sync, cancel orders, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9cx-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9CY_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default=(
            "user_chat:p9cy_review_p9cx_retained_evidence_before_final_live_order_decision"
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


def latest_p9cx_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9cx_summary).strip():
        return resolve_path(args.phase9cx_summary)
    return latest_match(P9CX_PARENT, "*/summary.json")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def p9cx_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9CX_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get(
            "p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_ready"
        )
        is True
        and summary.get("p9cw_sufficient_for_p9cx_big_package_execution") is True
        and summary.get("fresh_proof_collection_performed_in_p9cx") is True
        and summary.get("fresh_remote_account_read_performed") is True
        and summary.get("fresh_order_book_read_performed") is True
        and summary.get("exchange_filter_read_performed") is True
        and summary.get("pit_safe_v2v3_account_proof_ready") is True
        and summary.get("account_blocker_cleared_by_p9cx") is True
        and summary.get("read_only_fresh_proofs_ready") is True
        and summary.get("no_order_candidate_target_plan_replacement_dry_run_ready")
        is True
        and summary.get("candidate_target_plan_replacement_semantics_proven") is True
        and summary.get("same_risk_paired_target_plan_binding") is True
        and summary.get("distance_to_high_60_only_delta") is True
        and summary.get("only_distance_to_high_60_contribution_changed") is True
        and summary.get("pre_order_control_readback_ready") is True
        and summary.get("post_order_observation_plan_prepared") is True
        and summary.get("remote_control_boundary_unchanged") is True
        and summary.get("final_owner_live_order_gate_approval_collected") is False
        and summary.get("explicit_final_owner_live_order_decision_collected") is False
        and summary.get("p9cx_satisfies_final_owner_live_order_gate") is False
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
        and summary.get("order_test_endpoint_called") is False
        and int_zero(summary, "remote_files_written")
        and summary.get("remote_sync_performed") is False
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "orders_canceled")
        and int_zero(summary, "fill_count")
        and int_zero(summary, "trade_count")
        and int(summary.get("fresh_final_decision_evidence_total_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE)
        and int(summary.get("fresh_final_decision_evidence_read_only_or_plan_ready_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE) - 2
        and int(summary.get("fresh_final_decision_evidence_not_collected_by_design_count") or 0)
        == 2
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
        and summary.get("allowed_next_gate") == P9CY_GATE
        and summary.get("allowed_next_gate_scope") == P9CY_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def proof_bundle_ready(bundle: dict[str, Any]) -> bool:
    rows = [dict(row) for row in list(bundle.get("proof_rows") or [])]
    by_id = {str(row.get("proof_id")): row for row in rows}
    not_collected = {
        key for key, row in by_id.items() if row.get("status") == "not_collected_by_design"
    }
    ready_or_plan = {
        key
        for key, row in by_id.items()
        if row.get("status") in {"ready", "plan_prepared_not_executed"}
    }
    return (
        bundle.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cx_fresh_final_decision_proof_bundle.v1"
        and set(by_id) == set(EXPECTED_FINAL_EVIDENCE)
        and int(bundle.get("proof_row_count") or 0) == len(EXPECTED_FINAL_EVIDENCE)
        and int(bundle.get("read_only_or_plan_ready_count") or 0)
        == len(EXPECTED_FINAL_EVIDENCE) - 2
        and int(bundle.get("not_collected_by_design_count") or 0) == 2
        and bundle.get("all_read_only_fresh_proofs_ready") is True
        and bundle.get("pre_order_control_readback_ready") is True
        and bundle.get("post_order_observation_plan_prepared") is True
        and bundle.get("final_owner_live_order_gate_approval_collected") is False
        and bundle.get("p9cx_satisfies_final_owner_live_order_gate") is False
        and not_collected
        == {"final_owner_live_order_gate_approval", "explicit_final_owner_live_order_decision"}
        and "post_order_observation_and_rollback_plan" in ready_or_plan
        and all(
            int(by_id[key].get("max_age_seconds") or 0) == max_age
            for key, max_age in EXPECTED_FINAL_EVIDENCE.items()
        )
    )


def pre_order_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cx_pre_order_control_readback.v1"
        and control.get("pre_order_control_readback_ready") is True
        and control.get("source_p9cw_scope_ready") is True
        and control.get("source_p9co_read_only_fresh_proofs_ready") is True
        and control.get("executor_input_expected") == "baseline_only"
        and control.get("candidate_output_expected") == "shadow_or_proof_artifacts_only"
        and control.get("final_owner_live_order_gate_approval_collected") is False
        and control.get("live_order_submission_authorized") is False
        and control.get("candidate_enter_executor_target_plan_path_authorized") is False
        and control.get("candidate_execution_authorized") is False
        and control.get("target_plan_replacement_authorized") is False
        and control.get("executor_input_mutation_authorized") is False
        and control.get("timer_path_load_authorized") is False
        and control.get("supervisor_invocation_authorized") is False
        and control.get("order_test_endpoint_called") is False
        and int_zero(control, "remote_files_written")
        and control.get("remote_sync_performed") is False
        and int_zero(control, "orders_submitted")
        and int_zero(control, "orders_canceled")
        and int_zero(control, "fill_count")
        and int_zero(control, "trade_count")
        and bool(control.get("baseline_target_plan_sha256"))
        and bool(control.get("candidate_target_plan_sha256"))
        and control.get("baseline_target_plan_sha256")
        != control.get("candidate_target_plan_sha256")
        and control.get("only_distance_to_high_60_contribution_changed") is True
    )


def p9co_source_binding_ready(binding: dict[str, Any]) -> bool:
    return (
        binding.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cx_source_binding.v1"
        and dict(binding.get("source_p9cw_summary") or {}).get("exists") is True
        and dict(binding.get("source_p9cw_scope") or {}).get("exists") is True
        and dict(binding.get("embedded_p9co_summary") or {}).get("exists") is True
        and binding.get("embedded_p9co_status") == "ready"
        and int(binding.get("embedded_p9co_exit_code") or 0) == 0
        and not binding.get("embedded_p9co_exception")
        and bool(binding.get("baseline_target_plan_sha256"))
        and bool(binding.get("candidate_target_plan_sha256"))
        and binding.get("baseline_target_plan_sha256")
        != binding.get("candidate_target_plan_sha256")
        and binding.get("same_risk_paired_target_plan_binding") is True
        and binding.get("only_distance_to_high_60_contribution_changed") is True
    )


def p9cx_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cx_non_authorization.v1"
        and authorizations.get("execute_p9cx_big_package") is True
        and authorizations.get("fresh_read_only_remote_proof_collection") is True
        and authorizations.get("no_order_candidate_target_plan_replacement_dry_run")
        is True
        and authorizations.get("pre_order_control_readback") is True
        and authorizations.get("order_test_endpoint") is False
        and authorizations.get("remote_files_written") is False
        and authorizations.get("remote_sync") is False
        and authorizations.get("supervisor_invocation") is False
        and authorizations.get("timer_path_load") is False
        and authorizations.get("production_timer_service_load") is False
        and authorizations.get("actual_candidate_executor_target_path_entry") is False
        and authorizations.get("candidate_execution") is False
        and authorizations.get("live_order_submission") is False
        and authorizations.get("actual_target_plan_replacement") is False
        and authorizations.get("actual_executor_input_mutation") is False
        and authorizations.get("live_config_mutation") is False
        and authorizations.get("operator_state_mutation") is False
        and authorizations.get("timer_or_service_mutation") is False
        and authorizations.get("stage_governance_change") is False
    )


def p9cx_control_boundary_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9cx_control_boundary.v1"
        and control.get("scope")
        == "fresh_proof_no_order_replacement_pre_order_control_big_package"
        and control.get("fresh_remote_proof_collection_performed") is True
        and control.get("fresh_remote_account_read_performed") is True
        and control.get("fresh_order_book_read_performed") is True
        and control.get("exchange_filter_read_performed") is True
        and control.get("pre_order_control_readback_performed") is True
        and control.get("order_test_endpoint_called") is False
        and int_zero(control, "remote_files_written")
        and control.get("remote_sync_performed") is False
        and control.get("entered_timer_path") is False
        and control.get("ran_supervisor") is False
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


def command_records_ready(records: dict[str, Any]) -> bool:
    commands = [dict(item) for item in list(records.get("commands") or [])]
    labels = [str(item.get("label")) for item in commands]
    command_text = "\n".join(" ".join(map(str, item.get("args") or [])) for item in commands)
    forbidden = ("scp ", "/fapi/v1/order/test", "systemctl start", "systemctl enable")
    return (
        labels
        == [
            "pre_control_snapshot",
            "remote_stdout_pit_safe_v2v3_account_collector",
            "remote_stdout_market_and_fingerprint_collector",
            "post_control_snapshot",
        ]
        and all(int(item.get("returncode") or 0) == 0 for item in commands)
        and not any(token in command_text for token in forbidden)
    )


def build_sufficiency_review(checks: dict[str, bool], *, run_id: str) -> dict[str, Any]:
    ready = all(checks.values())
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cy_p9cx_sufficiency_review.v1",
        "run_id": run_id,
        "review_only": True,
        "p9cx_retained_evidence_sufficient_for_p9cy_review": ready,
        "p9cx_big_package_sufficient_for_final_live_order_decision_discussion": ready,
        "p9cx_big_package_sufficient_for_live_order_submission": False,
        "p9cx_big_package_sufficient_for_candidate_execution": False,
        "p9cx_satisfies_final_owner_live_order_gate": False,
        "final_owner_live_order_gate_approval_collected": False,
        "explicit_final_owner_live_order_decision_collected": False,
        "future_gate": P9CZ_GATE,
        "future_gate_scope": P9CZ_SCOPE,
        "future_gate_must_be_separately_requested": True,
        "checks": checks,
    }


def build_final_decision_gap_matrix(
    proof_bundle: dict[str, Any],
    *,
    run_id: str,
) -> dict[str, Any]:
    rows = [dict(row) for row in list(proof_bundle.get("proof_rows") or [])]
    matrix_rows = []
    for row in rows:
        proof_id = str(row.get("proof_id"))
        status = str(row.get("status"))
        matrix_rows.append(
            {
                "evidence_id": proof_id,
                "status_in_p9cx": status,
                "ready_for_final_decision_discussion": status
                in {"ready", "plan_prepared_not_executed"},
                "remaining_gap_before_final_live_order_decision": status
                == "not_collected_by_design",
            }
        )
    remaining = [
        row["evidence_id"]
        for row in matrix_rows
        if row["remaining_gap_before_final_live_order_decision"]
    ]
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cy_final_decision_gap_matrix.v1",
        "run_id": run_id,
        "review_only": True,
        "evidence_rows": matrix_rows,
        "evidence_total_count": len(EXPECTED_FINAL_EVIDENCE),
        "ready_or_plan_count": len(EXPECTED_FINAL_EVIDENCE) - len(remaining),
        "remaining_gap_count": len(remaining),
        "remaining_gap_ids": remaining,
        "p9cx_big_package_sufficient_for_final_live_order_decision_discussion": (
            set(remaining)
            == {"final_owner_live_order_gate_approval", "explicit_final_owner_live_order_decision"}
        ),
        "p9cx_satisfies_final_owner_live_order_gate": False,
    }


def build_phase9cy(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9cy" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9cx_path = latest_p9cx_summary(args)
    p9cx = load_optional(p9cx_path)
    proof_bundle_path = source_output_path(p9cx, "fresh_final_decision_proof_bundle")
    pre_order_path = source_output_path(p9cx, "pre_order_control_readback")
    source_binding_path = source_output_path(p9cx, "p9co_source_binding")
    non_auth_path = source_output_path(p9cx, "non_authorization")
    control_path = source_output_path(p9cx, "control_boundary_readback")
    embedded_p9co_path = source_output_path(p9cx, "embedded_p9co_summary")
    proof_bundle = load_optional(proof_bundle_path)
    pre_order = load_optional(pre_order_path)
    source_binding = load_optional(source_binding_path)
    non_auth = load_optional(non_auth_path)
    control = load_optional(control_path)
    embedded_p9co = load_optional(embedded_p9co_path)
    command_records_path = source_output_path(embedded_p9co, "command_records")
    command_records = load_optional(command_records_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)
    owner_decision_ok = str(args.owner_decision) == APPROVE_P9CY_DECISION

    checks = {
        "owner_decision_p9cy_review_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9cx_summary_exists": bool(p9cx),
        "p9cx_summary_ready_for_p9cy_review": p9cx_summary_ready(p9cx),
        "p9cx_proof_bundle_ready": proof_bundle_ready(proof_bundle),
        "p9cx_pre_order_control_ready": pre_order_control_ready(pre_order),
        "p9cx_source_binding_ready": p9co_source_binding_ready(source_binding),
        "p9cx_non_authorization_ready": p9cx_non_authorization_ready(non_auth),
        "p9cx_control_boundary_ready": p9cx_control_boundary_ready(control),
        "embedded_p9co_summary_ready_for_p9cx": p9co_summary_ready_for_p9cx(
            embedded_p9co
        ),
        "embedded_p9co_command_records_ready": command_records_ready(command_records),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cy_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "review_p9cx_big_package_for_final_live_order_decision_discussion_only",
        "recorded_at_utc": iso_z(now),
        "p9cy_review_only_approved": owner_decision_ok,
        "future_final_live_order_decision_gate_request_allowed_if_ready": ready,
        "final_owner_live_order_gate_approval_collected": False,
        "live_order_submission_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
    }
    sufficiency_review = build_sufficiency_review(checks, run_id=run_id)
    gap_matrix = build_final_decision_gap_matrix(proof_bundle, run_id=run_id)
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cy_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "review_p9cx_retained_big_package": owner_decision_ok,
            "allow_future_p9cz_final_owner_live_order_decision_gate_request": ready,
            "collect_final_owner_live_order_decision_in_p9cy": False,
            "final_owner_live_order_gate_approval": False,
            "fresh_remote_proof_collection": False,
            "fresh_remote_account_read": False,
            "fresh_order_book_read": False,
            "exchange_filter_read": False,
            "order_test_endpoint": False,
            "remote_execution": False,
            "remote_sync": False,
            "remote_file_write": False,
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
    control_readback = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9cy_control_boundary.v1",
        "run_id": run_id,
        "scope": "review_p9cx_retained_big_package_only",
        "ssh_invoked": False,
        "fresh_remote_proof_collection_performed_in_p9cy": False,
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
        "p9cx_sufficiency_review": str(proof_root / "p9cx_sufficiency_review.json"),
        "final_decision_gap_matrix": str(
            proof_root / "final_decision_gap_matrix.json"
        ),
        "non_authorization": str(proof_root / "non_authorization.json"),
        "control_boundary_readback": str(proof_root / "control_boundary_readback.json"),
        "report": str(root / "p9cy_review_p9cx_big_package.md"),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "p9cy_review_p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_ready": ready,
        "p9cx_retained_evidence_sufficient_for_p9cy_review": ready,
        "p9cx_big_package_sufficient_for_final_live_order_decision_discussion": ready,
        "p9cx_big_package_sufficient_for_live_order_submission": False,
        "p9cx_big_package_sufficient_for_candidate_execution": False,
        "p9cx_satisfies_final_owner_live_order_gate": False,
        "final_owner_live_order_gate_approval_collected": False,
        "explicit_final_owner_live_order_decision_collected": False,
        "fresh_final_decision_evidence_total_count": len(EXPECTED_FINAL_EVIDENCE),
        "fresh_final_decision_evidence_read_only_or_plan_ready_count": gap_matrix[
            "ready_or_plan_count"
        ],
        "fresh_final_decision_evidence_not_collected_by_design_count": gap_matrix[
            "remaining_gap_count"
        ],
        "remaining_gap_ids_before_final_live_order_decision": gap_matrix[
            "remaining_gap_ids"
        ],
        "eligible_for_future_p9cz_final_owner_live_order_decision_gate": ready,
        "eligible_for_future_live_order_submission": False,
        "eligible_for_future_candidate_execution": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "fresh_remote_proof_collection_performed_in_p9cy": False,
        "fresh_remote_account_read_performed": False,
        "fresh_order_book_read_performed": False,
        "exchange_filter_read_performed": False,
        "order_test_endpoint_called": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
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
        "baseline_target_plan_sha256": p9cx.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9cx.get("candidate_target_plan_sha256"),
        "only_distance_to_high_60_contribution_changed": p9cx.get(
            "only_distance_to_high_60_contribution_changed"
        )
        is True,
        "allowed_next_gate": P9CZ_GATE,
        "allowed_next_gate_scope": P9CZ_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9cx_summary": evidence_file(p9cx_path),
            "phase9cx_fresh_final_decision_proof_bundle": evidence_file(
                proof_bundle_path
            ),
            "phase9cx_pre_order_control_readback": evidence_file(pre_order_path),
            "phase9cx_p9co_source_binding": evidence_file(source_binding_path),
            "phase9cx_non_authorization": evidence_file(non_auth_path),
            "phase9cx_control_boundary": evidence_file(control_path),
            "embedded_p9co_summary": evidence_file(embedded_p9co_path),
            "embedded_p9co_command_records": evidence_file(command_records_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "checks": checks,
        "output_files": output_files,
    }

    write_json(Path(output_files["owner_decision_record"]), owner_record)
    write_json(Path(output_files["p9cx_sufficiency_review"]), sufficiency_review)
    write_json(Path(output_files["final_decision_gap_matrix"]), gap_matrix)
    write_json(Path(output_files["non_authorization"]), non_authorization)
    write_json(Path(output_files["control_boundary_readback"]), control_readback)
    write_json(Path(output_files["summary"]), summary)
    Path(output_files["report"]).write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if ready else 2


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hv_balanced DTH60/CoinGlass P9CY Review P9CX Big Package",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9CY reviews retained P9CX evidence only. It decides whether the P9CX big package is sufficient to enter a future final live-order decision gate. It does not collect a final owner decision, authorize live order submission, execute the candidate, replace target plans, mutate executor input, or invoke timer/supervisor paths.",
        "",
        "## Review Result",
        "",
        "```text",
        "p9cy_review_p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_ready = "
        f"{str(bool(summary['p9cy_review_p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_ready'])).lower()}",
        "p9cx_big_package_sufficient_for_final_live_order_decision_discussion = "
        f"{str(bool(summary['p9cx_big_package_sufficient_for_final_live_order_decision_discussion'])).lower()}",
        "p9cx_big_package_sufficient_for_live_order_submission = false",
        "final_owner_live_order_gate_approval_collected = false",
        "explicit_final_owner_live_order_decision_collected = false",
        f"remaining_gap_ids_before_final_live_order_decision = {', '.join(summary['remaining_gap_ids_before_final_live_order_decision'])}",
        "live_order_submission_authorized = false",
        "candidate_execution_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
        "orders_submitted = 0",
        "fill_count = 0",
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
    summary, exit_code = build_phase9cy(parse_args(argv))
    print(
        "p9cy_review_p9cx_big_package_ready="
        + str(
            bool(
                summary[
                    "p9cy_review_p9cx_fresh_proof_no_order_replacement_pre_order_control_big_package_ready"
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
