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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9br_review_after_p9bq import (  # noqa: E402
    CONTRACT_VERSION as P9BR_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9BR_PARENT,
    P9BS_GATE,
    P9BS_SCOPE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bs_execution_path_scope_definition import (  # noqa: E402
    DEFAULT_OUTPUT_PARENT as P9BS_SCOPE_PARENT,
    p9bs_scope_ready_for_live_order_gate_review,
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


CONTRACT_VERSION = "hv_balanced_dth60_coinglass_phase9bs_live_order_gate_request.v2"
APPROVE_P9BS_LIVE_ORDER_DECISION = (
    "approve_p9bs_live_order_gate_candidate_executor_target_path_request"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/hv_balanced_dth60_p9bs_live_order_gate_request"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review a direct live-order gate request after P9BR. This reviewer is "
            "fail-closed unless the P9BR allowed P9BS scope-definition gate has "
            "executed and the project stage permits human-approved execution-manifest "
            "review. The script records requested live-order terms and proves no executor, "
            "target-plan, config, timer, supervisor, remote, or order mutation."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9br-summary", default="")
    parser.add_argument("--phase9bs-scope-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BS_LIVE_ORDER_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:single_live_order_gate_candidate_executor_target_path_request",
    )
    parser.add_argument("--risk-ceiling-usdt", default="")
    parser.add_argument("--max-notional-usdt", default="")
    parser.add_argument("--order-type", default="")
    parser.add_argument("--kill-switch", default="")
    parser.add_argument("--rollback-condition", action="append", default=[])
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root).strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_p9br_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9br_summary).strip():
        return resolve_path(args.phase9br_summary)
    return latest_match(P9BR_PARENT, "*/summary.json")


def latest_p9bs_scope_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bs_scope_summary).strip():
        return resolve_path(args.phase9bs_scope_summary)
    return latest_match(P9BS_SCOPE_PARENT, "*/summary.json")


def parse_positive_float(text: str) -> float | None:
    try:
        value = float(str(text).strip())
    except ValueError:
        return None
    return value if value > 0 else None


def p9br_ready_for_scope_only(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9BR_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9br_retained_evidence_review_ready") is True
        and summary.get("p9bq_retained_shadow_cycles_sufficient") is True
        and summary.get("sufficient_for_execution_path_change_discussion") is True
        and summary.get("allowed_next_gate") == P9BS_GATE
        and summary.get("allowed_next_gate_scope") == P9BS_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("execution_path_change_discussion_scope_definition_authorized") is False
        and summary.get("execution_path_change_implementation_authorized") is False
        and summary.get("execution_path_change_execution_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
    )


def build_p9bs_live_order_gate_request(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9bs_live_order_request" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9br_summary_path = latest_p9br_summary(args)
    p9br = load_optional(p9br_summary_path)
    p9bs_scope_summary_path = latest_p9bs_scope_summary(args)
    p9bs_scope = load_optional(p9bs_scope_summary_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9BS_LIVE_ORDER_DECISION
    p9br_scope_only_ready = p9br_ready_for_scope_only(p9br)
    p9bs_scope_ready = p9bs_scope_ready_for_live_order_gate_review(p9bs_scope)
    stage = str(project_profile.get("current_stage") or "")
    stage_allows_live_order = stage in {
        "stage_3_human_approved_execution",
        "stage_4_automated_execution",
    }
    p9br_authorizes_live_order_gate = p9br_scope_only_ready and p9bs_scope_ready
    risk_ceiling = parse_positive_float(args.risk_ceiling_usdt)
    max_notional = parse_positive_float(args.max_notional_usdt)
    order_type = str(args.order_type or "").strip().lower()
    kill_switch = str(args.kill_switch or "").strip()
    rollback_conditions = [str(item).strip() for item in args.rollback_condition if str(item).strip()]
    requested_terms_complete = (
        risk_ceiling is not None
        and max_notional is not None
        and max_notional <= risk_ceiling
        and order_type in {"limit", "post_only_limit", "ioc_limit", "reduce_only_limit"}
        and bool(kill_switch)
        and len(rollback_conditions) >= 1
    )

    checks = {
        "owner_decision_live_order_request_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "project_stage_allows_live_order": stage_allows_live_order,
        "p9br_summary_exists": bool(p9br),
        "p9br_ready_for_scope_only": p9br_scope_only_ready,
        "p9bs_scope_summary_exists": bool(p9bs_scope),
        "p9bs_scope_ready_for_live_order_gate_review": p9bs_scope_ready,
        "p9br_authorizes_live_order_gate": p9br_authorizes_live_order_gate,
        "scope_definition_gate_executed_before_live_order_gate": p9bs_scope_ready,
        "candidate_executor_target_path_preapproval_exists": False,
        "risk_ceiling_explicit_positive": risk_ceiling is not None,
        "max_notional_explicit_positive": max_notional is not None,
        "max_notional_within_risk_ceiling": (
            risk_ceiling is not None and max_notional is not None and max_notional <= risk_ceiling
        ),
        "order_type_supported_and_explicit": order_type
        in {"limit", "post_only_limit", "ioc_limit", "reduce_only_limit"},
        "kill_switch_explicit": bool(kill_switch),
        "rollback_conditions_explicit": len(rollback_conditions) >= 1,
        "requested_live_order_terms_complete": requested_terms_complete,
    }
    approved = False
    blockers = [key for key, value in checks.items() if not value]

    requested_terms = {
        "candidate_executor_target_plan_path_requested": True,
        "risk_ceiling_usdt": risk_ceiling,
        "max_notional_usdt": max_notional,
        "order_type": order_type,
        "kill_switch": kill_switch,
        "rollback_conditions": rollback_conditions,
        "terms_complete": requested_terms_complete,
    }

    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bs_live_order_owner_request.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "direct_live_order_gate_candidate_executor_target_path_request",
        "recorded_at_utc": iso_z(now),
        "requested_live_order_terms": requested_terms,
        "live_order_gate_approved": False,
        "candidate_executor_target_path_approved": False,
        "risk_limit_approved": False,
        "order_type_approved": False,
        "max_notional_approved": False,
        "kill_switch_approved": False,
        "rollback_conditions_approved": False,
        "candidate_execution_approved": False,
        "live_order_submission_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_config_mutation_approved": False,
        "operator_state_mutation_approved": False,
        "timer_or_service_mutation_approved": False,
        "remote_sync_approved": False,
        "remote_execution_approved": False,
        "repo_stage_change_approved": False,
    }

    required_remediation = []
    if not p9bs_scope_ready:
        required_remediation.append("execute a separate P9BS scope-definition gate only")
    if not stage_allows_live_order:
        required_remediation.append(
            "obtain a stage/profile governance change to a human-approved execution stage"
        )
    required_remediation.extend(
        [
            "produce an explicit candidate executor/target-plan integration proposal",
            "prove candidate target-plan replacement semantics in no-order dry run",
            "provide exact numeric risk ceiling and max notional",
            "provide exact order type and exchange-side constraints",
            "provide an operator-visible kill switch and rollback procedure",
            "run fresh account/position/order/fill fingerprint immediately before any live-order review",
        ]
    )
    decision_text = (
        "blocked: Stage and P9BS scope prerequisites are satisfied; remaining "
        "live-order terms and candidate executor/target-plan preapproval are still missing."
        if stage_allows_live_order and p9bs_scope_ready
        else (
            "blocked: P9BR permits only the P9BS scope-definition chain until that "
            "scope is executed, and the checked-in project stage must permit "
            "human-approved execution-manifest review."
        )
    )

    review_packet = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bs_live_order_request_review.v1",
        "run_id": run_id,
        "status": "blocked",
        "review_scope": "direct_live_order_gate_request_fail_closed",
        "requested_live_order_terms": requested_terms,
        "checks": checks,
        "blockers": blockers,
        "live_order_gate_approved": approved,
        "decision": decision_text,
        "required_remediation_before_any_live_order_gate": required_remediation,
    }

    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bs_live_order_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "record_live_order_gate_request": True,
            "live_order_gate_approval": False,
            "candidate_executor_target_path_entry": False,
            "risk_limit_approval": False,
            "order_type_approval": False,
            "max_notional_approval": False,
            "kill_switch_approval": False,
            "rollback_conditions_approval": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "target_plan_replacement": False,
            "executor_input_mutation": False,
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

    control_boundary = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bs_live_order_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "retained_request_review_only",
        "phase9br_summary": evidence_file(p9br_summary_path),
        "phase9bs_scope_summary": evidence_file(p9bs_scope_summary_path),
        "project_profile": evidence_file(project_profile_path),
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_sync_performed": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
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
    review_path = proof_root / "live_order_gate_request_review.json"
    matrix_path = proof_root / "non_authorization_matrix.json"
    control_path = proof_root / "control_boundary_readback.json"
    summary_path = root / "summary.json"
    report_path = root / "p9bs_live_order_gate_request.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "live_order_gate_request_review": str(review_path),
        "non_authorization_matrix": str(matrix_path),
        "control_boundary_readback": str(control_path),
        "report": str(report_path),
    }

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "status": "blocked",
        "blockers": blockers,
        "live_order_gate_requested": True,
        "live_order_gate_approved": False,
        "candidate_executor_target_path_approved": False,
        "candidate_enter_executor_target_plan_path_authorized": False,
        "risk_limit_approved": False,
        "order_type_approved": False,
        "max_notional_approved": False,
        "kill_switch_approved": False,
        "rollback_conditions_approved": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
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
        "repo_stage_change_authorized": False,
        "entered_timer_path": False,
        "ran_supervisor": False,
        "remote_execution_performed": False,
        "candidate_execution_performed": False,
        "executor_input_changed": False,
        "target_plan_replaced": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "timer_state_changed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "requested_live_order_terms": requested_terms,
        "source_evidence": {
            "phase9br_summary": evidence_file(p9br_summary_path),
            "phase9bs_scope_summary": evidence_file(p9bs_scope_summary_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(review_path, review_packet)
    write_json(matrix_path, non_authorization_matrix)
    write_json(control_path, control_boundary)
    write_json(summary_path, summary)
    report_path.write_text(
        "\n".join(
            [
                "# hv_balanced DTH60/CoinGlass P9BS Live-Order Gate Request",
                "",
                "`Status: blocked`",
                "",
                "## Decision",
                "",
                f"The direct live-order gate request is blocked. {decision_text}",
                "",
                "```text",
                "live_order_gate_approved = false",
                "candidate_executor_target_path_approved = false",
                "candidate_execution_authorized = false",
                "live_order_submission_authorized = false",
                "orders_submitted = 0",
                "fill_count = 0",
                "```",
                "",
                "## Blockers",
                "",
                *[f"- {blocker}" for blocker in blockers],
                "",
            ]
        ),
        encoding="utf-8",
    )

    return summary, 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p9bs_live_order_gate_request(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
