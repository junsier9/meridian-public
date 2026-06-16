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

from scripts.live_trading.run_hv_balanced_12factor_p10akr_review_p10ak_blocker_resolution import (  # noqa: E402
    CONTRACT_VERSION as P10AKR_CONTRACT,
    DEFAULT_OUTPUT_PARENT as P10AKR_PARENT,
    P10AKS_GATE,
)
from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10aks_p10aku_revised_nonflat_terms_corridor.v1"
P10AKS_CONTRACT = "hv_balanced_12factor_p10aks_define_revised_nonflat_canary_terms_scope.v1"
P10AKT_CONTRACT = "hv_balanced_12factor_p10akt_revised_nonflat_canary_terms_package.v1"
P10AKU_CONTRACT = "hv_balanced_12factor_p10aku_review_revised_nonflat_canary_terms.v1"

DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/proof_artifacts/p10aks_p10aku_revised_nonflat_canary_terms_corridor"

P10AKT_GATE = "P10AKT_prepare_revised_nonflat_live_delta_canary_terms_package_only_if_separately_requested"
P10AKU_GATE = "P10AKU_review_revised_nonflat_live_delta_canary_terms_only_if_separately_requested"
P10AKV_GATE = "P10AKV_read_only_fresh_position_relation_proof_against_revised_terms_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run P10AKS-P10AKU as a proof-only corridor after P10AKR. "
            "It defines and reviews revised nonflat live_delta canary terms. "
            "It does not call remote APIs, run the supervisor/timer, mutate live "
            "config/operator/executor state, submit/cancel orders, or authorize "
            "another live_delta canary."
        )
    )
    parser.add_argument("--output-root", default="")
    parser.add_argument("--p10akr-summary", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:continue_next_bundled_gates_after_p10akr",
    )
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def phase_root(args: argparse.Namespace, run_id: str) -> Path:
    if str(args.output_root or "").strip():
        return resolve_path(args.output_root)
    return resolve_path(DEFAULT_OUTPUT_PARENT) / run_id


def latest_p10akr_summary(explicit: str = "") -> Path:
    if str(explicit or "").strip():
        return resolve_path(explicit)
    return latest_match(P10AKR_PARENT, "*/summary.json")


def source_path(summary: dict[str, Any], key: str) -> Path:
    text = str(dict(summary.get("source_evidence") or {}).get(key, {}).get("path") or "")
    return resolve_path(text) if text.strip() else Path("")


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def classify_position_relation(*, pre_position_amt: float, candidate_side: str, fill_qty: float) -> dict[str, Any]:
    side = str(candidate_side or "")
    if abs(pre_position_amt) <= 1e-12:
        relation = "flat_position_canary"
        reduce_only_restoration_possible = True
    elif pre_position_amt > 0 and side == "BUY":
        relation = "same_direction_long_add"
        reduce_only_restoration_possible = True
    elif pre_position_amt < 0 and side == "SELL":
        relation = "same_direction_short_add"
        reduce_only_restoration_possible = True
    elif pre_position_amt > 0 and side == "SELL":
        relation = "opposite_direction_reduce_existing_long"
        reduce_only_restoration_possible = False
    elif pre_position_amt < 0 and side == "BUY":
        relation = "opposite_direction_reduce_existing_short"
        reduce_only_restoration_possible = False
    else:
        relation = "unknown_or_unsupported_position_relation"
        reduce_only_restoration_possible = False
    crosses_or_flips = (
        pre_position_amt > 0
        and side == "SELL"
        and fill_qty > abs(pre_position_amt)
    ) or (
        pre_position_amt < 0
        and side == "BUY"
        and fill_qty > abs(pre_position_amt)
    )
    return {
        "relation": relation,
        "pre_position_amt": pre_position_amt,
        "candidate_side": side,
        "fill_qty": fill_qty,
        "crosses_or_flips_existing_position": crosses_or_flips,
        "reduce_only_restoration_possible": reduce_only_restoration_possible and not crosses_or_flips,
        "executable_under_revised_terms": reduce_only_restoration_possible and not crosses_or_flips,
    }


def p10akr_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("contract_version") == P10AKR_CONTRACT
        and summary.get("status") == "ready"
        and not summary.get("blockers")
        and summary.get("p10akr_blocker_resolution_review_ready") is True
        and summary.get("allowed_next_gate") == P10AKS_GATE
        and summary.get("allowed_next_gate_must_be_separately_requested") is True
        and summary.get("live_order_submission_authorized") is False
        and summary.get("candidate_executor_path_execution_authorized") is False
        and summary.get("non_reduce_only_restoration_authorized") is False
        and summary.get("non_reduce_only_restoration_required") is True
        and summary.get("open_order_remaining_after_readback") is False
    )


def no_execution_matrix() -> dict[str, Any]:
    return {
        "proof_artifacts_only": True,
        "remote_api_called": False,
        "remote_execution_performed": False,
        "remote_sync_performed": False,
        "remote_files_written": 0,
        "timer_path_load_authorized": False,
        "timer_path_load_performed": False,
        "supervisor_invocation_authorized": False,
        "supervisor_invocation_performed": False,
        "live_config_mutation_performed": False,
        "operator_state_mutation_performed": False,
        "executor_input_mutation_performed": False,
        "target_plan_replacement_performed": False,
        "live_order_submission_authorized": False,
        "live_order_submission_performed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }


def write_phase(root: Path, name: str, payloads: dict[str, dict[str, Any]]) -> Path:
    phase_dir = root / name
    proof_dir = phase_dir / "proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    for key, payload in payloads.items():
        write_json(proof_dir / f"{key}.json", payload)
    return phase_dir


def build_p10aks(
    *,
    root: Path,
    run_id: str,
    now: datetime,
    args: argparse.Namespace,
    p10akr_path: Path,
    p10akr: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    checks = {
        "owner_decision_p10aks_recorded": True,
        "p10akr_ready_for_p10aks": p10akr_ready(p10akr),
        "scope_only": True,
        "no_order_no_remote_no_timer": True,
    }
    blockers = sorted(key for key, ready in checks.items() if not ready)
    status = "ready" if not blockers else "blocked"
    owner_decision = {
        "contract_version": "hv_balanced_12factor_p10aks_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10aks_define_revised_nonflat_live_delta_canary_terms_scope_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "scope_only": True,
        "authorizes_terms_package": status == "ready",
        "authorizes_remote_read": False,
        "authorizes_live_order": False,
    }
    scope = {
        "contract_version": "hv_balanced_12factor_p10aks_scope.v1",
        "status": status,
        "blockers": blockers,
        "scope": "define_revised_nonflat_canary_terms_only_no_order_no_remote_no_timer",
        "must_define": [
            "position relation classification before any future canary",
            "flat-position canary is allowed in principle",
            "same-direction add canary is allowed in principle",
            "opposite-direction reduction of existing position is blocked",
            "crossing or flipping an existing position is blocked",
            "non-reduce-only restoration is not authorized",
            "baseline fallback and kill switch remain mandatory",
            "fresh read-only position relation proof is required before any future execution gate",
        ],
        "must_not_do": [
            "remote account read",
            "live order",
            "candidate execution",
            "timer/supervisor path load",
            "live config/operator/executor mutation",
        ],
    }
    phase_dir = write_phase(root, "p10aks_scope", {"owner_decision": owner_decision, "scope": scope})
    summary = {
        "contract_version": P10AKS_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10aks_revised_nonflat_terms_scope_ready": status == "ready",
        **no_execution_matrix(),
        "checks": checks,
        "blockers": blockers,
        "source_evidence": {"p10akr_summary": evidence_file(p10akr_path)},
        "allowed_next_gate": P10AKT_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "prepare_revised_nonflat_canary_terms_package_no_order_no_remote_no_timer"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {
            "summary": str(phase_dir / "summary.json"),
            "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
            "scope": str(phase_dir / "proof" / "scope.json"),
        },
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10akt(
    *,
    root: Path,
    run_id: str,
    now: datetime,
    args: argparse.Namespace,
    p10aks_path: Path,
    p10aks: dict[str, Any],
    p10akr: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    manual_cancel = load_optional(source_path(p10akr, "manual_cancel_readback"))
    reduce_only_close = load_optional(source_path(p10akr, "reduce_only_close_readback"))
    relation = classify_position_relation(
        pre_position_amt=_float(reduce_only_close.get("pre_position_amt")),
        candidate_side=str(_nested(reduce_only_close, "entry_order", "payload", "side") or ""),
        fill_qty=_float(manual_cancel.get("fill_qty")),
    )
    terms = {
        "contract_version": "hv_balanced_12factor_p10akt_revised_nonflat_canary_terms.v1",
        "status": "ready",
        "symbol": "BTCUSDT",
        "max_notional_usdt": 75.0,
        "max_cycles_total": 1,
        "max_candidate_entry_orders_total": 1,
        "max_reduce_only_rollback_orders_total": 1,
        "max_orders_total": 2,
        "order_type": "post_only_limit",
        "time_in_force": "GTX",
        "minimum_maker_buffer_ticks": 50,
        "market_orders_allowed": False,
        "post_only_required": True,
        "maker_only_required": True,
        "continuous_automation": False,
        "pre_submit_position_relation_required": True,
        "allowed_position_relations": [
            "flat_position_canary",
            "same_direction_long_add",
            "same_direction_short_add",
        ],
        "blocked_position_relations": [
            "opposite_direction_reduce_existing_long",
            "opposite_direction_reduce_existing_short",
            "crossing_or_flipping_existing_position",
            "unknown_or_unsupported_position_relation",
        ],
        "current_retained_position_relation": relation,
        "current_retained_relation_executable_under_revised_terms": relation["executable_under_revised_terms"],
        "rollback": (
            "cancel open candidate order; reduce-only close only if filled and "
            "pre-submit relation proves reduce-only restoration is possible; "
            "never place a non-reduce-only restoration order"
        ),
        "baseline_fallback": "any relation/proof/order/readback check failure reverts to baseline-only no-order",
        "kill_switch": "candidate_live_delta_enabled=false / revert baseline-only",
        "fresh_read_only_position_relation_proof_required_before_future_execution_gate": True,
        "does_not_authorize_execution": True,
    }
    checks = {
        "p10aks_ready": p10aks.get("status") == "ready"
        and p10aks.get("allowed_next_gate") == P10AKT_GATE,
        "terms_position_relation_required": terms["pre_submit_position_relation_required"] is True,
        "terms_blocks_current_retained_relation": terms["current_retained_relation_executable_under_revised_terms"] is False,
        "terms_forbid_non_reduce_only_restoration": "never place a non-reduce-only restoration order" in terms["rollback"],
        "terms_require_fresh_read_only_relation_proof": terms[
            "fresh_read_only_position_relation_proof_required_before_future_execution_gate"
        ]
        is True,
        "terms_no_execution": terms["does_not_authorize_execution"] is True,
    }
    blockers = sorted(key for key, ready in checks.items() if not ready)
    status = "ready" if not blockers else "blocked"
    terms["status"] = status
    terms["blockers"] = blockers
    owner_decision = {
        "contract_version": "hv_balanced_12factor_p10akt_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10akt_prepare_revised_nonflat_canary_terms_package_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "terms_package_only": True,
        "authorizes_live_order": False,
    }
    phase_dir = write_phase(root, "p10akt_terms_package", {"owner_decision": owner_decision, "execution_terms": terms})
    summary = {
        "contract_version": P10AKT_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10akt_revised_nonflat_terms_package_ready": status == "ready",
        "current_retained_position_relation": relation["relation"],
        "current_retained_relation_executable_under_revised_terms": relation["executable_under_revised_terms"],
        "fresh_read_only_position_relation_proof_required_before_future_execution_gate": True,
        "non_reduce_only_restoration_authorized": False,
        **no_execution_matrix(),
        "checks": checks,
        "blockers": blockers,
        "source_evidence": {
            "p10aks_summary": evidence_file(p10aks_path),
            "manual_cancel_readback": evidence_file(source_path(p10akr, "manual_cancel_readback")),
            "reduce_only_close_readback": evidence_file(source_path(p10akr, "reduce_only_close_readback")),
        },
        "allowed_next_gate": P10AKU_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "review_revised_nonflat_terms_no_order_no_remote_no_timer"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {
            "summary": str(phase_dir / "summary.json"),
            "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
            "execution_terms": str(phase_dir / "proof" / "execution_terms.json"),
        },
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def build_p10aku(
    *,
    root: Path,
    run_id: str,
    now: datetime,
    args: argparse.Namespace,
    p10akt_path: Path,
    p10akt: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    terms_path = Path(str(dict(p10akt.get("output_files") or {}).get("execution_terms") or ""))
    terms = load_optional(terms_path)
    checks = {
        "owner_decision_p10aku_recorded": True,
        "p10akt_ready": p10akt.get("status") == "ready"
        and p10akt.get("allowed_next_gate") == P10AKU_GATE,
        "terms_file_exists": terms_path.exists() and terms_path.is_file(),
        "terms_status_ready": terms.get("status") == "ready",
        "terms_current_relation_blocked": terms.get("current_retained_relation_executable_under_revised_terms") is False,
        "terms_require_fresh_read_only_relation_proof": terms.get(
            "fresh_read_only_position_relation_proof_required_before_future_execution_gate"
        )
        is True,
        "terms_do_not_authorize_execution": terms.get("does_not_authorize_execution") is True,
        "no_execution_matrix_clean": True,
    }
    blockers = sorted(key for key, ready in checks.items() if not ready)
    status = "ready" if not blockers else "blocked"
    owner_decision = {
        "contract_version": "hv_balanced_12factor_p10aku_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10aku_review_revised_nonflat_canary_terms_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "review_only": True,
        "authorizes_future_read_only_relation_proof_if_separately_requested": status == "ready",
        "authorizes_live_order": False,
    }
    review = {
        "contract_version": "hv_balanced_12factor_p10aku_revised_nonflat_terms_review.v1",
        "status": status,
        "blockers": blockers,
        "conclusion": (
            "terms_sufficient_for_read_only_position_relation_proof_gate_not_for_order"
            if status == "ready"
            else "terms_not_sufficient_for_next_gate"
        ),
        "current_retained_relation": terms.get("current_retained_position_relation"),
        "current_retained_relation_remains_not_executable": terms.get(
            "current_retained_relation_executable_under_revised_terms"
        )
        is False,
        "does_not_authorize": [
            "fresh remote read inside P10AKU",
            "additional live order",
            "candidate executor path execution",
            "timer/supervisor path load",
            "live config/operator/executor mutation",
            "continuous automated order flow",
        ],
    }
    phase_dir = write_phase(root, "p10aku_review", {"owner_decision": owner_decision, "review": review})
    summary = {
        "contract_version": P10AKU_CONTRACT,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10aku_review_revised_nonflat_terms_ready": status == "ready",
        "terms_sufficient_for_future_read_only_position_relation_proof": status == "ready",
        "terms_sufficient_for_additional_live_order_without_new_gate": False,
        "current_retained_relation_executable_under_revised_terms": False,
        **no_execution_matrix(),
        "checks": checks,
        "blockers": blockers,
        "source_evidence": {
            "p10akt_summary": evidence_file(p10akt_path),
            "execution_terms": evidence_file(terms_path),
        },
        "allowed_next_gate": P10AKV_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "read_only_fresh_position_relation_proof_no_order_no_timer_no_supervisor"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {
            "summary": str(phase_dir / "summary.json"),
            "owner_decision": str(phase_dir / "proof" / "owner_decision.json"),
            "review": str(phase_dir / "proof" / "review.json"),
        },
    }
    write_json(phase_dir / "summary.json", summary)
    return summary, phase_dir / "summary.json"


def run_corridor(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    started = utc_now()
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    root.mkdir(parents=True, exist_ok=True)

    p10akr_path = latest_p10akr_summary(args.p10akr_summary)
    p10akr = load_optional(p10akr_path)
    steps: list[dict[str, Any]] = []
    blockers: list[str] = []
    status = "ready"

    p10aks, p10aks_path = build_p10aks(
        root=root,
        run_id=run_id,
        now=started,
        args=args,
        p10akr_path=p10akr_path,
        p10akr=p10akr,
    )
    steps.append({"gate": "P10AKS", "status": p10aks.get("status"), "summary": evidence_file(p10aks_path)})
    if p10aks.get("status") != "ready":
        blockers.append("p10aks_blocked")
        status = "blocked"

    p10akt: dict[str, Any] = {}
    p10akt_path = root / "p10akt_terms_package" / "summary.json"
    if status == "ready":
        p10akt, p10akt_path = build_p10akt(
            root=root,
            run_id=run_id,
            now=started,
            args=args,
            p10aks_path=p10aks_path,
            p10aks=p10aks,
            p10akr=p10akr,
        )
        steps.append({"gate": "P10AKT", "status": p10akt.get("status"), "summary": evidence_file(p10akt_path)})
        if p10akt.get("status") != "ready":
            blockers.append("p10akt_blocked")
            status = "blocked"

    p10aku: dict[str, Any] = {}
    p10aku_path = root / "p10aku_review" / "summary.json"
    if status == "ready":
        p10aku, p10aku_path = build_p10aku(
            root=root,
            run_id=run_id,
            now=started,
            args=args,
            p10akt_path=p10akt_path,
            p10akt=p10akt,
        )
        steps.append({"gate": "P10AKU", "status": p10aku.get("status"), "summary": evidence_file(p10aku_path)})
        if p10aku.get("status") != "ready":
            blockers.append("p10aku_blocked")
            status = "blocked"

    finished = utc_now()
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "started_at_utc": iso_z(started),
        "finished_at_utc": iso_z(finished),
        "p10aks_p10aku_revised_nonflat_terms_corridor_ready": status == "ready",
        "corridor_scope": "P10AKS scope + P10AKT terms package + P10AKU review",
        "steps": steps,
        "blockers": blockers,
        "current_retained_relation_executable_under_revised_terms": False,
        "terms_sufficient_for_future_read_only_position_relation_proof": status == "ready",
        "terms_sufficient_for_additional_live_order_without_new_gate": False,
        **no_execution_matrix(),
        "source_evidence": {"p10akr_summary": evidence_file(p10akr_path)},
        "allowed_next_gate": P10AKV_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "read_only_fresh_position_relation_proof_no_order_no_timer_no_supervisor"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {"summary": str(root / "summary.json")},
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = run_corridor(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(
        "current_retained_relation_executable_under_revised_terms="
        + str(summary["current_retained_relation_executable_under_revised_terms"]).lower()
    )
    print("summary=" + summary["output_files"]["summary"])
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
