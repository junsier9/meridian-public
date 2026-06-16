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
from scripts.live_trading.run_hv_balanced_12factor_p10q_p10s_followup_proposal_corridor import (  # noqa: E402
    P10S_CONTRACT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10t_p10v_execution_terms_corridor.v1"
P10T_CONTRACT = "hv_balanced_12factor_p10t_allow_prepare_execution_terms_owner_gate.v1"
P10U_CONTRACT = "hv_balanced_12factor_p10u_prepare_future_execution_terms_package.v1"
P10V_CONTRACT = "hv_balanced_12factor_p10v_review_future_execution_terms_package.v1"

DEFAULT_P10S_SEARCH_PARENT = "artifacts/live_trading/proof_artifacts/p10q_p10s_followup_proposal_corridor"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/proof_artifacts/p10t_p10v_execution_terms_corridor"

P10T_GATE = "P10T_allow_prepare_limited_live_delta_candidate_executor_path_followup_execution_gate_only_if_separately_requested"
P10U_GATE = "P10U_prepare_limited_live_delta_candidate_executor_path_followup_execution_terms_only_if_separately_requested"
P10V_GATE = "P10V_review_p10u_execution_terms_package_only_if_separately_requested"
P10W_GATE = "P10W_owner_gate_allow_single_cycle_candidate_executor_path_followup_execution_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run P10T-P10V after retained P10S. This corridor records an owner "
            "gate that permits preparing future execution terms, prepares those "
            "terms, and reviews them. It does not SSH, submit/cancel orders, "
            "load timer/supervisor paths, mutate executor input, replace target "
            "plans, sync remote files, or authorize continuous automation."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--p10s-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:continue_next_bundled_gates_after_p10s",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def latest_p10s_summary(explicit: str = "") -> Path:
    if str(explicit or "").strip():
        return resolve_path(explicit)
    return latest_match(DEFAULT_P10S_SEARCH_PARENT, "*/p10s_review/summary.json")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root or "").strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def source_evidence_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("source_evidence") or {}).get(key, {}).get("path") or "")
    return resolve_path(text) if text.strip() else Path("")


def p10s_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P10S_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10s_review_followup_proposal_package_ready") is True
        and summary.get("p10r_sufficient_for_future_p10t_owner_gate") is True
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_executor_path_execution_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("continuous_automated_order_flow_authorized") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
        and int(summary.get("trade_count") or 0) == 0
        and summary.get("allowed_next_gate") == P10T_GATE
        and summary.get("allowed_next_gate_scope")
        == "owner_gate_only_to_allow_preparing_future_execution_terms_no_execution_no_order"
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
        "live_order_submission_performed": False,
        "candidate_execution_performed": False,
        "target_plan_replaced": False,
        "executor_input_changed": False,
        "timer_path_loaded": False,
        "supervisor_invoked": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def build_p10t(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10s: dict[str, Any],
    p10s_path: Path,
) -> tuple[dict[str, Any], Path]:
    p10r_path = source_evidence_path(p10s, "p10r_summary")
    gates = {
        "owner_decision_p10t_recorded": True,
        "p10s_ready": p10s_ready(p10s),
        "source_p10r_exists": p10r_path.exists(),
        "owner_gate_only": True,
        "no_execution_authorized": True,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"
    owner = {
        "contract_version": "hv_balanced_12factor_p10t_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10t_allow_prepare_future_execution_terms_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "prepare_future_execution_terms_approved": status == "ready",
        "execute_terms_inside_p10t": False,
        "live_order_submission_approved": False,
        "candidate_executor_path_execution_approved": False,
        "continuous_automation_approved": False,
    }
    gate_record = {
        "contract_version": "hv_balanced_12factor_p10t_gate_record.v1",
        "status": status,
        "scope": "owner_gate_only_to_allow_preparing_future_execution_terms",
        "allowed_next_gate": P10U_GATE,
        "allowed_next_gate_scope": "prepare_terms_package_only_no_execution_no_order_no_timer",
        "does_not_authorize": [
            "live order submission",
            "candidate execution",
            "target plan replacement",
            "executor input mutation",
            "timer path load",
            "supervisor invocation",
            "remote sync",
            "continuous automated order flow",
        ],
    }
    control = build_control("hv_balanced_12factor_p10t_control_boundary.v1", "owner_gate_only")
    phase_dir = write_phase(root, "p10t_owner_gate", {"owner_decision": owner, "gate_record": gate_record, "control_boundary": control})
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "gate_record": str(phase_dir / "proof" / "gate_record.json"),
        "control_boundary": str(phase_dir / "proof" / "control_boundary.json"),
    }
    summary = {
        "contract_version": P10T_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10t_allow_prepare_execution_terms_owner_gate_ready": status == "ready",
        "owner_gate_only": True,
        "future_p10u_terms_package_authorized_if_separately_requested": status == "ready",
        "live_order_submission_authorized": False,
        "candidate_executor_path_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automated_order_flow_authorized": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {"p10s_summary": evidence_file(p10s_path), "p10r_summary": evidence_file(p10r_path)},
        "allowed_next_gate": P10U_GATE,
        "allowed_next_gate_scope": "prepare_terms_package_only_no_execution_no_order_no_timer",
        "allowed_next_gate_must_be_separately_requested": True,
        "output_files": output_files,
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10u(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10t: dict[str, Any],
    p10t_path: Path,
) -> tuple[dict[str, Any], Path]:
    gates = {
        "owner_decision_p10u_recorded": True,
        "p10t_ready": p10t.get("status") == "ready"
        and p10t.get("future_p10u_terms_package_authorized_if_separately_requested") is True,
        "p10t_allowed_p10u": p10t.get("allowed_next_gate") == P10U_GATE,
        "terms_package_only": True,
        "no_execution_authorized": True,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"
    terms = {
        "contract_version": "hv_balanced_12factor_p10u_future_execution_terms_package.v1",
        "terms_status": "prepared_for_future_owner_review_only",
        "future_execution_shape": "single_cycle_candidate_executor_path_followup_canary",
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
        "candidate_delta_source": "12factor_scorer_candidate_target_plan",
        "candidate_plan_hash_binding": "fresh P10G or retained P10G hash plus fresh pre-submit proof required",
        "baseline_fallback": "any failed proof keeps executor baseline-only and submits zero candidate orders",
        "kill_switch": "candidate_live_delta_enabled=false / executor_target_source=baseline_only",
        "rollback": "cancel open candidate order; reduce-only close only if filled and separately owner-approved",
        "required_fresh_proofs_before_future_execution": [
            "/fapi/v2/account.canTrade true",
            "candidate-scope open-order/order/fill/trade baseline",
            "fresh BTCUSDT book and exchange filters",
            "candidate target plan hash equals owner-approved hash",
            "post-only non-crossing limit price with maker buffer",
            "static remote control boundary unchanged",
        ],
        "required_post_run_reconciliation": [
            "order accepted or fail-closed reason retained",
            "cancel status retained if accepted and unfilled",
            "executed quantity, fill count, and trade count retained",
            "post-cycle executor source reverts to baseline hash",
            "remote config/operator/static control boundary unchanged",
        ],
        "does_not_authorize_execution": True,
    }
    owner = {
        "contract_version": "hv_balanced_12factor_p10u_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10u_prepare_future_execution_terms_package_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "terms_package_preparation_approved": status == "ready",
        "live_order_submission_approved": False,
        "candidate_execution_approved": False,
        "continuous_automation_approved": False,
    }
    control = build_control("hv_balanced_12factor_p10u_control_boundary.v1", "terms_package_only")
    phase_dir = write_phase(root, "p10u_terms_package", {"owner_decision": owner, "execution_terms": terms, "control_boundary": control})
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "execution_terms": str(phase_dir / "proof" / "execution_terms.json"),
        "control_boundary": str(phase_dir / "proof" / "control_boundary.json"),
    }
    summary = {
        "contract_version": P10U_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10u_future_execution_terms_package_ready": status == "ready",
        "terms_package_only": True,
        "eligible_for_p10v_review": status == "ready",
        "symbol": DEFAULT_SYMBOL,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_gross_turnover_usdt": DEFAULT_MAX_GROSS_TURNOVER_USDT,
        "max_cycles_total": 1,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        "live_order_submission_authorized": False,
        "candidate_executor_path_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automated_order_flow_authorized": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {"p10t_summary": evidence_file(p10t_path)},
        "allowed_next_gate": P10V_GATE,
        "allowed_next_gate_scope": "review_terms_package_only_no_execution_no_order_no_timer",
        "allowed_next_gate_must_be_separately_requested": True,
        "output_files": output_files,
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10v(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10u: dict[str, Any],
    p10u_path: Path,
) -> tuple[dict[str, Any], Path]:
    terms_path = Path(str(dict(p10u.get("output_files") or {}).get("execution_terms") or ""))
    terms = load_optional(terms_path) if str(terms_path) else {}
    gates = {
        "owner_decision_p10v_recorded": True,
        "p10u_ready": p10u.get("status") == "ready" and p10u.get("p10u_future_execution_terms_package_ready") is True,
        "p10u_allowed_p10v": p10u.get("allowed_next_gate") == P10V_GATE,
        "terms_symbol_btcusdt": terms.get("symbol") == DEFAULT_SYMBOL,
        "terms_max_notional_75": float(terms.get("max_notional_usdt") or 0.0) == DEFAULT_MAX_NOTIONAL_USDT,
        "terms_post_only_gtx": terms.get("order_type") == DEFAULT_ORDER_TYPE
        and terms.get("time_in_force") == DEFAULT_TIME_IN_FORCE,
        "terms_continuous_automation_false": terms.get("continuous_automation") is False,
        "review_only": True,
        "no_execution_authorized": True,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"
    review = {
        "contract_version": "hv_balanced_12factor_p10v_terms_review.v1",
        "status": status,
        "blockers": blockers,
        "p10u_summary": evidence_file(p10u_path),
        "p10u_terms": evidence_file(terms_path),
        "conclusion": (
            "p10u_terms_sufficient_for_future_p10w_owner_gate_discussion"
            if status == "ready"
            else "p10u_terms_not_sufficient_for_p10w"
        ),
        "does_not_authorize": [
            "live order submission",
            "candidate execution",
            "target plan replacement",
            "executor input mutation",
            "timer path load",
            "supervisor invocation",
            "continuous automated order flow",
        ],
    }
    owner = {
        "contract_version": "hv_balanced_12factor_p10v_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10v_review_future_execution_terms_package_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "review_only_approved": True,
        "future_p10w_owner_gate_may_be_requested": status == "ready",
        "live_order_submission_approved": False,
        "continuous_automation_approved": False,
    }
    control = build_control("hv_balanced_12factor_p10v_control_boundary.v1", "review_only")
    phase_dir = write_phase(root, "p10v_review", {"owner_decision": owner, "review": review, "control_boundary": control})
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "review": str(phase_dir / "proof" / "review.json"),
        "control_boundary": str(phase_dir / "proof" / "control_boundary.json"),
    }
    summary = {
        "contract_version": P10V_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10v_review_future_execution_terms_package_ready": status == "ready",
        "p10u_sufficient_for_future_p10w_owner_gate": status == "ready",
        "review_only": True,
        "live_order_submission_authorized": False,
        "candidate_executor_path_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automated_order_flow_authorized": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {"p10u_summary": evidence_file(p10u_path), "p10u_terms": evidence_file(terms_path)},
        "allowed_next_gate": P10W_GATE if status == "ready" else "",
        "allowed_next_gate_scope": (
            "owner_gate_only_to_decide_single_cycle_execution_no_auto_execution"
            if status == "ready"
            else ""
        ),
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
    p10s_path = latest_p10s_summary(args.p10s_summary)
    p10s = load_optional(p10s_path)

    steps: list[dict[str, Any]] = []
    blockers: list[str] = []
    status = "ready"

    p10t, p10t_path = build_p10t(root=root, run_id=run_id, args=args, now=started, p10s=p10s, p10s_path=p10s_path)
    steps.append({"gate": "P10T", "status": p10t.get("status"), "summary": evidence_file(p10t_path)})
    if p10t.get("status") != "ready":
        status = "blocked"
        blockers.append("p10t_blocked")

    p10u: dict[str, Any] = {}
    p10u_path = Path("")
    if status == "ready":
        p10u, p10u_path = build_p10u(root=root, run_id=run_id, args=args, now=started, p10t=p10t, p10t_path=p10t_path)
        steps.append({"gate": "P10U", "status": p10u.get("status"), "summary": evidence_file(p10u_path)})
        if p10u.get("status") != "ready":
            status = "blocked"
            blockers.append("p10u_blocked")

    p10v: dict[str, Any] = {}
    p10v_path = Path("")
    if status == "ready":
        p10v, p10v_path = build_p10v(root=root, run_id=run_id, args=args, now=started, p10u=p10u, p10u_path=p10u_path)
        steps.append({"gate": "P10V", "status": p10v.get("status"), "summary": evidence_file(p10v_path)})
        if p10v.get("status") != "ready":
            status = "blocked"
            blockers.append("p10v_blocked")

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "started_at_utc": iso_z(started),
        "finished_at_utc": iso_z(utc_now()),
        "p10t_p10v_execution_terms_corridor_ready": status == "ready",
        "corridor_scope": "P10T owner gate + P10U future execution terms package + P10V review",
        "proof_artifacts_only": True,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "live_order_submission_performed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "candidate_executor_path_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automated_order_flow_authorized": False,
        "blockers": blockers,
        "steps": steps,
        "source_evidence": {"p10s_summary": evidence_file(p10s_path)},
        "allowed_next_gate": P10W_GATE if status == "ready" else "",
        "allowed_next_gate_scope": (
            "owner_gate_only_to_decide_single_cycle_execution_no_auto_execution"
            if status == "ready"
            else ""
        ),
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
