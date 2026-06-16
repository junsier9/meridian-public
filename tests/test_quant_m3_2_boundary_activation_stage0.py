from __future__ import annotations

import pandas as pd
import pytest

from scripts.quant_research.evaluate_m3_2_boundary_activation_stage0 import (
    BoundarySpec,
    _apply_boundary_rule,
    _as_bool,
    _compare,
    _portfolio_from_sides,
    _summarize_portfolio,
)


def _toy_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp_ms": [1, 1, 1, 1, 1],
            "date_utc": ["2026-01-01"] * 5,
            "subject": ["A", "B", "C", "D", "E"],
            "liquidity_bucket": ["mid_liquidity"] * 5,
            "parent_score": [0.9, 0.8, 0.7, 0.6, 0.5],
            "m3_2_panel_ready": [True] * 5,
            "m3_2_stable_supply_impulse_state": [1.0] * 5,
            "lead_lag_beta_btc": [0.0, 0.1, 3.0, 0.2, 0.0],
            "relative_strength_20": [0.0, 0.1, 3.0, 0.2, 0.0],
            "idiosyncratic_share": [0.1, 0.1, 0.1, 0.1, 0.1],
            "realized_volatility_20": [0.1, 0.1, 0.1, 0.1, 0.1],
            "forward_1d_log_return": [0.0, 0.0, 0.0, 0.0, 0.0],
            "forward_10d_log_return": [0.03, -0.01, 0.05, -0.02, -0.03],
        }
    )


def test_m3_2_bool_parser_handles_string_flags() -> None:
    flags = _as_bool(pd.Series(["true", "False", "1", "0", "yes", "no", None]))

    assert flags.tolist() == [True, False, True, False, True, False, False]


def test_m3_2_boundary_rule_replaces_weak_long_with_high_exposure_candidate() -> None:
    spec = BoundarySpec(
        label="toy",
        side="long",
        action="replace_high",
        state_column="m3_2_stable_supply_impulse_state",
        state_threshold=0.75,
        exposure_mode="high_beta_rs",
        interpretation="toy",
        pool_size=4,
        side_count=2,
    )

    sides, change = _apply_boundary_rule(_toy_frame(), spec)
    longs = sides[sides["side"].eq("long")]["subject"].tolist()

    assert set(longs) == {"A", "C"}
    assert change["active_timestamp_count"] == 1
    assert change["long_active_changed_timestamp_fraction"] == 1.0
    assert change["short_active_changed_timestamp_fraction"] == 0.0


def test_m3_2_compare_requires_active_window_edge_and_transmission() -> None:
    spec = BoundarySpec(
        label="toy",
        side="long",
        action="replace_high",
        state_column="m3_2_stable_supply_impulse_state",
        state_threshold=0.75,
        exposure_mode="high_beta_rs",
        interpretation="toy",
        pool_size=4,
        side_count=2,
    )
    frame = pd.concat(
        [
            _toy_frame().assign(timestamp_ms=timestamp, date_utc=f"2026-01-{timestamp:02d}")
            for timestamp in range(1, 11)
        ],
        ignore_index=True,
    )
    parent_sides, _ = _apply_boundary_rule(frame, spec, apply_replacement=False)
    candidate_sides, changes = _apply_boundary_rule(frame, spec)
    parent = _summarize_portfolio(_portfolio_from_sides(parent_sides, target_horizon_bars=10))
    candidate = _summarize_portfolio(_portfolio_from_sides(candidate_sides, target_horizon_bars=10))

    comparison = _compare(candidate, parent, changes)

    assert comparison["delta_active_long_short_mean"] == pytest.approx(0.03)
    assert comparison["verdict"] == "stage0_positive"
