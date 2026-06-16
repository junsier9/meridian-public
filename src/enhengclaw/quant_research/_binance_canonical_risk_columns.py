from __future__ import annotations


BINANCE_RISK_BRAKE_COLUMNS: tuple[str, ...] = (
    "binance_short_squeeze_veto_multiplier",
    "binance_high_vol_rebound_short_multiplier",
    "binance_risk_brake_short_multiplier",
    "binance_short_squeeze_veto_flag",
    "binance_high_vol_rebound_flag",
    "binance_high_vol_rebound_severe_flag",
    "binance_market_realized_vol_5_median",
    "binance_market_realized_vol_5_threshold",
    "binance_market_momentum_20_median",
    "binance_market_positive_momentum_share_20",
    "binance_market_close_to_high_share_5",
)
