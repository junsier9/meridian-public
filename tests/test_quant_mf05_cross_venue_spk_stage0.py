from __future__ import annotations

import pandas as pd
import pytest

from scripts.quant_research.evaluate_mf05_cross_venue_spk_stage0 import (
    _compare_short_baskets,
    _quantile_threshold,
    _summarize_rows,
)


def test_mf05_spk_quantile_threshold_ignores_missing_values() -> None:
    values = pd.Series([None, 1.0, 2.0, 3.0])

    assert _quantile_threshold(values, quantile=0.50) == 2.0


def test_mf05_spk_compare_short_baskets_prefers_more_negative_returns() -> None:
    comparison = _compare_short_baskets(
        candidate={"next_10d_mean": -0.020},
        baseline={"next_10d_mean": -0.010},
        target_horizon_bars=10,
    )

    assert comparison["verdict"] == "stage0_positive"
    assert comparison["short_basket_edge_vs_baseline_10d"] == 0.01


def test_mf05_spk_summary_tracks_cross_venue_flag_fraction() -> None:
    rows = pd.DataFrame(
        {
            "timestamp_ms": [1, 1],
            "subject": ["A", "B"],
            "forward_1d_log_return": [0.10, -0.02],
            "forward_10d_log_return": [-0.03, 0.01],
            "mf05_high_dispersion_flag": [True, False],
        }
    )

    summary = _summarize_rows(rows, target_horizon_bars=10)

    assert summary["row_count"] == 2
    assert summary["next_1d_squeeze_gt_5pct_fraction"] == 0.5
    assert summary["next_10d_mean"] == pytest.approx(-0.01)
    assert summary["mf05_high_dispersion_flag_fraction"] == 0.5
