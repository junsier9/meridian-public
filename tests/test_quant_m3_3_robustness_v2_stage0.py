from __future__ import annotations

import pandas as pd

from scripts.quant_research.evaluate_m3_3_robustness_v2_stage0 import (
    VariantSpec,
    _select_rows,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp_ms": [1] * 8,
            "date_utc": ["2026-01-02"] * 8,
            "subject": ["A", "B", "C", "D", "E", "F", "G", "H"],
            "liquidity_bucket": [
                "top_liquidity",
                "top_liquidity",
                "top_liquidity",
                "top_liquidity",
                "mid_liquidity",
                "top_liquidity",
                "top_liquidity",
                "top_liquidity",
            ],
            "forward_1d_log_return": [0.0] * 8,
            "forward_10d_log_return": [0.0] * 8,
            "m3_3_event_state_hype_pressure_v1": [0.0] * 8,
            "m3_3_event_state_confirmed_quality_v1": [0.0] * 8,
            "m3_3_event_state_short_quality_v1": [0.0, 0.0, 0.0, 2.5, 3.0, 0.0, 0.0, 0.0],
            "m3_3_event_state_noise_ratio_v1": [0.0] * 8,
        }
    )


def test_robustness_v2_max_replacements_caps_entered_rows() -> None:
    _, selected, entered, exited, meta = _select_rows(
        _frame(),
        spec=VariantSpec(label="one", min_quality=1.0, max_replacements=1),
        target_horizon_bars=10,
    )

    assert len(entered) == 1
    assert len(exited) == 1
    assert len(selected) == 3
    assert float(meta["changed_timestamp_fraction"]) == 1.0


def test_robustness_v2_liquidity_filter_blocks_mid_liquidity_candidate() -> None:
    _, _, entered, _, _ = _select_rows(
        _frame(),
        spec=VariantSpec(
            label="top_only",
            min_quality=1.0,
            max_replacements=2,
            eligible_liquidity_buckets=("top_liquidity",),
        ),
        target_horizon_bars=10,
    )

    assert set(entered["subject"]) == {"D"}
