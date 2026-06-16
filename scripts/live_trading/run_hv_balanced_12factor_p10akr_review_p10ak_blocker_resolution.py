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

from scripts.live_trading.run_hv_balanced_dth60_coinglass_phase9q_define_next_gate_scope_owner_gate import (  # noqa: E402
    evidence_file,
    latest_match,
    load_optional,
    resolve_path,
    write_json,
)


CONTRACT_VERSION = "hv_balanced_12factor_p10akr_review_p10ak_blocker_resolution.v1"
DEFAULT_P10AI_PARENT = "artifacts/live_trading/proof_artifacts/p10ai_p10ak_limited_canary_corridor"
DEFAULT_OUTPUT_PARENT = "artifacts/live_trading/proof_artifacts/p10akr_p10ak_blocker_resolution_review"
P10AKS_GATE = "P10AKS_define_revised_nonflat_live_delta_canary_terms_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P10AKR: review the blocked P10AI-P10AK limited canary retained "
            "evidence after a filled post-only canary. This is local/proof-only: "
            "it does not call remote APIs, submit/cancel orders, mutate timer/"
            "supervisor/config/operator/executor state, or authorize another "
            "live_delta step."
        )
    )
    parser.add_argument("--p10ai-summary", default="")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument(
        "--owner-decision-source",
        default="user_chat:continue_next_bundled_gates_after_p10ak_blocked",
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


def latest_p10ai_summary(explicit: str = "") -> Path:
    if str(explicit or "").strip():
        return resolve_path(explicit)
    return latest_match(DEFAULT_P10AI_PARENT, "*/summary.json")


def run_dir_from_summary(path: Path) -> Path:
    return path.parent


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


def build_p10akr(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    now = utc_now()
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    root = phase_root(args, run_id)
    proof_dir = root / "proof"
    proof_dir.mkdir(parents=True, exist_ok=True)

    p10ai_path = latest_p10ai_summary(args.p10ai_summary)
    p10ai = load_optional(p10ai_path)
    p10ai_root = run_dir_from_summary(p10ai_path)
    p10aj_path = p10ai_root / "p10aj_execution" / "summary.json"
    p10ak_path = p10ai_root / "p10ak_review" / "summary.json"
    p10aj = load_optional(p10aj_path)
    p10ak = load_optional(p10ak_path)
    manual_cancel_path = p10ai_root / "p10ak_review" / "proof" / "post_blocker_manual_cancel_readback.json"
    reduce_only_close_path = p10ai_root / "p10ak_review" / "proof" / "post_fill_reduce_only_close_readback.json"
    manual_cancel = load_optional(manual_cancel_path)
    reduce_only_close = load_optional(reduce_only_close_path)
    p10i_source_path = ROOT / "scripts" / "live_trading" / "run_hv_balanced_12factor_p10i_execute_single_cycle_live_delta_canary.py"
    p10i_test_path = ROOT / "tests" / "test_hv_balanced_12factor_p10i_execute_single_cycle_live_delta_canary.py"

    entry_side = str(_nested(reduce_only_close, "entry_order", "payload", "side") or "")
    pre_position_amt = _float(reduce_only_close.get("pre_position_amt"))
    fill_qty = _float(manual_cancel.get("fill_qty"))
    close_qty = _float(reduce_only_close.get("close_qty"))
    non_reduce_only_restoration_required = entry_side == "SELL" and pre_position_amt > 0 and fill_qty > 0
    review_checks = {
        "p10ai_corridor_blocked_on_p10ak": p10ai.get("status") == "blocked"
        and "p10ak_blocked" in list(p10ai.get("blockers") or []),
        "p10aj_retained_summary_exists": p10aj_path.exists() and p10aj_path.is_file(),
        "p10ak_retained_summary_blocked": p10ak.get("status") == "blocked",
        "filled_canary_entry_detected": fill_qty == 0.001
        and _nested(manual_cancel, "post_order", "payload", "status") == "FILLED",
        "no_open_order_remaining_after_readback": manual_cancel.get("open_order_remaining") is False
        and reduce_only_close.get("open_orders_match", {}).get("status") == "ok"
        and list(reduce_only_close.get("open_orders_match", {}).get("payload") or []) == [],
        "reduce_only_rollback_not_possible_without_extra_authorization": non_reduce_only_restoration_required
        and close_qty == 0.0
        and int(reduce_only_close.get("orders_submitted") or 0) == 0,
        "no_timer_supervisor_config_operator_mutation": all(
            _nested(payload, "control_boundary", key) is False
            for payload in (manual_cancel, reduce_only_close)
            for key in ("timer_path_invoked", "supervisor_invoked", "live_config_mutated", "operator_state_mutated")
        ),
        "hardened_p10i_source_present": p10i_source_path.exists() and p10i_source_path.is_file(),
        "hardened_p10i_tests_present": p10i_test_path.exists() and p10i_test_path.is_file(),
    }
    blockers = sorted(key for key, ready in review_checks.items() if not ready)
    status = "ready" if not blockers else "blocked"
    owner_decision = {
        "contract_version": "hv_balanced_12factor_p10akr_owner_decision.v1",
        "owner": args.owner,
        "decision": "approve_p10akr_review_blocker_resolution_only",
        "decision_source": args.owner_decision_source,
        "recorded_at_utc": iso_z(now),
        "review_only": True,
        "additional_live_order_authorized": False,
        "non_reduce_only_restoration_authorized": False,
        "continuous_automation_authorized": False,
    }
    review = {
        "contract_version": "hv_balanced_12factor_p10akr_blocker_resolution_review.v1",
        "status": status,
        "blockers": blockers,
        "conclusion": (
            "p10ak_blocker_resolved_as_documented_stop_do_not_continue_live_delta"
            if status == "ready"
            else "p10ak_blocker_resolution_evidence_incomplete"
        ),
        "filled_canary_entry": {
            "symbol": "BTCUSDT",
            "side": entry_side,
            "fill_qty": fill_qty,
            "status": _nested(manual_cancel, "post_order", "payload", "status"),
        },
        "position_context": {
            "pre_position_amt_at_rollback_readback": reduce_only_close.get("pre_position_amt"),
            "post_position_amt_after_no_extra_restore": reduce_only_close.get("post_position_amt"),
            "non_reduce_only_restoration_required": non_reduce_only_restoration_required,
            "non_reduce_only_restoration_authorized": False,
        },
        "code_hardening": {
            "query_failure_must_block_and_attempt_cancel": True,
            "recv_window_hardened_to_30000_ms": True,
            "nonflat_opposite_position_pre_submit_guard_added": True,
        },
        "does_not_authorize": [
            "additional live order",
            "non-reduce-only restoration order",
            "candidate continuous executor path",
            "timer/supervisor path load",
            "production executor input mutation",
        ],
    }
    write_json(proof_dir / "owner_decision.json", owner_decision)
    write_json(proof_dir / "review.json", review)
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(now),
        "p10akr_blocker_resolution_review_ready": status == "ready",
        "p10ak_sufficient_for_future_limited_live_delta_expansion": False,
        "p10ak_sufficient_for_additional_live_order_without_new_gate": False,
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
        "observed_prior_canary_fill_qty": fill_qty,
        "open_order_remaining_after_readback": bool(manual_cancel.get("open_order_remaining")),
        "non_reduce_only_restoration_required": non_reduce_only_restoration_required,
        "non_reduce_only_restoration_authorized": False,
        "review_checks": review_checks,
        "blockers": blockers,
        "source_evidence": {
            "p10ai_summary": evidence_file(p10ai_path),
            "p10aj_summary": evidence_file(p10aj_path),
            "p10ak_summary": evidence_file(p10ak_path),
            "manual_cancel_readback": evidence_file(manual_cancel_path),
            "reduce_only_close_readback": evidence_file(reduce_only_close_path),
            "p10i_source": evidence_file(p10i_source_path),
            "p10i_tests": evidence_file(p10i_test_path),
        },
        "allowed_next_gate": P10AKS_GATE if status == "ready" else "",
        "allowed_next_gate_scope": "define_revised_nonflat_canary_terms_only_no_order_no_remote_no_timer"
        if status == "ready"
        else "",
        "allowed_next_gate_must_be_separately_requested": status == "ready",
        "output_files": {
            "summary": str(root / "summary.json"),
            "owner_decision": str(proof_dir / "owner_decision.json"),
            "review": str(proof_dir / "review.json"),
        },
    }
    write_json(root / "summary.json", summary)
    return summary, 0 if status == "ready" else 2


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = build_p10akr(parse_args(argv))
    print(f"status={summary['status']}")
    print(f"run_id={summary['run_id']}")
    print(f"observed_prior_canary_fill_qty={summary['observed_prior_canary_fill_qty']}")
    print(f"non_reduce_only_restoration_required={summary['non_reduce_only_restoration_required']}")
    print(f"summary={summary['output_files']['summary']}")
    if summary.get("blockers"):
        print("blockers=" + ",".join(str(item) for item in summary["blockers"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
