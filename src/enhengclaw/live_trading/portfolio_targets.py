from __future__ import annotations

import math
from typing import Any

import pandas as pd

from enhengclaw.live_trading.models import LiveDecisionSnapshot, TargetPortfolio, TargetPosition
from enhengclaw.quant_research.execution_backtest import _scale_cross_sectional_turnover


def portfolio_drawdown_multiplier(*, current_drawdown: float, constraints: dict[str, Any]) -> float:
    drawdown = max(float(current_drawdown), 0.0)
    start = float(constraints.get("dd_throttle_start_threshold", constraints.get("dd_throttle_5pct_threshold", 0.10)) or 0.10)
    full = float(constraints.get("dd_throttle_full_threshold", constraints.get("dd_throttle_10pct_threshold", 0.25)) or 0.25)
    floor = float(constraints.get("dd_throttle_min_multiplier", constraints.get("dd_throttle_10pct_multiplier", 0.80)) or 0.80)
    if drawdown <= start:
        return 1.0
    if drawdown >= full:
        return floor
    span = max(full - start, 1e-12)
    return 1.0 - ((drawdown - start) / span) * (1.0 - floor)


def build_target_portfolio(
    snapshot: LiveDecisionSnapshot,
    *,
    config: dict[str, Any],
    allocated_capital_usdt: float,
    current_drawdown: float = 0.0,
    previous_weights: dict[str, float] | None = None,
) -> TargetPortfolio:
    constraints = dict(config.get("strategy_profile") or {})
    portfolio_id = f"{snapshot.decision_id}:portfolio"
    blockers: list[str] = list(snapshot.blockers)
    positions: list[TargetPosition] = []
    if snapshot.status != "ok":
        blockers.append("decision_snapshot_not_ok")
    if allocated_capital_usdt <= 0.0:
        blockers.append("allocated_capital_not_positive")
    scores = snapshot.scores.copy()
    if scores.empty:
        blockers.append("empty_decision_scores")
    if blockers:
        return _portfolio(
            portfolio_id=portfolio_id,
            snapshot=snapshot,
            allocated_capital_usdt=allocated_capital_usdt,
            current_drawdown=current_drawdown,
            multiplier=1.0,
            positions=positions,
            blockers=blockers,
        )

    raw_weights = _raw_target_weights(scores, constraints=constraints)
    if not raw_weights:
        blockers.append("no_target_weights")
    multiplier = portfolio_drawdown_multiplier(current_drawdown=current_drawdown, constraints=constraints)
    raw_weights = {subject: weight * multiplier for subject, weight in raw_weights.items()}
    max_gross = float(constraints.get("max_gross_leverage", math.inf) or math.inf)
    gross = sum(abs(weight) for weight in raw_weights.values())
    if math.isfinite(max_gross) and gross > max_gross and gross > 0.0:
        scale = max_gross / gross
        raw_weights = {subject: weight * scale for subject, weight in raw_weights.items()}
    previous = dict(previous_weights or {})
    target_weights = _scale_cross_sectional_turnover(
        raw_target_weights=raw_weights,
        previous_weights=previous,
        max_turnover_per_rebalance=float(constraints.get("max_turnover_per_rebalance", math.inf) or math.inf),
    )
    row_by_subject = {str(row["subject"]): row for _, row in scores.iterrows()}
    short_multiplier_column = str(constraints.get("short_position_weight_multiplier_column") or "").strip()
    for subject, weight in sorted(target_weights.items()):
        row = row_by_subject.get(str(subject))
        if row is None:
            continue
        side = "long" if float(weight) > 0.0 else "short"
        short_multiplier = 1.0
        if side == "short" and short_multiplier_column and short_multiplier_column in scores.columns:
            short_multiplier = float(pd.to_numeric(pd.Series([row.get(short_multiplier_column)]), errors="coerce").fillna(1.0).iloc[0])
        previous_weight = float(previous.get(str(subject), 0.0) or 0.0)
        positions.append(
            TargetPosition(
                subject=str(subject),
                usdm_symbol=str(row.get("usdm_symbol") or f"{subject}USDT"),
                side=side,
                score=float(row.get("score", 0.0) or 0.0),
                target_weight=float(weight),
                target_notional_usdt=float(abs(weight) * allocated_capital_usdt),
                previous_target_weight=previous_weight,
                delta_target_weight=float(weight - previous_weight),
                raw_short_multiplier=float(short_multiplier),
                portfolio_drawdown_multiplier=float(multiplier),
                selection_reason="top_long" if side == "long" else "bottom_short",
            )
        )
    if not positions and not blockers:
        blockers.append("empty_target_positions")
    return _portfolio(
        portfolio_id=portfolio_id,
        snapshot=snapshot,
        allocated_capital_usdt=allocated_capital_usdt,
        current_drawdown=current_drawdown,
        multiplier=multiplier,
        positions=positions,
        blockers=blockers,
    )


def _raw_target_weights(decision_group: pd.DataFrame, *, constraints: dict[str, Any]) -> dict[str, float]:
    decision = _filter_eligible(decision_group, str(constraints.get("decision_eligible_column") or "binance_decision_eligible"))
    long_group = _filter_eligible(decision, str(constraints.get("long_decision_eligible_column") or ""))
    short_group = _filter_eligible(decision, str(constraints.get("short_decision_eligible_column") or ""))
    long_ordered = long_group.sort_values("score", ascending=False)
    short_ordered = short_group.sort_values("score", ascending=False)
    top_n = min(max(int(constraints.get("top_long_count", 3) or 3), 0), len(long_ordered))
    bottom_n = min(max(int(constraints.get("bottom_short_count", 3) or 3), 0), len(short_ordered))
    weights: dict[str, float] = {}
    if top_n > 0:
        each = float(constraints.get("long_leverage", 0.5) or 0.5) / float(top_n)
        for subject in long_ordered.head(top_n)["subject"]:
            weights[str(subject)] = each
    if bool(constraints.get("short_allowed", False)) and bottom_n > 0:
        each = float(constraints.get("short_leverage", 0.5) or 0.5) / float(bottom_n)
        multiplier_column = str(constraints.get("short_position_weight_multiplier_column") or "").strip()
        for _, row in short_ordered.tail(bottom_n).iterrows():
            multiplier = 1.0
            if multiplier_column and multiplier_column in row.index:
                multiplier = float(pd.to_numeric(pd.Series([row[multiplier_column]]), errors="coerce").fillna(1.0).iloc[0])
            weights[str(row["subject"])] = weights.get(str(row["subject"]), 0.0) - each * max(min(multiplier, 1.0), 0.0)
    return {subject: float(weight) for subject, weight in weights.items() if abs(float(weight)) > 1e-12}


def _filter_eligible(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    if not column or column not in frame.columns:
        return frame.copy()
    raw = frame[column]
    if pd.api.types.is_bool_dtype(raw):
        mask = raw.fillna(False).astype("bool")
    else:
        mask = raw.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y"})
    return frame.loc[mask].copy()


def _portfolio(
    *,
    portfolio_id: str,
    snapshot: LiveDecisionSnapshot,
    allocated_capital_usdt: float,
    current_drawdown: float,
    multiplier: float,
    positions: list[TargetPosition],
    blockers: list[str],
) -> TargetPortfolio:
    gross = sum(abs(position.target_weight) for position in positions)
    net = sum(position.target_weight for position in positions)
    return TargetPortfolio(
        portfolio_id=portfolio_id,
        decision_id=snapshot.decision_id,
        strategy_label=snapshot.strategy_label,
        allocated_capital_usdt=float(allocated_capital_usdt),
        portfolio_drawdown=float(current_drawdown),
        portfolio_drawdown_multiplier=float(multiplier),
        target_gross_weight=float(gross),
        target_net_weight=float(net),
        status="ok" if not blockers else "blocked",
        blockers=blockers,
        positions=positions,
    )
