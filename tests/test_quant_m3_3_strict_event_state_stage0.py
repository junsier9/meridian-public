from __future__ import annotations

import pandas as pd

from scripts.quant_research.evaluate_m3_3_strict_event_state_stage0 import _strict_boundary_rows


def test_strict_boundary_rows_prefers_eligible_tail_candidate() -> None:
    frame = pd.DataFrame(
        {
            "timestamp_ms": [1] * 8,
            "date_utc": ["2026-01-02"] * 8,
            "subject": ["A", "B", "C", "D", "E", "F", "G", "H"],
            "liquidity_bucket": ["top_liquidity"] * 8,
            "forward_1d_log_return": [0.0] * 8,
            "forward_10d_log_return": [0.0] * 8,
            "m3_3_event_state_hype_pressure_v1": [0.0] * 8,
            "m3_3_event_state_confirmed_quality_v1": [0.0] * 8,
            "m3_3_event_state_short_quality_v1": [0.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0],
            "m3_3_event_state_noise_ratio_v1": [0.0] * 8,
        }
    )

    parent, selected, entered, exited, meta = _strict_boundary_rows(
        frame,
        min_quality=1.0,
        max_noise_ratio=0.0,
        require_no_hype=True,
        target_horizon_bars=10,
        pool_size=8,
        short_count=3,
    )

    assert set(parent["subject"]) == {"F", "G", "H"}
    assert set(selected["subject"]) == {"E", "F", "G"}
    assert set(entered["subject"]) == {"E"}
    assert set(exited["subject"]) == {"H"}
    assert float(meta.loc[0, "changed_timestamp_fraction"]) == 1.0
