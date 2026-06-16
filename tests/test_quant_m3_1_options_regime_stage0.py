from __future__ import annotations

import pandas as pd

from scripts.quant_research.audit_m3_1_options_regime_stage0 import (
    _build_options_panel,
    _decision,
    _exchange_history_payload_to_daily_frame,
)


def _history_payload(values_a: list[float], values_b: list[float]) -> dict:
    return {
        "code": "0",
        "data": {
            "time_list": [1609459200000, 1609545600000, 1609632000000],
            "price_list": [100.0, 101.0, 102.0],
            "data_map": {
                "Deribit": values_a,
                "OKX": values_b,
            },
        },
    }


def test_exchange_history_payload_to_daily_frame_sums_exchange_total() -> None:
    frame = _exchange_history_payload_to_daily_frame(
        _history_payload([1.0, 2.0, 3.0], [10.0, 20.0, 30.0]),
        symbol="BTC",
        metric="volume",
    )

    assert frame["btc_option_volume_usd_deribit"].tolist() == [1.0, 2.0, 3.0]
    assert frame["btc_option_volume_usd_okx"].tolist() == [10.0, 20.0, 30.0]
    assert frame["btc_option_volume_usd_total"].tolist() == [11.0, 22.0, 33.0]
    assert frame["date_utc"].dt.strftime("%Y-%m-%d").tolist() == [
        "2021-01-01",
        "2021-01-02",
        "2021-01-03",
    ]


def test_build_options_panel_merges_volume_oi_and_ratio() -> None:
    payloads = {
        "btc_option_oi_history": _history_payload([100.0, 110.0, 120.0], [5.0, 5.0, 5.0]),
        "eth_option_oi_history": _history_payload([200.0, 210.0, 220.0], [6.0, 6.0, 6.0]),
        "btc_option_volume_history": _history_payload([1.0, 2.0, 3.0], [10.0, 20.0, 30.0]),
        "eth_option_volume_history": _history_payload([4.0, 5.0, 6.0], [40.0, 50.0, 60.0]),
        "btc_option_max_pain_deribit": {"code": "0", "data": [{"date": "260508", "max_pain_price": "79000"}]},
        "eth_option_max_pain_deribit": {"code": "0", "data": [{"date": "260508", "max_pain_price": "2500"}]},
        "option_vs_futures_oi_ratio": {
            "code": "0",
            "data": [
                {
                    "timestamp": 1609459200000,
                    "btc_option_vs_futures_radio": 45.0,
                    "eth_option_vs_futures_radio": 25.0,
                }
            ],
        },
    }

    panel, meta = _build_options_panel(
        payloads,
        volume_z_threshold=1.5,
        ratio_z_threshold=1.0,
    )

    assert len(panel) == 3
    assert panel.loc[0, "btc_option_volume_usd_total"] == 11.0
    assert panel.loc[0, "eth_option_oi_usd_total"] == 206.0
    assert panel.loc[0, "btc_option_vs_futures_oi_ratio"] == 45.0
    assert meta["max_pain"]["btc"]["expiry_count"] == 1


def test_decision_blocks_market_level_and_missing_oi_history() -> None:
    decision = _decision(
        panel_summary={
            "parent_btc_option_volume_usd_total_coverage": 1.0,
            "parent_eth_option_volume_usd_total_coverage": 1.0,
            "parent_btc_option_vs_futures_oi_ratio_coverage": 1.0,
            "parent_eth_option_vs_futures_oi_ratio_coverage": 1.0,
            "parent_btc_option_oi_usd_total_coverage": 0.01,
            "parent_eth_option_oi_usd_total_coverage": 0.01,
        },
        conditionals={"variants": [{"label": "r8_any_options_stress_flag", "stage0_pass": False}]},
        min_feature_coverage=0.90,
        min_oi_coverage=0.80,
    )

    assert decision["alpha_rerun_allowed"] is False
    assert decision["manifest_ab_allowed"] is False
    assert "btc_option_oi_usd_total_history_not_backfilled" in decision["blocker_codes"]
    assert "market_level_only_not_cross_sectional_rank_factor" in decision["blocker_codes"]
