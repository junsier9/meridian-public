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
    DEFAULT_SYMBOL,
    DEFAULT_MAX_GROSS_TURNOVER_USDT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_ORDER_TYPE,
    DEFAULT_TIME_IN_FORCE,
    P10P_CONTRACT,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10q_p10s_followup_proposal_corridor.v1"
P10Q_CONTRACT = "hv_balanced_12factor_p10q_define_followup_scope.v1"
P10R_CONTRACT = "hv_balanced_12factor_p10r_prepare_followup_proposal_package.v1"
P10S_CONTRACT = "hv_balanced_12factor_p10s_review_followup_proposal_package.v1"

DEFAULT_P10P_SEARCH_PARENT = "artifacts/live_trading/proof_artifacts/p10m_p10p_bundled_corridor"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/proof_artifacts/p10q_p10s_followup_proposal_corridor"

P10Q_GATE = "P10Q_define_limited_live_delta_candidate_executor_path_followup_scope_only_if_separately_requested"
P10R_GATE = "P10R_prepare_limited_live_delta_candidate_executor_path_followup_proposal_package_only_if_separately_requested"
P10S_GATE = "P10S_review_p10r_followup_proposal_package_only_if_separately_requested"
P10T_GATE = "P10T_allow_prepare_limited_live_delta_candidate_executor_path_followup_execution_gate_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the P10Q-P10S follow-up proposal corridor after retained P10P. "
            "This corridor is local/proof-artifacts-only: it defines scope, "
            "prepares a proposal package, and reviews readiness. It does not "
            "SSH, sync remote files, invoke supervisor/timer paths, mutate "
            "executor input, replace target plans, or submit/cancel orders."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--p10p-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:continue_next_bundled_gates_after_p10p",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def latest_p10p_summary(explicit: str = "") -> Path:
    if str(explicit or "").strip():
        return resolve_path(explicit)
    return latest_match(DEFAULT_P10P_SEARCH_PARENT, "*/p10p_review/summary.json")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root or "").strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def source_evidence_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("source_evidence") or {}).get(key, {}).get("path") or "")
    return resolve_path(text) if text.strip() else Path("")


def p10p_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P10P_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10p_review_p10o_retained_evidence_ready") is True
        and summary.get("p10o_sufficient_for_limited_live_delta_candidate_executor_path_followup_discussion") is True
        and summary.get("p10o_sufficient_for_live_order_submission_without_new_gate") is False
        and summary.get("p10o_sufficient_for_continuous_automated_order_flow") is False
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_executor_path_execution_authorized") is False
        and summary.get("timer_path_load_authorized") is False
        and summary.get("continuous_automated_order_flow_authorized") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
        and int(summary.get("trade_count") or 0) == 0
        and summary.get("allowed_next_gate") == P10Q_GATE
        and summary.get("allowed_next_gate_scope") == "define_followup_scope_only_no_new_order_no_continuous_automation"
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def write_phase(root: Path, name: str, payloads: dict[str, dict[str, Any]]) -> Path:
    phase_dir = root / name
    phase_dir.mkdir(parents=True, exist_ok=True)
    proof_dir = phase_dir / "proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    output_files = {}
    for key, payload in payloads.items():
        path = proof_dir / f"{key}.json"
        write_json(path, payload)
        output_files[key] = str(path)
    return phase_dir


def build_p10q(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10p: dict[str, Any],
    p10p_path: Path,
) -> tuple[dict[str, Any], Path]:
    p10o_path = source_evidence_path(p10p, "p10o_summary")
    gates = {
        "owner_decision_p10q_recorded": True,
        "p10p_ready_for_scope_definition": p10p_ready(p10p),
        "p10o_source_evidence_exists": p10o_path.exists(),
        "scope_is_define_only": True,
        "no_execution_authorized": True,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"
    scope = {
        "contract_version": "hv_balanced_12factor_p10q_followup_scope.v1",
        "scope": "limited_live_delta_candidate_executor_path_followup_discussion",
        "scope_definition_only": True,
        "allowed_followup_work": [
            "prepare retained proposal package for a future separately requested execution gate",
            "bind any future execution to fresh or retained P10G/P10O hashes",
            "define fresh proof, baseline fallback, kill switch, and post-run reconciliation requirements",
        ],
        "not_authorized": [
            "live order submission",
            "candidate execution",
            "target plan replacement in production",
            "executor input mutation in production",
            "timer path load",
            "supervisor invocation",
            "remote sync",
            "continuous automated order flow",
        ],
        "hard_limits_for_any_future_execution_discussion": {
            "symbol": DEFAULT_SYMBOL,
            "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
            "max_gross_turnover_usdt": DEFAULT_MAX_GROSS_TURNOVER_USDT,
            "order_type": DEFAULT_ORDER_TYPE,
            "time_in_force": DEFAULT_TIME_IN_FORCE,
            "continuous_automation": False,
            "requires_new_owner_gate_before_any_order": True,
        },
        "allowed_next_gate": P10R_GATE,
        "allowed_next_gate_scope": "proposal_package_only_no_execution_no_order_no_continuous_automation",
        "allowed_next_gate_must_be_separately_requested": True,
    }
    owner = {
        "contract_version": "hv_balanced_12factor_p10q_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10q_define_followup_scope_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "scope_definition_approved": True,
        "live_order_submission_approved": False,
        "continuous_automation_approved": False,
    }
    control = {
        "contract_version": "hv_balanced_12factor_p10q_control_boundary.v1",
        "scope": "local_scope_definition_only",
        "ssh_invoked": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "live_order_submission_performed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }
    phase_dir = write_phase(root, "p10q_scope", {"owner_decision": owner, "scope": scope, "control_boundary": control})
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "scope": str(phase_dir / "proof" / "scope.json"),
        "control_boundary": str(phase_dir / "proof" / "control_boundary.json"),
    }
    summary = {
        "contract_version": P10Q_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10q_followup_scope_ready": status == "ready",
        "scope_definition_only": True,
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
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {"p10p_summary": evidence_file(p10p_path), "p10o_summary": evidence_file(p10o_path)},
        "allowed_next_gate": P10R_GATE,
        "allowed_next_gate_scope": "proposal_package_only_no_execution_no_order_no_continuous_automation",
        "allowed_next_gate_must_be_separately_requested": True,
        "output_files": output_files,
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10r(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10q: dict[str, Any],
    p10q_path: Path,
    p10p_path: Path,
) -> tuple[dict[str, Any], Path]:
    gates = {
        "owner_decision_p10r_recorded": True,
        "p10q_ready": p10q.get("status") == "ready" and p10q.get("p10q_followup_scope_ready") is True,
        "p10q_allowed_p10r": p10q.get("allowed_next_gate") == P10R_GATE,
        "proposal_package_only": True,
        "no_execution_authorized": True,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"
    package = {
        "contract_version": "hv_balanced_12factor_p10r_followup_proposal_package.v1",
        "proposal_status": "prepared_for_review_only",
        "proposal_scope": "future_limited_candidate_executor_path_followup_gate",
        "proposal_intent": (
            "A future separately requested gate may prepare exact execution terms for one more "
            "bounded candidate executor-path canary or a small retained sequence. This package "
            "does not approve or execute that work."
        ),
        "required_before_any_future_order": [
            "fresh P10A/P10C live feature parity or retained freshness proof still valid",
            "fresh or retained P10G candidate target plan hash binding",
            "fresh account proof using /fapi/v2/account.canTrade",
            "fresh order book and exchange filters",
            "candidate-scope order/trade/fill delta baseline",
            "baseline fallback and kill switch readback",
            "post-run reconciliation",
        ],
        "risk_order_bounds_for_future_discussion": {
            "symbol": DEFAULT_SYMBOL,
            "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
            "max_gross_turnover_usdt": DEFAULT_MAX_GROSS_TURNOVER_USDT,
            "order_type": DEFAULT_ORDER_TYPE,
            "time_in_force": DEFAULT_TIME_IN_FORCE,
            "market_orders_allowed": False,
            "maker_only_required": True,
            "post_only_required": True,
            "continuous_automation": False,
            "max_cycles_without_separate_gate": 0,
        },
        "boundary_invariants": {
            "production_executor_input_mutation_allowed_in_p10r": False,
            "production_target_plan_replacement_allowed_in_p10r": False,
            "timer_path_load_allowed_in_p10r": False,
            "supervisor_invocation_allowed_in_p10r": False,
            "remote_sync_allowed_in_p10r": False,
            "live_order_submission_allowed_in_p10r": False,
        },
        "allowed_next_gate": P10S_GATE,
        "allowed_next_gate_scope": "review_package_only_no_execution_no_order_no_continuous_automation",
        "allowed_next_gate_must_be_separately_requested": True,
    }
    owner = {
        "contract_version": "hv_balanced_12factor_p10r_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10r_prepare_followup_proposal_package_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "proposal_preparation_approved": True,
        "live_order_submission_approved": False,
        "continuous_automation_approved": False,
    }
    control = {
        "contract_version": "hv_balanced_12factor_p10r_control_boundary.v1",
        "scope": "local_proposal_package_only",
        "ssh_invoked": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "live_order_submission_performed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }
    phase_dir = write_phase(root, "p10r_proposal", {"owner_decision": owner, "proposal_package": package, "control_boundary": control})
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "proposal_package": str(phase_dir / "proof" / "proposal_package.json"),
        "control_boundary": str(phase_dir / "proof" / "control_boundary.json"),
    }
    summary = {
        "contract_version": P10R_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10r_followup_proposal_package_ready": status == "ready",
        "proposal_package_only": True,
        "eligible_for_p10s_review": status == "ready",
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
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {"p10q_summary": evidence_file(p10q_path), "p10p_summary": evidence_file(p10p_path)},
        "allowed_next_gate": P10S_GATE,
        "allowed_next_gate_scope": "review_package_only_no_execution_no_order_no_continuous_automation",
        "allowed_next_gate_must_be_separately_requested": True,
        "output_files": output_files,
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10s(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10r: dict[str, Any],
    p10r_path: Path,
) -> tuple[dict[str, Any], Path]:
    gates = {
        "owner_decision_p10s_recorded": True,
        "p10r_ready": p10r.get("status") == "ready" and p10r.get("p10r_followup_proposal_package_ready") is True,
        "p10r_allowed_p10s": p10r.get("allowed_next_gate") == P10S_GATE,
        "review_only": True,
        "no_execution_authorized": True,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"
    review = {
        "contract_version": "hv_balanced_12factor_p10s_followup_proposal_review.v1",
        "status": status,
        "blockers": blockers,
        "p10r_summary": evidence_file(p10r_path),
        "conclusion": (
            "p10r_sufficient_for_future_p10t_owner_gate_to_prepare_execution_terms"
            if status == "ready"
            else "p10r_not_sufficient_for_p10t"
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
        "contract_version": "hv_balanced_12factor_p10s_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10s_review_followup_proposal_package_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "review_only_approved": True,
        "future_p10t_owner_gate_may_be_requested": status == "ready",
        "live_order_submission_approved": False,
        "continuous_automation_approved": False,
    }
    phase_dir = write_phase(root, "p10s_review", {"owner_decision": owner, "review": review})
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "review": str(phase_dir / "proof" / "review.json"),
    }
    summary = {
        "contract_version": P10S_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10s_review_followup_proposal_package_ready": status == "ready",
        "p10r_sufficient_for_future_p10t_owner_gate": status == "ready",
        "review_only": True,
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
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {"p10r_summary": evidence_file(p10r_path)},
        "allowed_next_gate": P10T_GATE if status == "ready" else "",
        "allowed_next_gate_scope": (
            "owner_gate_only_to_allow_preparing_future_execution_terms_no_execution_no_order"
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
    p10p_path = latest_p10p_summary(args.p10p_summary)
    p10p = load_optional(p10p_path)

    steps: list[dict[str, Any]] = []
    blockers: list[str] = []
    status = "ready"

    p10q, p10q_path = build_p10q(root=root, run_id=run_id, args=args, now=started, p10p=p10p, p10p_path=p10p_path)
    steps.append({"gate": "P10Q", "status": p10q.get("status"), "summary": evidence_file(p10q_path)})
    if p10q.get("status") != "ready":
        status = "blocked"
        blockers.append("p10q_blocked")

    p10r: dict[str, Any] = {}
    p10r_path = Path("")
    if status == "ready":
        p10r, p10r_path = build_p10r(
            root=root,
            run_id=run_id,
            args=args,
            now=started,
            p10q=p10q,
            p10q_path=p10q_path,
            p10p_path=p10p_path,
        )
        steps.append({"gate": "P10R", "status": p10r.get("status"), "summary": evidence_file(p10r_path)})
        if p10r.get("status") != "ready":
            status = "blocked"
            blockers.append("p10r_blocked")

    p10s: dict[str, Any] = {}
    p10s_path = Path("")
    if status == "ready":
        p10s, p10s_path = build_p10s(root=root, run_id=run_id, args=args, now=started, p10r=p10r, p10r_path=p10r_path)
        steps.append({"gate": "P10S", "status": p10s.get("status"), "summary": evidence_file(p10s_path)})
        if p10s.get("status") != "ready":
            status = "blocked"
            blockers.append("p10s_blocked")

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "started_at_utc": iso_z(started),
        "finished_at_utc": iso_z(utc_now()),
        "p10q_p10s_followup_proposal_corridor_ready": status == "ready",
        "corridor_scope": "P10Q scope + P10R proposal package + P10S review",
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
        "source_evidence": {"p10p_summary": evidence_file(p10p_path)},
        "allowed_next_gate": P10T_GATE if status == "ready" else "",
        "allowed_next_gate_scope": (
            "owner_gate_only_to_allow_preparing_future_execution_terms_no_execution_no_order"
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
