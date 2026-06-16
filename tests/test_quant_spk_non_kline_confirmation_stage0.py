from __future__ import annotations

import pandas as pd

from scripts.quant_research.evaluate_spk_non_kline_confirmation_stage0 import (
    ConfirmationSpec,
    _add_confirmation_columns,
    _verdict,
)


def test_spk_non_kline_confirmation_respects_ready_gate() -> None:
    frame = pd.DataFrame(
        {
            "timestamp_ms": [1, 1, 1, 2, 2, 2],
            "stablecoin_flow_signal_ready": [True, True, False, False, False, False],
            "stablecoin_exchange_absorption_score_v1": [0.0, 100.0, 5.0, 100.0, 101.0, 102.0],
        }
    )
    spec = ConfirmationSpec(
        label="toy",
        description="toy",
        signed_columns=(("stablecoin_exchange_absorption_score_v1", 1.0),),
        require_ready_column="stablecoin_flow_signal_ready",
    )

    actual = _add_confirmation_columns(frame, spec=spec, threshold=0.90)

    assert actual["toy_flag"].tolist() == [False, True, False, False, False, False]
    assert actual["toy_candidate_veto"].tolist() == [True, False, True, True, True, True]


def test_spk_non_kline_verdict_requires_beating_spk() -> None:
    verdict = _verdict(
        variant_vs_parent={
            "total_replacements": 100,
            "entered_next_10d_mean": -0.01,
            "exited_next_10d_mean": 0.01,
            "entered_next_1d_squeeze_gt_5pct_fraction": 0.05,
        },
        spk_vs_parent={
            "total_replacements": 500,
            "entered_next_10d_mean": -0.02,
            "entered_next_1d_squeeze_gt_5pct_fraction": 0.04,
        },
        variant_vs_spk={"total_replacements": 50},
        short_basket_summary={
            "spk": {"next_horizon_mean": -0.02},
            "variant": {"next_horizon_mean": -0.01},
        },
        target_horizon_bars=10,
    )

    assert verdict["label"] == "stage0_watch"
    assert verdict["checks"]["variant_entered_beats_spk_entered_h10d"] is False
    assert verdict["checks"]["variant_short_basket_beats_spk_h10d"] is False
