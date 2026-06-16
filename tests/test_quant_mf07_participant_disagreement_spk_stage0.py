from __future__ import annotations

import pandas as pd
import pytest

from scripts.quant_research.evaluate_mf07_participant_disagreement_spk_stage0 import (
    _add_mf07_flags,
    _compare_short_baskets,
    _summarize_rows,
)


def test_mf07_flags_capture_low_corr_and_high_gap() -> None:
    frame = pd.DataFrame(
        {
            "top_global_disagreement_1h_30d": [-0.8, 0.0, 0.8],
            "disagree_tt_retail": [1.0, 2.0, 10.0],
            "top_trader_velocity_1h_abs_24h": [0.1, 0.2, 5.0],
        }
    )

    flagged, meta = _add_mf07_flags(frame)

    assert meta["top_global_corr_coverage"] == 1.0
    assert flagged["mf07_low_top_global_corr_flag"].tolist() == [True, False, False]
    assert flagged["mf07_high_abs_tt_retail_gap_flag"].tolist() == [False, False, True]
    assert flagged["mf07_high_tt_velocity_flag"].tolist() == [False, False, True]
    assert flagged["mf07_any_participant_stress_flag"].tolist() == [True, False, True]


def test_mf07_compare_short_baskets_prefers_more_negative_returns() -> None:
    comparison = _compare_short_baskets(
        candidate={"next_10d_mean": -0.020},
        baseline={"next_10d_mean": -0.010},
        target_horizon_bars=10,
    )

    assert comparison["verdict"] == "stage0_positive"
    assert comparison["short_basket_edge_vs_baseline_10d"] == pytest.approx(0.01)


def test_mf07_summary_tracks_flag_fraction() -> None:
    rows = pd.DataFrame(
        {
            "timestamp_ms": [1, 1],
            "subject": ["A", "B"],
            "forward_1d_log_return": [0.08, -0.01],
            "forward_10d_log_return": [-0.02, 0.00],
            "mf07_any_participant_stress_flag": [True, False],
        }
    )

    summary = _summarize_rows(rows, target_horizon_bars=10)

    assert summary["next_10d_mean"] == pytest.approx(-0.01)
    assert summary["next_1d_squeeze_gt_5pct_fraction"] == 0.5
    assert summary["mf07_any_participant_stress_flag_fraction"] == 0.5
