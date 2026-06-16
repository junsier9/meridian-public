from __future__ import annotations

import pandas as pd
import pytest

from scripts.quant_research.evaluate_mf07_subday_participant_pivot_stage0 import (
    HOUR_MS,
    _add_pivot_flags,
    _compare_short_baskets,
    _subject_participant_pivots,
)


def test_subday_participant_pivots_use_prior_1h_windows() -> None:
    event_ms = 24 * HOUR_MS
    events = pd.DataFrame({"timestamp_ms": [event_ms]})
    bars = pd.DataFrame(
        {
            "open_time_ms": [0, 18 * HOUR_MS, 23 * HOUR_MS],
            "top_trader_long_pct": [50.0, 48.0, 46.0],
            "global_account_long_pct": [50.0, 51.0, 53.0],
        }
    )

    pivots = _subject_participant_pivots(events, bars, symbol="ABC")
    row = pivots.iloc[0]

    assert row["subject"] == "ABC"
    assert row["mf07_subday_top_delta_6h"] == pytest.approx(-2.0)
    assert row["mf07_subday_global_delta_6h"] == pytest.approx(2.0)
    assert row["mf07_subday_top_delta_24h"] == pytest.approx(-4.0)
    assert row["mf07_subday_global_delta_24h"] == pytest.approx(3.0)
    assert row["mf07_subday_retail_minus_top_delta_24h"] == pytest.approx(7.0)


def test_subday_pivot_flags_capture_retail_chase_and_top_lead() -> None:
    frame = pd.DataFrame(
        {
            "mf07_subday_top_delta_24h": [-4.0, 0.0, 4.0, 1.0],
            "mf07_subday_global_delta_24h": [3.0, 1.0, 0.0, -1.0],
            "mf07_subday_top_delta_6h": [-2.0, 0.0, 2.0, 1.0],
            "mf07_subday_global_delta_6h": [2.0, 0.5, 0.0, -1.0],
            "mf07_subday_retail_minus_top_delta_24h": [7.0, 1.0, -4.0, -2.0],
            "mf07_subday_top_minus_retail_delta_24h": [-7.0, -1.0, 4.0, 2.0],
        }
    )

    flagged, meta = _add_pivot_flags(frame)

    assert meta["pivot_24h_coverage_after_merge"] == 1.0
    assert flagged["mf07_subday_retail_chase_top_fade_flag"].tolist() == [
        True,
        False,
        False,
        False,
    ]
    assert flagged["mf07_subday_retail_outpaces_top_flag"].tolist() == [
        True,
        False,
        False,
        False,
    ]
    assert flagged["mf07_subday_top_leads_retail_flag"].tolist() == [
        False,
        False,
        True,
        False,
    ]
    assert flagged["mf07_subday_not_retail_chase_top_fade_flag"].tolist() == [
        False,
        True,
        True,
        True,
    ]


def test_subday_compare_short_baskets_prefers_more_negative_returns() -> None:
    comparison = _compare_short_baskets(
        candidate={"next_10d_mean": -0.030},
        baseline={"next_10d_mean": -0.010},
        target_horizon_bars=10,
    )

    assert comparison["verdict"] == "stage0_positive"
    assert comparison["short_basket_edge_vs_baseline_10d"] == pytest.approx(0.02)
