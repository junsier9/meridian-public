from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import analyze_v5_rw_baseline_rebalance_phase_sensitivity as phase_sensitivity  # noqa: E402
from enhengclaw.quant_research.execution_backtest import (  # noqa: E402
    _borrow_cost_return,
    _cross_sectional_target_weights,
    _drawdown_throttle_multiplier,
    _funding_cost_return,
    _next_fill_offset,
    _price_path_return,
    _scale_cross_sectional_turnover,
    _trade_costs,
    filter_cross_sectional_execution_frame,
)
from enhengclaw.quant_research.execution_cost_model import (  # noqa: E402
    execution_venue_for_constraints,
    load_execution_cost_model,
    resolve_execution_cost_model,
)
from enhengclaw.quant_research.fixed_set_comparison import extract_period_frame  # noqa: E402
from enhengclaw.quant_research.overlap_integrity import walk_forward_split_with_purge  # noqa: E402
from enhengclaw.quant_research.split_realization_contract import (  # noqa: E402
    resolve_split_realization_contract,
    realization_step_bars,
)
from enhengclaw.quant_research.validation_contract import (  # noqa: E402
    execution_capacity_limits,
    load_validation_contract,
    validation_contract_reference_capital_usd,
)


DIAGNOSED_PHASES = (8, 9)
BASELINE_PHASE = 0
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "quant_research" / "v5_rw_baseline_phase8_9_attribution_20260521"
DEFAULT_DOC_PATH = (
    ROOT
    / "docs"
    / "quant_research"
    / "03_alpha_branches"
    / "v5_rw_baseline_phase8_9_attribution_2026_05_21.md"
)
DEFAULT_PHASE_SWEEP_ROOT = phase_sensitivity.DEFAULT_OUTPUT_ROOT
RECONCILIATION_TOLERANCE = 1e-10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Attribute the weak phase8/phase9 10d anchor outcomes for the original "
            "12-factor v5_rw_bridge_no_overlay_h10d baseline by period, symbol, side, "
            "price, funding, and trading friction."
        )
    )
    parser.add_argument("--manifest", type=Path, default=phase_sensitivity.DEFAULT_MANIFEST)
    parser.add_argument("--experiment-root", type=Path, default=phase_sensitivity.DEFAULT_EXPERIMENT_ROOT)
    parser.add_argument("--features", type=Path, default=phase_sensitivity.DEFAULT_FEATURES_PATH)
    parser.add_argument("--feature-manifest", type=Path, default=phase_sensitivity.DEFAULT_FEATURE_MANIFEST)
    parser.add_argument("--phase-sweep-root", type=Path, default=DEFAULT_PHASE_SWEEP_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC_PATH)
    parser.add_argument("--top-n", type=int, default=12)
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def ms_to_date(timestamp_ms: int | float | str | None) -> str:
    value = pd.to_numeric(pd.Series([timestamp_ms]), errors="coerce").iloc[0]
    if pd.isna(value):
        return ""
    return pd.to_datetime(int(value), unit="ms", utc=True).date().isoformat()


def json_safe(value: Any) -> Any:
    return phase_sensitivity.json_safe(value)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    phase_sensitivity.write_json(path, payload)


def records(frame: pd.DataFrame, *, limit: int | None = None) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    subset = frame.head(limit) if limit is not None else frame
    return json.loads(subset.replace([np.inf, -np.inf], np.nan).to_json(orient="records"))


def row_float(row: pd.Series | None, column: str) -> float:
    if row is None:
        return 0.0
    value = pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").iloc[0]
    if pd.isna(value):
        return 0.0
    return float(value)


def decision_rank_by_subject(decision_group: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if decision_group.empty:
        return {}
    frame = decision_group.copy()
    frame["score"] = pd.to_numeric(frame.get("score"), errors="coerce").fillna(0.0)
    frame["score_rank_desc"] = frame["score"].rank(method="first", ascending=False).astype(int)
    frame["score_rank_asc"] = frame["score"].rank(method="first", ascending=True).astype(int)
    out: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        subject = str(row.get("subject") or "")
        out[subject] = {
            "score": float(row.get("score", 0.0) or 0.0),
            "score_rank_desc": int(row.get("score_rank_desc", 0) or 0),
            "score_rank_asc": int(row.get("score_rank_asc", 0) or 0),
            "liquidity_bucket": str(row.get("liquidity_bucket") or ""),
            "usdm_symbol": str(row.get("usdm_symbol") or f"{subject}USDT"),
        }
    return out


def apply_short_position_multiplier(
    *,
    raw_target_weights: dict[str, float],
    decision_group: pd.DataFrame,
    constraints: dict[str, Any],
) -> dict[str, float]:
    short_multiplier_column = str(constraints.get("short_position_weight_multiplier_column") or "").strip()
    if not short_multiplier_column or not raw_target_weights or decision_group.empty or short_multiplier_column not in decision_group.columns:
        return raw_target_weights
    multiplier_series = pd.to_numeric(decision_group[short_multiplier_column], errors="coerce").fillna(1.0).clip(lower=0.0, upper=1.0)
    multiplier_by_subject = {
        str(subject): float(multiplier)
        for subject, multiplier in zip(decision_group["subject"], multiplier_series)
    }
    adjusted: dict[str, float] = {}
    for subject, weight in raw_target_weights.items():
        resolved = float(weight)
        if resolved < 0.0:
            resolved *= float(multiplier_by_subject.get(str(subject), 1.0))
        if abs(resolved) > 1e-12:
            adjusted[str(subject)] = resolved
    return adjusted


def build_position_ledger(
    *,
    frame: pd.DataFrame,
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float,
    capacity_limits: dict[str, float],
    phase: int,
    window_index: int,
) -> dict[str, pd.DataFrame]:
    execution_venue = execution_venue_for_constraints(constraints)
    execution_frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
    if execution_frame.empty:
        return {"positions": pd.DataFrame(), "ledger": pd.DataFrame(), "periods": pd.DataFrame()}
    ordered = execution_frame.sort_values(["timestamp_ms", "subject"]).copy()
    evaluation_step_bars = max(realization_step_bars(split_realization_contract), 1)
    timestamps = sorted(int(item) for item in ordered["timestamp_ms"].drop_duplicates().tolist())
    decision_timestamp_indices = list(range(0, len(timestamps), evaluation_step_bars))
    latency_bars = int(execution_cost_model["latency_bars"])
    grouped = {timestamp: group.copy() for timestamp, group in ordered.groupby("timestamp_ms")}
    row_maps = {
        timestamp: {str(row["subject"]): row for _, row in group.iterrows()}
        for timestamp, group in grouped.items()
    }

    dd_throttle_enabled = bool(constraints.get("drawdown_throttle_enabled", False))
    dd_window_days = int(constraints.get("dd_throttle_window_days", 30) or 30)
    equity = 1.0
    equity_history: list[tuple[int, float]] = []
    previous_weights: dict[str, float] = {}
    position_records: list[dict[str, Any]] = []
    ledger_records: list[dict[str, Any]] = []
    period_records: list[dict[str, Any]] = []
    data_gap_blockers: set[str] = set()

    for decision_offset, timestamp_offset in enumerate(decision_timestamp_indices):
        fill_offset = timestamp_offset + latency_bars
        if fill_offset >= len(timestamps):
            break
        decision_timestamp = int(timestamps[timestamp_offset])
        fill_timestamp = int(timestamps[fill_offset])
        next_fill_offset = _next_fill_offset(
            timestamp_count=len(timestamps),
            decision_timestamp_indices=decision_timestamp_indices,
            decision_offset=decision_offset,
            latency_bars=latency_bars,
        )
        exit_timestamp = int(timestamps[next_fill_offset]) if next_fill_offset is not None else int(timestamps[-1])
        decision_group = grouped[decision_timestamp]
        raw_target_weights = _cross_sectional_target_weights(
            decision_group=decision_group,
            constraints=constraints,
            previous_weights=previous_weights,
        )
        raw_target_weights = apply_short_position_multiplier(
            raw_target_weights=raw_target_weights,
            decision_group=decision_group,
            constraints=constraints,
        )

        external_throttle_multiplier: float | None = None
        throttle_drawdown = 0.0
        if dd_throttle_enabled and equity_history:
            cutoff_ms = decision_timestamp - dd_window_days * 86_400_000
            recent_equity = [item for ts, item in equity_history if ts >= cutoff_ms]
            if recent_equity:
                running_max = max(recent_equity)
                if running_max > 0.0:
                    throttle_drawdown = max(float((running_max - equity) / running_max), 0.0)
                    external_throttle_multiplier = _drawdown_throttle_multiplier(
                        current_drawdown=throttle_drawdown,
                        constraints=constraints,
                    )
        if external_throttle_multiplier is not None and external_throttle_multiplier < 1.0 and raw_target_weights:
            raw_target_weights = {
                subject: float(weight) * float(external_throttle_multiplier)
                for subject, weight in raw_target_weights.items()
            }
        actual_weights = _scale_cross_sectional_turnover(
            raw_target_weights=raw_target_weights,
            previous_weights=previous_weights,
            max_turnover_per_rebalance=float(constraints.get("max_turnover_per_rebalance", math.inf) or math.inf),
            turnover_mode=str(constraints.get("pair_turnover_mode") or constraints.get("turnover_mode") or "").strip().lower() or None,
        )
        fill_rows = row_maps.get(fill_timestamp, {})
        exit_rows = row_maps.get(exit_timestamp, {})
        hold_slice = ordered.loc[
            (pd.to_numeric(ordered["timestamp_ms"], errors="coerce") >= fill_timestamp)
            & (pd.to_numeric(ordered["timestamp_ms"], errors="coerce") < exit_timestamp)
        ].copy()
        funding_rows_by_subject = {
            str(subject): group.copy()
            for subject, group in hold_slice.groupby("subject")
        }
        decision_info_by_subject = decision_rank_by_subject(decision_group)
        period_subjects = sorted(set(previous_weights) | set(actual_weights) | set(fill_rows) | set(exit_rows))
        period_totals = {
            "gross_return_before_costs": 0.0,
            "fee_cost_return": 0.0,
            "slippage_cost_return": 0.0,
            "funding_cost_return": 0.0,
            "borrow_cost_return": 0.0,
            "trade_notional_usd": 0.0,
            "turnover": 0.0,
            "max_trade_participation_rate": 0.0,
            "max_inventory_participation_rate": 0.0,
            "max_participation_rate": 0.0,
            "capacity_breach_count": 0,
            "available_quote_volume_usd": 0.0,
        }
        current_weights: dict[str, float] = {}
        for subject in period_subjects:
            weight = float(actual_weights.get(subject, 0.0) or 0.0)
            previous_weight = float(previous_weights.get(subject, 0.0) or 0.0)
            delta_weight = weight - previous_weight
            fill_row = fill_rows.get(subject)
            exit_row = exit_rows.get(subject)
            row_blockers: set[str] = set()
            trade_costs = {
                "fee_cost_return": 0.0,
                "slippage_cost_return": 0.0,
                "trade_notional_usd": 0.0,
                "trade_participation_rate": 0.0,
                "inventory_participation_rate": 0.0,
                "max_participation_rate": 0.0,
                "capacity_breach_count": 0,
                "liquidity_volume_proxy_usd": 0.0,
                "data_gap_blockers": [],
            }
            if fill_row is None and (abs(delta_weight) > 1e-12 or abs(weight) > 1e-12):
                row_blockers.add(f"{subject}: missing fill row for attribution path")
            if fill_row is not None:
                trade_costs = _trade_costs(
                    row=fill_row,
                    delta_weight=delta_weight,
                    target_weight=weight,
                    execution_venue=execution_venue,
                    execution_cost_model=execution_cost_model,
                    reference_capital_usd=reference_capital_usd,
                    capacity_limits=capacity_limits,
                    subject=subject,
                )
                row_blockers.update(str(item) for item in list(trade_costs.get("data_gap_blockers") or []))
            gross_contribution = 0.0
            if abs(weight) > 1e-12:
                if exit_row is None:
                    row_blockers.add(f"{subject}: missing exit row for attribution path")
                elif fill_row is not None:
                    gross_contribution = _price_path_return(
                        entry_row=fill_row,
                        exit_row=exit_row,
                        weight=weight,
                        execution_venue=execution_venue,
                        subject=subject,
                        data_gap_blockers=row_blockers,
                    )
            funding_cost_return = _funding_cost_return(
                hold_slice=funding_rows_by_subject.get(subject, pd.DataFrame()),
                weight=weight,
                execution_venue=execution_venue,
            )
            borrow_cost_return = _borrow_cost_return(
                entry_timestamp_ms=fill_timestamp,
                exit_timestamp_ms=exit_timestamp,
                weight=weight,
                execution_venue=execution_venue,
                execution_cost_model=execution_cost_model,
            )
            fee_cost_return = float(trade_costs.get("fee_cost_return", 0.0) or 0.0)
            slippage_cost_return = float(trade_costs.get("slippage_cost_return", 0.0) or 0.0)
            net_contribution = gross_contribution - fee_cost_return - slippage_cost_return - funding_cost_return - borrow_cost_return
            period_totals["gross_return_before_costs"] += gross_contribution
            period_totals["fee_cost_return"] += fee_cost_return
            period_totals["slippage_cost_return"] += slippage_cost_return
            period_totals["funding_cost_return"] += funding_cost_return
            period_totals["borrow_cost_return"] += borrow_cost_return
            period_totals["trade_notional_usd"] += float(trade_costs.get("trade_notional_usd", 0.0) or 0.0)
            period_totals["turnover"] += abs(delta_weight)
            period_totals["max_trade_participation_rate"] = max(
                period_totals["max_trade_participation_rate"],
                float(trade_costs.get("trade_participation_rate", 0.0) or 0.0),
            )
            period_totals["max_inventory_participation_rate"] = max(
                period_totals["max_inventory_participation_rate"],
                float(trade_costs.get("inventory_participation_rate", 0.0) or 0.0),
            )
            period_totals["max_participation_rate"] = max(
                period_totals["max_participation_rate"],
                float(trade_costs.get("max_participation_rate", 0.0) or 0.0),
            )
            period_totals["capacity_breach_count"] += int(trade_costs.get("capacity_breach_count", 0) or 0)
            period_totals["available_quote_volume_usd"] += float(trade_costs.get("liquidity_volume_proxy_usd", 0.0) or 0.0)
            data_gap_blockers.update(row_blockers)

            if abs(delta_weight) > 1e-12 or abs(weight) > 1e-12 or abs(previous_weight) > 1e-12:
                decision_info = decision_info_by_subject.get(subject, {})
                price_field = "spot_close" if execution_venue == "spot" else "perp_close"
                entry_price = row_float(fill_row, price_field)
                exit_price = row_float(exit_row, price_field)
                underlying_forward_return = (
                    (exit_price / entry_price - 1.0)
                    if entry_price > 0.0 and exit_price > 0.0
                    else 0.0
                )
                ledger_records.append(
                    {
                        "phase_offset_days": int(phase),
                        "window_index": int(window_index),
                        "decision_timestamp_ms": decision_timestamp,
                        "fill_timestamp_ms": fill_timestamp,
                        "exit_timestamp_ms": exit_timestamp,
                        "decision_date_utc": ms_to_date(decision_timestamp),
                        "fill_date_utc": ms_to_date(fill_timestamp),
                        "exit_date_utc": ms_to_date(exit_timestamp),
                        "year": int(pd.to_datetime(fill_timestamp, unit="ms", utc=True).year),
                        "subject": subject,
                        "usdm_symbol": str((fill_row.get("usdm_symbol") if fill_row is not None else decision_info.get("usdm_symbol")) or f"{subject}USDT"),
                        "side": "long" if weight > 0.0 else ("short" if weight < 0.0 else "flat"),
                        "previous_side": "long" if previous_weight > 0.0 else ("short" if previous_weight < 0.0 else "flat"),
                        "previous_weight": previous_weight,
                        "target_weight": weight,
                        "delta_weight": delta_weight,
                        "target_notional_usd": float(reference_capital_usd * abs(weight)),
                        "delta_notional_usd": float(reference_capital_usd * abs(delta_weight)),
                        "score_at_decision": float(decision_info.get("score", 0.0) or 0.0),
                        "score_rank_desc": int(decision_info.get("score_rank_desc", 0) or 0),
                        "score_rank_asc": int(decision_info.get("score_rank_asc", 0) or 0),
                        "liquidity_bucket": str(decision_info.get("liquidity_bucket") or (fill_row.get("liquidity_bucket") if fill_row is not None else "") or ""),
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "underlying_forward_return": float(underlying_forward_return),
                        "gross_contribution": float(gross_contribution),
                        "fee_cost_return": fee_cost_return,
                        "slippage_cost_return": slippage_cost_return,
                        "funding_cost_return": float(funding_cost_return),
                        "borrow_cost_return": float(borrow_cost_return),
                        "net_contribution": float(net_contribution),
                        "net_before_trade_cost_contribution": float(gross_contribution - funding_cost_return - borrow_cost_return),
                        "trade_notional_usd": float(trade_costs.get("trade_notional_usd", 0.0) or 0.0),
                        "trade_participation_rate": float(trade_costs.get("trade_participation_rate", 0.0) or 0.0),
                        "inventory_participation_rate": float(trade_costs.get("inventory_participation_rate", 0.0) or 0.0),
                        "max_participation_rate": float(trade_costs.get("max_participation_rate", 0.0) or 0.0),
                        "capacity_breach_count": int(trade_costs.get("capacity_breach_count", 0) or 0),
                        "liquidity_volume_proxy_usd": float(trade_costs.get("liquidity_volume_proxy_usd", 0.0) or 0.0),
                        "portfolio_throttle_multiplier": float(external_throttle_multiplier if external_throttle_multiplier is not None else 1.0),
                        "portfolio_throttle_drawdown": float(throttle_drawdown),
                        "data_gap_blockers": ";".join(sorted(row_blockers)),
                    }
                )
                if abs(weight) > 1e-12 and fill_row is not None and exit_row is not None:
                    position_records.append(
                        {
                            "phase_offset_days": int(phase),
                            "window_index": int(window_index),
                            "decision_timestamp_ms": decision_timestamp,
                            "fill_timestamp_ms": fill_timestamp,
                            "exit_timestamp_ms": exit_timestamp,
                            "decision_date_utc": ms_to_date(decision_timestamp),
                            "fill_date_utc": ms_to_date(fill_timestamp),
                            "exit_date_utc": ms_to_date(exit_timestamp),
                            "year": int(pd.to_datetime(fill_timestamp, unit="ms", utc=True).year),
                            "subject": subject,
                            "usdm_symbol": str(fill_row.get("usdm_symbol") or f"{subject}USDT"),
                            "side": "long" if weight > 0.0 else "short",
                            "weight": weight,
                            "score_at_decision": float(decision_info.get("score", 0.0) or 0.0),
                            "score_rank_desc": int(decision_info.get("score_rank_desc", 0) or 0),
                            "score_rank_asc": int(decision_info.get("score_rank_asc", 0) or 0),
                            "liquidity_bucket": str(decision_info.get("liquidity_bucket") or fill_row.get("liquidity_bucket") or ""),
                            "entry_price": entry_price,
                            "exit_price": exit_price,
                            "underlying_forward_return": float(underlying_forward_return),
                            "gross_contribution": float(gross_contribution),
                            "funding_cost_return": float(funding_cost_return),
                            "borrow_cost_return": float(borrow_cost_return),
                            "net_before_trade_cost_contribution": float(gross_contribution - funding_cost_return - borrow_cost_return),
                            "portfolio_throttle_multiplier": float(external_throttle_multiplier if external_throttle_multiplier is not None else 1.0),
                            "portfolio_throttle_drawdown": float(throttle_drawdown),
                        }
                    )
            if abs(weight) > 1e-12:
                current_weights[subject] = weight

        net_period_return = (
            period_totals["gross_return_before_costs"]
            - period_totals["fee_cost_return"]
            - period_totals["slippage_cost_return"]
            - period_totals["funding_cost_return"]
            - period_totals["borrow_cost_return"]
        )
        period_records.append(
            {
                "phase_offset_days": int(phase),
                "window_index": int(window_index),
                "timestamp_ms": fill_timestamp,
                "timestamp_utc": pd.to_datetime(fill_timestamp, unit="ms", utc=True).isoformat().replace("+00:00", "Z"),
                "exit_timestamp_ms": exit_timestamp,
                "exit_timestamp_utc": pd.to_datetime(exit_timestamp, unit="ms", utc=True).isoformat().replace("+00:00", "Z"),
                "gross_return_before_costs": float(period_totals["gross_return_before_costs"]),
                "net_period_return": float(net_period_return),
                "fee_cost_return": float(period_totals["fee_cost_return"]),
                "slippage_cost_return": float(period_totals["slippage_cost_return"]),
                "funding_cost_return": float(period_totals["funding_cost_return"]),
                "borrow_cost_return": float(period_totals["borrow_cost_return"]),
                "trade_notional_usd": float(period_totals["trade_notional_usd"]),
                "turnover": float(period_totals["turnover"]),
                "trade_participation_rate": float(period_totals["max_trade_participation_rate"]),
                "inventory_participation_rate": float(period_totals["max_inventory_participation_rate"]),
                "max_participation_rate": float(period_totals["max_participation_rate"]),
                "capacity_breach_count": int(period_totals["capacity_breach_count"]),
                "available_quote_volume_usd": float(period_totals["available_quote_volume_usd"]),
                "portfolio_throttle_multiplier": float(external_throttle_multiplier if external_throttle_multiplier is not None else 1.0),
                "portfolio_throttle_drawdown": float(throttle_drawdown),
                "data_gap_blockers": ";".join(sorted(data_gap_blockers)),
            }
        )
        if dd_throttle_enabled:
            equity *= 1.0 + net_period_return
            equity_history.append((decision_timestamp, equity))
        previous_weights = current_weights

    return {
        "positions": pd.DataFrame(position_records),
        "ledger": pd.DataFrame(ledger_records),
        "periods": pd.DataFrame(period_records),
    }


def run_phase_attribution(
    *,
    phase: int,
    frame: pd.DataFrame,
    daily_ic_by_factor: dict[str, pd.Series],
    spec: dict[str, Any],
    contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float,
    capacity_limits: dict[str, float],
) -> dict[str, pd.DataFrame]:
    phase_data, _ = phase_sensitivity.phase_frame(frame, phase_offset_days=phase)
    if phase_data.empty:
        return {"positions": pd.DataFrame(), "ledger": pd.DataFrame(), "periods": pd.DataFrame()}
    constraints = dict(spec.get("profile_constraints") or {})
    constraints["strategy_profile"] = str(spec.get("strategy_profile") or "")
    time_index = pd.to_datetime(phase_data["timestamp_ms"], unit="ms", utc=True)
    current_anchor = time_index.min() + timedelta(days=120)
    final_anchor = time_index.max() - timedelta(days=30)
    all_positions: list[pd.DataFrame] = []
    all_ledgers: list[pd.DataFrame] = []
    all_periods: list[pd.DataFrame] = []
    window_index = 0
    while current_anchor <= final_anchor:
        train_end = current_anchor - timedelta(days=30)
        validation_end = current_anchor
        test_end = current_anchor + timedelta(days=30)
        train_df, validation_df, test_df = walk_forward_split_with_purge(
            frame=phase_data,
            time_col="timestamp_ms",
            train_end=train_end,
            validation_end=validation_end,
            test_end=test_end,
            split_realization_contract=contract,
        )
        if not train_df.empty and not validation_df.empty and not test_df.empty:
            train_end_ms = int(pd.to_numeric(train_df["timestamp_ms"], errors="coerce").max())
            weights = phase_sensitivity.weights_for_train_end(
                daily_ic_by_factor=daily_ic_by_factor,
                train_end_ms=train_end_ms,
            )
            scored_test = phase_sensitivity.score_frame(test_df, factor_weights=weights)
            result = build_position_ledger(
                frame=scored_test,
                constraints=constraints,
                split_realization_contract=contract,
                execution_cost_model=execution_cost_model,
                reference_capital_usd=reference_capital_usd,
                capacity_limits=capacity_limits,
                phase=phase,
                window_index=window_index,
            )
            for key, sink in (("positions", all_positions), ("ledger", all_ledgers), ("periods", all_periods)):
                if not result[key].empty:
                    sink.append(result[key])
            window_index += 1
        current_anchor += timedelta(days=30)
    return {
        "positions": pd.concat(all_positions, ignore_index=True) if all_positions else pd.DataFrame(),
        "ledger": pd.concat(all_ledgers, ignore_index=True) if all_ledgers else pd.DataFrame(),
        "periods": pd.concat(all_periods, ignore_index=True) if all_periods else pd.DataFrame(),
    }


def reconcile_periods(*, official: pd.DataFrame, rebuilt: pd.DataFrame, phase: int) -> dict[str, Any]:
    if official.empty or rebuilt.empty:
        return {
            "phase_offset_days": int(phase),
            "status": "blocked",
            "reason": "missing_periods",
            "official_period_count": int(len(official)),
            "rebuilt_period_count": int(len(rebuilt)),
        }
    left = official.loc[pd.to_numeric(official["phase_offset_days"], errors="coerce").eq(phase)].copy()
    right = rebuilt.loc[pd.to_numeric(rebuilt["phase_offset_days"], errors="coerce").eq(phase)].copy()
    left["timestamp_ms"] = pd.to_numeric(left["timestamp_ms"], errors="coerce").astype("Int64")
    right["timestamp_ms"] = pd.to_numeric(right["timestamp_ms"], errors="coerce").astype("Int64")
    merged = left.merge(right, on=["phase_offset_days", "window_index", "timestamp_ms"], how="outer", suffixes=("_official", "_rebuilt"), indicator=True)
    row: dict[str, Any] = {
        "phase_offset_days": int(phase),
        "status": "passed",
        "official_period_count": int(len(left)),
        "rebuilt_period_count": int(len(right)),
        "merged_period_count": int(len(merged)),
        "timestamp_join_mismatch_count": int((merged["_merge"] != "both").sum()),
        "tolerance": RECONCILIATION_TOLERANCE,
    }
    for metric in (
        "net_period_return",
        "gross_return_before_costs",
        "fee_cost_return",
        "slippage_cost_return",
        "funding_cost_return",
        "borrow_cost_return",
        "turnover",
    ):
        official_series = pd.to_numeric(merged.get(f"{metric}_official"), errors="coerce").fillna(0.0)
        rebuilt_series = pd.to_numeric(merged.get(f"{metric}_rebuilt"), errors="coerce").fillna(0.0)
        delta = rebuilt_series - official_series
        row[f"{metric}_sum_delta_rebuilt_minus_official"] = float(delta.sum())
        row[f"{metric}_max_abs_delta_rebuilt_minus_official"] = float(delta.abs().max()) if not delta.empty else 0.0
    if (
        row["official_period_count"] != row["rebuilt_period_count"]
        or row["timestamp_join_mismatch_count"] > 0
        or row["net_period_return_max_abs_delta_rebuilt_minus_official"] > RECONCILIATION_TOLERANCE
        or row["gross_return_before_costs_max_abs_delta_rebuilt_minus_official"] > RECONCILIATION_TOLERANCE
        or row["funding_cost_return_max_abs_delta_rebuilt_minus_official"] > RECONCILIATION_TOLERANCE
    ):
        row["status"] = "blocked"
    return row


def aggregate_positions(positions: pd.DataFrame, *, group_columns: list[str], prefix: str) -> pd.DataFrame:
    columns = [
        *group_columns,
        f"{prefix}_position_count",
        f"{prefix}_rebalance_count",
        f"{prefix}_gross_contribution",
        f"{prefix}_funding_cost_return",
        f"{prefix}_borrow_cost_return",
        f"{prefix}_net_before_trade_cost_contribution",
        f"{prefix}_mean_underlying_forward_return",
        f"{prefix}_mean_abs_weight",
        f"{prefix}_profitable_position_rate",
    ]
    if positions.empty:
        return pd.DataFrame(columns=columns)
    working = positions.copy()
    for column in group_columns:
        if column not in working.columns:
            working[column] = ""
    for column in (
        "gross_contribution",
        "funding_cost_return",
        "borrow_cost_return",
        "net_before_trade_cost_contribution",
        "underlying_forward_return",
        "weight",
    ):
        working[column] = pd.to_numeric(working.get(column), errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    grouped = (
        working.groupby(group_columns, dropna=False, sort=True)
        .agg(
            position_count=("subject", "count"),
            rebalance_count=("fill_timestamp_ms", "nunique"),
            gross_contribution=("gross_contribution", "sum"),
            funding_cost_return=("funding_cost_return", "sum"),
            borrow_cost_return=("borrow_cost_return", "sum"),
            net_before_trade_cost_contribution=("net_before_trade_cost_contribution", "sum"),
            mean_underlying_forward_return=("underlying_forward_return", "mean"),
            mean_abs_weight=("weight", lambda item: float(pd.to_numeric(item, errors="coerce").abs().mean())),
            profitable_position_rate=("net_before_trade_cost_contribution", lambda item: float(pd.to_numeric(item, errors="coerce").gt(0.0).mean())),
        )
        .reset_index()
    )
    rename = {
        column: f"{prefix}_{column}"
        for column in grouped.columns
        if column not in group_columns
    }
    return grouped.rename(columns=rename)


def compare_position_aggregates(
    *,
    baseline: pd.DataFrame,
    phase_positions: pd.DataFrame,
    phase: int,
    group_columns: list[str],
) -> pd.DataFrame:
    base = aggregate_positions(baseline, group_columns=group_columns, prefix="phase0")
    alt = aggregate_positions(phase_positions, group_columns=group_columns, prefix=f"phase{phase}")
    merged = base.merge(alt, on=group_columns, how="outer")
    for column in merged.columns:
        if column not in group_columns:
            merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)
    for metric in (
        "position_count",
        "rebalance_count",
        "gross_contribution",
        "funding_cost_return",
        "borrow_cost_return",
        "net_before_trade_cost_contribution",
        "mean_underlying_forward_return",
        "mean_abs_weight",
        "profitable_position_rate",
    ):
        left = f"phase{phase}_{metric}"
        right = f"phase0_{metric}"
        if left in merged.columns and right in merged.columns:
            merged[f"{metric}_delta_phase{phase}_minus_phase0"] = merged[left] - merged[right]
    sort_col = f"net_before_trade_cost_contribution_delta_phase{phase}_minus_phase0"
    if sort_col in merged.columns:
        merged = merged.sort_values(sort_col).reset_index(drop=True)
    return merged


def side_component_summary(positions: pd.DataFrame, ledger: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    phases = sorted(set(pd.to_numeric(positions.get("phase_offset_days"), errors="coerce").dropna().astype(int).tolist()))
    for phase in phases:
        p = positions.loc[pd.to_numeric(positions.get("phase_offset_days"), errors="coerce").eq(phase)].copy()
        l = ledger.loc[pd.to_numeric(ledger.get("phase_offset_days"), errors="coerce").eq(phase)].copy()
        for side in ("long", "short"):
            ps = p.loc[p.get("side", pd.Series(dtype=str)).astype(str).eq(side)].copy()
            ls = l.loc[l.get("side", pd.Series(dtype=str)).astype(str).eq(side)].copy()
            for column in ("gross_contribution", "funding_cost_return", "borrow_cost_return", "net_before_trade_cost_contribution"):
                ps[column] = pd.to_numeric(ps.get(column), errors="coerce").fillna(0.0) if not ps.empty else pd.Series(dtype="float64")
            for column in ("fee_cost_return", "slippage_cost_return", "net_contribution"):
                ls[column] = pd.to_numeric(ls.get(column), errors="coerce").fillna(0.0) if not ls.empty else pd.Series(dtype="float64")
            gross = float(ps["gross_contribution"].sum()) if not ps.empty else 0.0
            funding_cost = float(ps["funding_cost_return"].sum()) if not ps.empty else 0.0
            borrow_cost = float(ps["borrow_cost_return"].sum()) if not ps.empty else 0.0
            fee_cost = float(ls["fee_cost_return"].sum()) if not ls.empty else 0.0
            slippage_cost = float(ls["slippage_cost_return"].sum()) if not ls.empty else 0.0
            rows.append(
                {
                    "phase_offset_days": int(phase),
                    "side": side,
                    "position_count": int(len(ps)),
                    "rebalance_count": int(ps["fill_timestamp_ms"].nunique()) if not ps.empty else 0,
                    "gross_contribution": gross,
                    "funding_cost_return": funding_cost,
                    "borrow_cost_return": borrow_cost,
                    "fee_cost_return_on_target_side": fee_cost,
                    "slippage_cost_return_on_target_side": slippage_cost,
                    "net_before_trade_cost_contribution": gross - funding_cost - borrow_cost,
                    "net_after_target_side_trade_costs": gross - funding_cost - borrow_cost - fee_cost - slippage_cost,
                    "mean_underlying_forward_return": float(pd.to_numeric(ps.get("underlying_forward_return"), errors="coerce").mean()) if not ps.empty else 0.0,
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    baseline = out.loc[out["phase_offset_days"].eq(BASELINE_PHASE), ["side", "net_before_trade_cost_contribution", "gross_contribution", "funding_cost_return"]].copy()
    baseline = baseline.rename(
        columns={
            "net_before_trade_cost_contribution": "phase0_net_before_trade_cost_contribution",
            "gross_contribution": "phase0_gross_contribution",
            "funding_cost_return": "phase0_funding_cost_return",
        }
    )
    out = out.merge(baseline, on="side", how="left")
    out["net_before_trade_delta_vs_phase0"] = out["net_before_trade_cost_contribution"] - out["phase0_net_before_trade_cost_contribution"].fillna(0.0)
    out["gross_delta_vs_phase0"] = out["gross_contribution"] - out["phase0_gross_contribution"].fillna(0.0)
    out["funding_cost_delta_vs_phase0"] = out["funding_cost_return"] - out["phase0_funding_cost_return"].fillna(0.0)
    return out.sort_values(["phase_offset_days", "side"]).reset_index(drop=True)


def period_summary(
    *,
    periods: pd.DataFrame,
    positions: pd.DataFrame,
    top_n: int,
) -> pd.DataFrame:
    if periods.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, period in periods.sort_values(["phase_offset_days", "timestamp_ms"]).iterrows():
        phase = int(period["phase_offset_days"])
        timestamp_ms = int(period["timestamp_ms"])
        pos = positions.loc[
            pd.to_numeric(positions.get("phase_offset_days"), errors="coerce").eq(phase)
            & pd.to_numeric(positions.get("fill_timestamp_ms"), errors="coerce").eq(timestamp_ms)
        ].copy()
        if not pos.empty:
            pos["net_before_trade_cost_contribution"] = pd.to_numeric(pos["net_before_trade_cost_contribution"], errors="coerce").fillna(0.0)
            pos["funding_cost_return"] = pd.to_numeric(pos["funding_cost_return"], errors="coerce").fillna(0.0)
            top_negative = records(
                pos.sort_values("net_before_trade_cost_contribution").loc[
                    :,
                    [
                        "subject",
                        "side",
                        "weight",
                        "underlying_forward_return",
                        "gross_contribution",
                        "funding_cost_return",
                        "net_before_trade_cost_contribution",
                    ],
                ],
                limit=min(top_n, 8),
            )
        else:
            top_negative = []
        rows.append(
            {
                "phase_offset_days": phase,
                "window_index": int(period.get("window_index", -1)),
                "timestamp_ms": timestamp_ms,
                "fill_date_utc": ms_to_date(timestamp_ms),
                "exit_date_utc": ms_to_date(period.get("exit_timestamp_ms")),
                "net_period_return": float(period.get("net_period_return", 0.0) or 0.0),
                "gross_return_before_costs": float(period.get("gross_return_before_costs", 0.0) or 0.0),
                "fee_cost_return": float(period.get("fee_cost_return", 0.0) or 0.0),
                "slippage_cost_return": float(period.get("slippage_cost_return", 0.0) or 0.0),
                "funding_cost_return": float(period.get("funding_cost_return", 0.0) or 0.0),
                "turnover": float(period.get("turnover", 0.0) or 0.0),
                "held_position_count": int(len(pos)),
                "long_count": int(pos["side"].astype(str).eq("long").sum()) if not pos.empty else 0,
                "short_count": int(pos["side"].astype(str).eq("short").sum()) if not pos.empty else 0,
                "top_negative_legs_json": json.dumps(json_safe(top_negative), ensure_ascii=False),
            }
        )
    return pd.DataFrame(rows).sort_values(["phase_offset_days", "net_period_return"]).reset_index(drop=True)


def concentration_summary(periods: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for phase, group in periods.groupby("phase_offset_days", sort=True):
        returns = pd.to_numeric(group["net_period_return"], errors="coerce").fillna(0.0)
        negative = returns[returns < 0.0]
        worst = returns.sort_values().head(5)
        total_negative_loss = float(abs(negative.sum()))
        worst5_loss = float(abs(worst[worst < 0.0].sum()))
        rows.append(
            {
                "phase_offset_days": int(phase),
                "period_count": int(len(group)),
                "negative_period_count": int(len(negative)),
                "negative_period_fraction": float(len(negative) / len(group)) if len(group) else 0.0,
                "sum_simple_period_returns": float(returns.sum()),
                "median_period_return": float(returns.median()) if not returns.empty else 0.0,
                "worst_period_return": float(returns.min()) if not returns.empty else 0.0,
                "worst5_period_return_sum": float(worst.sum()) if not worst.empty else 0.0,
                "total_negative_loss_abs": total_negative_loss,
                "worst5_loss_share_of_total_negative_loss": (
                    worst5_loss / total_negative_loss if total_negative_loss > 1e-12 else 0.0
                ),
            }
        )
    return pd.DataFrame(rows)


def phase_metrics_lookup(phase_metrics: pd.DataFrame) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for _, row in phase_metrics.iterrows():
        out[int(row["phase_offset_days"])] = row.to_dict()
    return out


def table(frame: pd.DataFrame, columns: list[str], *, max_rows: int = 12) -> str:
    if frame.empty:
        return "_No rows._"
    existing = [column for column in columns if column in frame.columns]
    if not existing:
        return "_No requested columns._"
    subset = frame.loc[:, existing].head(max_rows).copy()
    header = "| " + " | ".join(existing) + " |"
    separator = "| " + " | ".join("---" for _ in existing) + " |"
    rows = [header, separator]
    for _, row in subset.iterrows():
        values = []
        for column in existing:
            value = row.get(column)
            if isinstance(value, float):
                text = f"{value:.6f}"
            elif pd.isna(value):
                text = ""
            else:
                text = str(value)
            values.append(text.replace("\n", " ").replace("|", "\\|"))
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join(rows)


def render_report(
    *,
    summary: dict[str, Any],
    concentration: pd.DataFrame,
    worst_periods: pd.DataFrame,
    side_components: pd.DataFrame,
    symbol_side_delta: dict[int, pd.DataFrame],
    artifact_paths: dict[str, str],
) -> str:
    lines = [
        "# v5_rw_bridge_no_overlay_h10d phase8/phase9 attribution",
        "",
        f"- generated_at_utc: `{summary['generated_at_utc']}`",
        f"- status: `{summary['status']}`",
        f"- baseline_phase: `{BASELINE_PHASE}`",
        f"- diagnosed_phases: `{list(DIAGNOSED_PHASES)}`",
        f"- reconciliation_status: `{summary['reconciliation_status']}`",
        "",
        "## Diagnosis",
        "",
        summary["diagnosis"],
        "",
        "## Period Concentration",
        "",
        table(
            concentration,
            [
                "phase_offset_days",
                "period_count",
                "negative_period_count",
                "negative_period_fraction",
                "sum_simple_period_returns",
                "median_period_return",
                "worst_period_return",
                "worst5_period_return_sum",
                "worst5_loss_share_of_total_negative_loss",
            ],
            max_rows=10,
        ),
        "",
        "## Worst Weak-Phase Periods",
        "",
        table(
            worst_periods,
            [
                "phase_offset_days",
                "fill_date_utc",
                "exit_date_utc",
                "net_period_return",
                "gross_return_before_costs",
                "funding_cost_return",
                "long_count",
                "short_count",
                "top_negative_legs_json",
            ],
            max_rows=16,
        ),
        "",
        "## Side Components",
        "",
        table(
            side_components,
            [
                "phase_offset_days",
                "side",
                "position_count",
                "gross_contribution",
                "funding_cost_return",
                "net_before_trade_cost_contribution",
                "net_before_trade_delta_vs_phase0",
                "gross_delta_vs_phase0",
                "funding_cost_delta_vs_phase0",
            ],
            max_rows=12,
        ),
    ]
    for phase in DIAGNOSED_PHASES:
        lines.extend(
            [
                "",
                f"## Phase {phase} Worst Symbol/Side Delta vs Phase 0",
                "",
                table(
                    symbol_side_delta[phase],
                    [
                        "subject",
                        "side",
                        "phase0_position_count",
                        f"phase{phase}_position_count",
                        "phase0_net_before_trade_cost_contribution",
                        f"phase{phase}_net_before_trade_cost_contribution",
                        f"net_before_trade_cost_contribution_delta_phase{phase}_minus_phase0",
                        f"gross_contribution_delta_phase{phase}_minus_phase0",
                        f"funding_cost_return_delta_phase{phase}_minus_phase0",
                    ],
                    max_rows=14,
                ),
            ]
        )
    lines.extend(["", "## Artifacts", ""])
    for key, value in artifact_paths.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Method Notes",
            "",
            "- This is an offline research replay; it does not read live accounts and does not submit orders.",
            "- Phase0/8/9 are rebuilt from the same original 12-factor manifest, feature matrix, WFO schedule, cost model, and execution constraints used by the phase sensitivity sweep.",
            "- Positive `funding_cost_return` is a drag because period net return subtracts it; negative funding cost is a funding receipt.",
            "- Symbol/side attribution is additive over period simple returns. Headline phase net return in the phase sweep remains compounded.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_diagnosis(
    *,
    concentration: pd.DataFrame,
    side_components: pd.DataFrame,
    symbol_side_delta: dict[int, pd.DataFrame],
) -> str:
    bullets: list[str] = []
    for phase in DIAGNOSED_PHASES:
        row = concentration.loc[concentration["phase_offset_days"].eq(phase)]
        if row.empty:
            continue
        item = row.iloc[0]
        bullets.append(
            "- Phase `{phase}`: negative periods `{neg}/{count}`; worst 5 periods sum `{worst5:.6f}` and explain `{share:.1%}` of total negative-period loss.".format(
                phase=phase,
                neg=int(item["negative_period_count"]),
                count=int(item["period_count"]),
                worst5=float(item["worst5_period_return_sum"]),
                share=float(item["worst5_loss_share_of_total_negative_loss"]),
            )
        )
        side_rows = side_components.loc[side_components["phase_offset_days"].eq(phase)].copy()
        if not side_rows.empty:
            side_rows["net_before_trade_delta_vs_phase0"] = pd.to_numeric(side_rows["net_before_trade_delta_vs_phase0"], errors="coerce").fillna(0.0)
            worst_side = side_rows.sort_values("net_before_trade_delta_vs_phase0").iloc[0]
            bullets.append(
                "- Phase `{phase}` worst side delta is `{side}`: net-before-trade delta `{delta:.6f}`, gross delta `{gross:.6f}`, funding-cost delta `{funding:.6f}`.".format(
                    phase=phase,
                    side=worst_side["side"],
                    delta=float(worst_side["net_before_trade_delta_vs_phase0"]),
                    gross=float(worst_side["gross_delta_vs_phase0"]),
                    funding=float(worst_side["funding_cost_delta_vs_phase0"]),
                )
            )
        top = symbol_side_delta[phase].head(5)
        if not top.empty:
            names = [
                f"{row.subject}/{row.side}({getattr(row, f'net_before_trade_cost_contribution_delta_phase{phase}_minus_phase0'):.4f})"
                for row in top.itertuples(index=False)
            ]
            bullets.append(f"- Phase `{phase}` top negative symbol/side deltas: " + ", ".join(names) + ".")
    return "\n".join(bullets) if bullets else "- No attribution rows were available."


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest.expanduser().resolve()
    experiment_root = args.experiment_root.expanduser().resolve()
    features_path = args.features.expanduser().resolve()
    feature_manifest_path = args.feature_manifest.expanduser().resolve()
    phase_sweep_root = args.phase_sweep_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    doc_path = args.doc_path.expanduser().resolve()
    top_n = max(int(args.top_n), 1)

    strategy = phase_sensitivity.load_strategy(manifest_path)
    spec = phase_sensitivity.read_experiment_spec(experiment_root)
    feature_manifest = json.loads(feature_manifest_path.read_text(encoding="utf-8"))
    contract = resolve_split_realization_contract(
        contract=dict(spec.get("split_realization_contract") or feature_manifest.get("split_realization_contract") or {}),
        shape=str(spec.get("shape") or "cross_sectional"),
        bar_interval_ms=int(spec.get("bar_interval_ms") or 86_400_000),
    )
    frame, derivatives_strategy_quality = phase_sensitivity.read_filtered_frame(
        features_path=features_path,
        strategy=strategy,
        spec=spec,
        contract=contract,
    )
    feature_columns = list(spec.get("feature_columns") or strategy.get("required_feature_columns") or [])
    daily_ic_by_factor = phase_sensitivity.build_daily_ic_by_factor(frame, feature_columns=feature_columns)
    validation_contract = load_validation_contract()
    execution_cost_model = resolve_execution_cost_model(contract=load_execution_cost_model(), scenario="base")
    reference_capital_usd = validation_contract_reference_capital_usd(
        strategy_profile=str(spec.get("strategy_profile") or ""),
        contract=validation_contract,
    )
    capacity_limits = execution_capacity_limits(validation_contract)

    phase_period_returns = pd.read_csv(phase_sweep_root / "phase_period_returns.csv")
    phase_metrics = pd.read_csv(phase_sweep_root / "phase_metrics.csv")
    phases_to_rebuild = (BASELINE_PHASE, *DIAGNOSED_PHASES)
    rebuilt_results: dict[int, dict[str, pd.DataFrame]] = {}
    for phase in phases_to_rebuild:
        rebuilt_results[phase] = run_phase_attribution(
            phase=phase,
            frame=frame,
            daily_ic_by_factor=daily_ic_by_factor,
            spec=spec,
            contract=contract,
            execution_cost_model=execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
        )

    positions_all = pd.concat([rebuilt_results[phase]["positions"] for phase in phases_to_rebuild], ignore_index=True)
    ledger_all = pd.concat([rebuilt_results[phase]["ledger"] for phase in phases_to_rebuild], ignore_index=True)
    periods_all = pd.concat([rebuilt_results[phase]["periods"] for phase in phases_to_rebuild], ignore_index=True)
    reconciliations = pd.DataFrame(
        [
            reconcile_periods(official=phase_period_returns, rebuilt=periods_all, phase=phase)
            for phase in phases_to_rebuild
        ]
    )
    reconciliation_status = "passed" if bool(reconciliations["status"].eq("passed").all()) else "blocked"

    concentration = concentration_summary(periods_all)
    period_details = period_summary(periods=periods_all, positions=positions_all, top_n=top_n)
    worst_periods = period_details.loc[period_details["phase_offset_days"].isin(DIAGNOSED_PHASES)].sort_values("net_period_return").reset_index(drop=True)
    side_components = side_component_summary(positions_all, ledger_all)
    symbol_side_delta = {
        phase: compare_position_aggregates(
            baseline=rebuilt_results[BASELINE_PHASE]["positions"],
            phase_positions=rebuilt_results[phase]["positions"],
            phase=phase,
            group_columns=["subject", "side"],
        )
        for phase in DIAGNOSED_PHASES
    }
    symbol_year_side_delta = {
        phase: compare_position_aggregates(
            baseline=rebuilt_results[BASELINE_PHASE]["positions"],
            phase_positions=rebuilt_results[phase]["positions"],
            phase=phase,
            group_columns=["subject", "year", "side"],
        )
        for phase in DIAGNOSED_PHASES
    }
    year_side_delta = {
        phase: compare_position_aggregates(
            baseline=rebuilt_results[BASELINE_PHASE]["positions"],
            phase_positions=rebuilt_results[phase]["positions"],
            phase=phase,
            group_columns=["year", "side"],
        )
        for phase in DIAGNOSED_PHASES
    }

    output_root.mkdir(parents=True, exist_ok=True)
    artifact_paths = {
        "summary_json": str(output_root / "summary.json"),
        "position_attribution_csv": str(output_root / "position_attribution_phase0_8_9.csv"),
        "paper_shadow_ledger_csv": str(output_root / "paper_shadow_ledger_phase0_8_9.csv"),
        "rebuilt_period_returns_csv": str(output_root / "rebuilt_period_returns_phase0_8_9.csv"),
        "period_reconciliation_csv": str(output_root / "period_reconciliation.csv"),
        "period_concentration_csv": str(output_root / "period_concentration.csv"),
        "period_details_csv": str(output_root / "period_details_phase0_8_9.csv"),
        "worst_periods_csv": str(output_root / "worst_periods_phase8_9.csv"),
        "side_component_summary_csv": str(output_root / "side_component_summary.csv"),
        "symbol_side_delta_phase8_csv": str(output_root / "symbol_side_delta_phase8_minus_phase0.csv"),
        "symbol_side_delta_phase9_csv": str(output_root / "symbol_side_delta_phase9_minus_phase0.csv"),
        "symbol_year_side_delta_phase8_csv": str(output_root / "symbol_year_side_delta_phase8_minus_phase0.csv"),
        "symbol_year_side_delta_phase9_csv": str(output_root / "symbol_year_side_delta_phase9_minus_phase0.csv"),
        "year_side_delta_phase8_csv": str(output_root / "year_side_delta_phase8_minus_phase0.csv"),
        "year_side_delta_phase9_csv": str(output_root / "year_side_delta_phase9_minus_phase0.csv"),
        "markdown_report": str(doc_path),
    }
    positions_all.to_csv(output_root / "position_attribution_phase0_8_9.csv", index=False)
    ledger_all.to_csv(output_root / "paper_shadow_ledger_phase0_8_9.csv", index=False)
    periods_all.to_csv(output_root / "rebuilt_period_returns_phase0_8_9.csv", index=False)
    reconciliations.to_csv(output_root / "period_reconciliation.csv", index=False)
    concentration.to_csv(output_root / "period_concentration.csv", index=False)
    period_details.to_csv(output_root / "period_details_phase0_8_9.csv", index=False)
    worst_periods.to_csv(output_root / "worst_periods_phase8_9.csv", index=False)
    side_components.to_csv(output_root / "side_component_summary.csv", index=False)
    for phase in DIAGNOSED_PHASES:
        symbol_side_delta[phase].to_csv(output_root / f"symbol_side_delta_phase{phase}_minus_phase0.csv", index=False)
        symbol_year_side_delta[phase].to_csv(output_root / f"symbol_year_side_delta_phase{phase}_minus_phase0.csv", index=False)
        year_side_delta[phase].to_csv(output_root / f"year_side_delta_phase{phase}_minus_phase0.csv", index=False)

    diagnosis = build_diagnosis(
        concentration=concentration,
        side_components=side_components,
        symbol_side_delta=symbol_side_delta,
    )
    metrics_by_phase = phase_metrics_lookup(phase_metrics)
    blockers = []
    if reconciliation_status != "passed":
        blockers.append({"code": "period_reconciliation_blocked", "rows": records(reconciliations)})
    data_gap_rows = ledger_all.loc[ledger_all.get("data_gap_blockers", pd.Series(dtype=str)).fillna("").astype(str).str.len().gt(0)] if not ledger_all.empty else pd.DataFrame()
    if not data_gap_rows.empty:
        blockers.append({"code": "ledger_data_gap_blockers", "row_count": int(len(data_gap_rows)), "sample": records(data_gap_rows.head(10))})
    summary = {
        "schema": "v5_rw_baseline_phase8_9_attribution.v1",
        "generated_at_utc": utc_now_iso(),
        "status": "passed" if not blockers else "blocked",
        "baseline_label": phase_sensitivity.BASELINE_LABEL,
        "strategy_id": phase_sensitivity.BASELINE_STRATEGY_ID,
        "baseline_phase": BASELINE_PHASE,
        "diagnosed_phases": list(DIAGNOSED_PHASES),
        "phase_metrics": {str(phase): json_safe(metrics_by_phase.get(phase, {})) for phase in phases_to_rebuild},
        "filtered_frame": {
            "row_count": int(len(frame)),
            "subject_count": int(frame["subject"].nunique()),
            "timestamp_count": int(frame["timestamp_ms"].nunique()),
            "derivatives_strategy_quality": derivatives_strategy_quality,
        },
        "reconciliation_status": reconciliation_status,
        "period_reconciliation": records(reconciliations),
        "period_concentration": records(concentration),
        "side_component_summary": records(side_components),
        "top_worst_periods": records(worst_periods, limit=top_n),
        "top_bad_symbol_side_delta": {
            str(phase): records(symbol_side_delta[phase], limit=top_n)
            for phase in DIAGNOSED_PHASES
        },
        "top_bad_year_side_delta": {
            str(phase): records(year_side_delta[phase], limit=top_n)
            for phase in DIAGNOSED_PHASES
        },
        "diagnosis": diagnosis,
        "blockers": blockers,
        "artifact_paths": artifact_paths,
    }
    write_json(output_root / "summary.json", json_safe(summary))
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(
        render_report(
            summary=summary,
            concentration=concentration,
            worst_periods=worst_periods,
            side_components=side_components,
            symbol_side_delta=symbol_side_delta,
            artifact_paths=artifact_paths,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            json_safe(
                {
                    "status": summary["status"],
                    "reconciliation_status": reconciliation_status,
                    "diagnosis": diagnosis,
                    "period_concentration": summary["period_concentration"],
                    "top_worst_periods": summary["top_worst_periods"][:8],
                    "top_bad_symbol_side_delta": summary["top_bad_symbol_side_delta"],
                    "artifact_paths": artifact_paths,
                    "blocker_count": len(blockers),
                }
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
