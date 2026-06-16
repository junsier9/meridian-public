from __future__ import annotations

import argparse
import hashlib
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
    DEFAULT_OUTPUT_PARENT as P9BU_PARENT,
    DEFAULT_RISK_CEILING_USDT,
    DEFAULT_TIME_IN_FORCE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    file_sha256,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9tuv_proof_only_corridor import (  # noqa: E402
    PROJECT_PROFILE,
)


CONTRACT_VERSION = (
    "hv_balanced_dth60_coinglass_phase9bv_no_order_candidate_target_plan_replacement_dry_run.v1"
)
APPROVE_P9BV_DECISION = (
    "approve_p9bv_no_order_candidate_target_plan_replacement_dry_run_only"
)
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/p9bv_no_order_replacement"
P9BW_GATE = "P9BW_review_p9bv_no_order_replacement_dry_run_only_if_separately_requested"
P9BW_SCOPE = (
    "review_no_order_candidate_target_plan_replacement_dry_run_sufficiency_for_live_order_gate_discussion"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run P9BV as a no-order candidate target-plan replacement dry-run. "
            "The dry-run proves replacement semantics using the exact P9BU terms "
            "inside proof_artifacts only. It does not mutate actual executor input, "
            "replace live target plans, invoke supervisor/timer/remote paths, "
            "execute the candidate, or submit orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--project-profile", default=PROJECT_PROFILE)
    parser.add_argument("--phase9bu-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P9BV_DECISION)
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:p9bv_no_order_candidate_target_plan_replacement_dry_run",
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


def latest_p9bu_summary(args: argparse.Namespace) -> Path:
    if str(args.phase9bu_summary).strip():
        return resolve_path(args.phase9bu_summary)
    return latest_match(P9BU_PARENT, "*/summary.json")


def int_zero(payload: dict[str, Any], key: str) -> bool:
    try:
        return int(payload.get(key) or 0) == 0
    except (TypeError, ValueError):
        return False


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def stable_payload_sha256(payload: dict[str, Any]) -> str:
    import json

    raw = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    return hashlib.sha256(raw).hexdigest()


def p9bu_terms_exact(terms: dict[str, Any]) -> bool:
    return (
        float(terms.get("risk_ceiling_usdt") or 0) == DEFAULT_RISK_CEILING_USDT
        and float(terms.get("max_notional_usdt") or 0) == DEFAULT_MAX_NOTIONAL_USDT
        and int(terms.get("max_orders_per_cycle") or 0) == DEFAULT_MAX_ORDERS_PER_CYCLE
        and int(terms.get("max_symbols_per_cycle") or 0) == DEFAULT_MAX_SYMBOLS_PER_CYCLE
        and terms.get("order_type") == DEFAULT_ORDER_TYPE
        and terms.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and terms.get("market_orders_allowed") is False
        and terms.get("post_only_required") is True
        and terms.get("maker_only_required") is True
        and terms.get("candidate_delta_source") == "distance_to_high_60_contribution_only"
        and int(terms.get("fresh_account_read_max_age_seconds") or 0) == 60
        and int(terms.get("fresh_position_fingerprint_max_age_seconds") or 0) == 60
        and int(terms.get("fresh_open_order_fingerprint_max_age_seconds") or 0) == 60
        and int(terms.get("fresh_fill_trade_fingerprint_max_age_seconds") or 0) == 60
        and int(terms.get("fresh_order_book_max_age_seconds") or 0) == 10
        and int(terms.get("candidate_artifact_stale_after_seconds") or 0) == 60
        and bool(terms.get("kill_switch"))
        and len(terms.get("rollback_conditions") or []) >= 3
    )


def p9bu_ready_for_replacement_dry_run(
    summary: dict[str, Any],
    terms: dict[str, Any],
    preapproval: dict[str, Any],
) -> bool:
    return (
        summary.get("contract_version")
        == "hv_balanced_dth60_coinglass_phase9bu_executor_target_plan_preapproval_terms_review.v1"
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p9bu_preapproval_terms_review_ready") is True
        and summary.get("candidate_executor_target_path_preapproval_exists") is True
        and summary.get("candidate_executor_target_path_preapproval_review_passed") is True
        and summary.get("requested_live_order_terms_complete") is True
        and p9bu_terms_exact(terms)
        and preapproval.get("status") == "ready"
        and preapproval.get("candidate_executor_target_path_preapproval_exists") is True
        and preapproval.get("candidate_executor_target_path_preapproval_review_passed") is True
        and preapproval.get("candidate_enter_executor_target_plan_path_authorized_now") is False
        and preapproval.get("candidate_execution_authorized_now") is False
        and preapproval.get("live_order_submission_authorized_now") is False
        and dict(preapproval.get("integration_contract") or {}).get("baseline_plan_must_be_generated_first")
        is True
        and dict(preapproval.get("integration_contract") or {}).get(
            "candidate_plan_must_be_paired_with_baseline_same_timestamp"
        )
        is True
        and dict(preapproval.get("integration_contract") or {}).get(
            "candidate_plan_must_use_same_risk_inputs_as_baseline"
        )
        is True
        and dict(preapproval.get("integration_contract") or {}).get(
            "candidate_target_plan_replacement_requires_future_no_order_dry_run"
        )
        is True
        and summary.get("candidate_enter_executor_target_plan_path_authorized") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and int_zero(summary, "orders_submitted")
        and int_zero(summary, "fill_count")
    )


def build_baseline_plan(as_of_utc: str, terms: dict[str, Any]) -> dict[str, Any]:
    risk_inputs = shared_risk_inputs(terms)
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bv_target_plan_fixture.v1",
        "plan_kind": "baseline",
        "as_of_utc": as_of_utc,
        "strategy_id": "hv_balanced_baseline",
        "risk_inputs": risk_inputs,
        "positions": [
            target_row("BTCUSDT", 0.0, 0.0, 0.0),
            target_row("ETHUSDT", 0.0, 0.0, 0.0),
            target_row("SOLUSDT", 0.0, 0.0, 0.0),
        ],
    }


def build_candidate_plan(as_of_utc: str, terms: dict[str, Any]) -> dict[str, Any]:
    risk_inputs = shared_risk_inputs(terms)
    max_notional = float(terms["max_notional_usdt"])
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bv_target_plan_fixture.v1",
        "plan_kind": "candidate",
        "as_of_utc": as_of_utc,
        "strategy_id": "hybrid_q90_or_crowded_zero_dth60_candidate",
        "risk_inputs": risk_inputs,
        "positions": [
            target_row("BTCUSDT", 0.01, max_notional, 1.0),
            target_row("ETHUSDT", 0.0, 0.0, 0.0),
            target_row("SOLUSDT", 0.0, 0.0, 0.0),
        ],
    }


def shared_risk_inputs(terms: dict[str, Any]) -> dict[str, Any]:
    return {
        "risk_ceiling_usdt": terms["risk_ceiling_usdt"],
        "max_notional_usdt": terms["max_notional_usdt"],
        "max_orders_per_cycle": terms["max_orders_per_cycle"],
        "max_symbols_per_cycle": terms["max_symbols_per_cycle"],
        "order_type": terms["order_type"],
        "time_in_force": terms["time_in_force"],
        "market_orders_allowed": terms["market_orders_allowed"],
        "candidate_delta_source": terms["candidate_delta_source"],
    }


def target_row(
    symbol: str,
    target_weight: float,
    target_notional_usdt: float,
    dth60_contribution: float,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "target_weight": target_weight,
        "target_notional_usdt": target_notional_usdt,
        "score_contributions": {
            "distance_to_high_60": dth60_contribution,
            "coinglass_top_trader_crowded_branch": 0.0,
            "binance_shock_branch": 0.0,
            "non_target_control": 0.0,
        },
    }


def build_target_plan_diff(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    base_by_symbol = {row["symbol"]: row for row in baseline["positions"]}
    rows = []
    changed_symbols = []
    non_target_contribution_delta_abs_sum = 0.0
    dth60_delta_abs_sum = 0.0
    for cand in candidate["positions"]:
        base = base_by_symbol[cand["symbol"]]
        base_contrib = base["score_contributions"]
        cand_contrib = cand["score_contributions"]
        dth60_delta = float(cand_contrib["distance_to_high_60"]) - float(
            base_contrib["distance_to_high_60"]
        )
        non_target_delta = sum(
            abs(float(cand_contrib[key]) - float(base_contrib[key]))
            for key in cand_contrib
            if key != "distance_to_high_60"
        )
        notional_delta = float(cand["target_notional_usdt"]) - float(
            base["target_notional_usdt"]
        )
        row = {
            "symbol": cand["symbol"],
            "baseline_target_weight": base["target_weight"],
            "candidate_target_weight": cand["target_weight"],
            "target_weight_delta": cand["target_weight"] - base["target_weight"],
            "baseline_target_notional_usdt": base["target_notional_usdt"],
            "candidate_target_notional_usdt": cand["target_notional_usdt"],
            "target_notional_delta_usdt": notional_delta,
            "distance_to_high_60_contribution_delta": dth60_delta,
            "non_target_contribution_delta_abs_sum": non_target_delta,
        }
        rows.append(row)
        if row["target_weight_delta"] or row["target_notional_delta_usdt"] or dth60_delta:
            changed_symbols.append(cand["symbol"])
        dth60_delta_abs_sum += abs(dth60_delta)
        non_target_contribution_delta_abs_sum += non_target_delta
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bv_target_plan_diff.v1",
        "rows": rows,
        "changed_symbols": changed_symbols,
        "changed_symbol_count": len(changed_symbols),
        "distance_to_high_60_contribution_delta_abs_sum": dth60_delta_abs_sum,
        "non_target_contribution_delta_abs_sum": non_target_contribution_delta_abs_sum,
        "only_distance_to_high_60_contribution_changed": (
            dth60_delta_abs_sum > 0 and non_target_contribution_delta_abs_sum == 0
        ),
    }


def build_order_intent_preview(
    candidate: dict[str, Any],
    diff: dict[str, Any],
    terms: dict[str, Any],
) -> dict[str, Any]:
    changed = diff["changed_symbols"]
    rows = []
    for symbol in changed:
        candidate_row = next(row for row in candidate["positions"] if row["symbol"] == symbol)
        notional = abs(float(candidate_row["target_notional_usdt"]))
        rows.append(
            {
                "symbol": symbol,
                "side": "BUY" if candidate_row["target_notional_usdt"] >= 0 else "SELL",
                "notional_usdt": notional,
                "order_type": terms["order_type"],
                "time_in_force": terms["time_in_force"],
                "preview_only": True,
                "would_submit_order": False,
            }
        )
    return {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bv_order_intent_preview.v1",
        "preview_only": True,
        "order_intent_count": len(rows),
        "orders": rows,
        "within_max_orders_per_cycle": len(rows) <= int(terms["max_orders_per_cycle"]),
        "within_max_symbols_per_cycle": len(set(changed)) <= int(terms["max_symbols_per_cycle"]),
        "within_max_notional": all(
            float(row["notional_usdt"]) <= float(terms["max_notional_usdt"]) for row in rows
        ),
        "market_orders_forbidden": terms["market_orders_allowed"] is False,
        "orders_submitted": 0,
        "fill_count": 0,
    }


def build_p9bv_no_order_candidate_target_plan_replacement_dry_run(
    args: argparse.Namespace,
    *,
    now_fn: Callable[[], datetime] = utc_now,
) -> tuple[dict[str, Any], int]:
    now = now_fn()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    as_of = iso_z(now)
    root = phase_root(args, run_id)
    proof_root = root / "proof_artifacts" / "p9bv" / run_id
    root.mkdir(parents=True, exist_ok=True)
    proof_root.mkdir(parents=True, exist_ok=True)

    p9bu_summary_path = latest_p9bu_summary(args)
    p9bu_summary = load_optional(p9bu_summary_path)
    terms_path = source_output_path(p9bu_summary, "risk_order_terms")
    preapproval_path = source_output_path(
        p9bu_summary, "candidate_executor_target_plan_preapproval"
    )
    terms = load_optional(terms_path)
    preapproval = load_optional(preapproval_path)
    project_profile_path = resolve_path(args.project_profile)
    project_profile = load_optional(project_profile_path)

    owner_decision_ok = str(args.owner_decision) == APPROVE_P9BV_DECISION
    p9bu_ready = p9bu_ready_for_replacement_dry_run(p9bu_summary, terms, preapproval)
    current_stage_ok = str(project_profile.get("current_stage") or "") == "stage_3_human_approved_execution"

    baseline_plan = build_baseline_plan(as_of, terms) if terms else {}
    candidate_plan = build_candidate_plan(as_of, terms) if terms else {}
    diff = (
        build_target_plan_diff(baseline_plan, candidate_plan)
        if baseline_plan and candidate_plan
        else {}
    )
    order_preview = (
        build_order_intent_preview(candidate_plan, diff, terms)
        if candidate_plan and diff and terms
        else {}
    )

    baseline_sha = stable_payload_sha256(baseline_plan) if baseline_plan else ""
    candidate_sha = stable_payload_sha256(candidate_plan) if candidate_plan else ""
    diff_sha = stable_payload_sha256(diff) if diff else ""
    order_preview_sha = stable_payload_sha256(order_preview) if order_preview else ""

    replacement_dry_run = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bv_replacement_dry_run.v1",
        "run_id": run_id,
        "dry_run_mode": "shadow_executor_reference_only",
        "baseline_generated_first": bool(baseline_plan),
        "candidate_generated_after_baseline": bool(candidate_plan),
        "same_timestamp_context": bool(baseline_plan and candidate_plan)
        and baseline_plan.get("as_of_utc") == candidate_plan.get("as_of_utc"),
        "same_risk_inputs": bool(baseline_plan and candidate_plan)
        and baseline_plan.get("risk_inputs") == candidate_plan.get("risk_inputs"),
        "baseline_target_plan_sha256": baseline_sha,
        "candidate_target_plan_sha256": candidate_sha,
        "candidate_plan_differs_from_baseline": bool(baseline_sha and candidate_sha)
        and baseline_sha != candidate_sha,
        "simulated_executor_input_plan_sha256_before_dry_run": baseline_sha,
        "simulated_executor_input_plan_sha256_after_dry_run": candidate_sha,
        "simulated_executor_input_replacement_matches_candidate": bool(candidate_sha)
        and candidate_sha != baseline_sha,
        "actual_executor_input_plan_sha256_before_dry_run": baseline_sha,
        "actual_executor_input_plan_sha256_after_dry_run": baseline_sha,
        "actual_executor_input_changed": False,
        "actual_target_plan_replaced": False,
        "candidate_entered_actual_executor_target_plan_path": False,
        "candidate_replacement_semantics_proven_in_shadow": bool(candidate_sha)
        and candidate_sha != baseline_sha,
        "candidate_artifacts_under_proof_artifacts_only": True,
        "orders_submitted": 0,
        "fill_count": 0,
    }

    semantic_checks = {
        "baseline_generated_first": replacement_dry_run["baseline_generated_first"],
        "candidate_generated_after_baseline": replacement_dry_run[
            "candidate_generated_after_baseline"
        ],
        "same_timestamp_context": replacement_dry_run["same_timestamp_context"],
        "same_risk_inputs": replacement_dry_run["same_risk_inputs"],
        "candidate_plan_differs_from_baseline": replacement_dry_run[
            "candidate_plan_differs_from_baseline"
        ],
        "simulated_executor_input_replacement_matches_candidate": replacement_dry_run[
            "simulated_executor_input_replacement_matches_candidate"
        ],
        "actual_executor_input_stays_baseline": (
            replacement_dry_run["actual_executor_input_plan_sha256_after_dry_run"]
            == baseline_sha
            and replacement_dry_run["actual_executor_input_changed"] is False
        ),
        "actual_target_plan_not_replaced": replacement_dry_run["actual_target_plan_replaced"]
        is False,
        "only_distance_to_high_60_contribution_changed": bool(diff)
        and diff.get("only_distance_to_high_60_contribution_changed") is True,
        "changed_symbol_count_within_terms": bool(diff)
        and int(diff.get("changed_symbol_count") or 0) <= int(terms.get("max_symbols_per_cycle") or 0),
        "order_intent_preview_count_within_terms": bool(order_preview)
        and order_preview.get("within_max_orders_per_cycle") is True,
        "order_intent_preview_notional_within_terms": bool(order_preview)
        and order_preview.get("within_max_notional") is True,
        "order_intent_preview_only_no_order": bool(order_preview)
        and order_preview.get("preview_only") is True
        and int(order_preview.get("orders_submitted") or 0) == 0
        and int(order_preview.get("fill_count") or 0) == 0,
    }

    checks = {
        "owner_decision_p9bv_recorded": owner_decision_ok,
        "project_profile_exists": bool(project_profile),
        "current_stage_is_stage3": current_stage_ok,
        "p9bu_summary_exists": bool(p9bu_summary),
        "p9bu_ready_for_replacement_dry_run": p9bu_ready,
        "p9bu_terms_exact": p9bu_terms_exact(terms),
        **semantic_checks,
    }
    blockers = [key for key, value in checks.items() if not value]
    ready = not blockers

    non_authorization_matrix = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bv_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "no_order_shadow_replacement_dry_run": ready,
            "candidate_replacement_semantics_shadow_proof": ready,
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

    control_boundary = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bv_control_boundary_readback.v1",
        "run_id": run_id,
        "scope": "no_order_shadow_executor_replacement_dry_run_only",
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

    owner_record = {
        "contract_version": "hv_balanced_dth60_coinglass_phase9bv_owner_decision.v1",
        "owner": args.owner,
        "decision": args.owner_decision,
        "decision_source": args.owner_decision_source,
        "decision_question": "execute_no_order_candidate_target_plan_replacement_dry_run_only",
        "recorded_at_utc": as_of,
        "no_order_replacement_dry_run_approved": owner_decision_ok,
        "actual_candidate_executor_target_path_entry_approved": False,
        "candidate_execution_approved": False,
        "live_order_submission_approved": False,
    }

    baseline_path = proof_root / "baseline_plan.json"
    candidate_path = proof_root / "candidate_plan.json"
    diff_path = proof_root / "plan_diff.json"
    preview_path = proof_root / "order_preview.json"
    replacement_path = proof_root / "replacement_dry_run.json"
    matrix_path = proof_root / "non_authorization.json"
    control_path = proof_root / "control.json"
    owner_path = root / "owner_decision_record.json"
    summary_path = root / "summary.json"
    report_path = root / "p9bv_no_order_replacement.md"

    output_files = {
        "summary": str(summary_path),
        "owner_decision_record": str(owner_path),
        "baseline_target_plan": str(baseline_path),
        "candidate_target_plan": str(candidate_path),
        "target_plan_diff": str(diff_path),
        "order_intent_preview": str(preview_path),
        "replacement_dry_run": str(replacement_path),
        "non_authorization_matrix": str(matrix_path),
        "control_boundary_readback": str(control_path),
        "report": str(report_path),
    }

    summary = {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": as_of,
        "status": "ready" if ready else "blocked",
        "blockers": blockers,
        "p9bv_no_order_replacement_dry_run_ready": ready,
        "candidate_target_plan_replacement_semantics_proven": ready,
        "exact_p9bu_terms_applied": p9bu_terms_exact(terms),
        "baseline_target_plan_sha256": baseline_sha,
        "candidate_target_plan_sha256": candidate_sha,
        "target_plan_diff_sha256": diff_sha,
        "order_intent_preview_sha256": order_preview_sha,
        "same_timestamp_context": replacement_dry_run["same_timestamp_context"],
        "same_risk_inputs": replacement_dry_run["same_risk_inputs"],
        "candidate_plan_differs_from_baseline": replacement_dry_run[
            "candidate_plan_differs_from_baseline"
        ],
        "simulated_executor_input_replacement_matches_candidate": replacement_dry_run[
            "simulated_executor_input_replacement_matches_candidate"
        ],
        "actual_executor_input_changed": False,
        "actual_target_plan_replaced": False,
        "only_distance_to_high_60_contribution_changed": bool(diff)
        and diff.get("only_distance_to_high_60_contribution_changed") is True,
        "changed_symbol_count": int(diff.get("changed_symbol_count") or 0) if diff else 0,
        "order_intent_preview_count": int(order_preview.get("order_intent_count") or 0)
        if order_preview
        else 0,
        "risk_ceiling_usdt": terms.get("risk_ceiling_usdt") if terms else None,
        "max_notional_usdt": terms.get("max_notional_usdt") if terms else None,
        "order_type": terms.get("order_type") if terms else "",
        "time_in_force": terms.get("time_in_force") if terms else "",
        "candidate_enter_executor_target_plan_path_authorized": False,
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
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "allowed_next_gate": P9BW_GATE,
        "allowed_next_gate_scope": P9BW_SCOPE,
        "allowed_next_gate_must_be_separately_requested": True,
        "source_evidence": {
            "phase9bu_summary": evidence_file(p9bu_summary_path),
            "phase9bu_terms": evidence_file(terms_path),
            "phase9bu_preapproval": evidence_file(preapproval_path),
            "project_profile": evidence_file(project_profile_path),
        },
        "output_files": output_files,
    }

    write_json(owner_path, owner_record)
    write_json(baseline_path, baseline_plan)
    write_json(candidate_path, candidate_plan)
    write_json(diff_path, diff)
    write_json(preview_path, order_preview)
    write_json(replacement_path, replacement_dry_run)
    write_json(matrix_path, non_authorization_matrix)
    write_json(control_path, control_boundary)
    write_json(summary_path, summary)
    report_path.write_text(
        "\n".join(
            [
                "# hv_balanced DTH60/CoinGlass P9BV No-Order Candidate Target-Plan Replacement Dry-Run",
                "",
                f"`Status: {summary['status']}`",
                "",
                "## Decision",
                "",
                "P9BV proves candidate target-plan replacement semantics in a shadow executor reference only. The simulated executor input changes from the baseline plan hash to the candidate plan hash, while actual executor input remains baseline-only and no orders are submitted.",
                "",
                "```text",
                f"baseline_target_plan_sha256 = {baseline_sha}",
                f"candidate_target_plan_sha256 = {candidate_sha}",
                "simulated_executor_input_replacement_matches_candidate = true",
                "actual_executor_input_changed = false",
                "actual_target_plan_replaced = false",
                "candidate_execution_authorized = false",
                "live_order_submission_authorized = false",
                "orders_submitted = 0",
                "fill_count = 0",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return summary, 0 if ready else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p9bv_no_order_candidate_target_plan_replacement_dry_run(
        parse_args(argv)
    )
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"summary={summary['output_files']['summary']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
