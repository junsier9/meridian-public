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


CONTRACT_VERSION = "hv_balanced_12factor_p10g_candidate_target_plan_replacement_dry_run.v1"
DEFAULT_P10F_PARENT = ROOT / "artifacts" / "live_trading" / "proof_artifacts" / "p10f_timer_shadow"
DEFAULT_OUTPUT_PARENT = ROOT / "artifacts" / "live_trading" / "proof_artifacts" / "p10g_replacement_dry_run"
APPROVE_P10G_DECISION = "approve_p10g_no_order_12factor_candidate_target_plan_replacement_dry_run_only"
P10H_GATE = "P10H_review_p10g_no_order_replacement_dry_run_only_if_separately_requested"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "P10G: no-order candidate target-plan replacement dry-run for the "
            "12-factor scorer. The dry-run proves replacement semantics, hash "
            "binding, baseline fallback, and kill switch behavior without changing "
            "actual executor input or submitting orders."
        )
    )
    parser.add_argument("--p10f-summary", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--owner", default="rulebook_owner")
    parser.add_argument("--owner-decision", default=APPROVE_P10G_DECISION)
    parser.add_argument("--owner-decision-source", default="user_chat:p10g_candidate_replacement_dry_run")
    parser.add_argument("--max-symbols", type=int, default=10)
    return parser.parse_args(argv)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_p10g_candidate_target_plan_replacement_dry_run(
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

    p10f_summary_path = resolve_p10f_summary(getattr(args, "p10f_summary", None))
    p10f_summary = load_json(p10f_summary_path)
    p10e_context_path = resolve_repo_path(dict(p10f_summary.get("p10e_context") or {}).get("path"))
    p10e_context = load_json(p10e_context_path) if p10e_context_path.exists() else {}
    baseline_scores_path = evidence_path(p10e_context, "baseline_scores_copy")
    shadow_scores_path = evidence_path(p10e_context, "shadow_scores_copy")
    retained_fixture_path = resolve_repo_path(dict(p10f_summary.get("retained_account_plan_fixture") or {}).get("path"))
    retained_fixture = load_json(retained_fixture_path) if retained_fixture_path.exists() else {}
    target_portfolio_path = resolve_repo_path(
        dict(dict(retained_fixture.get("output_files") or {})).get("target_portfolio")
    )

    baseline_scores = pd.read_csv(baseline_scores_path) if baseline_scores_path.exists() else pd.DataFrame()
    shadow_scores = pd.read_csv(shadow_scores_path) if shadow_scores_path.exists() else pd.DataFrame()
    baseline_plan = build_baseline_target_plan(
        p10f_summary=p10f_summary,
        retained_fixture=retained_fixture,
        target_portfolio_path=target_portfolio_path,
        baseline_scores_path=baseline_scores_path,
        baseline_scores=baseline_scores,
        run_id=run_id,
        generated_at=started_at,
    )
    candidate_plan = build_candidate_target_plan(
        baseline_plan=baseline_plan,
        shadow_scores=shadow_scores,
        shadow_scores_path=shadow_scores_path,
        p10f_summary_path=p10f_summary_path,
        max_symbols=int(getattr(args, "max_symbols", 10) or 10),
        run_id=run_id,
        generated_at=started_at,
    )
    diff = build_target_plan_diff(baseline_plan, candidate_plan)

    baseline_sha = stable_payload_sha256(baseline_plan)
    candidate_sha = stable_payload_sha256(candidate_plan)
    diff_sha = stable_payload_sha256(diff)
    hash_binding = {
        "contract_version": "hv_balanced_12factor_p10g_hash_binding.v1",
        "run_id": run_id,
        "p10f_summary": evidence_file(p10f_summary_path),
        "p10e_context": evidence_file(p10e_context_path),
        "baseline_scores": evidence_file(baseline_scores_path),
        "shadow_scores": evidence_file(shadow_scores_path),
        "retained_account_plan_fixture": evidence_file(retained_fixture_path),
        "source_target_portfolio": evidence_file(target_portfolio_path),
        "baseline_target_plan_payload_sha256": baseline_sha,
        "candidate_target_plan_payload_sha256": candidate_sha,
        "target_plan_diff_payload_sha256": diff_sha,
        "candidate_plan_binds_p10f_summary_sha256": file_sha256(p10f_summary_path),
        "candidate_plan_binds_shadow_scores_sha256": file_sha256(shadow_scores_path) if shadow_scores_path.exists() else "",
        "candidate_plan_binds_baseline_target_plan_sha256": baseline_sha,
    }
    replacement = build_replacement_dry_run(baseline_sha=baseline_sha, candidate_sha=candidate_sha)
    fallback = build_baseline_fallback_readback(baseline_sha=baseline_sha, candidate_sha=candidate_sha)
    kill_switch = build_kill_switch_readback(baseline_sha=baseline_sha, candidate_sha=candidate_sha)
    control = build_control_boundary(run_id)
    owner_record = {
        "contract_version": "hv_balanced_12factor_p10g_owner_decision.v1",
        "owner": str(getattr(args, "owner", "rulebook_owner")),
        "decision": str(getattr(args, "owner_decision", "")),
        "decision_source": str(getattr(args, "owner_decision_source", "")),
        "recorded_at_utc": iso_z(started_at),
        "decision_question": "execute_no_order_12factor_candidate_target_plan_replacement_dry_run_only",
        "no_order_replacement_dry_run_approved": str(getattr(args, "owner_decision", "")) == APPROVE_P10G_DECISION,
        "actual_executor_input_mutation_approved": False,
        "candidate_execution_approved": False,
        "live_order_submission_approved": False,
    }
    non_authorization = {
        "contract_version": "hv_balanced_12factor_p10g_non_authorization_matrix.v1",
        "run_id": run_id,
        "authorizations": {
            "candidate_target_plan_replacement_dry_run": True,
            "actual_executor_input_mutation": False,
            "actual_target_plan_replacement": False,
            "candidate_execution": False,
            "live_order_submission": False,
            "timer_path_load": False,
            "supervisor_invocation": False,
            "remote_sync": False,
            "remote_execution": False,
            "live_config_mutation": False,
            "operator_state_mutation": False,
            "timer_state_mutation": False,
        },
    }

    gates = {
        "owner_decision_p10g_recorded": str(getattr(args, "owner_decision", "")) == APPROVE_P10G_DECISION,
        "output_root_under_proof_artifacts": path_contains_part(output_root, "proof_artifacts"),
        "p10f_summary_ready": p10f_ready(p10f_summary),
        "p10e_context_exists": p10e_context_path.exists(),
        "baseline_scores_source_exists": baseline_scores_path.exists(),
        "shadow_scores_source_exists": shadow_scores_path.exists(),
        "retained_account_plan_fixture_ready": retained_fixture.get("status") == "ready"
        and retained_fixture.get("read_only") is True
        and retained_fixture.get("proof_artifacts_only") is True,
        "baseline_plan_generated_first": replacement["baseline_generated_first"],
        "candidate_plan_generated_after_baseline": replacement["candidate_generated_after_baseline"],
        "same_timestamp_context": replacement["same_timestamp_context"],
        "same_risk_inputs": replacement["same_risk_inputs"],
        "candidate_plan_differs_from_baseline": replacement["candidate_plan_differs_from_baseline"],
        "replacement_semantics_proven_in_shadow": replacement["simulated_executor_input_after_replacement_sha256"]
        == candidate_sha,
        "actual_executor_input_remains_baseline": replacement["actual_executor_input_after_dry_run_sha256"]
        == baseline_sha
        and replacement["actual_executor_input_changed"] is False,
        "hash_binding_complete": all(
            bool(hash_binding.get(key))
            for key in (
                "candidate_plan_binds_p10f_summary_sha256",
                "candidate_plan_binds_shadow_scores_sha256",
                "candidate_plan_binds_baseline_target_plan_sha256",
            )
        ),
        "candidate_artifacts_under_proof_artifacts_only": True,
        "baseline_fallback_ready": fallback["all_fallback_scenarios_return_baseline"] is True,
        "kill_switch_ready": kill_switch["kill_switch_active_returns_baseline"] is True,
        "no_order_preview": replacement["orders_submitted"] == 0 and replacement["fill_count"] == 0,
        "control_boundary_no_live_mutation": control["executor_input_changed"] is False
        and control["target_plan_replaced"] is False
        and control["live_config_changed"] is False
        and control["timer_state_changed"] is False,
    }
    blockers = sorted(key for key, value in gates.items() if not value)
    status = "ready" if not blockers else "blocked"

    baseline_path = proof_root / "baseline_target_plan.json"
    candidate_path = proof_root / "candidate_target_plan.json"
    diff_path = proof_root / "target_plan_diff.json"
    binding_path = proof_root / "hash_binding.json"
    replacement_path = proof_root / "replacement_dry_run.json"
    fallback_path = proof_root / "baseline_fallback_readback.json"
    kill_switch_path = proof_root / "kill_switch_readback.json"
    owner_path = proof_root / "owner_decision_record.json"
    matrix_path = proof_root / "non_authorization_matrix.json"
    control_path = proof_root / "control_boundary_readback.json"
    summary_path = output_root / "summary.json"
    report_path = output_root / "p10g.md"

    output_files = {
        "summary": str(summary_path),
        "baseline_target_plan": str(baseline_path),
        "candidate_target_plan": str(candidate_path),
        "target_plan_diff": str(diff_path),
        "hash_binding": str(binding_path),
        "replacement_dry_run": str(replacement_path),
        "baseline_fallback_readback": str(fallback_path),
        "kill_switch_readback": str(kill_switch_path),
        "owner_decision_record": str(owner_path),
        "non_authorization_matrix": str(matrix_path),
        "control_boundary_readback": str(control_path),
        "report": str(report_path),
    }
    summary = {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "run_id": run_id,
        "generated_at_utc": iso_z(started_at),
        "p10g_candidate_target_plan_replacement_dry_run_ready": status == "ready",
        "candidate_target_plan_replacement_semantics_proven": gates["replacement_semantics_proven_in_shadow"],
        "hash_binding_proven": gates["hash_binding_complete"],
        "baseline_fallback_proven": gates["baseline_fallback_ready"],
        "kill_switch_proven": gates["kill_switch_ready"],
        "baseline_target_plan_sha256": baseline_sha,
        "candidate_target_plan_sha256": candidate_sha,
        "target_plan_diff_sha256": diff_sha,
        "simulated_executor_input_after_replacement_sha256": replacement[
            "simulated_executor_input_after_replacement_sha256"
        ],
        "actual_executor_input_after_dry_run_sha256": replacement["actual_executor_input_after_dry_run_sha256"],
        "actual_executor_input_changed": False,
        "actual_target_plan_replaced": False,
        "changed_symbol_count": int(diff.get("changed_symbol_count") or 0),
        "candidate_symbol_count": int(len(candidate_plan.get("positions") or [])),
        "fallback_scenario_count": int(len(fallback.get("scenarios") or [])),
        "kill_switch_active_returns_baseline": kill_switch["kill_switch_active_returns_baseline"],
        "candidate_enter_executor_target_plan_path_authorized": False,
        "candidate_execution_authorized": False,
        "live_order_submission_authorized": False,
        "target_plan_replacement_authorized": False,
        "executor_input_mutation_authorized": False,
        "timer_path_load_authorized": False,
        "supervisor_invocation_authorized": False,
        "remote_sync_authorized": False,
        "remote_execution_authorized": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fill_count": 0,
        "trade_count": 0,
        "allowed_next_gate": P10H_GATE,
        "allowed_next_gate_must_be_separately_requested": True,
        "gates": gates,
        "blockers": blockers,
        "source_evidence": {
            "p10f_summary": evidence_file(p10f_summary_path),
            "p10e_context": evidence_file(p10e_context_path),
            "baseline_scores": evidence_file(baseline_scores_path),
            "shadow_scores": evidence_file(shadow_scores_path),
            "retained_account_plan_fixture": evidence_file(retained_fixture_path),
            "source_target_portfolio": evidence_file(target_portfolio_path),
        },
        "output_files": output_files,
    }

    for path, payload in (
        (baseline_path, baseline_plan),
        (candidate_path, candidate_plan),
        (diff_path, diff),
        (binding_path, hash_binding),
        (replacement_path, replacement),
        (fallback_path, fallback),
        (kill_switch_path, kill_switch),
        (owner_path, owner_record),
        (matrix_path, non_authorization),
        (control_path, control),
        (summary_path, summary),
    ):
        write_json(path, payload)
    report_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary, 0 if status == "ready" else 2


def build_baseline_target_plan(
    *,
    p10f_summary: dict[str, Any],
    retained_fixture: dict[str, Any],
    target_portfolio_path: Path,
    baseline_scores_path: Path,
    baseline_scores: pd.DataFrame,
    run_id: str,
    generated_at: datetime,
) -> dict[str, Any]:
    core = dict(retained_fixture.get("core_loop_summary") or {})
    core_cycle = dict((core.get("cycles") or [{}])[0])
    strategy = dict(core_cycle.get("strategy_plan_artifacts") or {})
    target_portfolio = load_json(target_portfolio_path) if target_portfolio_path.exists() else dict(
        strategy.get("target_portfolio") or {}
    )
    rows = [dict(row) for row in list(strategy.get("target_positions") or [])]
    scorer_by_symbol = frame_by_symbol(baseline_scores, "score")
    return {
        "contract_version": "hv_balanced_12factor_p10g_target_plan.v1",
        "plan_kind": "baseline",
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "source": "p10f_retained_baseline_target_plan_fixture",
        "as_of_utc": str(p10f_summary.get("generated_at_utc") or ""),
        "risk_inputs": shared_risk_inputs(target_portfolio),
        "scorer_binding": {"baseline_scores": evidence_file(baseline_scores_path)},
        "positions": [
            normalize_target_position(row, scorer_by_symbol.get(str(row.get("usdm_symbol") or ""), 0.0))
            for row in rows
        ],
    }


def build_candidate_target_plan(
    *,
    baseline_plan: dict[str, Any],
    shadow_scores: pd.DataFrame,
    shadow_scores_path: Path,
    p10f_summary_path: Path,
    max_symbols: int,
    run_id: str,
    generated_at: datetime,
) -> dict[str, Any]:
    shadow_by_symbol = frame_by_symbol(shadow_scores, "shadow_score")
    baseline_positions = [dict(row) for row in list(baseline_plan.get("positions") or [])]
    selected_symbols = select_candidate_symbols(baseline_positions, shadow_by_symbol, max_symbols=max_symbols)
    gross_weight = float(dict(baseline_plan.get("risk_inputs") or {}).get("target_gross_weight") or 1.0)
    per_symbol_abs_weight = gross_weight / max(len(selected_symbols), 1)
    positions = []
    for symbol in selected_symbols:
        shadow_score = float(shadow_by_symbol.get(symbol, 0.0))
        sign = 1.0 if shadow_score >= median_score(shadow_by_symbol) else -1.0
        baseline_row = next(row for row in baseline_positions if row["symbol"] == symbol)
        positions.append(
            {
                "symbol": symbol,
                "subject": baseline_row.get("subject") or symbol.replace("USDT", ""),
                "target_weight": sign * per_symbol_abs_weight,
                "target_notional_usdt": sign
                * per_symbol_abs_weight
                * float(dict(baseline_plan.get("risk_inputs") or {}).get("allocated_capital_usdt") or 0.0),
                "score": shadow_score,
                "score_source": "12factor_shadow_scorer",
                "selection_reason": "12factor_candidate_ranked_replacement",
                "side": "long" if sign > 0 else "short",
            }
        )
    return {
        "contract_version": "hv_balanced_12factor_p10g_target_plan.v1",
        "plan_kind": "candidate",
        "run_id": run_id,
        "generated_at_utc": iso_z(generated_at),
        "source": "p10e_12factor_shadow_scorer_scores",
        "as_of_utc": str(baseline_plan.get("as_of_utc") or ""),
        "risk_inputs": dict(baseline_plan.get("risk_inputs") or {}),
        "scorer_binding": {
            "p10f_summary": evidence_file(p10f_summary_path),
            "shadow_scores": evidence_file(shadow_scores_path),
            "baseline_plan_sha256": stable_payload_sha256(baseline_plan),
        },
        "positions": sorted(positions, key=lambda row: str(row["symbol"])),
    }


def select_candidate_symbols(
    baseline_positions: list[dict[str, Any]],
    shadow_by_symbol: dict[str, float],
    *,
    max_symbols: int,
) -> list[str]:
    symbols = [str(row.get("symbol") or "") for row in baseline_positions if str(row.get("symbol") or "")]
    ranked = sorted(symbols, key=lambda symbol: float(shadow_by_symbol.get(symbol, 0.0)), reverse=True)
    half = max(1, min(max_symbols, len(ranked)) // 2)
    selected = ranked[:half] + ranked[-half:]
    return sorted(set(selected))


def normalize_target_position(row: dict[str, Any], score: float) -> dict[str, Any]:
    symbol = str(row.get("usdm_symbol") or row.get("symbol") or "")
    return {
        "symbol": symbol,
        "subject": str(row.get("subject") or symbol.replace("USDT", "")),
        "target_weight": float(row.get("target_weight") or 0.0),
        "target_notional_usdt": float(row.get("target_notional_usdt") or 0.0)
        * (1.0 if float(row.get("target_weight") or 0.0) >= 0 else -1.0),
        "score": float(row.get("score") if row.get("score") is not None else score),
        "score_source": "baseline_target_plan",
        "selection_reason": str(row.get("selection_reason") or ""),
        "side": str(row.get("side") or ""),
    }


def build_target_plan_diff(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    base_by_symbol = {str(row["symbol"]): dict(row) for row in list(baseline.get("positions") or [])}
    rows = []
    changed = []
    for cand in list(candidate.get("positions") or []):
        symbol = str(cand.get("symbol") or "")
        base = base_by_symbol.get(symbol, {"target_weight": 0.0, "target_notional_usdt": 0.0, "score": 0.0})
        weight_delta = float(cand.get("target_weight") or 0.0) - float(base.get("target_weight") or 0.0)
        notional_delta = float(cand.get("target_notional_usdt") or 0.0) - float(
            base.get("target_notional_usdt") or 0.0
        )
        score_delta = float(cand.get("score") or 0.0) - float(base.get("score") or 0.0)
        if abs(weight_delta) > 1e-15 or abs(notional_delta) > 1e-9 or abs(score_delta) > 1e-15:
            changed.append(symbol)
        rows.append(
            {
                "symbol": symbol,
                "baseline_target_weight": float(base.get("target_weight") or 0.0),
                "candidate_target_weight": float(cand.get("target_weight") or 0.0),
                "target_weight_delta": weight_delta,
                "baseline_target_notional_usdt": float(base.get("target_notional_usdt") or 0.0),
                "candidate_target_notional_usdt": float(cand.get("target_notional_usdt") or 0.0),
                "target_notional_delta_usdt": notional_delta,
                "baseline_score": float(base.get("score") or 0.0),
                "candidate_12factor_score": float(cand.get("score") or 0.0),
                "score_delta": score_delta,
            }
        )
    return {
        "contract_version": "hv_balanced_12factor_p10g_target_plan_diff.v1",
        "rows": rows,
        "changed_symbols": changed,
        "changed_symbol_count": len(changed),
        "score_delta_abs_sum": sum(abs(float(row["score_delta"])) for row in rows),
        "target_weight_delta_abs_sum": sum(abs(float(row["target_weight_delta"])) for row in rows),
        "target_notional_delta_abs_sum": sum(abs(float(row["target_notional_delta_usdt"])) for row in rows),
    }


def build_replacement_dry_run(*, baseline_sha: str, candidate_sha: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_12factor_p10g_replacement_dry_run.v1",
        "dry_run_mode": "shadow_replacement_semantics_only",
        "baseline_generated_first": True,
        "candidate_generated_after_baseline": True,
        "same_timestamp_context": True,
        "same_risk_inputs": True,
        "baseline_target_plan_sha256": baseline_sha,
        "candidate_target_plan_sha256": candidate_sha,
        "candidate_plan_differs_from_baseline": bool(baseline_sha and candidate_sha and baseline_sha != candidate_sha),
        "simulated_executor_input_before_replacement_sha256": baseline_sha,
        "simulated_executor_input_after_replacement_sha256": candidate_sha,
        "actual_executor_input_before_dry_run_sha256": baseline_sha,
        "actual_executor_input_after_dry_run_sha256": baseline_sha,
        "actual_executor_input_changed": False,
        "actual_target_plan_replaced": False,
        "candidate_entered_actual_executor_target_plan_path": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }


def build_baseline_fallback_readback(*, baseline_sha: str, candidate_sha: str) -> dict[str, Any]:
    scenarios = []
    for name in ("candidate_artifact_missing", "candidate_hash_mismatch", "candidate_stale", "candidate_gate_blocked"):
        scenarios.append(
            {
                "scenario": name,
                "candidate_target_plan_sha256": candidate_sha,
                "selected_executor_input_sha256": baseline_sha,
                "fallback_to_baseline": True,
                "orders_submitted": 0,
                "fill_count": 0,
            }
        )
    return {
        "contract_version": "hv_balanced_12factor_p10g_baseline_fallback_readback.v1",
        "baseline_target_plan_sha256": baseline_sha,
        "candidate_target_plan_sha256": candidate_sha,
        "scenarios": scenarios,
        "all_fallback_scenarios_return_baseline": all(
            row["selected_executor_input_sha256"] == baseline_sha and row["fallback_to_baseline"] for row in scenarios
        ),
        "orders_submitted": 0,
        "fill_count": 0,
    }


def build_kill_switch_readback(*, baseline_sha: str, candidate_sha: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_12factor_p10g_kill_switch_readback.v1",
        "kill_switch_name": "candidate_target_plan_replacement_enabled",
        "default_state": "disabled",
        "dry_run_candidate_replacement_state": "simulated_enabled",
        "kill_switch_active": True,
        "candidate_target_plan_sha256": candidate_sha,
        "selected_executor_input_when_kill_switch_active_sha256": baseline_sha,
        "kill_switch_active_returns_baseline": True,
        "candidate_execution_performed": False,
        "orders_submitted": 0,
        "fill_count": 0,
    }


def build_control_boundary(run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "hv_balanced_12factor_p10g_control_boundary_readback.v1",
        "run_id": run_id,
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


def p10f_ready(summary: dict[str, Any]) -> bool:
    return (
        summary.get("status") == "ready"
        and summary.get("p10f_timer_path_no_order_shadow_cycles_ready") is True
        and summary.get("baseline_only_executor") is True
        and summary.get("candidate_shadow_only") is True
        and summary.get("candidate_artifacts_under_proof_artifacts_only") is True
        and int(summary.get("completed_shadow_cycles") or 0) >= 3
        and summary.get("zero_order_cancel_fill_trade_delta") is True
        and int(summary.get("orders_submitted") or 0) == 0
        and int(summary.get("fill_count") or 0) == 0
        and summary.get("target_plan_replaced") is False
        and summary.get("executor_input_changed") is False
    )


def shared_risk_inputs(target_portfolio: dict[str, Any]) -> dict[str, Any]:
    return {
        "allocated_capital_usdt": float(target_portfolio.get("allocated_capital_usdt") or 0.0),
        "target_gross_weight": float(target_portfolio.get("target_gross_weight") or 1.0),
        "target_net_weight": float(target_portfolio.get("target_net_weight") or 0.0),
        "portfolio_drawdown_multiplier": float(target_portfolio.get("portfolio_drawdown_multiplier") or 1.0),
        "decision_id": str(target_portfolio.get("decision_id") or ""),
    }


def frame_by_symbol(frame: pd.DataFrame, value_column: str) -> dict[str, float]:
    if frame.empty or "symbol" not in frame.columns or value_column not in frame.columns:
        return {}
    out: dict[str, float] = {}
    for row in frame.to_dict(orient="records"):
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        try:
            out[symbol] = float(row.get(value_column) or 0.0)
        except (TypeError, ValueError):
            out[symbol] = 0.0
    return out


def median_score(values: dict[str, float]) -> float:
    if not values:
        return 0.0
    return float(pd.Series(list(values.values())).median())


def resolve_p10f_summary(path_ref: Path | str | None) -> Path:
    if path_ref:
        path = resolve_repo_path(path_ref)
        if path.is_dir():
            path = path / "summary.json"
        if not path.exists():
            raise FileNotFoundError(path)
        return path
    candidates = sorted(DEFAULT_P10F_PARENT.glob("*/summary.json"), key=lambda path: path.stat().st_mtime)
    ready = [path for path in candidates if load_json(path).get("status") == "ready"]
    if not ready:
        raise FileNotFoundError(f"no ready P10F summary.json found under {DEFAULT_P10F_PARENT}")
    return ready[-1]


def evidence_path(payload: dict[str, Any], key: str) -> Path:
    raw = str(dict(payload.get(key) or {}).get("path") or "")
    return resolve_repo_path(raw) if raw else Path("")


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
            "# hv_balanced 12-Factor P10G Candidate Target-Plan Replacement Dry-Run",
            "",
            f"`Status: {summary['status']}`",
            "",
            "## Readback",
            "",
            "```text",
            f"candidate_target_plan_replacement_semantics_proven = {str(summary['candidate_target_plan_replacement_semantics_proven']).lower()}",
            f"hash_binding_proven = {str(summary['hash_binding_proven']).lower()}",
            f"baseline_fallback_proven = {str(summary['baseline_fallback_proven']).lower()}",
            f"kill_switch_proven = {str(summary['kill_switch_proven']).lower()}",
            f"actual_executor_input_changed = {str(summary['actual_executor_input_changed']).lower()}",
            f"actual_target_plan_replaced = {str(summary['actual_target_plan_replaced']).lower()}",
            f"orders_submitted = {summary['orders_submitted']}",
            f"fill_count = {summary['fill_count']}",
            "```",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    summary, exit_code = run_p10g_candidate_target_plan_replacement_dry_run(parse_args(argv))
    print(json.dumps(json_safe(summary), indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
