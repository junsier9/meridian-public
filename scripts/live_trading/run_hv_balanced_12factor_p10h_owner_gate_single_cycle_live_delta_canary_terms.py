from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


CONTRACT_VERSION = "hv_balanced_12factor_p10h_owner_gate_single_cycle_live_delta_canary_terms.v1"
DEFAULT_P10G_PARENT = ROOT / "artifacts" / "live_trading" / "proof_artifacts" / "p10g_replacement_dry_run"
DEFAULT_OUTPUT_PARENT = ROOT / "artifacts" / "live_trading" / "proof_artifacts" / "p10h_live_delta_canary_terms"
APPROVE_P10H_DECISION = "approve_p10h_single_cycle_live_delta_canary_terms_only_no_execution"
P10I_GATE = "P10I_execute_single_cycle_live_delta_canary_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P10H owner gate: record exact single-cycle live_delta canary terms. "
            "This gate does not execute live_delta, mutate executor input, invoke "
            "supervisor/timer/remote paths, or submit orders."
        )
    )
    parser.add_argument("--p10g-summary", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P10H_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:p10h_single_cycle_live_delta_canary_terms")
    parser.add_argument("--max-notional-usdt", type=float, default=75.0)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--order-type", default="post_only_limit")
    parser.add_argument("--time-in-force", default="GTX")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--continuous-automation", action="store_true")
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_p10h_owner_gate_single_cycle_live_delta_canary_terms(
    args: argparse.Namespace,
    *,
    now_fn: Any | None = None,
) -> tuple[dict[str, Any], int]:
    now = now_fn or utc_now
    started_at = now()
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    output_root = (
        resolve_repo_path(getattr(args, "output_root", None))
        if getattr(args, "output_root", None)
        else DEFAULT_OUTPUT_PARENT / run_id
    )
    proof_root = output_root / "proof"
    proof_root.mkdir(parents=True, exist_ok=True)

    p10g_summary_path = resolve_p10g_summary(getattr(args, "p10g_summary", None))
    p10g_summary = load_json(p10g_summary_path)
    candidate_plan_path = resolve_repo_path(dict(p10g_summary.get("output_files") or {}).get("candidate_target_plan"))
    candidate_plan = load_json(candidate_plan_path) if candidate_plan_path.exists() else {}
    candidate_symbols = sorted(str(row.get("symbol") or "") for row in list(candidate_plan.get("positions") or []))
    candidate_plan_sha = str(p10g_summary.get("candidate_target_plan_sha256") or "")
    candidate_plan_file_sha = stable_payload_sha256(candidate_plan) if candidate_plan else ""
    requested_symbol = str(getattr(args, "symbol", "") or "").upper()
    terms = build_terms(args=args, candidate_plan_hash=candidate_plan_sha, p10g_summary_path=p10g_summary_path)
    owner_record = {
        "contract_version": "hv_balanced_12factor_p10h_owner_decision.v1",
        "owner": str(getattr(args, "owner", "rulebook_owner")),
        "decision": str(getattr(args, "owner_decision", "")),
        "decision_source": str(getattr(args, "owner_decision_source", "")),
        "recorded_at_utc": iso_z(started_at),
        "decision_question": "approve_single_cycle_live_delta_canary_terms_only_no_execution",
        "terms_approved": str(getattr(args, "owner_decision", "")) == APPROVE_P10H_DECISION,
        "execute_canary_inside_p10h_approved": False,
        "continuous_automation_approved": False,
        "candidate_execution_approved_now": False,
        "live_order_submission_approved_now": False,
    }
    binding = {
        "contract_version": "hv_balanced_12factor_p10h_candidate_plan_hash_binding.v1",
        "run_id": run_id,
        "binding_source": "retained_p10g_or_future_fresh_p10g_rerun_required",
        "retained_p10g_summary": evidence_file(p10g_summary_path),
        "retained_candidate_target_plan": evidence_file(candidate_plan_path),
        "candidate_plan_hash_from_p10g_summary": candidate_plan_sha,
        "candidate_plan_hash_from_candidate_file_payload": candidate_plan_file_sha,
        "candidate_plan_hash_matches_p10g_summary": bool(candidate_plan_sha and candidate_plan_sha == candidate_plan_file_sha),
        "candidate_symbol": requested_symbol,
        "candidate_symbol_in_plan": requested_symbol in candidate_symbols,
        "candidate_symbols_in_plan": candidate_symbols,
        "fresh_rerun_allowed_as_replacement_binding": True,
        "future_execution_must_bind_exact_candidate_hash": True,
    }
    fallback = {
        "contract_version": "hv_balanced_12factor_p10h_baseline_fallback_contract.v1",
        "run_id": run_id,
        "rule": "any_check_failure_reverts_to_baseline_only",
        "fallback_triggers": [
            "fresh account read missing, stale, or canTrade false",
            "fresh position, open-order, fill, or trade fingerprint missing or changed unexpectedly",
            "order book or exchange filters missing, stale, crossed, or incompatible with post-only maker order",
            "candidate plan hash missing, stale, mismatched, or symbol not present",
            "candidate live_delta would exceed max_notional_usdt or more than one order/symbol/cycle",
            "candidate live_delta side/quantity cannot be derived from fresh candidate-vs-current delta",
            "any timer, supervisor, executor, provider, exchange, or risk anomaly appears",
        ],
        "fallback_action": "executor_target_source=baseline_only; candidate_live_delta_enabled=false; submit_no_candidate_order",
        "orders_submitted_on_fallback": 0,
        "fill_count_on_fallback": 0,
    }
    kill_switch = {
        "contract_version": "hv_balanced_12factor_p10h_kill_switch_contract.v1",
        "run_id": run_id,
        "kill_switch": "candidate_live_delta_enabled=false",
        "effect": "revert executor target source to baseline_only and block candidate order submission",
        "must_be_checked_before_order": True,
        "must_be_checked_after_order": True,
        "active_state_selects_baseline": True,
        "orders_submitted_when_active": 0,
        "fill_count_when_active": 0,
    }
    rollback = {
        "contract_version": "hv_balanced_12factor_p10h_rollback_contract.v1",
        "run_id": run_id,
        "rollback_conditions": [
            "open canary order remains after observation window",
            "post-only order is rejected, expires, crosses, or violates exchange filters",
            "candidate fill is partial or complete and post-run reconciliation detects mismatch",
            "unexpected order/cancel/fill/trade delta appears",
            "candidate plan hash or executor input hash differs from approved binding",
            "manual/operator kill switch is toggled",
        ],
        "rollback_actions": [
            "cancel open canary order",
            "if filled, prepare reduce-only close plan only after explicit owner confirmation unless emergency safety policy requires otherwise",
            "write post-run reconciliation bundle with pre/post account, position, open-order, fill, and trade fingerprints",
            "disable candidate_live_delta_enabled and revert to baseline-only",
        ],
        "reduce_only_close_only_if_filled": True,
        "post_run_reconciliation_required": True,
    }
    acceptance = {
        "contract_version": "hv_balanced_12factor_p10h_future_p10i_acceptance_contract.v1",
        "run_id": run_id,
        "allowed_next_gate": P10I_GATE,
        "must_be_separately_requested": True,
        "fresh_remote_proof_required_before_execution": True,
        "required_pre_order_proofs": [
            "fresh remote account read with canTrade=true",
            "pre position fingerprint",
            "pre open-order fingerprint",
            "pre fill/trade fingerprint",
            "fresh BTCUSDT order book and exchange filters",
            "candidate plan hash binding to retained P10G or fresh P10G rerun",
            "baseline fallback readback",
            "kill switch readback",
        ],
        "required_post_order_proofs": [
            "post position fingerprint",
            "post open-order fingerprint",
            "post fill/trade fingerprint",
            "post-run reconciliation",
            "zero unexpected order/cancel/fill/trade delta",
        ],
    }
    non_authorization = {
        "contract_version": "hv_balanced_12factor_p10h_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "define_single_cycle_canary_terms": True,
            "future_p10i_single_cycle_canary_discussion": True,
            "execute_canary_inside_p10h": False,
            "candidate_execution_now": False,
            "live_order_submission_now": False,
            "target_plan_replacement_now": False,
            "executor_input_mutation_now": False,
            "timer_path_load": False,
            "supervisor_invocation": False,
            "remote_sync": False,
            "remote_execution": False,
            "continuous_automation": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_state_mutation": False,
        },
    }
    control = {
        "contract_version": "hv_balanced_12factor_p10h_control_boundary_readback.v1",
        "run_id": run_id,
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
        "continuous_automation_enabled": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
    }

    term_checks = terms_valid(terms)
    gates = {
        "owner_decision_p10h_terms_only_recorded": owner_record["terms_approved"],
        "output_root_under_proof_artifacts": path_contains_part(output_root, "proof_artifacts"),
        "p10g_replacement_dry_run_ready": p10g_ready(p10g_summary),
        "candidate_plan_hash_binding_ready": binding["candidate_plan_hash_matches_p10g_summary"]
        and binding["candidate_symbol_in_plan"],
        "baseline_fallback_contract_ready": fallback["orders_submitted_on_fallback"] == 0,
        "kill_switch_contract_ready": kill_switch["active_state_selects_baseline"],
        "rollback_contract_ready": rollback["reduce_only_close_only_if_filled"]
        and rollback["post_run_reconciliation_required"],
        "no_execution_inside_p10h": control["candidate_execution_performed"] is False
        and control["live_order_submission_performed"] is False,
        **term_checks,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"

    terms_path = proof_root / "single_cycle_live_delta_canary_terms.json"
    owner_path = proof_root / "owner_decision_record.json"
    binding_path = proof_root / "candidate_plan_hash_binding.json"
    fallback_path = proof_root / "baseline_fallback_contract.json"
    kill_switch_path = proof_root / "kill_switch_contract.json"
    rollback_path = proof_root / "rollback_contract.json"
    acceptance_path = proof_root / "future_p10i_acceptance_contract.json"
    matrix_path = proof_root / "non_authorization_matrix.json"
    control_path = proof_root / "control_boundary_readback.json"
    summary_path = output_root / "summary.json"
    report_path = output_root / "p10h.md"

    output_files = {
        "summary": str(summary_path),
        "terms": str(terms_path),
        "owner_decision_record": str(owner_path),
        "candidate_plan_hash_binding": str(binding_path),
        "baseline_fallback_contract": str(fallback_path),
        "kill_switch_contract": str(kill_switch_path),
        "rollback_contract": str(rollback_path),
        "future_p10i_acceptance_contract": str(acceptance_path),
        "non_authorization_matrix": str(matrix_path),
        "control_boundary_readback": str(control_path),
        "report": str(report_path),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "p10h_owner_gate_single_cycle_live_delta_canary_terms_ready": status == "ready",
        "approved_max_notional_usdt": terms["max_notional_usdt"],
        "approved_symbol": terms["symbol"],
        "approved_order_type": terms["order_type"],
        "approved_time_in_force": terms["time_in_force"],
        "approved_cycles": terms["cycles"],
        "continuous_automation": terms["continuous_automation"],
        "candidate_plan_hash": terms["candidate_plan_hash"],
        "candidate_plan_hash_binding_ready": gates["candidate_plan_hash_binding_ready"],
        "baseline_fallback_ready": gates["baseline_fallback_contract_ready"],
        "kill_switch_ready": gates["kill_switch_contract_ready"],
        "rollback_ready": gates["rollback_contract_ready"],
        "future_p10i_single_cycle_canary_authorized_if_separately_requested": status == "ready",
        "fresh_remote_proof_required_before_execution": True,
        "execute_canary_inside_p10h": False,
        "candidate_execution_authorized_now": False,
        "live_order_submission_authorized_now": False,
        "target_plan_replacement_authorized_now": False,
        "executor_input_mutation_authorized_now": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "allowed_next_gate": P10I_GATE,
        "allowed_next_gate_must_be_separately_requested": True,
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {
            "p10g_summary": evidence_file(p10g_summary_path),
            "candidate_target_plan": evidence_file(candidate_plan_path),
        },
        "output_files": output_files,
    }

    for path, payload in (
        (terms_path, terms),
        (owner_path, owner_record),
        (binding_path, binding),
        (fallback_path, fallback),
        (kill_switch_path, kill_switch),
        (rollback_path, rollback),
        (acceptance_path, acceptance),
        (matrix_path, non_authorization),
        (control_path, control),
        (summary_path, summary),
    ):
        write_json(path, payload)
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if status == "ready" else 2


def build_terms(*, args: argparse.Namespace, candidate_plan_hash: str, p10g_summary_path: Path) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_12factor_p10h_single_cycle_live_delta_canary_terms.v1",
        "max_notional_usdt": float(getattr(args, "max_notional_usdt", 75.0)),
        "symbol": str(getattr(args, "symbol", "BTCUSDT") or "").upper(),
        "order_type": str(getattr(args, "order_type", "post_only_limit") or "").lower(),
        "maker_only_required": True,
        "post_only_required": True,
        "time_in_force": str(getattr(args, "time_in_force", "GTX") or "").upper(),
        "cycles": int(getattr(args, "cycles", 1) or 0),
        "continuous_automation": bool(getattr(args, "continuous_automation", False)),
        "max_orders_per_cycle": 1,
        "max_symbols_per_cycle": 1,
        "market_orders_allowed": False,
        "side": "derive_from_fresh_candidate_delta",
        "quantity": "derive_from_fresh_candidate_delta_capped_by_max_notional_and_exchange_filters",
        "candidate_plan_hash": candidate_plan_hash,
        "candidate_plan_hash_binding_source": str(p10g_summary_path),
        "baseline_fallback": "any_check_failure_reverts_to_baseline_only",
        "kill_switch": "candidate_live_delta_enabled=false / revert baseline-only",
        "rollback": "cancel open order; reduce-only close only if filled; post-run reconciliation",
    }


def terms_valid(terms: dict[str, Any]) -> dict[str, bool]:
    return {
        "max_notional_usdt_is_75": abs(float(terms.get("max_notional_usdt") or 0.0) - 75.0) <= 1e-12,
        "symbol_is_btcusdt": terms.get("symbol") == "BTCUSDT",
        "order_type_is_post_only_limit": terms.get("order_type") == "post_only_limit",
        "maker_only_required": terms.get("maker_only_required") is True,
        "post_only_required": terms.get("post_only_required") is True,
        "time_in_force_is_gtx": terms.get("time_in_force") == "GTX",
        "cycles_is_one": int(terms.get("cycles") or 0) == 1,
        "continuous_automation_false": terms.get("continuous_automation") is False,
        "single_order_single_symbol": int(terms.get("max_orders_per_cycle") or 0) == 1
        and int(terms.get("max_symbols_per_cycle") or 0) == 1,
        "market_orders_forbidden": terms.get("market_orders_allowed") is False,
        "candidate_plan_hash_present": bool(terms.get("candidate_plan_hash")),
        "baseline_fallback_explicit": "baseline" in str(terms.get("baseline_fallback") or ""),
        "kill_switch_explicit": "candidate_live_delta_enabled=false" in str(terms.get("kill_switch") or ""),
        "rollback_explicit": "cancel open order" in str(terms.get("rollback") or "")
        and "reduce-only close only if filled" in str(terms.get("rollback") or "")
        and "post-run reconciliation" in str(terms.get("rollback") or ""),
    }


def p10g_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("status") == "ready"
        and summary.get("p10g_candidate_target_plan_replacement_dry_run_ready") is True
        and summary.get("candidate_target_plan_replacement_semantics_proven") is True
        and summary.get("hash_binding_proven") is True
        and summary.get("baseline_fallback_proven") is True
        and summary.get("kill_switch_proven") is True
        and summary.get("actual_executor_input_changed") is False
        and summary.get("actual_target_plan_replaced") is False
        and summary.get("candidate_execution_authorized") is False
        and summary.get("live_order_submission_authorized") is False
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
    )


def resolve_p10g_summary(path_ref: Path | str | None) -> Path:
    if path_ref:
        path = resolve_repo_path(path_ref)
        if path.is_dir():
            path = path / "summary.json"
        if not path.exists():
            raise FileNotFoundError(path)
        return path
    candidates = sorted(DEFAULT_P10G_PARENT.glob("*/summary.json"), key=lambda path: path.stat().st_mtime)
    ready = [path for path in candidates if load_json(path).get("status") == "ready"]
    if not ready:
        raise FileNotFoundError(f"no ready P10G summary.json found under {DEFAULT_P10G_PARENT}")
    return ready[-1]


def resolve_repo_path(path_ref: Path | str | None) -> Path:
    raw = str(path_ref or "").strip()
    if not raw:
        return Path("")
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (ROOT / path).resolve()


def path_contains_part(path: Path, part: str) -> bool:
    text = str(path)
    return bool(text) and text != "." and part.lower() in [item.lower() for item in path.resolve().parts]


def stable_payload_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(json_safe(payload), indent=2, sort_keys=True).encode("utf-8") + b"\n").hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_file(path: Path | None) -> dict[str, Any]:
    if not path or str(path) == "." or not path.exists() or not path.is_file():
        return {"path": "" if not path or str(path) == "." else str(path), "exists": False, "sha256": ""}
    return {"path": str(path), "exists": True, "sha256": file_sha256(path)}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if pd.isna(value):
        return None
    return value


def render_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# hv_balanced 12-Factor P10H Owner Gate Single-Cycle Live Delta Canary Terms",
            "",
            f"`Status: {summary['status']}`",
            "",
            "```text",
            f"max_notional_usdt = {summary['approved_max_notional_usdt']}",
            f"symbol = {summary['approved_symbol']}",
            f"order_type = {summary['approved_order_type']}",
            f"time_in_force = {summary['approved_time_in_force']}",
            f"cycles = {summary['approved_cycles']}",
            f"continuous_automation = {str(summary['continuous_automation']).lower()}",
            f"candidate_plan_hash = {summary['candidate_plan_hash']}",
            "execute_canary_inside_p10h = false",
            "orders_submitted = 0",
            "fill_count = 0",
            "```",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = run_p10h_owner_gate_single_cycle_live_delta_canary_terms(parse_args(argv))
    print(json.dumps(json_safe(summary), indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
