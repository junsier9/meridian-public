from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from .execution_cost_model import execution_venue_for_constraints
from .split_realization_contract import realization_step_bars as split_contract_realization_step_bars


DAY_MS = 86_400_000.0
SPOT_TRADE_LIQUIDITY_FIELDS = (
    "spot_quote_volume",
    "intraday_quote_volume_4h",
    "intraday_quote_volume_1d",
    "daily_quote_volume",
)


def filter_cross_sectional_execution_frame(
    *,
    frame: pd.DataFrame,
    constraints: dict[str, Any],
) -> pd.DataFrame:
    if frame.empty or execution_venue_for_constraints(constraints) != "perp":
        return frame.copy()
    if "subject" not in frame.columns or "timestamp_ms" not in frame.columns:
        return frame.copy()
    filtered = frame.copy()
    has_perp_mask = _perp_subject_available_mask(filtered)
    row_eligible_mask = _perp_execution_row_eligible_mask(filtered)
    executable_start_ms = _perp_executable_start_ms_series(
        filtered,
        has_perp_mask=has_perp_mask,
        row_eligible_mask=row_eligible_mask,
    )
    timestamp_ms = pd.to_numeric(filtered["timestamp_ms"], errors="coerce")
    eligible_mask = (
        has_perp_mask
        & row_eligible_mask
        & timestamp_ms.notna()
        & executable_start_ms.notna()
        & timestamp_ms.ge(executable_start_ms)
    )
    if not bool(eligible_mask.any()):
        return filtered.iloc[0:0].copy()
    order_columns = [column for column in ("timestamp_ms", "subject") if column in filtered.columns]
    return filtered.loc[eligible_mask].sort_values(order_columns).copy()


def backtest_single_asset(
    *,
    frame: pd.DataFrame,
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None = None,
    capacity_limits: dict[str, float] | None = None,
    include_periods: bool = False,
) -> dict[str, Any]:
    ordered = frame.sort_values("timestamp_ms").copy()
    execution_venue = execution_venue_for_constraints(constraints)
    if ordered.empty:
        return _empty_metrics(
            execution_cost_model=execution_cost_model,
            execution_venue=execution_venue,
        )
    evaluation_step_bars = max(split_contract_realization_step_bars(split_realization_contract), 1)
    decision_indices = list(range(0, len(ordered), evaluation_step_bars))
    decision_frame = ordered.iloc[decision_indices].copy().reset_index(drop=True)
    target_positions = _single_asset_positions(decision_frame["score"], constraints=constraints)
    periods: list[dict[str, Any]] = []
    data_gap_blockers: set[str] = set()
    current_position = 0.0
    trade_count = 0
    latency_bars = int(execution_cost_model["latency_bars"])
    for decision_offset, decision_index in enumerate(decision_indices):
        fill_index = decision_index + latency_bars
        if fill_index >= len(ordered):
            break
        current_position, period = _single_asset_period(
            ordered=ordered,
            fill_index=fill_index,
            next_fill_index=_next_fill_index(
                ordered_length=len(ordered),
                decision_indices=decision_indices,
                decision_offset=decision_offset,
                latency_bars=latency_bars,
            ),
            raw_target_position=float(target_positions.iloc[decision_offset]),
            current_position=current_position,
            constraints=constraints,
            execution_venue=execution_venue,
            execution_cost_model=execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
        )
        if abs(float(period["delta_weight"])) > 0.0:
            trade_count += 1
        data_gap_blockers.update(str(item) for item in list(period.get("data_gap_blockers") or []))
        periods.append(period)
    return _aggregate_periods(
        periods=periods,
        periods_per_year=_periods_per_year(
            bar_interval_ms=int(split_realization_contract["bar_interval_ms"]),
            evaluation_step_bars=evaluation_step_bars,
        ),
        trade_count=trade_count,
        rebalance_count=len(periods),
        evaluation_step_bars=evaluation_step_bars,
        execution_cost_model=execution_cost_model,
        execution_venue=execution_venue,
        data_gap_blockers=sorted(data_gap_blockers),
        include_periods=include_periods,
    )


def backtest_cross_sectional(
    *,
    frame: pd.DataFrame,
    constraints: dict[str, Any],
    split_realization_contract: dict[str, Any],
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None = None,
    capacity_limits: dict[str, float] | None = None,
    include_periods: bool = False,
) -> dict[str, Any]:
    execution_venue = execution_venue_for_constraints(constraints)
    execution_frame = filter_cross_sectional_execution_frame(frame=frame, constraints=constraints)
    if execution_frame.empty:
        return _empty_metrics(
            execution_cost_model=execution_cost_model,
            execution_venue=execution_venue,
        )
    ordered = execution_frame.sort_values(["timestamp_ms", "subject"]).copy()
    evaluation_step_bars = max(split_contract_realization_step_bars(split_realization_contract), 1)
    timestamps = sorted(int(item) for item in ordered["timestamp_ms"].drop_duplicates().tolist())
    decision_timestamp_indices = list(range(0, len(timestamps), evaluation_step_bars))
    previous_weights: dict[str, float] = {}
    periods: list[dict[str, Any]] = []
    trade_count = 0
    data_gap_blockers: set[str] = set()
    latency_bars = int(execution_cost_model["latency_bars"])
    grouped = {timestamp: group.copy() for timestamp, group in ordered.groupby("timestamp_ms")}
    # Phase 2d: drawdown-conditional throttle state (cross-period equity curve tracking).
    # When constraints.drawdown_throttle_enabled is True, maintain a running equity series
    # across periods. Before each period's decision, compute rolling-window drawdown vs
    # the recent equity peak; if DD exceeds threshold, scale all target positions by a
    # configured multiplier (e.g. DD>5% -> x0.5, DD>10% -> x0.0). Stateful: cannot be
    # implemented inside _cross_sectional_period or via the multiplier overlay registry,
    # so passed in via external_throttle_multiplier kwarg.
    dd_throttle_enabled = bool(constraints.get("drawdown_throttle_enabled", False))
    dd_window_days = int(constraints.get("dd_throttle_window_days", 30) or 30)
    equity = 1.0
    equity_history: list[tuple[int, float]] = []
    for decision_offset, timestamp_offset in enumerate(decision_timestamp_indices):
        fill_offset = timestamp_offset + latency_bars
        if fill_offset >= len(timestamps):
            break
        fill_group = grouped[timestamps[fill_offset]]
        next_fill_offset = _next_fill_offset(
            timestamp_count=len(timestamps),
            decision_timestamp_indices=decision_timestamp_indices,
            decision_offset=decision_offset,
            latency_bars=latency_bars,
        )
        exit_timestamp = timestamps[next_fill_offset] if next_fill_offset is not None else timestamps[-1]
        hold_slice = ordered.loc[
            (ordered["timestamp_ms"] >= int(fill_group["timestamp_ms"].iloc[0]))
            & (ordered["timestamp_ms"] < int(exit_timestamp))
        ].copy()
        # Phase 2d: derive DD throttle multiplier from running equity history (PIT-safe:
        # only uses periods that already closed by current decision time).
        external_throttle_multiplier: float | None = None
        throttle_drawdown = 0.0
        if dd_throttle_enabled and equity_history:
            decision_ts_ms = int(timestamps[timestamp_offset])
            cutoff_ms = decision_ts_ms - dd_window_days * 86_400_000
            recent_equity = [eq for ts, eq in equity_history if ts >= cutoff_ms]
            if recent_equity:
                running_max = max(recent_equity)
                if running_max > 0.0:
                    throttle_drawdown = max(float((running_max - equity) / running_max), 0.0)
                    external_throttle_multiplier = _drawdown_throttle_multiplier(
                        current_drawdown=throttle_drawdown,
                        constraints=constraints,
                    )
        previous_weights, period = _cross_sectional_period(
            decision_group=grouped[timestamps[timestamp_offset]],
            fill_group=fill_group,
            exit_group=grouped[exit_timestamp],
            hold_slice=hold_slice,
            previous_weights=previous_weights,
            constraints=constraints,
            execution_venue=execution_venue,
            execution_cost_model=execution_cost_model,
            reference_capital_usd=reference_capital_usd,
            capacity_limits=capacity_limits,
            external_throttle_multiplier=external_throttle_multiplier,
        )
        period["portfolio_throttle_multiplier"] = float(
            external_throttle_multiplier if external_throttle_multiplier is not None else 1.0
        )
        period["portfolio_throttle_drawdown"] = float(throttle_drawdown)
        if float(period["turnover"]) > 0.0:
            trade_count += 1
        data_gap_blockers.update(str(item) for item in list(period.get("data_gap_blockers") or []))
        periods.append(period)
        # Phase 2d: update equity from period return for next iteration's DD computation.
        if dd_throttle_enabled:
            period_return = float(period.get("net_period_return", 0.0) or 0.0)
            equity = equity * (1.0 + period_return)
            equity_history.append((int(timestamps[timestamp_offset]), equity))
    return _aggregate_periods(
        periods=periods,
        periods_per_year=_periods_per_year(
            bar_interval_ms=int(split_realization_contract["bar_interval_ms"]),
            evaluation_step_bars=evaluation_step_bars,
        ),
        trade_count=trade_count,
        rebalance_count=len(periods),
        evaluation_step_bars=evaluation_step_bars,
        execution_cost_model=execution_cost_model,
        execution_venue=execution_venue,
        data_gap_blockers=sorted(data_gap_blockers),
        include_periods=include_periods,
    )


def _drawdown_throttle_multiplier(
    *,
    current_drawdown: float,
    constraints: dict[str, Any],
) -> float | None:
    drawdown = max(float(current_drawdown), 0.0)
    mode = str(constraints.get("dd_throttle_mode") or "step").strip().lower()
    if mode in {"soft_linear", "linear", "soft"}:
        start_threshold = float(
            constraints.get(
                "dd_throttle_start_threshold",
                constraints.get("dd_throttle_5pct_threshold", 0.05),
            )
            or 0.05
        )
        full_threshold = float(
            constraints.get(
                "dd_throttle_full_threshold",
                constraints.get("dd_throttle_10pct_threshold", 0.10),
            )
            or 0.10
        )
        min_multiplier = _clip_unit(
            float(
                constraints.get(
                    "dd_throttle_min_multiplier",
                    constraints.get("dd_throttle_10pct_multiplier", 0.0),
                )
                or 0.0
            )
        )
        if drawdown <= start_threshold:
            return None
        if full_threshold <= start_threshold:
            return min_multiplier
        span = min(max((drawdown - start_threshold) / (full_threshold - start_threshold), 0.0), 1.0)
        return _clip_unit(1.0 - (1.0 - min_multiplier) * span)

    dd_5pct_threshold = float(constraints.get("dd_throttle_5pct_threshold", 0.05) or 0.05)
    dd_10pct_threshold = float(constraints.get("dd_throttle_10pct_threshold", 0.10) or 0.10)
    dd_5pct_multiplier = _clip_unit(float(constraints.get("dd_throttle_5pct_multiplier", 0.5) or 0.5))
    dd_10pct_multiplier = _clip_unit(float(constraints.get("dd_throttle_10pct_multiplier", 0.0) or 0.0))
    if drawdown > dd_10pct_threshold:
        return dd_10pct_multiplier
    if drawdown > dd_5pct_threshold:
        return dd_5pct_multiplier
    return None


def _clip_unit(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def _single_asset_period(
    *,
    ordered: pd.DataFrame,
    fill_index: int,
    next_fill_index: int | None,
    raw_target_position: float,
    current_position: float,
    constraints: dict[str, Any],
    execution_venue: str,
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
) -> tuple[float, dict[str, Any]]:
    fill_row = ordered.iloc[fill_index]
    exit_index = next_fill_index if next_fill_index is not None else len(ordered) - 1
    exit_row = ordered.iloc[exit_index]
    raw_delta_weight = raw_target_position - current_position
    delta_weight = _apply_turnover_cap(
        raw_delta_weight=raw_delta_weight,
        max_turnover_per_rebalance=float(constraints.get("max_turnover_per_rebalance", math.inf) or math.inf),
    )
    target_position = current_position + delta_weight
    trade_costs = _trade_costs(
        row=fill_row,
        delta_weight=delta_weight,
        target_weight=target_position,
        execution_venue=execution_venue,
        execution_cost_model=execution_cost_model,
        reference_capital_usd=reference_capital_usd,
        capacity_limits=capacity_limits,
        subject=str(fill_row.get("subject") or ""),
    )
    gross_return = _price_path_return(
        entry_row=fill_row,
        exit_row=exit_row,
        weight=target_position,
        execution_venue=execution_venue,
        subject=str(fill_row.get("subject") or ""),
        data_gap_blockers=trade_costs["data_gap_blockers"],
    )
    hold_slice = ordered.iloc[fill_index:exit_index].copy()
    funding_cost_return = _funding_cost_return(
        hold_slice=hold_slice,
        weight=target_position,
        execution_venue=execution_venue,
    )
    borrow_cost_return = _borrow_cost_return(
        entry_timestamp_ms=int(fill_row["timestamp_ms"]),
        exit_timestamp_ms=int(exit_row["timestamp_ms"]),
        weight=target_position,
        execution_venue=execution_venue,
        execution_cost_model=execution_cost_model,
    )
    net_period_return = (
        gross_return
        - float(trade_costs["fee_cost_return"])
        - float(trade_costs["slippage_cost_return"])
        - float(funding_cost_return)
        - float(borrow_cost_return)
    )
    return target_position, {
        "timestamp_ms": int(fill_row["timestamp_ms"]),
        "gross_return_before_costs": float(gross_return),
        "net_period_return": float(net_period_return),
        "fee_cost_return": float(trade_costs["fee_cost_return"]),
        "slippage_cost_return": float(trade_costs["slippage_cost_return"]),
        "funding_cost_return": float(funding_cost_return),
        "borrow_cost_return": float(borrow_cost_return),
        "trade_notional_usd": float(trade_costs["trade_notional_usd"]),
        "turnover": float(abs(delta_weight)),
        "delta_weight": float(delta_weight),
        "trade_participation_rate": float(trade_costs["trade_participation_rate"]),
        "inventory_participation_rate": float(trade_costs["inventory_participation_rate"]),
        "max_participation_rate": float(trade_costs["max_participation_rate"]),
        "capacity_breach_count": int(trade_costs["capacity_breach_count"]),
        "available_quote_volume_usd": float(trade_costs["liquidity_volume_proxy_usd"]),
        "data_gap_blockers": list(trade_costs["data_gap_blockers"]),
    }


def _cross_sectional_period(
    *,
    decision_group: pd.DataFrame,
    fill_group: pd.DataFrame,
    exit_group: pd.DataFrame,
    hold_slice: pd.DataFrame,
    previous_weights: dict[str, float],
    constraints: dict[str, Any],
    execution_venue: str,
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
    external_throttle_multiplier: float | None = None,
) -> tuple[dict[str, float], dict[str, Any]]:
    raw_target_weights = _cross_sectional_target_weights(
        decision_group=decision_group,
        constraints=constraints,
        previous_weights=previous_weights,
    )
    short_multiplier_column = str(constraints.get("short_position_weight_multiplier_column") or "").strip()
    if short_multiplier_column and raw_target_weights and not decision_group.empty and short_multiplier_column in decision_group.columns:
        multiplier_series = pd.to_numeric(
            decision_group[short_multiplier_column],
            errors="coerce",
        ).fillna(1.0).clip(lower=0.0, upper=1.0)
        multiplier_by_subject = {
            str(subject): float(multiplier)
            for subject, multiplier in zip(decision_group["subject"], multiplier_series)
        }
        adjusted_weights: dict[str, float] = {}
        for subject, weight in raw_target_weights.items():
            resolved = float(weight)
            if resolved < 0.0:
                resolved *= float(multiplier_by_subject.get(str(subject), 1.0))
            if abs(resolved) > 1e-12:
                adjusted_weights[str(subject)] = resolved
        raw_target_weights = adjusted_weights
    # Optional portfolio-level position multiplier overlay (e.g. DVOL regime throttle).
    # Applied to raw_target_weights BEFORE turnover scaling so the cap sees the
    # post-multiplier targets and may further reduce (but never inflate) weights.
    overlay_id = str(constraints.get("position_multiplier_overlay_id") or "").strip() or None
    if overlay_id is not None and raw_target_weights and not decision_group.empty:
        from .multiplier_overlay import position_multiplier_lookup
        lookup = position_multiplier_lookup(
            overlay_id,
            overlay_context=dict(constraints.get("position_multiplier_overlay_context") or {}),
        )
        if lookup is not None:
            decision_ts_ms = int(decision_group["timestamp_ms"].iloc[0])
            multiplier = float(lookup(decision_ts_ms))
            if multiplier < 1.0:
                raw_target_weights = {k: float(v) * multiplier for k, v in raw_target_weights.items()}
    # Phase 2d: external drawdown-conditional throttle (computed by main backtest loop
    # from running equity curve; stateful across periods so passed in here rather than
    # via constraint registry like the multiplier overlay).
    if external_throttle_multiplier is not None and external_throttle_multiplier < 1.0 and raw_target_weights:
        raw_target_weights = {k: float(v) * float(external_throttle_multiplier) for k, v in raw_target_weights.items()}
    actual_weights = _scale_cross_sectional_turnover(
        raw_target_weights=raw_target_weights,
        previous_weights=previous_weights,
        max_turnover_per_rebalance=float(constraints.get("max_turnover_per_rebalance", math.inf) or math.inf),
        turnover_mode=str(constraints.get("pair_turnover_mode") or constraints.get("turnover_mode") or "").strip().lower() or None,
    )
    fill_rows = {str(row["subject"]): row for _, row in fill_group.iterrows()}
    exit_rows = {str(row["subject"]): row for _, row in exit_group.iterrows()}
    funding_rows_by_subject = {
        str(subject): group.copy()
        for subject, group in hold_slice.groupby("subject")
    }
    union_subjects = sorted(set(previous_weights) | set(actual_weights) | set(fill_rows) | set(exit_rows))
    gross_return = 0.0
    fee_cost_return = 0.0
    slippage_cost_return = 0.0
    funding_cost_return = 0.0
    borrow_cost_return = 0.0
    trade_notional_usd_total = 0.0
    turnover = 0.0
    max_trade_participation_rate = 0.0
    max_inventory_participation_rate = 0.0
    max_participation_rate = 0.0
    capacity_breach_count = 0
    available_quote_volume_usd_total = 0.0
    data_gap_blockers: set[str] = set()
    current_weights: dict[str, float] = {}
    for subject in union_subjects:
        weight = float(actual_weights.get(subject, 0.0))
        previous_weight = float(previous_weights.get(subject, 0.0))
        delta_weight = weight - previous_weight
        fill_row = fill_rows.get(subject)
        exit_row = exit_rows.get(subject)
        if fill_row is None and (abs(delta_weight) > 0.0 or abs(weight) > 0.0):
            data_gap_blockers.add(f"{subject}: missing fill row for execution venue")
            continue
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
            fee_cost_return += float(trade_costs["fee_cost_return"])
            slippage_cost_return += float(trade_costs["slippage_cost_return"])
            trade_notional_usd_total += float(trade_costs["trade_notional_usd"])
            max_trade_participation_rate = max(max_trade_participation_rate, float(trade_costs["trade_participation_rate"]))
            max_inventory_participation_rate = max(max_inventory_participation_rate, float(trade_costs["inventory_participation_rate"]))
            max_participation_rate = max(max_participation_rate, float(trade_costs["max_participation_rate"]))
            capacity_breach_count += int(trade_costs["capacity_breach_count"])
            available_quote_volume_usd_total += float(trade_costs["liquidity_volume_proxy_usd"])
            data_gap_blockers.update(str(item) for item in list(trade_costs["data_gap_blockers"] or []))
        if abs(weight) > 0.0:
            if exit_row is None:
                data_gap_blockers.add(f"{subject}: missing exit row for execution venue")
            else:
                gross_return += _price_path_return(
                    entry_row=fill_row if fill_row is not None else exit_row,
                    exit_row=exit_row,
                    weight=weight,
                    execution_venue=execution_venue,
                    subject=subject,
                    data_gap_blockers=data_gap_blockers,
                )
        funding_cost_return += _funding_cost_return(
            hold_slice=funding_rows_by_subject.get(subject, pd.DataFrame()),
            weight=weight,
            execution_venue=execution_venue,
        )
        borrow_cost_return += _borrow_cost_return(
            entry_timestamp_ms=int(fill_group["timestamp_ms"].iloc[0]),
            exit_timestamp_ms=int(exit_group["timestamp_ms"].iloc[0]),
            weight=weight,
            execution_venue=execution_venue,
            execution_cost_model=execution_cost_model,
        )
        turnover += abs(delta_weight)
        if abs(weight) > 0.0:
            current_weights[subject] = weight
    net_period_return = gross_return - fee_cost_return - slippage_cost_return - funding_cost_return - borrow_cost_return
    return current_weights, {
        "timestamp_ms": int(fill_group["timestamp_ms"].iloc[0]),
        "gross_return_before_costs": float(gross_return),
        "net_period_return": float(net_period_return),
        "fee_cost_return": float(fee_cost_return),
        "slippage_cost_return": float(slippage_cost_return),
        "funding_cost_return": float(funding_cost_return),
        "borrow_cost_return": float(borrow_cost_return),
        "trade_notional_usd": float(trade_notional_usd_total),
        "turnover": float(turnover),
        "delta_weight": float(turnover),
        "trade_participation_rate": float(max_trade_participation_rate),
        "inventory_participation_rate": float(max_inventory_participation_rate),
        "max_participation_rate": float(max_participation_rate),
        "capacity_breach_count": int(capacity_breach_count),
        "available_quote_volume_usd": float(available_quote_volume_usd_total),
        "data_gap_blockers": sorted(data_gap_blockers),
    }


def _aggregate_periods(
    *,
    periods: list[dict[str, Any]],
    periods_per_year: int,
    trade_count: int,
    rebalance_count: int,
    evaluation_step_bars: int,
    execution_cost_model: dict[str, Any],
    execution_venue: str,
    data_gap_blockers: list[str],
    include_periods: bool = False,
) -> dict[str, Any]:
    if not periods:
        return _empty_metrics(
            execution_cost_model=execution_cost_model,
            execution_venue=execution_venue,
            evaluation_step_bars=evaluation_step_bars,
            data_gap_blockers=data_gap_blockers,
        )
    net_returns = pd.Series([float(item["net_period_return"]) for item in periods], dtype="float64")
    gross_returns = pd.Series([float(item["gross_return_before_costs"]) for item in periods], dtype="float64")
    turnover = pd.Series([float(item["turnover"]) for item in periods], dtype="float64")
    frictionless_metrics = _performance_summary(
        period_returns=gross_returns,
        periods_per_year=periods_per_year,
    )
    net_metrics = _performance_summary(
        period_returns=net_returns,
        periods_per_year=periods_per_year,
    )
    trade_participation = pd.Series([float(item["trade_participation_rate"]) for item in periods], dtype="float64")
    inventory_participation = pd.Series([float(item["inventory_participation_rate"]) for item in periods], dtype="float64")
    max_participation = pd.Series([float(item["max_participation_rate"]) for item in periods], dtype="float64")
    available_quote_volume = pd.Series([float(item["available_quote_volume_usd"]) for item in periods], dtype="float64")
    payload = {
        "net_return": float(net_metrics["net_return"]),
        "sharpe": float(net_metrics["sharpe"]),
        "max_drawdown": float(net_metrics["max_drawdown"]),
        "gross_return_before_costs": float(frictionless_metrics["net_return"]),
        "fee_cost_return": float(sum(float(item["fee_cost_return"]) for item in periods)),
        "slippage_cost_return": float(sum(float(item["slippage_cost_return"]) for item in periods)),
        "funding_cost_return": float(sum(float(item["funding_cost_return"]) for item in periods)),
        "borrow_cost_return": float(sum(float(item["borrow_cost_return"]) for item in periods)),
        "turnover": float(turnover.sum()),
        "trade_count": int(trade_count),
        "rebalance_count": int(rebalance_count),
        "evaluation_step_bars": int(evaluation_step_bars),
        "latency_bars": int(execution_cost_model["latency_bars"]),
        "execution_venue": execution_venue,
        "trade_notional_usd_total": float(sum(float(item["trade_notional_usd"]) for item in periods)),
        "max_trade_participation_rate": float(trade_participation.max()) if not trade_participation.empty else 0.0,
        "max_inventory_participation_rate": float(inventory_participation.max()) if not inventory_participation.empty else 0.0,
        "max_participation_rate": float(max_participation.max()) if not max_participation.empty else 0.0,
        "capacity_breach_count": int(sum(int(item["capacity_breach_count"]) for item in periods)),
        "available_quote_volume_usd_total": float(available_quote_volume.sum()) if not available_quote_volume.empty else 0.0,
        "frictionless_metrics": frictionless_metrics,
        "execution_cost_model": dict(execution_cost_model),
        "data_gap_blockers": list(data_gap_blockers),
    }
    if include_periods:
        payload["periods"] = [dict(item) for item in periods]
    return payload


def _empty_metrics(
    *,
    execution_cost_model: dict[str, Any],
    execution_venue: str,
    evaluation_step_bars: int = 1,
    data_gap_blockers: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "net_return": 0.0,
        "sharpe": 0.0,
        "max_drawdown": 0.0,
        "gross_return_before_costs": 0.0,
        "fee_cost_return": 0.0,
        "slippage_cost_return": 0.0,
        "funding_cost_return": 0.0,
        "borrow_cost_return": 0.0,
        "turnover": 0.0,
        "trade_count": 0,
        "rebalance_count": 0,
        "evaluation_step_bars": int(evaluation_step_bars),
        "latency_bars": int(execution_cost_model["latency_bars"]),
        "execution_venue": execution_venue,
        "trade_notional_usd_total": 0.0,
        "max_trade_participation_rate": 0.0,
        "max_inventory_participation_rate": 0.0,
        "max_participation_rate": 0.0,
        "capacity_breach_count": 0,
        "available_quote_volume_usd_total": 0.0,
        "frictionless_metrics": {
            "net_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
        },
        "execution_cost_model": dict(execution_cost_model),
        "data_gap_blockers": list(data_gap_blockers or []),
    }


def _performance_summary(*, period_returns: pd.Series, periods_per_year: int) -> dict[str, float]:
    cleaned_returns = period_returns.fillna(0.0).astype("float64")
    equity_curve = (1.0 + cleaned_returns).cumprod()
    running_max = equity_curve.cummax()
    drawdown = ((running_max - equity_curve) / running_max.replace(0.0, np.nan)).fillna(0.0)
    std = float(cleaned_returns.std(ddof=0))
    sharpe = 0.0 if std == 0.0 else float(cleaned_returns.mean() / std * math.sqrt(periods_per_year))
    return {
        "net_return": float(equity_curve.iloc[-1] - 1.0) if not equity_curve.empty else 0.0,
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.max()) if not drawdown.empty else 0.0,
    }


def _periods_per_year(*, bar_interval_ms: int, evaluation_step_bars: int) -> int:
    return max(int((365 * 24 * 60 * 60 * 1000) / (int(bar_interval_ms) * max(int(evaluation_step_bars), 1))), 1)


def _single_asset_positions(scores: pd.Series, *, constraints: dict[str, Any]) -> pd.Series:
    neutral_band_abs_score = float(constraints.get("neutral_band_abs_score", 0.0) or 0.0)
    if neutral_band_abs_score < 0.0:
        neutral_band_abs_score = 0.0
    active_scores = scores.where(scores.abs() >= neutral_band_abs_score, other=0.0)
    if bool(constraints.get("long_only")):
        execution_venue = execution_venue_for_constraints(constraints)
        if execution_venue == "spot":
            long_leverage = float(constraints.get("long_leverage", 1.0) or 1.0)
            full_size_abs_score = float(constraints.get("long_only_full_size_abs_score", 0.5) or 0.5)
            if full_size_abs_score <= neutral_band_abs_score:
                full_size_abs_score = neutral_band_abs_score + 0.1
            positive_scores = active_scores.clip(lower=0.0)
            scaled_exposure = (
                (positive_scores - neutral_band_abs_score)
                / max(full_size_abs_score - neutral_band_abs_score, 1e-9)
            ).clip(lower=0.0, upper=1.0)
            return pd.Series(
                scaled_exposure * long_leverage,
                index=scores.index,
                dtype="float64",
            )
        return pd.Series(
            np.where(active_scores > 0, float(constraints.get("long_leverage", 1.0) or 1.0), 0.0),
            index=scores.index,
            dtype="float64",
        )
    positions = np.where(active_scores > 0, float(constraints.get("long_leverage", 1.0) or 1.0), 0.0)
    positions = np.where(active_scores < 0, -float(constraints.get("short_leverage", 0.0) or 0.0), positions)
    return pd.Series(positions, index=scores.index, dtype="float64")


def _cross_sectional_target_weights(
    *,
    decision_group: pd.DataFrame,
    constraints: dict[str, Any],
    previous_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    decision_group = _filter_by_decision_eligible_column(
        decision_group,
        column=str(constraints.get("decision_eligible_column") or "").strip(),
    )
    if decision_group.empty:
        return {}
    pair_construction = str(constraints.get("pair_construction") or "").strip().lower()
    if pair_construction == "quality_bucket_pairs":
        return _cross_sectional_pair_target_weights(
            decision_group=decision_group,
            constraints=constraints,
            previous_weights=previous_weights,
        )
    if pair_construction == "inverse_vol_weighted_long_only":
        return _cross_sectional_inverse_vol_long_only_weights(
            decision_group=decision_group,
            constraints=constraints,
        )
    long_group = _filter_by_decision_eligible_column(
        decision_group,
        column=str(constraints.get("long_decision_eligible_column") or "").strip(),
    )
    short_group = _filter_by_decision_eligible_column(
        decision_group,
        column=str(constraints.get("short_decision_eligible_column") or "").strip(),
    )
    long_ordered = long_group.sort_values("score", ascending=False).copy()
    short_ordered = short_group.sort_values("score", ascending=False).copy()
    weights: dict[str, float] = {}
    # W2-A (2026-04-29): top_long_count and bottom_short_count are now
    # configurable via profile_constraints. Defaults preserve the historical
    # top-3 long / bottom-2 short behaviour. Wider K is the doc §H.2 W2-A
    # path for breaking BTC/ETH/PAXG capacity binding without switching off
    # spot or pair_construction. See threshold_provenance.md "Alpha Ontology
    # cycle blockers" entry.
    top_long_count = max(int(constraints.get("top_long_count", 3) or 3), 0)
    bottom_short_count = max(int(constraints.get("bottom_short_count", 2) or 2), 0)
    top_n = min(top_long_count, len(long_ordered))
    bottom_n = min(bottom_short_count, len(short_ordered))
    if top_n > 0:
        long_weight = float(constraints.get("long_leverage", 1.0) or 1.0) / float(top_n)
        for subject in long_ordered.head(top_n)["subject"]:
            weights[str(subject)] = long_weight
    if bool(constraints.get("short_allowed")) and bottom_n > 0:
        short_weight = float(constraints.get("short_leverage", 0.0) or 0.0) / float(bottom_n)
        for subject in short_ordered.tail(bottom_n)["subject"]:
            weights[str(subject)] = weights.get(str(subject), 0.0) - short_weight
    return weights


def _filter_by_decision_eligible_column(decision_group: pd.DataFrame, *, column: str) -> pd.DataFrame:
    if not column or column not in decision_group.columns:
        return decision_group.copy()
    eligible_raw = decision_group[column]
    if pd.api.types.is_bool_dtype(eligible_raw):
        eligible_mask = eligible_raw.fillna(False).astype("bool")
    else:
        eligible_text = eligible_raw.astype(str).str.strip().str.lower()
        eligible_mask = eligible_text.isin({"1", "true", "yes", "y"})
    return decision_group.loc[eligible_mask].copy()


def _cross_sectional_inverse_vol_long_only_weights(
    *,
    decision_group: pd.DataFrame,
    constraints: dict[str, Any],
) -> dict[str, float]:
    if decision_group.empty:
        return {}
    top_long_count = max(int(constraints.get("top_long_count", 5) or 5), 1)
    long_leverage = float(constraints.get("long_leverage", 1.0) or 1.0)
    vol_column = str(constraints.get("inverse_vol_column", "realized_volatility_20") or "realized_volatility_20")
    vol_floor = float(constraints.get("inverse_vol_floor", 1e-4) or 1e-4)
    ordered = decision_group.sort_values("score", ascending=False).copy()
    top = ordered.head(min(top_long_count, len(ordered))).copy()
    if top.empty:
        return {}
    if vol_column in top.columns:
        vol_values = pd.to_numeric(top[vol_column], errors="coerce").fillna(0.0).clip(lower=vol_floor)
    else:
        vol_values = pd.Series(vol_floor, index=top.index)
    inv_vol = 1.0 / vol_values
    if not float(inv_vol.sum()) > 0:
        equal_weight = long_leverage / float(len(top))
        return {str(s): equal_weight for s in top["subject"]}
    normalized = inv_vol / inv_vol.sum() * long_leverage
    return {str(subject): float(weight) for subject, weight in zip(top["subject"], normalized)}


def _cross_sectional_pair_target_weights(
    *,
    decision_group: pd.DataFrame,
    constraints: dict[str, Any],
    previous_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    if decision_group.empty:
        return {}
    ordered = decision_group.copy()
    score = pd.to_numeric(ordered["score"], errors="coerce").fillna(0.0).astype("float64")
    momentum_20 = pd.to_numeric(
        ordered.get("momentum_20", pd.Series(0.0, index=ordered.index)),
        errors="coerce",
    ).fillna(0.0).astype("float64")
    relative_strength = pd.to_numeric(ordered.get("relative_strength_20"), errors="coerce").fillna(0.0).astype("float64")
    ema_slope = pd.to_numeric(ordered.get("ema_slope_5_20"), errors="coerce").fillna(0.0).astype("float64")
    distance_to_low = pd.to_numeric(ordered.get("distance_to_low_20"), errors="coerce").fillna(0.0).astype("float64")
    intraday_vol = pd.to_numeric(ordered.get("intraday_realized_vol_4h_to_1d"), errors="coerce").fillna(0.0).astype("float64")
    realized_vol = pd.to_numeric(ordered.get("realized_volatility_20"), errors="coerce").fillna(0.0).astype("float64")
    stress_penalty = (intraday_vol * 0.55 + realized_vol * 0.45).astype("float64")

    rs_rank = relative_strength.rank(pct=True, method="average")
    ema_rank = ema_slope.rank(pct=True, method="average")
    support_rank = distance_to_low.rank(pct=True, method="average")
    low_stress_rank = (-stress_penalty).rank(pct=True, method="average")
    trend_crowding = (
        rs_rank * 0.50
        + ema_rank * 0.30
        + support_rank * 0.20
    ).astype("float64")
    quality_anchor = (
        rs_rank * 0.44
        + ema_rank * 0.24
        + support_rank * 0.20
        + low_stress_rank * 0.12
    ).astype("float64")

    bucket_count = max(int(constraints.get("pair_bucket_count", 4) or 4), 2)
    pair_count = max(int(constraints.get("pair_count", 2) or 2), 1)
    score_spread_min = float(constraints.get("pair_score_spread_min", 0.08) or 0.08)
    quality_floor = float(constraints.get("pair_quality_floor", 0.35) or 0.35)
    trend_crowding_max = constraints.get("pair_trend_crowding_max")
    pair_strength_soft_cap = constraints.get("pair_strength_soft_cap")
    pair_additional_strength_ratio_min = constraints.get("pair_additional_strength_ratio_min")
    trend_crowding_soft_threshold = constraints.get("pair_trend_crowding_soft_threshold")
    trend_crowding_soft_scale = constraints.get("pair_trend_crowding_soft_scale")
    short_trend_crowding_soft_threshold = constraints.get("pair_short_trend_crowding_soft_threshold")
    short_trend_crowding_soft_scale = constraints.get("pair_short_trend_crowding_soft_scale")
    short_quality_max = constraints.get("pair_short_quality_max")
    short_quality_soft_threshold = constraints.get("pair_short_quality_soft_threshold")
    short_quality_soft_scale = constraints.get("pair_short_quality_soft_scale")
    pair_quality_balance_soft_floor = constraints.get("pair_quality_balance_soft_floor")
    pair_quality_balance_soft_scale = constraints.get("pair_quality_balance_soft_scale")
    pair_market_momentum_soft_threshold = constraints.get("pair_market_momentum_soft_threshold")
    pair_market_ema_soft_threshold = constraints.get("pair_market_ema_soft_threshold")
    pair_market_trend_short_scale = constraints.get("pair_market_trend_short_scale")
    pair_switch_strength_ratio_min = constraints.get("pair_switch_strength_ratio_min")
    ordered = ordered.assign(_quality_anchor=quality_anchor)
    ordered["_trend_crowding"] = trend_crowding
    market_momentum = float(momentum_20.median())
    market_ema_slope = float(ema_slope.median())
    trend_crowding_by_subject = {
        str(row["subject"]): float(row["_trend_crowding"])
        for _, row in ordered.iterrows()
    }
    quality_anchor_by_subject = {
        str(row["subject"]): float(row["_quality_anchor"])
        for _, row in ordered.iterrows()
    }
    ordered["_quality_bucket"] = (
        (ordered["_quality_anchor"] * float(bucket_count))
        .clip(lower=0.0, upper=float(bucket_count) - 1e-6)
        .astype("int64")
    )

    pair_candidates: list[tuple[float, float, str, str]] = []
    for _, cohort in ordered.groupby("_quality_bucket", sort=True):
        eligible = cohort.loc[cohort["_quality_anchor"] >= quality_floor].copy()
        if trend_crowding_max is not None:
            eligible = eligible.loc[
                pd.to_numeric(eligible["_trend_crowding"], errors="coerce").fillna(1.0)
                <= float(trend_crowding_max)
            ].copy()
        if len(eligible) < 2:
            continue
        eligible.sort_values("score", ascending=False, inplace=True)
        long_row = eligible.iloc[0]
        long_subject = str(long_row["subject"])
        short_candidates = eligible.sort_values("score", ascending=True).copy()
        short_candidates = short_candidates.loc[short_candidates["subject"] != long_subject].copy()
        if short_quality_max is not None:
            short_candidates = short_candidates.loc[
                pd.to_numeric(short_candidates["_quality_anchor"], errors="coerce").fillna(1.0)
                <= float(short_quality_max)
            ].copy()
        if short_candidates.empty:
            continue
        short_row = short_candidates.iloc[0]
        short_subject = str(short_row["subject"])
        if not long_subject or not short_subject or long_subject == short_subject:
            continue
        spread = float(long_row["score"]) - float(short_row["score"])
        if spread <= score_spread_min:
            continue
        quality_balance = 1.0 - abs(float(long_row["_quality_anchor"]) - float(short_row["_quality_anchor"]))
        pair_strength = spread * max(quality_balance, 0.1)
        pair_candidates.append((pair_strength, quality_balance, long_subject, short_subject))

    if not pair_candidates:
        return {}

    pair_candidates.sort(key=lambda item: item[0], reverse=True)
    selected_pairs: list[tuple[float, float, str, str]] = []
    used_subjects: set[str] = set()
    lead_pair_strength: float | None = None
    for pair in pair_candidates:
        pair_strength, _, long_subject, short_subject = pair
        if long_subject in used_subjects or short_subject in used_subjects:
            continue
        if (
            lead_pair_strength is not None
            and pair_additional_strength_ratio_min is not None
            and float(pair_strength) < float(lead_pair_strength) * float(pair_additional_strength_ratio_min)
        ):
            continue
        selected_pairs.append(pair)
        if lead_pair_strength is None:
            lead_pair_strength = float(pair_strength)
        used_subjects.add(long_subject)
        used_subjects.add(short_subject)
        if len(selected_pairs) >= pair_count:
            break

    if not selected_pairs:
        return {}

    if pair_switch_strength_ratio_min is not None and int(pair_count) == 1:
        previous_pair = _dominant_pair_from_weights(previous_weights or {})
        current_pair = _dominant_pair_from_selected_pairs(selected_pairs)
        if previous_pair is not None and current_pair is not None and previous_pair != current_pair:
            previous_pair_candidate = _pair_candidate_from_subjects(
                ordered=ordered,
                constraints=constraints,
                long_subject=previous_pair[0],
                short_subject=previous_pair[1],
            )
            if previous_pair_candidate is not None:
                current_pair_strength = float(selected_pairs[0][0])
                if current_pair_strength < float(previous_pair_candidate[0]) * float(pair_switch_strength_ratio_min):
                    selected_pairs = [previous_pair_candidate]

    long_total = float(constraints.get("long_leverage", 0.5) or 0.5)
    short_total = float(constraints.get("short_leverage", 0.5) or 0.5)
    per_pair_long = long_total / float(len(selected_pairs))
    per_pair_short = short_total / float(len(selected_pairs))
    weights: dict[str, float] = {}
    for pair_strength, quality_balance, long_subject, short_subject in selected_pairs:
        pair_scale = 1.0
        if pair_strength_soft_cap is not None:
            soft_cap = max(float(pair_strength_soft_cap), 1e-9)
            pair_scale = min(1.0, soft_cap / max(float(pair_strength), 1e-9))
        if (
            pair_quality_balance_soft_floor is not None
            and pair_quality_balance_soft_scale is not None
            and float(quality_balance) < float(pair_quality_balance_soft_floor)
        ):
            pair_scale *= float(pair_quality_balance_soft_scale)
        if (
            trend_crowding_soft_threshold is not None
            and trend_crowding_soft_scale is not None
        ):
            long_crowding = trend_crowding_by_subject.get(long_subject, 0.0)
            short_crowding = trend_crowding_by_subject.get(short_subject, 0.0)
            if max(long_crowding, short_crowding) >= float(trend_crowding_soft_threshold):
                pair_scale *= float(trend_crowding_soft_scale)
        if (
            short_trend_crowding_soft_threshold is not None
            and short_trend_crowding_soft_scale is not None
        ):
            short_crowding = trend_crowding_by_subject.get(short_subject, 0.0)
            if short_crowding >= float(short_trend_crowding_soft_threshold):
                pair_scale *= float(short_trend_crowding_soft_scale)
        if (
            short_quality_soft_threshold is not None
            and short_quality_soft_scale is not None
        ):
            short_quality = quality_anchor_by_subject.get(short_subject, 0.0)
            if short_quality >= float(short_quality_soft_threshold):
                pair_scale *= float(short_quality_soft_scale)
        short_scale = pair_scale
        if (
            pair_market_momentum_soft_threshold is not None
            and pair_market_ema_soft_threshold is not None
            and pair_market_trend_short_scale is not None
            and market_momentum >= float(pair_market_momentum_soft_threshold)
            and market_ema_slope >= float(pair_market_ema_soft_threshold)
        ):
            short_scale *= float(pair_market_trend_short_scale)
        weights[long_subject] = weights.get(long_subject, 0.0) + per_pair_long * pair_scale
        weights[short_subject] = weights.get(short_subject, 0.0) - per_pair_short * short_scale
    return weights


def _dominant_pair_from_weights(weights: dict[str, float]) -> tuple[str, str] | None:
    if not weights:
        return None
    positive_subjects = [
        (str(subject), float(weight))
        for subject, weight in weights.items()
        if float(weight) > 0.0
    ]
    negative_subjects = [
        (str(subject), float(weight))
        for subject, weight in weights.items()
        if float(weight) < 0.0
    ]
    if not positive_subjects or not negative_subjects:
        return None
    long_subject = max(positive_subjects, key=lambda item: item[1])[0]
    short_subject = min(negative_subjects, key=lambda item: item[1])[0]
    if not long_subject or not short_subject or long_subject == short_subject:
        return None
    return long_subject, short_subject


def _dominant_pair_from_selected_pairs(
    selected_pairs: list[tuple[float, float, str, str]],
) -> tuple[str, str] | None:
    if not selected_pairs:
        return None
    _, _, long_subject, short_subject = selected_pairs[0]
    if not long_subject or not short_subject or long_subject == short_subject:
        return None
    return str(long_subject), str(short_subject)


def _pair_candidate_from_subjects(
    *,
    ordered: pd.DataFrame,
    constraints: dict[str, Any],
    long_subject: str,
    short_subject: str,
) -> tuple[float, float, str, str] | None:
    if ordered.empty or not long_subject or not short_subject or long_subject == short_subject:
        return None
    if "subject" not in ordered.columns or "score" not in ordered.columns:
        return None
    pair_rows = ordered.loc[ordered["subject"].astype(str).isin([str(long_subject), str(short_subject)])].copy()
    if len(pair_rows) != 2:
        return None
    long_row = pair_rows.loc[pair_rows["subject"].astype(str) == str(long_subject)]
    short_row = pair_rows.loc[pair_rows["subject"].astype(str) == str(short_subject)]
    if long_row.empty or short_row.empty:
        return None
    long_row = long_row.iloc[0]
    short_row = short_row.iloc[0]
    quality_floor = float(constraints.get("pair_quality_floor", 0.35) or 0.35)
    score_spread_min = float(constraints.get("pair_score_spread_min", 0.08) or 0.08)
    trend_crowding_max = constraints.get("pair_trend_crowding_max")
    short_quality_max = constraints.get("pair_short_quality_max")
    long_quality = float(long_row.get("_quality_anchor", 0.0))
    short_quality = float(short_row.get("_quality_anchor", 0.0))
    if long_quality < quality_floor or short_quality < quality_floor:
        return None
    if int(long_row.get("_quality_bucket", -1)) != int(short_row.get("_quality_bucket", -2)):
        return None
    if trend_crowding_max is not None:
        long_crowding = float(long_row.get("_trend_crowding", 1.0))
        short_crowding = float(short_row.get("_trend_crowding", 1.0))
        if max(long_crowding, short_crowding) > float(trend_crowding_max):
            return None
    if short_quality_max is not None and short_quality > float(short_quality_max):
        return None
    spread = float(long_row.get("score", 0.0)) - float(short_row.get("score", 0.0))
    if spread <= score_spread_min:
        return None
    quality_balance = 1.0 - abs(long_quality - short_quality)
    pair_strength = spread * max(quality_balance, 0.1)
    return float(pair_strength), float(quality_balance), str(long_subject), str(short_subject)


def _scale_cross_sectional_turnover(
    *,
    raw_target_weights: dict[str, float],
    previous_weights: dict[str, float],
    max_turnover_per_rebalance: float,
    turnover_mode: str | None = None,
) -> dict[str, float]:
    union_subjects = sorted(set(raw_target_weights) | set(previous_weights))
    raw_deltas = {
        subject: float(raw_target_weights.get(subject, 0.0)) - float(previous_weights.get(subject, 0.0))
        for subject in union_subjects
    }
    gross_turnover = sum(abs(delta) for delta in raw_deltas.values())
    if not math.isfinite(max_turnover_per_rebalance) or gross_turnover <= 0.0 or gross_turnover <= max_turnover_per_rebalance:
        return {subject: float(weight) for subject, weight in raw_target_weights.items() if abs(float(weight)) > 0.0}
    if str(turnover_mode or "").strip().lower() == "exit_first":
        return _scale_cross_sectional_turnover_exit_first(
            raw_target_weights=raw_target_weights,
            previous_weights=previous_weights,
            max_turnover_per_rebalance=max_turnover_per_rebalance,
            union_subjects=union_subjects,
        )
    if str(turnover_mode or "").strip().lower() == "pair_hold":
        return _scale_cross_sectional_turnover_pair_hold(
            raw_target_weights=raw_target_weights,
            previous_weights=previous_weights,
            max_turnover_per_rebalance=max_turnover_per_rebalance,
            union_subjects=union_subjects,
        )
    if str(turnover_mode or "").strip().lower() == "pair_project":
        return _scale_cross_sectional_turnover_pair_project(
            raw_target_weights=raw_target_weights,
            previous_weights=previous_weights,
            max_turnover_per_rebalance=max_turnover_per_rebalance,
            union_subjects=union_subjects,
        )
    scale = float(max_turnover_per_rebalance) / float(gross_turnover)
    scaled_weights = {
        subject: float(previous_weights.get(subject, 0.0)) + (float(delta) * scale)
        for subject, delta in raw_deltas.items()
    }
    return {subject: float(weight) for subject, weight in scaled_weights.items() if abs(float(weight)) > 0.0}


def _scale_cross_sectional_turnover_exit_first(
    *,
    raw_target_weights: dict[str, float],
    previous_weights: dict[str, float],
    max_turnover_per_rebalance: float,
    union_subjects: list[str],
) -> dict[str, float]:
    scaled_weights = {
        subject: float(previous_weights.get(subject, 0.0))
        for subject in union_subjects
    }
    exit_deltas: dict[str, float] = {}
    entry_deltas: dict[str, float] = {}
    for subject in union_subjects:
        previous_weight = float(previous_weights.get(subject, 0.0))
        target_weight = float(raw_target_weights.get(subject, 0.0))
        if abs(previous_weight) <= 0.0 and abs(target_weight) <= 0.0:
            continue
        if abs(previous_weight) <= 0.0:
            entry_deltas[subject] = target_weight
            continue
        if abs(target_weight) <= 0.0:
            exit_deltas[subject] = -previous_weight
            continue
        if previous_weight * target_weight < 0.0:
            exit_deltas[subject] = -previous_weight
            entry_deltas[subject] = target_weight
            continue
        if abs(target_weight) < abs(previous_weight):
            exit_deltas[subject] = target_weight - previous_weight
            continue
        if abs(target_weight) > abs(previous_weight):
            entry_deltas[subject] = target_weight - previous_weight

    remaining_turnover = float(max_turnover_per_rebalance)
    exit_turnover = sum(abs(delta) for delta in exit_deltas.values())
    if exit_turnover > 0.0:
        exit_scale = min(1.0, remaining_turnover / exit_turnover)
        for subject, delta in exit_deltas.items():
            scaled_weights[subject] = float(scaled_weights.get(subject, 0.0)) + (float(delta) * exit_scale)
        remaining_turnover -= exit_turnover * exit_scale

    entry_turnover = sum(abs(delta) for delta in entry_deltas.values())
    if remaining_turnover > 0.0 and entry_turnover > 0.0:
        entry_scale = min(1.0, remaining_turnover / entry_turnover)
        for subject, delta in entry_deltas.items():
            scaled_weights[subject] = float(scaled_weights.get(subject, 0.0)) + (float(delta) * entry_scale)

    return {
        subject: float(weight)
        for subject, weight in scaled_weights.items()
        if abs(float(weight)) > 0.0
    }


def _scale_cross_sectional_turnover_pair_hold(
    *,
    raw_target_weights: dict[str, float],
    previous_weights: dict[str, float],
    max_turnover_per_rebalance: float,
    union_subjects: list[str],
) -> dict[str, float]:
    previous_subjects = {
        subject
        for subject, weight in previous_weights.items()
        if abs(float(weight)) > 0.0
    }
    raw_subjects = {
        subject
        for subject, weight in raw_target_weights.items()
        if abs(float(weight)) > 0.0
    }
    if (
        previous_subjects
        and raw_subjects
        and len(previous_subjects) <= 2
        and len(raw_subjects) <= 2
        and previous_subjects != raw_subjects
    ):
        return {
            subject: float(weight)
            for subject, weight in previous_weights.items()
            if abs(float(weight)) > 0.0
        }
    scale = float(max_turnover_per_rebalance) / float(
        sum(
            abs(float(raw_target_weights.get(subject, 0.0)) - float(previous_weights.get(subject, 0.0)))
            for subject in union_subjects
        )
    )
    scaled_weights = {
        subject: float(previous_weights.get(subject, 0.0))
        + (
            float(raw_target_weights.get(subject, 0.0))
            - float(previous_weights.get(subject, 0.0))
        ) * scale
        for subject in union_subjects
    }
    return {
        subject: float(weight)
        for subject, weight in scaled_weights.items()
        if abs(float(weight)) > 0.0
    }


def _scale_cross_sectional_turnover_pair_project(
    *,
    raw_target_weights: dict[str, float],
    previous_weights: dict[str, float],
    max_turnover_per_rebalance: float,
    union_subjects: list[str],
) -> dict[str, float]:
    gross_turnover = sum(
        abs(float(raw_target_weights.get(subject, 0.0)) - float(previous_weights.get(subject, 0.0)))
        for subject in union_subjects
    )
    scale = float(max_turnover_per_rebalance) / float(max(gross_turnover, 1e-12))
    scaled_weights = {
        subject: float(previous_weights.get(subject, 0.0))
        + (
            float(raw_target_weights.get(subject, 0.0))
            - float(previous_weights.get(subject, 0.0))
        ) * scale
        for subject in union_subjects
    }
    positive_weights = {
        subject: float(weight)
        for subject, weight in scaled_weights.items()
        if float(weight) > 0.0
    }
    negative_weights = {
        subject: float(weight)
        for subject, weight in scaled_weights.items()
        if float(weight) < 0.0
    }
    if not positive_weights or not negative_weights:
        return {
            subject: float(weight)
            for subject, weight in scaled_weights.items()
            if abs(float(weight)) > 0.0
        }
    strongest_long = max(positive_weights, key=lambda subject: abs(float(positive_weights[subject])))
    strongest_short = min(negative_weights, key=lambda subject: float(negative_weights[subject]))
    projected_notional = min(
        sum(float(weight) for weight in positive_weights.values()),
        abs(sum(float(weight) for weight in negative_weights.values())),
    )
    if projected_notional <= 0.0:
        return {}
    return {
        strongest_long: float(projected_notional),
        strongest_short: -float(projected_notional),
    }


def _apply_turnover_cap(*, raw_delta_weight: float, max_turnover_per_rebalance: float) -> float:
    if not math.isfinite(max_turnover_per_rebalance) or abs(float(raw_delta_weight)) <= float(max_turnover_per_rebalance):
        return float(raw_delta_weight)
    scale = float(max_turnover_per_rebalance) / abs(float(raw_delta_weight))
    return float(raw_delta_weight) * scale


def _next_fill_index(
    *,
    ordered_length: int,
    decision_indices: list[int],
    decision_offset: int,
    latency_bars: int,
) -> int | None:
    if decision_offset + 1 >= len(decision_indices):
        return None
    next_fill_index = decision_indices[decision_offset + 1] + latency_bars
    return next_fill_index if next_fill_index < ordered_length else None


def _next_fill_offset(
    *,
    timestamp_count: int,
    decision_timestamp_indices: list[int],
    decision_offset: int,
    latency_bars: int,
) -> int | None:
    if decision_offset + 1 >= len(decision_timestamp_indices):
        return None
    next_fill_offset = decision_timestamp_indices[decision_offset + 1] + latency_bars
    return next_fill_offset if next_fill_offset < timestamp_count else None


def _price_path_return(
    *,
    entry_row: pd.Series,
    exit_row: pd.Series,
    weight: float,
    execution_venue: str,
    subject: str,
    data_gap_blockers: set[str] | list[str],
) -> float:
    if abs(float(weight)) <= 0.0:
        return 0.0
    price_field = "spot_close" if execution_venue == "spot" else "perp_close"
    entry_price = _safe_float(entry_row.get(price_field))
    exit_price = _safe_float(exit_row.get(price_field))
    if entry_price <= 0.0 or exit_price <= 0.0:
        blocker = f"{subject or 'unknown'}: missing {price_field} for execution path"
        if isinstance(data_gap_blockers, set):
            data_gap_blockers.add(blocker)
        else:
            data_gap_blockers.append(blocker)
        return 0.0
    return float(weight) * ((exit_price / entry_price) - 1.0)


def _funding_cost_return(*, hold_slice: pd.DataFrame, weight: float, execution_venue: str) -> float:
    if execution_venue != "perp" or abs(float(weight)) <= 0.0 or hold_slice.empty:
        return 0.0
    if "funding_rate" in hold_slice.columns:
        funding_rate = pd.to_numeric(hold_slice["funding_rate"], errors="coerce").fillna(0.0)
    else:
        funding_rate = pd.Series(0.0, index=hold_slice.index, dtype="float64")
    if "funding_sample_count" in hold_slice.columns:
        funding_sample_count = pd.to_numeric(hold_slice["funding_sample_count"], errors="coerce").fillna(0.0)
    else:
        funding_sample_count = pd.Series(0.0, index=hold_slice.index, dtype="float64")
    return float((float(weight) * funding_rate * funding_sample_count).sum())


def _borrow_cost_return(
    *,
    entry_timestamp_ms: int,
    exit_timestamp_ms: int,
    weight: float,
    execution_venue: str,
    execution_cost_model: dict[str, Any],
) -> float:
    if execution_venue != "spot" or float(weight) >= 0.0 or exit_timestamp_ms <= entry_timestamp_ms:
        return 0.0
    holding_days = float(exit_timestamp_ms - entry_timestamp_ms) / DAY_MS
    borrow_bps_per_day = float(execution_cost_model.get("spot_short_borrow_bps_per_day", 15.0) or 15.0)
    return abs(float(weight)) * borrow_bps_per_day * holding_days / 10000.0


def _trade_costs(
    *,
    row: pd.Series,
    delta_weight: float,
    target_weight: float,
    execution_venue: str,
    execution_cost_model: dict[str, Any],
    reference_capital_usd: float | None,
    capacity_limits: dict[str, float] | None,
    subject: str,
) -> dict[str, Any]:
    data_gap_blockers: set[str] = set()
    venue_costs = dict(dict(execution_cost_model.get("venues") or {}).get(execution_venue) or {})
    trade_notional_usd = 0.0
    trade_participation_rate = 0.0
    inventory_participation_rate = 0.0
    liquidity_volume_proxy_usd = 0.0
    if reference_capital_usd is not None and float(reference_capital_usd) > 0.0:
        trade_notional_usd = float(reference_capital_usd) * abs(float(delta_weight))
        raw_liquidity_volume_proxy_usd = _trade_liquidity_volume_proxy_usd(row=row, execution_venue=execution_venue)
        if trade_notional_usd > 0.0:
            if raw_liquidity_volume_proxy_usd <= 0.0:
                data_gap_blockers.add(f"{subject or 'unknown'}: missing trade liquidity proxy for {execution_venue}")
            else:
                liquidity_volume_proxy_usd = raw_liquidity_volume_proxy_usd * float(execution_cost_model["liquidity_volume_scale"])
                trade_participation_rate = trade_notional_usd / liquidity_volume_proxy_usd
        else:
            liquidity_volume_proxy_usd = raw_liquidity_volume_proxy_usd
        require_perp_inventory_open_interest = bool(
            execution_cost_model.get("require_perp_inventory_open_interest", True)
        )
        if execution_venue == "perp" and require_perp_inventory_open_interest and abs(float(target_weight)) > 0.0:
            open_interest_value = _safe_float(row.get("open_interest_value"))
            if open_interest_value <= 0.0:
                data_gap_blockers.add(f"{subject or 'unknown'}: missing open_interest_value for perp inventory capacity")
            else:
                inventory_participation_rate = (float(reference_capital_usd) * abs(float(target_weight))) / open_interest_value
    impact_bps = float(venue_costs.get("impact_coefficient_bps", 0.0) or 0.0) * math.sqrt(max(trade_participation_rate, 0.0))
    fee_cost_return = abs(float(delta_weight)) * float(venue_costs.get("fee_bps_one_way", 0.0) or 0.0) / 10000.0
    slippage_cost_return = abs(float(delta_weight)) * (
        float(venue_costs.get("half_spread_bps", 0.0) or 0.0) + impact_bps
    ) / 10000.0
    trade_limit = float(dict(capacity_limits or {}).get("max_trade_participation_rate_max", 0.0) or 0.0)
    inventory_limit = float(dict(capacity_limits or {}).get("max_inventory_participation_rate_max", 0.0) or 0.0)
    capacity_breach_count = 0
    if trade_limit > 0.0 and trade_participation_rate > trade_limit:
        capacity_breach_count += 1
    if inventory_limit > 0.0 and inventory_participation_rate > inventory_limit:
        capacity_breach_count += 1
    return {
        "fee_cost_return": float(fee_cost_return),
        "slippage_cost_return": float(slippage_cost_return),
        "trade_notional_usd": float(trade_notional_usd),
        "trade_participation_rate": float(trade_participation_rate),
        "inventory_participation_rate": float(inventory_participation_rate),
        "max_participation_rate": float(max(trade_participation_rate, inventory_participation_rate)),
        "capacity_breach_count": int(capacity_breach_count),
        "liquidity_volume_proxy_usd": float(liquidity_volume_proxy_usd),
        "data_gap_blockers": sorted(data_gap_blockers),
    }


def _trade_liquidity_volume_proxy_usd(*, row: pd.Series, execution_venue: str) -> float:
    if execution_venue == "perp":
        perp_quote_volume_usd = _safe_float(row.get("perp_quote_volume_usd"))
        if perp_quote_volume_usd > 0.0:
            return perp_quote_volume_usd
        perp_volume = _safe_float(row.get("perp_volume"))
        perp_close = _safe_float(row.get("perp_close"))
        if perp_volume > 0.0 and perp_close > 0.0:
            return perp_volume * perp_close
        return 0.0
    for field_name in SPOT_TRADE_LIQUIDITY_FIELDS:
        value = _safe_float(row.get(field_name))
        if value > 0.0:
            return value
    return 0.0


def _perp_subject_available_mask(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype="bool")
    if "has_perp" not in frame.columns and "usdm_symbol" not in frame.columns:
        return pd.Series(True, index=frame.index, dtype="bool")
    has_perp = _bool_series(frame, "has_perp") if "has_perp" in frame.columns else pd.Series(True, index=frame.index, dtype="bool")
    if "usdm_symbol" not in frame.columns:
        return has_perp
    usdm_symbol = frame["usdm_symbol"].fillna("").astype(str).str.strip()
    return has_perp & usdm_symbol.ne("")


def _perp_execution_row_eligible_mask(frame: pd.DataFrame) -> pd.Series:
    explicit_mask = _bool_series(frame, "perp_execution_eligible")
    if "perp_execution_eligible" in frame.columns:
        return explicit_mask
    if (
        "perp_close" not in frame.columns
        and "open_interest_value" not in frame.columns
        and "perp_quote_volume_usd" not in frame.columns
        and "perp_volume" not in frame.columns
    ):
        return pd.Series(True, index=frame.index, dtype="bool")
    perp_close = _numeric_series(frame, "perp_close")
    perp_quote_volume_usd = _numeric_series(frame, "perp_quote_volume_usd")
    perp_volume = _numeric_series(frame, "perp_volume")
    open_interest_value = _numeric_series(frame, "open_interest_value")
    liquidity_ready = perp_quote_volume_usd.gt(0.0) | (perp_volume.gt(0.0) & perp_close.gt(0.0))
    return perp_close.gt(0.0) & open_interest_value.gt(0.0) & liquidity_ready


def _perp_executable_start_ms_series(
    frame: pd.DataFrame,
    *,
    has_perp_mask: pd.Series,
    row_eligible_mask: pd.Series,
) -> pd.Series:
    if "perp_executable_start_ms" in frame.columns:
        return pd.to_numeric(frame["perp_executable_start_ms"], errors="coerce")
    if frame.empty:
        return pd.Series(dtype="float64")
    subject_ready = frame.loc[has_perp_mask & row_eligible_mask, ["subject", "timestamp_ms"]].copy()
    if subject_ready.empty:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    subject_ready["timestamp_ms"] = pd.to_numeric(subject_ready["timestamp_ms"], errors="coerce")
    subject_start = subject_ready.groupby("subject", dropna=False)["timestamp_ms"].min().to_dict()
    return frame["subject"].map(subject_start).astype("float64")


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _bool_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(False, index=frame.index, dtype="bool")
    series = frame[column]
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype("bool")
    normalized = series.fillna("").astype(str).str.strip().str.lower()
    return normalized.isin({"1", "true", "yes"})


def _safe_float(value: Any) -> float:
    try:
        numeric = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(numeric):
        return 0.0
    return numeric
