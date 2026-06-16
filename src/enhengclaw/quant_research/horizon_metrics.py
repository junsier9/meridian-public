from __future__ import annotations

from typing import Any

import pandas as pd

from .fixed_set_comparison import performance_summary


SHARPE_METRIC_CONVENTION_VERSION = "quant_h10d_overlap_adjusted_sharpe.v1"
YEAR_DAYS = 365.0
DAY_MS = 24 * 60 * 60 * 1000


def independent_period_bars(
    *,
    target_horizon_bars: int,
    realization_step_bars: int | None = None,
) -> int:
    horizon = max(int(target_horizon_bars), 1)
    step = horizon if realization_step_bars is None else max(int(realization_step_bars), 1)
    return max(horizon, step)


def overlap_adjusted_periods_per_year(
    *,
    bar_interval_ms: int,
    target_horizon_bars: int,
    realization_step_bars: int | None = None,
) -> float:
    interval_days = max(float(bar_interval_ms) / float(DAY_MS), 1e-12)
    bars = independent_period_bars(
        target_horizon_bars=target_horizon_bars,
        realization_step_bars=realization_step_bars,
    )
    return float(YEAR_DAYS / (interval_days * float(bars)))


def overlap_adjusted_performance_summary(
    period_returns: pd.Series,
    *,
    bar_interval_ms: int,
    target_horizon_bars: int,
    realization_step_bars: int | None = None,
) -> dict[str, Any]:
    periods_per_year = overlap_adjusted_periods_per_year(
        bar_interval_ms=bar_interval_ms,
        target_horizon_bars=target_horizon_bars,
        realization_step_bars=realization_step_bars,
    )
    summary = dict(performance_summary(period_returns, periods_per_year=periods_per_year))
    summary.update(
        {
            "sharpe_metric_convention": SHARPE_METRIC_CONVENTION_VERSION,
            "overlap_adjusted_periods_per_year": float(periods_per_year),
            "independent_period_bars": int(
                independent_period_bars(
                    target_horizon_bars=target_horizon_bars,
                    realization_step_bars=realization_step_bars,
                )
            ),
        }
    )
    return summary
