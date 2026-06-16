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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bu_executor_target_plan_preapproval_terms_review import (  # noqa: E402
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_MAX_ORDERS_PER_CYCLE,
    DEFAULT_MAX_SYMBOLS_PER_CYCLE,
    DEFAULT_ORDER_TYPE,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9bw_review_after_p9bv import (  # noqa: E402
    CONTRACT_VERSION as P9BW_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P9BW_PARENT,
    P9BX_GATE,
    P9BX_SCOPE,
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
    "hv_balanced_dth60_coinglass_phase9bx_live_order_gate_scope_definition.v1"
)
APPROVE_P9BX_DECISION = (
    "approve_p9bx_define_live_order_gate_scope_only_no_order_no_execution"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9bx_live_order_scope"
P9BY_GATE = "P9BY_prepare_live_order_gate_review_package_only_if_separately_requested"
P9BY_SCOPE = (
    "prepare_live_order_gate_review_package_from_p9bx_scope_only_no_order_no_execution"
)
CANARY_SYMBOL = "BTCUSDT"
CANARY_SIDE = "BUY"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Define the P9BX live-order gate scope only. This consumes retained "
            "P9BW evidence and writes a proof-only scope package. It does not "
            "approve live orders, enter candidate execution, replace target "
            "plans, mutate executor input, invoke supervisor/timer/remote paths, "
            "or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9bw-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BX_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9bx_define_live_order_gate_scope_only_if_separately_requested",
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


def latest_p9bw_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bw_summary).strip():
        return resolve_path(args.phase9bw_summary)
    return latest_match(P9BW_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def p9bw_summary_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P9BW_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9bw_review_after_p9bv_ready") is True
        and summary.get("p9bv_retained_evidence_sufficient_for_live_order_gate_discussion")
        is True
        and summary.get("eligible_for_future_live_order_gate_discussion") is True
        and summary.get("eligible_for_future_live_order_submission") is False
        and summary.get("live_order_gate_approved") is False
        and summary.get("allowed_next_gate") == P9BX_GATE
        and summary.get("allowed_next_gate_scope") == P9BX_SCOPE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("simulated_executor_input_replacement_matches_candidate") is True
        and summary.get("actual_executor_input_changed") is False
        and summary.get("actual_target_plan_replaced") is False
        and summary.get("only_distance_to_high_60_contribution_changed") is True
        and int(summary.get("changed_symbol_count") or 0) == 1
        and int(summary.get("order_intent_preview_count") or 0) == 1
        and summary.get("candidate_enter_executor_target_plan_path_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("remote_sync_authorized") is False
        and summary.get("remote_execution_authorized") is False
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "fill_count")
    )


def p9bw_non_authorization_ready(matrix: dict[str, Any]) -> bool:
    authorizations = dict(matrix.get("authorizations") or {})
    return (
        matrix.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bw_non_authorization_matrix.v1"
        and authorizations.get("review_p9bv_retained_evidence") is True
        and authorizations.get("enter_live_order_gate_discussion") is True
        and authorizations.get("define_p9bx_scope") is False
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


def p9bw_control_ready(control: dict[str, Any]) -> bool:
    return (
        control.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bw_control_boundary_readback.v1"
        and control.get("scope") == "retained_review_only"
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


def required_fresh_proofs() -> list[dict[str, Any]]:
    return [
        {
            "proof_id": "fresh_remote_account_read",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "must_be_from_target_runner": True,
            "purpose": "prove account is readable and bind available balance/equity before canary order discussion",
        },
        {
            "proof_id": "pre_position_fingerprint",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "purpose": "bind current non-empty or empty positions without mutating the account",
        },
        {
            "proof_id": "pre_open_order_fingerprint",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "purpose": "prove existing open-order state before any candidate order discussion",
        },
        {
            "proof_id": "pre_fill_trade_fingerprint",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "purpose": "prove fill/trade baseline before canary order discussion",
        },
        {
            "proof_id": "fresh_order_book",
            "max_age_seconds": 10,
            "required_before": "future_live_order_gate_approval",
            "purpose": "bind maker-only post-only limit price to a fresh book snapshot",
        },
        {
            "proof_id": "exchange_filter_readback",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "purpose": "prove min notional, tick size, step size, precision, and post-only support",
        },
        {
            "proof_id": "p9bu_terms_operator_acceptance",
            "max_age_seconds": 300,
            "required_before": "future_live_order_gate_approval",
            "purpose": "bind owner acceptance of exact risk and order terms",
        },
        {
            "proof_id": "candidate_target_plan_hash_binding",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "purpose": "prove candidate executor input in a no-order gate equals the approved candidate target-plan hash",
        },
        {
            "proof_id": "baseline_candidate_plan_diff",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "purpose": "prove the only strategy delta remains distance_to_high_60 contribution for one symbol",
        },
        {
            "proof_id": "kill_switch_readback",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "purpose": "prove target runner can disable candidate overlay and force baseline-only executor path",
        },
        {
            "proof_id": "rollback_command_readback",
            "max_age_seconds": 60,
            "required_before": "future_live_order_gate_approval",
            "purpose": "prove rollback commands and operator boundary are readable before discussion",
        },
        {
            "proof_id": "final_owner_live_order_gate_approval",
            "max_age_seconds": 300,
            "required_before": "any_order_submission",
            "purpose": "separate final owner decision from this scope definition",
        },
    ]


def build_live_order_gate_scope() -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bx_live_order_gate_scope.v1",
        "scope_definition_only": True,
        "future_gate_name": "candidate_live_order_gate",
        "future_gate_may_discuss": [
            "single canary order submission under exact P9BU terms",
            "candidate target-plan replacement semantics if fresh no-order binding still passes",
            "post-order observation and rollback obligations",
        ],
        "future_gate_may_not_skip": [
            "fresh remote account read",
            "pre/post position fingerprint",
            "pre/post open-order fingerprint",
            "pre/post fill and trade fingerprint",
            "fresh order book",
            "exchange filters and post-only support",
            "final owner live-order gate approval",
        ],
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
            "candidate_delta_source": "distance_to_high_60_contribution_only",
        },
        "rollback_conditions": [
            "any required fresh proof is missing, stale, or hash-mismatched",
            "candidate target-plan hash differs from no-order approved hash",
            "executor input is not explicitly bound to the candidate target-plan hash in the final gate",
            "candidate delta affects anything outside distance_to_high_60 contribution",
            "open-order, fill, trade, or position delta is unexplained",
            "order book no longer supports maker-only post-only execution",
            "supervisor, timer, operator, exchange, or provider health readback reports an exception",
            "kill switch readback is unavailable",
        ],
        "out_of_scope_for_p9bx": [
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


def build_p9bx_live_order_gate_scope_definition(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9bx" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9bw_summary_path = latest_p9bw_summary(args)
    p9bw = load_optional(p9bw_summary_path)
    matrix_path = source_output_path(p9bw, "non_authorization_matrix")
    control_path = source_output_path(p9bw, "control_boundary_readback")
    p9bw_matrix = load_optional(matrix_path)
    p9bw_control = load_optional(control_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9BX_DECISION
    checks = {
        "owner_decision_p9bx_scope_only_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": str(project_profile.get("current_stage") or "")
        == "stage_3_human_approved_execution",
        "p9bw_summary_exists": bool(p9bw),
        "p9bw_summary_ready_for_scope_definition": p9bw_summary_ready(p9bw),
        "p9bw_non_authorization_ready": p9bw_non_authorization_ready(p9bw_matrix),
        "p9bw_control_boundary_ready": p9bw_control_ready(p9bw_control),
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    live_order_scope = build_live_order_gate_scope()
    fresh_proofs = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bx_required_fresh_proofs.v1",
        "scope_definition_only": True,
        "proofs": required_fresh_proofs(),
        "fresh_proofs_required_before_any_future_order_submission": True,
        "p9bx_satisfies_fresh_proofs": False,
    }
    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bx_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "define_live_order_gate_scope_only_no_order_no_execution",
        "recorded_at_utc": iso_z(now),
        "scope_definition_approved": owner_decision_ok,
        "live_order_gate_approved": False,
        "candidate_execution_approved": False,
        "target_plan_replacement_approved": False,
        "executor_input_mutation_approved": False,
        "live_order_submission_approved": False,
    }
    non_authorization = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bx_non_authorization.v1",
        "run_id": run_id,
        "authorizations": {
            "define_live_order_gate_scope": ready,
            "prepare_future_live_order_gate_review_package": ready,
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
        "contract_version": "hv_balanced_dth60_coinglass_phase9bx_control_boundary.v1",
        "run_id": run_id,
        "scope": "live_order_gate_scope_definition_only",
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
    scope_path = proof_root / "live_order_gate_scope.json"
    proofs_path = proof_root / "required_fresh_proofs.json"
    non_auth_path = proof_root / "non_authorization.json"
    control_path_out = proof_root / "control.json"
    summary_path = root / "summary.json"
    report_path = root / "p9bx_live_order_gate_scope.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "live_order_gate_scope": str(scope_path),
        "required_fresh_proofs": str(proofs_path),
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
        "p9bx_live_order_gate_scope_defined": ready,
        "p9bw_sufficient_for_scope_definition": p9bw_summary_ready(p9bw),
        "eligible_for_future_live_order_gate_review_package": ready,
        "eligible_for_future_live_order_submission": False,
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
        "allowed_next_gate": P9BY_GATE,
        "allowed_next_gate_scope": P9BY_SCOPE,
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
        "required_fresh_proof_count": len(fresh_proofs["proofs"]),
        "source_p9bw_summary_sha256": evidence_file(p9bw_summary_path).get("sha256", ""),
        "baseline_target_plan_sha256": p9bw.get("baseline_target_plan_sha256"),
        "candidate_target_plan_sha256": p9bw.get("candidate_target_plan_sha256"),
        "simulated_executor_input_replacement_matches_candidate": p9bw.get(
            "simulated_executor_input_replacement_matches_candidate"
        ),
        "actual_executor_input_changed": False,
        "actual_target_plan_replaced": False,
        "only_distance_to_high_60_contribution_changed": p9bw.get(
            "only_distance_to_high_60_contribution_changed"
        ),
        "changed_symbol_count": p9bw.get("changed_symbol_count"),
        "order_intent_preview_count": p9bw.get("order_intent_preview_count"),
        "source_evidence": {
            "phase9bw_summary": evidence_file(p9bw_summary_path),
            "phase9bw_non_authorization": evidence_file(matrix_path),
            "phase9bw_control_boundary": evidence_file(control_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(scope_path, live_order_scope)
    write_json(proofs_path, fresh_proofs)
    write_json(non_auth_path, non_authorization)
    write_json(control_path_out, control)
    write_json(summary_path, summary)
    report_path.write_text(render_markdown(summary, live_order_scope, fresh_proofs), encoding="utf-8")

    return summary, 0 if ready else 2


def render_markdown(
    summary: dict[str, Any],
    scope: dict[str, Any],
    fresh_proofs: dict[str, Any],
) -> str:
    canary = dict(scope.get("canary_terms") or {})
    lines = [
        "# hv_balanced DTH60/CoinGlass P9BX Live-Order Gate Scope Definition",
        "",
        f"`Status: {summary['status']}`",
        "",
        "P9BX defines the future live-order gate scope only. It does not approve live orders, execute the candidate, replace target plans, mutate executor input, invoke supervisor/timer/remote paths, or submit orders.",
        "",
        "## Scope",
        "",
        "```text",
        f"p9bx_live_order_gate_scope_defined = {str(bool(summary['p9bx_live_order_gate_scope_defined'])).lower()}",
        f"eligible_for_future_live_order_gate_review_package = {str(bool(summary['eligible_for_future_live_order_gate_review_package'])).lower()}",
        "live_order_gate_approved = false",
        "live_order_submission_authorized = false",
        "candidate_execution_authorized = false",
        "target_plan_replacement_authorized = false",
        "executor_input_mutation_authorized = false",
        "orders_submitted = 0",
        "fill_count = 0",
        "```",
        "",
        "## Canary Discussion Boundary",
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
        "```",
        "",
        "## Required Fresh Proofs",
        "",
    ]
    for proof in list(fresh_proofs.get("proofs") or []):
        lines.append(
            f"- `{proof['proof_id']}` max_age_seconds={proof['max_age_seconds']}"
        )
    lines.extend(
        [
            "",
            "## Out Of Scope",
            "",
        ]
    )
    for item in list(scope.get("out_of_scope_for_p9bx") or []):
        lines.append(f"- {item}")
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
    summary, exit_code = build_p9bx_live_order_gate_scope_definition(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
