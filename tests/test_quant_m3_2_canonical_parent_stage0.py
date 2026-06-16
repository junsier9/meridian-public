from __future__ import annotations

import pandas as pd

from scripts.quant_research.evaluate_m3_2_canonical_parent_stage0 import (
    _boundary_change_summary,
    _compare,
)


def test_m3_2_canonical_compare_fail_closes_small_delta() -> None:
    parent = {
        "ready_long_short_mean": 0.0100,
        "ready_long_short_positive_fraction": 0.55,
        "long_short_mean": 0.0090,
        "long_short_positive_fraction": 0.54,
    }
    candidate = {
        "ready_long_short_mean": 0.0103,
        "ready_long_short_positive_fraction": 0.56,
        "long_short_mean": 0.0091,
        "long_short_positive_fraction": 0.54,
    }

    comparison = _compare(candidate, parent)

    assert comparison["verdict"] == "stage0_at_par"
    assert comparison["delta_ready_long_short_mean"] == 0.0002999999999999999


def test_m3_2_canonical_boundary_change_splits_sides() -> None:
    parent = pd.DataFrame(
        {
            "timestamp_ms": [1, 1, 1, 1],
            "side": ["long", "long", "short", "short"],
            "subject": ["A", "B", "C", "D"],
        }
    )
    candidate = pd.DataFrame(
        {
            "timestamp_ms": [1, 1, 1, 1],
            "side": ["long", "long", "short", "short"],
            "subject": ["A", "E", "C", "D"],
        }
    )

    summary = _boundary_change_summary(parent, candidate)

    assert summary["long_changed_timestamp_fraction"] == 1.0
    assert summary["short_changed_timestamp_fraction"] == 0.0
    assert summary["long_mean_entered_count"] == 1.0
