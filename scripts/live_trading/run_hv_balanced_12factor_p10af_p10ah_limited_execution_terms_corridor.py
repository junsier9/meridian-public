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

from scripts.live_trading.run_hv_balanced_12factor_p10ac_p10ae_limited_live_delta_expansion_corridor import (  # noqa: E402
    P10AE_CONTRACT,
    P10AF_GATE,
)
from scripts.live_trading.run_hv_balanced_12factor_p10m_p10p_bundled_corridor import (  # noqa: E402
    DEFAULT_MAX_GROSS_TURNOVER_USDT,
    DEFAULT_MAX_NOTIONAL_USDT,
    DEFAULT_ORDER_TYPE,
    DEFAULT_SYMBOL,
    DEFAULT_TIME_IN_FORCE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10af_p10ah_limited_execution_terms_corridor.v1"
P10AF_CONTRACT = "hv_balanced_12factor_p10af_owner_gate_allow_prepare_limited_execution_terms.v1"
P10AG_CONTRACT = "hv_balanced_12factor_p10ag_prepare_limited_execution_terms_package.v1"
P10AH_CONTRACT = "hv_balanced_12factor_p10ah_review_limited_execution_terms_package.v1"

DEFAULT_P10AE_SEARCH_PARENT = "artifacts/live_trading/proof_artifacts/p10ac_p10ae_limited_live_delta_expansion_corridor"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/proof_artifacts/p10af_p10ah_limited_execution_terms_corridor"

P10AG_GATE = "P10AG_prepare_limited_live_delta_expansion_execution_terms_package_only_if_separately_requested"
P10AH_GATE = "P10AH_review_p10ag_limited_live_delta_expansion_execution_terms_package_only_if_separately_requested"
P10AI_GATE = "P10AI_owner_gate_execute_one_limited_live_delta_expansion_canary_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run P10AF-P10AH after retained P10AE. This corridor is local and "
            "proof-artifacts-only: it records an owner gate that permits "
            "preparing future limited execution terms, prepares those terms, "
            "and reviews them. It does not SSH, call Binance, submit/cancel "
            "orders, invoke timer/supervisor paths, remote sync, mutate live "
            "config/operator state, replace target plans, or mutate executor input."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--p10ae-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:continue_next_bundled_gates_after_p10ae",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def latest_p10ae_summary(explicit: str = "") -> Path:
    if str(explicit or "").strip():
        return resolve_path(explicit)
    return latest_match(DEFAULT_P10AE_SEARCH_PARENT, "*/p10ae_review/summary.json")


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


def p10ae_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P10AE_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10ae_review_limited_live_delta_expansion_package_ready") is True
        and summary.get("p10ad_package_sufficient_for_future_p10af_owner_gate") is True
        and summary.get("p10ad_package_sufficient_for_live_order_submission_without_p10af") is False
        and summary.get("review_only") is True
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
        and summary.get("allowed_next_gate") == P10AF_GATE
        and summary.get("allowed_next_gate_scope") == "owner_gate_only_to_allow_prepare_future_limited_execution_terms_no_order_no_timer"
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
    )


def p10ad_package_ready(package: dict[str, Any]) -> bool:
    terms = dict(package.get("future_discussion_terms_not_execution") or {})
    evidence = dict(package.get("retained_canary_evidence") or {})
    prior = dict(evidence.get("prior_p10o") or {})
    followup = dict(evidence.get("followup_p10aa") or {})
    return (
        package.get("contract_version") == "hv_balanced_12factor_p10ad_limited_expansion_package.v1"
        and package.get("status") == "ready"
        and terms.get("symbols") == [DEFAULT_SYMBOL]
        and terms.get("order_type") == DEFAULT_ORDER_TYPE
        and terms.get("time_in_force") == DEFAULT_TIME_IN_FORCE
        and terms.get("market_orders_allowed") is False
        and terms.get("post_only_required") is True
        and terms.get("maker_only_required") is True
        and terms.get("continuous_automation_allowed") is False
        and terms.get("timer_supervisor_path_allowed") is False
        and int(terms.get("minimum_maker_buffer_ticks_for_future_discussion") or 0) >= 50
        and int(prior.get("orders_submitted") or 0) == 1
        and int(followup.get("orders_submitted") or 0) == 1
        and int(prior.get("fill_count") or 0) == 0
        and int(followup.get("fill_count") or 0) == 0
        and str(prior.get("candidate_target_plan_sha256") or "")
        == str(followup.get("candidate_target_plan_sha256") or "")
        and str(prior.get("baseline_target_plan_sha256") or "")
        == str(followup.get("baseline_target_plan_sha256") or "")
    )


def write_phase(root: Path, name: str, payloads: dict[str, dict[str, Any]]) -> Path:
    phase_dir = root / name
    proof_dir = phase_dir / "proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    for key, payload in payloads.items():
        write_json(proof_dir / f"{key}.json", payload)
    return phase_dir


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
        "live_config_mutation_performed": False,
        "operator_state_mutation_performed": False,
        "target_plan_replacement_performed": False,
        "executor_input_mutation_performed": False,
        "timer_path_load_performed": False,
        "supervisor_invocation_performed": False,
    }


def non_authorization() -> dict[str, Any]:
    return {
        "live_order_submission_authorized": False,
        "candidate_executor_path_execution_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "continuous_automated_order_flow_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
    }


def build_p10af(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10ae: dict[str, Any],
    p10ae_path: Path,
    p10ad_package: dict[str, Any],
    p10ad_package_path: Path,
) -> tuple[dict[str, Any], Path]:
    gates = {
        "owner_decision_p10af_recorded": True,
        "p10ae_ready_for_p10af": p10ae_ready(p10ae),
        "p10ad_package_exists": p10ad_package_path.exists() and p10ad_package_path.is_file(),
        "p10ad_package_ready": p10ad_package_ready(p10ad_package),
        "owner_gate_only": True,
        "no_execution_authorized": True,
    }
    blockers = sorted(key for key, ready in gates.items() if not ready)
    status = "ready" if not blockers else "blocked"
    owner = {
        "contract_version": "hv_balanced_12factor_p10af_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10af_allow_prepare_future_limited_execution_terms_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "p10ag_terms_package_preparation_approved": status == "ready",
        "live_order_submission_approved": False,
        "candidate_executor_path_execution_approved": False,
        "continuous_automation_approved": False,
        "timer_supervisor_load_approved": False,
    }
    gate_record = {
        "contract_version": "hv_balanced_12factor_p10af_gate_record.v1",
        "status": status,
        "scope": "owner_gate_only_to_allow_preparing_future_limited_execution_terms",
        "allowed_next_gate": P10AG_GATE,
        "allowed_next_gate_scope": "prepare_limited_execution_terms_package_only_no_order_no_remote_no_timer",
        "allowed_next_gate_must_be_separately_requested": True,
        "does_not_authorize": [
            "live order submission",
            "candidate execution",
            "production target plan replacement",
            "executor input mutation",
            "timer path load",
            "supervisor invocation",
            "remote sync",
            "continuous automated order flow",
        ],
    }
    phase_dir = write_phase(root, "p10af_owner_gate", {"owner_decision": owner, "gate_record": gate_record})
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "gate_record": str(phase_dir / "proof" / "gate_record.json"),
    }
    summary = {
        "contract_version": P10AF_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10af_owner_gate_ready": status == "ready",
        "p10ag_terms_package_authorized_if_separately_requested": status == "ready",
        "owner_gate_only": True,
        **non_authorization(),
        **no_side_effects(),
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {
            "p10ae_summary": evidence_file(p10ae_path),
            "p10ad_proposal_package": evidence_file(p10ad_package_path),
        },
        "allowed_next_gate": P10AG_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "prepare_limited_execution_terms_package_only_no_order_no_remote_no_timer"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": output_files,
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10ag(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10af: dict[str, Any],
    p10af_path: Path,
    p10ad_package: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    gates = {
        "owner_decision_p10ag_recorded": True,
        "p10af_ready": p10af.get("status") == "ready"
        and p10af.get("p10ag_terms_package_authorized_if_separately_requested") is True,
        "p10af_allowed_p10ag": p10af.get("allowed_next_gate") == P10AG_GATE,
        "terms_package_only": True,
        "no_execution_authorized": True,
    }
    blockers = sorted(key for key, ready in gates.items() if not ready)
    status = "ready" if not blockers else "blocked"
    retained = dict(p10ad_package.get("retained_canary_evidence") or {})
    terms = {
        "contract_version": "hv_balanced_12factor_p10ag_limited_execution_terms_package.v1",
        "status": status,
        "terms_status": "prepared_for_future_owner_review_only",
        "future_execution_shape": "one_single_cycle_limited_live_delta_expansion_canary",
        "retained_evidence_basis": retained,
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
        "minimum_maker_buffer_ticks": 50,
        "candidate_plan_hash_binding": "fresh P10G rerun or explicitly owner-accepted retained P10G hash required",
        "baseline_fallback": "any failed proof keeps executor baseline-only and submits zero candidate orders",
        "kill_switch": "candidate_live_delta_enabled=false / executor_target_source=baseline_only",
        "rollback": "cancel open candidate order; reduce-only close only if filled and separately owner-approved",
        "required_fresh_proofs_before_future_execution": [
            "/fapi/v2/account.canTrade true; ignore /fapi/v3.canTrade for permission decision",
            "pre-submit open orders count and fingerprint",
            "pre-submit order/fill/trade baseline",
            "pre-submit candidate-scope position and balance fingerprint",
            "fresh BTCUSDT book and exchange filters",
            "post-only non-crossing limit price with maker buffer >= 50 ticks",
            "static remote control boundary unchanged before submit",
        ],
        "required_post_run_reconciliation": [
            "order accepted or fail-closed reason retained",
            "query/cancel status retained if order accepted",
            "executedQty, fill count, and trade count retained",
            "post-cycle executor source remains or reverts to baseline-only",
            "remote config/operator/timer/supervisor/static boundary unchanged",
        ],
        "does_not_authorize_execution": True,
    }
    owner = {
        "contract_version": "hv_balanced_12factor_p10ag_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10ag_prepare_future_limited_execution_terms_package_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "terms_package_preparation_approved": status == "ready",
        "live_order_submission_approved": False,
        "candidate_execution_approved": False,
        "continuous_automation_approved": False,
    }
    phase_dir = write_phase(root, "p10ag_terms_package", {"owner_decision": owner, "execution_terms": terms})
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "execution_terms": str(phase_dir / "proof" / "execution_terms.json"),
    }
    summary = {
        "contract_version": P10AG_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10ag_limited_execution_terms_package_ready": status == "ready",
        "terms_package_only": True,
        "eligible_for_p10ah_review": status == "ready",
        "symbol": DEFAULT_SYMBOL,
        "max_notional_usdt": DEFAULT_MAX_NOTIONAL_USDT,
        "max_gross_turnover_usdt": DEFAULT_MAX_GROSS_TURNOVER_USDT,
        "max_cycles_total": 1,
        "minimum_maker_buffer_ticks": 50,
        "order_type": DEFAULT_ORDER_TYPE,
        "time_in_force": DEFAULT_TIME_IN_FORCE,
        **non_authorization(),
        **no_side_effects(),
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {"p10af_summary": evidence_file(p10af_path)},
        "allowed_next_gate": P10AH_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "review_limited_execution_terms_package_only_no_order_no_remote_no_timer"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": output_files,
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10ah(
    *,
    root: Path,
    run_id: str,
    args: argparse.Namespace,
    now: datetime,
    p10ag: dict[str, Any],
    p10ag_path: Path,
) -> tuple[dict[str, Any], Path]:
    terms_path = source_output_path(p10ag, "execution_terms")
    terms = load_optional(terms_path)
    gates = {
        "owner_decision_p10ah_recorded": True,
        "p10ag_ready": p10ag.get("status") == "ready"
        and p10ag.get("p10ag_limited_execution_terms_package_ready") is True,
        "p10ag_allowed_p10ah": p10ag.get("allowed_next_gate") == P10AH_GATE,
        "terms_file_exists": terms_path.exists() and terms_path.is_file(),
        "terms_single_symbol": terms.get("symbol") == DEFAULT_SYMBOL,
        "terms_single_cycle": int(terms.get("max_cycles_total") or 0) == 1
        and terms.get("continuous_automation") is False,
        "terms_post_only_gtx": terms.get("order_type") == DEFAULT_ORDER_TYPE
        and terms.get("time_in_force") == DEFAULT_TIME_IN_FORCE,
        "terms_maker_buffer_min_50": int(terms.get("minimum_maker_buffer_ticks") or 0) >= 50,
        "review_only": True,
        "no_execution_authorized": True,
    }
    blockers = sorted(key for key, ready in gates.items() if not ready)
    status = "ready" if not blockers else "blocked"
    review = {
        "contract_version": "hv_balanced_12factor_p10ah_limited_execution_terms_review.v1",
        "status": status,
        "blockers": blockers,
        "p10ag_summary": evidence_file(p10ag_path),
        "p10ag_execution_terms": evidence_file(terms_path),
        "p10ag_terms_sufficient_for_p10ah_review": status == "ready",
        "p10ag_terms_sufficient_for_future_p10ai_owner_execution_gate": status == "ready",
        "p10ag_terms_sufficient_for_live_order_submission_without_p10ai": False,
        "p10ag_terms_sufficient_for_continuous_automation": False,
        "remaining_required_gate_before_any_future_order": P10AI_GATE,
        "does_not_authorize": [
            "new live order",
            "candidate execution",
            "continuous automated order flow",
            "timer path load",
            "supervisor invocation",
            "remote sync",
            "production executor input mutation",
            "production target plan replacement",
        ],
    }
    owner = {
        "contract_version": "hv_balanced_12factor_p10ah_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10ah_review_limited_execution_terms_package_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "review_only_approved": True,
        "future_p10ai_owner_execution_gate_may_be_requested": status == "ready",
        "live_order_submission_approved": False,
        "continuous_automation_approved": False,
    }
    phase_dir = write_phase(root, "p10ah_review", {"owner_decision": owner, "review": review})
    output_files = {
        "summary": str(phase_dir / "summary.json"),
        "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
        "review": str(phase_dir / "proof" / "review.json"),
    }
    summary = {
        "contract_version": P10AH_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10ah_review_limited_execution_terms_package_ready": status == "ready",
        "p10ag_terms_sufficient_for_future_p10ai_owner_execution_gate": status == "ready",
        "p10ag_terms_sufficient_for_live_order_submission_without_p10ai": False,
        "p10ag_terms_sufficient_for_continuous_automation": False,
        "review_only": True,
        **non_authorization(),
        **no_side_effects(),
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {"p10ag_summary": evidence_file(p10ag_path), "p10ag_execution_terms": evidence_file(terms_path)},
        "allowed_next_gate": P10AI_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "owner_gate_to_execute_one_single_cycle_limited_canary_no_auto_execution"
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

    p10ae_path = latest_p10ae_summary(args.p10ae_summary)
    p10ae = load_optional(p10ae_path)
    p10ad_package_path = source_evidence_path(p10ae, "p10ad_proposal_package")
    p10ad_package = load_optional(p10ad_package_path)

    steps: list[dict[str, Any]] = []
    blockers: list[str] = []
    status = "ready"

    p10af, p10af_path = build_p10af(
        root=root,
        run_id=run_id,
        args=args,
        now=started,
        p10ae=p10ae,
        p10ae_path=p10ae_path,
        p10ad_package=p10ad_package,
        p10ad_package_path=p10ad_package_path,
    )
    steps.append({"gate": "P10AF", "status": p10af.get("status"), "summary": evidence_file(p10af_path)})
    if p10af.get("status") != "ready":
        status = "blocked"
        blockers.append("p10af_blocked")

    p10ag: dict[str, Any] = {}
    p10ag_path = Path("")
    if status == "ready":
        p10ag, p10ag_path = build_p10ag(
            root=root,
            run_id=run_id,
            args=args,
            now=utc_now(),
            p10af=p10af,
            p10af_path=p10af_path,
            p10ad_package=p10ad_package,
        )
        steps.append({"gate": "P10AG", "status": p10ag.get("status"), "summary": evidence_file(p10ag_path)})
        if p10ag.get("status") != "ready":
            status = "blocked"
            blockers.append("p10ag_blocked")

    p10ah: dict[str, Any] = {}
    p10ah_path = Path("")
    if status == "ready":
        p10ah, p10ah_path = build_p10ah(
            root=root,
            run_id=run_id,
            args=args,
            now=utc_now(),
            p10ag=p10ag,
            p10ag_path=p10ag_path,
        )
        steps.append({"gate": "P10AH", "status": p10ah.get("status"), "summary": evidence_file(p10ah_path)})
        if p10ah.get("status") != "ready":
            status = "blocked"
            blockers.append("p10ah_blocked")

    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "started_at_utc": iso_z(started),
        "finished_at_utc": iso_z(utc_now()),
        "p10af_p10ah_limited_execution_terms_corridor_ready": status == "ready",
        "corridor_scope": "P10AF owner gate + P10AG limited execution terms package + P10AH review",
        **non_authorization(),
        **no_side_effects(),
        "blockers": blockers,
        "steps": steps,
        "source_evidence": {"p10ae_summary": evidence_file(p10ae_path)},
        "allowed_next_gate": P10AI_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "owner_gate_to_execute_one_single_cycle_limited_canary_no_auto_execution"
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
