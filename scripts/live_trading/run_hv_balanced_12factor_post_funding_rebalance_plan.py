from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.live_trading.execution_planner import build_execution_plan, build_order_sizing_report
from enhengclaw.live_trading.models import RiskGateResult, TargetPortfolio, TargetPosition
from enhengclaw.quant_research.contracts import write_json


DEFAULT_ACCOUNT_PROOF = (
    "artifacts/live_trading/proof_artifacts/deposit_post_funding_rebalance_plan/"
    "20260608T172816Z/fresh_read_only_account_proof.json"
)
DEFAULT_TARGET_PLAN = (
    "artifacts/live_trading/proof_artifacts/hv_balanced_12factor_candidate/counterfactual_path_replay/"
    "20260609T002000Z_from_20260523_t0_hour45_paginated_settlement_frozen_wfo/latest_counterfactual_target_plan.json"
)
DEFAULT_OUTPUT_ROOT = "artifacts/live_trading/proof_artifacts/deposit_post_funding_rebalance_plan"
CONTRACT_VERSION = "hv_balanced_12factor_post_funding_candidate_vs_current_no_order_rebalance_plan.v2"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Proof-only post-funding candidate-vs-current rebalance plan. "
            "Consumes retained account proof and candidate target plan; never calls live services or exchange APIs."
        )
    )
    parser.add_argument("--account-proof", default=DEFAULT_ACCOUNT_PROOF)
    parser.add_argument("--target-plan", default=DEFAULT_TARGET_PLAN)
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-label", default="")
    parser.add_argument("--target-margin-safety-buffer-usdt", type=float, default=300.0)
    parser.add_argument("--target-operating-buffer-usdt", type=float, default=50.0)
    parser.add_argument("--sizing-multiplier", type=float, default=2.0)
    args = parser.parse_args(argv)
    summary = run_post_funding_rebalance_plan(
        account_proof_path=Path(args.account_proof),
        target_plan_path=Path(args.target_plan),
        output_root=Path(args.output_root),
        run_label=str(args.run_label or ""),
        margin_buffer_usdt=float(args.target_margin_safety_buffer_usdt),
        operating_buffer_usdt=float(args.target_operating_buffer_usdt),
        sizing_multiplier=float(args.sizing_multiplier),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "ready" else 2


def run_post_funding_rebalance_plan(
    *,
    account_proof_path: Path,
    target_plan_path: Path,
    output_root: Path,
    run_label: str = "",
    margin_buffer_usdt: float = 300.0,
    operating_buffer_usdt: float = 50.0,
    sizing_multiplier: float = 2.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    label = run_label.strip() or generated_at.strftime("%Y%m%dT%H%M%SZ")
    run_root = output_root / label
    run_root.mkdir(parents=True, exist_ok=True)

    account_proof = _read_json(account_proof_path)
    target_plan = _read_json(target_plan_path)
    total_wallet_balance = _float(dict(account_proof.get("account_totals") or {}).get("totalWalletBalance"))
    available_balance = _float(dict(account_proof.get("account_totals") or {}).get("availableBalance"))
    resolved_allocated_capital = max(
        0.0,
        (total_wallet_balance - float(margin_buffer_usdt) - float(operating_buffer_usdt)) * float(sizing_multiplier),
    )

    portfolio_id = _portfolio_id(target_plan)
    portfolio = _target_portfolio_from_plan(
        target_plan,
        portfolio_id=portfolio_id,
        allocated_capital_usdt=resolved_allocated_capital,
    )
    current_positions = _current_positions(account_proof)
    mark_prices = _mark_prices(account_proof)
    symbol_filters = _symbol_filters(account_proof)
    risk_gate = RiskGateResult(
        risk_gate_id=f"{portfolio_id}:risk:plan_only",
        portfolio_id=portfolio_id,
        mode="plan_only",
        passed=True,
        decision="allow_plan",
        blockers=[],
        warnings=[],
    )
    sizing_report = build_order_sizing_report(
        portfolio,
        mode="plan_only",
        current_positions=current_positions,
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
    )
    sizing_report = _annotate_sizing_report(sizing_report, active_phase_hint="")
    plan = build_execution_plan(
        portfolio,
        risk_gate,
        mode="plan_only",
        current_positions=current_positions,
        mark_prices=mark_prices,
        symbol_filters=symbol_filters,
    )
    sizing_report = _annotate_sizing_report(sizing_report, active_phase_hint=plan.active_execution_phase)

    rows = sizing_report.to_dict(orient="records")
    raw_blocked_rows = [row for row in rows if _split_blockers(row.get("blockers")) and not _truthy(row.get("no_order_required"))]
    dust_rows = [row for row in raw_blocked_rows if str(row.get("execution_phase") or "") == "dust_noop"]
    material_blocked_rows = [row for row in raw_blocked_rows if str(row.get("execution_phase") or "") != "dust_noop"]
    material_blockers = sorted(
        {
            blocker
            for row in material_blocked_rows
            for blocker in _split_blockers(row.get("blockers"))
        }
    )
    blockers = sorted(set(plan.blockers).union(material_blockers))
    status = "ready" if not blockers and risk_gate.passed and plan.status == "ok" else "blocked"

    sizing_report_path = run_root / "candidate_vs_current_rebalance_sizing_report.csv"
    intents_path = run_root / "plan_only_intents_this_cycle.json"
    execution_plan_path = run_root / "execution_plan.json"
    summary_path = run_root / "rebalance_plan_summary.json"
    sizing_report.to_csv(sizing_report_path, index=False)
    write_json(intents_path, [intent.to_dict() for intent in plan.intents])
    write_json(execution_plan_path, plan.metadata())
    _write_standard_delta_plan_artifacts(
        run_root,
        account_proof=account_proof,
        portfolio=portfolio,
        risk_gate=risk_gate,
        plan=plan,
        sizing_report=sizing_report,
        generated_at=generated_at,
    )

    summary = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "status": status,
        "blockers": blockers,
        "proof_only": True,
        "source_account_proof": str(account_proof_path),
        "source_target_plan": str(target_plan_path),
        "target_plan_decision_time_utc": str(target_plan.get("decision_time_utc") or ""),
        "target_plan_sha256": _sha256_file(target_plan_path),
        "account_position_hash": str(account_proof.get("position_hash") or ""),
        "can_trade_v2": bool(account_proof.get("can_trade_v2")),
        "egress_ip": str(dict(account_proof.get("remote_runner_identity_readback") or {}).get("egress_ip") or ""),
        "open_order_count": int(account_proof.get("open_order_count") or 0),
        "open_position_count": int(account_proof.get("open_position_count") or 0),
        "capital_context": {
            "total_wallet_balance_usdt": total_wallet_balance,
            "available_balance_usdt": available_balance,
            "resolved_allocated_capital_usdt": resolved_allocated_capital,
            "sizing_formula": (
                f"(totalWalletBalance - {float(margin_buffer_usdt):g} - "
                f"{float(operating_buffer_usdt):g}) * {float(sizing_multiplier):g}"
            ),
        },
        "current_gross_notional_usdt": _current_gross_notional(account_proof),
        "target_gross_notional_usdt": float(resolved_allocated_capital * sum(abs(p.target_weight) for p in portfolio.positions)),
        "total_abs_delta_notional_usdt": float(sum(abs(float(row.get("delta_signed_notional_usdt") or 0.0)) for row in rows)),
        "risk_gate": risk_gate.to_dict(),
        "execution_plan_status": plan.status,
        "active_execution_phase": plan.active_execution_phase,
        "phase_counts": plan.phase_counts,
        "deferred_phase_counts": plan.deferred_phase_counts,
        "intent_count_this_cycle_if_executed_by_existing_planner": int(len(plan.intents)),
        "reduce_first_order_count": int(sum(1 for intent in plan.intents if intent.execution_phase == "reduce_first")),
        "entry_second_order_count": int(sum(1 for intent in plan.intents if intent.execution_phase == "entry_second")),
        "noop_row_count": int(sum(1 for row in rows if str(row.get("recommended_stage") or "") == "noop")),
        "raw_blocked_order_row_count": int(len(raw_blocked_rows)),
        "blocked_order_row_count": int(len(material_blocked_rows)),
        "material_blocked_order_row_count": int(len(material_blocked_rows)),
        "dust_noop_row_count": int(len(dust_rows)),
        "dust_noop_symbols": sorted({str(row.get("symbol") or "") for row in dust_rows}),
        "dust_noop_blockers": sorted({blocker for row in dust_rows for blocker in _split_blockers(row.get("blockers"))}),
        "intents_this_cycle": [intent.to_dict() for intent in plan.intents],
        "timer_invoked": False,
        "supervisor_invoked": False,
        "executor_invoked": False,
        "target_plan_replaced": False,
        "live_config_changed": False,
        "operator_state_changed": False,
        "orders_submitted": 0,
        "orders_canceled": 0,
        "fills_observed": 0,
        "output_files": {
            "summary": str(summary_path),
            "sizing_report": str(sizing_report_path),
            "intents_this_cycle": str(intents_path),
            "execution_plan": str(execution_plan_path),
        },
    }
    write_json(summary_path, summary)
    return summary


def _write_standard_delta_plan_artifacts(
    run_root: Path,
    *,
    account_proof: dict[str, Any],
    portfolio: TargetPortfolio,
    risk_gate: RiskGateResult,
    plan: Any,
    sizing_report: pd.DataFrame,
    generated_at: datetime,
) -> None:
    run_summary = {
        "run_id": f"{generated_at.strftime('%Y%m%dT%H%M%SZ')}-post-funding-candidate-reduce-first-plan",
        "mode": "live",
        "environment": "mainnet",
        "started_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "finished_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "status": "mainnet_current_position_rebalance_plan_ready",
        "blockers": [],
        "artifact_root": str(run_root),
        "latest_decision_id": portfolio.decision_id,
        "latest_portfolio_id": portfolio.portfolio_id,
        "current_position_aware": True,
        "plan_only": True,
        "mainnet_order_submission_authorized": False,
        "recurring_mainnet_enabled": False,
        "orders_submitted": 0,
        "fill_count": 0,
        "open_order_count": int(account_proof.get("open_order_count") or 0),
        "current_position_count": int(account_proof.get("open_position_count") or 0),
        "target_position_count": int(len(portfolio.positions)),
        "planned_delta_order_count": int(len(plan.intents)),
        "reduce_only_intent_count": int(sum(bool(intent.reduce_only) for intent in plan.intents)),
        "non_reduce_only_intent_count": int(sum(not bool(intent.reduce_only) for intent in plan.intents)),
        "risk_gate_status": "passed" if risk_gate.passed else "blocked",
        "execution_plan_status": plan.status,
        "active_execution_phase": plan.active_execution_phase,
        "phase_counts": dict(plan.phase_counts),
        "deferred_phase_counts": dict(plan.deferred_phase_counts),
        "dust_delta_noop": False,
        "dust_delta_symbols": [],
        "dust_delta_blockers": [],
    }
    runtime_gate_context = {
        "mode": "post_funding_candidate_vs_current_reduce_first_plan_gate",
        "plan_only": True,
        "current_position_aware": True,
        "mainnet_order_submission_authorized": False,
        "recurring_mainnet_authorized": False,
        "candidate_target_plan_replacement": False,
        "timer_invoked": False,
        "supervisor_invoked": False,
        "executor_invoked": False,
    }
    write_json(run_root / "run_summary.json", run_summary)
    write_json(run_root / "runtime_gate_context.json", runtime_gate_context)
    write_json(run_root / "risk_gate.json", risk_gate.to_dict())
    write_json(run_root / "target_portfolio.json", portfolio.metadata())
    portfolio.positions_frame().to_csv(run_root / "target_positions.csv", index=False)
    pd.DataFrame([_current_position_row(row) for row in list(account_proof.get("nonzero_positions") or [])]).to_csv(
        run_root / "current_positions.csv",
        index=False,
    )
    plan.intents_frame().to_csv(run_root / "execution_plan.csv", index=False)
    sizing_report.to_csv(run_root / "order_sizing_report.csv", index=False)


def _current_position_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": str(row.get("symbol") or ""),
        "positionAmt": _float(row.get("positionAmt")),
        "positionSide": str(row.get("positionSide") or "BOTH"),
        "markPrice": _float(row.get("markPrice")),
        "notional": _float(row.get("notional")),
        "marginType": str(row.get("marginType") or ""),
        "leverage": int(_float(row.get("leverage"))),
    }


def _target_portfolio_from_plan(
    target_plan: dict[str, Any],
    *,
    portfolio_id: str,
    allocated_capital_usdt: float,
) -> TargetPortfolio:
    positions: list[TargetPosition] = []
    for row in list(target_plan.get("positions") or []):
        symbol = str(row.get("symbol") or "").strip()
        weight = _float(row.get("target_weight"))
        if not symbol or abs(weight) <= 1e-12:
            continue
        positions.append(
            TargetPosition(
                subject=_subject_from_symbol(symbol),
                usdm_symbol=symbol,
                side="long" if weight > 0.0 else "short",
                score=0.0,
                target_weight=float(weight),
                target_notional_usdt=float(abs(weight) * allocated_capital_usdt),
                previous_target_weight=0.0,
                delta_target_weight=float(weight),
                raw_short_multiplier=1.0,
                portfolio_drawdown_multiplier=1.0,
                selection_reason="counterfactual_12factor_multiphase_sleeve_target",
            )
        )
    return TargetPortfolio(
        portfolio_id=portfolio_id,
        decision_id=str(target_plan.get("decision_time_utc") or target_plan.get("decision_date_utc") or "candidate_target_plan"),
        strategy_label="hv_balanced_12factor_candidate_counterfactual_target_plan",
        allocated_capital_usdt=float(allocated_capital_usdt),
        portfolio_drawdown=0.0,
        portfolio_drawdown_multiplier=1.0,
        target_gross_weight=float(sum(abs(position.target_weight) for position in positions)),
        target_net_weight=float(sum(position.target_weight for position in positions)),
        status="ok",
        blockers=[],
        positions=positions,
    )


def _annotate_sizing_report(report: pd.DataFrame, *, active_phase_hint: str) -> pd.DataFrame:
    frame = report.copy()
    if frame.empty:
        return frame
    current = pd.to_numeric(frame["current_position_amt"], errors="coerce").fillna(0.0)
    target = pd.to_numeric(frame["target_position_amt"], errors="coerce").fillna(0.0)
    mark = pd.to_numeric(frame["mark_price"], errors="coerce").fillna(0.0)
    frame["current_signed_notional_usdt"] = current * mark
    frame["target_signed_notional_usdt"] = target * mark
    frame["delta_signed_notional_usdt"] = frame["target_signed_notional_usdt"] - frame["current_signed_notional_usdt"]
    frame["abs_delta_notional_usdt"] = frame["delta_signed_notional_usdt"].abs()
    active = str(active_phase_hint or "").strip().lower()

    def stage(row: pd.Series) -> str:
        phase = str(row.get("execution_phase") or "")
        if phase in {"dust_noop", "deadband_noop", "noop"}:
            return "noop"
        if bool(row.get("blockers")):
            return "blocked"
        if active == "reduce_first":
            if phase == "reduce_first":
                return "stage_1_reduce_first"
            if phase == "entry_second":
                return "stage_2_entry_second"
        if active == "entry_second" and phase == "entry_second":
            return "stage_1_entry_second"
        return phase or "unknown"

    frame["recommended_stage"] = frame.apply(stage, axis=1)
    return frame


def _portfolio_id(target_plan: dict[str, Any]) -> str:
    decision_date = str(target_plan.get("decision_date_utc") or "").replace("-", "")
    suffix = f"_{decision_date}" if decision_date else ""
    return f"candidate_counterfactual_post_funding{suffix}_vs_fresh_current"


def _current_positions(account_proof: dict[str, Any]) -> dict[str, float]:
    return {str(row["symbol"]): _float(row.get("positionAmt")) for row in list(account_proof.get("nonzero_positions") or [])}


def _mark_prices(account_proof: dict[str, Any]) -> dict[str, float]:
    prices = {str(symbol): _float(price) for symbol, price in dict(account_proof.get("mark_prices") or {}).items()}
    for row in list(account_proof.get("nonzero_positions") or []):
        symbol = str(row.get("symbol") or "")
        mark = _float(row.get("markPrice"))
        if symbol and mark > 0.0:
            prices[symbol] = mark
    return prices


def _symbol_filters(account_proof: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(symbol): dict(value) for symbol, value in dict(account_proof.get("exchange_filters") or {}).items()}


def _current_gross_notional(account_proof: dict[str, Any]) -> float:
    total = 0.0
    for row in list(account_proof.get("nonzero_positions") or []):
        notional = _float(row.get("notional"))
        if notional == 0.0:
            notional = _float(row.get("positionAmt")) * _float(row.get("markPrice"))
        total += abs(notional)
    return float(total)


def _subject_from_symbol(symbol: str) -> str:
    return symbol[:-4] if symbol.endswith("USDT") else symbol


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _split_blockers(value: Any) -> list[str]:
    return [item for item in str(value or "").split(";") if item]


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
