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

from scripts.live_trading.run_hv_balanced_12factor_p10m_p10p_bundled_corridor import (  # noqa: E402
    DEFAULT_MAX_GROSS_TURNOVER_USDT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_ORDER_TYPE,
    DEFAULT_SYMBOL,
    DEFAULT_TIME_IN_FORCE,
)
from scripts.live_trading.run_hv_balanced_12factor_p10t_p10v_execution_terms_corridor import (  # noqa: E402
    P10V_CONTRACT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10w_p10y_execution_readiness_corridor.v1"
P10W_CONTRACT = "hv_balanced_12factor_p10w_owner_gate_allow_prepare_execution_readiness.v1"
P10X_CONTRACT = "hv_balanced_12factor_p10x_prepare_execution_readiness_package.v1"
P10Y_CONTRACT = "hv_balanced_12factor_p10y_review_execution_readiness_package.v1"

DEFAULT_P10V_SEARCH_PARENT = "artifacts/live_trading/proof_artifacts/p10t_p10v_execution_terms_corridor"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/proof_artifacts/p10w_p10y_execution_readiness_corridor"

P10W_GATE = "P10W_owner_gate_allow_single_cycle_candidate_executor_path_followup_execution_only_if_separately_requested"
P10X_GATE = "P10X_prepare_single_cycle_candidate_executor_path_followup_execution_readiness_package_only_if_separately_requested"
P10Y_GATE = "P10Y_review_p10x_execution_readiness_package_only_if_separately_requested"
P10Z_GATE = "P10Z_owner_gate_execute_single_cycle_candidate_executor_path_followup_canary_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the P10W-P10Y execution-readiness corridor after retained P10V. "
            "This is proof-artifacts-only: it records an owner gate, prepares a "
            "readiness package for a future separately requested single-cycle "
            "candidate executor-path canary, and reviews that package. It does "
            "not SSH, invoke supervisor/timer paths, mutate live config, mutate "
            "executor input, replace production target plans, execute candidate "
            "logic, or submit/cancel orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--p10v-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:continue_next_bundled_gates_after_p10v",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def latest_p10v_summary(explicit: str = "") -> Path:
    if str(explicit or "").strip():
        return resolve_path(explicit)
    return latest_match(DEFAULT_P10V_SEARCH_PARENT, "*/p10v_review/summary.json")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root or "").strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def source_evidence_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("source_evidence") or {}).get(key, {}).get("path") or "")
    return resolve_path(text) if text.strip() else Path("")


def p10v_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P10V_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10v_review_future_execution_terms_package_ready") is True
        and summary.get("p10u_sufficient_for_future_p10w_owner_gate") is True
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_executor_path_execution_authorized") is False
        and summary.get("target_plan_replacement_authorized") is False
        and summary.get("executor_input_mutation_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("supervisor_invocation_authorized") is False
        and summary.get("continuous_automated_order_flow_authorized") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("orders_canceled") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
        and int(summary.get("trade_count") or 0) == 0
        and summary.get("allowed_next_gate") == P10W_GATE
        and summary.get("allowed_next_gate_scope") == "owner_gate_only_to_decide_single_cycle_execution_no_auto_execution"
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def write_phase(root: Path, name: str, payloads: dict[str, dict[str, Any]]) -> Path:
    phase_dir = root / name
    proof_dir = phase_dir / "proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    for key, payload in payloads.items():
        write_json(proof_dir / f"{key}.json", payload)
    return phase_dir


def build_control(contract: str, scope: str) -> dict[str, Any]:
    return {
        "contract_version": contract,
        "scope": scope,
        "ssh_invoked": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "live_config_mutated": False,
        "operator_state_mutated": False,
        "timer_state_mutated": False,
        "supervisor_invoked": False,
        "timer_path_loaded": False,
        "candidate_execution_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "live_order_submission_performed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def not_authorized_matrix() -> dict[str, Any]:
    return {
        "live_order_submission_authorized": False,
        "candidate_executor_path_execution_authorized": False,
        "candidate_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_execution_authorized": False,
        "remote_sync_authorized": False,
        "live_config_mutation_authorized": False,
        "operator_state_mutation_authorized": False,
        "continuous_automated_order_flow_authorized": False,
    }


def no_side_effects() -> dict[str, Any]:
    return {
        "proof_artifacts_only": True,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "live_order_submission_performed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def load_p10u_terms(p10v: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    terms_path = source_evidence_path(p10v, "p10u_terms")
    return terms_path, load_optional(terms_path) if str(terms_path) else {}


def build_p10w(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10v: dict[str, Any],
    p10v_path: Path,
) -> tuple[dict[str, Any], Path]:
    terms_path, terms = load_p10u_terms(p10v)
    gates = {
        "owner_decision_p10w_recorded": True,
        "p10v_ready_for_p10w": p10v_ready(p10v),
        "p10v_terms_source_exists": terms_path.exists() and terms_path.is_file(),
        "terms_symbol_btcusdt": terms.get("symbol") == DEFAULT_SYMBOL,
        "terms_post_only_gtx": terms.get("order_type") == DEFAULT_ORDER_TYPE
        and terms.get("time_in_force") == DEFAULT_TIME_IN_FORCE,
        "terms_max_notional_75": float(terms.get("max_notional_usdt") or 0.0) == DEFAULT_MAX_NOTIONAL_USDT,
        "owner_gate_only": True,
        "execution_deferred_to_future_p10z": True,
        "no_execution_authorized": True,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"
    owner = {
        "contract_version": "hv_balanced_12factor_p10w_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10w_allow_prepare_single_cycle_execution_readiness_package_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "p10x_readiness_package_preparation_approved": status == "ready",
        "single_cycle_execution_approved_in_p10w": False,
        "live_order_submission_approved": False,
        "candidate_executor_path_execution_approved": False,
        "continuous_automation_approved": False,
    }
    gate_record = {
        "contract_version": "hv_balanced_12factor_p10w_gate_record.v1",
        "status": status,
        "source_allowed_gate": P10W_GATE,
        "source_allowed_gate_scope": "owner_gate_only_to_decide_single_cycle_execution_no_auto_execution",
        "narrowed_current_scope": "prepare_future_execution_readiness_package_only",
        "allowed_next_gate": P10X_GATE,
        "allowed_next_gate_scope": "prepare_execution_readiness_package_only_no_ssh_no_order_no_timer",
        "allowed_next_gate_must_be_separately_requested": True,
        "explicit_defer_to_future_execution_gate": P10Z_GATE,
        "does_not_authorize": [
            "live order submission",
            "candidate executor-path execution",
            "production target plan replacement",
            "executor input mutation",
            "timer path load",
            "supervisor invocation",
            "remote sync",
            "continuous automated order flow",
        ],
    }
    control = build_control("hv_balanced_12factor_p10w_control_boundary.v1", "owner_gate_readiness_only")
    phase_dir = write_phase(
        root,
        "p10w_owner_gate",
        {"owner_decision": owner, "gate_record": gate_record, "control_boundary": control},
    )
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "gate_record": str(phase_dir / "proof" / "gate_record.json"),
        "control_boundary": str(phase_dir / "proof" / "control_boundary.json"),
    }
    summary = {
        "contract_version": P10W_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10w_owner_gate_ready": status == "ready",
        "p10w_allows_p10x_readiness_package_only": status == "ready",
        "single_cycle_execution_decision_deferred_to_future_p10z": True,
        **not_authorized_matrix(),
        **no_side_effects(),
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {"p10v_summary": evidence_file(p10v_path), "p10u_terms": evidence_file(terms_path)},
        "allowed_next_gate": P10X_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "prepare_execution_readiness_package_only_no_ssh_no_order_no_timer"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": output_files,
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10x(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10w: dict[str, Any],
    p10w_path: Path,
) -> tuple[dict[str, Any], Path]:
    gates = {
        "owner_decision_p10x_recorded": True,
        "p10w_ready": p10w.get("status") == "ready" and p10w.get("p10w_allows_p10x_readiness_package_only") is True,
        "p10w_allowed_p10x": p10w.get("allowed_next_gate") == P10X_GATE,
        "package_only": True,
        "no_execution_authorized": True,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"
    readiness_package = {
        "contract_version": "hv_balanced_12factor_p10x_execution_readiness_package.v1",
        "status": status,
        "package_status": "prepared_for_future_separately_requested_execution_owner_gate_only",
        "future_gate": P10Z_GATE,
        "future_execution_shape": "one_single_cycle_candidate_executor_path_followup_canary",
        "terms": {
            "symbol": DEFAULT_SYMBOL,
            "max_symbols_total": 1,
            "max_cycles_total": 1,
            "continuous_automation": False,
            "max_candidate_entry_orders_total": 1,
            "max_reduce_only_rollback_orders_total": 1,
            "max_orders_total": 2,
            "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
            "max_gross_turnover_usdt": DEFAULT_MAX_GROSS_TURNOVER_USDT,
            "order_type": DEFAULT_ORDER_TYPE,
            "time_in_force": DEFAULT_TIME_IN_FORCE,
            "market_orders_allowed": False,
            "maker_only_required": True,
            "post_only_required": True,
            "taker_execution_allowed": False,
        },
        "fresh_or_retained_hash_binding_required_before_future_execution": [
            "candidate plan hash must equal fresh P10G rerun or retained P10G hash accepted by owner",
            "baseline fallback hash must be retained before submission",
            "submitted order client id must bind run id and candidate plan hash prefix",
        ],
        "fresh_proofs_required_at_future_execution_time": [
            "/fapi/v2/account.canTrade true; /fapi/v3 canTrade ignored for permission decision",
            "pre-submit open orders count and fingerprint",
            "pre-submit order/fill/trade baseline",
            "pre-submit position and balance candidate-scope fingerprint",
            "fresh BTCUSDT best bid/ask and exchange filters",
            "post-only non-crossing limit price with maker buffer and min-notional check",
            "static remote control boundary readback before any order",
        ],
        "fail_closed_baseline_fallback": [
            "any proof missing or stale keeps executor baseline-only",
            "any candidate plan hash mismatch submits zero candidate orders",
            "any post-only price/filter failure submits zero candidate orders",
            "any remote control-boundary drift submits zero candidate orders",
        ],
        "kill_switch_and_rollback": [
            "candidate_live_delta_enabled=false",
            "executor_target_source=baseline_only",
            "cancel open candidate order if accepted and unfilled",
            "reduce-only close only if filled and separately owner-approved by the canary terms",
        ],
        "post_run_reconciliation_required": [
            "accepted/rejected/canceled order status retained",
            "executedQty, fill count, and trade count retained",
            "pre/post order/cancel/fill/trade deltas retained",
            "pre/post candidate-scope position and balance fingerprints retained",
            "post-cycle executor source remains or reverts to baseline-only",
            "live config/operator/timer/supervisor/static boundary unchanged",
        ],
        "not_authorized_by_p10x": [
            "live order submission",
            "candidate executor-path execution",
            "production target plan replacement",
            "executor input mutation",
            "timer path load",
            "supervisor invocation",
            "remote sync",
            "continuous automated order flow",
        ],
    }
    owner = {
        "contract_version": "hv_balanced_12factor_p10x_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10x_prepare_execution_readiness_package_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "readiness_package_preparation_approved": status == "ready",
        "live_order_submission_approved": False,
        "candidate_executor_path_execution_approved": False,
        "continuous_automation_approved": False,
    }
    control = build_control("hv_balanced_12factor_p10x_control_boundary.v1", "readiness_package_only")
    phase_dir = write_phase(
        root,
        "p10x_readiness_package",
        {"owner_decision": owner, "readiness_package": readiness_package, "control_boundary": control},
    )
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "readiness_package": str(phase_dir / "proof" / "readiness_package.json"),
        "control_boundary": str(phase_dir / "proof" / "control_boundary.json"),
    }
    summary = {
        "contract_version": P10X_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10x_execution_readiness_package_ready": status == "ready",
        "readiness_package_only": True,
        "eligible_for_p10y_review": status == "ready",
        "future_gate": P10Z_GATE,
        "symbol": DEFAULT_SYMBOL,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_gross_turnover_usdt": DEFAULT_MAX_GROSS_TURNOVER_USDT,
        "max_cycles_total": 1,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        **not_authorized_matrix(),
        **no_side_effects(),
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {"p10w_summary": evidence_file(p10w_path)},
        "allowed_next_gate": P10Y_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "review_execution_readiness_package_only_no_ssh_no_order_no_timer"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": output_files,
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10y(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10x: dict[str, Any],
    p10x_path: Path,
) -> tuple[dict[str, Any], Path]:
    package_path = Path(str(dict(p10x.get("output_files") or {}).get("readiness_package") or ""))
    package = load_optional(package_path) if str(package_path) else {}
    terms = dict(package.get("terms") or {})
    gates = {
        "owner_decision_p10y_recorded": True,
        "p10x_ready": p10x.get("status") == "ready" and p10x.get("p10x_execution_readiness_package_ready") is True,
        "p10x_allowed_p10y": p10x.get("allowed_next_gate") == P10Y_GATE,
        "readiness_package_exists": package_path.exists() and package_path.is_file(),
        "terms_symbol_btcusdt": terms.get("symbol") == DEFAULT_SYMBOL,
        "terms_max_notional_75": float(terms.get("max_notional_usdt") or 0.0) == DEFAULT_MAX_NOTIONAL_USDT,
        "terms_single_cycle": int(terms.get("max_cycles_total") or 0) == 1
        and terms.get("continuous_automation") is False,
        "terms_post_only_gtx": terms.get("order_type") == DEFAULT_ORDER_TYPE
        and terms.get("time_in_force") == DEFAULT_TIME_IN_FORCE,
        "review_only": True,
        "no_execution_authorized": True,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"
    review = {
        "contract_version": "hv_balanced_12factor_p10y_readiness_review.v1",
        "status": status,
        "blockers": blockers,
        "p10x_summary": evidence_file(p10x_path),
        "p10x_readiness_package": evidence_file(package_path),
        "p10x_package_sufficient_for_p10y_review": status == "ready",
        "p10x_package_sufficient_to_open_future_p10z_owner_execution_gate": status == "ready",
        "p10x_package_sufficient_for_live_order_submission_without_p10z": False,
        "p10x_package_sufficient_for_continuous_automation": False,
        "remaining_required_gate_before_any_future_order": P10Z_GATE,
        "future_p10z_must_collect_or_rebind": [
            "explicit owner decision to execute exactly one single-cycle canary",
            "fresh or owner-accepted candidate plan hash",
            "fresh account/book/filter/order/fill/trade/control proofs at execution time",
            "post-run reconciliation and baseline fallback evidence",
        ],
        "does_not_authorize": [
            "live order submission",
            "candidate executor-path execution",
            "production target plan replacement",
            "executor input mutation",
            "timer path load",
            "supervisor invocation",
            "remote sync",
            "continuous automated order flow",
        ],
    }
    owner = {
        "contract_version": "hv_balanced_12factor_p10y_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10y_review_execution_readiness_package_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "review_only_approved": True,
        "future_p10z_owner_execution_gate_may_be_requested": status == "ready",
        "live_order_submission_approved": False,
        "candidate_executor_path_execution_approved": False,
        "continuous_automation_approved": False,
    }
    control = build_control("hv_balanced_12factor_p10y_control_boundary.v1", "readiness_review_only")
    phase_dir = write_phase(
        root,
        "p10y_review",
        {"owner_decision": owner, "review": review, "control_boundary": control},
    )
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "review": str(phase_dir / "proof" / "review.json"),
        "control_boundary": str(phase_dir / "proof" / "control_boundary.json"),
    }
    summary = {
        "contract_version": P10Y_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10y_review_execution_readiness_package_ready": status == "ready",
        "p10x_package_sufficient_for_future_p10z_owner_execution_gate": status == "ready",
        "p10x_package_sufficient_for_live_order_submission_without_p10z": False,
        "review_only": True,
        "future_gate": P10Z_GATE,
        **not_authorized_matrix(),
        **no_side_effects(),
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {"p10x_summary": evidence_file(p10x_path), "p10x_readiness_package": evidence_file(package_path)},
        "allowed_next_gate": P10Z_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "owner_gate_to_execute_one_single_cycle_only_no_auto_execution"
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
    p10v_path = latest_p10v_summary(args.p10v_summary)
    p10v = load_optional(p10v_path)

    steps: list[dict[str, Any]] = []
    blockers: list[str] = []
    status = "ready"

    p10w, p10w_path = build_p10w(root=root, run_id=run_id, args=args, now=started, p10v=p10v, p10v_path=p10v_path)
    steps.append({"gate": "P10W", "status": p10w.get("status"), "summary": evidence_file(p10w_path)})
    if p10w.get("status") != "ready":
        status = "blocked"
        blockers.append("p10w_blocked")

    p10x: dict[str, Any] = {}
    p10x_path = Path("")
    if status == "ready":
        p10x, p10x_path = build_p10x(root=root, run_id=run_id, args=args, now=started, p10w=p10w, p10w_path=p10w_path)
        steps.append({"gate": "P10X", "status": p10x.get("status"), "summary": evidence_file(p10x_path)})
        if p10x.get("status") != "ready":
            status = "blocked"
            blockers.append("p10x_blocked")

    p10y: dict[str, Any] = {}
    p10y_path = Path("")
    if status == "ready":
        p10y, p10y_path = build_p10y(root=root, run_id=run_id, args=args, now=started, p10x=p10x, p10x_path=p10x_path)
        steps.append({"gate": "P10Y", "status": p10y.get("status"), "summary": evidence_file(p10y_path)})
        if p10y.get("status") != "ready":
            status = "blocked"
            blockers.append("p10y_blocked")

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "started_at_utc": iso_z(started),
        "finished_at_utc": iso_z(utc_now()),
        "p10w_p10y_execution_readiness_corridor_ready": status == "ready",
        "corridor_scope": "P10W owner gate + P10X execution-readiness package + P10Y readiness review",
        "future_gate_after_corridor": P10Z_GATE if status == "ready" else "",
        "future_gate_scope": "owner_gate_to_execute_one_single_cycle_only_no_auto_execution" if status == "ready" else "",
        **not_authorized_matrix(),
        **no_side_effects(),
        "blockers": blockers,
        "steps": steps,
        "source_evidence": {"p10v_summary": evidence_file(p10v_path)},
        "allowed_next_gate": P10Z_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "owner_gate_to_execute_one_single_cycle_only_no_auto_execution"
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
    print("fill_count=" + str(summary["fill_count"]))
    print("summary=" + str(summary["output_files"]["summary"]))
    if summary.get("blockers"):
        print("blockers=" + ",".join(summary["blockers"]))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
