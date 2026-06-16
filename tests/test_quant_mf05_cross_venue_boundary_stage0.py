from __future__ import annotations

import pandas as pd

from scripts.quant_research.evaluate_mf05_cross_venue_boundary_stage0 import (
    BoundarySpec,
    _compare,
    _signal_mask,
)


def test_mf05_signal_mask_requires_min_venues_and_threshold() -> None:
    frame = pd.DataFrame(
        {
            "n_venues": [2, 3, 4],
            "cross_venue_spot_dispersion": [0.50, 0.40, 0.70],
        }
    )
    spec = BoundarySpec(
        label="x",
        signal_column="cross_venue_spot_dispersion",
        mode="select",
        min_venues=3,
    )

    mask = _signal_mask(frame, spec=spec, threshold=0.45)

    assert mask.tolist() == [False, False, True]


def test_mf05_compare_uses_short_return_direction() -> None:
    parent = {"next_10d_mean": -0.010}
    candidate = {"next_10d_mean": -0.016}

    comparison = _compare(candidate, parent, target_horizon_bars=10)

    assert comparison["verdict"] == "stage0_positive"
    assert comparison["selected_short_edge_vs_parent_10d"] == 0.006
