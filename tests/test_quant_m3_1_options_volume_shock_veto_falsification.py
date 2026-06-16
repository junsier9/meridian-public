from __future__ import annotations

import pandas as pd

from scripts.quant_research.evaluate_m3_1_options_volume_shock_veto_falsification import (
    _date_level,
    _decision,
    _edge_summary,
    _liquidity_bucket_test,
    _passes_edge_contract,
)


def test_options_volume_veto_edge_is_active_minus_inactive_short_return() -> None:
    date_level = pd.DataFrame(
        {
            "date_utc": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "r8_high_option_volume_shock_flag": [True, True, False],
            "forward_10d_log_return": [0.04, 0.02, -0.01],
        }
    )

    summary = _edge_summary(
        date_level,
        flag_column="r8_high_option_volume_shock_flag",
        target_horizon_bars=10,
    )

    assert summary["active_date_count"] == 2
    assert summary["inactive_date_count"] == 1
    assert summary["veto_short_edge_active_minus_inactive"] == 0.04
    assert _passes_edge_contract(
        summary,
        min_edge=0.005,
        min_active_date_count=2,
        min_active_date_fraction=0.10,
        max_active_date_fraction=0.80,
    )


def test_options_volume_veto_date_level_averages_parent_short_basket() -> None:
    rows = pd.DataFrame(
        {
            "date_utc": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-02"]),
            "r8_high_option_volume_shock_flag": [True, True, False],
            "forward_10d_log_return": [0.02, 0.06, -0.01],
            "forward_1d_log_return": [0.0, 0.0, 0.0],
        }
    )

    out = _date_level(
        rows,
        flag_column="r8_high_option_volume_shock_flag",
        target_horizon_bars=10,
    )

    assert out["forward_10d_log_return"].tolist() == [0.04, -0.01]
    assert out["r8_high_option_volume_shock_flag"].tolist() == [True, False]


def test_options_volume_veto_liquidity_bucket_blocks_negative_eligible_bucket() -> None:
    rows = pd.DataFrame(
        {
            "date_utc": pd.to_datetime(
                ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"] * 2
            ),
            "liquidity_bucket": ["top"] * 4 + ["tail"] * 4,
            "subject": ["A"] * 4 + ["B"] * 4,
            "r8_high_option_volume_shock_flag": [True, True, False, False] * 2,
            "forward_10d_log_return": [0.04, 0.03, -0.01, -0.02, -0.03, -0.02, 0.01, 0.02],
            "forward_1d_log_return": [0.0] * 8,
        }
    )

    result = _liquidity_bucket_test(
        rows,
        flag_column="r8_high_option_volume_shock_flag",
        target_horizon_bars=10,
        min_edge=0.005,
        min_active_dates=2,
        min_inactive_dates=2,
    )

    assert result["passed"] is False
    assert result["eligible_bucket_count"] == 2
    assert result["positive_eligible_bucket_count"] == 1
    assert result["min_eligible_bucket_edge"] < 0


def test_options_volume_veto_decision_keeps_manifest_blocked_after_strict_clear() -> None:
    decision = _decision({"status": "cleared", "blocker_codes": []}, label="toy_flag")

    assert decision["status"] == "cleared"
    assert decision["alpha_rerun_allowed"] is True
    assert decision["manifest_ab_allowed"] is False
    assert decision["strict_cleared_variants"] == ["toy_flag"]
