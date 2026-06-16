from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.quant_research.evaluate_m3_2_boundary_activation_falsification import (
    _cost_stress_test,
    _delay_state_by_timestamp,
    _shuffle_forward_returns_within_timestamp,
    _side_bucket_edge,
)
from scripts.quant_research.evaluate_m3_2_boundary_activation_stage0 import BoundarySpec


def _spec(side: str = "long") -> BoundarySpec:
    return BoundarySpec(
        label="toy",
        side=side,
        action="replace_high",
        state_column="m3_2_reflexive_rebound_state",
        state_threshold=0.75,
        exposure_mode="idio",
        interpretation="toy",
        pool_size=4,
        side_count=2,
    )


def test_m3_2_falsification_delay_uses_previous_timestamp_state() -> None:
    frame = pd.DataFrame(
        {
            "timestamp_ms": [1, 1, 2, 2, 3, 3],
            "date_utc": ["2026-01-01"] * 2 + ["2026-01-02"] * 2 + ["2026-01-03"] * 2,
            "subject": ["A", "B", "A", "B", "A", "B"],
            "m3_2_panel_ready": [True, True, True, True, False, False],
            "m3_2_reflexive_rebound_state": [1.0, 1.0, 0.0, 0.0, 0.9, 0.9],
        }
    )

    delayed = _delay_state_by_timestamp(frame, _spec(), lags=1)
    unique = delayed.drop_duplicates("timestamp_ms").sort_values("timestamp_ms")

    assert pd.isna(unique.iloc[0]["m3_2_reflexive_rebound_state"])
    assert unique.iloc[1]["m3_2_reflexive_rebound_state"] == 1.0
    assert unique.iloc[2]["m3_2_reflexive_rebound_state"] == 0.0
    assert bool(unique.iloc[2]["m3_2_panel_ready"]) is True


def test_m3_2_falsification_label_shuffle_preserves_timestamp_return_multisets() -> None:
    frame = pd.DataFrame(
        {
            "timestamp_ms": [1, 1, 1, 2, 2, 2],
            "forward_1d_log_return": [1, 2, 3, 4, 5, 6],
            "forward_10d_log_return": [10, 20, 30, 40, 50, 60],
        }
    )

    shuffled = _shuffle_forward_returns_within_timestamp(
        frame,
        target_horizon_bars=10,
        rng=np.random.default_rng(7),
    )

    for timestamp in [1, 2]:
        original = frame.loc[frame["timestamp_ms"].eq(timestamp), "forward_10d_log_return"].tolist()
        actual = shuffled.loc[shuffled["timestamp_ms"].eq(timestamp), "forward_10d_log_return"].tolist()
        assert sorted(actual) == sorted(original)


def test_m3_2_falsification_cost_stress_penalizes_active_changes() -> None:
    observed = {
        "comparison_vs_parent": {"delta_active_long_short_mean": 0.010},
        "boundary_change": {
            "long_active_changed_timestamp_fraction": 0.50,
            "short_active_changed_timestamp_fraction": 0.0,
        },
    }

    result = _cost_stress_test(observed, base_replacement_cost_bps=10.0)

    assert result["two_x_cost_rate"] == 0.002
    assert result["cost_stressed_delta_active_long_short_mean"] == pytest.approx(0.009)
    assert result["passed"] is True


def test_m3_2_falsification_bucket_edge_requires_two_positive_buckets() -> None:
    parent = pd.DataFrame(
        {
            "side": ["long", "long", "long", "long", "long", "long"],
            "_m3_2_active": [True] * 6,
            "liquidity_bucket": ["top", "top", "top", "mid", "mid", "mid"],
            "forward_10d_log_return": [0.01, 0.01, 0.01, 0.00, 0.00, 0.00],
        }
    )
    candidate = pd.DataFrame(
        {
            "side": ["long", "long", "long", "long", "long", "long"],
            "_m3_2_active": [True] * 6,
            "liquidity_bucket": ["top", "top", "top", "mid", "mid", "mid"],
            "forward_10d_log_return": [0.03, 0.03, 0.03, 0.02, 0.02, 0.02],
        }
    )

    result = _side_bucket_edge(parent, candidate, _spec("long"), target_horizon_bars=10, min_rows=3)

    assert result["passed"] is True
    assert result["bucket_count"] == 2
    assert result["positive_bucket_count"] == 2
