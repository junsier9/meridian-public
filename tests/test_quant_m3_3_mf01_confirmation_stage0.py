from __future__ import annotations

import pandas as pd

from scripts.quant_research.evaluate_m3_3_mf01_confirmation_stage0 import (
    ConfirmationSpec,
    _select_rows,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp_ms": [1] * 8,
            "date_utc": ["2026-01-02"] * 8,
            "subject": ["A", "B", "C", "D", "E", "F", "G", "H"],
            "liquidity_bucket": ["top_liquidity"] * 8,
            "forward_1d_log_return": [0.0] * 8,
            "forward_10d_log_return": [0.0] * 8,
            "m3_3_event_state_hype_pressure_v1": [0.0] * 8,
            "m3_3_event_state_confirmed_quality_v1": [0.0] * 8,
            "m3_3_event_state_short_quality_v1": [0.0, 0.0, 0.0, 3.0, 2.5, 0.0, 0.0, 0.0],
            "m3_3_event_state_noise_ratio_v1": [0.0] * 8,
            "boundary_fragile_orderbook_flag": [False, False, False, True, False, False, False, False],
            "pump_bid_replenishment_failure_flag": [False] * 8,
            "boundary_fragile_orderbook_score": [0.0, 0.0, 0.0, -2.0, 0.0, 0.0, 0.0, 0.0],
            "pump_bid_replenishment_failure_score": [0.0] * 8,
            "mf01_short_boundary_combo_score": [0.0, 0.0, 0.0, -2.0, 0.0, 0.0, 0.0, 0.0],
        }
    )


def test_mf01_confirmation_allows_only_mechanically_confirmed_event_candidate() -> None:
    _, selected, entered, exited, meta = _select_rows(
        _frame(),
        spec=ConfirmationSpec(label="confirmed", confirmation_mode="mf01_any_flag", max_replacements=1),
        target_horizon_bars=10,
    )

    assert set(selected["subject"]) == {"D", "F", "G"}
    assert set(entered["subject"]) == {"D"}
    assert set(exited["subject"]) == {"H"}
    assert float(meta["changed_timestamp_fraction"]) == 1.0


def test_mf01_confirmation_blocks_unconfirmed_higher_quality_candidate() -> None:
    _, _, entered, _, _ = _select_rows(
        _frame(),
        spec=ConfirmationSpec(label="boundary", confirmation_mode="mf01_boundary_flag", max_replacements=1),
        target_horizon_bars=10,
    )

    assert set(entered["subject"]) == {"D"}
