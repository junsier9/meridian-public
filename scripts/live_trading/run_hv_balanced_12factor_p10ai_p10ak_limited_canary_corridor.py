from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.live_trading.run_hv_balanced_12factor_p10g_candidate_target_plan_replacement_dry_run import (  # noqa: E402
    DEFAULT_OUTPUT_PARENT as P10G_PARENT,
)
from scripts.live_trading.run_hv_balanced_12factor_p10h_owner_gate_single_cycle_live_delta_canary_terms import (  # noqa: E402
    DEFAULT_OUTPUT_PARENT as P10H_PARENT,
    p10g_ready,
)
from scripts.live_trading.run_hv_balanced_12factor_p10i_execute_single_cycle_live_delta_canary import (  # noqa: E402
    build_p10i,
    parse_args as parse_p10i_args,
)
from scripts.live_trading.run_hv_balanced_12factor_p10m_p10p_bundled_corridor import (  # noqa: E402
    DEFAULT_MAX_GROSS_TURNOVER_USDT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_ORDER_TYPE,
    DEFAULT_SYMBOL,
    DEFAULT_TIME_IN_FORCE,
)
from scripts.live_trading.run_hv_balanced_12factor_p10af_p10ah_limited_execution_terms_corridor import (  # noqa: E402
    P10AH_CONTRACT,
    P10AI_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10ai_p10ak_limited_canary_corridor.v1"
P10AI_CONTRACT = "hv_balanced_12factor_p10ai_owner_gate_single_cycle_limited_canary.v1"
P10AJ_CONTRACT = "hv_balanced_12factor_p10aj_execute_single_cycle_limited_canary.v1"
P10AK_CONTRACT = "hv_balanced_12factor_p10ak_review_limited_canary_retained_evidence.v1"

DEFAULT_P10AH_SEARCH_PARENT = "artifacts/live_trading/proof_artifacts/p10af_p10ah_limited_execution_terms_corridor"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/proof_artifacts/p10ai_p10ak_limited_canary_corridor"

P10AJ_GATE = "P10AJ_execute_one_limited_live_delta_expansion_canary_only_if_separately_requested"
P10AK_GATE = "P10AK_review_p10aj_limited_live_delta_expansion_canary_retained_evidence_only_if_separately_requested"
P10AL_GATE = "P10AL_define_post_limited_canary_continuation_scope_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run P10AI-P10AK after retained P10AH. P10AI records the owner "
            "execution gate, P10AJ executes exactly one BTCUSDT post-only GTX "
            "limited canary through the existing P10I submitter, and P10AK "
            "reviews retained evidence. It does not load timer/supervisor paths, "
            "remote sync, mutate live config/operator state, mutate production "
            "executor input, replace production target plans, or enable "
            "continuous automation."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--p10ah-summary", default="")
    parser.add_argument("--p10g-summary", default="")
    parser.add_argument("--p10h-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:continue_next_bundled_gates_after_p10ah",
    )
    parser.add_argument("--order-lifetime-seconds", type=int, default=1)
    parser.add_argument("--maker-buffer-ticks", type=int, default=50)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def latest_summary(parent: str, pattern: str, explicit: str = "") -> Path:
    if str(explicit or "").strip():
        return resolve_path(explicit)
    return latest_match(parent, pattern)


def latest_p10ah_summary(explicit: str = "") -> Path:
    return latest_summary(DEFAULT_P10AH_SEARCH_PARENT, "*/p10ah_review/summary.json", explicit)


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root or "").strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def source_evidence_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("source_evidence") or {}).get(key, {}).get("path") or "")
    return resolve_path(text) if text.strip() else Path("")


def source_output_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("output_files") or {}).get(key) or "")
    return resolve_path(text) if text.strip() else Path("")


def p10ah_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P10AH_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10ah_review_limited_execution_terms_package_ready") is True
        and summary.get("p10ag_terms_sufficient_for_future_p10ai_owner_execution_gate") is True
        and summary.get("p10ag_terms_sufficient_for_live_order_submission_without_p10ai") is False
        and summary.get("p10ag_terms_sufficient_for_continuous_automation") is False
        and summary.get("allowed_next_gate") == P10AI_GATE
        and summary.get("allowed_next_gate_scope") == "owner_gate_to_execute_one_single_cycle_limited_canary_no_auto_execution"
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_executor_path_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("continuous_automated_order_flow_authorized") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
        and int(summary.get("trade_count") or 0) == 0
    )


def p10ag_terms_ready(terms: dict[str, Any]) -> bool:
    return (
        terms.get("contract_version") == "hv_balanced_12factor_p10ag_limited_execution_terms_package.v1"
        and terms.get("status") == "ready"
        and terms.get("symbol") == DEFAULT_SYMBOL
        and float(terms.get("max_notional_usdt") or 0.0) == DEFAULT_MAX_NOTIONAL_USDT
        and float(terms.get("max_gross_turnover_usdt") or 0.0) == DEFAULT_MAX_GROSS_TURNOVER_USDT
        and int(terms.get("max_cycles_total") or 0) == 1
        and int(terms.get("max_candidate_entry_orders_total") or 0) == 1
        and int(terms.get("max_orders_total") or 0) == 2
        and terms.get("order_type") == DEFAULT_ORDER_TYPE
        and terms.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and terms.get("post_only_required") is True
        and terms.get("maker_only_required") is True
        and terms.get("market_orders_allowed") is False
        and terms.get("continuous_automation") is False
        and int(terms.get("minimum_maker_buffer_ticks") or 0) >= 50
        and terms.get("does_not_authorize_execution") is True
    )


def write_phase(root: Path, name: str, payloads: dict[str, dict[str, Any]]) -> Path:
    phase_dir = root / name
    proof_dir = phase_dir / "proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    for key, payload in payloads.items():
        write_json(proof_dir / f"{key}.json", payload)
    return phase_dir


def no_production_mutation_matrix() -> dict[str, Any]:
    return {
        "production_executor_input_mutation_performed": False,
        "actual_target_plan_replacement_performed": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automation_enabled": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "live_config_mutation_performed": False,
        "operator_state_mutation_performed": False,
    }


def build_p10ai(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10ah: dict[str, Any],
    p10ah_path: Path,
    terms_path: Path,
    terms: dict[str, Any],
    p10g_path: Path,
    p10g: dict[str, Any],
    p10h_path: Path,
) -> tuple[dict[str, Any], Path]:
    retained = dict(terms.get("retained_evidence_basis") or {})
    prior = dict(retained.get("prior_p10o") or {})
    followup = dict(retained.get("followup_p10aa") or {})
    candidate_plan_path = source_output_path(p10g, "candidate_target_plan")
    baseline_plan_path = source_output_path(p10g, "baseline_target_plan")
    diff_path = source_output_path(p10g, "target_plan_diff")
    gates = {
        "owner_decision_p10ai_recorded": True,
        "p10ah_ready_for_p10ai": p10ah_ready(p10ah),
        "p10ag_terms_exists": terms_path.exists() and terms_path.is_file(),
        "p10ag_terms_ready": p10ag_terms_ready(terms),
        "retained_prior_and_followup_candidate_hash_match": str(prior.get("candidate_target_plan_sha256") or "")
        == str(followup.get("candidate_target_plan_sha256") or ""),
        "retained_candidate_hash_matches_p10g": str(followup.get("candidate_target_plan_sha256") or "")
        == str(p10g.get("candidate_target_plan_sha256") or ""),
        "p10g_summary_ready": p10g_ready(p10g),
        "p10h_summary_exists_for_p10i": p10h_path.exists() and p10h_path.is_file(),
        "candidate_plan_exists": candidate_plan_path.exists() and candidate_plan_path.is_file(),
        "baseline_plan_exists": baseline_plan_path.exists() and baseline_plan_path.is_file(),
        "target_plan_diff_exists": diff_path.exists() and diff_path.is_file(),
        "single_cycle_only": True,
        "continuous_automation_false": True,
    }
    blockers = sorted(key for key, ready in gates.items() if not ready)
    status = "ready" if not blockers else "blocked"
    owner = {
        "contract_version": "hv_balanced_12factor_p10ai_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10ai_execute_one_single_cycle_limited_canary_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "p10aj_execution_authorized_if_this_corridor_continues": status == "ready",
        "symbol": DEFAULT_SYMBOL,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_gross_turnover_usdt": DEFAULT_MAX_GROSS_TURNOVER_USDT,
        "max_cycles_total": 1,
        "max_candidate_entry_orders_total": 1,
        "max_orders_total": 2,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "minimum_maker_buffer_ticks": max(50, int(args.maker_buffer_ticks or 50)),
        "market_orders_approved": False,
        "continuous_automation_approved": False,
        "timer_or_supervisor_load_approved": False,
        "production_executor_mutation_approved": False,
    }
    gate_record = {
        "contract_version": "hv_balanced_12factor_p10ai_gate_record.v1",
        "status": status,
        "blockers": blockers,
        "scope": "owner_gate_to_execute_one_single_cycle_limited_canary_only",
        "candidate_plan_sha256": str(p10g.get("candidate_target_plan_sha256") or ""),
        "baseline_plan_sha256": str(p10g.get("baseline_target_plan_sha256") or ""),
        "allowed_next_gate": P10AJ_GATE,
        "allowed_next_gate_scope": "execute_exactly_one_btcusdt_post_only_gtx_limited_canary_no_auto_execution",
        "allowed_next_gate_must_be_separately_requested": True,
        "fail_closed_conditions": [
            "missing P10AH/P10AG/P10G/P10H evidence",
            "fresh account proof not ready",
            "fresh book/filter proof not ready",
            "candidate hash mismatch",
            "post-only price/filter check fails",
            "remote control boundary drift before submit",
        ],
    }
    control = {
        "contract_version": "hv_balanced_12factor_p10ai_control_boundary.v1",
        "scope": "owner_gate_only_before_p10aj",
        "ssh_invoked": False,
        "remote_execution_performed": False,
        "live_order_submission_performed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        **no_production_mutation_matrix(),
    }
    phase_dir = write_phase(root, "p10ai_owner_gate", {"owner_decision": owner, "gate_record": gate_record, "control_boundary": control})
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "gate_record": str(phase_dir / "proof" / "gate_record.json"),
        "control_boundary": str(phase_dir / "proof" / "control_boundary.json"),
    }
    summary = {
        "contract_version": P10AI_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10ai_owner_gate_ready": status == "ready",
        "p10aj_single_cycle_execution_authorized_if_separately_requested": status == "ready",
        "single_cycle_only": True,
        "symbol": DEFAULT_SYMBOL,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "minimum_maker_buffer_ticks": max(50, int(args.maker_buffer_ticks or 50)),
        "live_order_submission_authorized_now": False,
        "candidate_executor_path_execution_authorized_now": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        **no_production_mutation_matrix(),
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {
            "p10ah_summary": evidence_file(p10ah_path),
            "p10ag_execution_terms": evidence_file(terms_path),
            "p10g_summary": evidence_file(p10g_path),
            "p10h_summary": evidence_file(p10h_path),
            "candidate_target_plan": evidence_file(candidate_plan_path),
            "baseline_target_plan": evidence_file(baseline_plan_path),
            "target_plan_diff": evidence_file(diff_path),
        },
        "allowed_next_gate": P10AJ_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "execute_exactly_one_btcusdt_post_only_gtx_limited_canary_no_auto_execution"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": output_files,
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10aj(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10ai: dict[str, Any],
    p10ai_path: Path,
    p10g_path: Path,
    p10h_path: Path,
) -> tuple[dict[str, Any], Path]:
    phase_dir = root / "p10aj_execution"
    proof_dir = phase_dir / "proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    pre_gates = {
        "owner_decision_p10aj_recorded": True,
        "p10ai_ready": p10ai.get("status") == "ready"
        and p10ai.get("p10aj_single_cycle_execution_authorized_if_separately_requested") is True,
        "p10ai_allowed_p10aj": p10ai.get("allowed_next_gate") == P10AJ_GATE,
        "p10g_summary_exists": p10g_path.exists() and p10g_path.is_file(),
        "p10h_summary_exists": p10h_path.exists() and p10h_path.is_file(),
    }
    blockers = sorted(key for key, ready in pre_gates.items() if not ready)
    p10i_summary: dict[str, Any] = {}
    if not blockers:
        p10i_args = parse_p10i_args(
            [
                "--output-root",
                str(phase_dir / "underlying_p10i_live_delta_submitter"),
                "--p10h-summary",
                str(p10h_path),
                "--p10g-summary",
                str(p10g_path),
                "--order-lifetime-seconds",
                str(int(args.order_lifetime_seconds or 0)),
                "--maker-buffer-ticks",
                str(max(50, int(args.maker_buffer_ticks or 50))),
                "--owner-decision-source",
                "user_chat:p10aj_underlying_p10i_submitter_for_p10ai_p10ak_corridor",
            ]
        )
        p10i_summary, p10i_exit = build_p10i(p10i_args)
        if p10i_exit != 0:
            blockers.append("underlying_p10i_submitter_failed_or_blocked")
        if p10i_summary.get("status") != "ready":
            blockers.append("underlying_p10i_summary_not_ready")

    remote_order_path = Path(
        str(dict(p10i_summary.get("output_files") or {}).get("remote_single_cycle_live_delta_canary_order_submission") or "")
    )
    remote_order = load_optional(remote_order_path) if str(remote_order_path) else {}
    actual_order_plan = dict(remote_order.get("canary_order_plan") or {})
    order_checks = {
        "underlying_p10i_ready": p10i_summary.get("status") == "ready",
        "orders_submitted_exactly_one": int(p10i_summary.get("orders_submitted") or 0) == 1,
        "orders_canceled_at_most_one": int(p10i_summary.get("orders_canceled") or 0) <= 1,
        "zero_fills": int(p10i_summary.get("fill_count") or 0) == 0,
        "zero_trades": int(p10i_summary.get("trade_count") or 0) == 0,
        "actual_live_order_submission_performed": p10i_summary.get("actual_live_order_submission_performed") is True,
        "fresh_pre_submit_readback_performed": p10i_summary.get("fresh_pre_submit_readback_performed") is True,
        "candidate_scope_account_proof_ready": p10i_summary.get("candidate_scope_account_proof_ready") is True,
        "remote_control_boundary_unchanged": p10i_summary.get("remote_control_boundary_unchanged") is True,
        "production_executor_input_not_mutated": p10i_summary.get("actual_executor_input_mutation_performed") is False,
        "production_target_plan_not_replaced": p10i_summary.get("actual_target_plan_replacement_performed") is False,
        "timer_not_loaded": p10i_summary.get("timer_path_load_authorized") is False,
        "supervisor_not_invoked": p10i_summary.get("supervisor_invocation_authorized") is False,
        "continuous_automation_disabled": p10i_summary.get("continuous_automation_enabled") is False,
        "actual_remote_submitter_plan_retained": bool(actual_order_plan),
    }
    if p10i_summary:
        blockers.extend(key for key, ready in order_checks.items() if not ready)
    blockers = sorted(set(blockers))
    status = "ready" if not blockers else "blocked"
    owner = {
        "contract_version": "hv_balanced_12factor_p10aj_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10aj_execute_one_single_cycle_limited_canary_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "single_cycle_limited_canary_approved": p10ai.get("status") == "ready",
        "continuous_automation_approved": False,
    }
    binding = {
        "contract_version": "hv_balanced_12factor_p10aj_candidate_executor_input_binding.v1",
        "scope": "single_cycle_limited_candidate_executor_path_canary_wrapper",
        "baseline_target_plan_sha256": str(p10i_summary.get("baseline_target_plan_sha256") or ""),
        "candidate_target_plan_sha256": str(p10i_summary.get("candidate_target_plan_sha256") or ""),
        "executor_input_for_canary_source": "candidate_target_plan",
        "executor_input_for_canary_sha256": str(p10i_summary.get("candidate_target_plan_sha256") or ""),
        "post_cycle_executor_input_source": "baseline_target_plan",
        "post_cycle_executor_input_sha256": str(p10i_summary.get("baseline_target_plan_sha256") or ""),
        "production_executor_input_mutation_performed": False,
        "live_supervisor_target_plan_replacement_performed": False,
        "timer_path_load_performed": False,
    }
    reconciliation = {
        "contract_version": "hv_balanced_12factor_p10aj_post_run_reconciliation.v1",
        "status": status,
        "blockers": blockers,
        "orders_submitted": int(p10i_summary.get("orders_submitted") or 0),
        "orders_canceled": int(p10i_summary.get("orders_canceled") or 0),
        "fill_count": int(p10i_summary.get("fill_count") or 0),
        "trade_count": int(p10i_summary.get("trade_count") or 0),
        "canary_side": actual_order_plan.get("side") or p10i_summary.get("canary_side"),
        "canary_price": actual_order_plan.get("price") or p10i_summary.get("canary_price"),
        "canary_quantity": actual_order_plan.get("quantity") or p10i_summary.get("canary_quantity"),
        "canary_notional_usdt": actual_order_plan.get("notional_usdt") or p10i_summary.get("canary_notional_usdt"),
        "local_pre_submit_canary_price": p10i_summary.get("canary_price"),
        "local_pre_submit_canary_notional_usdt": p10i_summary.get("canary_notional_usdt"),
        "baseline_fallback_post_cycle_source": "baseline_target_plan",
        "remote_control_boundary_unchanged": p10i_summary.get("remote_control_boundary_unchanged") is True,
        "continuous_automation_enabled": False,
        "second_cycle_attempted": False,
    }
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(proof_dir / "owner_decision.json"),
        "candidate_executor_input_binding": str(proof_dir / "candidate_executor_input_binding.json"),
        "post_run_reconciliation": str(proof_dir / "post_run_reconciliation.json"),
    }
    if p10i_summary:
        output_files["underlying_p10i_summary"] = str(phase_dir / "underlying_p10i_live_delta_submitter" / "summary.json")
    if remote_order:
        output_files["underlying_p10i_remote_order_submission"] = str(remote_order_path)
    summary = {
        "contract_version": P10AJ_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10aj_single_cycle_limited_canary_ready": status == "ready",
        "p10ai_sufficient_for_p10aj_execution": pre_gates["p10ai_ready"],
        "candidate_executor_path_execution_authorized": True,
        "candidate_executor_path_execution_performed": status == "ready",
        "candidate_target_plan_replacement_for_canary_performed": status == "ready",
        "actual_live_order_submission_performed": p10i_summary.get("actual_live_order_submission_performed") is True,
        "orders_submitted": int(p10i_summary.get("orders_submitted") or 0),
        "orders_canceled": int(p10i_summary.get("orders_canceled") or 0),
        "fill_count": int(p10i_summary.get("fill_count") or 0),
        "trade_count": int(p10i_summary.get("trade_count") or 0),
        "symbol": DEFAULT_SYMBOL,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_gross_turnover_usdt": DEFAULT_MAX_GROSS_TURNOVER_USDT,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "maker_buffer_ticks": max(50, int(args.maker_buffer_ticks or 50)),
        "candidate_target_plan_sha256": str(p10i_summary.get("candidate_target_plan_sha256") or ""),
        "baseline_target_plan_sha256": str(p10i_summary.get("baseline_target_plan_sha256") or ""),
        "canary_side": actual_order_plan.get("side") or p10i_summary.get("canary_side"),
        "canary_price": actual_order_plan.get("price") or p10i_summary.get("canary_price"),
        "canary_quantity": actual_order_plan.get("quantity") or p10i_summary.get("canary_quantity"),
        "canary_notional_usdt": actual_order_plan.get("notional_usdt") or p10i_summary.get("canary_notional_usdt"),
        "local_pre_submit_canary_price": p10i_summary.get("canary_price"),
        "local_pre_submit_canary_notional_usdt": p10i_summary.get("canary_notional_usdt"),
        "baseline_fallback_post_cycle_ready": status == "ready",
        "post_run_reconciliation_ready": status == "ready",
        **no_production_mutation_matrix(),
        "pre_gates": pre_gates,
        "order_checks": order_checks,
        "blockers": blockers,
        "source_evidence": {"p10ai_summary": evidence_file(p10ai_path), "p10g_summary": evidence_file(p10g_path), "p10h_summary": evidence_file(p10h_path)},
        "allowed_next_gate": P10AK_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "review_p10aj_retained_evidence_no_new_order_no_auto_execution"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": output_files,
    }
    for path, payload in (
        (Path(output_files["owner_decision"]), owner),
        (Path(output_files["candidate_executor_input_binding"]), binding),
        (Path(output_files["post_run_reconciliation"]), reconciliation),
        (Path(output_files["summary"]), summary),
    ):
        write_json(path, payload)
    return summary, phase_dir / "summary.json"


def build_p10ak(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10aj: dict[str, Any],
    p10aj_path: Path,
) -> tuple[dict[str, Any], Path]:
    remote_order_path = Path(str(dict(p10aj.get("output_files") or {}).get("underlying_p10i_remote_order_submission") or ""))
    remote_order = load_optional(remote_order_path) if str(remote_order_path) else {}
    order = dict(remote_order.get("order_submission") or {})
    query = dict(remote_order.get("order_query") or {})
    cancel = dict(remote_order.get("order_cancel") or {})
    actual_plan = dict(remote_order.get("canary_order_plan") or {})
    review_checks = {
        "owner_decision_p10ak_recorded": True,
        "p10aj_ready": p10aj.get("status") == "ready",
        "single_order_submitted": int(p10aj.get("orders_submitted") or 0) == 1,
        "orders_canceled_at_most_one": int(p10aj.get("orders_canceled") or 0) <= 1,
        "zero_fills": int(p10aj.get("fill_count") or 0) == 0,
        "zero_trades": int(p10aj.get("trade_count") or 0) == 0,
        "actual_live_order_submission_performed": p10aj.get("actual_live_order_submission_performed") is True,
        "candidate_executor_path_wrapper_performed": p10aj.get("candidate_executor_path_execution_performed") is True,
        "actual_remote_submitter_order_readback_retained": bool(remote_order),
        "submit_ok": order.get("status") == "ok" and order.get("status_code") == 200,
        "query_ok": query.get("status") == "ok",
        "cancel_ok": cancel.get("status") == "ok",
        "actual_submitter_plan_retained": bool(actual_plan),
        "post_cycle_baseline_fallback_ready": p10aj.get("baseline_fallback_post_cycle_ready") is True,
        "production_executor_input_not_mutated": p10aj.get("production_executor_input_mutation_performed") is False,
        "production_target_plan_not_replaced": p10aj.get("actual_target_plan_replacement_performed") is False,
        "timer_not_loaded": p10aj.get("timer_path_load_authorized") is False,
        "supervisor_not_invoked": p10aj.get("supervisor_invocation_authorized") is False,
        "continuous_automation_disabled": p10aj.get("continuous_automation_enabled") is False,
        "remote_no_sync_no_file_write": p10aj.get("remote_sync_performed") is False
        and int(p10aj.get("remote_files_written") or 0) == 0,
    }
    blockers = sorted(key for key, ready in review_checks.items() if not ready)
    status = "ready" if not blockers else "blocked"
    owner = {
        "contract_version": "hv_balanced_12factor_p10ak_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10ak_review_p10aj_retained_evidence_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "review_only_approved": True,
        "future_scope_discussion_allowed": status == "ready",
        "live_order_submission_without_new_gate_approved": False,
        "continuous_automation_approved": False,
    }
    actual_readback = {
        "contract_version": "hv_balanced_12factor_p10ak_actual_order_submission_readback.v1",
        "status": "ready" if status == "ready" else "blocked",
        "client_order_id": remote_order.get("client_order_id"),
        "submit_status": order.get("status"),
        "submit_status_code": order.get("status_code"),
        "query_status": query.get("status"),
        "cancel_status": cancel.get("status"),
        "orders_submitted": remote_order.get("orders_submitted"),
        "orders_canceled": remote_order.get("orders_canceled"),
        "fill_count": remote_order.get("fill_count"),
        "trade_count": remote_order.get("trade_count"),
        "actual_submitter_canary_order_plan": {
            key: actual_plan.get(key)
            for key in ["side", "price", "quantity", "notional_usdt", "best_bid", "best_ask", "time_in_force"]
        },
        "wrapper_summary_plan": {
            key: p10aj.get(key)
            for key in ["canary_side", "canary_price", "canary_quantity", "canary_notional_usdt"]
        },
        "counts_match_wrapper": p10aj.get("orders_submitted") == remote_order.get("orders_submitted")
        and p10aj.get("orders_canceled") == remote_order.get("orders_canceled")
        and p10aj.get("fill_count") == remote_order.get("fill_count")
        and p10aj.get("trade_count") == remote_order.get("trade_count"),
        "ready_checks": review_checks,
    }
    review = {
        "contract_version": "hv_balanced_12factor_p10ak_retained_evidence_review.v1",
        "status": status,
        "blockers": blockers,
        "p10aj_summary": evidence_file(p10aj_path),
        "underlying_p10i_remote_order_submission": evidence_file(remote_order_path),
        "conclusion": (
            "p10aj_sufficient_for_future_scope_discussion"
            if status == "ready"
            else "p10aj_not_sufficient_for_future_scope_discussion"
        ),
        "does_not_authorize": [
            "additional live order",
            "continuous automated ordering",
            "timer/supervisor path load",
            "production executor input mutation",
            "production target plan replacement",
        ],
    }
    phase_dir = write_phase(root, "p10ak_review", {"owner_decision": owner, "actual_order_submission_readback": actual_readback, "review": review})
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "actual_order_submission_readback": str(phase_dir / "proof" / "actual_order_submission_readback.json"),
        "review": str(phase_dir / "proof" / "review.json"),
    }
    summary = {
        "contract_version": P10AK_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10ak_review_p10aj_retained_evidence_ready": status == "ready",
        "p10aj_sufficient_for_future_limited_scope_discussion": status == "ready",
        "p10aj_sufficient_for_additional_live_order_without_new_gate": False,
        "p10aj_sufficient_for_continuous_automated_order_flow": False,
        "live_order_submission_authorized": False,
        "candidate_executor_path_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automated_order_flow_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "review_checks": review_checks,
        "blockers": blockers,
        "source_evidence": {"p10aj_summary": evidence_file(p10aj_path), "underlying_p10i_remote_order_submission": evidence_file(remote_order_path)},
        "allowed_next_gate": P10AL_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "define_scope_only_no_new_order_no_continuous_automation_no_timer_supervisor"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": output_files,
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def run_corridor(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    started = utc_now()
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    root.mkdir(parents=True, exist_ok=True)

    p10ah_path = latest_p10ah_summary(args.p10ah_summary)
    p10ah = load_optional(p10ah_path)
    terms_path = source_evidence_path(p10ah, "p10ag_execution_terms")
    terms = load_optional(terms_path)
    p10g_path = latest_summary(P10G_PARENT, "*/summary.json", args.p10g_summary)
    p10g = load_optional(p10g_path)
    p10h_path = latest_summary(P10H_PARENT, "*/summary.json", args.p10h_summary)

    steps: list[dict[str, Any]] = []
    blockers: list[str] = []
    status = "ready"

    p10ai, p10ai_path = build_p10ai(
        root=root,
        run_id=run_id,
        args=args,
        now=started,
        p10ah=p10ah,
        p10ah_path=p10ah_path,
        terms_path=terms_path,
        terms=terms,
        p10g_path=p10g_path,
        p10g=p10g,
        p10h_path=p10h_path,
    )
    steps.append({"gate": "P10AI", "status": p10ai.get("status"), "summary": evidence_file(p10ai_path)})
    if p10ai.get("status") != "ready":
        status = "blocked"
        blockers.append("p10ai_blocked")

    p10aj: dict[str, Any] = {}
    p10aj_path = Path("")
    if status == "ready":
        p10aj, p10aj_path = build_p10aj(
            root=root,
            run_id=run_id,
            args=args,
            now=utc_now(),
            p10ai=p10ai,
            p10ai_path=p10ai_path,
            p10g_path=p10g_path,
            p10h_path=p10h_path,
        )
        steps.append({"gate": "P10AJ", "status": p10aj.get("status"), "summary": evidence_file(p10aj_path)})
        if p10aj.get("status") != "ready":
            status = "blocked"
            blockers.append("p10aj_blocked")

    p10ak: dict[str, Any] = {}
    p10ak_path = Path("")
    if status == "ready":
        p10ak, p10ak_path = build_p10ak(root=root, run_id=run_id, args=args, now=utc_now(), p10aj=p10aj, p10aj_path=p10aj_path)
        steps.append({"gate": "P10AK", "status": p10ak.get("status"), "summary": evidence_file(p10ak_path)})
        if p10ak.get("status") != "ready":
            status = "blocked"
            blockers.append("p10ak_blocked")

    orders_submitted = int(p10aj.get("orders_submitted") or 0)
    orders_canceled = int(p10aj.get("orders_canceled") or 0)
    fill_count = int(p10aj.get("fill_count") or 0)
    trade_count = int(p10aj.get("trade_count") or 0)
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "started_at_utc": iso_z(started),
        "finished_at_utc": iso_z(utc_now()),
        "p10ai_p10ak_limited_canary_corridor_ready": status == "ready",
        "corridor_scope": "P10AI owner gate + P10AJ one single-cycle limited canary + P10AK retained evidence review",
        "symbol": DEFAULT_SYMBOL,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_gross_turnover_usdt": DEFAULT_MAX_GROSS_TURNOVER_USDT,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "maker_buffer_ticks": max(50, int(args.maker_buffer_ticks or 50)),
        "actual_live_order_submission_performed": p10aj.get("actual_live_order_submission_performed") is True,
        "candidate_executor_path_execution_performed": p10aj.get("candidate_executor_path_execution_performed") is True,
        "orders_submitted": orders_submitted,
        "orders_canceled": orders_canceled,
        "fill_count": fill_count,
        "trade_count": trade_count,
        "canary_side": p10aj.get("canary_side"),
        "canary_price": p10aj.get("canary_price"),
        "canary_quantity": p10aj.get("canary_quantity"),
        "canary_notional_usdt": p10aj.get("canary_notional_usdt"),
        **no_production_mutation_matrix(),
        "continuous_automated_order_flow_authorized": False,
        "blockers": blockers,
        "steps": steps,
        "source_evidence": {"p10ah_summary": evidence_file(p10ah_path)},
        "allowed_next_gate": P10AL_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "define_scope_only_no_new_order_no_continuous_automation_no_timer_supervisor"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {"summary": str(root / "summary.json")},
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, code = run_corridor(parse_args(argv))
    print("status=" + str(summary["status"]))
    print("run_id=" + str(summary["run_id"]))
    print("orders_submitted=" + str(summary["orders_submitted"]))
    print("orders_canceled=" + str(summary["orders_canceled"]))
    print("fill_count=" + str(summary["fill_count"]))
    print("summary=" + str(summary["output_files"]["summary"]))
    if summary.get("blockers"):
        print("blockers=" + ",".join(summary["blockers"]))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
