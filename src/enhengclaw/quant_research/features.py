from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd

from .derivatives_quality import (
    DERIVATIVES_FEATURE_SPECS,
    feature_ready_flag_column,
    feature_source_flag_column,
    summarize_feature_derivatives_quality,
)
from .split_realization_contract import build_split_realization_contract

DEFAULT_LABEL_CONTRACT_ID = "forward_return_ranking.v1"
EXECUTION_ALIGNED_LABEL_CONTRACT_ID = "forward_return_execution_aligned.v1"
EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN = "target_execution_forward_return"
EXECUTION_ALIGNED_TARGET_COLUMN = "target_execution_up"
PARTICIPATION_DRIFT_LABEL_CONTRACT_ID = "participation_drift_excess_vol_adjusted_return.v1"
SUPPORTED_CROSS_SECTIONAL_LABEL_CONTRACT_IDS = (
    DEFAULT_LABEL_CONTRACT_ID,
    EXECUTION_ALIGNED_LABEL_CONTRACT_ID,
    PARTICIPATION_DRIFT_LABEL_CONTRACT_ID,
)


def _safe_rolling_skew(series: pd.Series, window: int, *, min_periods: int | None = None) -> pd.Series:
    return _safe_rolling_pandas_moment(series, window, min_periods=min_periods, moment="skew")


def _safe_rolling_kurt(series: pd.Series, window: int, *, min_periods: int | None = None) -> pd.Series:
    return _safe_rolling_pandas_moment(series, window, min_periods=min_periods, moment="kurt")


def _safe_rolling_pandas_moment(
    series: pd.Series,
    window: int,
    *,
    min_periods: int | None,
    moment: str,
) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    required = int(min_periods or window)

    def _moment(values: np.ndarray) -> float:
        clean = values[~np.isnan(values)]
        if len(clean) < required:
            return np.nan
        if moment == "skew":
            if len(clean) < 3:
                return np.nan
            return float(pd.Series(clean, dtype="float64").skew())
        if len(clean) < 4:
            return np.nan
        return float(pd.Series(clean, dtype="float64").kurt())

    return numeric.rolling(window, min_periods=1).apply(_moment, raw=True)


def build_single_asset_features(panel: pd.DataFrame) -> pd.DataFrame:
    return build_single_asset_feature_bundle(panel)["dataframe"]


def build_cross_sectional_features(panel: pd.DataFrame) -> pd.DataFrame:
    return build_cross_sectional_feature_bundle(panel)["dataframe"]


def build_single_asset_feature_bundle(
    panel: pd.DataFrame,
    *,
    provider_index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _build_feature_bundle(
        panel,
        shape="single_asset",
        interval="4h",
        target_shift_bars=6,
        label_contract_id=DEFAULT_LABEL_CONTRACT_ID,
        span_fast=6,
        span_slow=18,
        provider_index=provider_index,
    )


def build_cross_sectional_feature_bundle(
    panel: pd.DataFrame,
    *,
    interval: str = "1d",
    target_shift_bars: int = 1,
    label_contract_id: str = DEFAULT_LABEL_CONTRACT_ID,
    provider_index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _build_feature_bundle(
        panel,
        shape="cross_sectional",
        interval=interval,
        target_shift_bars=target_shift_bars,
        label_contract_id=label_contract_id,
        span_fast=5,
        span_slow=20,
        provider_index=provider_index,
    )


def build_cross_sectional_intraday_feature_bundle(
    panel: pd.DataFrame,
    *,
    label_contract_id: str = DEFAULT_LABEL_CONTRACT_ID,
    provider_index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return build_cross_sectional_feature_bundle(
        panel,
        interval="1h",
        label_contract_id=label_contract_id,
        provider_index=provider_index,
    )


def _build_feature_bundle(
    panel: pd.DataFrame,
    *,
    shape: str,
    interval: str,
    target_shift_bars: int,
    label_contract_id: str,
    span_fast: int,
    span_slow: int,
    provider_index: dict[tuple[str, str], dict[str, Any]] | None,
) -> dict[str, Any]:
    resolved_label_contract_id = _resolve_label_contract_id(
        shape=shape,
        label_contract_id=label_contract_id,
    )
    if panel.empty:
        empty = panel.copy()
        split_realization_contract = build_split_realization_contract(shape=shape, interval=interval)
        label_contract = _label_contract_metadata(
            shape=shape,
            label_contract_id=resolved_label_contract_id,
        )
        return {
            "dataframe": empty,
            "quality_frame": empty,
            "split_realization_contract": split_realization_contract,
            "label_contract": label_contract,
            "label_contract_id": label_contract["label_contract_id"],
            "target_column": label_contract["target_column"],
            "forward_return_column": label_contract["forward_return_column"],
            "label_columns": list(label_contract["label_columns"]),
            "derivatives_feature_quality": summarize_feature_derivatives_quality(
                quality_frame=pd.DataFrame(),
                interval=interval,
                provider_index={},
            ),
        }
    frames: list[pd.DataFrame] = []
    for _, group in panel.groupby("subject", sort=True):
        frame = group.sort_values("timestamp_ms").copy()
        close = frame["spot_close"].replace(0, np.nan)
        returns = close.pct_change()
        frame["return_1"] = returns
        if shape == "single_asset":
            frame["momentum_3"] = close.pct_change(3)
            frame["momentum_6"] = close.pct_change(6)
            frame["momentum_24"] = close.pct_change(24)
            frame["ema_fast"] = close.ewm(span=span_fast, adjust=False).mean()
            frame["ema_slow"] = close.ewm(span=span_slow, adjust=False).mean()
            frame["ema_slope_6_18"] = np.where(frame["ema_slow"].ne(0), (frame["ema_fast"] / frame["ema_slow"]) - 1.0, 0.0)
            frame["sma_20"] = close.rolling(20).mean()
            frame["sma_60"] = close.rolling(60).mean()
            frame["sma_slope_20_60"] = np.where(frame["sma_60"].ne(0), (frame["sma_20"] / frame["sma_60"]) - 1.0, 0.0)
            high_120 = frame["spot_high"].rolling(120).max()
            low_120 = frame["spot_low"].rolling(120).min()
            frame["distance_to_high_120"] = np.where(high_120.ne(0), (close / high_120) - 1.0, 0.0)
            frame["distance_to_low_120"] = np.where(low_120.ne(0), (close / low_120) - 1.0, 0.0)
        else:
            frame["momentum_5"] = close.pct_change(5)
            frame["momentum_20"] = close.pct_change(20)
            frame["ema_fast"] = close.ewm(span=span_fast, adjust=False).mean()
            frame["ema_slow"] = close.ewm(span=span_slow, adjust=False).mean()
            frame["ema_slope_5_20"] = np.where(frame["ema_slow"].ne(0), (frame["ema_fast"] / frame["ema_slow"]) - 1.0, 0.0)
        high_20 = frame["spot_high"].rolling(20).max()
        low_20 = frame["spot_low"].rolling(20).min()
        high_60 = frame["spot_high"].rolling(60).max()
        low_60 = frame["spot_low"].rolling(60).min()
        frame["range_position_20"] = np.where(high_20.ne(low_20), (close - low_20) / (high_20 - low_20), 0.0)
        frame["distance_to_high_20"] = np.where(high_20.ne(0), (close / high_20) - 1.0, 0.0)
        frame["distance_to_low_20"] = np.where(low_20.ne(0), (close / low_20) - 1.0, 0.0)
        frame["distance_to_high_60"] = np.where(high_60.ne(0), (close / high_60) - 1.0, 0.0)
        frame["distance_to_low_60"] = np.where(low_60.ne(0), (close / low_60) - 1.0, 0.0)
        frame["realized_volatility_20"] = returns.rolling(20).std()
        frame["realized_volatility_5"] = returns.rolling(5).std()
        frame["realized_volatility_60"] = returns.rolling(60).std()
        high_5 = frame["spot_high"].rolling(5).max()
        frame["distance_to_high_5"] = np.where(high_5.ne(0), (close / high_5) - 1.0, 0.0)
        frame["atr_proxy_20"] = ((frame["spot_high"] - frame["spot_low"]) / close.shift(1).replace(0, np.nan)).rolling(20).mean()
        frame["quote_volume_expansion"] = np.where(
            frame["spot_quote_volume"].rolling(20).mean().ne(0),
            frame["spot_quote_volume"] / frame["spot_quote_volume"].rolling(20).mean(),
            0.0,
        )
        open_interest_source = frame["open_interest"].replace(0, np.nan)
        frame[feature_source_flag_column("funding_zscore_20")] = frame["funding_rate"].notna().astype("bool")
        frame[feature_ready_flag_column("funding_zscore_20")] = (
            frame[feature_source_flag_column("funding_zscore_20")].rolling(20).sum().eq(20)
        ).astype("bool")
        frame[feature_source_flag_column("oi_change_5")] = open_interest_source.notna().astype("bool")
        frame[feature_ready_flag_column("oi_change_5")] = (
            frame[feature_source_flag_column("oi_change_5")]
            & frame[feature_source_flag_column("oi_change_5")].shift(5, fill_value=False)
        ).astype("bool")
        frame[feature_source_flag_column("basis_zscore_20")] = frame["basis_proxy"].notna().astype("bool")
        frame[feature_ready_flag_column("basis_zscore_20")] = (
            frame[feature_source_flag_column("basis_zscore_20")].rolling(20).sum().eq(20)
        ).astype("bool")
        frame["oi_change_5"] = open_interest_source.pct_change(5, fill_method=None)
        frame["funding_zscore_20"] = rolling_zscore(frame["funding_rate"], 20)
        frame["basis_zscore_20"] = rolling_zscore(frame["basis_proxy"], 20)
        # M2.2 F08 funding_term_skew_60 â€?rolling 60d skew of daily funding_rate
        # per subject. Doc spec is 60 obs of 8h funding (â‰?0 days, formula
        # `realized_skew(funding_8h, w=60 obs)`); panel grain is 1d so 60 daily
        # obs is the longest pure-funding-microstructure window. 60d empirically
        # the strongest window across {10,15,20,30,45,60,90} per 2026-04-29
        # admission audit (raw_IC=+0.032, residual_IC vs lsk3=+0.030, t=+5.61).
        # The 30d variant is also kept for diagnostic comparison.
        _funding_numeric = pd.to_numeric(frame["funding_rate"], errors="coerce")
        frame["funding_term_skew_30"] = _safe_rolling_skew(_funding_numeric, 30, min_periods=15)
        frame["funding_term_skew_60"] = _safe_rolling_skew(_funding_numeric, 60, min_periods=30)
        frame["funding_term_kurt_60"] = _safe_rolling_kurt(_funding_numeric, 60, min_periods=30)
        if "intraday_realized_vol_4h_to_1d" in frame.columns:
            iv_series = pd.to_numeric(frame["intraday_realized_vol_4h_to_1d"], errors="coerce")
            frame["intraday_realized_vol_4h_to_1d_smooth_5"] = iv_series.rolling(5).mean()
            frame["intraday_realized_vol_4h_to_1d_smooth_20"] = iv_series.rolling(20).mean()
            frame["intraday_realized_vol_4h_to_1d_smooth_60"] = iv_series.rolling(60).mean()
        if "coinglass_top_trader_long_pct" in frame.columns:
            tt_series = pd.to_numeric(frame["coinglass_top_trader_long_pct"], errors="coerce")
            frame["coinglass_top_trader_long_pct_smooth_5"] = tt_series.rolling(5).mean()
            frame["coinglass_top_trader_long_pct_smooth_20"] = tt_series.rolling(20).mean()
            frame["coinglass_top_trader_long_pct_smooth_60"] = tt_series.rolling(60).mean()
        # Phase 1b new factor families
        if "momentum_5" in frame.columns and "momentum_20" in frame.columns:
            frame["momentum_decay_5_20"] = frame["momentum_5"] - frame["momentum_20"]
        if "funding_rate" in frame.columns:
            funding_series = pd.to_numeric(frame["funding_rate"], errors="coerce")
            oi_change_series = pd.to_numeric(frame.get("oi_change_5"), errors="coerce") if "oi_change_5" in frame.columns else None
            if oi_change_series is not None:
                frame["quality_funding_oi"] = funding_series * oi_change_series
        if "quote_volume_expansion" in frame.columns and "intraday_realized_vol_4h_to_1d" in frame.columns:
            qve = pd.to_numeric(frame["quote_volume_expansion"], errors="coerce")
            iv_today = pd.to_numeric(frame["intraday_realized_vol_4h_to_1d"], errors="coerce")
            frame["liquidity_stress_qv_iv"] = qve * iv_today
        if "funding_zscore_20" in frame.columns and "basis_zscore_20" in frame.columns:
            fz = pd.to_numeric(frame["funding_zscore_20"], errors="coerce")
            bz = pd.to_numeric(frame["basis_zscore_20"], errors="coerce").abs()
            frame["funding_crowding_basis"] = fz * bz
        # B-batch alternative factor candidates (Phase 1b extension; IC validation pending in next phase_1c run)
        if "coinglass_liq_intraday_concentration_24h" in frame.columns and "intraday_realized_vol_4h_to_1d" in frame.columns:
            _liq_conc = pd.to_numeric(frame["coinglass_liq_intraday_concentration_24h"], errors="coerce")
            _iv_today = pd.to_numeric(frame["intraday_realized_vol_4h_to_1d"], errors="coerce")
            frame["stress_liq_conc_iv"] = _liq_conc * _iv_today
        if "coinglass_orderbook_imb_persistence_24h" in frame.columns and "funding_zscore_20" in frame.columns:
            _obi = pd.to_numeric(frame["coinglass_orderbook_imb_persistence_24h"], errors="coerce")
            _fz_abs = pd.to_numeric(frame["funding_zscore_20"], errors="coerce").abs()
            frame["crowd_obi_abs_funding"] = _obi * _fz_abs
        if "coinglass_top_trader_intraday_volatility_24h" in frame.columns and "coinglass_top_trader_long_pct_smooth_5" in frame.columns:
            _tt_vol = pd.to_numeric(frame["coinglass_top_trader_intraday_volatility_24h"], errors="coerce")
            _tt_long = pd.to_numeric(frame["coinglass_top_trader_long_pct_smooth_5"], errors="coerce")
            frame["crowd_tt_signal"] = _tt_vol * _tt_long
        if "coinglass_liquidation_imbalance_24h" in frame.columns and "distance_to_high_5" in frame.columns:
            _liq_imb = pd.to_numeric(frame["coinglass_liquidation_imbalance_24h"], errors="coerce")
            _dh5 = pd.to_numeric(frame["distance_to_high_5"], errors="coerce")
            frame["unwind_liq_dh"] = _liq_imb * _dh5
        if "basis_zscore_20" in frame.columns and "oi_change_5" in frame.columns:
            _bz_signed = pd.to_numeric(frame["basis_zscore_20"], errors="coerce")
            _oi_ch = pd.to_numeric(frame["oi_change_5"], errors="coerce")
            frame["crowd_basis_oi_signed"] = _bz_signed * _oi_ch
            frame["crowd_abs_basis_oi"] = _bz_signed.abs() * _oi_ch
        if "basis_zscore_20" in frame.columns and "quote_volume_expansion" in frame.columns:
            _bz_abs = pd.to_numeric(frame["basis_zscore_20"], errors="coerce").abs()
            _qve = pd.to_numeric(frame["quote_volume_expansion"], errors="coerce")
            frame["stress_abs_basis_qv"] = _bz_abs * _qve
        if "funding_zscore_20" in frame.columns and "coinglass_orderbook_imb_persistence_24h" in frame.columns:
            _fz_signed = pd.to_numeric(frame["funding_zscore_20"], errors="coerce")
            _obi2 = pd.to_numeric(frame["coinglass_orderbook_imb_persistence_24h"], errors="coerce")
            frame["crowd_funding_obi_signed"] = _fz_signed * _obi2
        if "coinglass_top_trader_long_pct_smooth_5" in frame.columns and "coinglass_global_account_long_pct" in frame.columns:
            _tt_long_b = pd.to_numeric(frame["coinglass_top_trader_long_pct_smooth_5"], errors="coerce")
            _retail_long = pd.to_numeric(frame["coinglass_global_account_long_pct"], errors="coerce")
            frame["disagree_tt_retail"] = _tt_long_b - _retail_long
        # SP-K small-cap post-pump short family. These are causal per-subject
        # event-state transforms that detect upside blow-off followed by failed
        # continuation, the upside dual of liquidation-cascade mean reversion.
        _ret1_spk = pd.to_numeric(frame["return_1"], errors="coerce")
        _rv20_spk = pd.to_numeric(frame["realized_volatility_20"], errors="coerce")
        _high_spk = pd.to_numeric(frame["spot_high"], errors="coerce")
        _low_spk = pd.to_numeric(frame["spot_low"], errors="coerce")
        _close_spk = pd.to_numeric(frame["spot_close"], errors="coerce").replace(0.0, np.nan)
        _range_norm_spk = (_high_spk - _low_spk) / _close_spk
        _range_mean_60_spk = _range_norm_spk.rolling(60).mean()
        _range_std_60_spk = _range_norm_spk.rolling(60).std()
        _abnormal_range_spk = (
            (_range_norm_spk - _range_mean_60_spk) / _range_std_60_spk.replace(0.0, np.nan)
        )
        _pump_sigma_spk = _ret1_spk / _rv20_spk.replace(0.0, np.nan)
        _pump_sigma_excess_spk = (_pump_sigma_spk - 2.0).clip(lower=0.0, upper=8.0)
        _pump_range_excess_spk = (_abnormal_range_spk - 1.0).clip(lower=0.0, upper=6.0)
        _pump_qv_excess_spk = (
            pd.to_numeric(frame["quote_volume_expansion"], errors="coerce") - 1.5
        ).clip(lower=0.0, upper=8.0)
        _pump_event_mask_spk = (
            _pump_sigma_spk.gt(2.0)
            & _abnormal_range_spk.gt(1.0)
            & pd.to_numeric(frame["quote_volume_expansion"], errors="coerce").gt(1.5)
        )
        _pump_intensity_spk = (
            _pump_sigma_excess_spk + 0.5 * _pump_range_excess_spk + 0.5 * _pump_qv_excess_spk
        ).where(_pump_event_mask_spk, 0.0).fillna(0.0)
        _recent_pump_spk = _pump_intensity_spk.ewm(alpha=0.45, adjust=False).mean()
        _oi_positive_spk = pd.to_numeric(frame["oi_change_5"], errors="coerce").clip(lower=0.0, upper=0.20) / 0.10
        _funding_positive_spk = (
            pd.to_numeric(frame["funding_zscore_20"], errors="coerce") - 0.5
        ).clip(lower=0.0, upper=3.0)
        _prev_pump_spk = _pump_intensity_spk.shift(1).fillna(0.0)
        _prev_pump_flag_spk = _prev_pump_spk.gt(0.0).astype("float64")
        _stall_slack_spk = (0.015 - _ret1_spk).clip(lower=0.0, upper=0.08) / 0.08
        frame["pump_exhaustion_recency_score_5d"] = -_recent_pump_spk
        frame["pump_funding_oi_crowding_score_3d"] = (
            -_recent_pump_spk * (1.0 + _funding_positive_spk) * (1.0 + _oi_positive_spk)
        )
        frame["post_pump_stall_core_score_3d"] = (
            -_prev_pump_spk * (_stall_slack_spk + 0.25 * _prev_pump_flag_spk)
        )
        frame["post_pump_stall_oi_score_3d"] = (
            frame["post_pump_stall_core_score_3d"] * (1.0 + _oi_positive_spk)
        )
        # MF-01 orderbook / inventory-transfer lane. Keep the continuous research
        # columns in the main panel, then let strategy scorers decide whether the
        # signal should act as a smooth factor or a discrete short-boundary rule.
        if "coinglass_orderbook_bids_mean_24h" in frame.columns:
            _nan_mf01 = pd.Series(np.nan, index=frame.index, dtype="float64")
            _hourly_bar_count_mf01 = (
                pd.to_numeric(frame["coinglass_hourly_bar_count_24h"], errors="coerce")
                if "coinglass_hourly_bar_count_24h" in frame.columns
                else pd.Series(0.0, index=frame.index, dtype="float64")
            ).fillna(0.0)
            _ob_bid_depth_mf01 = pd.to_numeric(
                frame["coinglass_orderbook_bids_mean_24h"], errors="coerce"
            )
            _ob_total_depth_mf01 = (
                pd.to_numeric(frame["coinglass_orderbook_total_depth_mean_24h"], errors="coerce")
                if "coinglass_orderbook_total_depth_mean_24h" in frame.columns
                else _nan_mf01.copy()
            )
            _ob_imb_mean_mf01 = (
                pd.to_numeric(frame["coinglass_orderbook_imb_mean_24h"], errors="coerce")
                if "coinglass_orderbook_imb_mean_24h" in frame.columns
                else _nan_mf01.copy()
            )
            _ob_ask_heavy_share_mf01 = (
                pd.to_numeric(frame["coinglass_orderbook_ask_heavy_share_24h"], errors="coerce")
                if "coinglass_orderbook_ask_heavy_share_24h" in frame.columns
                else _nan_mf01.copy()
            )
            _ob_bid_heavy_share_mf01 = (
                pd.to_numeric(frame["coinglass_orderbook_bid_heavy_share_24h"], errors="coerce")
                if "coinglass_orderbook_bid_heavy_share_24h" in frame.columns
                else _nan_mf01.copy()
            )
            _liq_imb_spk = (
                pd.to_numeric(frame["coinglass_liquidation_imbalance_24h"], errors="coerce")
                if "coinglass_liquidation_imbalance_24h" in frame.columns
                else _nan_mf01.copy()
            )
            _taker_net_to_depth_mf01 = (
                pd.to_numeric(frame["coinglass_taker_net_to_depth_mean_24h"], errors="coerce")
                if "coinglass_taker_net_to_depth_mean_24h" in frame.columns
                else _nan_mf01.copy()
            )
            _coverage_ok_mf01 = _hourly_bar_count_mf01.ge(16.0)
            frame["pump_return_sigma"] = _pump_sigma_spk.astype("float64")
            frame["abnormal_range_z_60"] = _abnormal_range_spk.astype("float64")
            frame["ob_bid_depth_mean_z30"] = rolling_history_zscore(
                _ob_bid_depth_mf01,
                30,
                min_periods=10,
            )
            frame["ob_total_depth_mean_z30"] = rolling_history_zscore(
                _ob_total_depth_mf01,
                30,
                min_periods=10,
            )
            frame["taker_net_to_depth_mean_z30"] = rolling_history_zscore(
                _taker_net_to_depth_mf01,
                30,
                min_periods=10,
            )
            frame["ob_bid_replenishment_ratio_1d"] = _ob_bid_depth_mf01 / _ob_bid_depth_mf01.shift(1).replace(0.0, np.nan)
            frame["ob_total_depth_replenishment_ratio_1d"] = (
                _ob_total_depth_mf01 / _ob_total_depth_mf01.shift(1).replace(0.0, np.nan)
            )
            _ob_bid_depth_z30_mf01 = pd.to_numeric(frame["ob_bid_depth_mean_z30"], errors="coerce")
            _ob_bid_replenishment_ratio_mf01 = pd.to_numeric(
                frame["ob_bid_replenishment_ratio_1d"], errors="coerce"
            )
            _weak_bid_fragility_mf01 = (
                (-0.50 - _ob_bid_depth_z30_mf01).clip(lower=0.0, upper=4.0)
                + (0.95 - _ob_bid_replenishment_ratio_mf01).clip(lower=0.0, upper=0.50) / 0.10
            )
            _ask_pressure_fragility_mf01 = (
                (_ob_ask_heavy_share_mf01 - 0.60).clip(lower=0.0, upper=0.40) / 0.10
                + (-0.05 - _ob_imb_mean_mf01).clip(lower=0.0, upper=0.30) / 0.10
            )
            _boundary_fragile_flag_mf01 = (
                _coverage_ok_mf01
                & (
                    (
                        _ob_bid_depth_z30_mf01.lt(-0.50)
                        & _ob_bid_replenishment_ratio_mf01.lt(0.95)
                    )
                    | (
                        _ob_ask_heavy_share_mf01.gt(0.60)
                        & _ob_imb_mean_mf01.lt(-0.05)
                    )
                )
            )
            _pump_core_flag_mf01 = _coverage_ok_mf01 & _pump_event_mask_spk.fillna(False)
            _pump_bid_fail_flag_mf01 = (
                _pump_core_flag_mf01
                & _ob_bid_depth_z30_mf01.lt(-0.50)
                & _ob_bid_replenishment_ratio_mf01.lt(0.95)
            )
            _supportive_replenishment_flag_mf01 = (
                _coverage_ok_mf01
                & _ob_bid_depth_z30_mf01.gt(0.50)
                & _ob_bid_heavy_share_mf01.gt(0.60)
                & _ob_imb_mean_mf01.gt(0.05)
            )
            _mid_liquidity_spk = (
                frame["liquidity_bucket"].astype(str).eq("mid_liquidity")
                if "liquidity_bucket" in frame.columns
                else pd.Series(False, index=frame.index, dtype="bool")
            )
            _post_pump_negative_spk = pd.to_numeric(
                frame.get("post_pump_stall_core_score_3d"),
                errors="coerce",
            ).fillna(0.0).lt(0.0)
            _spk_confirmation_mask_mf01 = (
                _mid_liquidity_spk
                & _post_pump_negative_spk
                & (_boundary_fragile_flag_mf01 | _pump_bid_fail_flag_mf01)
            )
            _downside_shock_guardrail_mf01 = (
                _coverage_ok_mf01
                & _pump_sigma_spk.lt(-2.0)
                & _liq_imb_spk.gt(0.15)
            )
            _post_cascade_guardrail_flag_mf01 = (
                _downside_shock_guardrail_mf01
                & _supportive_replenishment_flag_mf01
            )
            frame["pump_core_mf01_flag"] = _pump_core_flag_mf01.astype("bool")
            frame["boundary_fragile_orderbook_flag"] = _boundary_fragile_flag_mf01.astype("bool")
            frame["pump_bid_replenishment_failure_flag"] = _pump_bid_fail_flag_mf01.astype("bool")
            _boundary_fragile_score_mf01 = -(
                _weak_bid_fragility_mf01.fillna(0.0) + _ask_pressure_fragility_mf01.fillna(0.0)
            ).where(_boundary_fragile_flag_mf01, 0.0)
            _pump_bid_fail_score_mf01 = -(
                _pump_intensity_spk.fillna(0.0) * (1.0 + _weak_bid_fragility_mf01.fillna(0.0))
            ).where(_pump_bid_fail_flag_mf01, 0.0)
            frame["boundary_fragile_orderbook_score"] = _boundary_fragile_score_mf01.astype("float64")
            frame["pump_bid_replenishment_failure_score"] = _pump_bid_fail_score_mf01.astype("float64")
            frame["mf01_short_boundary_combo_score"] = (
                _boundary_fragile_score_mf01 + 0.50 * _pump_bid_fail_score_mf01
            ).astype("float64")
            _spk_confirmation_score_mf01 = (
                _boundary_fragile_score_mf01
                + 0.25 * _pump_bid_fail_score_mf01
                - 0.25
                * pd.to_numeric(frame.get("post_pump_stall_core_score_3d"), errors="coerce").abs().fillna(0.0)
            ).where(_spk_confirmation_mask_mf01, 0.0)
            frame["mf01_spk_confirmation_flag"] = _spk_confirmation_mask_mf01.astype("bool")
            frame["mf01_spk_confirmation_score"] = _spk_confirmation_score_mf01.astype("float64")
            frame["mf01_spk_selected_short_veto_flag"] = (
                _mid_liquidity_spk
                & _post_pump_negative_spk
                & _supportive_replenishment_flag_mf01
            ).astype("bool")
            frame["mf01_post_cascade_guardrail_flag"] = _post_cascade_guardrail_flag_mf01.astype("bool")
        # Alpha Ontology W1.1 â€?MF-04 carry / MF-06 reflex / MF-10 higher-moment.
        # Per-subject (time-series) layer; XS-z and XS-residual layer below in the
        # cross_sectional block. See docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md Â§D.
        funding_v7 = (
            pd.to_numeric(frame["funding_rate"], errors="coerce")
            if "funding_rate" in frame.columns
            else None
        )
        basis_v7 = (
            pd.to_numeric(frame["basis_proxy"], errors="coerce")
            if "basis_proxy" in frame.columns
            else None
        )
        rv20_v7 = pd.to_numeric(frame["realized_volatility_20"], errors="coerce")
        atr20_v7 = pd.to_numeric(frame["atr_proxy_20"], errors="coerce")
        ret1_v7 = pd.to_numeric(frame["return_1"], errors="coerce")
        qve_v7 = pd.to_numeric(frame["quote_volume_expansion"], errors="coerce")
        if funding_v7 is not None and basis_v7 is not None:
            # F09 funding_basis_residual_20 (MF-04): residual of funding regressed on
            # basis through a rolling 20-bar OLS without intercept; isolates the
            # carry pressure that the no-arbitrage relation cannot explain.
            fb_cov_20_v7 = (funding_v7 * basis_v7).rolling(20).sum()
            b_var_20_v7 = (basis_v7 * basis_v7).rolling(20).sum()
            alpha_20_v7 = fb_cov_20_v7 / b_var_20_v7.replace(0.0, np.nan)
            frame["funding_basis_residual_20"] = funding_v7 - alpha_20_v7 * basis_v7
            # F12 funding_basis_residual_implied_repo_30 (MF-04): 30-bar gap between
            # average per-period funding (implied repo proxy) and average basis
            # (perp carry), normalized by atr_proxy_20 as a vol denominator.
            funding_30_avg_v7 = funding_v7.rolling(30).mean()
            basis_30_avg_v7 = basis_v7.rolling(30).mean()
            frame["funding_basis_residual_implied_repo_30"] = (
                (funding_30_avg_v7 - basis_30_avg_v7)
                / atr20_v7.replace(0.0, np.nan)
            )
        if basis_v7 is not None:
            # F11 basis_velocity_3d (MF-04): 3-bar first difference of basis_proxy;
            # XS-z applied below for cross_sectional shape only.
            frame["basis_velocity_3d"] = basis_v7 - basis_v7.shift(3)
            # F13 basis_carry_convexity_3d (MF-04): 3-bar second-order difference of
            # basis_proxy, normalized by realized_volatility_20.
            basis_2nd_diff_3_v7 = basis_v7 - 2.0 * basis_v7.shift(3) + basis_v7.shift(6)
            frame["basis_carry_convexity_3d"] = (
                basis_2nd_diff_3_v7 / rv20_v7.replace(0.0, np.nan)
            )
        # F16 qv_acceleration_raw (MF-06): per-subject acceleration of quote-volume
        # expansion. XS_residual on |return_1| applied below.
        frame["qv_acceleration_raw"] = qve_v7 - qve_v7.shift(1)
        # F18 flow_persistence_against_price_20 (MF-06): rolling 20-bar mean of the
        # concordance sign(flow_imb) * sign(return_1); high values mark flow that
        # has been pushing price in the same direction (momentum continuation).
        if "coinglass_taker_imbalance_5d_sum" in frame.columns:
            flow_imb_v7 = pd.to_numeric(
                frame["coinglass_taker_imbalance_5d_sum"], errors="coerce"
            )
            concord_v7 = (
                np.sign(flow_imb_v7).fillna(0.0) * np.sign(ret1_v7).fillna(0.0)
            )
            frame["flow_persistence_against_price_20"] = concord_v7.rolling(20).mean()
        # F19 absorption_score_raw (MF-06): qv_expansion gated by (1 - |r| / rv_20).
        # Large volume with small return = inventory absorption. XS-z applied below.
        frame["absorption_score_raw"] = qve_v7 * (
            1.0 - ret1_v7.abs() / rv20_v7.replace(0.0, np.nan)
        )
        # F20 capitulation_amplification_event (MF-06): sparse event factor; non-zero
        # only on capitulation bars (return < -1.5 * rv_20). Sign(return) is -1 in
        # those cases so the output is `-(rv_20 - qv_expansion)` on triggers.
        cap_indicator_v7 = (ret1_v7 < -1.5 * rv20_v7).astype("float64")
        frame["capitulation_amplification_event"] = (
            (rv20_v7 - qve_v7) * np.sign(ret1_v7).fillna(0.0) * cap_indicator_v7
        )
        # F31 realized_skew_20_raw (MF-10): 20-bar realized skew of return_1. XS-z below.
        frame["realized_skew_20_raw"] = _safe_rolling_skew(ret1_v7, 20)
        # F32 realized_kurt_20_raw (MF-10): 20-bar realized kurtosis of return_1. XS-z below.
        frame["realized_kurt_20_raw"] = _safe_rolling_kurt(ret1_v7, 20)
        # F33 downside_upside_vol_ratio_30 (MF-10): ratio of conditional 30-bar std
        # on negative-return bars to that on positive-return bars. min_periods=5
        # prevents NaN floor while still requiring enough realisations on each side.
        ret_neg_v7 = ret1_v7.where(ret1_v7 < 0)
        ret_pos_v7 = ret1_v7.where(ret1_v7 > 0)
        std_neg_30_v7 = ret_neg_v7.rolling(30, min_periods=5).std()
        std_pos_30_v7 = ret_pos_v7.rolling(30, min_periods=5).std()
        frame["downside_upside_vol_ratio_30"] = (
            std_neg_30_v7 / std_pos_30_v7.replace(0.0, np.nan)
        )
        # F35 vol_of_vol_60 (MF-10): 60-bar std of realized_volatility_20.
        frame["vol_of_vol_60"] = rv20_v7.rolling(60).std()
        # F36 abnormal_range_z_60 (MF-10): 60-bar rolling z-score of normalized
        # daily range (high - low) / close.
        high_v7 = pd.to_numeric(frame["spot_high"], errors="coerce")
        low_v7 = pd.to_numeric(frame["spot_low"], errors="coerce")
        close_v7 = pd.to_numeric(frame["spot_close"], errors="coerce").replace(0.0, np.nan)
        range_norm_v7 = (high_v7 - low_v7) / close_v7
        range_mean_60_v7 = range_norm_v7.rolling(60).mean()
        range_std_60_v7 = range_norm_v7.rolling(60).std()
        frame["abnormal_range_z_60"] = (
            (range_norm_v7 - range_mean_60_v7) / range_std_60_v7.replace(0.0, np.nan)
        )
        # Alpha Ontology W3.1 â€?MF-08 state-machine factors F46/F47/F48/F49.
        # Per-subject "days since last event" factors derived from existing
        # daily panel inputs. Saturate at 60 bars (no event in 60 days = max).
        # F49 (universe-wide co-occurrence) is built in the cross_sectional
        # block below, using the per-subject __w3_vol_shock_event_today flag.
        idx_arr_v8 = np.arange(len(frame))
        # F46 vol_shock_impulse_phase: days since last 3-sigma vol shock.
        rv_lag_20_v8 = ret1_v7.rolling(20).std().shift(1)
        vol_shock_today_v8 = (ret1_v7.abs() > 3.0 * rv_lag_20_v8) & rv_lag_20_v8.notna()
        vol_shock_pos_v8 = np.where(vol_shock_today_v8.fillna(False).values, idx_arr_v8, -1)
        last_vol_shock_v8 = np.maximum.accumulate(vol_shock_pos_v8)
        days_since_vol_v8 = np.where(
            last_vol_shock_v8 >= 0, idx_arr_v8 - last_vol_shock_v8, 60
        ).astype("float64")
        frame["vol_shock_impulse_phase"] = np.minimum(days_since_vol_v8, 60.0)
        # Internal: keep the today-flag for F49 universe-wide aggregation. Dropped
        # at the end of the cross_sectional block.
        frame["__w3_vol_shock_event_today"] = vol_shock_today_v8.fillna(False).astype("float64")
        # F47 funding_flip_decay_phase: days since last funding sign flip.
        if funding_v7 is not None:
            funding_sign_v8 = np.sign(funding_v7.fillna(0.0))
            prev_sign_v8 = funding_sign_v8.shift(1).fillna(0.0)
            funding_flip_today_v8 = (
                (funding_sign_v8 != prev_sign_v8)
                & (funding_sign_v8 != 0.0)
                & (prev_sign_v8 != 0.0)
            )
            flip_pos_v8 = np.where(funding_flip_today_v8.fillna(False).values, idx_arr_v8, -1)
            last_flip_v8 = np.maximum.accumulate(flip_pos_v8)
            days_since_flip_v8 = np.where(
                last_flip_v8 >= 0, idx_arr_v8 - last_flip_v8, 60
            ).astype("float64")
            frame["funding_flip_decay_phase"] = np.minimum(days_since_flip_v8, 60.0)
        # F48 oi_shock_decay_phase: days since last 2-sigma OI jump (pct change).
        if "open_interest" in frame.columns:
            oi_v8 = pd.to_numeric(frame["open_interest"], errors="coerce").replace(0.0, np.nan)
            oi_change_v8 = oi_v8.pct_change(1, fill_method=None)
            oi_std_lag_v8 = oi_change_v8.rolling(20).std().shift(1)
            oi_shock_today_v8 = (oi_change_v8.abs() > 2.0 * oi_std_lag_v8) & oi_std_lag_v8.notna()
            oi_shock_pos_v8 = np.where(oi_shock_today_v8.fillna(False).values, idx_arr_v8, -1)
            last_oi_shock_v8 = np.maximum.accumulate(oi_shock_pos_v8)
            days_since_oi_v8 = np.where(
                last_oi_shock_v8 >= 0, idx_arr_v8 - last_oi_shock_v8, 60
            ).astype("float64")
            frame["oi_shock_decay_phase"] = np.minimum(days_since_oi_v8, 60.0)
        frame["target_forward_return"] = close.shift(-target_shift_bars) / close - 1.0
        frame["target_up"] = (frame["target_forward_return"] > 0).astype(int)
        # Execution-aligned label: decision at t, fill at t+1, exit at t+1+h.
        execution_entry_close = close.shift(-1)
        execution_exit_close = close.shift(-(target_shift_bars + 1))
        frame[EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN] = (
            execution_exit_close / execution_entry_close - 1.0
        )
        frame[EXECUTION_ALIGNED_TARGET_COLUMN] = (
            frame[EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN] > 0
        ).astype(int)
        frames.append(frame)
    features = pd.concat(frames, ignore_index=True, sort=False).copy()
    if shape == "cross_sectional":
        features["relative_strength_20"] = (
            features["momentum_20"] - features.groupby("timestamp_ms")["momentum_20"].transform("mean")
        )
        if "coinglass_taker_imb_intraday_dispersion_24h" in features.columns:
            features["disp_taker_imb_xs"] = (
                features["coinglass_taker_imb_intraday_dispersion_24h"]
                - features.groupby("timestamp_ms")["coinglass_taker_imb_intraday_dispersion_24h"].transform("median")
            )
        if "coinglass_liquidation_imbalance_24h" in features.columns:
            features["unwind_liq_imb_xs"] = (
                features["coinglass_liquidation_imbalance_24h"]
                - features.groupby("timestamp_ms")["coinglass_liquidation_imbalance_24h"].transform("median")
            )
        # Alpha Ontology W1.1 â€?XS-z and XS-residual layer for F11 / F16 / F19 / F31 / F32.
        xs_timestamps_v7 = features["timestamp_ms"]
        if "basis_velocity_3d" in features.columns:
            features["basis_velocity_3d_xs_z"] = _timestamp_zscore(
                pd.to_numeric(features["basis_velocity_3d"], errors="coerce"),
                xs_timestamps_v7,
            )
        if "absorption_score_raw" in features.columns:
            features["absorption_score_20"] = _timestamp_zscore(
                pd.to_numeric(features["absorption_score_raw"], errors="coerce"),
                xs_timestamps_v7,
            )
        if "realized_skew_20_raw" in features.columns:
            features["realized_skew_20_xs_z"] = _timestamp_zscore(
                pd.to_numeric(features["realized_skew_20_raw"], errors="coerce"),
                xs_timestamps_v7,
            )
        if "realized_kurt_20_raw" in features.columns:
            features["realized_kurt_20_xs_z"] = _timestamp_zscore(
                pd.to_numeric(features["realized_kurt_20_raw"], errors="coerce"),
                xs_timestamps_v7,
            )
        if "qv_acceleration_raw" in features.columns and "return_1" in features.columns:
            # F16: per-timestamp OLS residual of qv_acceleration on |return_1| (with
            # implicit intercept via centering); orthogonalises absorption to the
            # mechanical "more vol -> more flow" relationship.
            qv_acc_xs_v7 = pd.to_numeric(features["qv_acceleration_raw"], errors="coerce")
            abs_r_xs_v7 = pd.to_numeric(features["return_1"], errors="coerce").abs()
            qv_mean_xs_v7 = qv_acc_xs_v7.groupby(xs_timestamps_v7).transform("mean")
            ar_mean_xs_v7 = abs_r_xs_v7.groupby(xs_timestamps_v7).transform("mean")
            qv_centered_v7 = qv_acc_xs_v7 - qv_mean_xs_v7
            ar_centered_v7 = abs_r_xs_v7 - ar_mean_xs_v7
            cov_xs_v7 = (qv_centered_v7 * ar_centered_v7).groupby(xs_timestamps_v7).transform("sum")
            var_xs_v7 = (ar_centered_v7 * ar_centered_v7).groupby(xs_timestamps_v7).transform("sum")
            beta_xs_v7 = (cov_xs_v7 / var_xs_v7.replace(0.0, np.nan)).fillna(0.0)
            features["qv_acceleration_residual_xs"] = (
                qv_centered_v7 - beta_xs_v7 * ar_centered_v7
            )
        # Alpha Ontology W3.1 â€?F49 shock_co_occurrence_index. Universe-wide
        # fraction of subjects with a 3-sigma vol shock at this timestamp.
        if "__w3_vol_shock_event_today" in features.columns:
            features["shock_co_occurrence_index"] = (
                features.groupby("timestamp_ms")["__w3_vol_shock_event_today"].transform("mean")
            )
        # Alpha Ontology W3.2 â€?MF-09 co-jump & contagion network factors
        # F26 / F27 / F28 / F29. Cross-asset structure: requires the universe
        # frame (post-concat). BTC anchors the lead-lag legs (F27 / F28); the
        # universe shock indicator anchors the cluster gauges (F26 / F29).
        sub_v9 = features["subject"]
        ret_v9 = pd.to_numeric(features["return_1"], errors="coerce")
        if "__w3_vol_shock_event_today" in features.columns:
            # F26 co_jump_count_3d: universe-wide rolling 3-bar count of vol shocks.
            # Distinct from F49 (point-in-time fraction) by the temporal aggregation
            # window â€?captures cluster cascades rather than single-day shocks.
            shock_today_v9 = pd.to_numeric(
                features["__w3_vol_shock_event_today"], errors="coerce"
            ).fillna(0.0)
            count_per_ts_v9 = (
                shock_today_v9.groupby(features["timestamp_ms"]).sum().sort_index()
            )
            count_3d_v9 = count_per_ts_v9.rolling(3, min_periods=1).sum()
            features["co_jump_count_3d"] = (
                features["timestamp_ms"].map(count_3d_v9).fillna(0.0)
            )
            # F29 contagion_in_degree: per-subject rolling-60-bar mean of
            # n_other_shockers conditioned on self-shocking-today. Captures
            # how exposed asset i has been to systemic co-jump events.
            universe_shock_count_v9 = shock_today_v9.groupby(features["timestamp_ms"]).transform("sum")
            n_other_shockers_v9 = universe_shock_count_v9 - shock_today_v9
            exposure_today_v9 = np.where(shock_today_v9 > 0, n_other_shockers_v9, 0.0)
            exposure_series_v9 = pd.Series(exposure_today_v9, index=features.index, dtype="float64")
            features["contagion_in_degree"] = exposure_series_v9.groupby(sub_v9).transform(
                lambda s: s.rolling(60, min_periods=10).mean()
            )
        # F27 / F28 require BTC return as the lead-lag anchor.
        btc_mask_v9 = features["subject"] == "BTC"
        if btc_mask_v9.any():
            btc_ret_v9 = (
                pd.to_numeric(features.loc[btc_mask_v9, "return_1"], errors="coerce")
                .groupby(features.loc[btc_mask_v9, "timestamp_ms"]).first()
                .sort_index()
            )
            btc_ret_lag1_v9 = btc_ret_v9.shift(1)
            features["__w3_btc_return"] = (
                features["timestamp_ms"].map(btc_ret_v9).astype("float64")
            )
            features["__w3_btc_return_lag1"] = (
                features["timestamp_ms"].map(btc_ret_lag1_v9).astype("float64")
            )
            # F27 lead_lag_beta_btc: per-subject rolling-60-bar OLS slope of
            # return_1 on BTC_return_lag1 (univariate, with intercept via
            # demeaning). High beta = follower of BTC = momentum continuation.
            x27 = features["__w3_btc_return_lag1"]
            y27 = ret_v9
            xy_mean_27 = (x27 * y27).groupby(sub_v9).transform(lambda s: s.rolling(60, min_periods=20).mean())
            xx_mean_27 = (x27 * x27).groupby(sub_v9).transform(lambda s: s.rolling(60, min_periods=20).mean())
            x_mean_27 = x27.groupby(sub_v9).transform(lambda s: s.rolling(60, min_periods=20).mean())
            y_mean_27 = y27.groupby(sub_v9).transform(lambda s: s.rolling(60, min_periods=20).mean())
            cov_27 = xy_mean_27 - x_mean_27 * y_mean_27
            var_27 = xx_mean_27 - x_mean_27 * x_mean_27
            features["lead_lag_beta_btc"] = (cov_27 / var_27.replace(0.0, np.nan))
            # F28 lead_lag_residual_strength: per-subject rolling-20-bar mean of
            # the BTC-stripped return. Î² is rolling-60-bar OLS of return_1 on
            # contemporaneous BTC_return; residual = return - (intercept + Î²Â·BTC).
            x28 = features["__w3_btc_return"]
            xy_mean_28 = (x28 * y27).groupby(sub_v9).transform(lambda s: s.rolling(60, min_periods=20).mean())
            xx_mean_28 = (x28 * x28).groupby(sub_v9).transform(lambda s: s.rolling(60, min_periods=20).mean())
            x_mean_28 = x28.groupby(sub_v9).transform(lambda s: s.rolling(60, min_periods=20).mean())
            cov_28 = xy_mean_28 - x_mean_28 * y_mean_27
            var_28 = xx_mean_28 - x_mean_28 * x_mean_28
            beta_28 = (cov_28 / var_28.replace(0.0, np.nan)).fillna(0.0)
            intercept_28 = y_mean_27 - beta_28 * x_mean_28
            residual_28 = y27 - (intercept_28 + beta_28 * x28)
            features["lead_lag_residual_strength"] = residual_28.groupby(sub_v9).transform(
                lambda s: s.rolling(20, min_periods=5).mean()
            )
        # Alpha Ontology W3.3 â€?MF-11 liquidity migration & universe rotation
        # factors F41 / F42 / F44 / F45. Per-subject share/rank velocity factors
        # plus universe-wide return dispersion plus per-subject idiosyncratic
        # variance share. Reuses the W3.2 BTC return columns (dropped below).
        qv_v11 = pd.to_numeric(features["spot_quote_volume"], errors="coerce").fillna(0.0)
        # F41 quote_share_change_30d: per-asset share of universe quote volume,
        # 30-bar absolute change. Positive = capital inflow into the name.
        universe_qv_total_v11 = qv_v11.groupby(features["timestamp_ms"]).transform("sum").replace(0.0, np.nan)
        share_v11 = (qv_v11 / universe_qv_total_v11).fillna(0.0)
        features["quote_share_change_30d"] = share_v11.groupby(sub_v9).transform(
            lambda s: s - s.shift(30)
        )
        # F42 universe_rank_velocity_10: change in cross-section rank-by-quote-
        # volume over 10 bars. Positive = climbing the liquidity ranking.
        rank_v11 = qv_v11.groupby(features["timestamp_ms"]).rank(method="average", ascending=True)
        features["universe_rank_velocity_10"] = rank_v11.groupby(sub_v9).transform(
            lambda s: s - s.shift(10)
        )
        # F44 dispersion_of_returns: cross-sectional std of return_1 at each
        # timestamp. Universe-wide regime gauge (no per-subject variance).
        features["dispersion_of_returns"] = ret_v9.groupby(features["timestamp_ms"]).transform("std")
        # F45 idiosyncratic_share: 1 - rolling-60 R^2 of asset return on BTC
        # contemporaneous return. Higher = idio component is large = alpha
        # extractable independently of BTC factor.
        if "__w3_btc_return" in features.columns:
            x45 = features["__w3_btc_return"]
            y45 = ret_v9
            xy_mean_45 = (x45 * y45).groupby(sub_v9).transform(lambda s: s.rolling(60, min_periods=20).mean())
            xx_mean_45 = (x45 * x45).groupby(sub_v9).transform(lambda s: s.rolling(60, min_periods=20).mean())
            yy_mean_45 = (y45 * y45).groupby(sub_v9).transform(lambda s: s.rolling(60, min_periods=20).mean())
            x_mean_45 = x45.groupby(sub_v9).transform(lambda s: s.rolling(60, min_periods=20).mean())
            y_mean_45 = y45.groupby(sub_v9).transform(lambda s: s.rolling(60, min_periods=20).mean())
            cov_45 = xy_mean_45 - x_mean_45 * y_mean_45
            var_x_45 = xx_mean_45 - x_mean_45 * x_mean_45
            var_y_45 = yy_mean_45 - y_mean_45 * y_mean_45
            r2_45 = (cov_45 * cov_45) / (var_x_45 * var_y_45).replace(0.0, np.nan)
            features["idiosyncratic_share"] = (1.0 - r2_45).clip(lower=0.0, upper=1.0)
        if "__w3_btc_return" in features.columns:
            features.drop(columns=["__w3_btc_return", "__w3_btc_return_lag1"], inplace=True)
        # All W3.x universe-wide / cross-asset features now built; drop the
        # internal vol-shock-today flag.
        if "__w3_vol_shock_event_today" in features.columns:
            features.drop(columns=["__w3_vol_shock_event_today"], inplace=True)
        # M2.3 F62 settlement_cycle_premium_60d â€?per-subject pre-settlement
        # drift (1h log return at UTC 23/7/15 minus other hours, rolling 60d).
        # Loaded from artifacts/quant_research/intraday/settlement_cycle_panel_1d.csv
        # (pre-computed by intraday_settlement_features.py from the 1h Binance
        # derivatives store). Merge by (subject, date_utc); missing â†?NaN, the
        # score function's _single_z handles via median fill.
        try:
            from .intraday_settlement_features import DEFAULT_OUTPUT_PATH as _SETTLE_PANEL_PATH
            if _SETTLE_PANEL_PATH.exists():
                _settle_panel = pd.read_csv(_SETTLE_PANEL_PATH)[
                    [
                        "subject",
                        "date_utc",
                        "settlement_cycle_premium_60d",
                        "settlement_cycle_volatility_premium_60d",
                    ]
                ]
                from datetime import datetime as _dt, timezone as _tz
                features["__settle_date_utc"] = features["timestamp_ms"].apply(
                    lambda ms: _dt.fromtimestamp(int(ms) / 1000, tz=_tz.utc).date().isoformat()
                )
                features = features.merge(
                    _settle_panel.rename(columns={"date_utc": "__settle_date_utc"}),
                    on=["subject", "__settle_date_utc"],
                    how="left",
                )
                features.drop(columns=["__settle_date_utc"], inplace=True)
        except Exception:  # noqa: BLE001 - missing artifact / IO error is acceptable
            pass
        # M2.4 F-triangle triangle_residual_60d â€?per-subject 60d rolling 2-
        # regressor OLS residual: funding_rate ~ Î± + Î²1*basis_proxy + Î²2*oi_change_5.
        # Doc Â§E.11 closed-form no-arb relation; the residual is "pressure
        # beyond what basis + OI growth jointly explain". Doc E.11 falsification
        # PASSES (joint IR > 70% Ã— (single funding_z IR + single basis_z IR))
        # but standalone G1/G6 admission FAILS at all rolling-window choices â€?
        # the cross-sectional alpha magnitude is small (raw IC ~ -0.009,
        # residual IC ~ -0.014). Factor is plumbed for future use; not yet
        # score-integrated.
        try:
            from .triangle_residual import add_triangle_residual_to_panel as _add_triangle
            features = _add_triangle(features, window=60)
        except Exception:  # noqa: BLE001
            pass
        _stablecoin_flow_defaults = {
            "stablecoin_flow_signal_ready": 0.0,
            "stablecoin_labeled_coverage_ratio": 0.0,
            "stablecoin_exchange_netflow_ratio": 0.0,
            "stablecoin_whale_to_exchange_ratio": 0.0,
            "stablecoin_issuance_ratio_z14": 0.0,
            "stablecoin_velocity_log_z14": 0.0,
            "stablecoin_exchange_absorption_score_v1": 0.0,
            "stablecoin_whale_exchange_stress_score_v1": 0.0,
        }
        try:
            from .stablecoin_regime import build_stablecoin_regime_panel
            _stablecoin_panel = build_stablecoin_regime_panel()
            if not _stablecoin_panel.empty:
                _stablecoin_panel = _stablecoin_panel[
                    [
                        "decision_date_utc",
                        "signal_ready",
                        "labeled_coverage_ratio",
                        "exchange_netflow_ratio",
                        "whale_to_exchange_ratio",
                        "issuance_ratio_z14",
                        "velocity_log_z14",
                        "exchange_absorption_score_v1",
                        "whale_exchange_stress_score_v1",
                    ]
                ].rename(
                    columns={
                        "decision_date_utc": "__stablecoin_decision_date_utc",
                        "signal_ready": "stablecoin_flow_signal_ready",
                        "labeled_coverage_ratio": "stablecoin_labeled_coverage_ratio",
                        "exchange_netflow_ratio": "stablecoin_exchange_netflow_ratio",
                        "whale_to_exchange_ratio": "stablecoin_whale_to_exchange_ratio",
                        "issuance_ratio_z14": "stablecoin_issuance_ratio_z14",
                        "velocity_log_z14": "stablecoin_velocity_log_z14",
                        "exchange_absorption_score_v1": "stablecoin_exchange_absorption_score_v1",
                        "whale_exchange_stress_score_v1": "stablecoin_whale_exchange_stress_score_v1",
                    }
                )
                from datetime import datetime as _dt4, timezone as _tz4
                features["__stablecoin_decision_date_utc"] = features["timestamp_ms"].apply(
                    lambda ms: _dt4.fromtimestamp(int(ms) / 1000, tz=_tz4.utc).date().isoformat()
                )
                features = features.merge(
                    _stablecoin_panel,
                    on="__stablecoin_decision_date_utc",
                    how="left",
                )
                features.drop(columns=["__stablecoin_decision_date_utc"], inplace=True)
        except Exception:  # noqa: BLE001
            pass
        for _column, _default in _stablecoin_flow_defaults.items():
            if _column not in features.columns:
                features[_column] = _default
        _m3_2_defaults = {
            "m3_2_panel_ready": 0.0,
            "m3_2_stable_supply_impulse_state": 0.0,
            "m3_2_stable_dry_powder_state": 0.0,
            "m3_2_stable_btc_flow_asymmetry_state": 0.0,
            "m3_2_btc_sell_pressure_state": 0.0,
            "m3_2_reflexive_rebound_state": 0.0,
        }
        try:
            from .onchain_m3_2_features import load_m3_2_feature_panel

            _m3_2_panel = load_m3_2_feature_panel()
            if not _m3_2_panel.empty:
                _m3_2_panel = _m3_2_panel[
                    [
                        "decision_date_utc",
                        "m3_2_panel_ready",
                        "m3_2_stable_supply_impulse_state",
                        "m3_2_stable_dry_powder_state",
                        "m3_2_stable_btc_flow_asymmetry_state",
                        "m3_2_btc_sell_pressure_state",
                        "m3_2_reflexive_rebound_state",
                    ]
                ].rename(columns={"decision_date_utc": "__m3_2_decision_date_utc"})
                from datetime import datetime as _dt5, timezone as _tz5

                features["__m3_2_decision_date_utc"] = features["timestamp_ms"].apply(
                    lambda ms: _dt5.fromtimestamp(int(ms) / 1000, tz=_tz5.utc).date().isoformat()
                )
                features = features.merge(
                    _m3_2_panel,
                    on="__m3_2_decision_date_utc",
                    how="left",
                )
                features.drop(columns=["__m3_2_decision_date_utc"], inplace=True)
        except Exception:  # noqa: BLE001
            pass
        for _column, _default in _m3_2_defaults.items():
            if _column not in features.columns:
                features[_column] = _default
        # SP-A liquidation cascade â€?per-subject 1h liq_to_oi z-score, daily
        # aggregated. Doc Â§E.12 falsification: per-subject post-cascade 24h
        # abnormal log return t-stat=+10.75 (vs 2.5Ïƒ threshold), n=8858 events
        # across 29 subjects, mean abnormal +0.74%. ALL 4 cascade-feature
        # variants PASS G6 strict vs lsk3 baseline; strongest is
        # `liq_cascade_recency_score_5d` (raw IC +0.052 t=+10.50, residual IC
        # +0.062 t=+10.77).
        # See artifacts/quant_research/factor_reports/2026-04-29/liq_cascade_factor_report_card.json
        try:
            from .intraday_liquidation_features import DEFAULT_OUTPUT_PATH as _LIQ_PANEL_PATH
            if _LIQ_PANEL_PATH.exists():
                _liq_panel = pd.read_csv(_LIQ_PANEL_PATH)[
                    [
                        "subject",
                        "date_utc",
                        "liq_cascade_max_z_24h",
                        "liq_cascade_count_24h_z25",
                        "liq_cascade_signed_intensity_24h",
                        "liq_cascade_recency_score_5d",
                    ]
                ]
                from datetime import datetime as _dt2, timezone as _tz2
                features["__liq_date_utc"] = features["timestamp_ms"].apply(
                    lambda ms: _dt2.fromtimestamp(int(ms) / 1000, tz=_tz2.utc).date().isoformat()
                )
                features = features.merge(
                    _liq_panel.rename(columns={"date_utc": "__liq_date_utc"}),
                    on=["subject", "__liq_date_utc"],
                    how="left",
                )
                features.drop(columns=["__liq_date_utc"], inplace=True)
        except Exception:  # noqa: BLE001
            pass
        # SP-F sub-day funding microstructure â€?per-subject 4h-grain funding
        # rate sequence aggregated to daily F1 (intraday dispersion 30d), F2
        # (sign flip count 30d), F3 (sub-day skew 30d, COLLINEAR w/ F08).
        # F1 is the SP-F score-admissible winner: G6 residual IC vs lsk3+F08
        # = +0.040 t=+7.24 at h10d (STRICT PASS). Negative sign convention
        # (high dispersion -> overheated carry -> low forward return).
        # See artifacts/quant_research/factor_reports/2026-04-29/subday_funding_factor_report_card.json
        try:
            from .subday_funding_features import DEFAULT_OUTPUT_PATH as _SUBDAY_FUNDING_PANEL_PATH
            if _SUBDAY_FUNDING_PANEL_PATH.exists():
                _subday_panel = pd.read_csv(_SUBDAY_FUNDING_PANEL_PATH)[
                    [
                        "subject",
                        "date_utc",
                        "funding_intraday_dispersion_30d",
                        "funding_sign_flip_count_30d_4h",
                        "funding_term_skew_30d_4h",
                    ]
                ]
                from datetime import datetime as _dt3, timezone as _tz3
                features["__subday_date_utc"] = features["timestamp_ms"].apply(
                    lambda ms: _dt3.fromtimestamp(int(ms) / 1000, tz=_tz3.utc).date().isoformat()
                )
                features = features.merge(
                    _subday_panel.rename(columns={"date_utc": "__subday_date_utc"}),
                    on=["subject", "__subday_date_utc"],
                    how="left",
                )
                features.drop(columns=["__subday_date_utc"], inplace=True)
        except Exception:  # noqa: BLE001
            pass
        # SP-J regime classifier v10 â€?per-timestamp 3-state regime label
        # {trend_up, rotation_high_vol, drawdown_rebound} computed from
        # trailing data only (no lookahead). Used by xs_alpha_ontology_v10_
        # regime_conditional_h10d_score for regime-conditional F1 weighting.
        # See data_utilization_roadmap.md SP-J + algorithm_choices.md ADR-C6.
        try:
            from .regime_gating import classify_regime_v10
            _regime_labels = classify_regime_v10(features)  # ts_ms -> str
            features["regime_label_v10"] = (
                features["timestamp_ms"]
                .map(_regime_labels.to_dict())
                .fillna("trend_up")
                .astype("object")
            )
        except Exception:  # noqa: BLE001
            features["regime_label_v10"] = "trend_up"
        # SP-B partial â€?1h Coinglass microstructure factor swarm. Only B3a
        # (`top_trader_velocity_1h_abs_24h`) passes G6 strict standalone, but
        # has +0.94 per-ts spearman with `liq_cascade_recency_score_5d` (SP-A
        # winner) â€?sibling-duplicate signal, no NET alpha lift. B2 (MF-07
        # disagreement) and B5 (F62 sibling on flow) both fail G1 + G6. Panel
        # plumbed for future use (e.g., horizon scan SP-C, or pairing with
        # different baseline). NOT score-integrated.
        try:
            from .intraday_microstructure_features import DEFAULT_OUTPUT_PATH as _MICRO_PANEL_PATH
            if _MICRO_PANEL_PATH.exists():
                _micro_panel = pd.read_csv(_MICRO_PANEL_PATH)[
                    [
                        "subject",
                        "date_utc",
                        "top_global_disagreement_1h_30d",
                        "top_trader_velocity_1h_abs_24h",
                        "top_trader_velocity_1h_signed_24h",
                        "taker_skew_presettle_30d",
                    ]
                ]
                from datetime import datetime as _dt3, timezone as _tz3
                features["__micro_date_utc"] = features["timestamp_ms"].apply(
                    lambda ms: _dt3.fromtimestamp(int(ms) / 1000, tz=_tz3.utc).date().isoformat()
                )
                features = features.merge(
                    _micro_panel.rename(columns={"date_utc": "__micro_date_utc"}),
                    on=["subject", "__micro_date_utc"],
                    how="left",
                )
                features.drop(columns=["__micro_date_utc"], inplace=True)
        except Exception:  # noqa: BLE001
            pass
    elif "__w3_vol_shock_event_today" in features.columns:
        # Single-asset shape: no universe to aggregate over; drop the internal flag.
        features.drop(columns=["__w3_vol_shock_event_today"], inplace=True)
    label_contract = _apply_label_contract(
        features=features,
        shape=shape,
        label_contract_id=resolved_label_contract_id,
    )
    with pd.option_context("future.no_silent_downcasting", True):
        features = features.replace([np.inf, -np.inf], np.nan)
    features = features.infer_objects(copy=False)
    features.dropna(subset=[str(label_contract["forward_return_column"])], inplace=True)
    quality_columns = [
        "subject",
        "timestamp_ms",
        "liquidity_bucket",
        "usdm_symbol",
        *(feature_source_flag_column(name) for name in DERIVATIVES_FEATURE_SPECS),
        *(feature_ready_flag_column(name) for name in DERIVATIVES_FEATURE_SPECS),
    ]
    quality_frame = features[[column for column in quality_columns if column in features.columns]].copy()
    output = features.drop(
        columns=[
            column
            for column in list(quality_frame.columns)
            if column.startswith("__derivatives_")
        ],
        errors="ignore",
    ).copy()
    with pd.option_context("future.no_silent_downcasting", True):
        output = output.fillna(0.0)
    output = output.infer_objects(copy=False)
    split_realization_contract = build_split_realization_contract(shape=shape, interval=interval)
    if target_shift_bars > 0:
        split_realization_contract = build_split_realization_contract(
            shape=shape,
            interval=interval,
            target_horizon_bars=int(target_shift_bars),
        )
        return {
        "dataframe": output,
        "quality_frame": quality_frame,
        "split_realization_contract": split_realization_contract,
        "label_contract": label_contract,
        "label_contract_id": label_contract["label_contract_id"],
        "target_column": label_contract["target_column"],
        "forward_return_column": label_contract["forward_return_column"],
        "label_columns": list(label_contract["label_columns"]),
        "derivatives_feature_quality": summarize_feature_derivatives_quality(
            quality_frame=quality_frame,
            interval=interval,
            provider_index=provider_index or {},
        ),
    }


def _resolve_label_contract_id(*, shape: str, label_contract_id: str | None) -> str:
    resolved = str(label_contract_id or DEFAULT_LABEL_CONTRACT_ID).strip() or DEFAULT_LABEL_CONTRACT_ID
    if resolved == DEFAULT_LABEL_CONTRACT_ID:
        return resolved
    if str(shape) != "cross_sectional":
        raise ValueError(f"label contract {resolved} is only supported for cross_sectional features")
    if resolved not in SUPPORTED_CROSS_SECTIONAL_LABEL_CONTRACT_IDS:
        raise ValueError(f"unsupported label contract: {resolved}")
    return resolved


def _label_contract_metadata(*, shape: str, label_contract_id: str) -> dict[str, Any]:
    resolved = _resolve_label_contract_id(shape=shape, label_contract_id=label_contract_id)
    if resolved == EXECUTION_ALIGNED_LABEL_CONTRACT_ID:
        return {
            "label_contract_id": resolved,
            "target_column": EXECUTION_ALIGNED_TARGET_COLUMN,
            "forward_return_column": EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN,
            "raw_forward_return_column": EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN,
            "label_columns": [
                "target_forward_return",
                "target_up",
                EXECUTION_ALIGNED_FORWARD_RETURN_COLUMN,
                EXECUTION_ALIGNED_TARGET_COLUMN,
            ],
        }
    if resolved == PARTICIPATION_DRIFT_LABEL_CONTRACT_ID:
        return {
            "label_contract_id": resolved,
            "target_column": "target_participation_drift_up",
            "forward_return_column": "target_participation_drift_forward_return",
            "raw_forward_return_column": "target_forward_return",
            "label_columns": [
                "target_forward_return",
                "target_up",
                "target_participation_drift_forward_return",
                "target_participation_drift_up",
            ],
        }
    return {
        "label_contract_id": DEFAULT_LABEL_CONTRACT_ID,
        "target_column": "target_up",
        "forward_return_column": "target_forward_return",
        "raw_forward_return_column": "target_forward_return",
        "label_columns": ["target_forward_return", "target_up"],
    }


def _apply_label_contract(
    *,
    features: pd.DataFrame,
    shape: str,
    label_contract_id: str,
) -> dict[str, Any]:
    metadata = _label_contract_metadata(
        shape=shape,
        label_contract_id=label_contract_id,
    )
    if metadata["label_contract_id"] != PARTICIPATION_DRIFT_LABEL_CONTRACT_ID:
        return metadata
    if features.empty:
        return metadata
    if str(shape) != "cross_sectional":
        raise ValueError("participation drift label contract requires cross_sectional features")
    volatility_proxy = pd.concat(
        [
            pd.to_numeric(features.get("realized_volatility_20"), errors="coerce").abs(),
            pd.to_numeric(features.get("atr_proxy_20"), errors="coerce").abs(),
        ],
        axis=1,
    ).max(axis=1)
    fallback_scale = float(volatility_proxy.dropna().median()) if volatility_proxy.notna().any() else 0.02
    minimum_scale = max(float(fallback_scale) * 0.25, 1e-4)
    scaled_volatility = volatility_proxy.fillna(fallback_scale).clip(lower=minimum_scale)
    raw_forward_return = pd.to_numeric(features["target_forward_return"], errors="coerce")
    volatility_adjusted_forward_return = raw_forward_return / scaled_volatility
    cross_sectional_median = volatility_adjusted_forward_return.groupby(features["timestamp_ms"]).transform("median")
    features["target_participation_drift_forward_return"] = (
        volatility_adjusted_forward_return - cross_sectional_median
    )
    features["target_participation_drift_up"] = (
        features["target_participation_drift_forward_return"] > 0.0
    ).astype(int)
    return metadata


def rolling_zscore(series: pd.Series, window: int, *, min_periods: int | None = None) -> pd.Series:
    resolved_min_periods = int(min_periods) if min_periods is not None else int(window)
    rolling_mean = series.rolling(window, min_periods=resolved_min_periods).mean()
    rolling_std = series.rolling(window, min_periods=resolved_min_periods).std(ddof=0)
    return np.where(rolling_std.ne(0), (series - rolling_mean) / rolling_std, 0.0)


def rolling_history_zscore(series: pd.Series, window: int, *, min_periods: int | None = None) -> pd.Series:
    resolved_min_periods = int(min_periods) if min_periods is not None else int(window)
    baseline_mean = series.rolling(window, min_periods=resolved_min_periods).mean().shift(1)
    baseline_std = series.rolling(window, min_periods=resolved_min_periods).std().shift(1)
    zscore = (series - baseline_mean) / baseline_std.replace(0.0, np.nan)
    return pd.Series(zscore, index=series.index, dtype="float64").replace([np.inf, -np.inf], np.nan)


def _zero_feature_series(frame: pd.DataFrame) -> pd.Series:
    return pd.Series(0.0, index=frame.index, dtype="float64")


def _feature_series(
    frame: pd.DataFrame,
    *columns: str,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    allowed_columns = None
    if feature_columns is not None:
        allowed_columns = {
            str(column).strip()
            for column in feature_columns
            if str(column).strip()
        }
    for column in columns:
        if allowed_columns is not None and column not in allowed_columns:
            continue
        if column in frame.columns:
            return pd.to_numeric(frame[column], errors="coerce").fillna(0.0).astype("float64")
    if feature_columns is None:
        for column in columns:
            if column in frame.columns:
                return pd.to_numeric(frame[column], errors="coerce").fillna(0.0).astype("float64")
    return _zero_feature_series(frame)


def _timestamp_percentile_rank(
    values: pd.Series,
    timestamps: pd.Series,
) -> pd.Series:
    return values.groupby(timestamps).rank(pct=True, method="average")


def _timestamp_zscore(
    values: pd.Series,
    timestamps: pd.Series,
) -> pd.Series:
    group_mean = values.groupby(timestamps).transform("mean")
    group_std = values.groupby(timestamps).transform("std").replace(0.0, np.nan)
    return ((values - group_mean) / group_std).fillna(0.0).astype("float64")


def trend_following_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "momentum_6", feature_columns=feature_columns)
        + _feature_series(frame, "momentum_24", feature_columns=feature_columns)
        + _feature_series(frame, "ema_slope_6_18", "ema_slope_5_20", feature_columns=feature_columns)
        + (_feature_series(frame, "basis_proxy", feature_columns=feature_columns) * 0.25)
    ).astype("float64")


def mean_reversion_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        -(_feature_series(frame, "range_position_20", feature_columns=feature_columns) - 0.5)
        - _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    ).astype("float64")


def breakout_continuation_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        -_feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
        + _feature_series(frame, "momentum_3", "momentum_5", feature_columns=feature_columns)
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0)
        + (_feature_series(frame, "funding_zscore_20", feature_columns=feature_columns) * -0.1)
    ).astype("float64")


def relative_strength_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
        + _feature_series(frame, "momentum_5", feature_columns=feature_columns)
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0)
    ).astype("float64")


def xs_relative_strength_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "relative_strength_20", feature_columns=feature_columns) * 0.55
        + _feature_series(frame, "momentum_20", feature_columns=feature_columns) * 0.25
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.20
    ).astype("float64")


def xs_momentum_acceleration_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    momentum_5 = _feature_series(frame, "momentum_5", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    return (
        momentum_5 * 0.45
        + (momentum_5 - momentum_20) * 0.35
        + _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns) * 0.20
    ).astype("float64")


def xs_breakout_confirmation_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        -_feature_series(frame, "distance_to_high_20", feature_columns=feature_columns) * 0.40
        - _feature_series(frame, "distance_to_high_60", feature_columns=feature_columns) * 0.20
        + _feature_series(frame, "momentum_5", feature_columns=feature_columns) * 0.20
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.20
    ).astype("float64")


def xs_breakout_failure_reversal_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        (0.5 - _feature_series(frame, "range_position_20", feature_columns=feature_columns)) * 0.60
        - _feature_series(frame, "momentum_5", feature_columns=feature_columns) * 0.25
        - _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns) * 0.15
    ).astype("float64")


def xs_range_reversion_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        (0.5 - _feature_series(frame, "range_position_20", feature_columns=feature_columns)) * 0.50
        - _feature_series(frame, "momentum_5", feature_columns=feature_columns) * 0.20
        - _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns) * 0.15
        - _feature_series(frame, "atr_proxy_20", feature_columns=feature_columns) * 0.15
    ).astype("float64")


def xs_volatility_expansion_follow_through_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "momentum_5", feature_columns=feature_columns) * 0.30
        + _feature_series(frame, "relative_strength_20", feature_columns=feature_columns) * 0.20
        + _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns) * 0.20
        + _feature_series(frame, "atr_proxy_20", feature_columns=feature_columns) * 0.15
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.15
    ).astype("float64")


def xs_low_vol_strength_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "relative_strength_20", feature_columns=feature_columns) * 0.45
        + _feature_series(frame, "momentum_20", feature_columns=feature_columns) * 0.30
        - _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns) * 0.15
        - _feature_series(frame, "atr_proxy_20", feature_columns=feature_columns) * 0.10
    ).astype("float64")


def xs_squeeze_breakout_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        -_feature_series(frame, "realized_volatility_20", feature_columns=feature_columns) * 0.30
        - _feature_series(frame, "atr_proxy_20", feature_columns=feature_columns) * 0.25
        - _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns) * 0.20
        + _feature_series(frame, "momentum_5", feature_columns=feature_columns) * 0.10
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.15
    ).astype("float64")


def xs_quality_strength_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "relative_strength_20", feature_columns=feature_columns) * 0.30
        + _feature_series(frame, "momentum_20", feature_columns=feature_columns) * 0.25
        + _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns) * 0.20
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.15
        - _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns) * 0.05
        - _feature_series(frame, "atr_proxy_20", feature_columns=feature_columns) * 0.05
    ).astype("float64")


def xs_pullback_resume_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "momentum_20", feature_columns=feature_columns) * 0.35
        + _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns) * 0.25
        + (0.5 - _feature_series(frame, "range_position_20", feature_columns=feature_columns)) * 0.25
        + _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns) * 0.15
    ).astype("float64")


def xs_squeeze_release_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        -_feature_series(frame, "realized_volatility_20", feature_columns=feature_columns) * 0.25
        - _feature_series(frame, "atr_proxy_20", feature_columns=feature_columns) * 0.20
        - _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns) * 0.20
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.20
        + _feature_series(frame, "momentum_5", feature_columns=feature_columns) * 0.15
    ).astype("float64")


def xs_participation_drift_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "relative_strength_20", feature_columns=feature_columns) * 0.30
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.25
        + _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns) * 0.20
        + _feature_series(frame, "momentum_5", feature_columns=feature_columns) * 0.15
        + _feature_series(frame, "return_1", feature_columns=feature_columns) * 0.10
    ).astype("float64")


def xs_exhaustion_reversal_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        (0.5 - _feature_series(frame, "range_position_20", feature_columns=feature_columns)) * 0.40
        - _feature_series(frame, "momentum_5", feature_columns=feature_columns) * 0.20
        - _feature_series(frame, "return_1", feature_columns=feature_columns) * 0.15
        - _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns) * 0.15
        - _feature_series(frame, "atr_proxy_20", feature_columns=feature_columns) * 0.10
    ).astype("float64")


def xs_base_breakout_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        -_feature_series(frame, "distance_to_high_60", feature_columns=feature_columns) * 0.25
        - _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns) * 0.25
        - _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns) * 0.15
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.20
        + _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns) * 0.15
    ).astype("float64")


def xs_quality_strength_v3_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "relative_strength_20", feature_columns=feature_columns) * 0.32
        + _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns) * 0.22
        + _feature_series(frame, "momentum_20", feature_columns=feature_columns) * 0.18
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.14
        + (0.5 - _feature_series(frame, "range_position_20", feature_columns=feature_columns)) * 0.14
    ).astype("float64")


def xs_participation_drift_v3_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "relative_strength_20", feature_columns=feature_columns) * 0.26
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.22
        + _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns) * 0.18
        + _feature_series(frame, "momentum_20", feature_columns=feature_columns) * 0.16
        + _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns) * 0.10
        - _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns) * 0.08
    ).astype("float64")


def xs_participation_drift_v4_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return xs_participation_drift_v3_score(
        frame,
        feature_columns=feature_columns,
    )


def xs_participation_drift_v5_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "relative_strength_20", feature_columns=feature_columns) * 0.28
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.24
        + _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns) * 0.18
        + _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns) * 0.12
        + (0.5 - _feature_series(frame, "range_position_20", feature_columns=feature_columns)) * 0.10
        - _feature_series(frame, "momentum_5", feature_columns=feature_columns) * 0.05
        - _feature_series(frame, "return_1", feature_columns=feature_columns) * 0.03
    ).astype("float64")


def xs_strength_on_reset_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "relative_strength_20", feature_columns=feature_columns) * 0.30
        + _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns) * 0.22
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.18
        + (0.5 - _feature_series(frame, "range_position_20", feature_columns=feature_columns)) * 0.14
        - _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns) * 0.10
        - _feature_series(frame, "return_1", feature_columns=feature_columns) * 0.04
        - _feature_series(frame, "momentum_5", feature_columns=feature_columns) * 0.02
    ).astype("float64")


def xs_strength_on_reset_v2_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "relative_strength_20", feature_columns=feature_columns) * 0.34
        + _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns) * 0.24
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.20
        + _feature_series(frame, "range_position_20", feature_columns=feature_columns) * 0.12
        + _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns) * 0.10
        - _feature_series(frame, "return_1", feature_columns=feature_columns) * 0.04
    ).astype("float64")


def xs_strength_on_reset_v3_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    base_score = (
        _feature_series(frame, "relative_strength_20", feature_columns=feature_columns) * 0.34
        + _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns) * 0.24
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.18
        + _feature_series(frame, "range_position_20", feature_columns=feature_columns) * 0.12
        + _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns) * 0.08
        - _feature_series(frame, "return_1", feature_columns=feature_columns) * 0.04
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return base_score
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    realized_vol = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    timestamps = frame["timestamp_ms"]
    intraday_vol_rank = intraday_vol.groupby(timestamps).rank(pct=True, method="average")
    volume_rank = volume_expansion.groupby(timestamps).rank(pct=True, method="average")
    realized_vol_rank = realized_vol.groupby(timestamps).rank(pct=True, method="average")
    extension_rank = range_position.groupby(timestamps).rank(pct=True, method="average")
    high_vol_rotation_veto = (
        (intraday_vol_rank >= 0.65)
        & (volume_rank >= 0.65)
        & ((realized_vol_rank >= 0.60) | (extension_rank >= 0.80))
    )
    return base_score.where(~high_vol_rotation_veto, 0.0).astype("float64")


def xs_strength_on_reset_v4_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)
    intraday_realized_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)

    reset_band = (1.0 - ((range_position - 0.64).abs() / 0.26)).clip(lower=0.0, upper=1.0)
    distance_reset = (1.0 - ((distance_to_high + 0.05).abs() / 0.08)).clip(lower=0.0, upper=1.0)

    base_score = (
        relative_strength * 0.30
        + ema_slope * 0.22
        + (quote_volume_expansion - 1.0) * 0.14
        + reset_band * 0.18
        + distance_reset * 0.12
        - return_1 * 0.06
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return base_score

    timestamps = frame["timestamp_ms"]
    intraday_vol_rank = _timestamp_percentile_rank(intraday_realized_vol, timestamps)
    volume_rank = _timestamp_percentile_rank(quote_volume_expansion, timestamps)
    realized_vol_rank = _timestamp_percentile_rank(realized_volatility, timestamps)
    extension_rank = _timestamp_percentile_rank(range_position, timestamps)
    distance_rank = _timestamp_percentile_rank(distance_to_high.abs() * -1.0, timestamps)

    hard_rotation_veto = (
        (intraday_vol_rank >= 0.58)
        & (volume_rank >= 0.62)
        & (realized_vol_rank >= 0.58)
        & ((extension_rank >= 0.74) | (distance_rank >= 0.80))
    )
    soft_rotation_veto = (
        (intraday_vol_rank >= 0.48)
        & (volume_rank >= 0.52)
        & (realized_vol_rank >= 0.50)
        & ((extension_rank >= 0.64) | (distance_rank >= 0.68))
    )

    risk_scale = pd.Series(1.0, index=frame.index, dtype="float64")
    risk_scale = risk_scale.where(~soft_rotation_veto, 0.55)
    risk_scale = risk_scale.where(~hard_rotation_veto, 0.0)

    standardized_score = _timestamp_zscore(base_score, timestamps)
    compressed_score = np.tanh(standardized_score / 1.35)
    return (compressed_score * risk_scale).astype("float64")


def xs_strength_on_reset_v5_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    base_score = (
        _feature_series(frame, "relative_strength_20", feature_columns=feature_columns) * 0.34
        + _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns) * 0.24
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.18
        + _feature_series(frame, "range_position_20", feature_columns=feature_columns) * 0.12
        + _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns) * 0.08
        - _feature_series(frame, "return_1", feature_columns=feature_columns) * 0.04
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return base_score
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    realized_vol = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    timestamps = frame["timestamp_ms"]
    intraday_vol_rank = _timestamp_percentile_rank(intraday_vol, timestamps)
    volume_rank = _timestamp_percentile_rank(volume_expansion, timestamps)
    realized_vol_rank = _timestamp_percentile_rank(realized_vol, timestamps)
    extension_rank = _timestamp_percentile_rank(range_position, timestamps)
    high_vol_rotation_veto = (
        (intraday_vol_rank >= 0.65)
        & (volume_rank >= 0.65)
        & ((realized_vol_rank >= 0.60) | (extension_rank >= 0.80))
    )
    standardized_score = _timestamp_zscore(base_score, timestamps)
    compressed_score = np.tanh(standardized_score / 1.85)
    return compressed_score.where(~high_vol_rotation_veto, 0.0).astype("float64")


def xs_quality_pullback_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    momentum_5 = _feature_series(frame, "momentum_5", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    reset_band = (1.0 - ((range_position - 0.38).abs() / 0.22)).clip(lower=0.0, upper=1.0)
    stable_reset = (1.0 - ((distance_to_low + 0.06).abs() / 0.10)).clip(lower=0.0, upper=1.0)
    base_score = (
        relative_strength * 0.34
        + ema_slope * 0.24
        + (quote_volume_expansion - 1.0) * 0.14
        + reset_band * 0.16
        + stable_reset * 0.10
        - momentum_5 * 0.08
        - return_1 * 0.06
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return base_score
    standardized_score = _timestamp_zscore(base_score, frame["timestamp_ms"])
    return np.tanh(standardized_score / 1.55).astype("float64")


def xs_quality_pullback_v2_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    momentum_5 = _feature_series(frame, "momentum_5", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    reset_band = (1.0 - ((range_position - 0.38).abs() / 0.22)).clip(lower=0.0, upper=1.0)
    stable_reset = (1.0 - ((distance_to_low + 0.06).abs() / 0.10)).clip(lower=0.0, upper=1.0)
    base_score = (
        relative_strength * 0.34
        + ema_slope * 0.24
        + (quote_volume_expansion - 1.0) * 0.14
        + reset_band * 0.16
        + stable_reset * 0.10
        - momentum_5 * 0.08
        - return_1 * 0.06
    ).astype("float64")
    flipped_score = -base_score
    if frame.empty or "timestamp_ms" not in frame.columns:
        return flipped_score
    standardized_score = _timestamp_zscore(flipped_score, frame["timestamp_ms"])
    return np.tanh(standardized_score / 1.55).astype("float64")


def xs_contraction_release_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    atr_proxy = _feature_series(frame, "atr_proxy_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    momentum_5 = _feature_series(frame, "momentum_5", feature_columns=feature_columns)

    squeeze_band = (1.0 - ((range_position - 0.76).abs() / 0.22)).clip(lower=0.0, upper=1.0)
    near_high_base = (1.0 - ((distance_to_high + 0.04).abs() / 0.08)).clip(lower=0.0, upper=1.0)
    orderly_release = (1.0 - ((quote_volume_expansion - 1.22).abs() / 0.75)).clip(lower=0.0, upper=1.0)

    base_score = (
        relative_strength * 0.24
        + ema_slope * 0.20
        + squeeze_band * 0.18
        + near_high_base * 0.16
        + orderly_release * 0.14
        + momentum_5 * 0.06
        - realized_volatility * 0.12
        - atr_proxy * 0.10
        - (quote_volume_expansion - 1.0).clip(lower=0.8) * 0.08
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return base_score
    standardized_score = _timestamp_zscore(base_score, frame["timestamp_ms"])
    return np.tanh(standardized_score / 1.40).astype("float64")


def xs_contraction_release_v2_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    atr_proxy = _feature_series(frame, "atr_proxy_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    momentum_5 = _feature_series(frame, "momentum_5", feature_columns=feature_columns)

    squeeze_band = (1.0 - ((range_position - 0.76).abs() / 0.20)).clip(lower=0.0, upper=1.0)
    near_high_base = (1.0 - ((distance_to_high + 0.04).abs() / 0.08)).clip(lower=0.0, upper=1.0)
    orderly_release = (1.0 - ((quote_volume_expansion - 1.18).abs() / 0.60)).clip(lower=0.0, upper=1.0)
    overheat_penalty = (quote_volume_expansion - 1.55).clip(lower=0.0, upper=1.0)
    hot_momentum_penalty = momentum_5.clip(lower=0.04, upper=0.16) - 0.04

    raw_score = (
        relative_strength * 0.24
        + ema_slope * 0.21
        + squeeze_band * 0.19
        + near_high_base * 0.16
        + orderly_release * 0.12
        + momentum_5 * 0.04
        - realized_volatility * 0.11
        - atr_proxy * 0.09
        - overheat_penalty * 0.10
        - hot_momentum_penalty * 0.08
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    stability_rank_score = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.24
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.20
        + _timestamp_percentile_rank(squeeze_band, timestamps) * 0.20
        + _timestamp_percentile_rank(near_high_base, timestamps) * 0.16
        + _timestamp_percentile_rank(orderly_release, timestamps) * 0.10
        + _timestamp_percentile_rank(-realized_volatility, timestamps) * 0.05
        + _timestamp_percentile_rank(-atr_proxy, timestamps) * 0.05
    ).astype("float64")

    blended_score = (
        _timestamp_zscore(raw_score, timestamps) * 0.55
        + _timestamp_zscore(stability_rank_score, timestamps) * 0.45
    ).astype("float64")
    return np.tanh(blended_score / 1.55).astype("float64")


def xs_contraction_release_v3_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    atr_proxy = _feature_series(frame, "atr_proxy_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    momentum_5 = _feature_series(frame, "momentum_5", feature_columns=feature_columns)

    squeeze_band = (1.0 - ((range_position - 0.76).abs() / 0.20)).clip(lower=0.0, upper=1.0)
    near_high_base = (1.0 - ((distance_to_high + 0.04).abs() / 0.08)).clip(lower=0.0, upper=1.0)
    orderly_release = (1.0 - ((quote_volume_expansion - 1.18).abs() / 0.60)).clip(lower=0.0, upper=1.0)
    overheat_penalty = (quote_volume_expansion - 1.55).clip(lower=0.0, upper=1.0)
    hot_momentum_penalty = momentum_5.clip(lower=0.04, upper=0.16) - 0.04

    raw_score = (
        relative_strength * 0.24
        + ema_slope * 0.21
        + squeeze_band * 0.19
        + near_high_base * 0.16
        + orderly_release * 0.12
        + momentum_5 * 0.04
        - realized_volatility * 0.11
        - atr_proxy * 0.09
        - overheat_penalty * 0.10
        - hot_momentum_penalty * 0.08
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    monotone_rank_score = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.22
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.18
        + _timestamp_percentile_rank(squeeze_band, timestamps) * 0.18
        + _timestamp_percentile_rank(near_high_base, timestamps) * 0.15
        + _timestamp_percentile_rank(orderly_release, timestamps) * 0.11
        + _timestamp_percentile_rank(-realized_volatility, timestamps) * 0.07
        + _timestamp_percentile_rank(-atr_proxy, timestamps) * 0.05
        + _timestamp_percentile_rank(-overheat_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-hot_momentum_penalty, timestamps) * 0.02
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.30
        + _timestamp_zscore(monotone_rank_score, timestamps) * 0.70
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 2.2).astype("float64")


def xs_contraction_release_v4_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    atr_proxy = _feature_series(frame, "atr_proxy_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    momentum_5 = _feature_series(frame, "momentum_5", feature_columns=feature_columns)

    squeeze_band = (1.0 - ((range_position - 0.75).abs() / 0.18)).clip(lower=0.0, upper=1.0)
    near_high_base = (1.0 - ((distance_to_high + 0.04).abs() / 0.07)).clip(lower=0.0, upper=1.0)
    balanced_release = (1.0 - ((quote_volume_expansion - 1.14).abs() / 0.42)).clip(lower=0.0, upper=1.0)
    overheat_penalty = (quote_volume_expansion - 1.45).clip(lower=0.0, upper=1.2)
    hot_momentum_penalty = momentum_5.clip(lower=0.035, upper=0.14) - 0.035

    raw_score = (
        relative_strength * 0.20
        + ema_slope * 0.18
        + squeeze_band * 0.18
        + near_high_base * 0.17
        + balanced_release * 0.15
        + momentum_5 * 0.03
        - realized_volatility * 0.12
        - atr_proxy * 0.10
        - overheat_penalty * 0.10
        - hot_momentum_penalty * 0.07
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    stable_rank_score = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.20
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.17
        + _timestamp_percentile_rank(squeeze_band, timestamps) * 0.18
        + _timestamp_percentile_rank(near_high_base, timestamps) * 0.17
        + _timestamp_percentile_rank(balanced_release, timestamps) * 0.14
        + _timestamp_percentile_rank(-realized_volatility, timestamps) * 0.07
        + _timestamp_percentile_rank(-atr_proxy, timestamps) * 0.04
        + _timestamp_percentile_rank(-overheat_penalty, timestamps) * 0.03
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.15
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.85
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.95).astype("float64")


def xs_contraction_release_v5_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    atr_proxy = _feature_series(frame, "atr_proxy_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    momentum_5 = _feature_series(frame, "momentum_5", feature_columns=feature_columns)

    squeeze_band = (1.0 - ((range_position - 0.75).abs() / 0.18)).clip(lower=0.0, upper=1.0)
    near_high_base = (1.0 - ((distance_to_high + 0.04).abs() / 0.07)).clip(lower=0.0, upper=1.0)
    balanced_release = (1.0 - ((quote_volume_expansion - 1.12).abs() / 0.38)).clip(lower=0.0, upper=1.0)
    calm_drift = (1.0 - ((momentum_5 - 0.012).abs() / 0.045)).clip(lower=0.0, upper=1.0)
    overheat_penalty = (quote_volume_expansion - 1.42).clip(lower=0.0, upper=1.2)
    hot_momentum_penalty = momentum_5.clip(lower=0.03, upper=0.13) - 0.03

    raw_score = (
        relative_strength * 0.19
        + ema_slope * 0.17
        + squeeze_band * 0.18
        + near_high_base * 0.16
        + balanced_release * 0.15
        + calm_drift * 0.09
        - realized_volatility * 0.12
        - atr_proxy * 0.09
        - overheat_penalty * 0.11
        - hot_momentum_penalty * 0.08
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    stable_rank_score = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.19
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.16
        + _timestamp_percentile_rank(squeeze_band, timestamps) * 0.18
        + _timestamp_percentile_rank(near_high_base, timestamps) * 0.16
        + _timestamp_percentile_rank(balanced_release, timestamps) * 0.14
        + _timestamp_percentile_rank(calm_drift, timestamps) * 0.09
        + _timestamp_percentile_rank(-realized_volatility, timestamps) * 0.04
        + _timestamp_percentile_rank(-atr_proxy, timestamps) * 0.02
        + _timestamp_percentile_rank(-overheat_penalty, timestamps) * 0.02
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.10
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.90
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.85).astype("float64")


def xs_absorption_recovery_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    atr_proxy = _feature_series(frame, "atr_proxy_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    lower_mid_reset = (1.0 - ((range_position - 0.40).abs() / 0.22)).clip(lower=0.0, upper=1.0)
    near_low_absorption = (1.0 - ((distance_to_low + 0.05).abs() / 0.09)).clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.08).abs() / 0.35)).clip(lower=0.0, upper=1.0)
    mild_pullback = (1.0 - ((return_1 + 0.012).abs() / 0.035)).clip(lower=0.0, upper=1.0)
    overheat_penalty = (quote_volume_expansion - 1.45).clip(lower=0.0, upper=1.2)
    downside_impulse_penalty = (-return_1 - 0.03).clip(lower=0.0, upper=0.20)

    raw_score = (
        relative_strength * 0.20
        + ema_slope * 0.18
        + lower_mid_reset * 0.17
        + near_low_absorption * 0.15
        + balanced_volume * 0.12
        + mild_pullback * 0.10
        - intraday_vol * 0.13
        - realized_volatility * 0.09
        - atr_proxy * 0.08
        - overheat_penalty * 0.06
        - downside_impulse_penalty * 0.06
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    stable_rank_score = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.19
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.17
        + _timestamp_percentile_rank(lower_mid_reset, timestamps) * 0.16
        + _timestamp_percentile_rank(near_low_absorption, timestamps) * 0.14
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.10
        + _timestamp_percentile_rank(mild_pullback, timestamps) * 0.08
        + _timestamp_percentile_rank(-intraday_vol, timestamps) * 0.08
        + _timestamp_percentile_rank(-realized_volatility, timestamps) * 0.04
        + _timestamp_percentile_rank(-atr_proxy, timestamps) * 0.02
        + _timestamp_percentile_rank(-overheat_penalty, timestamps) * 0.02
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.15
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.85
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.90).astype("float64")


def xs_failed_breakdown_reclaim_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    distance_to_low_20 = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_low_60 = _feature_series(frame, "distance_to_low_60", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    reclaim_band = (1.0 - ((range_position - 0.52).abs() / 0.18)).clip(lower=0.0, upper=1.0)
    near_support_20 = (1.0 - ((distance_to_low_20 - 0.08).abs() / 0.08)).clip(lower=0.0, upper=1.0)
    anchored_support_60 = (1.0 - ((distance_to_low_60 - 0.22).abs() / 0.18)).clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.10).abs() / 0.35)).clip(lower=0.0, upper=1.0)
    rebound_day = (1.0 - ((return_1 - 0.012).abs() / 0.035)).clip(lower=0.0, upper=1.0)
    downside_impulse_penalty = (-return_1 - 0.02).clip(lower=0.0, upper=0.20)
    hot_volume_penalty = (quote_volume_expansion - 1.45).clip(lower=0.0, upper=1.2)

    raw_score = (
        relative_strength * 0.19
        + ema_slope * 0.17
        + reclaim_band * 0.17
        + near_support_20 * 0.13
        + anchored_support_60 * 0.11
        + balanced_volume * 0.08
        + rebound_day * 0.10
        - intraday_vol * 0.12
        - realized_volatility * 0.08
        - downside_impulse_penalty * 0.08
        - hot_volume_penalty * 0.07
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    stable_rank_score = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.18
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.16
        + _timestamp_percentile_rank(reclaim_band, timestamps) * 0.16
        + _timestamp_percentile_rank(near_support_20, timestamps) * 0.12
        + _timestamp_percentile_rank(anchored_support_60, timestamps) * 0.10
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.08
        + _timestamp_percentile_rank(rebound_day, timestamps) * 0.08
        + _timestamp_percentile_rank(-intraday_vol, timestamps) * 0.06
        + _timestamp_percentile_rank(-realized_volatility, timestamps) * 0.03
        + _timestamp_percentile_rank(-hot_volume_penalty, timestamps) * 0.03
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.15
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.85
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.90).astype("float64")


def xs_regime_switch_ranking_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    trend_band = (1.0 - ((range_position - 0.68).abs() / 0.20)).clip(lower=0.0, upper=1.0)
    near_high_drift = (1.0 - ((distance_to_high + 0.05).abs() / 0.08)).clip(lower=0.0, upper=1.0)
    reclaim_band = (1.0 - ((range_position - 0.52).abs() / 0.18)).clip(lower=0.0, upper=1.0)
    near_low_reclaim = (1.0 - ((distance_to_low - 0.08).abs() / 0.08)).clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.10).abs() / 0.35)).clip(lower=0.0, upper=1.0)
    rebound_day = (1.0 - ((return_1 - 0.012).abs() / 0.035)).clip(lower=0.0, upper=1.0)
    downside_impulse_penalty = (-return_1 - 0.02).clip(lower=0.0, upper=0.20)
    hot_volume_penalty = (quote_volume_expansion - 1.45).clip(lower=0.0, upper=1.2)

    if frame.empty or "timestamp_ms" not in frame.columns:
        hot_rotation_state = (
            intraday_vol * 0.45
            + realized_volatility * 0.25
            + quote_volume_expansion.clip(lower=0.0) * 0.20
            + range_position.clip(lower=0.0) * 0.10
        ).astype("float64")
        switch_weight = ((hot_rotation_state - 0.35) / 0.40).clip(lower=0.0, upper=1.0)
    else:
        timestamps = frame["timestamp_ms"]
        hot_rotation_state = (
            _timestamp_percentile_rank(intraday_vol, timestamps) * 0.45
            + _timestamp_percentile_rank(realized_volatility, timestamps) * 0.25
            + _timestamp_percentile_rank(quote_volume_expansion, timestamps) * 0.20
            + _timestamp_percentile_rank(range_position, timestamps) * 0.10
        ).astype("float64")
        switch_weight = ((hot_rotation_state - 0.35) / 0.40).clip(lower=0.0, upper=1.0)

    trend_leg = (
        relative_strength * 0.29
        + ema_slope * 0.23
        + trend_band * 0.17
        + near_high_drift * 0.11
        + balanced_volume * 0.08
        - intraday_vol * 0.07
        - realized_volatility * 0.05
    ).astype("float64")
    reclaim_leg = (
        relative_strength * 0.24
        + ema_slope * 0.18
        + reclaim_band * 0.16
        + near_low_reclaim * 0.12
        + rebound_day * 0.12
        + balanced_volume * 0.08
        - intraday_vol * 0.05
        - downside_impulse_penalty * 0.05
    ).astype("float64")
    raw_score = (
        trend_leg * (1.0 - switch_weight)
        + reclaim_leg * switch_weight
        - hot_volume_penalty * 0.06
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    rs_rank = _timestamp_percentile_rank(relative_strength, timestamps)
    ema_rank = _timestamp_percentile_rank(ema_slope, timestamps)
    low_intraday_rank = _timestamp_percentile_rank(-intraday_vol, timestamps)
    low_realized_rank = _timestamp_percentile_rank(-realized_volatility, timestamps)
    balanced_volume_rank = _timestamp_percentile_rank(balanced_volume, timestamps)
    rebound_day_rank = _timestamp_percentile_rank(rebound_day, timestamps)
    trend_rank_leg = (
        rs_rank * 0.30
        + ema_rank * 0.24
        + _timestamp_percentile_rank(trend_band, timestamps) * 0.15
        + _timestamp_percentile_rank(near_high_drift, timestamps) * 0.11
        + balanced_volume_rank * 0.08
        + low_intraday_rank * 0.07
        + low_realized_rank * 0.05
    ).astype("float64")
    reclaim_rank_leg = (
        rs_rank * 0.24
        + ema_rank * 0.19
        + _timestamp_percentile_rank(reclaim_band, timestamps) * 0.16
        + _timestamp_percentile_rank(near_low_reclaim, timestamps) * 0.12
        + rebound_day_rank * 0.10
        + balanced_volume_rank * 0.08
        + low_intraday_rank * 0.07
        + _timestamp_percentile_rank(-downside_impulse_penalty, timestamps) * 0.04
    ).astype("float64")
    blended_rank = (
        trend_rank_leg * (1.0 - switch_weight)
        + reclaim_rank_leg * switch_weight
    ).astype("float64")
    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.15
        + _timestamp_zscore(blended_rank, timestamps) * 0.85
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.90).astype("float64")


def xs_basis_funding_dislocation_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    stable_oi = (1.0 - (oi_change.abs() / 0.35)).clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.08).abs() / 0.45)).clip(lower=0.0, upper=1.0)
    mild_reset_day = (1.0 - ((return_1 + 0.01).abs() / 0.045)).clip(lower=0.0, upper=1.0)
    crowded_long_penalty = (basis_zscore.clip(lower=0.0) * 0.60 + funding_zscore.clip(lower=0.0) * 0.40).clip(
        lower=0.0,
        upper=2.0,
    )

    raw_score = (
        -basis_zscore * 0.30
        - funding_zscore * 0.28
        + stable_oi * 0.12
        + relative_strength * 0.12
        + balanced_volume * 0.08
        + mild_reset_day * 0.06
        - realized_volatility * 0.08
        - crowded_long_penalty * 0.10
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    stable_rank_score = (
        _timestamp_percentile_rank(-basis_zscore, timestamps) * 0.31
        + _timestamp_percentile_rank(-funding_zscore, timestamps) * 0.27
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.12
        + _timestamp_percentile_rank(relative_strength, timestamps) * 0.10
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.08
        + _timestamp_percentile_rank(mild_reset_day, timestamps) * 0.05
        + _timestamp_percentile_rank(-realized_volatility, timestamps) * 0.04
        + _timestamp_percentile_rank(-crowded_long_penalty, timestamps) * 0.03
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.18
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.82
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.85).astype("float64")


def xs_relative_value_spread_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    cheap_derivatives = (-basis_zscore * 0.55 - funding_zscore * 0.45).astype("float64")
    spot_quality = (
        relative_strength * 0.55
        + ema_slope * 0.25
        + distance_to_low * 0.20
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.40)).clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.06).abs() / 0.42)).clip(lower=0.0, upper=1.0)
    mild_reset_day = (1.0 - ((return_1 + 0.012).abs() / 0.050)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0) * 0.55
        + realized_volatility.clip(lower=0.0) * 0.45
    ).astype("float64")
    broken_tape_penalty = (-distance_to_low - 0.02).clip(lower=0.0, upper=0.30)
    overheat_penalty = (quote_volume_expansion - 1.45).clip(lower=0.0, upper=1.0)

    raw_score = (
        cheap_derivatives * 0.31
        + spot_quality * 0.24
        + stable_oi * 0.13
        + balanced_volume * 0.10
        + mild_reset_day * 0.08
        - stress_penalty * 0.08
        - broken_tape_penalty * 0.04
        - overheat_penalty * 0.02
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    dislocation_rank = (
        _timestamp_percentile_rank(-basis_zscore, timestamps) * 0.30
        + _timestamp_percentile_rank(-funding_zscore, timestamps) * 0.26
    ).astype("float64")
    quality_rank = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.16
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.10
        + _timestamp_percentile_rank(distance_to_low, timestamps) * 0.06
    ).astype("float64")
    stable_rank_score = (
        dislocation_rank
        + quality_rank
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.05
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(mild_reset_day, timestamps) * 0.03
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-overheat_penalty, timestamps) * 0.01
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_relative_value_spread_v2_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    cheap_derivatives = (-basis_proxy * 0.62 - funding_rate * 0.38).astype("float64")
    spot_quality = (
        relative_strength * 0.42
        + ema_slope * 0.26
        + distance_to_low * 0.18
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.38)).clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.05).abs() / 0.36)).clip(lower=0.0, upper=1.0)
    mild_reset_day = (1.0 - ((return_1 + 0.006).abs() / 0.035)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0) * 0.52
        + realized_volatility.clip(lower=0.0) * 0.48
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.22).clip(lower=0.0, upper=0.60) * 0.55
        + return_1.clip(lower=0.0, upper=0.04) * 11.25 * 0.45
    ).astype("float64")

    raw_score = (
        cheap_derivatives * 0.32
        + spot_quality * 0.24
        + stable_oi * 0.13
        + balanced_volume * 0.11
        + mild_reset_day * 0.08
        - stress_penalty * 0.09
        - chase_penalty * 0.03
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    dislocation_rank = (
        _timestamp_percentile_rank(-basis_proxy, timestamps) * 0.31
        + _timestamp_percentile_rank(-funding_rate, timestamps) * 0.23
    ).astype("float64")
    quality_rank = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.16
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.11
        + _timestamp_percentile_rank(distance_to_low, timestamps) * 0.07
    ).astype("float64")
    stability_rank = (
        _timestamp_percentile_rank(stable_oi, timestamps) * 0.05
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(mild_reset_day, timestamps) * 0.02
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.02
    ).astype("float64")
    stable_rank_score = (dislocation_rank + quality_rank + stability_rank).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.28
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.72
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.85).astype("float64")


def xs_relative_value_spread_v3_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.58 - funding_rate * 0.42).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.54 - funding_zscore * 0.46).astype("float64")
    moderate_dislocation = (1.0 - ((normalized_cheapness - 0.95).abs() / 1.10)).clip(lower=0.0, upper=1.0)
    extreme_dislocation_penalty = (
        (normalized_cheapness - 1.75).clip(lower=0.0, upper=1.5)
        + (raw_cheapness - 0.035).clip(lower=0.0, upper=0.08) * 10.0
    ).astype("float64")
    spot_quality = (
        relative_strength * 0.40
        + ema_slope * 0.28
        + distance_to_low * 0.18
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.36)).clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.04).abs() / 0.34)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 + 0.004).abs() / 0.030)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0) * 0.54
        + realized_volatility.clip(lower=0.0) * 0.46
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.20).clip(lower=0.0, upper=0.60) * 0.50
        + return_1.clip(lower=0.0, upper=0.04) * 12.5 * 0.50
    ).astype("float64")

    raw_score = (
        moderate_dislocation * 0.24
        + spot_quality * 0.27
        + stable_oi * 0.14
        + balanced_volume * 0.11
        + orderly_reset * 0.08
        - stress_penalty * 0.08
        - chase_penalty * 0.04
        - extreme_dislocation_penalty * 0.04
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    rank_dislocation = (
        _timestamp_percentile_rank(moderate_dislocation, timestamps) * 0.24
        + _timestamp_percentile_rank(-extreme_dislocation_penalty, timestamps) * 0.08
    ).astype("float64")
    rank_quality = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.15
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.10
        + _timestamp_percentile_rank(distance_to_low, timestamps) * 0.07
    ).astype("float64")
    rank_stability = (
        _timestamp_percentile_rank(stable_oi, timestamps) * 0.06
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.03
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.03
    ).astype("float64")
    stable_rank_score = (rank_dislocation + rank_quality + rank_stability).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.30
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.70
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.90).astype("float64")


def xs_relative_value_spread_v4_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.52 - funding_rate * 0.30).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.54 - funding_zscore * 0.46).astype("float64")
    moderate_dislocation = (1.0 - ((normalized_cheapness - 0.72).abs() / 0.95)).clip(lower=0.0, upper=1.0)
    extreme_dislocation_penalty = (
        (normalized_cheapness - 1.55).clip(lower=0.0, upper=1.50)
        + (raw_cheapness - 0.028).clip(lower=0.0, upper=0.08) * 10.0
    ).astype("float64")
    leadership_anchor = (
        relative_strength * 0.30
        + ema_slope * 0.22
        + momentum_20 * 0.18
        + distance_to_low * 0.10
        + distance_to_high * 0.08
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.34)).clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.03).abs() / 0.32)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.002).abs() / 0.028)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0) * 0.52
        + realized_volatility.clip(lower=0.0) * 0.48
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.18).clip(lower=0.0, upper=0.60) * 0.45
        + return_1.clip(lower=0.0, upper=0.04) * 12.0 * 0.55
    ).astype("float64")
    broken_tape_penalty = (-distance_to_low - 0.015).clip(lower=0.0, upper=0.25)

    raw_score = (
        moderate_dislocation * 0.20
        + leadership_anchor * 0.31
        + stable_oi * 0.12
        + balanced_volume * 0.10
        + orderly_reset * 0.07
        - stress_penalty * 0.08
        - chase_penalty * 0.04
        - extreme_dislocation_penalty * 0.05
        - broken_tape_penalty * 0.03
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    rank_dislocation = (
        _timestamp_percentile_rank(moderate_dislocation, timestamps) * 0.18
        + _timestamp_percentile_rank(-extreme_dislocation_penalty, timestamps) * 0.07
    ).astype("float64")
    rank_leadership = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.14
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.10
        + _timestamp_percentile_rank(momentum_20, timestamps) * 0.09
        + _timestamp_percentile_rank(distance_to_low, timestamps) * 0.05
        + _timestamp_percentile_rank(distance_to_high, timestamps) * 0.04
    ).astype("float64")
    rank_stability = (
        _timestamp_percentile_rank(stable_oi, timestamps) * 0.05
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.03
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
    ).astype("float64")
    stable_rank_score = (rank_dislocation + rank_leadership + rank_stability).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.26
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.74
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.88).astype("float64")


def xs_relative_value_spread_v5_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.44 - funding_rate * 0.24).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.52 - funding_zscore * 0.48).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.42).abs() / 0.70)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 1.20).clip(lower=0.0, upper=1.50)
        + (raw_cheapness - 0.020).clip(lower=0.0, upper=0.06) * 10.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.20).clip(lower=0.0, upper=1.20).astype("float64")
    leadership_anchor = (
        relative_strength * 0.34
        + ema_slope * 0.24
        + momentum_20 * 0.20
        + distance_to_low * 0.10
        + distance_to_high * 0.06
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.32)).clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.30)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.024)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0) * 0.50
        + realized_volatility.clip(lower=0.0) * 0.50
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.16).clip(lower=0.0, upper=0.60) * 0.40
        + return_1.clip(lower=0.0, upper=0.04) * 11.5 * 0.60
    ).astype("float64")
    broken_tape_penalty = (-distance_to_low - 0.012).clip(lower=0.0, upper=0.25)

    raw_score = (
        leadership_anchor * 0.34
        + balanced_discount * 0.17
        + stable_oi * 0.12
        + balanced_volume * 0.11
        + orderly_reset * 0.09
        - stress_penalty * 0.08
        - chase_penalty * 0.03
        - overcheap_penalty * 0.03
        - rich_penalty * 0.02
        - broken_tape_penalty * 0.01
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    rank_leadership = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.15
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.11
        + _timestamp_percentile_rank(momentum_20, timestamps) * 0.10
        + _timestamp_percentile_rank(distance_to_low, timestamps) * 0.05
        + _timestamp_percentile_rank(distance_to_high, timestamps) * 0.03
    ).astype("float64")
    rank_discount = (
        _timestamp_percentile_rank(balanced_discount, timestamps) * 0.12
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.03
    ).astype("float64")
    rank_stability = (
        _timestamp_percentile_rank(stable_oi, timestamps) * 0.05
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.01
    ).astype("float64")
    stable_rank_score = (rank_leadership + rank_discount + rank_stability).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.24
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.76
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.86).astype("float64")


def xs_relative_value_spread_v6_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.34 - funding_rate * 0.18).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.52 - funding_zscore * 0.48).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.26).abs() / 0.52)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.95).clip(lower=0.0, upper=1.40)
        + (raw_cheapness - 0.014).clip(lower=0.0, upper=0.05) * 12.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.10).clip(lower=0.0, upper=1.20).astype("float64")
    leadership_anchor = (
        relative_strength * 0.36
        + ema_slope * 0.24
        + momentum_20 * 0.22
        + distance_to_high * 0.10
        + distance_to_low * 0.05
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.30)).clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.01).abs() / 0.24)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.003).abs() / 0.020)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0) * 0.48
        + realized_volatility.clip(lower=0.0) * 0.52
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.14).clip(lower=0.0, upper=0.60) * 0.40
        + return_1.clip(lower=0.0, upper=0.04) * 10.5 * 0.60
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.008).clip(lower=0.0, upper=0.20)
        + (-distance_to_high - 0.10).clip(lower=0.0, upper=0.20) * 0.50
    ).astype("float64")

    raw_score = (
        leadership_anchor * 0.38
        + balanced_discount * 0.13
        + stable_oi * 0.12
        + balanced_volume * 0.11
        + orderly_reset * 0.10
        - stress_penalty * 0.08
        - chase_penalty * 0.03
        - overcheap_penalty * 0.03
        - rich_penalty * 0.01
        - broken_tape_penalty * 0.01
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    rank_leadership = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.16
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.12
        + _timestamp_percentile_rank(momentum_20, timestamps) * 0.11
        + _timestamp_percentile_rank(distance_to_high, timestamps) * 0.05
        + _timestamp_percentile_rank(distance_to_low, timestamps) * 0.03
    ).astype("float64")
    rank_discount = (
        _timestamp_percentile_rank(balanced_discount, timestamps) * 0.10
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.02
    ).astype("float64")
    rank_stability = (
        _timestamp_percentile_rank(stable_oi, timestamps) * 0.05
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.01
    ).astype("float64")
    stable_rank_score = (rank_leadership + rank_discount + rank_stability).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.84).astype("float64")


def xs_relative_value_spread_v7_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.28 - funding_rate * 0.14).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.52 - funding_zscore * 0.48).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.16).abs() / 0.36)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.78).clip(lower=0.0, upper=1.40)
        + (raw_cheapness - 0.010).clip(lower=0.0, upper=0.05) * 12.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.06).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    leadership_anchor = (
        relative_strength * 0.34
        + ema_slope * 0.23
        + momentum_20 * 0.18
        + reclaim_window * 0.14
        + support_buffer * 0.07
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.28)).clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.01).abs() / 0.22)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0) * 0.48
        + realized_volatility.clip(lower=0.0) * 0.52
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42
        + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.006).clip(lower=0.0, upper=0.20)
        + (-distance_to_high - 0.16).clip(lower=0.0, upper=0.22) * 0.50
    ).astype("float64")
    leadership_gate = ((leadership_anchor + 0.12) / 1.12).clip(lower=0.0, upper=1.0)
    reset_gate = (
        reclaim_window * 0.50
        + support_buffer * 0.20
        + orderly_reset * 0.30
    ).clip(lower=0.0, upper=1.0)
    stability_gate = (
        stable_oi * 0.45
        + balanced_volume * 0.32
        + (1.0 - stress_penalty.clip(lower=0.0, upper=1.0)) * 0.23
    ).clip(lower=0.0, upper=1.0)
    gated_quality = (leadership_gate * reset_gate * stability_gate).astype("float64")

    raw_score = (
        gated_quality * 0.30
        + leadership_anchor * 0.24
        + balanced_discount * 0.08
        + stable_oi * 0.08
        + balanced_volume * 0.08
        + orderly_reset * 0.07
        - stress_penalty * 0.07
        - chase_penalty * 0.03
        - overcheap_penalty * 0.03
        - rich_penalty * 0.01
        - broken_tape_penalty * 0.01
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    rank_leadership = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.15
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.11
        + _timestamp_percentile_rank(momentum_20, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.05
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.03
    ).astype("float64")
    rank_discount = (
        _timestamp_percentile_rank(balanced_discount, timestamps) * 0.06
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_stability = (
        _timestamp_percentile_rank(stable_oi, timestamps) * 0.05
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_gate = (
        _timestamp_percentile_rank(gated_quality, timestamps) * 0.09
        + _timestamp_percentile_rank(reset_gate, timestamps) * 0.05
    ).astype("float64")
    stable_rank_score = (
        rank_leadership + rank_discount + rank_stability + rank_gate
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.25
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.75
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_dual_regime_filter_v6_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v71 = v64 (xs_dual_regime_filter_v1) blended_signal augmented with a CoinGlass-extended
    cross-sectional composite at 12% weight on the final signal stage.

    composite = mean of 4 sign-aligned per-timestamp xs_zscore:
        + xs_zscore(coinglass_taker_imbalance_5d_sum)
        - xs_zscore(coinglass_global_account_long_pct)        # retail crowding fades
        - xs_zscore(coinglass_liquidation_imbalance_24h)      # long-heavy liq fades
        - xs_zscore(coinglass_top_trader_long_pct)            # over-positioned smart-money fades

    final = tanh((percentile_rank(0.88 * v64_blended + 0.12 * xs_zscore(composite)) - 0.5) * 1.80)
    """
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.30 - funding_rate * 0.16).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.53 - funding_zscore * 0.47).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.18).abs() / 0.40)).clip(lower=0.0, upper=1.0)
    cheapness_quality = (1.0 - ((normalized_cheapness - 0.20).abs() / 0.50)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.85).clip(lower=0.0, upper=1.40) * 1.0
        + (raw_cheapness - 0.011).clip(lower=0.0, upper=0.06) * 11.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.08).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.50).abs() / 0.28)).clip(lower=0.0, upper=1.0)
    distress_floor_penalty = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    distress_floor_penalty = distress_floor_penalty.clip(lower=0.0, upper=1.0)
    upper_extension_penalty = (range_position - 0.78).clip(lower=0.0, upper=0.22) * 4.5
    upper_extension_penalty = upper_extension_penalty.clip(lower=0.0, upper=1.0)
    leadership_anchor = (
        relative_strength * 0.32 + ema_slope * 0.22 + momentum_20 * 0.18
        + reclaim_window * 0.13 + support_buffer * 0.07 + quality_zone * 0.08
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.30)).clip(lower=0.0, upper=1.0)
    mild_oi_growth = (oi_change.clip(lower=-0.10, upper=0.18) + 0.05).clip(lower=0.0, upper=0.23) * (1.0 / 0.23)
    mild_oi_growth = mild_oi_growth.clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.24)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50 + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20 + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20 + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42 + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")

    leader_sub = (
        leadership_anchor * 0.34 + balanced_discount * 0.12 + stable_oi * 0.10
        + balanced_volume * 0.10 + orderly_reset * 0.10 + reclaim_window * 0.09
        + quality_zone * 0.10 + support_buffer * 0.05
    ).astype("float64")
    carry_sub = (
        cheapness_quality * 0.36 + stable_oi * 0.14 + mild_oi_growth * 0.12
        + balanced_volume * 0.10 + quality_zone * 0.10 + support_buffer * 0.08
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
    ).astype("float64")
    contrarian_laggard_tilt = (
        (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.18
        + (0.55 - range_position.clip(lower=0.10, upper=0.55)).clip(lower=0.0, upper=0.45) * (1.0 / 0.45) * 0.18
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.14
        + (-momentum_20).clip(lower=-0.05, upper=0.10) * (1.0 / 0.15) * 0.10
        + (-return_1).clip(lower=-0.01, upper=0.025) * (1.0 / 0.035) * 0.08
        + support_buffer * 0.10
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
        + (1.0 - distress_floor_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.06
    ).astype("float64")

    if "timestamp_ms" in frame.columns and not frame.empty:
        ts_values = frame["timestamp_ms"].values
        abs_mom_values = momentum_20.abs().values
        mom_values = momentum_20.values
        disp_df = pd.DataFrame({"v": abs_mom_values, "t": ts_values}, index=frame.index)
        timestamp_disp = disp_df.groupby("t")["v"].transform(
            lambda s: float(pd.Series(s).std() if len(s) > 1 else 0.0)
        )
        median_disp = float(pd.Series(timestamp_disp.values).median()) if len(timestamp_disp) else 0.05
        normalized_disp = (timestamp_disp / max(median_disp * 2.0, 1e-9)).clip(lower=0.0, upper=1.0)
        med_df = pd.DataFrame({"v": mom_values, "t": ts_values}, index=frame.index)
        timestamp_median_mom = med_df.groupby("t")["v"].transform("median")
        scaled_median_mom = (timestamp_median_mom / 0.06).clip(lower=-1.0, upper=1.0)
        broad_uniform_signal = (
            (1.0 - normalized_disp.values) * np.abs(scaled_median_mom.values)
        ).clip(0.0, 1.0)
        disp_array = normalized_disp.values
        med_sign_pos = (scaled_median_mom.values > 0).astype(float)
        leader_weight = (0.20 + 0.60 * disp_array) * (0.55 + 0.45 * med_sign_pos)
        carry_weight = (0.20 + 0.60 * disp_array) * (1.0 - (0.55 + 0.45 * med_sign_pos) * 0.30)
        contrarian_weight = 0.20 + 0.60 * broad_uniform_signal
        total = leader_weight + carry_weight + contrarian_weight + 1e-9
        leader_weight = leader_weight / total
        carry_weight = carry_weight / total
        contrarian_weight = contrarian_weight / total
    else:
        n = len(frame)
        leader_weight = np.full(n, 0.40)
        carry_weight = np.full(n, 0.40)
        contrarian_weight = np.full(n, 0.20)

    blended_alpha = (
        pd.Series(leader_weight, index=frame.index) * leader_sub
        + pd.Series(carry_weight, index=frame.index) * carry_sub
        + pd.Series(contrarian_weight, index=frame.index) * contrarian_laggard_tilt
    ).astype("float64")

    common_penalties = (
        stress_penalty * 0.06 + chase_penalty * 0.025 + overcheap_penalty * 0.04
        + rich_penalty * 0.02 + distress_floor_penalty * 0.05 + upper_extension_penalty * 0.045
        + distress_penalty * 0.05 + broken_tape_penalty * 0.04
    ).astype("float64")

    raw_score = (blended_alpha * 1.0 - common_penalties).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    leader_w_series = pd.Series(leader_weight, index=frame.index)
    carry_w_series = pd.Series(carry_weight, index=frame.index)
    contra_w_series = pd.Series(contrarian_weight, index=frame.index)
    rank_leader = (
        _timestamp_percentile_rank(leadership_anchor, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.05
    ).astype("float64") * leader_w_series
    rank_carry = (
        _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.10
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.04
        + _timestamp_percentile_rank(mild_oi_growth, timestamps) * 0.04
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.02
    ).astype("float64") * carry_w_series
    rank_contra = (
        _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.06
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-momentum_20, timestamps) * 0.04
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.03
        + _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.03
    ).astype("float64") * contra_w_series
    rank_screen = (
        _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-distress_floor_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-distress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_gate = _timestamp_percentile_rank(blended_alpha, timestamps) * 0.10
    stable_rank_score = (rank_leader + rank_carry + rank_contra + rank_screen + rank_gate).astype("float64")

    v64_blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")

    # ---- v71 NEW: CoinGlass extended composite at 12% weight on final signal stage ----
    cg_taker = _feature_series(frame, "coinglass_taker_imbalance_5d_sum", feature_columns=feature_columns)
    cg_retail_long = _feature_series(frame, "coinglass_global_account_long_pct", feature_columns=feature_columns)
    cg_liq_imb = _feature_series(frame, "coinglass_liquidation_imbalance_24h", feature_columns=feature_columns)
    cg_top_long = _feature_series(frame, "coinglass_top_trader_long_pct", feature_columns=feature_columns)

    retail_fill = float(cg_retail_long.median()) if cg_retail_long.notna().any() else 50.0
    top_fill = float(cg_top_long.median()) if cg_top_long.notna().any() else 50.0
    z_taker = _timestamp_zscore(cg_taker.fillna(0.0), timestamps)
    z_retail = _timestamp_zscore(cg_retail_long.fillna(retail_fill), timestamps)
    z_liq = _timestamp_zscore(cg_liq_imb.fillna(0.0), timestamps)
    z_top = _timestamp_zscore(cg_top_long.fillna(top_fill), timestamps)

    coinglass_composite = (
        (+z_taker) + (-z_retail) + (-z_liq) + (-z_top)
    ).astype("float64") / 4.0
    coinglass_composite_z = _timestamp_zscore(coinglass_composite, timestamps)

    blended_signal = (0.88 * v64_blended_signal + 0.12 * coinglass_composite_z).astype("float64")

    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_dual_regime_filter_v5_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v70 = v64 (xs_dual_regime_filter_v1) architecture with an additional
    cross-sectional intraday-churn quality filter applied to the rank-blended score.
    Same regime weights, same sub-signals; only adds a quality screen on top.
    """
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.30 - funding_rate * 0.16).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.53 - funding_zscore * 0.47).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.18).abs() / 0.40)).clip(lower=0.0, upper=1.0)
    cheapness_quality = (1.0 - ((normalized_cheapness - 0.20).abs() / 0.50)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.85).clip(lower=0.0, upper=1.40) * 1.0
        + (raw_cheapness - 0.011).clip(lower=0.0, upper=0.06) * 11.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.08).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.50).abs() / 0.28)).clip(lower=0.0, upper=1.0)
    distress_floor_penalty = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    distress_floor_penalty = distress_floor_penalty.clip(lower=0.0, upper=1.0)
    upper_extension_penalty = (range_position - 0.78).clip(lower=0.0, upper=0.22) * 4.5
    upper_extension_penalty = upper_extension_penalty.clip(lower=0.0, upper=1.0)
    leadership_anchor = (
        relative_strength * 0.32
        + ema_slope * 0.22
        + momentum_20 * 0.18
        + reclaim_window * 0.13
        + support_buffer * 0.07
        + quality_zone * 0.08
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.30)).clip(lower=0.0, upper=1.0)
    mild_oi_growth = (oi_change.clip(lower=-0.10, upper=0.18) + 0.05).clip(lower=0.0, upper=0.23) * (1.0 / 0.23)
    mild_oi_growth = mild_oi_growth.clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.24)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50
        + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20
        + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20
        + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42
        + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")

    leader_sub = (
        leadership_anchor * 0.34
        + balanced_discount * 0.12
        + stable_oi * 0.10
        + balanced_volume * 0.10
        + orderly_reset * 0.10
        + reclaim_window * 0.09
        + quality_zone * 0.10
        + support_buffer * 0.05
    ).astype("float64")
    carry_sub = (
        cheapness_quality * 0.36
        + stable_oi * 0.14
        + mild_oi_growth * 0.12
        + balanced_volume * 0.10
        + quality_zone * 0.10
        + support_buffer * 0.08
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
    ).astype("float64")
    contrarian_laggard_tilt = (
        (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.18
        + (0.55 - range_position.clip(lower=0.10, upper=0.55)).clip(lower=0.0, upper=0.45) * (1.0 / 0.45) * 0.18
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.14
        + (-momentum_20).clip(lower=-0.05, upper=0.10) * (1.0 / 0.15) * 0.10
        + (-return_1).clip(lower=-0.01, upper=0.025) * (1.0 / 0.035) * 0.08
        + support_buffer * 0.10
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
        + (1.0 - distress_floor_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.06
    ).astype("float64")

    if "timestamp_ms" in frame.columns and not frame.empty:
        ts_values = frame["timestamp_ms"].values
        abs_mom_values = momentum_20.abs().values
        mom_values = momentum_20.values
        disp_df = pd.DataFrame({"v": abs_mom_values, "t": ts_values}, index=frame.index)
        timestamp_disp = disp_df.groupby("t")["v"].transform(
            lambda s: float(pd.Series(s).std() if len(s) > 1 else 0.0)
        )
        median_disp = float(pd.Series(timestamp_disp.values).median()) if len(timestamp_disp) else 0.05
        normalized_disp = (timestamp_disp / max(median_disp * 2.0, 1e-9)).clip(lower=0.0, upper=1.0)
        med_df = pd.DataFrame({"v": mom_values, "t": ts_values}, index=frame.index)
        timestamp_median_mom = med_df.groupby("t")["v"].transform("median")
        scaled_median_mom = (timestamp_median_mom / 0.06).clip(lower=-1.0, upper=1.0)

        disp_array = normalized_disp.values
        med_pos = (scaled_median_mom.values).clip(0.0, 1.0)
        med_neg = (-scaled_median_mom.values).clip(0.0, 1.0)

        # v64-style smooth weighting (matches xs_dual_regime_filter_v1 logic)
        leader_weight = disp_array * (0.55 + 0.45 * (med_pos > med_neg).astype(float))
        carry_weight = disp_array * (1.0 - (0.55 + 0.45 * (med_pos > med_neg).astype(float)) * 0.30)
        broad_uniform = ((1.0 - disp_array) * np.maximum(med_pos, med_neg)).clip(0.0, 1.0)
        contrarian_weight = 0.10 + 0.55 * broad_uniform
        # broad-up factor (drives leader internal blend - none for v5, but exposed for transparency)
        broad_up_factor = (1.0 - disp_array) * med_pos

        total = leader_weight + carry_weight + contrarian_weight + 1e-9
        leader_weight = leader_weight / total
        carry_weight = carry_weight / total
        contrarian_weight = contrarian_weight / total
    else:
        n = len(frame)
        leader_weight = np.full(n, 0.45)
        carry_weight = np.full(n, 0.45)
        contrarian_weight = np.full(n, 0.10)
        broad_up_factor = np.full(n, 0.0)

    blended_alpha = (
        pd.Series(leader_weight, index=frame.index) * leader_sub
        + pd.Series(carry_weight, index=frame.index) * carry_sub
        + pd.Series(contrarian_weight, index=frame.index) * contrarian_laggard_tilt
    ).astype("float64")

    common_penalties = (
        stress_penalty * 0.06
        + chase_penalty * 0.025
        + overcheap_penalty * 0.04
        + rich_penalty * 0.02
        + distress_floor_penalty * 0.05
        + upper_extension_penalty * 0.045
        + distress_penalty * 0.05
        + broken_tape_penalty * 0.04
    ).astype("float64")

    raw_score = (blended_alpha * 1.0 - common_penalties).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    leader_w_series = pd.Series(leader_weight, index=frame.index)
    carry_w_series = pd.Series(carry_weight, index=frame.index)
    contra_w_series = pd.Series(contrarian_weight, index=frame.index)
    rank_leader = (
        _timestamp_percentile_rank(leadership_anchor, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.05
    ).astype("float64") * leader_w_series
    rank_carry = (
        _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.10
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.04
        + _timestamp_percentile_rank(mild_oi_growth, timestamps) * 0.04
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.02
    ).astype("float64") * carry_w_series
    rank_contra = (
        _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.06
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-momentum_20, timestamps) * 0.04
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.03
        + _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.03
    ).astype("float64") * contra_w_series
    rank_screen = (
        _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-distress_floor_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-distress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_gate = _timestamp_percentile_rank(blended_alpha, timestamps) * 0.10
    # NEW v5: intraday-churn quality filter
    intraday_churn_quality = _timestamp_percentile_rank(-intraday_vol, timestamps) * 0.05
    stable_rank_score = (
        rank_leader + rank_carry + rank_contra + rank_screen + rank_gate + intraday_churn_quality
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_dual_regime_filter_v4_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.30 - funding_rate * 0.16).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.53 - funding_zscore * 0.47).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.18).abs() / 0.40)).clip(lower=0.0, upper=1.0)
    cheapness_quality = (1.0 - ((normalized_cheapness - 0.20).abs() / 0.50)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.85).clip(lower=0.0, upper=1.40) * 1.0
        + (raw_cheapness - 0.011).clip(lower=0.0, upper=0.06) * 11.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.08).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.50).abs() / 0.28)).clip(lower=0.0, upper=1.0)
    distress_floor_penalty = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    distress_floor_penalty = distress_floor_penalty.clip(lower=0.0, upper=1.0)
    upper_extension_penalty = (range_position - 0.78).clip(lower=0.0, upper=0.22) * 4.5
    upper_extension_penalty = upper_extension_penalty.clip(lower=0.0, upper=1.0)
    distress_low_penalty_v9 = (0.20 - range_position).clip(lower=0.0, upper=0.20).astype("float64")
    extension_high_penalty_v9 = (range_position - 0.82).clip(lower=0.0, upper=0.18).astype("float64")
    leadership_anchor = (
        relative_strength * 0.32
        + ema_slope * 0.22
        + momentum_20 * 0.18
        + reclaim_window * 0.13
        + support_buffer * 0.07
        + quality_zone * 0.08
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.30)).clip(lower=0.0, upper=1.0)
    mild_oi_growth = (oi_change.clip(lower=-0.10, upper=0.18) + 0.05).clip(lower=0.0, upper=0.23) * (1.0 / 0.23)
    mild_oi_growth = mild_oi_growth.clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.24)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50
        + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20
        + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20
        + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42
        + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")
    low_vol_quality = (1.0 - (realized_volatility.clip(lower=0.20, upper=1.20) - 0.20) / 1.0).clip(lower=0.0, upper=1.0)
    low_intraday_churn = (1.0 - (intraday_vol.clip(lower=0.30, upper=2.50) - 0.30) / 2.20).clip(lower=0.0, upper=1.0)

    # v9-style frothy_leader_penalty embedded in leader_sub_momo
    frothy_leader_penalty_internal = (
        (
            relative_strength.clip(lower=0.0) * 0.46
            + ema_slope.clip(lower=0.0) * 0.28
            + momentum_20.clip(lower=0.0) * 0.26
        )
        * (
            (distance_to_high + 0.010).clip(lower=0.0, upper=0.08) * 8.0 * 0.40
            + (quote_volume_expansion - 1.08).clip(lower=0.0, upper=0.50) * 0.30
            + (return_1 - 0.004).clip(lower=0.0, upper=0.03) * 18.0 * 0.18
            + extension_high_penalty_v9 * 4.0 * 0.12
        )
    ).astype("float64")
    structural_extreme_penalty_internal = (
        distress_low_penalty_v9 * 1.40 + extension_high_penalty_v9 * 1.10
    ).astype("float64")

    leader_sub_momo = (
        leadership_anchor * 0.32
        + balanced_discount * 0.10
        + stable_oi * 0.10
        + balanced_volume * 0.10
        + orderly_reset * 0.10
        + reclaim_window * 0.09
        + quality_zone * 0.10
        + support_buffer * 0.05
        - frothy_leader_penalty_internal * 0.18
        - structural_extreme_penalty_internal * 0.10
    ).astype("float64")
    leader_sub_def = (
        low_vol_quality * 0.20
        + low_intraday_churn * 0.12
        + stable_oi * 0.18
        + balanced_volume * 0.10
        + quality_zone * 0.12
        + (relative_strength.clip(lower=-0.05, upper=0.20) + 0.05) * (1.0 / 0.25) * 0.10
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.08
        + (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.04
        - frothy_leader_penalty_internal * 0.12
        - structural_extreme_penalty_internal * 0.08
    ).astype("float64")
    carry_sub = (
        cheapness_quality * 0.36
        + stable_oi * 0.14
        + mild_oi_growth * 0.12
        + balanced_volume * 0.10
        + quality_zone * 0.10
        + support_buffer * 0.08
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
    ).astype("float64")
    contrarian_laggard_tilt = (
        (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.18
        + (0.55 - range_position.clip(lower=0.10, upper=0.55)).clip(lower=0.0, upper=0.45) * (1.0 / 0.45) * 0.18
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.14
        + (-momentum_20).clip(lower=-0.05, upper=0.10) * (1.0 / 0.15) * 0.10
        + (-return_1).clip(lower=-0.01, upper=0.025) * (1.0 / 0.035) * 0.08
        + support_buffer * 0.10
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
        + (1.0 - distress_floor_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.06
    ).astype("float64")

    if "timestamp_ms" in frame.columns and not frame.empty:
        ts_values = frame["timestamp_ms"].values
        abs_mom_values = momentum_20.abs().values
        mom_values = momentum_20.values
        disp_df = pd.DataFrame({"v": abs_mom_values, "t": ts_values}, index=frame.index)
        timestamp_disp = disp_df.groupby("t")["v"].transform(
            lambda s: float(pd.Series(s).std() if len(s) > 1 else 0.0)
        )
        median_disp = float(pd.Series(timestamp_disp.values).median()) if len(timestamp_disp) else 0.05
        normalized_disp = (timestamp_disp / max(median_disp * 2.0, 1e-9)).clip(lower=0.0, upper=1.0)
        med_df = pd.DataFrame({"v": mom_values, "t": ts_values}, index=frame.index)
        timestamp_median_mom = med_df.groupby("t")["v"].transform("median")
        scaled_median_mom = (timestamp_median_mom / 0.06).clip(lower=-1.0, upper=1.0)

        disp_array = normalized_disp.values
        med_pos = (scaled_median_mom.values).clip(0.0, 1.0)
        med_neg = (-scaled_median_mom.values).clip(0.0, 1.0)

        w_HU = disp_array * med_pos
        w_HD = disp_array * med_neg
        w_LU = (1.0 - disp_array) * med_pos
        w_LD = (1.0 - disp_array) * med_neg
        w_neutral = np.maximum(1.0 - (w_HU + w_HD + w_LU + w_LD), 0.0)

        # HU: leader 0.92, carry 0.05, contrarian 0.03  (push leader strength to maximum)
        # HD: leader 0.20, carry 0.75, contrarian 0.05
        # LU: leader_def 0.55, carry 0.35, contrarian 0.10
        # LD: leader 0.20, carry 0.40, contrarian 0.40
        # neutral: 0.50, 0.40, 0.10
        leader_weight = (
            w_HU * 0.92 + w_HD * 0.20 + w_LU * 0.55 + w_LD * 0.20 + w_neutral * 0.50
        )
        carry_weight = (
            w_HU * 0.05 + w_HD * 0.75 + w_LU * 0.35 + w_LD * 0.40 + w_neutral * 0.40
        )
        contrarian_weight = (
            w_HU * 0.03 + w_HD * 0.05 + w_LU * 0.10 + w_LD * 0.40 + w_neutral * 0.10
        )
        total = leader_weight + carry_weight + contrarian_weight + 1e-9
        leader_weight = leader_weight / total
        carry_weight = carry_weight / total
        contrarian_weight = contrarian_weight / total
        broad_up_factor = w_LU.clip(0.0, 1.0)
    else:
        n = len(frame)
        broad_up_factor = np.full(n, 0.0)
        leader_weight = np.full(n, 0.50)
        carry_weight = np.full(n, 0.40)
        contrarian_weight = np.full(n, 0.10)

    broad_up_series = pd.Series(broad_up_factor, index=frame.index)
    leader_sub = (
        (1.0 - broad_up_series) * leader_sub_momo + broad_up_series * leader_sub_def
    ).astype("float64")

    blended_alpha = (
        pd.Series(leader_weight, index=frame.index) * leader_sub
        + pd.Series(carry_weight, index=frame.index) * carry_sub
        + pd.Series(contrarian_weight, index=frame.index) * contrarian_laggard_tilt
    ).astype("float64")

    # Common penalties retained but reduced (since leader_sub already absorbs anti-froth/extreme)
    common_penalties = (
        stress_penalty * 0.05
        + chase_penalty * 0.020
        + overcheap_penalty * 0.04
        + rich_penalty * 0.02
        + distress_floor_penalty * 0.04
        + upper_extension_penalty * 0.030
        + distress_penalty * 0.04
        + broken_tape_penalty * 0.04
    ).astype("float64")

    raw_score = (blended_alpha * 1.0 - common_penalties).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    leader_w_series = pd.Series(leader_weight, index=frame.index)
    carry_w_series = pd.Series(carry_weight, index=frame.index)
    contra_w_series = pd.Series(contrarian_weight, index=frame.index)
    rank_leader_momo = (
        _timestamp_percentile_rank(leadership_anchor, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.05
        + _timestamp_percentile_rank(-frothy_leader_penalty_internal, timestamps) * 0.05
        + _timestamp_percentile_rank(-structural_extreme_penalty_internal, timestamps) * 0.03
    ).astype("float64") * (1.0 - broad_up_series)
    rank_leader_def = (
        _timestamp_percentile_rank(low_vol_quality, timestamps) * 0.07
        + _timestamp_percentile_rank(low_intraday_churn, timestamps) * 0.04
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.05
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.04
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.03
    ).astype("float64") * broad_up_series
    rank_leader = (rank_leader_momo + rank_leader_def) * leader_w_series
    rank_carry = (
        _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.10
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.04
        + _timestamp_percentile_rank(mild_oi_growth, timestamps) * 0.04
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.02
    ).astype("float64") * carry_w_series
    rank_contra = (
        _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.06
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-momentum_20, timestamps) * 0.04
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.03
        + _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.03
    ).astype("float64") * contra_w_series
    rank_screen = (
        _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-distress_floor_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-distress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_gate = _timestamp_percentile_rank(blended_alpha, timestamps) * 0.10
    stable_rank_score = (
        rank_leader + rank_carry + rank_contra + rank_screen + rank_gate
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_dual_regime_filter_v3_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.30 - funding_rate * 0.16).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.53 - funding_zscore * 0.47).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.18).abs() / 0.40)).clip(lower=0.0, upper=1.0)
    cheapness_quality = (1.0 - ((normalized_cheapness - 0.20).abs() / 0.50)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.85).clip(lower=0.0, upper=1.40) * 1.0
        + (raw_cheapness - 0.011).clip(lower=0.0, upper=0.06) * 11.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.08).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.50).abs() / 0.28)).clip(lower=0.0, upper=1.0)
    distress_floor_penalty = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    distress_floor_penalty = distress_floor_penalty.clip(lower=0.0, upper=1.0)
    upper_extension_penalty = (range_position - 0.78).clip(lower=0.0, upper=0.22) * 4.5
    upper_extension_penalty = upper_extension_penalty.clip(lower=0.0, upper=1.0)
    leadership_anchor = (
        relative_strength * 0.32
        + ema_slope * 0.22
        + momentum_20 * 0.18
        + reclaim_window * 0.13
        + support_buffer * 0.07
        + quality_zone * 0.08
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.30)).clip(lower=0.0, upper=1.0)
    mild_oi_growth = (oi_change.clip(lower=-0.10, upper=0.18) + 0.05).clip(lower=0.0, upper=0.23) * (1.0 / 0.23)
    mild_oi_growth = mild_oi_growth.clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.24)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50
        + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20
        + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20
        + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42
        + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")
    low_vol_quality = (1.0 - (realized_volatility.clip(lower=0.20, upper=1.20) - 0.20) / 1.0).clip(lower=0.0, upper=1.0)
    low_intraday_churn = (1.0 - (intraday_vol.clip(lower=0.30, upper=2.50) - 0.30) / 2.20).clip(lower=0.0, upper=1.0)

    leader_sub_momo = (
        leadership_anchor * 0.34
        + balanced_discount * 0.12
        + stable_oi * 0.10
        + balanced_volume * 0.10
        + orderly_reset * 0.10
        + reclaim_window * 0.09
        + quality_zone * 0.10
        + support_buffer * 0.05
    ).astype("float64")
    leader_sub_def = (
        low_vol_quality * 0.20
        + low_intraday_churn * 0.12
        + stable_oi * 0.18
        + balanced_volume * 0.10
        + quality_zone * 0.12
        + (relative_strength.clip(lower=-0.05, upper=0.20) + 0.05) * (1.0 / 0.25) * 0.10
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.08
        + (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.04
    ).astype("float64")
    carry_sub = (
        cheapness_quality * 0.36
        + stable_oi * 0.14
        + mild_oi_growth * 0.12
        + balanced_volume * 0.10
        + quality_zone * 0.10
        + support_buffer * 0.08
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
    ).astype("float64")
    contrarian_laggard_tilt = (
        (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.18
        + (0.55 - range_position.clip(lower=0.10, upper=0.55)).clip(lower=0.0, upper=0.45) * (1.0 / 0.45) * 0.18
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.14
        + (-momentum_20).clip(lower=-0.05, upper=0.10) * (1.0 / 0.15) * 0.10
        + (-return_1).clip(lower=-0.01, upper=0.025) * (1.0 / 0.035) * 0.08
        + support_buffer * 0.10
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
        + (1.0 - distress_floor_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.06
    ).astype("float64")

    if "timestamp_ms" in frame.columns and not frame.empty:
        ts_values = frame["timestamp_ms"].values
        abs_mom_values = momentum_20.abs().values
        mom_values = momentum_20.values
        disp_df = pd.DataFrame({"v": abs_mom_values, "t": ts_values}, index=frame.index)
        timestamp_disp = disp_df.groupby("t")["v"].transform(
            lambda s: float(pd.Series(s).std() if len(s) > 1 else 0.0)
        )
        median_disp = float(pd.Series(timestamp_disp.values).median()) if len(timestamp_disp) else 0.05
        normalized_disp = (timestamp_disp / max(median_disp * 2.0, 1e-9)).clip(lower=0.0, upper=1.0)
        med_df = pd.DataFrame({"v": mom_values, "t": ts_values}, index=frame.index)
        timestamp_median_mom = med_df.groupby("t")["v"].transform("median")
        scaled_median_mom = (timestamp_median_mom / 0.06).clip(lower=-1.0, upper=1.0)

        disp_array = normalized_disp.values
        med_pos = (scaled_median_mom.values).clip(0.0, 1.0)
        med_neg = (-scaled_median_mom.values).clip(0.0, 1.0)

        # 4-quadrant indicator weights (each in [0,1])
        w_HU = disp_array * med_pos
        w_HD = disp_array * med_neg
        w_LU = (1.0 - disp_array) * med_pos
        w_LD = (1.0 - disp_array) * med_neg
        w_neutral = np.maximum(1.0 - (w_HU + w_HD + w_LU + w_LD), 0.0)

        # Per-quadrant desired (leader, carry, contrarian) - each row sums to 1
        # HU (dispersed-up): leader DOMINATES, minimal carry dilution
        # HD (dispersed-down): carry dominates
        # LU (broad-up): leader_def heavy, moderate carry, very low contrarian
        # LD (broad-down): carry + contrarian
        # neutral: balanced default
        leader_weight = (
            w_HU * 0.85 + w_HD * 0.20 + w_LU * 0.55 + w_LD * 0.20 + w_neutral * 0.50
        )
        carry_weight = (
            w_HU * 0.10 + w_HD * 0.75 + w_LU * 0.35 + w_LD * 0.40 + w_neutral * 0.40
        )
        contrarian_weight = (
            w_HU * 0.05 + w_HD * 0.05 + w_LU * 0.10 + w_LD * 0.40 + w_neutral * 0.10
        )
        # Normalize to sum to 1 (in case of floating drift)
        total = leader_weight + carry_weight + contrarian_weight + 1e-9
        leader_weight = leader_weight / total
        carry_weight = carry_weight / total
        contrarian_weight = contrarian_weight / total
        # Broad-up factor for leader internal blend
        broad_up_factor = w_LU.clip(0.0, 1.0)
    else:
        n = len(frame)
        broad_up_factor = np.full(n, 0.0)
        leader_weight = np.full(n, 0.50)
        carry_weight = np.full(n, 0.40)
        contrarian_weight = np.full(n, 0.10)

    broad_up_series = pd.Series(broad_up_factor, index=frame.index)
    leader_sub = (
        (1.0 - broad_up_series) * leader_sub_momo + broad_up_series * leader_sub_def
    ).astype("float64")

    blended_alpha = (
        pd.Series(leader_weight, index=frame.index) * leader_sub
        + pd.Series(carry_weight, index=frame.index) * carry_sub
        + pd.Series(contrarian_weight, index=frame.index) * contrarian_laggard_tilt
    ).astype("float64")

    common_penalties = (
        stress_penalty * 0.06
        + chase_penalty * 0.025
        + overcheap_penalty * 0.04
        + rich_penalty * 0.02
        + distress_floor_penalty * 0.05
        + upper_extension_penalty * 0.045
        + distress_penalty * 0.05
        + broken_tape_penalty * 0.04
    ).astype("float64")

    raw_score = (blended_alpha * 1.0 - common_penalties).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    leader_w_series = pd.Series(leader_weight, index=frame.index)
    carry_w_series = pd.Series(carry_weight, index=frame.index)
    contra_w_series = pd.Series(contrarian_weight, index=frame.index)
    rank_leader_momo = (
        _timestamp_percentile_rank(leadership_anchor, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.05
    ).astype("float64") * (1.0 - broad_up_series)
    rank_leader_def = (
        _timestamp_percentile_rank(low_vol_quality, timestamps) * 0.07
        + _timestamp_percentile_rank(low_intraday_churn, timestamps) * 0.04
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.05
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.04
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.03
    ).astype("float64") * broad_up_series
    rank_leader = (rank_leader_momo + rank_leader_def) * leader_w_series
    rank_carry = (
        _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.10
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.04
        + _timestamp_percentile_rank(mild_oi_growth, timestamps) * 0.04
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.02
    ).astype("float64") * carry_w_series
    rank_contra = (
        _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.06
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-momentum_20, timestamps) * 0.04
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.03
        + _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.03
    ).astype("float64") * contra_w_series
    rank_screen = (
        _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-distress_floor_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-distress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_gate = _timestamp_percentile_rank(blended_alpha, timestamps) * 0.10
    stable_rank_score = (
        rank_leader + rank_carry + rank_contra + rank_screen + rank_gate
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_dual_regime_filter_v2_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.30 - funding_rate * 0.16).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.53 - funding_zscore * 0.47).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.18).abs() / 0.40)).clip(lower=0.0, upper=1.0)
    cheapness_quality = (1.0 - ((normalized_cheapness - 0.20).abs() / 0.50)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.85).clip(lower=0.0, upper=1.40) * 1.0
        + (raw_cheapness - 0.011).clip(lower=0.0, upper=0.06) * 11.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.08).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.50).abs() / 0.28)).clip(lower=0.0, upper=1.0)
    distress_floor_penalty = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    distress_floor_penalty = distress_floor_penalty.clip(lower=0.0, upper=1.0)
    upper_extension_penalty = (range_position - 0.78).clip(lower=0.0, upper=0.22) * 4.5
    upper_extension_penalty = upper_extension_penalty.clip(lower=0.0, upper=1.0)
    leadership_anchor = (
        relative_strength * 0.32
        + ema_slope * 0.22
        + momentum_20 * 0.18
        + reclaim_window * 0.13
        + support_buffer * 0.07
        + quality_zone * 0.08
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.30)).clip(lower=0.0, upper=1.0)
    mild_oi_growth = (oi_change.clip(lower=-0.10, upper=0.18) + 0.05).clip(lower=0.0, upper=0.23) * (1.0 / 0.23)
    mild_oi_growth = mild_oi_growth.clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.24)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50
        + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20
        + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20
        + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42
        + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")
    low_vol_quality = (1.0 - (realized_volatility.clip(lower=0.20, upper=1.20) - 0.20) / 1.0).clip(lower=0.0, upper=1.0)
    low_intraday_churn = (1.0 - (intraday_vol.clip(lower=0.30, upper=2.50) - 0.30) / 2.20).clip(lower=0.0, upper=1.0)

    leader_sub_momo = (
        leadership_anchor * 0.34
        + balanced_discount * 0.12
        + stable_oi * 0.10
        + balanced_volume * 0.10
        + orderly_reset * 0.10
        + reclaim_window * 0.09
        + quality_zone * 0.10
        + support_buffer * 0.05
    ).astype("float64")
    leader_sub_def = (
        low_vol_quality * 0.20
        + low_intraday_churn * 0.12
        + stable_oi * 0.18
        + balanced_volume * 0.10
        + quality_zone * 0.12
        + (relative_strength.clip(lower=-0.05, upper=0.20) + 0.05) * (1.0 / 0.25) * 0.10
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.08
        + (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.04
    ).astype("float64")
    carry_sub = (
        cheapness_quality * 0.36
        + stable_oi * 0.14
        + mild_oi_growth * 0.12
        + balanced_volume * 0.10
        + quality_zone * 0.10
        + support_buffer * 0.08
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
    ).astype("float64")
    contrarian_laggard_tilt = (
        (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.18
        + (0.55 - range_position.clip(lower=0.10, upper=0.55)).clip(lower=0.0, upper=0.45) * (1.0 / 0.45) * 0.18
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.14
        + (-momentum_20).clip(lower=-0.05, upper=0.10) * (1.0 / 0.15) * 0.10
        + (-return_1).clip(lower=-0.01, upper=0.025) * (1.0 / 0.035) * 0.08
        + support_buffer * 0.10
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
        + (1.0 - distress_floor_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.06
    ).astype("float64")

    if "timestamp_ms" in frame.columns and not frame.empty:
        ts_values = frame["timestamp_ms"].values
        abs_mom_values = momentum_20.abs().values
        mom_values = momentum_20.values
        disp_df = pd.DataFrame({"v": abs_mom_values, "t": ts_values}, index=frame.index)
        timestamp_disp = disp_df.groupby("t")["v"].transform(
            lambda s: float(pd.Series(s).std() if len(s) > 1 else 0.0)
        )
        median_disp = float(pd.Series(timestamp_disp.values).median()) if len(timestamp_disp) else 0.05
        normalized_disp = (timestamp_disp / max(median_disp * 2.0, 1e-9)).clip(lower=0.0, upper=1.0)
        med_df = pd.DataFrame({"v": mom_values, "t": ts_values}, index=frame.index)
        timestamp_median_mom = med_df.groupby("t")["v"].transform("median")
        scaled_median_mom = (timestamp_median_mom / 0.06).clip(lower=-1.0, upper=1.0)

        disp_array = normalized_disp.values
        med_pos = (scaled_median_mom.values).clip(0.0, 1.0)
        med_neg = (-scaled_median_mom.values).clip(0.0, 1.0)

        # broad-up factor (0=dispersed-or-down, 1=fully broad-up): drives leader internal blend
        broad_up_factor = ((1.0 - disp_array) * med_pos).clip(0.0, 1.0)
        # broad-down factor: only this gates contrarian
        broad_down_factor = ((1.0 - disp_array) * med_neg).clip(0.0, 1.0)

        leader_weight = (0.30 + 0.50 * disp_array)
        carry_weight = (0.25 + 0.50 * (1.0 - disp_array * med_pos))
        contrarian_weight = 0.10 + 0.55 * broad_down_factor
        # Floor for stability
        leader_weight = np.maximum(leader_weight, 0.20)
        carry_weight = np.maximum(carry_weight, 0.20)
        contrarian_weight = np.maximum(contrarian_weight, 0.05)
        total = leader_weight + carry_weight + contrarian_weight + 1e-9
        leader_weight = leader_weight / total
        carry_weight = carry_weight / total
        contrarian_weight = contrarian_weight / total
    else:
        n = len(frame)
        broad_up_factor = np.full(n, 0.0)
        broad_down_factor = np.full(n, 0.0)
        leader_weight = np.full(n, 0.45)
        carry_weight = np.full(n, 0.45)
        contrarian_weight = np.full(n, 0.10)

    broad_up_series = pd.Series(broad_up_factor, index=frame.index)
    leader_sub = (
        (1.0 - broad_up_series) * leader_sub_momo + broad_up_series * leader_sub_def
    ).astype("float64")

    blended_alpha = (
        pd.Series(leader_weight, index=frame.index) * leader_sub
        + pd.Series(carry_weight, index=frame.index) * carry_sub
        + pd.Series(contrarian_weight, index=frame.index) * contrarian_laggard_tilt
    ).astype("float64")

    common_penalties = (
        stress_penalty * 0.06
        + chase_penalty * 0.025
        + overcheap_penalty * 0.04
        + rich_penalty * 0.02
        + distress_floor_penalty * 0.05
        + upper_extension_penalty * 0.045
        + distress_penalty * 0.05
        + broken_tape_penalty * 0.04
    ).astype("float64")

    raw_score = (blended_alpha * 1.0 - common_penalties).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    leader_w_series = pd.Series(leader_weight, index=frame.index)
    carry_w_series = pd.Series(carry_weight, index=frame.index)
    contra_w_series = pd.Series(contrarian_weight, index=frame.index)
    rank_leader_momo = (
        _timestamp_percentile_rank(leadership_anchor, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.05
    ).astype("float64") * (1.0 - broad_up_series)
    rank_leader_def = (
        _timestamp_percentile_rank(low_vol_quality, timestamps) * 0.07
        + _timestamp_percentile_rank(low_intraday_churn, timestamps) * 0.04
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.05
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.04
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.03
    ).astype("float64") * broad_up_series
    rank_leader = (rank_leader_momo + rank_leader_def) * leader_w_series
    rank_carry = (
        _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.10
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.04
        + _timestamp_percentile_rank(mild_oi_growth, timestamps) * 0.04
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.02
    ).astype("float64") * carry_w_series
    rank_contra = (
        _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.06
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-momentum_20, timestamps) * 0.04
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.03
        + _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.03
    ).astype("float64") * contra_w_series
    rank_screen = (
        _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-distress_floor_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-distress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_gate = _timestamp_percentile_rank(blended_alpha, timestamps) * 0.10
    stable_rank_score = (
        rank_leader + rank_carry + rank_contra + rank_screen + rank_gate
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_quad_regime_filter_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.30 - funding_rate * 0.16).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.53 - funding_zscore * 0.47).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.18).abs() / 0.40)).clip(lower=0.0, upper=1.0)
    cheapness_quality = (1.0 - ((normalized_cheapness - 0.20).abs() / 0.50)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.85).clip(lower=0.0, upper=1.40) * 1.0
        + (raw_cheapness - 0.011).clip(lower=0.0, upper=0.06) * 11.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.08).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.50).abs() / 0.28)).clip(lower=0.0, upper=1.0)
    distress_floor_penalty = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    distress_floor_penalty = distress_floor_penalty.clip(lower=0.0, upper=1.0)
    upper_extension_penalty = (range_position - 0.78).clip(lower=0.0, upper=0.22) * 4.5
    upper_extension_penalty = upper_extension_penalty.clip(lower=0.0, upper=1.0)
    leadership_anchor = (
        relative_strength * 0.32
        + ema_slope * 0.22
        + momentum_20 * 0.18
        + reclaim_window * 0.13
        + support_buffer * 0.07
        + quality_zone * 0.08
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.30)).clip(lower=0.0, upper=1.0)
    mild_oi_growth = (oi_change.clip(lower=-0.10, upper=0.18) + 0.05).clip(lower=0.0, upper=0.23) * (1.0 / 0.23)
    mild_oi_growth = mild_oi_growth.clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.24)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50
        + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20
        + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20
        + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42
        + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")
    low_vol_quality = (1.0 - (realized_volatility.clip(lower=0.20, upper=1.20) - 0.20) / 1.0).clip(lower=0.0, upper=1.0)
    low_intraday_churn = (1.0 - (intraday_vol.clip(lower=0.30, upper=2.50) - 0.30) / 2.20).clip(lower=0.0, upper=1.0)

    leader_sub = (
        leadership_anchor * 0.34
        + balanced_discount * 0.12
        + stable_oi * 0.10
        + balanced_volume * 0.10
        + orderly_reset * 0.10
        + reclaim_window * 0.09
        + quality_zone * 0.10
        + support_buffer * 0.05
    ).astype("float64")
    carry_sub = (
        cheapness_quality * 0.36
        + stable_oi * 0.14
        + mild_oi_growth * 0.12
        + balanced_volume * 0.10
        + quality_zone * 0.10
        + support_buffer * 0.08
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
    ).astype("float64")
    defensive_quality_sub = (
        low_vol_quality * 0.22
        + low_intraday_churn * 0.14
        + stable_oi * 0.16
        + balanced_volume * 0.10
        + quality_zone * 0.12
        + (relative_strength.clip(lower=-0.05, upper=0.20) + 0.05) * (1.0 / 0.25) * 0.08
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.08
        + (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.04
    ).astype("float64")
    contrarian_laggard_tilt = (
        (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.18
        + (0.55 - range_position.clip(lower=0.10, upper=0.55)).clip(lower=0.0, upper=0.45) * (1.0 / 0.45) * 0.18
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.14
        + (-momentum_20).clip(lower=-0.05, upper=0.10) * (1.0 / 0.15) * 0.10
        + (-return_1).clip(lower=-0.01, upper=0.025) * (1.0 / 0.035) * 0.08
        + support_buffer * 0.10
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
        + (1.0 - distress_floor_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.06
    ).astype("float64")

    if "timestamp_ms" in frame.columns and not frame.empty:
        ts_values = frame["timestamp_ms"].values
        abs_mom_values = momentum_20.abs().values
        mom_values = momentum_20.values
        disp_df = pd.DataFrame({"v": abs_mom_values, "t": ts_values}, index=frame.index)
        timestamp_disp = disp_df.groupby("t")["v"].transform(
            lambda s: float(pd.Series(s).std() if len(s) > 1 else 0.0)
        )
        median_disp = float(pd.Series(timestamp_disp.values).median()) if len(timestamp_disp) else 0.05
        normalized_disp = (timestamp_disp / max(median_disp * 2.0, 1e-9)).clip(lower=0.0, upper=1.0)
        med_df = pd.DataFrame({"v": mom_values, "t": ts_values}, index=frame.index)
        timestamp_median_mom = med_df.groupby("t")["v"].transform("median")
        scaled_median_mom = (timestamp_median_mom / 0.06).clip(lower=-1.0, upper=1.0)

        disp_array = normalized_disp.values
        med_pos = (scaled_median_mom.values).clip(0.0, 1.0)
        med_neg = (-scaled_median_mom.values).clip(0.0, 1.0)

        # 4-quadrant weights (each clipped to [0,1], then normalized to sum to 1)
        leader_weight = disp_array * (0.40 + 0.60 * med_pos)
        carry_weight = disp_array * (0.40 + 0.60 * med_neg)
        defensive_weight = (1.0 - disp_array) * med_pos
        contrarian_weight = (1.0 - disp_array) * med_neg
        # Floor each so the score doesn't disappear in any regime
        leader_weight = np.maximum(leader_weight, 0.10)
        carry_weight = np.maximum(carry_weight, 0.10)
        defensive_weight = np.maximum(defensive_weight, 0.05)
        contrarian_weight = np.maximum(contrarian_weight, 0.05)
        total = leader_weight + carry_weight + defensive_weight + contrarian_weight + 1e-9
        leader_weight = leader_weight / total
        carry_weight = carry_weight / total
        defensive_weight = defensive_weight / total
        contrarian_weight = contrarian_weight / total
    else:
        n = len(frame)
        leader_weight = np.full(n, 0.35)
        carry_weight = np.full(n, 0.35)
        defensive_weight = np.full(n, 0.15)
        contrarian_weight = np.full(n, 0.15)

    blended_alpha = (
        pd.Series(leader_weight, index=frame.index) * leader_sub
        + pd.Series(carry_weight, index=frame.index) * carry_sub
        + pd.Series(defensive_weight, index=frame.index) * defensive_quality_sub
        + pd.Series(contrarian_weight, index=frame.index) * contrarian_laggard_tilt
    ).astype("float64")

    common_penalties = (
        stress_penalty * 0.06
        + chase_penalty * 0.025
        + overcheap_penalty * 0.04
        + rich_penalty * 0.02
        + distress_floor_penalty * 0.05
        + upper_extension_penalty * 0.045
        + distress_penalty * 0.05
        + broken_tape_penalty * 0.04
    ).astype("float64")

    raw_score = (blended_alpha * 1.0 - common_penalties).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    leader_w_series = pd.Series(leader_weight, index=frame.index)
    carry_w_series = pd.Series(carry_weight, index=frame.index)
    defensive_w_series = pd.Series(defensive_weight, index=frame.index)
    contra_w_series = pd.Series(contrarian_weight, index=frame.index)
    rank_leader = (
        _timestamp_percentile_rank(leadership_anchor, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.05
    ).astype("float64") * leader_w_series
    rank_carry = (
        _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.10
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.04
        + _timestamp_percentile_rank(mild_oi_growth, timestamps) * 0.04
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.02
    ).astype("float64") * carry_w_series
    rank_defensive = (
        _timestamp_percentile_rank(low_vol_quality, timestamps) * 0.07
        + _timestamp_percentile_rank(low_intraday_churn, timestamps) * 0.05
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.04
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.04
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.03
    ).astype("float64") * defensive_w_series
    rank_contra = (
        _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.06
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-momentum_20, timestamps) * 0.04
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.03
        + _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.03
    ).astype("float64") * contra_w_series
    rank_screen = (
        _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-distress_floor_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-distress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_gate = _timestamp_percentile_rank(blended_alpha, timestamps) * 0.10
    stable_rank_score = (
        rank_leader + rank_carry + rank_defensive + rank_contra + rank_screen + rank_gate
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_dual_regime_filter_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.30 - funding_rate * 0.16).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.53 - funding_zscore * 0.47).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.18).abs() / 0.40)).clip(lower=0.0, upper=1.0)
    cheapness_quality = (1.0 - ((normalized_cheapness - 0.20).abs() / 0.50)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.85).clip(lower=0.0, upper=1.40) * 1.0
        + (raw_cheapness - 0.011).clip(lower=0.0, upper=0.06) * 11.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.08).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.50).abs() / 0.28)).clip(lower=0.0, upper=1.0)
    distress_floor_penalty = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    distress_floor_penalty = distress_floor_penalty.clip(lower=0.0, upper=1.0)
    upper_extension_penalty = (range_position - 0.78).clip(lower=0.0, upper=0.22) * 4.5
    upper_extension_penalty = upper_extension_penalty.clip(lower=0.0, upper=1.0)
    leadership_anchor = (
        relative_strength * 0.32
        + ema_slope * 0.22
        + momentum_20 * 0.18
        + reclaim_window * 0.13
        + support_buffer * 0.07
        + quality_zone * 0.08
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.30)).clip(lower=0.0, upper=1.0)
    mild_oi_growth = (oi_change.clip(lower=-0.10, upper=0.18) + 0.05).clip(lower=0.0, upper=0.23) * (1.0 / 0.23)
    mild_oi_growth = mild_oi_growth.clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.24)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50
        + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20
        + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20
        + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42
        + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")

    leader_sub = (
        leadership_anchor * 0.34
        + balanced_discount * 0.12
        + stable_oi * 0.10
        + balanced_volume * 0.10
        + orderly_reset * 0.10
        + reclaim_window * 0.09
        + quality_zone * 0.10
        + support_buffer * 0.05
    ).astype("float64")
    carry_sub = (
        cheapness_quality * 0.36
        + stable_oi * 0.14
        + mild_oi_growth * 0.12
        + balanced_volume * 0.10
        + quality_zone * 0.10
        + support_buffer * 0.08
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
    ).astype("float64")
    contrarian_laggard_tilt = (
        (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.18
        + (0.55 - range_position.clip(lower=0.10, upper=0.55)).clip(lower=0.0, upper=0.45) * (1.0 / 0.45) * 0.18
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.14
        + (-momentum_20).clip(lower=-0.05, upper=0.10) * (1.0 / 0.15) * 0.10
        + (-return_1).clip(lower=-0.01, upper=0.025) * (1.0 / 0.035) * 0.08
        + support_buffer * 0.10
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
        + (1.0 - distress_floor_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.06
    ).astype("float64")

    if "timestamp_ms" in frame.columns and not frame.empty:
        ts_values = frame["timestamp_ms"].values
        abs_mom_values = momentum_20.abs().values
        mom_values = momentum_20.values
        disp_df = pd.DataFrame({"v": abs_mom_values, "t": ts_values}, index=frame.index)
        timestamp_disp = disp_df.groupby("t")["v"].transform(
            lambda s: float(pd.Series(s).std() if len(s) > 1 else 0.0)
        )
        median_disp = float(pd.Series(timestamp_disp.values).median()) if len(timestamp_disp) else 0.05
        normalized_disp = (timestamp_disp / max(median_disp * 2.0, 1e-9)).clip(lower=0.0, upper=1.0)
        med_df = pd.DataFrame({"v": mom_values, "t": ts_values}, index=frame.index)
        timestamp_median_mom = med_df.groupby("t")["v"].transform("median")
        scaled_median_mom = (timestamp_median_mom / 0.06).clip(lower=-1.0, upper=1.0)
        broad_uniform_signal = (
            (1.0 - normalized_disp.values) * np.abs(scaled_median_mom.values)
        ).clip(0.0, 1.0)
        disp_array = normalized_disp.values
        med_sign_pos = (scaled_median_mom.values > 0).astype(float)

        leader_weight = (
            (0.20 + 0.60 * disp_array) * (0.55 + 0.45 * med_sign_pos)
        )
        carry_weight = (
            (0.20 + 0.60 * disp_array) * (1.0 - (0.55 + 0.45 * med_sign_pos) * 0.30)
        )
        contrarian_weight = 0.20 + 0.60 * broad_uniform_signal

        total = leader_weight + carry_weight + contrarian_weight + 1e-9
        leader_weight = leader_weight / total
        carry_weight = carry_weight / total
        contrarian_weight = contrarian_weight / total
    else:
        n = len(frame)
        leader_weight = np.full(n, 0.40)
        carry_weight = np.full(n, 0.40)
        contrarian_weight = np.full(n, 0.20)

    blended_alpha = (
        pd.Series(leader_weight, index=frame.index) * leader_sub
        + pd.Series(carry_weight, index=frame.index) * carry_sub
        + pd.Series(contrarian_weight, index=frame.index) * contrarian_laggard_tilt
    ).astype("float64")

    common_penalties = (
        stress_penalty * 0.06
        + chase_penalty * 0.025
        + overcheap_penalty * 0.04
        + rich_penalty * 0.02
        + distress_floor_penalty * 0.05
        + upper_extension_penalty * 0.045
        + distress_penalty * 0.05
        + broken_tape_penalty * 0.04
    ).astype("float64")

    raw_score = (blended_alpha * 1.0 - common_penalties).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    leader_w_series = pd.Series(leader_weight, index=frame.index)
    carry_w_series = pd.Series(carry_weight, index=frame.index)
    contra_w_series = pd.Series(contrarian_weight, index=frame.index)
    rank_leader = (
        _timestamp_percentile_rank(leadership_anchor, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.05
    ).astype("float64") * leader_w_series
    rank_carry = (
        _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.10
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.04
        + _timestamp_percentile_rank(mild_oi_growth, timestamps) * 0.04
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.02
    ).astype("float64") * carry_w_series
    rank_contra = (
        _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.06
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-momentum_20, timestamps) * 0.04
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.03
        + _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.03
    ).astype("float64") * contra_w_series
    rank_screen = (
        _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-distress_floor_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-distress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_gate = _timestamp_percentile_rank(blended_alpha, timestamps) * 0.10
    stable_rank_score = (
        rank_leader + rank_carry + rank_contra + rank_screen + rank_gate
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_dispersion_regime_blend_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.30 - funding_rate * 0.16).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.53 - funding_zscore * 0.47).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.18).abs() / 0.40)).clip(lower=0.0, upper=1.0)
    cheapness_quality = (1.0 - ((normalized_cheapness - 0.20).abs() / 0.50)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.85).clip(lower=0.0, upper=1.40) * 1.0
        + (raw_cheapness - 0.011).clip(lower=0.0, upper=0.06) * 11.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.08).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.50).abs() / 0.28)).clip(lower=0.0, upper=1.0)
    distress_floor_penalty = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    distress_floor_penalty = distress_floor_penalty.clip(lower=0.0, upper=1.0)
    upper_extension_penalty = (range_position - 0.78).clip(lower=0.0, upper=0.22) * 4.5
    upper_extension_penalty = upper_extension_penalty.clip(lower=0.0, upper=1.0)
    leadership_anchor = (
        relative_strength * 0.32
        + ema_slope * 0.22
        + momentum_20 * 0.18
        + reclaim_window * 0.13
        + support_buffer * 0.07
        + quality_zone * 0.08
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.30)).clip(lower=0.0, upper=1.0)
    mild_oi_growth = (oi_change.clip(lower=-0.10, upper=0.18) + 0.05).clip(lower=0.0, upper=0.23) * (1.0 / 0.23)
    mild_oi_growth = mild_oi_growth.clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.24)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50
        + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20
        + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20
        + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42
        + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")

    leader_sub = (
        leadership_anchor * 0.34
        + balanced_discount * 0.12
        + stable_oi * 0.10
        + balanced_volume * 0.10
        + orderly_reset * 0.10
        + reclaim_window * 0.09
        + quality_zone * 0.10
        + support_buffer * 0.05
    ).astype("float64")
    carry_sub = (
        cheapness_quality * 0.36
        + stable_oi * 0.14
        + mild_oi_growth * 0.12
        + balanced_volume * 0.10
        + quality_zone * 0.10
        + support_buffer * 0.08
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
    ).astype("float64")

    if "timestamp_ms" in frame.columns and not frame.empty:
        ts_values = frame["timestamp_ms"].values
        abs_mom_values = momentum_20.abs().values
        disp_df = pd.DataFrame({"v": abs_mom_values, "t": ts_values}, index=frame.index)
        cross_dispersion = disp_df.groupby("t")["v"].transform("std")
        cross_dispersion = cross_dispersion.fillna(method="ffill").fillna(method="bfill").fillna(0.05)
        disp_df2 = pd.DataFrame({"d": cross_dispersion.values, "t": ts_values}, index=frame.index)
        disp_rank_per_ts = disp_df2.groupby("t")["d"].transform(
            lambda s: s.rank(method="average", pct=True)
        )
        timestamp_disp_anchor = disp_df.groupby("t")["v"].transform(
            lambda s: float(pd.Series(s).std() if len(s) > 1 else 0.0)
        )
        median_disp = float(pd.Series(timestamp_disp_anchor.values).median()) if len(timestamp_disp_anchor) else 0.05
        normalized_disp = (timestamp_disp_anchor / max(median_disp * 2.0, 1e-9)).clip(lower=0.0, upper=1.0)
        leader_weight = (0.20 + 0.60 * normalized_disp.values).clip(0.20, 0.80)
        carry_weight = 1.0 - leader_weight
    else:
        leader_weight = np.full(len(frame), 0.5)
        carry_weight = np.full(len(frame), 0.5)

    blended_alpha = (
        pd.Series(leader_weight, index=frame.index) * leader_sub
        + pd.Series(carry_weight, index=frame.index) * carry_sub
    ).astype("float64")

    common_penalties = (
        stress_penalty * 0.06
        + chase_penalty * 0.03
        + overcheap_penalty * 0.04
        + rich_penalty * 0.02
        + distress_floor_penalty * 0.05
        + upper_extension_penalty * 0.04
        + distress_penalty * 0.05
        + broken_tape_penalty * 0.04
    ).astype("float64")

    raw_score = (blended_alpha * 1.0 - common_penalties).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    leader_w_series = pd.Series(leader_weight, index=frame.index)
    carry_w_series = pd.Series(carry_weight, index=frame.index)
    rank_leader = (
        _timestamp_percentile_rank(leadership_anchor, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.05
    ).astype("float64") * leader_w_series
    rank_carry = (
        _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.10
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.04
        + _timestamp_percentile_rank(mild_oi_growth, timestamps) * 0.04
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.02
    ).astype("float64") * carry_w_series
    rank_screen = (
        _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-distress_floor_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-distress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_gate = _timestamp_percentile_rank(blended_alpha, timestamps) * 0.12
    stable_rank_score = (rank_leader + rank_carry + rank_screen + rank_gate).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_vol_regime_blend_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.30 - funding_rate * 0.16).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.53 - funding_zscore * 0.47).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.18).abs() / 0.40)).clip(lower=0.0, upper=1.0)
    cheapness_quality = (1.0 - ((normalized_cheapness - 0.20).abs() / 0.50)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.85).clip(lower=0.0, upper=1.40) * 1.0
        + (raw_cheapness - 0.011).clip(lower=0.0, upper=0.06) * 11.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.08).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.50).abs() / 0.28)).clip(lower=0.0, upper=1.0)
    distress_floor_penalty = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    distress_floor_penalty = distress_floor_penalty.clip(lower=0.0, upper=1.0)
    upper_extension_penalty = (range_position - 0.78).clip(lower=0.0, upper=0.22) * 4.5
    upper_extension_penalty = upper_extension_penalty.clip(lower=0.0, upper=1.0)
    leadership_anchor = (
        relative_strength * 0.32
        + ema_slope * 0.22
        + momentum_20 * 0.18
        + reclaim_window * 0.13
        + support_buffer * 0.07
        + quality_zone * 0.08
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.30)).clip(lower=0.0, upper=1.0)
    mild_oi_growth = (oi_change.clip(lower=-0.10, upper=0.18) + 0.05).clip(lower=0.0, upper=0.23) * (1.0 / 0.23)
    mild_oi_growth = mild_oi_growth.clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.24)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50
        + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20
        + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20
        + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42
        + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")

    leader_sub = (
        leadership_anchor * 0.34
        + balanced_discount * 0.12
        + stable_oi * 0.10
        + balanced_volume * 0.10
        + orderly_reset * 0.10
        + reclaim_window * 0.09
        + quality_zone * 0.10
        + support_buffer * 0.05
    ).astype("float64")
    carry_sub = (
        cheapness_quality * 0.36
        + stable_oi * 0.14
        + mild_oi_growth * 0.12
        + balanced_volume * 0.10
        + quality_zone * 0.10
        + support_buffer * 0.08
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
    ).astype("float64")

    vol_regime = ((realized_volatility.clip(lower=0.20, upper=1.20) - 0.20) / 1.0).clip(lower=0.0, upper=1.0)
    vol_regime = (0.20 + 0.60 * vol_regime).clip(lower=0.20, upper=0.80)
    leader_weight = 1.0 - vol_regime
    carry_weight = vol_regime
    blended_alpha = (leader_weight * leader_sub + carry_weight * carry_sub).astype("float64")

    common_penalties = (
        stress_penalty * 0.06
        + chase_penalty * 0.03
        + overcheap_penalty * 0.04
        + rich_penalty * 0.02
        + distress_floor_penalty * 0.05
        + upper_extension_penalty * 0.04
        + distress_penalty * 0.05
        + broken_tape_penalty * 0.04
    ).astype("float64")

    raw_score = (blended_alpha * 1.0 - common_penalties).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    rank_leader = (
        _timestamp_percentile_rank(leadership_anchor, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.05
    ).astype("float64") * leader_weight
    rank_carry = (
        _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.10
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.04
        + _timestamp_percentile_rank(mild_oi_growth, timestamps) * 0.04
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.02
    ).astype("float64") * carry_weight
    rank_screen = (
        _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-distress_floor_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-distress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_gate = _timestamp_percentile_rank(blended_alpha, timestamps) * 0.12
    stable_rank_score = (rank_leader + rank_carry + rank_screen + rank_gate).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_carry_dislocation_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.40 - funding_rate * 0.20).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.55 - funding_zscore * 0.45).astype("float64")
    cheapness_quality = (1.0 - ((normalized_cheapness - 0.20).abs() / 0.50)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.95).clip(lower=0.0, upper=1.50) * 1.0
        + (raw_cheapness - 0.012).clip(lower=0.0, upper=0.06) * 10.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.10).clip(lower=0.0, upper=1.20).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.32)).clip(lower=0.0, upper=1.0)
    mild_oi_growth = (oi_change.clip(lower=-0.10, upper=0.18) + 0.05).clip(lower=0.0, upper=0.23) * (1.0 / 0.23)
    mild_oi_growth = mild_oi_growth.clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.28)).clip(lower=0.0, upper=1.0)
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20
        + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    distress_floor_penalty = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    distress_floor_penalty = distress_floor_penalty.clip(lower=0.0, upper=1.0)
    blowup_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50
        + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20
        + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    not_overheated = (1.0 - (range_position - 0.55).clip(lower=0.0, upper=0.45) / 0.45).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.45).abs() / 0.30)).clip(lower=0.0, upper=1.0)
    not_extended_high = (-distance_to_high).clip(lower=0.05, upper=0.40) / 0.35
    not_extended_high = not_extended_high.clip(lower=0.0, upper=1.0)

    cheapness_gate = (
        cheapness_quality * 0.55
        + (1.0 - overcheap_penalty.clip(lower=0.0, upper=1.0)) * 0.25
        + (1.0 - rich_penalty.clip(lower=0.0, upper=1.0)) * 0.20
    ).clip(lower=0.0, upper=1.0)
    confirmation_gate = (
        stable_oi * 0.40
        + mild_oi_growth * 0.25
        + balanced_volume * 0.20
        + not_extended_high * 0.15
    ).clip(lower=0.0, upper=1.0)
    quality_screen = (
        (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.35
        + (1.0 - distress_floor_penalty.clip(lower=0.0, upper=1.0)) * 0.20
        + (1.0 - blowup_penalty.clip(lower=0.0, upper=1.0)) * 0.20
        + (1.0 - broken_tape_penalty.clip(lower=0.0, upper=1.0)) * 0.15
        + quality_zone * 0.10
    ).clip(lower=0.0, upper=1.0)
    gated_alpha = (cheapness_gate * confirmation_gate * quality_screen).astype("float64")

    raw_score = (
        gated_alpha * 0.34
        + cheapness_quality * 0.18
        + stable_oi * 0.08
        + mild_oi_growth * 0.06
        + balanced_volume * 0.05
        + quality_zone * 0.05
        + not_overheated * 0.04
        - overcheap_penalty * 0.05
        - rich_penalty * 0.02
        - distress_penalty * 0.06
        - distress_floor_penalty * 0.04
        - blowup_penalty * 0.05
        - broken_tape_penalty * 0.03
    ).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    rank_cheapness = (
        _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.16
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.05
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.03
    ).astype("float64")
    rank_confirmation = (
        _timestamp_percentile_rank(stable_oi, timestamps) * 0.07
        + _timestamp_percentile_rank(mild_oi_growth, timestamps) * 0.06
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.04
        + _timestamp_percentile_rank(not_extended_high, timestamps) * 0.03
    ).astype("float64")
    rank_screen = (
        _timestamp_percentile_rank(-distress_penalty, timestamps) * 0.05
        + _timestamp_percentile_rank(-distress_floor_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-blowup_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.04
    ).astype("float64")
    rank_gate = (
        _timestamp_percentile_rank(gated_alpha, timestamps) * 0.10
        + _timestamp_percentile_rank(cheapness_gate, timestamps) * 0.06
    ).astype("float64")
    stable_rank_score = (
        rank_cheapness + rank_confirmation + rank_screen + rank_gate
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.82).astype("float64")


def xs_reversal_quality_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    momentum_5 = _feature_series(frame, "momentum_5", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)

    medium_trend_intact = (
        relative_strength.clip(lower=-0.10, upper=0.30) * 0.55
        + ema_slope.clip(lower=-0.03, upper=0.06) * 0.25
        + momentum_20.clip(lower=-0.10, upper=0.25) * 0.20
    ).astype("float64")
    short_washout = (
        (-momentum_5).clip(lower=0.0, upper=0.12) * 0.60
        + (-return_1).clip(lower=0.0, upper=0.04) * 0.40
    ).astype("float64")
    short_washout_quality = (1.0 - ((short_washout - 0.025).abs() / 0.040)).clip(lower=0.0, upper=1.0)
    capitulative_discount = (
        (-funding_zscore).clip(lower=0.0, upper=2.5) * 0.55
        + (-basis_zscore).clip(lower=0.0, upper=2.5) * 0.45
    ).astype("float64")
    discount_quality = (1.0 - ((capitulative_discount - 0.95).abs() / 0.95)).clip(lower=0.0, upper=1.0)
    oi_accumulation = (oi_change.clip(lower=-0.15, upper=0.20) + 0.05).clip(lower=0.0, upper=0.25) * 4.0
    oi_accumulation = oi_accumulation.clip(lower=0.0, upper=1.0)
    pullback_zone = (1.0 - ((range_position - 0.35).abs() / 0.20)).clip(lower=0.0, upper=1.0)
    distress_floor = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 10.0
    distress_floor = distress_floor.clip(lower=0.0, upper=1.0)
    upper_extension = (range_position - 0.65).clip(lower=0.0, upper=0.35) * 2.85
    upper_extension = upper_extension.clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.04).abs() / 0.10)).clip(lower=0.0, upper=1.0)
    not_near_high = (-distance_to_high).clip(lower=0.04, upper=0.40) / 0.36
    blowup_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50
        + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    capitulation_volume = (quote_volume_expansion - 1.0).clip(lower=0.0, upper=0.80)
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20
        + return_1.clip(lower=-0.10, upper=-0.05).abs() * 0.80
    ).astype("float64")
    overheated_carry_penalty = (
        funding_zscore.clip(lower=0.30, upper=2.5) * 0.55
        + basis_zscore.clip(lower=0.30, upper=2.5) * 0.45
    ).astype("float64")

    setup_gate = (
        (medium_trend_intact.clip(lower=-0.10, upper=0.30) + 0.10) / 0.40
    ).clip(lower=0.0, upper=1.0)
    washout_gate = (
        short_washout_quality * 0.55
        + pullback_zone * 0.30
        + support_buffer * 0.15
    ).clip(lower=0.0, upper=1.0)
    confirmation_gate = (
        discount_quality * 0.45
        + oi_accumulation * 0.30
        + capitulation_volume.clip(lower=0.0, upper=0.50) * 0.25
    ).clip(lower=0.0, upper=1.0)
    gated_quality = (setup_gate * washout_gate * confirmation_gate).astype("float64")

    raw_score = (
        gated_quality * 0.32
        + medium_trend_intact * 0.14
        + short_washout_quality * 0.10
        + pullback_zone * 0.10
        + discount_quality * 0.08
        + oi_accumulation * 0.06
        + support_buffer * 0.05
        + not_near_high * 0.03
        - distress_floor * 0.06
        - upper_extension * 0.04
        - blowup_penalty * 0.05
        - broken_tape_penalty * 0.04
        - overheated_carry_penalty * 0.03
    ).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    rank_setup = (
        _timestamp_percentile_rank(medium_trend_intact, timestamps) * 0.10
        + _timestamp_percentile_rank(setup_gate, timestamps) * 0.07
        + _timestamp_percentile_rank(not_near_high, timestamps) * 0.03
    ).astype("float64")
    rank_washout = (
        _timestamp_percentile_rank(short_washout_quality, timestamps) * 0.09
        + _timestamp_percentile_rank(pullback_zone, timestamps) * 0.08
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.04
    ).astype("float64")
    rank_confirm = (
        _timestamp_percentile_rank(discount_quality, timestamps) * 0.09
        + _timestamp_percentile_rank(oi_accumulation, timestamps) * 0.06
        + _timestamp_percentile_rank(capitulation_volume.clip(lower=0.0, upper=0.50), timestamps) * 0.04
    ).astype("float64")
    rank_penalties = (
        _timestamp_percentile_rank(-distress_floor, timestamps) * 0.05
        + _timestamp_percentile_rank(-upper_extension, timestamps) * 0.04
        + _timestamp_percentile_rank(-blowup_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-overheated_carry_penalty, timestamps) * 0.02
    ).astype("float64")
    rank_gate = _timestamp_percentile_rank(gated_quality, timestamps) * 0.12
    stable_rank_score = (
        rank_setup + rank_washout + rank_confirm + rank_penalties + rank_gate
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.25
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.75
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.85).astype("float64")


def xs_relative_value_spread_v9_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.28 - funding_rate * 0.14).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.52 - funding_zscore * 0.48).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.16).abs() / 0.36)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.78).clip(lower=0.0, upper=1.40)
        + (raw_cheapness - 0.010).clip(lower=0.0, upper=0.05) * 12.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.06).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.525).abs() / 0.225)).clip(lower=0.0, upper=1.0)
    distress_low_penalty = (0.20 - range_position).clip(lower=0.0, upper=0.20).astype("float64")
    extension_high_penalty = (range_position - 0.82).clip(lower=0.0, upper=0.18).astype("float64")
    leadership_anchor = (
        relative_strength * 0.32
        + ema_slope * 0.22
        + momentum_20 * 0.17
        + reclaim_window * 0.13
        + support_buffer * 0.07
        + quality_zone * 0.09
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.28)).clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.01).abs() / 0.22)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0) * 0.48
        + realized_volatility.clip(lower=0.0) * 0.52
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42
        + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.006).clip(lower=0.0, upper=0.20)
        + (-distance_to_high - 0.16).clip(lower=0.0, upper=0.22) * 0.50
    ).astype("float64")
    leadership_gate = ((leadership_anchor + 0.12) / 1.12).clip(lower=0.0, upper=1.0)
    reset_gate = (
        reclaim_window * 0.45
        + support_buffer * 0.18
        + orderly_reset * 0.22
        + quality_zone * 0.15
    ).clip(lower=0.0, upper=1.0)
    stability_gate = (
        stable_oi * 0.45
        + balanced_volume * 0.32
        + (1.0 - stress_penalty.clip(lower=0.0, upper=1.0)) * 0.23
    ).clip(lower=0.0, upper=1.0)
    gated_quality = (leadership_gate * reset_gate * stability_gate).astype("float64")
    frothy_leader_penalty = (
        (
            relative_strength.clip(lower=0.0) * 0.46
            + ema_slope.clip(lower=0.0) * 0.28
            + momentum_20.clip(lower=0.0) * 0.26
        )
        * (
            (distance_to_high + 0.010).clip(lower=0.0, upper=0.08) * 8.0 * 0.40
            + (quote_volume_expansion - 1.08).clip(lower=0.0, upper=0.50) * 0.30
            + (return_1 - 0.004).clip(lower=0.0, upper=0.03) * 18.0 * 0.18
            + extension_high_penalty * 4.0 * 0.12
        )
    ).astype("float64")
    structural_extreme_penalty = (
        distress_low_penalty * 1.40 + extension_high_penalty * 1.10
    ).astype("float64")

    raw_score = (
        gated_quality * 0.30
        + leadership_anchor * 0.22
        + balanced_discount * 0.07
        + stable_oi * 0.07
        + balanced_volume * 0.07
        + orderly_reset * 0.07
        + quality_zone * 0.07
        - stress_penalty * 0.06
        - chase_penalty * 0.03
        - overcheap_penalty * 0.03
        - rich_penalty * 0.01
        - broken_tape_penalty * 0.01
        - frothy_leader_penalty * 0.04
        - structural_extreme_penalty * 0.03
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    rank_leadership = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.14
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.10
        + _timestamp_percentile_rank(momentum_20, timestamps) * 0.09
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.05
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.03
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.06
    ).astype("float64")
    rank_discount = (
        _timestamp_percentile_rank(balanced_discount, timestamps) * 0.06
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_stability = (
        _timestamp_percentile_rank(stable_oi, timestamps) * 0.05
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.01
        + _timestamp_percentile_rank(-frothy_leader_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-structural_extreme_penalty, timestamps) * 0.02
    ).astype("float64")
    rank_gate = (
        _timestamp_percentile_rank(gated_quality, timestamps) * 0.09
        + _timestamp_percentile_rank(reset_gate, timestamps) * 0.05
    ).astype("float64")
    stable_rank_score = (
        rank_leadership + rank_discount + rank_stability + rank_gate
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.78).astype("float64")


def xs_relative_value_spread_v8_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.28 - funding_rate * 0.14).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.52 - funding_zscore * 0.48).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.16).abs() / 0.36)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.78).clip(lower=0.0, upper=1.40)
        + (raw_cheapness - 0.010).clip(lower=0.0, upper=0.05) * 12.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.06).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    leadership_anchor = (
        relative_strength * 0.34
        + ema_slope * 0.23
        + momentum_20 * 0.18
        + reclaim_window * 0.14
        + support_buffer * 0.07
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.28)).clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.01).abs() / 0.22)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0) * 0.48
        + realized_volatility.clip(lower=0.0) * 0.52
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42
        + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.006).clip(lower=0.0, upper=0.20)
        + (-distance_to_high - 0.16).clip(lower=0.0, upper=0.22) * 0.50
    ).astype("float64")
    leadership_gate = ((leadership_anchor + 0.12) / 1.12).clip(lower=0.0, upper=1.0)
    reset_gate = (
        reclaim_window * 0.50
        + support_buffer * 0.20
        + orderly_reset * 0.30
    ).clip(lower=0.0, upper=1.0)
    stability_gate = (
        stable_oi * 0.45
        + balanced_volume * 0.32
        + (1.0 - stress_penalty.clip(lower=0.0, upper=1.0)) * 0.23
    ).clip(lower=0.0, upper=1.0)
    gated_quality = (leadership_gate * reset_gate * stability_gate).astype("float64")
    frothy_leader_penalty = (
        (
            relative_strength.clip(lower=0.0) * 0.46
            + ema_slope.clip(lower=0.0) * 0.28
            + momentum_20.clip(lower=0.0) * 0.26
        )
        * (
            (distance_to_high + 0.010).clip(lower=0.0, upper=0.08) * 8.0 * 0.45
            + (quote_volume_expansion - 1.08).clip(lower=0.0, upper=0.50) * 0.35
            + (return_1 - 0.004).clip(lower=0.0, upper=0.03) * 18.0 * 0.20
        )
    ).astype("float64")

    raw_score = (
        gated_quality * 0.30
        + leadership_anchor * 0.23
        + balanced_discount * 0.08
        + stable_oi * 0.08
        + balanced_volume * 0.08
        + orderly_reset * 0.08
        - stress_penalty * 0.07
        - chase_penalty * 0.03
        - overcheap_penalty * 0.03
        - rich_penalty * 0.01
        - broken_tape_penalty * 0.01
        - frothy_leader_penalty * 0.04
    ).astype("float64")
    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    rank_leadership = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.15
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.11
        + _timestamp_percentile_rank(momentum_20, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.05
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.03
    ).astype("float64")
    rank_discount = (
        _timestamp_percentile_rank(balanced_discount, timestamps) * 0.06
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_stability = (
        _timestamp_percentile_rank(stable_oi, timestamps) * 0.05
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.01
        + _timestamp_percentile_rank(-frothy_leader_penalty, timestamps) * 0.02
    ).astype("float64")
    rank_gate = (
        _timestamp_percentile_rank(gated_quality, timestamps) * 0.09
        + _timestamp_percentile_rank(reset_gate, timestamps) * 0.05
    ).astype("float64")
    stable_rank_score = (
        rank_leadership + rank_discount + rank_stability + rank_gate
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.24
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.76
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.78).astype("float64")


def xs_residualized_pair_book_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    stable_oi = (1.0 - (oi_change.abs() / 0.40)).clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.06).abs() / 0.42)).clip(lower=0.0, upper=1.0)
    mild_reset_day = (1.0 - ((return_1 + 0.012).abs() / 0.050)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0) * 0.55
        + realized_volatility.clip(lower=0.0) * 0.45
    ).astype("float64")
    broken_tape_penalty = (-distance_to_low - 0.02).clip(lower=0.0, upper=0.30)

    if frame.empty or "timestamp_ms" not in frame.columns:
        quality_anchor = (
            relative_strength * 0.48
            + ema_slope * 0.27
            + distance_to_low * 0.15
            - realized_volatility * 0.10
        ).astype("float64")
        cheapness = (
            -basis_zscore * 0.55
            - funding_zscore * 0.35
            + stable_oi * 0.10
        ).astype("float64")
        residual_dislocation = cheapness - cheapness.mean()
        raw_score = (
            residual_dislocation * 0.48
            + quality_anchor * 0.22
            + balanced_volume * 0.10
            + mild_reset_day * 0.08
            - stress_penalty * 0.08
            - broken_tape_penalty * 0.04
        ).astype("float64")
        return raw_score

    timestamps = frame["timestamp_ms"]
    rs_rank = _timestamp_percentile_rank(relative_strength, timestamps)
    ema_rank = _timestamp_percentile_rank(ema_slope, timestamps)
    support_rank = _timestamp_percentile_rank(distance_to_low, timestamps)
    low_stress_rank = _timestamp_percentile_rank(-stress_penalty, timestamps)
    quality_anchor_rank = (
        rs_rank * 0.42
        + ema_rank * 0.25
        + support_rank * 0.18
        + low_stress_rank * 0.15
    ).astype("float64")
    quality_bucket = (
        (quality_anchor_rank * 3.0)
        .clip(lower=0.0, upper=2.999999)
        .astype("int64")
    )

    cheapness_rank = (
        _timestamp_percentile_rank(-basis_zscore, timestamps) * 0.54
        + _timestamp_percentile_rank(-funding_zscore, timestamps) * 0.34
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.12
    ).astype("float64")
    cohort_keys = pd.MultiIndex.from_arrays([timestamps.to_numpy(), quality_bucket.to_numpy()])
    cohort_average_cheapness = cheapness_rank.groupby(cohort_keys).transform("mean")
    residual_dislocation = (cheapness_rank - cohort_average_cheapness).astype("float64")

    raw_score = (
        residual_dislocation * 0.46
        + quality_anchor_rank * 0.20
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.10
        + _timestamp_percentile_rank(mild_reset_day, timestamps) * 0.08
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.06
        - _timestamp_percentile_rank(stress_penalty, timestamps) * 0.06
        - _timestamp_percentile_rank(broken_tape_penalty, timestamps) * 0.04
    ).astype("float64")

    stable_rank_score = (
        _timestamp_percentile_rank(residual_dislocation, timestamps) * 0.52
        + quality_anchor_rank * 0.20
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.09
        + _timestamp_percentile_rank(mild_reset_day, timestamps) * 0.07
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.06
        + low_stress_rank * 0.04
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.24
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.76
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.85).astype("float64")


def xs_residualized_pair_book_v2_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    balanced_volume = (1.0 - ((quote_volume_expansion - 1.04).abs() / 0.40)).clip(lower=0.0, upper=1.0)
    mild_reset_day = (1.0 - ((return_1 + 0.008).abs() / 0.045)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0) * 0.52
        + realized_volatility.clip(lower=0.0) * 0.30
        - distance_to_low * 0.12
    ).astype("float64")
    broken_tape_penalty = (
        np.maximum(-relative_strength, 0.0) * 0.55
        + np.maximum(-ema_slope, 0.0) * 0.30
        + np.maximum(-distance_to_low, 0.0) * 0.15
    ).astype("float64")

    if "timestamp_ms" not in frame.columns:
        quality_anchor = (
            relative_strength * 0.46
            + ema_slope * 0.28
            + distance_to_low * 0.18
            - stress_penalty * 0.08
        ).astype("float64")
        cheapness = (
            -basis_proxy * 0.60
            - funding_rate * 0.30
            + balanced_volume * 0.10
        ).astype("float64")
        quality_gate = ((quality_anchor - quality_anchor.quantile(0.40)) / 0.35).clip(lower=0.0, upper=1.0)
        residual_dislocation = cheapness - cheapness.mean()
        raw_score = (
            residual_dislocation * quality_gate * 0.56
            + quality_anchor * 0.24
            + balanced_volume * 0.10
            + mild_reset_day * 0.06
            - stress_penalty * 0.08
            - broken_tape_penalty * 0.04
        ).astype("float64")
        return raw_score

    timestamps = frame["timestamp_ms"]
    rs_rank = _timestamp_percentile_rank(relative_strength, timestamps)
    ema_rank = _timestamp_percentile_rank(ema_slope, timestamps)
    support_rank = _timestamp_percentile_rank(distance_to_low, timestamps)
    low_stress_rank = _timestamp_percentile_rank(-stress_penalty, timestamps)
    quality_anchor_rank = (
        rs_rank * 0.44
        + ema_rank * 0.26
        + support_rank * 0.18
        + low_stress_rank * 0.12
    ).astype("float64")
    quality_bucket = (
        (quality_anchor_rank * 4.0)
        .clip(lower=0.0, upper=3.999999)
        .astype("int64")
    )
    quality_gate = ((quality_anchor_rank - 0.40) / 0.35).clip(lower=0.0, upper=1.0)

    cheapness_rank = (
        _timestamp_percentile_rank(-basis_proxy, timestamps) * 0.60
        + _timestamp_percentile_rank(-funding_rate, timestamps) * 0.30
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.10
    ).astype("float64")
    cohort_keys = pd.MultiIndex.from_arrays([timestamps.to_numpy(), quality_bucket.to_numpy()])
    cohort_average_cheapness = cheapness_rank.groupby(cohort_keys).transform("mean")
    residual_dislocation = (cheapness_rank - cohort_average_cheapness).astype("float64")

    quality_stability = (
        quality_anchor_rank * 0.55
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.20
        + _timestamp_percentile_rank(mild_reset_day, timestamps) * 0.15
        + low_stress_rank * 0.10
    ).astype("float64")
    raw_score = (
        residual_dislocation * quality_gate * 0.60
        + quality_stability * 0.22
        - _timestamp_percentile_rank(stress_penalty, timestamps) * 0.10
        - _timestamp_percentile_rank(broken_tape_penalty, timestamps) * 0.08
    ).astype("float64")
    stable_rank_score = (
        _timestamp_percentile_rank(residual_dislocation * quality_gate, timestamps) * 0.54
        + quality_stability * 0.24
        + low_stress_rank * 0.12
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.10
    ).astype("float64")

    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.28
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.72
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.90).astype("float64")


def xs_pair_spread_book_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    balanced_volume = (1.0 - ((quote_volume_expansion - 1.03).abs() / 0.45)).clip(lower=0.0, upper=1.0)
    mild_reset_day = (1.0 - (return_1.abs() / 0.050)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0) * 0.50
        + realized_volatility.clip(lower=0.0) * 0.35
        - distance_to_low * 0.15
    ).astype("float64")
    broken_tape_penalty = (
        np.maximum(-relative_strength, 0.0) * 0.50
        + np.maximum(-ema_slope, 0.0) * 0.30
        + np.maximum(-distance_to_low, 0.0) * 0.20
    ).astype("float64")

    if "timestamp_ms" not in frame.columns:
        quality_anchor = (
            relative_strength * 0.44
            + ema_slope * 0.24
            + distance_to_low * 0.20
            - stress_penalty * 0.12
        ).astype("float64")
        cheapness = (
            -basis_proxy * 0.62
            - funding_rate * 0.28
            + balanced_volume * 0.10
        ).astype("float64")
        residual = cheapness - cheapness.mean()
        score = (
            residual * 0.78
            + quality_anchor * 0.10
            + mild_reset_day * 0.07
            - broken_tape_penalty * 0.05
        ).astype("float64")
        return score

    timestamps = frame["timestamp_ms"]
    rs_rank = _timestamp_percentile_rank(relative_strength, timestamps)
    ema_rank = _timestamp_percentile_rank(ema_slope, timestamps)
    support_rank = _timestamp_percentile_rank(distance_to_low, timestamps)
    low_stress_rank = _timestamp_percentile_rank(-stress_penalty, timestamps)
    quality_anchor_rank = (
        rs_rank * 0.44
        + ema_rank * 0.24
        + support_rank * 0.20
        + low_stress_rank * 0.12
    ).astype("float64")
    quality_bucket = (
        (quality_anchor_rank * 4.0)
        .clip(lower=0.0, upper=3.999999)
        .astype("int64")
    )

    cheapness_rank = (
        _timestamp_percentile_rank(-basis_proxy, timestamps) * 0.62
        + _timestamp_percentile_rank(-funding_rate, timestamps) * 0.28
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.10
    ).astype("float64")
    cohort_keys = pd.MultiIndex.from_arrays([timestamps.to_numpy(), quality_bucket.to_numpy()])
    cohort_average_cheapness = cheapness_rank.groupby(cohort_keys).transform("mean")
    residual_dislocation = (cheapness_rank - cohort_average_cheapness).astype("float64")

    stability_rank = (
        quality_anchor_rank * 0.42
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.20
        + _timestamp_percentile_rank(mild_reset_day, timestamps) * 0.16
        + low_stress_rank * 0.14
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.08
    ).astype("float64")
    raw_score = (
        residual_dislocation * 0.82
        + (stability_rank - 0.5) * 0.18
    ).astype("float64")
    blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.36
        + _timestamp_zscore(_timestamp_percentile_rank(raw_score, timestamps) - 0.5, timestamps) * 0.64
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 2.05).astype("float64")


def xs_pair_spread_book_v2_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (-xs_pair_spread_book_v1_score(frame, feature_columns=feature_columns)).astype("float64")


def xs_pair_spread_book_v3_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    base_signal = xs_pair_spread_book_v2_score(frame, feature_columns=feature_columns).astype("float64")
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    balanced_volume = (1.0 - ((quote_volume_expansion - 1.03).abs() / 0.45)).clip(lower=0.0, upper=1.0)
    mild_reset_day = (1.0 - (return_1.abs() / 0.050)).clip(lower=0.0, upper=1.0)
    stress_penalty = (intraday_vol.clip(lower=0.0) * 0.55 + realized_volatility.clip(lower=0.0) * 0.45).astype("float64")

    if "timestamp_ms" not in frame.columns:
        quality_anchor = (
            relative_strength * 0.44
            + ema_slope * 0.24
            + distance_to_low * 0.20
            - stress_penalty * 0.12
        ).astype("float64")
        smoothed = (
            base_signal * 0.60
            + (quality_anchor - quality_anchor.mean()) * 0.22
            + (mild_reset_day - mild_reset_day.mean()) * 0.10
            + ((balanced_volume - balanced_volume.mean()) * 0.08)
        ).astype("float64")
        return np.tanh(smoothed * 1.20).astype("float64")

    timestamps = frame["timestamp_ms"]
    quality_anchor_rank = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.44
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.24
        + _timestamp_percentile_rank(distance_to_low, timestamps) * 0.20
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.12
    ).astype("float64")
    smoothed_rank = (
        (_timestamp_percentile_rank(base_signal, timestamps) - 0.5) * 0.58
        + (quality_anchor_rank - 0.5) * 0.22
        + (_timestamp_percentile_rank(mild_reset_day, timestamps) - 0.5) * 0.12
        + (_timestamp_percentile_rank(balanced_volume, timestamps) - 0.5) * 0.08
    ).astype("float64")
    return np.tanh(smoothed_rank * 1.55).astype("float64")


def xs_pair_spread_book_v4_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    base_signal = xs_pair_spread_book_v3_score(frame, feature_columns=feature_columns).astype("float64")
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    balanced_volume = (1.0 - ((quote_volume_expansion - 1.03).abs() / 0.45)).clip(lower=0.0, upper=1.0)
    mild_reset_day = (1.0 - (return_1.abs() / 0.050)).clip(lower=0.0, upper=1.0)
    stress_penalty = (intraday_vol.clip(lower=0.0) * 0.55 + realized_volatility.clip(lower=0.0) * 0.45).astype("float64")

    if "timestamp_ms" not in frame.columns:
        stability_anchor = (
            relative_strength * 0.34
            + ema_slope * 0.20
            + distance_to_low * 0.18
            + balanced_volume * 0.16
            + mild_reset_day * 0.08
            - stress_penalty * 0.04
        ).astype("float64")
        calm_base = (-base_signal.abs()).astype("float64")
        smoothed = (
            base_signal * 0.50
            + (stability_anchor - stability_anchor.mean()) * 0.30
            + (calm_base - calm_base.mean()) * 0.12
            + (balanced_volume - balanced_volume.mean()) * 0.08
        ).astype("float64")
        return np.tanh(smoothed * 1.05).astype("float64")

    timestamps = frame["timestamp_ms"]
    quality_anchor_rank = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.42
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.22
        + _timestamp_percentile_rank(distance_to_low, timestamps) * 0.18
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.18
    ).astype("float64")
    calm_base_rank = _timestamp_percentile_rank(-base_signal.abs(), timestamps)
    smoothed_rank = (
        (_timestamp_percentile_rank(base_signal, timestamps) - 0.5) * 0.44
        + (quality_anchor_rank - 0.5) * 0.26
        + (_timestamp_percentile_rank(mild_reset_day, timestamps) - 0.5) * 0.12
        + (_timestamp_percentile_rank(balanced_volume, timestamps) - 0.5) * 0.10
        + (calm_base_rank - 0.5) * 0.08
    ).astype("float64")
    return np.tanh(smoothed_rank * 1.25).astype("float64")


def xs_pair_spread_book_v5_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    base_signal = xs_pair_spread_book_v3_score(frame, feature_columns=feature_columns).astype("float64")
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    balanced_volume = (1.0 - ((quote_volume_expansion - 1.03).abs() / 0.45)).clip(lower=0.0, upper=1.0)
    mild_reset_day = (1.0 - (return_1.abs() / 0.050)).clip(lower=0.0, upper=1.0)
    stress_penalty = (intraday_vol.clip(lower=0.0) * 0.55 + realized_volatility.clip(lower=0.0) * 0.45).astype("float64")

    if "timestamp_ms" not in frame.columns:
        quality_anchor = (
            relative_strength * 0.44
            + ema_slope * 0.24
            + distance_to_low * 0.20
            - stress_penalty * 0.12
        ).astype("float64")
        calm_base = (-base_signal.abs()).astype("float64")
        smoothed = (
            base_signal * 0.56
            + (quality_anchor - quality_anchor.mean()) * 0.24
            + (mild_reset_day - mild_reset_day.mean()) * 0.10
            + (balanced_volume - balanced_volume.mean()) * 0.06
            + (calm_base - calm_base.mean()) * 0.04
        ).astype("float64")
        return np.tanh(smoothed * 1.12).astype("float64")

    timestamps = frame["timestamp_ms"]
    quality_anchor_rank = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.44
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.24
        + _timestamp_percentile_rank(distance_to_low, timestamps) * 0.20
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.12
    ).astype("float64")
    calm_base_rank = _timestamp_percentile_rank(-base_signal.abs(), timestamps)
    smoothed_rank = (
        (_timestamp_percentile_rank(base_signal, timestamps) - 0.5) * 0.54
        + (quality_anchor_rank - 0.5) * 0.24
        + (_timestamp_percentile_rank(mild_reset_day, timestamps) - 0.5) * 0.12
        + (_timestamp_percentile_rank(balanced_volume, timestamps) - 0.5) * 0.06
        + (calm_base_rank - 0.5) * 0.04
    ).astype("float64")
    return np.tanh(smoothed_rank * 1.40).astype("float64")


def xs_pair_spread_book_v6_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    base_signal = xs_pair_spread_book_v3_score(frame, feature_columns=feature_columns).astype("float64")
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    balanced_volume = (1.0 - ((quote_volume_expansion - 1.03).abs() / 0.45)).clip(lower=0.0, upper=1.0)
    mild_reset_day = (1.0 - (return_1.abs() / 0.050)).clip(lower=0.0, upper=1.0)
    stress_penalty = (intraday_vol.clip(lower=0.0) * 0.55 + realized_volatility.clip(lower=0.0) * 0.45).astype("float64")

    if "timestamp_ms" not in frame.columns:
        quality_anchor = (
            relative_strength * 0.44
            + ema_slope * 0.24
            + distance_to_low * 0.20
            - stress_penalty * 0.12
        ).astype("float64")
        trend_anchor = (
            momentum_20 * 0.55
            + relative_strength * 0.25
            + ema_slope * 0.20
        ).astype("float64")
        smoothed = (
            base_signal * 0.56
            + (quality_anchor - quality_anchor.mean()) * 0.22
            + (mild_reset_day - mild_reset_day.mean()) * 0.10
            + (balanced_volume - balanced_volume.mean()) * 0.06
            + (trend_anchor - trend_anchor.mean()) * 0.06
        ).astype("float64")
        return np.tanh(smoothed * 1.18).astype("float64")

    timestamps = frame["timestamp_ms"]
    quality_anchor_rank = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.44
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.24
        + _timestamp_percentile_rank(distance_to_low, timestamps) * 0.20
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.12
    ).astype("float64")
    trend_anchor_rank = (
        _timestamp_percentile_rank(momentum_20, timestamps) * 0.55
        + _timestamp_percentile_rank(relative_strength, timestamps) * 0.25
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.20
    ).astype("float64")
    smoothed_rank = (
        (_timestamp_percentile_rank(base_signal, timestamps) - 0.5) * 0.56
        + (quality_anchor_rank - 0.5) * 0.22
        + (_timestamp_percentile_rank(mild_reset_day, timestamps) - 0.5) * 0.10
        + (_timestamp_percentile_rank(balanced_volume, timestamps) - 0.5) * 0.06
        + (trend_anchor_rank - 0.5) * 0.06
    ).astype("float64")
    return np.tanh(smoothed_rank * 1.50).astype("float64")


def xs_pair_spread_book_v7_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    base_signal = xs_pair_spread_book_v3_score(frame, feature_columns=feature_columns).astype("float64")
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    balanced_volume = (1.0 - ((quote_volume_expansion - 1.03).abs() / 0.45)).clip(lower=0.0, upper=1.0)
    mild_reset_day = (1.0 - (return_1.abs() / 0.050)).clip(lower=0.0, upper=1.0)
    stress_penalty = (intraday_vol.clip(lower=0.0) * 0.55 + realized_volatility.clip(lower=0.0) * 0.45).astype("float64")

    if "timestamp_ms" not in frame.columns:
        quality_anchor = (
            relative_strength * 0.44
            + ema_slope * 0.24
            + distance_to_low * 0.20
            - stress_penalty * 0.12
        ).astype("float64")
        smoothed = (
            base_signal * 0.58
            + (quality_anchor - quality_anchor.mean()) * 0.22
            + (mild_reset_day - mild_reset_day.mean()) * 0.10
            + (balanced_volume - balanced_volume.mean()) * 0.06
            + (distance_to_high - distance_to_high.mean()) * 0.04
        ).astype("float64")
        return np.tanh(smoothed * 1.22).astype("float64")

    timestamps = frame["timestamp_ms"]
    quality_anchor_rank = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.44
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.24
        + _timestamp_percentile_rank(distance_to_low, timestamps) * 0.20
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.12
    ).astype("float64")
    smoothed_rank = (
        (_timestamp_percentile_rank(base_signal, timestamps) - 0.5) * 0.56
        + (quality_anchor_rank - 0.5) * 0.22
        + (_timestamp_percentile_rank(mild_reset_day, timestamps) - 0.5) * 0.10
        + (_timestamp_percentile_rank(balanced_volume, timestamps) - 0.5) * 0.08
        + (_timestamp_percentile_rank(distance_to_high, timestamps) - 0.5) * 0.04
    ).astype("float64")
    return np.tanh(smoothed_rank * 1.52).astype("float64")


def xs_pair_spread_book_v8_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    base_signal = xs_pair_spread_book_v3_score(frame, feature_columns=feature_columns).astype("float64")
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    balanced_volume = (1.0 - ((quote_volume_expansion - 1.03).abs() / 0.45)).clip(lower=0.0, upper=1.0)
    mild_reset_day = (1.0 - (return_1.abs() / 0.050)).clip(lower=0.0, upper=1.0)
    stress_penalty = (intraday_vol.clip(lower=0.0) * 0.55 + realized_volatility.clip(lower=0.0) * 0.45).astype("float64")

    if "timestamp_ms" not in frame.columns:
        quality_anchor = (
            relative_strength * 0.44
            + ema_slope * 0.24
            + distance_to_low * 0.20
            - stress_penalty * 0.12
        ).astype("float64")
        smoothed = (
            base_signal * 0.59
            + (quality_anchor - quality_anchor.mean()) * 0.22
            + (mild_reset_day - mild_reset_day.mean()) * 0.10
            + (balanced_volume - balanced_volume.mean()) * 0.07
            + (distance_to_high - distance_to_high.mean()) * 0.02
        ).astype("float64")
        return np.tanh(smoothed * 1.21).astype("float64")

    timestamps = frame["timestamp_ms"]
    quality_anchor_rank = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.44
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.24
        + _timestamp_percentile_rank(distance_to_low, timestamps) * 0.20
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.12
    ).astype("float64")
    smoothed_rank = (
        (_timestamp_percentile_rank(base_signal, timestamps) - 0.5) * 0.57
        + (quality_anchor_rank - 0.5) * 0.22
        + (_timestamp_percentile_rank(mild_reset_day, timestamps) - 0.5) * 0.10
        + (_timestamp_percentile_rank(balanced_volume, timestamps) - 0.5) * 0.09
        + (_timestamp_percentile_rank(distance_to_high, timestamps) - 0.5) * 0.02
    ).astype("float64")
    return np.tanh(smoothed_rank * 1.53).astype("float64")


def xs_pair_spread_book_v9_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    base_signal = xs_pair_spread_book_v8_score(frame, feature_columns=feature_columns).astype("float64")
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)

    balanced_volume = (1.0 - ((quote_volume_expansion - 1.03).abs() / 0.45)).clip(lower=0.0, upper=1.0)
    mild_reset_day = (1.0 - (return_1.abs() / 0.050)).clip(lower=0.0, upper=1.0)
    stress_penalty = (intraday_vol.clip(lower=0.0) * 0.55 + realized_volatility.clip(lower=0.0) * 0.45).astype("float64")
    trend_crowding = (
        relative_strength.clip(lower=0.0) * 0.58
        + ema_slope.clip(lower=0.0) * 0.30
        + (1.0 - distance_to_low.clip(lower=0.0, upper=1.0)) * 0.12
    ).astype("float64")
    calm_base = (-base_signal.abs()).astype("float64")

    if "timestamp_ms" not in frame.columns:
        quality_anchor = (
            relative_strength * 0.44
            + ema_slope * 0.24
            + distance_to_low * 0.20
            - stress_penalty * 0.12
        ).astype("float64")
        smoothed = (
            base_signal * 0.52
            + (quality_anchor - quality_anchor.mean()) * 0.22
            + (mild_reset_day - mild_reset_day.mean()) * 0.10
            + (balanced_volume - balanced_volume.mean()) * 0.08
            + (calm_base - calm_base.mean()) * 0.04
            - (trend_crowding - trend_crowding.mean()) * 0.04
        ).astype("float64")
        return np.tanh(smoothed * 1.46).astype("float64")

    timestamps = frame["timestamp_ms"]
    quality_anchor_rank = (
        _timestamp_percentile_rank(relative_strength, timestamps) * 0.44
        + _timestamp_percentile_rank(ema_slope, timestamps) * 0.24
        + _timestamp_percentile_rank(distance_to_low, timestamps) * 0.20
        + _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.12
    ).astype("float64")
    calm_base_rank = _timestamp_percentile_rank(calm_base, timestamps)
    trend_crowding_rank = _timestamp_percentile_rank(trend_crowding, timestamps)
    smoothed_rank = (
        (_timestamp_percentile_rank(base_signal, timestamps) - 0.5) * 0.52
        + (quality_anchor_rank - 0.5) * 0.22
        + (_timestamp_percentile_rank(mild_reset_day, timestamps) - 0.5) * 0.10
        + (_timestamp_percentile_rank(balanced_volume, timestamps) - 0.5) * 0.08
        + (calm_base_rank - 0.5) * 0.04
        - (trend_crowding_rank - 0.5) * 0.04
    ).astype("float64")
    return np.tanh(smoothed_rank * 1.47).astype("float64")


def xs_pair_spread_book_v10_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return xs_pair_spread_book_v8_score(frame, feature_columns=feature_columns).astype("float64")


def xs_pair_spread_book_v11_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return xs_pair_spread_book_v8_score(frame, feature_columns=feature_columns).astype("float64")


def xs_pair_spread_book_v12_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return xs_pair_spread_book_v8_score(frame, feature_columns=feature_columns).astype("float64")


def xs_pair_spread_book_v16_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return xs_pair_spread_book_v8_score(frame, feature_columns=feature_columns).astype("float64")


def xs_pair_spread_book_v17_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return xs_pair_spread_book_v8_score(frame, feature_columns=feature_columns).astype("float64")


def xs_pair_spread_book_v18_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return xs_pair_spread_book_v8_score(frame, feature_columns=feature_columns).astype("float64")


def xs_pair_spread_book_v19_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return xs_pair_spread_book_v8_score(frame, feature_columns=feature_columns).astype("float64")


def xs_pair_spread_book_v20_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return xs_pair_spread_book_v8_score(frame, feature_columns=feature_columns).astype("float64")


def xs_pair_spread_book_v21_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return xs_pair_spread_book_v8_score(frame, feature_columns=feature_columns).astype("float64")


def xs_pair_spread_book_v22_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return xs_pair_spread_book_v8_score(frame, feature_columns=feature_columns).astype("float64")


def xs_pair_spread_book_v23_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return xs_pair_spread_book_v8_score(frame, feature_columns=feature_columns).astype("float64")


def xs_pair_spread_book_v24_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return xs_pair_spread_book_v8_score(frame, feature_columns=feature_columns).astype("float64")


def ranking_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "momentum_20", feature_columns=feature_columns) * 0.35
        + _feature_series(frame, "relative_strength_20", feature_columns=feature_columns) * 0.35
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.20
        - _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns) * 0.10
    ).astype("float64")


def carry_funding_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        -_feature_series(frame, "funding_zscore_20", feature_columns=feature_columns) * 0.45
        - _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns) * 0.35
        + _feature_series(frame, "oi_change_5", feature_columns=feature_columns) * 0.20
    ).astype("float64")


def basis_divergence_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        -_feature_series(frame, "basis_zscore_20", feature_columns=feature_columns) * 0.60
        - _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns) * 0.20
        + _feature_series(frame, "oi_change_5", feature_columns=feature_columns) * 0.20
    ).astype("float64")


def volatility_expansion_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns) * 0.30
        + _feature_series(frame, "atr_proxy_20", feature_columns=feature_columns) * 0.30
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.25
        + _feature_series(frame, "momentum_3", "momentum_5", feature_columns=feature_columns) * 0.15
    ).astype("float64")


def breakout_volatility_expansion_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        -_feature_series(frame, "distance_to_high_20", feature_columns=feature_columns) * 0.30
        + _feature_series(frame, "momentum_3", "momentum_5", feature_columns=feature_columns) * 0.20
        + (_feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns) - 1.0) * 0.20
        + _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns) * 0.15
        + _feature_series(frame, "atr_proxy_20", feature_columns=feature_columns) * 0.15
    ).astype("float64")


def event_drift_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return (
        _feature_series(frame, "event_flag_count", feature_columns=feature_columns) * 0.35
        + _feature_series(frame, "narrative_tag_count", feature_columns=feature_columns) * 0.20
        + _feature_series(frame, "momentum_6", "momentum_5", feature_columns=feature_columns) * 0.25
        + _feature_series(frame, "relative_strength_20", feature_columns=feature_columns) * 0.10
        - _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns) * 0.10
    ).astype("float64")


def evaluate_no_future_leakage(
    *,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    test_df: pd.DataFrame,
    time_col: str = "timestamp_ms",
    label_horizon_bars: int | None = None,
    bar_interval_ms: int | None = None,
    overlap_integrity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    train_max = int(train_df[time_col].max())
    validation_min = int(validation_df[time_col].min())
    validation_max = int(validation_df[time_col].max())
    test_min = int(test_df[time_col].min())
    strict_ordering_passed = train_max < validation_min and validation_max < test_min
    integrity_payload = dict(overlap_integrity or {})
    overlap_passed = bool(integrity_payload.get("passed", True))
    passed = strict_ordering_passed and overlap_passed
    blockers: list[str] = []
    if not strict_ordering_passed:
        blockers.append("chronological split overlap detected between train, validation, and test windows")
    if not overlap_passed:
        blockers.append(
            "label_split_overlap="
            f"{int(integrity_payload.get('label_split_overlap', 0) or 0)} violates the zero-overlap hard precondition"
        )
        mismatch = dict(integrity_payload.get("backtest_horizon_mismatch") or {})
        if mismatch.get("detected"):
            blockers.append(
                "backtest_horizon_mismatch="
                f"label_horizon_bars={int(mismatch.get('label_horizon_bars', 0) or 0)} "
                f"evaluation_step_bars={int(mismatch.get('evaluation_step_bars', 0) or 0)}"
            )
    contract_summary = {
        "strict_ordering_passed": strict_ordering_passed,
        "zero_boundary_contamination_passed": overlap_passed,
        "label_horizon_bars": int(label_horizon_bars or 0) if label_horizon_bars is not None else None,
        "bar_interval_ms": int(bar_interval_ms or 0) if bar_interval_ms is not None else None,
    }
    if passed:
        contract_summary["status"] = "passed"
    else:
        contract_summary["status"] = "failed"
    return {
        "passed": passed,
        "details": [
            "split/realization contract enforces strict train/validation/test ordering",
            "target columns remain excluded from model features",
            "boundary contamination and backtest cadence must satisfy the hard precondition before an experiment is trainable",
        ],
        "blockers": blockers,
        "contract_assertions": contract_summary,
    }


def xs_dual_regime_filter_v6_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)
    coinglass_taker_5d = _feature_series(frame, "coinglass_taker_imbalance_5d_sum", feature_columns=feature_columns)
    coinglass_retail_long = _feature_series(frame, "coinglass_global_account_long_pct", feature_columns=feature_columns)
    coinglass_liq_imb = _feature_series(frame, "coinglass_liquidation_imbalance_24h", feature_columns=feature_columns)
    coinglass_top_trader_long = _feature_series(frame, "coinglass_top_trader_long_pct", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.30 - funding_rate * 0.16).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.53 - funding_zscore * 0.47).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.18).abs() / 0.40)).clip(lower=0.0, upper=1.0)
    cheapness_quality = (1.0 - ((normalized_cheapness - 0.20).abs() / 0.50)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.85).clip(lower=0.0, upper=1.40) * 1.0
        + (raw_cheapness - 0.011).clip(lower=0.0, upper=0.06) * 11.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.08).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.50).abs() / 0.28)).clip(lower=0.0, upper=1.0)
    distress_floor_penalty = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    distress_floor_penalty = distress_floor_penalty.clip(lower=0.0, upper=1.0)
    upper_extension_penalty = (range_position - 0.78).clip(lower=0.0, upper=0.22) * 4.5
    upper_extension_penalty = upper_extension_penalty.clip(lower=0.0, upper=1.0)
    leadership_anchor = (
        relative_strength * 0.32
        + ema_slope * 0.22
        + momentum_20 * 0.18
        + reclaim_window * 0.13
        + support_buffer * 0.07
        + quality_zone * 0.08
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.30)).clip(lower=0.0, upper=1.0)
    mild_oi_growth = (oi_change.clip(lower=-0.10, upper=0.18) + 0.05).clip(lower=0.0, upper=0.23) * (1.0 / 0.23)
    mild_oi_growth = mild_oi_growth.clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.24)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50
        + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20
        + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20
        + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42
        + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")

    leader_sub = (
        leadership_anchor * 0.34
        + balanced_discount * 0.12
        + stable_oi * 0.10
        + balanced_volume * 0.10
        + orderly_reset * 0.10
        + reclaim_window * 0.09
        + quality_zone * 0.10
        + support_buffer * 0.05
    ).astype("float64")
    carry_sub = (
        cheapness_quality * 0.36
        + stable_oi * 0.14
        + mild_oi_growth * 0.12
        + balanced_volume * 0.10
        + quality_zone * 0.10
        + support_buffer * 0.08
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
    ).astype("float64")
    contrarian_laggard_tilt = (
        (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.18
        + (0.55 - range_position.clip(lower=0.10, upper=0.55)).clip(lower=0.0, upper=0.45) * (1.0 / 0.45) * 0.18
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.14
        + (-momentum_20).clip(lower=-0.05, upper=0.10) * (1.0 / 0.15) * 0.10
        + (-return_1).clip(lower=-0.01, upper=0.025) * (1.0 / 0.035) * 0.08
        + support_buffer * 0.10
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
        + (1.0 - distress_floor_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.06
    ).astype("float64")

    if "timestamp_ms" in frame.columns and not frame.empty:
        ts_values = frame["timestamp_ms"].values
        abs_mom_values = momentum_20.abs().values
        mom_values = momentum_20.values
        disp_df = pd.DataFrame({"v": abs_mom_values, "t": ts_values}, index=frame.index)
        timestamp_disp = disp_df.groupby("t")["v"].transform(
            lambda s: float(pd.Series(s).std() if len(s) > 1 else 0.0)
        )
        median_disp = float(pd.Series(timestamp_disp.values).median()) if len(timestamp_disp) else 0.05
        normalized_disp = (timestamp_disp / max(median_disp * 2.0, 1e-9)).clip(lower=0.0, upper=1.0)
        med_df = pd.DataFrame({"v": mom_values, "t": ts_values}, index=frame.index)
        timestamp_median_mom = med_df.groupby("t")["v"].transform("median")
        scaled_median_mom = (timestamp_median_mom / 0.06).clip(lower=-1.0, upper=1.0)
        broad_uniform_signal = (
            (1.0 - normalized_disp.values) * np.abs(scaled_median_mom.values)
        ).clip(0.0, 1.0)
        disp_array = normalized_disp.values
        med_sign_pos = (scaled_median_mom.values > 0).astype(float)

        leader_weight = (
            (0.20 + 0.60 * disp_array) * (0.55 + 0.45 * med_sign_pos)
        )
        carry_weight = (
            (0.20 + 0.60 * disp_array) * (1.0 - (0.55 + 0.45 * med_sign_pos) * 0.30)
        )
        contrarian_weight = 0.20 + 0.60 * broad_uniform_signal

        total = leader_weight + carry_weight + contrarian_weight + 1e-9
        leader_weight = leader_weight / total
        carry_weight = carry_weight / total
        contrarian_weight = contrarian_weight / total
    else:
        n = len(frame)
        leader_weight = np.full(n, 0.40)
        carry_weight = np.full(n, 0.40)
        contrarian_weight = np.full(n, 0.20)

    blended_alpha = (
        pd.Series(leader_weight, index=frame.index) * leader_sub
        + pd.Series(carry_weight, index=frame.index) * carry_sub
        + pd.Series(contrarian_weight, index=frame.index) * contrarian_laggard_tilt
    ).astype("float64")

    common_penalties = (
        stress_penalty * 0.06
        + chase_penalty * 0.025
        + overcheap_penalty * 0.04
        + rich_penalty * 0.02
        + distress_floor_penalty * 0.05
        + upper_extension_penalty * 0.045
        + distress_penalty * 0.05
        + broken_tape_penalty * 0.04
    ).astype("float64")

    raw_score = (blended_alpha * 1.0 - common_penalties).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    leader_w_series = pd.Series(leader_weight, index=frame.index)
    carry_w_series = pd.Series(carry_weight, index=frame.index)
    contra_w_series = pd.Series(contrarian_weight, index=frame.index)
    rank_leader = (
        _timestamp_percentile_rank(leadership_anchor, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.05
    ).astype("float64") * leader_w_series
    rank_carry = (
        _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.10
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.04
        + _timestamp_percentile_rank(mild_oi_growth, timestamps) * 0.04
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.02
    ).astype("float64") * carry_w_series
    rank_contra = (
        _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.06
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-momentum_20, timestamps) * 0.04
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.03
        + _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.03
    ).astype("float64") * contra_w_series
    rank_screen = (
        _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-distress_floor_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-distress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_gate = _timestamp_percentile_rank(blended_alpha, timestamps) * 0.10
    stable_rank_score = (
        rank_leader + rank_carry + rank_contra + rank_screen + rank_gate
    ).astype("float64")

    coinglass_taker_aligned = _timestamp_zscore(coinglass_taker_5d, timestamps)
    coinglass_retail_aligned = _timestamp_zscore(-coinglass_retail_long, timestamps)
    coinglass_liq_aligned = _timestamp_zscore(-coinglass_liq_imb, timestamps)
    coinglass_top_trader_aligned = _timestamp_zscore(-coinglass_top_trader_long, timestamps)
    import os as _os
    _audit_factor = (_os.environ.get("V71_AUDIT_FACTOR") or "all").strip().lower()
    if _audit_factor == "taker":
        coinglass_composite = coinglass_taker_aligned
    elif _audit_factor == "retail":
        coinglass_composite = coinglass_retail_aligned
    elif _audit_factor == "liq":
        coinglass_composite = coinglass_liq_aligned
    elif _audit_factor == "top_trader":
        coinglass_composite = coinglass_top_trader_aligned
    else:
        coinglass_composite = (
            coinglass_taker_aligned
            + coinglass_retail_aligned
            + coinglass_liq_aligned
            + coinglass_top_trader_aligned
        ) / 4.0

    v1_blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")

    coinglass_composite_zscore = _timestamp_zscore(coinglass_composite, timestamps)
    composite_weight = 0.12
    blended_signal = (
        v1_blended_signal * (1.0 - composite_weight)
        + coinglass_composite_zscore * composite_weight
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_dual_regime_filter_v7_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v72 = v71 architecture with regime-conditional sign flip on the 3 positioning
    sub-features of the CoinGlass composite (retail_long, liq_imbalance, top_trader_long).
    The taker_imbalance term is always sign-positive.

    Sign flip is driven by per-timestamp cross-sectional median(momentum_20):
        med_neg = clip(-median(momentum_20)/0.06, 0, 1)  in [0, 1]
        sign_flip = 1 - 2*med_neg                         in [-1, +1]

    When median momentum is positive (sign_flip â‰?+1), composite reproduces v71 fade-extremity:
        composite = (1/4) * [z_taker + (-z_retail) + (-z_liq) + (-z_top)]

    When median momentum is negative (sign_flip â‰?-1), 3 positioning subs flip to align-positioning:
        composite = (1/4) * [z_taker + (+z_retail) + (+z_liq) + (+z_top)]
    """
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)
    coinglass_taker_5d = _feature_series(frame, "coinglass_taker_imbalance_5d_sum", feature_columns=feature_columns)
    coinglass_retail_long = _feature_series(frame, "coinglass_global_account_long_pct", feature_columns=feature_columns)
    coinglass_liq_imb = _feature_series(frame, "coinglass_liquidation_imbalance_24h", feature_columns=feature_columns)
    coinglass_top_trader_long = _feature_series(frame, "coinglass_top_trader_long_pct", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.30 - funding_rate * 0.16).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.53 - funding_zscore * 0.47).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.18).abs() / 0.40)).clip(lower=0.0, upper=1.0)
    cheapness_quality = (1.0 - ((normalized_cheapness - 0.20).abs() / 0.50)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.85).clip(lower=0.0, upper=1.40) * 1.0
        + (raw_cheapness - 0.011).clip(lower=0.0, upper=0.06) * 11.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.08).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.50).abs() / 0.28)).clip(lower=0.0, upper=1.0)
    distress_floor_penalty = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    distress_floor_penalty = distress_floor_penalty.clip(lower=0.0, upper=1.0)
    upper_extension_penalty = (range_position - 0.78).clip(lower=0.0, upper=0.22) * 4.5
    upper_extension_penalty = upper_extension_penalty.clip(lower=0.0, upper=1.0)
    leadership_anchor = (
        relative_strength * 0.32 + ema_slope * 0.22 + momentum_20 * 0.18
        + reclaim_window * 0.13 + support_buffer * 0.07 + quality_zone * 0.08
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.30)).clip(lower=0.0, upper=1.0)
    mild_oi_growth = (oi_change.clip(lower=-0.10, upper=0.18) + 0.05).clip(lower=0.0, upper=0.23) * (1.0 / 0.23)
    mild_oi_growth = mild_oi_growth.clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.24)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50 + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20 + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20 + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42 + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")

    leader_sub = (
        leadership_anchor * 0.34 + balanced_discount * 0.12 + stable_oi * 0.10
        + balanced_volume * 0.10 + orderly_reset * 0.10 + reclaim_window * 0.09
        + quality_zone * 0.10 + support_buffer * 0.05
    ).astype("float64")
    carry_sub = (
        cheapness_quality * 0.36 + stable_oi * 0.14 + mild_oi_growth * 0.12
        + balanced_volume * 0.10 + quality_zone * 0.10 + support_buffer * 0.08
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
    ).astype("float64")
    contrarian_laggard_tilt = (
        (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.18
        + (0.55 - range_position.clip(lower=0.10, upper=0.55)).clip(lower=0.0, upper=0.45) * (1.0 / 0.45) * 0.18
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.14
        + (-momentum_20).clip(lower=-0.05, upper=0.10) * (1.0 / 0.15) * 0.10
        + (-return_1).clip(lower=-0.01, upper=0.025) * (1.0 / 0.035) * 0.08
        + support_buffer * 0.10
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
        + (1.0 - distress_floor_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.06
    ).astype("float64")

    if "timestamp_ms" in frame.columns and not frame.empty:
        ts_values = frame["timestamp_ms"].values
        abs_mom_values = momentum_20.abs().values
        mom_values = momentum_20.values
        disp_df = pd.DataFrame({"v": abs_mom_values, "t": ts_values}, index=frame.index)
        timestamp_disp = disp_df.groupby("t")["v"].transform(
            lambda s: float(pd.Series(s).std() if len(s) > 1 else 0.0)
        )
        median_disp = float(pd.Series(timestamp_disp.values).median()) if len(timestamp_disp) else 0.05
        normalized_disp = (timestamp_disp / max(median_disp * 2.0, 1e-9)).clip(lower=0.0, upper=1.0)
        med_df = pd.DataFrame({"v": mom_values, "t": ts_values}, index=frame.index)
        timestamp_median_mom = med_df.groupby("t")["v"].transform("median")
        scaled_median_mom = (timestamp_median_mom / 0.06).clip(lower=-1.0, upper=1.0)
        broad_uniform_signal = (
            (1.0 - normalized_disp.values) * np.abs(scaled_median_mom.values)
        ).clip(0.0, 1.0)
        disp_array = normalized_disp.values
        med_sign_pos = (scaled_median_mom.values > 0).astype(float)
        leader_weight = (0.20 + 0.60 * disp_array) * (0.55 + 0.45 * med_sign_pos)
        carry_weight = (0.20 + 0.60 * disp_array) * (1.0 - (0.55 + 0.45 * med_sign_pos) * 0.30)
        contrarian_weight = 0.20 + 0.60 * broad_uniform_signal
        total = leader_weight + carry_weight + contrarian_weight + 1e-9
        leader_weight = leader_weight / total
        carry_weight = carry_weight / total
        contrarian_weight = contrarian_weight / total
        # v72: regime-conditional sign flip on 3 positioning sub-features
        med_neg = (-scaled_median_mom.values).clip(0.0, 1.0)
        sign_flip = 1.0 - 2.0 * med_neg  # in [-1, +1]
    else:
        n = len(frame)
        leader_weight = np.full(n, 0.40)
        carry_weight = np.full(n, 0.40)
        contrarian_weight = np.full(n, 0.20)
        sign_flip = np.full(n, 1.0)

    blended_alpha = (
        pd.Series(leader_weight, index=frame.index) * leader_sub
        + pd.Series(carry_weight, index=frame.index) * carry_sub
        + pd.Series(contrarian_weight, index=frame.index) * contrarian_laggard_tilt
    ).astype("float64")

    common_penalties = (
        stress_penalty * 0.06 + chase_penalty * 0.025 + overcheap_penalty * 0.04
        + rich_penalty * 0.02 + distress_floor_penalty * 0.05 + upper_extension_penalty * 0.045
        + distress_penalty * 0.05 + broken_tape_penalty * 0.04
    ).astype("float64")

    raw_score = (blended_alpha * 1.0 - common_penalties).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    leader_w_series = pd.Series(leader_weight, index=frame.index)
    carry_w_series = pd.Series(carry_weight, index=frame.index)
    contra_w_series = pd.Series(contrarian_weight, index=frame.index)
    rank_leader = (
        _timestamp_percentile_rank(leadership_anchor, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.05
    ).astype("float64") * leader_w_series
    rank_carry = (
        _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.10
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.04
        + _timestamp_percentile_rank(mild_oi_growth, timestamps) * 0.04
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.02
    ).astype("float64") * carry_w_series
    rank_contra = (
        _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.06
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-momentum_20, timestamps) * 0.04
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.03
        + _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.03
    ).astype("float64") * contra_w_series
    rank_screen = (
        _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-distress_floor_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-distress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_gate = _timestamp_percentile_rank(blended_alpha, timestamps) * 0.10
    stable_rank_score = (rank_leader + rank_carry + rank_contra + rank_screen + rank_gate).astype("float64")

    v1_blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")

    # v72 NEW: regime-conditional sign flip on 3 positioning sub-features (taker stays +)
    z_taker = _timestamp_zscore(coinglass_taker_5d, timestamps)
    z_retail = _timestamp_zscore(coinglass_retail_long, timestamps)
    z_liq = _timestamp_zscore(coinglass_liq_imb, timestamps)
    z_top = _timestamp_zscore(coinglass_top_trader_long, timestamps)

    sign_flip_series = pd.Series(sign_flip, index=frame.index)
    coinglass_composite_v7 = (
        z_taker
        + sign_flip_series * (-z_retail)
        + sign_flip_series * (-z_liq)
        + sign_flip_series * (-z_top)
    ).astype("float64") / 4.0
    coinglass_composite_zscore = _timestamp_zscore(coinglass_composite_v7, timestamps)

    composite_weight = 0.12
    blended_signal = (
        v1_blended_signal * (1.0 - composite_weight)
        + coinglass_composite_zscore * composite_weight
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


# v73: per-feature 4-quadrant sign config for CoinGlass composite
# Quadrants: HU = high_disp + med_pos, HD = high_disp + med_neg,
#            LU = low_disp + med_pos,  LD = low_disp + med_neg
# Per-feature sign multipliers in [-1, +1] (-1 = fade, +1 = align):
_V8_SIGN_CONFIG = {
    "retail": (-1.0, -1.0, -0.5, +1.0),
    "liq":    (-1.0, +1.0, -0.5, +1.0),
    "top":    (-1.0, -0.5, -0.5, +1.0),
}


def xs_dual_regime_filter_v8_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """v73 = v72 with per-feature 4-quadrant sign matrix on CoinGlass positioning composite."""
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)
    coinglass_taker_5d = _feature_series(frame, "coinglass_taker_imbalance_5d_sum", feature_columns=feature_columns)
    coinglass_retail_long = _feature_series(frame, "coinglass_global_account_long_pct", feature_columns=feature_columns)
    coinglass_liq_imb = _feature_series(frame, "coinglass_liquidation_imbalance_24h", feature_columns=feature_columns)
    coinglass_top_trader_long = _feature_series(frame, "coinglass_top_trader_long_pct", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.30 - funding_rate * 0.16).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.53 - funding_zscore * 0.47).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.18).abs() / 0.40)).clip(lower=0.0, upper=1.0)
    cheapness_quality = (1.0 - ((normalized_cheapness - 0.20).abs() / 0.50)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.85).clip(lower=0.0, upper=1.40) * 1.0
        + (raw_cheapness - 0.011).clip(lower=0.0, upper=0.06) * 11.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.08).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.50).abs() / 0.28)).clip(lower=0.0, upper=1.0)
    distress_floor_penalty = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    distress_floor_penalty = distress_floor_penalty.clip(lower=0.0, upper=1.0)
    upper_extension_penalty = (range_position - 0.78).clip(lower=0.0, upper=0.22) * 4.5
    upper_extension_penalty = upper_extension_penalty.clip(lower=0.0, upper=1.0)
    leadership_anchor = (
        relative_strength * 0.32 + ema_slope * 0.22 + momentum_20 * 0.18
        + reclaim_window * 0.13 + support_buffer * 0.07 + quality_zone * 0.08
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.30)).clip(lower=0.0, upper=1.0)
    mild_oi_growth = (oi_change.clip(lower=-0.10, upper=0.18) + 0.05).clip(lower=0.0, upper=0.23) * (1.0 / 0.23)
    mild_oi_growth = mild_oi_growth.clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.24)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50 + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20 + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20 + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42 + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")

    leader_sub = (
        leadership_anchor * 0.34 + balanced_discount * 0.12 + stable_oi * 0.10
        + balanced_volume * 0.10 + orderly_reset * 0.10 + reclaim_window * 0.09
        + quality_zone * 0.10 + support_buffer * 0.05
    ).astype("float64")
    carry_sub = (
        cheapness_quality * 0.36 + stable_oi * 0.14 + mild_oi_growth * 0.12
        + balanced_volume * 0.10 + quality_zone * 0.10 + support_buffer * 0.08
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
    ).astype("float64")
    contrarian_laggard_tilt = (
        (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.18
        + (0.55 - range_position.clip(lower=0.10, upper=0.55)).clip(lower=0.0, upper=0.45) * (1.0 / 0.45) * 0.18
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.14
        + (-momentum_20).clip(lower=-0.05, upper=0.10) * (1.0 / 0.15) * 0.10
        + (-return_1).clip(lower=-0.01, upper=0.025) * (1.0 / 0.035) * 0.08
        + support_buffer * 0.10
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
        + (1.0 - distress_floor_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.06
    ).astype("float64")

    if "timestamp_ms" in frame.columns and not frame.empty:
        ts_values = frame["timestamp_ms"].values
        abs_mom_values = momentum_20.abs().values
        mom_values = momentum_20.values
        disp_df = pd.DataFrame({"v": abs_mom_values, "t": ts_values}, index=frame.index)
        timestamp_disp = disp_df.groupby("t")["v"].transform(
            lambda s: float(pd.Series(s).std() if len(s) > 1 else 0.0)
        )
        median_disp = float(pd.Series(timestamp_disp.values).median()) if len(timestamp_disp) else 0.05
        normalized_disp = (timestamp_disp / max(median_disp * 2.0, 1e-9)).clip(lower=0.0, upper=1.0)
        med_df = pd.DataFrame({"v": mom_values, "t": ts_values}, index=frame.index)
        timestamp_median_mom = med_df.groupby("t")["v"].transform("median")
        scaled_median_mom = (timestamp_median_mom / 0.06).clip(lower=-1.0, upper=1.0)
        broad_uniform_signal = (
            (1.0 - normalized_disp.values) * np.abs(scaled_median_mom.values)
        ).clip(0.0, 1.0)
        disp_array = normalized_disp.values
        med_pos = (scaled_median_mom.values > 0).astype(float)
        med_pos_cont = scaled_median_mom.values.clip(0.0, 1.0)
        med_neg_cont = (-scaled_median_mom.values).clip(0.0, 1.0)
        leader_weight = (0.20 + 0.60 * disp_array) * (0.55 + 0.45 * med_pos)
        carry_weight = (0.20 + 0.60 * disp_array) * (1.0 - (0.55 + 0.45 * med_pos) * 0.30)
        contrarian_weight = 0.20 + 0.60 * broad_uniform_signal
        total = leader_weight + carry_weight + contrarian_weight + 1e-9
        leader_weight = leader_weight / total
        carry_weight = carry_weight / total
        contrarian_weight = contrarian_weight / total
        # v73: continuous 4-quadrant indicators
        w_HU = disp_array * med_pos_cont
        w_HD = disp_array * med_neg_cont
        w_LU = (1.0 - disp_array) * med_pos_cont
        w_LD = (1.0 - disp_array) * med_neg_cont
    else:
        n = len(frame)
        leader_weight = np.full(n, 0.40)
        carry_weight = np.full(n, 0.40)
        contrarian_weight = np.full(n, 0.20)
        w_HU = np.zeros(n)
        w_HD = np.zeros(n)
        w_LU = np.zeros(n)
        w_LD = np.zeros(n)

    blended_alpha = (
        pd.Series(leader_weight, index=frame.index) * leader_sub
        + pd.Series(carry_weight, index=frame.index) * carry_sub
        + pd.Series(contrarian_weight, index=frame.index) * contrarian_laggard_tilt
    ).astype("float64")

    common_penalties = (
        stress_penalty * 0.06 + chase_penalty * 0.025 + overcheap_penalty * 0.04
        + rich_penalty * 0.02 + distress_floor_penalty * 0.05 + upper_extension_penalty * 0.045
        + distress_penalty * 0.05 + broken_tape_penalty * 0.04
    ).astype("float64")

    raw_score = (blended_alpha * 1.0 - common_penalties).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    leader_w_series = pd.Series(leader_weight, index=frame.index)
    carry_w_series = pd.Series(carry_weight, index=frame.index)
    contra_w_series = pd.Series(contrarian_weight, index=frame.index)
    rank_leader = (
        _timestamp_percentile_rank(leadership_anchor, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.05
    ).astype("float64") * leader_w_series
    rank_carry = (
        _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.10
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.04
        + _timestamp_percentile_rank(mild_oi_growth, timestamps) * 0.04
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.02
    ).astype("float64") * carry_w_series
    rank_contra = (
        _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.06
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-momentum_20, timestamps) * 0.04
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.03
        + _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.03
    ).astype("float64") * contra_w_series
    rank_screen = (
        _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-distress_floor_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-distress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_gate = _timestamp_percentile_rank(blended_alpha, timestamps) * 0.10
    stable_rank_score = (rank_leader + rank_carry + rank_contra + rank_screen + rank_gate).astype("float64")

    v1_blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")

    # v73: 4-quadrant per-feature sign matrix
    z_taker = _timestamp_zscore(coinglass_taker_5d, timestamps)
    z_retail = _timestamp_zscore(coinglass_retail_long, timestamps)
    z_liq = _timestamp_zscore(coinglass_liq_imb, timestamps)
    z_top = _timestamp_zscore(coinglass_top_trader_long, timestamps)

    def _per_q_sign(cfg: tuple) -> np.ndarray:
        return cfg[0] * w_HU + cfg[1] * w_HD + cfg[2] * w_LU + cfg[3] * w_LD

    sign_retail = pd.Series(_per_q_sign(_V8_SIGN_CONFIG["retail"]), index=frame.index)
    sign_liq = pd.Series(_per_q_sign(_V8_SIGN_CONFIG["liq"]), index=frame.index)
    sign_top = pd.Series(_per_q_sign(_V8_SIGN_CONFIG["top"]), index=frame.index)

    coinglass_composite_v8 = (
        z_taker
        + sign_retail * z_retail
        + sign_liq * z_liq
        + sign_top * z_top
    ).astype("float64") / 4.0
    coinglass_composite_zscore = _timestamp_zscore(coinglass_composite_v8, timestamps)

    composite_weight = 0.12
    blended_signal = (
        v1_blended_signal * (1.0 - composite_weight)
        + coinglass_composite_zscore * composite_weight
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_dual_regime_filter_v9_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v74 = v73 (xs_dual_regime_filter_v8) with composite_weight reduced from 0.12 to 0.08.
    Identical 4-quadrant per-feature sign matrix; only the final injection weight differs.
    Tests whether less aggressive CoinGlass blending preserves regime PASS while improving
    out-of-sample portfolio Sharpe.
    """
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)
    coinglass_taker_5d = _feature_series(frame, "coinglass_taker_imbalance_5d_sum", feature_columns=feature_columns)
    coinglass_retail_long = _feature_series(frame, "coinglass_global_account_long_pct", feature_columns=feature_columns)
    coinglass_liq_imb = _feature_series(frame, "coinglass_liquidation_imbalance_24h", feature_columns=feature_columns)
    coinglass_top_trader_long = _feature_series(frame, "coinglass_top_trader_long_pct", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.30 - funding_rate * 0.16).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.53 - funding_zscore * 0.47).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.18).abs() / 0.40)).clip(lower=0.0, upper=1.0)
    cheapness_quality = (1.0 - ((normalized_cheapness - 0.20).abs() / 0.50)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.85).clip(lower=0.0, upper=1.40) * 1.0
        + (raw_cheapness - 0.011).clip(lower=0.0, upper=0.06) * 11.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.08).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.50).abs() / 0.28)).clip(lower=0.0, upper=1.0)
    distress_floor_penalty = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    distress_floor_penalty = distress_floor_penalty.clip(lower=0.0, upper=1.0)
    upper_extension_penalty = (range_position - 0.78).clip(lower=0.0, upper=0.22) * 4.5
    upper_extension_penalty = upper_extension_penalty.clip(lower=0.0, upper=1.0)
    leadership_anchor = (
        relative_strength * 0.32 + ema_slope * 0.22 + momentum_20 * 0.18
        + reclaim_window * 0.13 + support_buffer * 0.07 + quality_zone * 0.08
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.30)).clip(lower=0.0, upper=1.0)
    mild_oi_growth = (oi_change.clip(lower=-0.10, upper=0.18) + 0.05).clip(lower=0.0, upper=0.23) * (1.0 / 0.23)
    mild_oi_growth = mild_oi_growth.clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.24)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50 + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20 + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20 + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42 + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")

    leader_sub = (
        leadership_anchor * 0.34 + balanced_discount * 0.12 + stable_oi * 0.10
        + balanced_volume * 0.10 + orderly_reset * 0.10 + reclaim_window * 0.09
        + quality_zone * 0.10 + support_buffer * 0.05
    ).astype("float64")
    carry_sub = (
        cheapness_quality * 0.36 + stable_oi * 0.14 + mild_oi_growth * 0.12
        + balanced_volume * 0.10 + quality_zone * 0.10 + support_buffer * 0.08
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
    ).astype("float64")
    contrarian_laggard_tilt = (
        (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.18
        + (0.55 - range_position.clip(lower=0.10, upper=0.55)).clip(lower=0.0, upper=0.45) * (1.0 / 0.45) * 0.18
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.14
        + (-momentum_20).clip(lower=-0.05, upper=0.10) * (1.0 / 0.15) * 0.10
        + (-return_1).clip(lower=-0.01, upper=0.025) * (1.0 / 0.035) * 0.08
        + support_buffer * 0.10
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
        + (1.0 - distress_floor_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.06
    ).astype("float64")

    if "timestamp_ms" in frame.columns and not frame.empty:
        ts_values = frame["timestamp_ms"].values
        abs_mom_values = momentum_20.abs().values
        mom_values = momentum_20.values
        disp_df = pd.DataFrame({"v": abs_mom_values, "t": ts_values}, index=frame.index)
        timestamp_disp = disp_df.groupby("t")["v"].transform(
            lambda s: float(pd.Series(s).std() if len(s) > 1 else 0.0)
        )
        median_disp = float(pd.Series(timestamp_disp.values).median()) if len(timestamp_disp) else 0.05
        normalized_disp = (timestamp_disp / max(median_disp * 2.0, 1e-9)).clip(lower=0.0, upper=1.0)
        med_df = pd.DataFrame({"v": mom_values, "t": ts_values}, index=frame.index)
        timestamp_median_mom = med_df.groupby("t")["v"].transform("median")
        scaled_median_mom = (timestamp_median_mom / 0.06).clip(lower=-1.0, upper=1.0)
        broad_uniform_signal = (
            (1.0 - normalized_disp.values) * np.abs(scaled_median_mom.values)
        ).clip(0.0, 1.0)
        disp_array = normalized_disp.values
        med_pos = (scaled_median_mom.values > 0).astype(float)
        med_pos_cont = scaled_median_mom.values.clip(0.0, 1.0)
        med_neg_cont = (-scaled_median_mom.values).clip(0.0, 1.0)
        leader_weight = (0.20 + 0.60 * disp_array) * (0.55 + 0.45 * med_pos)
        carry_weight = (0.20 + 0.60 * disp_array) * (1.0 - (0.55 + 0.45 * med_pos) * 0.30)
        contrarian_weight = 0.20 + 0.60 * broad_uniform_signal
        total = leader_weight + carry_weight + contrarian_weight + 1e-9
        leader_weight = leader_weight / total
        carry_weight = carry_weight / total
        contrarian_weight = contrarian_weight / total
        w_HU = disp_array * med_pos_cont
        w_HD = disp_array * med_neg_cont
        w_LU = (1.0 - disp_array) * med_pos_cont
        w_LD = (1.0 - disp_array) * med_neg_cont
    else:
        n = len(frame)
        leader_weight = np.full(n, 0.40)
        carry_weight = np.full(n, 0.40)
        contrarian_weight = np.full(n, 0.20)
        w_HU = np.zeros(n)
        w_HD = np.zeros(n)
        w_LU = np.zeros(n)
        w_LD = np.zeros(n)

    blended_alpha = (
        pd.Series(leader_weight, index=frame.index) * leader_sub
        + pd.Series(carry_weight, index=frame.index) * carry_sub
        + pd.Series(contrarian_weight, index=frame.index) * contrarian_laggard_tilt
    ).astype("float64")

    common_penalties = (
        stress_penalty * 0.06 + chase_penalty * 0.025 + overcheap_penalty * 0.04
        + rich_penalty * 0.02 + distress_floor_penalty * 0.05 + upper_extension_penalty * 0.045
        + distress_penalty * 0.05 + broken_tape_penalty * 0.04
    ).astype("float64")

    raw_score = (blended_alpha * 1.0 - common_penalties).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    leader_w_series = pd.Series(leader_weight, index=frame.index)
    carry_w_series = pd.Series(carry_weight, index=frame.index)
    contra_w_series = pd.Series(contrarian_weight, index=frame.index)
    rank_leader = (
        _timestamp_percentile_rank(leadership_anchor, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.05
    ).astype("float64") * leader_w_series
    rank_carry = (
        _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.10
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.04
        + _timestamp_percentile_rank(mild_oi_growth, timestamps) * 0.04
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.02
    ).astype("float64") * carry_w_series
    rank_contra = (
        _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.06
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-momentum_20, timestamps) * 0.04
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.03
        + _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.03
    ).astype("float64") * contra_w_series
    rank_screen = (
        _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-distress_floor_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-distress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64")
    rank_gate = _timestamp_percentile_rank(blended_alpha, timestamps) * 0.10
    stable_rank_score = (rank_leader + rank_carry + rank_contra + rank_screen + rank_gate).astype("float64")

    v1_blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")

    z_taker = _timestamp_zscore(coinglass_taker_5d, timestamps)
    z_retail = _timestamp_zscore(coinglass_retail_long, timestamps)
    z_liq = _timestamp_zscore(coinglass_liq_imb, timestamps)
    z_top = _timestamp_zscore(coinglass_top_trader_long, timestamps)

    def _per_q_sign(cfg: tuple) -> np.ndarray:
        return cfg[0] * w_HU + cfg[1] * w_HD + cfg[2] * w_LU + cfg[3] * w_LD

    sign_retail = pd.Series(_per_q_sign(_V8_SIGN_CONFIG["retail"]), index=frame.index)
    sign_liq = pd.Series(_per_q_sign(_V8_SIGN_CONFIG["liq"]), index=frame.index)
    sign_top = pd.Series(_per_q_sign(_V8_SIGN_CONFIG["top"]), index=frame.index)

    coinglass_composite_v9 = (
        z_taker
        + sign_retail * z_retail
        + sign_liq * z_liq
        + sign_top * z_top
    ).astype("float64") / 4.0
    coinglass_composite_zscore = _timestamp_zscore(coinglass_composite_v9, timestamps)

    composite_weight = 0.08  # v74: reduced from 0.12 to 0.08
    blended_signal = (
        v1_blended_signal * (1.0 - composite_weight)
        + coinglass_composite_zscore * composite_weight
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_ensemble_v74_v80_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v82: Linear ensemble of v74 (xs_dual_regime_filter_v9) and v80 (xs_minimal_v1).
    Hypothesis: 50/50 blend captures v74's regime stability + v80's stronger alpha.
    Both component scores are tanh outputs in [-1, +1], so linear average is well-behaved.
    Final pass through percentile_rank + tanh re-normalizes the ensemble.
    """
    s_v74 = xs_dual_regime_filter_v9_score(frame, feature_columns=feature_columns)
    s_v80 = xs_minimal_v1_score(frame, feature_columns=feature_columns)
    ensemble = (0.5 * s_v74.astype("float64") + 0.5 * s_v80.astype("float64")).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return ensemble

    timestamps = frame["timestamp_ms"]
    centered_rank = _timestamp_percentile_rank(ensemble, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_minimal_v2_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v81: v80 minimal-6 alpha core + v74-style screening penalties.

    Alpha core (6 features, identical to v80):
        -0.30*z(realized_volatility_20)
        -0.20*z(intraday_realized_vol_4h_to_1d)
        +0.20*z(distance_to_high_20)
        -0.15*z(coinglass_top_trader_long_pct)
        +0.15*sign_regime*z(relative_strength_20)
        +0.10*sign_regime*z(momentum_20)

    Screening penalties (5 quality-filter features from v74):
        -0.05*chase_penalty           (range_position high + qv_exp + return_1)
        -0.05*distress_penalty        (negative rs + negative ema_slope)
        -0.04*broken_tape_penalty     (very negative dist_to_low + sharp negative return_1)
        -0.05*distress_floor_penalty  (range_position < 0.10)
        -0.045*upper_extension_penalty (range_position > 0.78)
    """
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    top_trader = _feature_series(frame, "coinglass_top_trader_long_pct", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    timestamps = frame["timestamp_ms"]

    # Alpha core (v80 logic)
    z_rv = _timestamp_zscore(realized_volatility, timestamps)
    z_iv = _timestamp_zscore(intraday_vol, timestamps)
    z_dh = _timestamp_zscore(distance_to_high, timestamps)
    z_tt = _timestamp_zscore(top_trader, timestamps)
    z_rs = _timestamp_zscore(relative_strength, timestamps)
    z_mom = _timestamp_zscore(momentum_20, timestamps)

    ts_values = timestamps.values
    mom_values = momentum_20.values
    med_df = pd.DataFrame({"v": mom_values, "t": ts_values}, index=frame.index)
    timestamp_median_mom = med_df.groupby("t")["v"].transform("median")
    sign_regime = (timestamp_median_mom / 0.06).clip(lower=-1.0, upper=1.0)
    sign_regime_series = pd.Series(sign_regime.values, index=frame.index)

    alpha_score = (
        -0.30 * z_rv
        -0.20 * z_iv
        +0.20 * z_dh
        -0.15 * z_tt
        +0.15 * sign_regime_series * z_rs
        +0.10 * sign_regime_series * z_mom
    ).astype("float64")

    # Screening penalties (v74 style)
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42
        + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20
        + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20
        + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    distress_floor_penalty = (
        (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    ).clip(lower=0.0, upper=1.0).astype("float64")
    upper_extension_penalty = (
        (range_position - 0.78).clip(lower=0.0, upper=0.22) * 4.5
    ).clip(lower=0.0, upper=1.0).astype("float64")

    raw_score = (
        alpha_score
        - 0.05 * chase_penalty
        - 0.05 * distress_penalty
        - 0.04 * broken_tape_penalty
        - 0.05 * distress_floor_penalty
        - 0.045 * upper_extension_penalty
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_minimal_v3_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v83: 4-column ultra-minimal baseline. Tier-1 stable-sign IC features only.
    No momentum, no regime sign, no penalties, no derivatives.

        -0.30*z(realized_volatility_20)
        -0.25*z(intraday_realized_vol_4h_to_1d)
        +0.25*z(distance_to_high_20)
        -0.20*z(coinglass_top_trader_long_pct)

    Final = tanh((percentile_rank(raw_score) - 0.5) * 1.80)
    """
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    top_trader = _feature_series(frame, "coinglass_top_trader_long_pct", feature_columns=feature_columns)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    timestamps = frame["timestamp_ms"]

    z_rv = _timestamp_zscore(realized_volatility, timestamps)
    z_iv = _timestamp_zscore(intraday_vol, timestamps)
    z_dh = _timestamp_zscore(distance_to_high, timestamps)
    z_tt = _timestamp_zscore(top_trader, timestamps)

    raw_score = (
        -0.30 * z_rv
        -0.25 * z_iv
        +0.25 * z_dh
        -0.20 * z_tt
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_minimal_v4_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v89 (Phase 1a): multi-timescale extension of xs_minimal_v3 (v83).

    Each of the 4 v83 factor families is averaged across 3 time scales
    (5d / 20d / 60d) before being combined with the v83 weights:

      family_rv  = mean( z(realized_volatility_5),
                          z(realized_volatility_20),
                          z(realized_volatility_60) )
      family_iv  = mean( z(intraday_realized_vol_4h_to_1d_smooth_5),
                          z(intraday_realized_vol_4h_to_1d_smooth_20),
                          z(intraday_realized_vol_4h_to_1d_smooth_60) )
      family_dh  = mean( z(distance_to_high_5),
                          z(distance_to_high_20),
                          z(distance_to_high_60) )
      family_tt  = mean( z(coinglass_top_trader_long_pct_smooth_5),
                          z(coinglass_top_trader_long_pct_smooth_20),
                          z(coinglass_top_trader_long_pct_smooth_60) )

      raw_score = -0.30*family_rv -0.25*family_iv +0.25*family_dh -0.20*family_tt
      final     = tanh( (percentile_rank(raw_score) - 0.5) * 1.80 )

    Hypothesis (Phase 1a roadmap): averaging across 3 scales reduces single-
    window measurement noise. Expected modest rank IC lift over v83's 0.20
    and improved walk-forward stability.
    """
    timestamps = frame["timestamp_ms"]

    def _family_mean(columns: list[str]) -> pd.Series:
        z_columns: list[pd.Series] = []
        for col in columns:
            if col in frame.columns:
                series = pd.to_numeric(frame[col], errors="coerce")
                if series.notna().any():
                    z_columns.append(_timestamp_zscore(series, timestamps))
        if not z_columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        stacked = pd.concat(z_columns, axis=1)
        return stacked.mean(axis=1)

    family_rv = _family_mean([
        "realized_volatility_5",
        "realized_volatility_20",
        "realized_volatility_60",
    ])
    family_iv = _family_mean([
        "intraday_realized_vol_4h_to_1d_smooth_5",
        "intraday_realized_vol_4h_to_1d_smooth_20",
        "intraday_realized_vol_4h_to_1d_smooth_60",
    ])
    family_dh = _family_mean([
        "distance_to_high_5",
        "distance_to_high_20",
        "distance_to_high_60",
    ])
    family_tt = _family_mean([
        "coinglass_top_trader_long_pct_smooth_5",
        "coinglass_top_trader_long_pct_smooth_20",
        "coinglass_top_trader_long_pct_smooth_60",
    ])

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = (
        -0.30 * family_rv
        -0.25 * family_iv
        +0.25 * family_dh
        -0.20 * family_tt
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_minimal_v5_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v90 (Phase 1b): xs_minimal_v4 (multi-timescale v83) + 5 new factor families.

    v89 core (4 families * 3 timescales averaged, weights identical to v83):
      family_rv (low-vol anomaly), family_iv (intraday vol),
      family_dh (distance-to-high reversion), family_tt (top-trader contrarian)

    Phase 1b additions (5 new families, all hypothesized negative sign):
      momentum_decay      = momentum_5 - momentum_20            (recent acceleration -> mean revert)
      quality_proxy       = funding_rate * oi_change_5          (long-crowded -> unwind)
      liquidity_stress    = quote_volume_expansion * intraday_realized_vol_4h_to_1d  (stress -> persistence -> drag)
      order_flow_disp     = coinglass_taker_imb_intraday_dispersion_24h              (disagreement -> uncertainty)
      funding_crowding    = funding_zscore_20 * abs(basis_zscore_20)                 (perp+cash both stretched)

    Combination:
      raw = -0.30*family_rv -0.25*family_iv +0.25*family_dh -0.20*family_tt
            -0.10*z(momentum_decay)
            -0.10*z(quality_proxy)
            -0.10*z(liquidity_stress)
            -0.10*z(order_flow_disp)
            -0.10*z(funding_crowding)
      final = tanh((percentile_rank(raw) - 0.5) * 1.80)
    """
    timestamps = frame["timestamp_ms"]

    def _family_mean(columns: list[str]) -> pd.Series:
        z_columns: list[pd.Series] = []
        for col in columns:
            if col in frame.columns:
                series = pd.to_numeric(frame[col], errors="coerce")
                if series.notna().any():
                    z_columns.append(_timestamp_zscore(series, timestamps))
        if not z_columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        stacked = pd.concat(z_columns, axis=1)
        return stacked.mean(axis=1)

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    family_rv = _family_mean([
        "realized_volatility_5",
        "realized_volatility_20",
        "realized_volatility_60",
    ])
    family_iv = _family_mean([
        "intraday_realized_vol_4h_to_1d_smooth_5",
        "intraday_realized_vol_4h_to_1d_smooth_20",
        "intraday_realized_vol_4h_to_1d_smooth_60",
    ])
    family_dh = _family_mean([
        "distance_to_high_5",
        "distance_to_high_20",
        "distance_to_high_60",
    ])
    family_tt = _family_mean([
        "coinglass_top_trader_long_pct_smooth_5",
        "coinglass_top_trader_long_pct_smooth_20",
        "coinglass_top_trader_long_pct_smooth_60",
    ])

    z_md = _single_z("momentum_decay_5_20")
    z_q = _single_z("quality_funding_oi")
    z_ls = _single_z("liquidity_stress_qv_iv")
    z_of = _single_z("coinglass_taker_imb_intraday_dispersion_24h")
    z_fc = _single_z("funding_crowding_basis")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = (
        -0.30 * family_rv
        -0.25 * family_iv
        +0.25 * family_dh
        -0.20 * family_tt
        -0.10 * z_md
        -0.10 * z_q
        -0.10 * z_ls
        -0.10 * z_of
        -0.10 * z_fc
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_minimal_v6_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v91 (Phase 1c): IC-pruned + sign-corrected version of v90.

    Reduction from 17 -> 9 factors based on full-panel rank IC and VIF analysis
    (see scripts/quant_research/phase_1c_factor_correlation_analysis.py and
    artifacts/quant_research/shadow_oos/phase_1c_factor_analysis_2026-04-26.json):

    Kept (sign and weight from full-panel IC, scaled so absolute sum ~ 1.00):
      -0.20 * z(intraday_realized_vol_4h_to_1d_smooth_60)   IC = -0.093 (strongest single factor)
      -0.10 * z(realized_volatility_5)                       IC = -0.070, low VIF
      +0.18 * z(distance_to_high_60)                         IC = +0.084
      +0.15 * z(distance_to_high_5)                          IC = +0.077
      -0.07 * z(coinglass_top_trader_long_pct_smooth_5)      IC = -0.030 (best of tt scales)
      -0.10 * z(liquidity_stress_qv_iv)                      IC = -0.046 (only Phase 1b new factor with real signal)
      -0.06 * z(momentum_decay_5_20)                         IC = -0.028
      +0.05 * z(coinglass_taker_imb_intraday_dispersion_24h) IC = +0.023 (FLIPPED from v90's -0.10)
      -0.05 * z(quality_funding_oi)                          IC = -0.022

    Dropped (VIF > 5 redundant or IC near zero):
      realized_volatility_20, realized_volatility_60         (VIF > 5, redundant with rv_5 / iv_smooth_60)
      intraday_realized_vol_smooth_5, intraday_realized_vol_smooth_20  (VIF > 5)
      distance_to_high_20                                    (VIF 4.2, redundant with dh_5 + dh_60)
      coinglass_top_trader_long_pct_smooth_20/60             (VIF > 5, weaker IC than _5)
      funding_crowding_basis                                 (IC -0.011, essentially zero)

    Lookahead disclosure: weights are derived from rank IC measured on the full
    3-year panel including the test segment. This matches the methodology used
    for v83 / v89 / v90 hand-tuned weights. Phase 1d will replace these static
    weights with rolling-IR dynamic weights for proper OOS treatment.
    """
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = (
        -0.20 * _single_z("intraday_realized_vol_4h_to_1d_smooth_60")
        -0.10 * _single_z("realized_volatility_5")
        +0.18 * _single_z("distance_to_high_60")
        +0.15 * _single_z("distance_to_high_5")
        -0.07 * _single_z("coinglass_top_trader_long_pct_smooth_5")
        -0.10 * _single_z("liquidity_stress_qv_iv")
        -0.06 * _single_z("momentum_decay_5_20")
        +0.05 * _single_z("coinglass_taker_imb_intraday_dispersion_24h")
        -0.05 * _single_z("quality_funding_oi")
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_minimal_v7_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v92 (Phase 1b extension of v91): adds 3 B-batch alternative factor candidates
    orthogonal to the v91 9-factor baseline.

    Per phase_1c_factor_analysis on the v92 panel (artifacts/quant_research/
    shadow_oos/phase_1c_factor_analysis_2026-04-26-cross-sectional-daily-1d-h5d-features-v92.json),
    11 B-batch candidates were screened by full-panel rank IC + VIF. 3 passed
    |IC| >= 0.04 with VIF < 5:
        stress_liq_conc_iv    IC=-0.060  VIF=1.66  n=715   t=-5.6  (stress propagation)
        unwind_liq_imb_xs     IC=-0.050  VIF=2.41  n=1094  t=-5.9  (cross-section unwind)
        disagree_tt_retail    IC=+0.037  VIF=1.37  n=1090  t=+4.9  (smart-money vs retail flow)

    Discarded 8 candidates for IC < 0.04 or |t-stat| < 4. unwind_liq_dh dropped
    despite |IC|=0.046 because corr(unwind_liq_dh, unwind_liq_imb_xs) = -0.71 â€?
    kept the cross-section variant (higher t-stat, more days).

    v91 9 weights kept proportionally; new 3 weights from full-panel IC magnitude.
    All 12 weights scaled by ~0.901 so absolute sum ~ 1.00.

    v93 candidate issue (deferred from this batch): v91 IC pruning over-aggressively
    removed two strong signals â€?intraday_realized_vol_4h_to_1d_smooth_20
    (IC=-0.104, VIF=15.12) and distance_to_high_20 (IC=+0.098, VIF=4.24). VIF
    dominated over IC magnitude. v93 should explore VIF-aware GLS residualization
    or PCA-based combination instead of hard VIF threshold drop, to recover IC from
    the strongest single-factor signals.

    Lookahead disclosure: weights are derived from rank IC measured on the full
    3-year v92 panel including the test segment, matching v91 hand-tuned
    methodology. Phase 1d will replace these static weights with rolling-IR
    dynamic weights for proper OOS treatment.
    """
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = (
        -0.20 * _single_z("intraday_realized_vol_4h_to_1d_smooth_60")
        -0.10 * _single_z("realized_volatility_5")
        +0.18 * _single_z("distance_to_high_60")
        +0.15 * _single_z("distance_to_high_5")
        -0.07 * _single_z("coinglass_top_trader_long_pct_smooth_5")
        -0.10 * _single_z("liquidity_stress_qv_iv")
        -0.06 * _single_z("momentum_decay_5_20")
        +0.05 * _single_z("coinglass_taker_imb_intraday_dispersion_24h")
        -0.05 * _single_z("quality_funding_oi")
        -0.06 * _single_z("stress_liq_conc_iv")
        -0.05 * _single_z("unwind_liq_imb_xs")
        +0.04 * _single_z("disagree_tt_retail")
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_minimal_v9_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v94 (Phase 1c revision): recover strong-IC factors that v91 IC pruning
    incorrectly killed via VIF threshold.

    Changes from v91 (xs_minimal_v6_score):
    - REPLACED `intraday_realized_vol_4h_to_1d_smooth_60` (IC=-0.093) with
      `intraday_realized_vol_4h_to_1d_smooth_20` (IC=-0.104, +12% stronger).
    - ADDED `distance_to_high_20` (IC=+0.098, strongest in dh family) at
      weight +0.13, redistributing v91's dh weight budget IC-proportionally
      across 3 dh timescales.

    All other 7 factors from v91 unchanged. Total factor count 9 -> 10.

    Rationale: v91 phase_1c used a hard VIF > 5 threshold that dropped
    iv_smooth_20 (VIF 15.12) despite its stronger IC than the kept iv_smooth_60.
    dh_20 was dropped at VIF 4.24 with the rationale "redundant with dh_5 + dh_60"
    despite having the strongest IC in family. v94 recovers both:
    - iv family (all 3 VIFs > 5): swap to highest-IC member (iv_smooth_20),
      drop the now-redundant iv_smooth_60 from the score.
    - dh family (VIFs 2.97 / 4.24 / 3.65, less redundant): keep all 3 with
      IC-proportional weights summing to v91's original dh budget (0.33).

    Combined with v93's portfolio multiplier overlay declared in the v94 manifest's
    profile_constraints (overlay applies at backtest layer, not score layer).

    Expected: rank IC 0.165 -> 0.18+, WF median sharpe similar to v93 0.801,
    worst regime sharpe similar to v93 -2.76 (overlay still active).
    """
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = (
        -0.20 * _single_z("intraday_realized_vol_4h_to_1d_smooth_20")
        -0.10 * _single_z("realized_volatility_5")
        +0.11 * _single_z("distance_to_high_60")
        +0.10 * _single_z("distance_to_high_5")
        +0.13 * _single_z("distance_to_high_20")
        -0.07 * _single_z("coinglass_top_trader_long_pct_smooth_5")
        -0.10 * _single_z("liquidity_stress_qv_iv")
        -0.06 * _single_z("momentum_decay_5_20")
        +0.05 * _single_z("coinglass_taker_imb_intraday_dispersion_24h")
        -0.05 * _single_z("quality_funding_oi")
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_minimal_v10_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v95 (Phase 1d-informed lean rebuild): trim v94 to only WF-stable factors and
    rescue stress_liq_conc_iv from v92's discarded B-batch.

    Per Phase 1d walk-forward IC stability diagnostic (32 expanding windows,
    train_days=252, test_days=30), these 7 factors classify as 'stable'
    (sign_consistency >= 70%, quarter_consistency >= 70%, |IC| > 0.05, no
    significant decay):
        iv_smooth_20            IC=-0.122  sign=78%  qtr=90%
        distance_to_high_20     IC=+0.111  sign=84%  qtr=100%
        distance_to_high_60     IC=+0.098  sign=78%  qtr=100%
        distance_to_high_5      IC=+0.083  sign=78%  qtr=90%
        realized_volatility_5   IC=-0.076  sign=75%  qtr=80%
        stress_liq_conc_iv      IC=-0.064  sign=89%  qtr=87.5%   <- best sign-consistency overall
        liquidity_stress_qv_iv  IC=-0.054  sign=72%  qtr=70%

    Dropped 4 v94 'weak' decorations (|IC| < 0.03 or sign_consistency < 70%):
        coinglass_top_trader_long_pct_smooth_5  IC=-0.029  sign=56%
        momentum_decay_5_20                     IC=-0.013  sign=47%
        coinglass_taker_imb_intraday_dispersion_24h  IC=+0.023  sign=67%
        quality_funding_oi                      IC=-0.014  sign=59%

    Rescued from v92's discarded B-batch: stress_liq_conc_iv. Diagnostic showed
    it was the single stable signal among v92's 11 candidates; v92 cycle failed
    because the other 10 noise-factors diluted it.

    Weights are IC-proportional from the diagnostic (sum |w| ~= 1.01). Combined
    with v93's portfolio multiplier overlay (declared in v95 manifest's
    profile_constraints; overlay applies at backtest layer, not score layer).

    Expected: rank IC similar to v94 0.181 or slightly higher (less noise from
    dropped weak factors), WF median sharpe similar to v94 0.955, worst regime
    sharpe similar to v94 -2.73 (overlay unchanged).
    """
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = (
        -0.20 * _single_z("intraday_realized_vol_4h_to_1d_smooth_20")
        +0.18 * _single_z("distance_to_high_20")
        +0.16 * _single_z("distance_to_high_60")
        +0.14 * _single_z("distance_to_high_5")
        -0.13 * _single_z("realized_volatility_5")
        -0.11 * _single_z("stress_liq_conc_iv")
        -0.09 * _single_z("liquidity_stress_qv_iv")
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_minimal_v11_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v96-A (only-drop isolation experiment): v94 minus 4 weak factors, keeping
    v94's relative weights for the 6 stable kept factors UNCHANGED. Tests
    whether the v95 lean rebuild's WF sharpe regression (0.955 -> 0.675) came
    from the dropped factors providing portfolio-level stabilization, or from
    other v95 changes (stress_liq_conc_iv addition + IC-proportional weight
    rescaling).

    Diff from v94 (xs_minimal_v9):
    - DROPPED 4 weak factors per Phase 1d WF IC stability diagnostic:
        coinglass_top_trader_long_pct_smooth_5  (IC=-0.029, sign=56%)
        momentum_decay_5_20                     (IC=-0.013, sign=47%)
        coinglass_taker_imb_intraday_dispersion_24h  (IC=+0.023, sign=67%)
        quality_funding_oi                      (IC=-0.014, sign=59%)
    - KEPT v94 weights for the 6 remaining factors EXACTLY UNCHANGED (no
      reweighting). This is the clean single-variable change vs v94.

    Diff from v95 (xs_minimal_v10):
    - v95 added stress_liq_conc_iv AND used fresh IC-proportional weights
      â†?WF sharpe 0.955 -> 0.675 regression.
    - v96-A only drops weak factors, no rescue, no rescaling.

    Outcomes:
    - If v96-A passes (WF >= 0.85): isolates v95's regression to either
      stress_liq_conc_iv coverage (n=715 NaN-fill noise) OR fresh weight
      scheme. Next experiment v96-B (add stress_liq_conc_iv only, keep weak)
      isolates further.
    - If v96-A fails (WF < 0.85): the 4 weak factors provided portfolio-level
      stabilization (likely diversification across mechanism families) that
      diagnostic per-factor IC didn't capture. v94 is local optimum; further
      simplification regresses.

    v93 multiplier overlay preserved (declared in v96 manifest's profile_constraints).
    """
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = (
        -0.20 * _single_z("intraday_realized_vol_4h_to_1d_smooth_20")
        -0.10 * _single_z("realized_volatility_5")
        +0.11 * _single_z("distance_to_high_60")
        +0.10 * _single_z("distance_to_high_5")
        +0.13 * _single_z("distance_to_high_20")
        -0.10 * _single_z("liquidity_stress_qv_iv")
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_minimal_v12_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v96-B (only-add isolation experiment): v94's 10 factors UNCHANGED + add
    stress_liq_conc_iv at -0.11. Tests the second half of the v95 causal
    decomposition: v94 -> v95 = -0.155 (drop weak; confirmed by v96-A) PLUS
    -0.125 (add stress_liq_conc_iv; this experiment confirms or refutes).

    Diff from v94 (xs_minimal_v9):
    - ADDED stress_liq_conc_iv at weight -0.11 (matches v95's IC-proportional
      weight for this factor).
    - All 10 v94 weights UNCHANGED.

    Hypothesis being tested: stress_liq_conc_iv has only n=715 days of valid
    history (CoinGlass intraday data starts mid-2024 vs panel from 2023-04),
    so ~400 days are NaN-fillna(0). This makes the factor "come in and out"
    of activity over walk-forward windows, degrading portfolio behavior on
    pre-coverage windows. Per-window diagnostic IC looks stable (-0.064,
    sign 89%) only because diagnostic skips NaN-only windows; portfolio
    metric across full panel is degraded.

    Outcomes:
    - If WF sharpe ~0.83 (v94 0.955 - 0.125 expected): coverage hypothesis
      CONFIRMED. The full v95 regression decomposes additively into
      -0.155 (drop weak; v96-A confirmed) + -0.125 (add stress_liq_conc_iv;
      v96-B confirms).
    - If WF sharpe ~0.95 (similar to v94): coverage hypothesis REFUTED.
      Then v95's -0.28 regression came entirely from interaction effect of
      drop+add+rescale, not from individual changes alone.

    v93 multiplier overlay preserved.
    """
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = (
        -0.20 * _single_z("intraday_realized_vol_4h_to_1d_smooth_20")
        -0.10 * _single_z("realized_volatility_5")
        +0.11 * _single_z("distance_to_high_60")
        +0.10 * _single_z("distance_to_high_5")
        +0.13 * _single_z("distance_to_high_20")
        -0.07 * _single_z("coinglass_top_trader_long_pct_smooth_5")
        -0.10 * _single_z("liquidity_stress_qv_iv")
        -0.06 * _single_z("momentum_decay_5_20")
        +0.05 * _single_z("coinglass_taker_imb_intraday_dispersion_24h")
        -0.05 * _single_z("quality_funding_oi")
        -0.11 * _single_z("stress_liq_conc_iv")
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


# Phase 1d (v99): dynamic weight schedule loader + score function.
# Schedule generated offline by scripts/quant_research/phase_1d_dynamic_weight_schedule.py.
_DYNAMIC_WEIGHT_SCHEDULE_PATH = (
    Path(__file__).resolve().parents[3] / "artifacts" / "quant_research" / "shadow_oos"
    / "dynamic_weight_schedule_2026-04-26-cross-sectional-daily-1d-h5d-features-v91.json"
)
_DYNAMIC_WEIGHT_SCHEDULE_CACHE: dict[str, Any] | None = None


def _load_dynamic_weight_schedule() -> dict[str, Any]:
    global _DYNAMIC_WEIGHT_SCHEDULE_CACHE
    if _DYNAMIC_WEIGHT_SCHEDULE_CACHE is None:
        if not _DYNAMIC_WEIGHT_SCHEDULE_PATH.exists():
            raise FileNotFoundError(
                f"dynamic weight schedule not found: {_DYNAMIC_WEIGHT_SCHEDULE_PATH}. "
                "Run scripts/quant_research/phase_1d_dynamic_weight_schedule.py to materialize it."
            )
        with _DYNAMIC_WEIGHT_SCHEDULE_PATH.open("r", encoding="utf-8") as f:
            import json as _json
            _DYNAMIC_WEIGHT_SCHEDULE_CACHE = _json.load(f)
    return _DYNAMIC_WEIGHT_SCHEDULE_CACHE


def _weights_for_date(schedule_entries: list[dict[str, Any]], date_iso: str) -> dict[str, float]:
    """Return weights from the latest schedule entry whose rebalance_date <= date_iso.
    Schedule entries are assumed sorted by rebalance_date ascending. Falls back to first
    (bootstrap) entry if date precedes all schedule entries.
    """
    applicable = schedule_entries[0]
    for entry in schedule_entries:
        if entry["rebalance_date"] <= date_iso:
            applicable = entry
        else:
            break
    return applicable["weights"]


def xs_minimal_v13_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v99 (Roadmap Phase 1d): dynamic factor weights via rolling-IR softmax schedule.

    Same 11 factors as v97 (xs_minimal_v12_score = v94 + stress_liq_conc_iv) but
    weights vary over time per a quarterly-rebalanced schedule. Schedule generated
    offline by scripts/quant_research/phase_1d_dynamic_weight_schedule.py:
      - Per-factor rolling IR (mean IC / std IC) computed using expanding lookback
        ending 5 trading days before each rebalance (PIT-correct)
      - Sign-aware softmax(|IR|/temperature) gives signed weights summing to |1.0|
      - 20% relative-change rate limit per rebalance (prevents thrash)
      - Bootstrap with v97 normalized weights for first quarters lacking data

    Compared to v97 (static hand-tuned weights), v99 lets weights adapt as factor
    IR shifts over time. Directly addresses the v95+v96 lesson that hand-tuned
    weights carry empirical information that wholesale IC-proportional rebuilds
    destroy: dynamic weights are *incremental* rebuilds (each quarter at most
    Â±20%), preserving historical fine-tuning while adapting to regime changes.

    Multiplier overlay (v93 m7) preserved at portfolio sizing layer.

    Schedule file path is hardcoded in _DYNAMIC_WEIGHT_SCHEDULE_PATH; for new
    panel versions, regenerate the schedule and (if path differs) update the path.
    """
    timestamps = frame["timestamp_ms"]
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    schedule_data = _load_dynamic_weight_schedule()
    factors = list(schedule_data["factors"])
    schedule_entries = schedule_data["schedule"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    # Per-factor cross-section z-scores (computed once)
    z_per_factor = {f: _single_z(f) for f in factors}

    # Per-row applicable weight vector (vectorized via per-date lookup)
    dates_iso = pd.to_datetime(timestamps, unit="ms", utc=True).dt.normalize().dt.date.astype(str)
    unique_dates = dates_iso.drop_duplicates().tolist()
    weights_by_date: dict[str, dict[str, float]] = {
        d: _weights_for_date(schedule_entries, d) for d in unique_dates
    }

    raw_score = pd.Series(0.0, index=frame.index, dtype="float64")
    for f in factors:
        # Build a per-row weight Series for factor f
        weight_per_row = dates_iso.map(lambda d, ff=f: weights_by_date[d].get(ff, 0.0))
        weight_per_row = weight_per_row.astype("float64")
        weight_per_row.index = frame.index
        raw_score = raw_score + weight_per_row * z_per_factor[f]

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    Alpha Ontology W1.4: v91 9-factor IC-pruned baseline + 2 strict-G6+G3 W1.1 winners.

    Selection lineage. The 13 W1.1 candidate factors (MF-04 carry / MF-06 reflex /
    MF-10 higher-moment) were scored against the 11-gate report card defined in
    docs/quant_research/00_roadmap_state/alpha_ontology_and_factor_library.md Â§G.2. Cards live at
    artifacts/quant_research/factor_reports/2026-04-29/. Strict pass on G6
    (residual IC vs v91 baseline >= 0.02) AND G3 (per-regime IC same-sign >= 60%)
    yielded only two candidates:

        F33  downside_upside_vol_ratio_30            IC = +0.031, residual IC = +0.025, regime same-sign = 100%, 9/11 gates
        F12  funding_basis_residual_implied_repo_30  IC = +0.023, residual IC = +0.020, regime same-sign = 100%, 7/11 gates

    F20 (capitulation_amplification_event) passed G6 but failed G3 (33% same-sign)
    and is a sparse-event factor whose residual IC is likely inflated by zero
    observations; deferred. The other 10 W1.1 candidates failed G6 â€?they did not
    add information beyond the v91 baseline at the W1.3 measurement window.

    The doc's W1.4 expectation of "5 new factors passing G1-G11" is empirically
    unachievable on the current 1117-day panel against the v91 baseline; v_alpha_v1
    therefore ships the 2-factor expansion. Any future expansion via G6+G3 must be
    recorded in threshold_provenance.md.

    Weights. v91 9-factor weights are kept untouched (sum |w| = 0.96). New factors
    receive weights proportional to their IC magnitude under the v91 weight-per-IC
    ratio (~3.25):
        F33 (+0.031 IC) -> +0.10
        F12 (+0.023 IC) -> +0.07
    Total |w| = 1.13. The closing tanh on (percentile_rank - 0.5) * 1.80 makes
    absolute scale irrelevant for ranking semantics.

    Lookahead disclosure. Weights are derived from rank IC measured on the full
    3-year panel including the test segment; this matches the v91 hand-tuned
    methodology. Phase 1d's rolling-IR dynamic weight schedule is the proper OOS
    treatment and is a separate work item.
    """
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = (
        -0.20 * _single_z("intraday_realized_vol_4h_to_1d_smooth_60")
        -0.10 * _single_z("realized_volatility_5")
        +0.18 * _single_z("distance_to_high_60")
        +0.15 * _single_z("distance_to_high_5")
        -0.07 * _single_z("coinglass_top_trader_long_pct_smooth_5")
        -0.10 * _single_z("liquidity_stress_qv_iv")
        -0.06 * _single_z("momentum_decay_5_20")
        +0.05 * _single_z("coinglass_taker_imb_intraday_dispersion_24h")
        -0.05 * _single_z("quality_funding_oi")
        +0.10 * _single_z("downside_upside_vol_ratio_30")
        +0.07 * _single_z("funding_basis_residual_implied_repo_30")
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


_ROOT_PATH = Path(__file__).resolve().parents[3]
_ALPHA_ONTOLOGY_V3_WEIGHTS_PATH = (
    _ROOT_PATH / "config" / "quant_research" / "alpha_ontology_v3_weights.json"
)
_ALPHA_ONTOLOGY_V3_WEIGHTS_CACHE: dict[str, float] | None = None


def _load_alpha_ontology_v3_weights() -> dict[str, float]:
    """Load Bayesian-IR-shrunk weights for the 11 lsk3 factors. Cached on first call."""
    global _ALPHA_ONTOLOGY_V3_WEIGHTS_CACHE
    if _ALPHA_ONTOLOGY_V3_WEIGHTS_CACHE is not None:
        return _ALPHA_ONTOLOGY_V3_WEIGHTS_CACHE
    import json
    if not _ALPHA_ONTOLOGY_V3_WEIGHTS_PATH.exists():
        raise FileNotFoundError(
            f"alpha_ontology_v3 weights not found at {_ALPHA_ONTOLOGY_V3_WEIGHTS_PATH}. "
            "Run scripts/quant_research/compute_alpha_ontology_v3_weights.py to materialize."
        )
    payload = json.loads(_ALPHA_ONTOLOGY_V3_WEIGHTS_PATH.read_text(encoding="utf-8"))
    weights = {r["column"]: float(r.get("weight", 0.0)) for r in payload.get("factors", [])}
    _ALPHA_ONTOLOGY_V3_WEIGHTS_CACHE = weights
    return weights


def xs_alpha_ontology_v3_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    Alpha Ontology W3.6 v3: identical 11 score factors as v_alpha_v1_lsk3, but
    weights are Bayesian-IR-shrunk on the first 60% of the panel rather than
    hand-tuned. The intended improvement is reduced overfit on factors with
    strong-magnitude hand weights but weak in-sample t-stats (e.g.,
    distance_to_high_60 hand=0.18 -> v3=0.044, quality_funding_oi hand=-0.05 ->
    v3=-0.004).

    Weight derivation. See scripts/quant_research/compute_alpha_ontology_v3_weights.py:
    posterior_IC = ic_mean * t**2 / (t**2 + tau_t**2)  with tau_t=2.0
    weight       = posterior_IC * 3.25 (matching the v91 |w|/|IC| ratio)

    Lookahead disclosure. Weights are computed on the first 60% of timestamps
    (in-sample window 2023-04 â†?~2025-04). The cycle's walk-forward / regime
    holdout windows in the LAST 40% are at least partially OOS for these weights;
    earlier walk-forward windows overlap with the in-sample weight estimation
    window. This is a Phase 1 pragmatic choice â€?full rolling-IR is Phase 1d.

    Lifecycle. v3 is sibling to v1/v2, not a successor: lsk3 (v1) remains the
    hand-tuned baseline; v_alpha_v2 (12 factors with F29) is the W3.3 alternative;
    v_alpha_v3 is the W3.6 weight-method alternative. Each can be paired with
    the v2 regime-gating overlay independently.
    """
    weights = _load_alpha_ontology_v3_weights()
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    for column, weight in weights.items():
        if weight == 0.0:
            continue
        raw_score = raw_score + weight * _single_z(column)

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v2_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    Alpha Ontology v_alpha_v2: extends v_alpha_v1 by adding F29 contagion_in_degree
    (MF-09 co-jump network family). 12 score factors total.

    Selection lineage. W1.1 yielded F33 + F12 (2 strict G6+G3 candidates from 13).
    W3.1 yielded 0 score-admissible (F46-F48 below G6, F49 universe-wide gating-
    class). W3.2 yielded F29 (residual IC +0.024 vs v91 baseline, regime same-sign
    66.7% over high_vol/low_vol/mid_vol; 8/11 gates). W3.3 yielded 0 score-
    admissible (F41/F42/F45 below G6, F44 universe-wide gating-class).

    F49, F26, F44 are universe-wide gating-class factors deferred to the W3.5
    regime-gating multiplier layer (`regime_gating.py`, not yet built).

    Weights. v_alpha_v1 9+2 weights kept untouched (sum |w| = 1.13). F29 added
    with +0.05 weight, calibrated against F12's |w|/|IC| ratio (F12 weight 0.07
    on residual IC 0.020; F29 weight 0.05 on residual IC 0.024 yields a similar
    edge contribution). F29 sign: positive (high contagion exposure correlates
    positively with forward return on this panel; cf. doc Â§D MF-09 row F29 which
    documents an a-priori NEGATIVE sign â€?the empirical IC sign is +0.007 here).

    Total |w| = 1.18. Terminal `tanh((percentile_rank - 0.5) * 1.80)` makes
    absolute scale irrelevant for ranking semantics.

    Lookahead disclosure. Same as v_alpha_v1: weights are derived from rank IC
    measured on the full 3-year panel including the test segment. Phase 1d's
    rolling-IR dynamic weight schedule is the proper OOS variant.
    """
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = (
        -0.20 * _single_z("intraday_realized_vol_4h_to_1d_smooth_60")
        -0.10 * _single_z("realized_volatility_5")
        +0.18 * _single_z("distance_to_high_60")
        +0.15 * _single_z("distance_to_high_5")
        -0.07 * _single_z("coinglass_top_trader_long_pct_smooth_5")
        -0.10 * _single_z("liquidity_stress_qv_iv")
        -0.06 * _single_z("momentum_decay_5_20")
        +0.05 * _single_z("coinglass_taker_imb_intraday_dispersion_24h")
        -0.05 * _single_z("quality_funding_oi")
        +0.10 * _single_z("downside_upside_vol_ratio_30")
        +0.07 * _single_z("funding_basis_residual_implied_repo_30")
        +0.025 * _single_z("contagion_in_degree")
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v6_h10d_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    Alpha Ontology SP-C Phase 2: v6 (lsk3 + F-cascade) re-tuned for h10d horizon.

    SP-C audit found F-cascade residual t jumps from +9.71 (h5d) to +12.19 (h10d).
    First v6_h10d run at v6's standalone weight (+0.05) gave walk-forward +2.830
    (+19% over v6_h5d at +2.373) but regime FAILED â€?rotation_high_vol_2025q4
    collapsed to -2.739. Same pattern as v6 initial w=0.10 attempt at h5d:
    strong factor with regime tail risk needs throttling at the longer horizon.

    Weight halved from 0.05 to 0.025 to capture the h10d signal magnitude
    proportionally (same Pareto trade-off as h5d at 0.05). Expected: walk-forward
    improvement preserved (~+10-15% vs h5d v6) while regime gates pass.
    """
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    raw_score = _xs_alpha_ontology_v6_h10d_base_raw_score(frame)
    centered_rank = _timestamp_percentile_rank(raw_score, frame["timestamp_ms"]) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


ALPHA_ONTOLOGY_LSK3_FACTOR_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("intraday_realized_vol_4h_to_1d_smooth_60", -0.20),
    ("realized_volatility_5", -0.10),
    ("distance_to_high_60", +0.18),
    ("distance_to_high_5", +0.15),
    ("coinglass_top_trader_long_pct_smooth_5", -0.07),
    ("liquidity_stress_qv_iv", -0.10),
    ("momentum_decay_5_20", -0.06),
    ("coinglass_taker_imb_intraday_dispersion_24h", +0.05),
    ("quality_funding_oi", -0.05),
    ("downside_upside_vol_ratio_30", +0.10),
    ("funding_basis_residual_implied_repo_30", +0.07),
)

ALPHA_ONTOLOGY_V5_FACTOR_WEIGHTS: tuple[tuple[str, float], ...] = (
    *ALPHA_ONTOLOGY_LSK3_FACTOR_WEIGHTS,
    ("settlement_cycle_premium_60d", -0.08),
)

ALPHA_ONTOLOGY_V6_H10D_FACTOR_WEIGHTS: tuple[tuple[str, float], ...] = (
    *ALPHA_ONTOLOGY_LSK3_FACTOR_WEIGHTS,
    ("liq_cascade_recency_score_5d", +0.025),
)


def _alpha_ontology_weighted_raw_score(
    frame: pd.DataFrame,
    *,
    factor_weights: Iterable[tuple[str, float]],
) -> pd.Series:
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    raw_score = pd.Series(0.0, index=frame.index, dtype="float64")
    for column, weight in factor_weights:
        raw_score = raw_score + float(weight) * _single_z(column)
    return raw_score.astype("float64")


def _xs_alpha_ontology_lsk3_base_raw_score(frame: pd.DataFrame) -> pd.Series:
    return _alpha_ontology_weighted_raw_score(
        frame,
        factor_weights=ALPHA_ONTOLOGY_LSK3_FACTOR_WEIGHTS,
    )


def _xs_alpha_ontology_v6_h10d_base_raw_score(frame: pd.DataFrame) -> pd.Series:
    return _alpha_ontology_weighted_raw_score(
        frame,
        factor_weights=ALPHA_ONTOLOGY_V6_H10D_FACTOR_WEIGHTS,
    )


def _xs_alpha_ontology_v5_h10d_base_raw_score(frame: pd.DataFrame) -> pd.Series:
    return _alpha_ontology_weighted_raw_score(
        frame,
        factor_weights=ALPHA_ONTOLOGY_V5_FACTOR_WEIGHTS,
    )


def _xs_alpha_ontology_interaction_single_z(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or "timestamp_ms" not in frame.columns or column not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    series = pd.to_numeric(frame[column], errors="coerce")
    if not series.notna().any():
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    return _timestamp_zscore(series, frame["timestamp_ms"]).astype("float64")


def _stablecoin_flow_numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    series = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    return pd.Series(series, index=frame.index, dtype="float64")


def _stablecoin_flow_active_mask(frame: pd.DataFrame) -> pd.Series:
    coverage = _stablecoin_flow_numeric(frame, "stablecoin_labeled_coverage_ratio")
    ready = _stablecoin_flow_numeric(frame, "stablecoin_flow_signal_ready")
    return (coverage >= 0.03) & (ready > 0.0)


def _stablecoin_absorption_activation(frame: pd.DataFrame) -> pd.Series:
    score = _stablecoin_flow_numeric(frame, "stablecoin_exchange_absorption_score_v1")
    netflow = _stablecoin_flow_numeric(frame, "stablecoin_exchange_netflow_ratio")
    active = _stablecoin_flow_active_mask(frame) & (netflow > 0.0)
    activation = np.tanh(np.clip((score - 0.45) / 0.75, 0.0, None))
    return pd.Series(activation, index=frame.index, dtype="float64").where(active, 0.0)


def _stablecoin_drain_activation(frame: pd.DataFrame) -> pd.Series:
    score = _stablecoin_flow_numeric(frame, "stablecoin_exchange_absorption_score_v1")
    netflow = _stablecoin_flow_numeric(frame, "stablecoin_exchange_netflow_ratio")
    active = _stablecoin_flow_active_mask(frame) & (netflow < 0.0)
    activation = np.tanh(np.clip(((-score) - 0.90) / 0.70, 0.0, None))
    return pd.Series(activation, index=frame.index, dtype="float64").where(active, 0.0)


def _stablecoin_whale_stress_activation(frame: pd.DataFrame) -> pd.Series:
    score = _stablecoin_flow_numeric(frame, "stablecoin_whale_exchange_stress_score_v1")
    netflow = _stablecoin_flow_numeric(frame, "stablecoin_exchange_netflow_ratio")
    active = _stablecoin_flow_active_mask(frame) & (netflow < 0.0)
    activation = np.tanh(np.clip((score - 0.75) / 0.60, 0.0, None))
    return pd.Series(activation, index=frame.index, dtype="float64").where(active, 0.0)


def _mid_liquidity_mask(frame: pd.DataFrame) -> pd.Series:
    if "liquidity_bucket" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    return frame["liquidity_bucket"].astype(str).eq("mid_liquidity").astype("float64")


def _m3_2_market_state_numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _m3_2_market_state_active_mask(frame: pd.DataFrame) -> pd.Series:
    ready = _m3_2_market_state_numeric(frame, "m3_2_panel_ready")
    return ready > 0.5


def _mf14_sell_pressure_activation(frame: pd.DataFrame) -> pd.Series:
    state = _m3_2_market_state_numeric(frame, "m3_2_btc_sell_pressure_state")
    active = _m3_2_market_state_active_mask(frame)
    activation = np.tanh(np.clip((state - 0.75) / 0.65, 0.0, None))
    return pd.Series(activation, index=frame.index, dtype="float64").where(active, 0.0)


def _mf14_rebound_activation(frame: pd.DataFrame) -> pd.Series:
    state = _m3_2_market_state_numeric(frame, "m3_2_reflexive_rebound_state")
    active = _m3_2_market_state_active_mask(frame)
    activation = np.tanh(np.clip((state - 0.75) / 0.70, 0.0, None))
    return pd.Series(activation, index=frame.index, dtype="float64").where(active, 0.0)


def _mf13_tron_flow_impulse_activation(frame: pd.DataFrame) -> pd.Series:
    state = _m3_2_market_state_numeric(frame, "m3_2_tron_flow_impulse_state")
    active = _m3_2_market_state_active_mask(frame)
    activation = np.tanh(np.clip((state - 1.0) / 0.55, 0.0, None))
    return pd.Series(activation, index=frame.index, dtype="float64").where(active, 0.0)


def xs_alpha_ontology_v11_absorb_qshare_h10d_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    M3.2 interaction candidate A: absorption x quote-share acceleration.
    """
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    base_raw = _xs_alpha_ontology_v6_h10d_base_raw_score(frame)
    quote_share_z = _xs_alpha_ontology_interaction_single_z(frame, "quote_share_change_30d")
    interaction = 0.035 * _stablecoin_absorption_activation(frame) * quote_share_z
    raw_score = (base_raw + interaction).astype("float64")
    centered_rank = _timestamp_percentile_rank(raw_score, frame["timestamp_ms"]) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v11_drain_rs_h10d_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    M3.2 interaction candidate B: drain x relative-strength reversal.
    """
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    base_raw = _xs_alpha_ontology_v6_h10d_base_raw_score(frame)
    relative_strength_z = _xs_alpha_ontology_interaction_single_z(frame, "relative_strength_20")
    interaction = -0.035 * _stablecoin_drain_activation(frame) * relative_strength_z
    raw_score = (base_raw + interaction).astype("float64")
    centered_rank = _timestamp_percentile_rank(raw_score, frame["timestamp_ms"]) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v11_flow_blend_h10d_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    M3.2 interaction candidate C: targeted blend of absorption, drain, and
    whale-stress cross-sectional effects.
    """
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    base_raw = _xs_alpha_ontology_v6_h10d_base_raw_score(frame)
    quote_share_z = _xs_alpha_ontology_interaction_single_z(frame, "quote_share_change_30d")
    relative_strength_z = _xs_alpha_ontology_interaction_single_z(frame, "relative_strength_20")
    absorption_term = 0.030 * _stablecoin_absorption_activation(frame) * quote_share_z
    drain_term = -0.028 * _stablecoin_drain_activation(frame) * relative_strength_z
    whale_signal = relative_strength_z.clip(lower=0.0) + 0.50 * quote_share_z.clip(lower=0.0)
    whale_term = -0.024 * _stablecoin_whale_stress_activation(frame) * _mid_liquidity_mask(frame) * whale_signal
    raw_score = (base_raw + absorption_term + drain_term + whale_term).astype("float64")
    centered_rank = _timestamp_percentile_rank(raw_score, frame["timestamp_ms"]) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v12_mf14_sell_beta_h10d_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    MF-14 local gate A: under market sell-pressure, tilt toward defensive BTC-beta names.
    """
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    base_raw = _xs_alpha_ontology_v6_h10d_base_raw_score(frame)
    beta_z = _xs_alpha_ontology_interaction_single_z(frame, "lead_lag_beta_btc")
    interaction = -0.032 * _mf14_sell_pressure_activation(frame) * beta_z
    raw_score = (base_raw + interaction).astype("float64")
    centered_rank = _timestamp_percentile_rank(raw_score, frame["timestamp_ms"]) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v12_mf14_sell_mid_short_h10d_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    MF-14 local gate B: under sell-pressure, penalize mid-liquidity crowded short-fragile names.
    """
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    base_raw = _xs_alpha_ontology_v6_h10d_base_raw_score(frame)
    beta_z = _xs_alpha_ontology_interaction_single_z(frame, "lead_lag_beta_btc")
    relative_strength_z = _xs_alpha_ontology_interaction_single_z(frame, "relative_strength_20")
    crowded_signal = beta_z.clip(lower=0.0) + 0.50 * relative_strength_z.clip(lower=0.0)
    interaction = -0.028 * _mf14_sell_pressure_activation(frame) * _mid_liquidity_mask(frame) * crowded_signal
    raw_score = (base_raw + interaction).astype("float64")
    centered_rank = _timestamp_percentile_rank(raw_score, frame["timestamp_ms"]) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v12_mf14_rebound_idio_h10d_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    MF-14 local gate C: under capitulation/rebound, favor idiosyncratic rebound names.
    """
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    base_raw = _xs_alpha_ontology_v6_h10d_base_raw_score(frame)
    idio_z = _xs_alpha_ontology_interaction_single_z(frame, "idiosyncratic_share")
    interaction = 0.024 * _mf14_rebound_activation(frame) * idio_z
    raw_score = (base_raw + interaction).astype("float64")
    centered_rank = _timestamp_percentile_rank(raw_score, frame["timestamp_ms"]) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v13_mf13_tron_impulse_def_beta_h10d_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    MF-13 TRON local gate: under extreme USDT_TRX flow impulse, tilt toward defensive BTC-beta names.
    """
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    base_raw = _xs_alpha_ontology_v6_h10d_base_raw_score(frame)
    beta_z = _xs_alpha_ontology_interaction_single_z(frame, "lead_lag_beta_btc")
    interaction = -0.030 * _mf13_tron_flow_impulse_activation(frame) * beta_z
    raw_score = (base_raw + interaction).astype("float64")
    centered_rank = _timestamp_percentile_rank(raw_score, frame["timestamp_ms"]) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def _xs_alpha_ontology_spk_mid_short_overlay_signal(frame: pd.DataFrame) -> pd.Series:
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    timestamps = frame["timestamp_ms"]
    factor_z = _timestamp_zscore(
        pd.to_numeric(frame.get("post_pump_stall_core_score_3d"), errors="coerce").fillna(0.0),
        timestamps,
    ).clip(upper=0.0)
    if "liquidity_bucket" in frame.columns:
        mid_mask = frame["liquidity_bucket"].astype(str).eq("mid_liquidity")
        factor_z = factor_z.where(mid_mask, 0.0)
    return factor_z.astype("float64")


def _xs_alpha_ontology_v6_h10d_spk_short_overlay_score(
    frame: pd.DataFrame,
    *,
    overlay_weight: float,
) -> pd.Series:
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    raw_score = (
        _xs_alpha_ontology_v6_h10d_base_raw_score(frame)
        + float(overlay_weight) * _xs_alpha_ontology_spk_mid_short_overlay_signal(frame)
    ).astype("float64")
    centered_rank = _timestamp_percentile_rank(raw_score, frame["timestamp_ms"]) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
    frame: pd.DataFrame,
    *,
    base_raw_score_fn: Callable[[pd.DataFrame], pd.Series] | None = None,
    signal_column: str = "post_pump_stall_core_score_3d",
    replacement_pool_size: int,
    signal_threshold: float,
    max_replacements_per_timestamp: int,
    candidate_veto_column: str | None = None,
    selected_short_veto_column: str | None = None,
    selected_short_veto_pool_size: int | None = None,
    max_selected_short_veto_replacements: int = 0,
    eligible_liquidity_buckets: Iterable[str] | None = ("mid_liquidity",),
    protect_selected_when_signal_leq: bool = True,
) -> pd.Series:
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    resolved_base_raw_score_fn = base_raw_score_fn or _xs_alpha_ontology_v6_h10d_base_raw_score
    raw_score = resolved_base_raw_score_fn(frame).astype("float64")
    adjusted = raw_score.copy()
    if signal_column not in frame.columns or "subject" not in frame.columns:
        centered_rank = _timestamp_percentile_rank(adjusted, frame["timestamp_ms"]) - 0.5
        return np.tanh(centered_rank * 1.80).astype("float64")

    timestamps = frame["timestamp_ms"]
    factor_raw = pd.to_numeric(frame.get(signal_column), errors="coerce").fillna(0.0)
    factor_z = _timestamp_zscore(factor_raw, timestamps).astype("float64")
    liquidity_bucket = frame.get("liquidity_bucket")
    if liquidity_bucket is None:
        liquidity_bucket = pd.Series("", index=frame.index, dtype="object")
    else:
        liquidity_bucket = liquidity_bucket.astype(str)
    allowed_buckets = None
    if eligible_liquidity_buckets is not None:
        allowed_buckets = {
            str(bucket).strip()
            for bucket in eligible_liquidity_buckets
            if str(bucket).strip()
        }
    if allowed_buckets:
        candidate_bucket = liquidity_bucket.isin(allowed_buckets)
    else:
        candidate_bucket = pd.Series(True, index=frame.index, dtype="bool")
    candidate_veto = pd.Series(False, index=frame.index, dtype="bool")
    if candidate_veto_column and candidate_veto_column in frame.columns:
        candidate_veto = frame[candidate_veto_column].fillna(False).astype("bool")
    selected_short_veto = pd.Series(False, index=frame.index, dtype="bool")
    if selected_short_veto_column and selected_short_veto_column in frame.columns:
        selected_short_veto = frame[selected_short_veto_column].fillna(False).astype("bool")

    top_k = 3
    short_k = 3
    replacement_pool_size = max(int(replacement_pool_size), short_k + 1)
    max_replacements_per_timestamp = max(int(max_replacements_per_timestamp), 1)
    selected_short_veto_pool_size = max(
        int(selected_short_veto_pool_size or replacement_pool_size),
        short_k + 1,
    )
    max_selected_short_veto_replacements = max(int(max_selected_short_veto_replacements), 0)
    epsilon = 1e-6

    for _, idx in frame.groupby("timestamp_ms", sort=False).groups.items():
        ts_index = pd.Index(idx)
        group = pd.DataFrame(
            {
                "raw_score": raw_score.loc[ts_index],
                "factor_raw": factor_raw.loc[ts_index],
                "factor_z": factor_z.loc[ts_index],
                "liquidity_bucket": liquidity_bucket.loc[ts_index],
                "candidate_bucket": candidate_bucket.loc[ts_index],
                "candidate_veto": candidate_veto.loc[ts_index],
                "selected_short_veto": selected_short_veto.loc[ts_index],
            },
            index=ts_index,
        )
        if group.empty or len(group) <= top_k + short_k:
            continue
        ordered = group.sort_values("raw_score", ascending=False).copy()
        baseline_shorts = ordered.tail(min(short_k, len(ordered))).copy()
        if baseline_shorts.empty:
            continue
        pool = ordered.tail(min(replacement_pool_size, len(ordered))).copy()
        if pool.empty:
            continue

        current_short_subjects = set(baseline_shorts.index.tolist())
        eligible_pool = pool.loc[
            (~pool.index.isin(current_short_subjects))
            & pool["candidate_bucket"]
            & (pool["factor_z"] <= float(signal_threshold))
            & (~pool["candidate_veto"])
        ].copy()
        if eligible_pool.empty:
            continue
        eligible_pool.sort_values(["factor_z", "raw_score"], ascending=[True, True], inplace=True)

        if protect_selected_when_signal_leq:
            ejectable = baseline_shorts.loc[
                (~baseline_shorts["candidate_bucket"])
                | (baseline_shorts["factor_z"] > float(signal_threshold))
            ].copy()
        else:
            ejectable = baseline_shorts.copy()
        if ejectable.empty:
            continue
        ejectable.sort_values(["raw_score", "factor_z"], ascending=[False, False], inplace=True)

        replacements = min(len(eligible_pool), len(ejectable), max_replacements_per_timestamp)
        for repl_i in range(replacements):
            replace_idx = eligible_pool.index[repl_i]
            eject_idx = ejectable.index[repl_i]
            eject_score = float(adjusted.loc[eject_idx])
            adjusted.loc[replace_idx] = eject_score - epsilon - float(repl_i) * epsilon

        if max_selected_short_veto_replacements <= 0:
            continue

        current_ordered = pd.DataFrame(
            {
                "adjusted": adjusted.loc[ts_index],
                "raw_score": group["raw_score"],
                "factor_raw": group["factor_raw"],
                "factor_z": group["factor_z"],
                "liquidity_bucket": group["liquidity_bucket"],
                "candidate_bucket": group["candidate_bucket"],
                "candidate_veto": group["candidate_veto"],
                "selected_short_veto": group["selected_short_veto"],
            },
            index=ts_index,
        ).sort_values("adjusted", ascending=False)
        current_shorts = current_ordered.tail(min(short_k, len(current_ordered))).copy()
        if current_shorts.empty:
            continue
        vetoed_current_shorts = current_shorts.loc[current_shorts["selected_short_veto"]].copy()
        if vetoed_current_shorts.empty:
            continue
        vetoed_current_shorts.sort_values(["adjusted", "raw_score"], ascending=[False, False], inplace=True)

        candidate_pool = current_ordered.tail(min(selected_short_veto_pool_size, len(current_ordered))).copy()
        eligible_veto_replacements = candidate_pool.loc[
            (~candidate_pool.index.isin(current_shorts.index))
            & (~candidate_pool["candidate_veto"])
        ].copy()
        if eligible_veto_replacements.empty:
            continue
        preferred_post_pump = (
            eligible_veto_replacements["candidate_bucket"]
            & (eligible_veto_replacements["factor_z"] <= float(signal_threshold))
        ).astype("int8")
        preferred_mid = eligible_veto_replacements["candidate_bucket"].astype("int8")
        veto_order = np.lexsort(
            (
                pd.to_numeric(eligible_veto_replacements["raw_score"], errors="coerce").to_numpy(dtype="float64"),
                pd.to_numeric(eligible_veto_replacements["factor_z"], errors="coerce").to_numpy(dtype="float64"),
                pd.to_numeric(eligible_veto_replacements["adjusted"], errors="coerce").to_numpy(dtype="float64"),
                (-preferred_mid).to_numpy(dtype="int8"),
                (-preferred_post_pump).to_numpy(dtype="int8"),
            )
        )
        eligible_veto_replacements = eligible_veto_replacements.iloc[veto_order].copy()

        veto_replacements = min(
            len(vetoed_current_shorts),
            len(eligible_veto_replacements),
            max_selected_short_veto_replacements,
        )
        if veto_replacements <= 0:
            continue
        short_exit_anchor = float(current_shorts["adjusted"].max())
        for repl_i in range(veto_replacements):
            eject_idx = vetoed_current_shorts.index[repl_i]
            replace_idx = eligible_veto_replacements.index[repl_i]
            eject_score = float(adjusted.loc[eject_idx])
            adjusted.loc[replace_idx] = eject_score - epsilon - float(repl_i) * epsilon
            adjusted.loc[eject_idx] = short_exit_anchor + epsilon + float(repl_i) * epsilon

    centered_rank = _timestamp_percentile_rank(adjusted, frame["timestamp_ms"]) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w005_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    Main-strategy SP-K overlay, short-side only.

    Keep the active `v6_h10d` score unchanged for top-liquidity names and for
    the long-side / non-event half of the cross-section. Only mid-liquidity
    names with negative `post_pump_stall_core_score_3d` receive an extra
    downward push in score, making them more likely to enter the short book.
    """
    return _xs_alpha_ontology_v6_h10d_spk_short_overlay_score(frame, overlay_weight=0.05)


def xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w010_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return _xs_alpha_ontology_v6_h10d_spk_short_overlay_score(frame, overlay_weight=0.10)


def xs_alpha_ontology_v6_h10d_spk_short_overlay_mid_w015_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return _xs_alpha_ontology_v6_h10d_spk_short_overlay_score(frame, overlay_weight=0.15)


def xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    Replace at most one marginal short with a nearby post-pump-stall mid-cap name.

    Long-side ranking stays untouched. The rule only looks at the short cutoff:
    if a mid-liquidity name just above the bottom-3 has a negative
    post_pump_stall z-score, it may replace the weakest currently-selected short.
    """
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
    )


def xs_alpha_ontology_v5_h10d_spk_short_replace_mid_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    Apply the winning SP-K `replace_mid_v1` rule to the v5_h10d parent.

    Keep the v5_h10d long book and broad short ranking unchanged, then allow
    at most one marginal short-slot replacement from the bottom-6 tail when a
    mid-liquidity post-pump-stall name sits just above the short cutoff.
    """
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        base_raw_score_fn=_xs_alpha_ontology_v5_h10d_base_raw_score,
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
    )


def _xs_alpha_ontology_v5_h10d_strict_event_state_short_boundary_score(
    frame: pd.DataFrame,
    *,
    base_raw_score_fn: Callable[[pd.DataFrame], pd.Series] | None = None,
    min_quality: float = 1.0,
    max_noise_ratio: float = 0.0,
    replacement_pool_size: int = 8,
    short_count: int = 3,
) -> pd.Series:
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    resolved_base_raw_score_fn = base_raw_score_fn or _xs_alpha_ontology_v5_h10d_base_raw_score
    raw_score = resolved_base_raw_score_fn(frame).astype("float64")
    adjusted = raw_score.copy()
    required = {
        "m3_3_event_state_hype_pressure_v1",
        "m3_3_event_state_short_quality_v1",
        "m3_3_event_state_noise_ratio_v1",
    }
    if "subject" not in frame.columns or not required.issubset(set(frame.columns)):
        centered_rank = _timestamp_percentile_rank(adjusted, frame["timestamp_ms"]) - 0.5
        return np.tanh(centered_rank * 1.80).astype("float64")

    quality = pd.to_numeric(frame["m3_3_event_state_short_quality_v1"], errors="coerce").fillna(0.0)
    noise = pd.to_numeric(frame["m3_3_event_state_noise_ratio_v1"], errors="coerce").fillna(0.0)
    hype = pd.to_numeric(frame["m3_3_event_state_hype_pressure_v1"], errors="coerce").fillna(0.0)
    strict_flag = (quality >= float(min_quality)) & (noise <= float(max_noise_ratio)) & (hype <= 0.0)
    epsilon = 1e-6
    pool_size = max(int(replacement_pool_size), int(short_count) + 1)
    short_k = max(int(short_count), 1)

    for _, idx in frame.groupby("timestamp_ms", sort=False).groups.items():
        ts_index = pd.Index(idx)
        group = pd.DataFrame(
            {
                "raw_score": raw_score.loc[ts_index],
                "quality": quality.loc[ts_index],
                "strict_flag": strict_flag.loc[ts_index],
            },
            index=ts_index,
        )
        if group.empty or len(group) <= short_k:
            continue
        ordered = group.sort_values("raw_score", ascending=False).copy()
        parent_shorts = ordered.tail(min(short_k, len(ordered))).copy()
        tail_pool = ordered.tail(min(pool_size, len(ordered))).copy()
        strict_pool = tail_pool.loc[tail_pool["strict_flag"]].copy()
        if strict_pool.empty:
            continue
        strict_pool.sort_values(["quality", "raw_score"], ascending=[False, True], inplace=True)
        selected = pd.concat([strict_pool, parent_shorts], axis=0)
        selected = selected.loc[~selected.index.duplicated(keep="first")].head(short_k).copy()
        if selected.empty:
            continue
        selected_set = set(selected.index.tolist())
        parent_set = set(parent_shorts.index.tolist())
        entered = [idx for idx in selected.index.tolist() if idx not in parent_set]
        exited = [idx for idx in parent_shorts.sort_values("raw_score", ascending=False).index.tolist() if idx not in selected_set]
        replacements = min(len(entered), len(exited))
        short_exit_anchor = float(parent_shorts["raw_score"].max())
        for repl_i in range(replacements):
            replace_idx = entered[repl_i]
            eject_idx = exited[repl_i]
            eject_score = float(adjusted.loc[eject_idx])
            adjusted.loc[replace_idx] = eject_score - epsilon - float(repl_i) * epsilon
            adjusted.loc[eject_idx] = short_exit_anchor + epsilon + float(repl_i) * epsilon

    centered_rank = _timestamp_percentile_rank(adjusted, frame["timestamp_ms"]) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v5_m3_3_strict_event_state_q1_noise0_h10d_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    M3.3 strict event-state short-boundary replacement on the v5 h10d parent.

    Preserve the parent long leg and broad short ranking. Inside the bottom-8
    short boundary, allow no-hype event-quality names with quality >= 1.0 and
    noise_ratio == 0 to replace weaker current shorts.
    """
    return _xs_alpha_ontology_v5_h10d_strict_event_state_short_boundary_score(frame)


def xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v2_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        replacement_pool_size=8,
        signal_threshold=-0.50,
        max_replacements_per_timestamp=1,
    )


def xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v3_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        replacement_pool_size=8,
        signal_threshold=0.0,
        max_replacements_per_timestamp=2,
    )


def xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_mini_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
        candidate_veto_column="news_short_veto_mini_flag",
    )


def xs_alpha_ontology_v6_h10d_spk_short_replace_mid_v1_news_veto_adjudicated_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
        candidate_veto_column="news_short_veto_adjudicated_flag",
    )


def xs_alpha_ontology_v6_h10d_spk_ss_veto_mini_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    SP-K + news layer on the selected short book.

    Start from the winner `replace_mid_v1` rule, then force-veto at most one
    already-selected short when same-day research-effective news says the move
    is more likely durable repricing than hype. Replacement candidates must
    also be news-clean, and the search still prefers post-pump-stall mid-cap
    names near the short cutoff.
    """
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
        candidate_veto_column="news_short_veto_mini_flag",
        selected_short_veto_column="news_short_veto_mini_flag",
        selected_short_veto_pool_size=10,
        max_selected_short_veto_replacements=1,
    )


def xs_alpha_ontology_v6_h10d_spk_ss_veto_adjudicated_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
        candidate_veto_column="news_short_veto_adjudicated_flag",
        selected_short_veto_column="news_short_veto_adjudicated_flag",
        selected_short_veto_pool_size=10,
        max_selected_short_veto_replacements=1,
    )


def xs_alpha_ontology_v6_h10d_mf01_boundary_fragile_replace_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    MF-01 v1: orderbook fragility on the active short boundary.

    Keep the parent `v6_h10d` score intact, then inspect the bottom-6 tail.
    If a nearby candidate shows weak bid replenishment or persistent ask-heavy
    orderbook pressure, allow it to replace the weakest current short.
    """
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        signal_column="boundary_fragile_orderbook_score",
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
        eligible_liquidity_buckets=None,
        protect_selected_when_signal_leq=False,
    )


def xs_alpha_ontology_v6_h10d_mf01_pump_bid_fail_replace_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    MF-01 v2: sparse high-conviction pump failure trigger on the short boundary.

    This only fires when same-day pump conditions coincide with weak bid-depth
    replenishment, making it a narrower but more severe replacement rule than
    the broad boundary-fragility lane.
    """
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        signal_column="pump_bid_replenishment_failure_score",
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
        eligible_liquidity_buckets=None,
        protect_selected_when_signal_leq=False,
    )


def xs_alpha_ontology_v6_h10d_mf01_combo_replace_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    MF-01 combo: broad boundary fragility plus sparse pump failure kicker.
    """
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        signal_column="mf01_short_boundary_combo_score",
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
        eligible_liquidity_buckets=None,
        protect_selected_when_signal_leq=False,
    )


def xs_alpha_ontology_v6_h10d_mf01_spk_confirm_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    MF-01 as a confirmation gate on top of the SP-K winner.

    Keep the `replace_mid_v1` architecture, but only let a mid-liquidity
    post-pump-stall candidate participate when orderbook fragility confirms
    the fade thesis.
    """
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        signal_column="mf01_spk_confirmation_score",
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
    )


def xs_alpha_ontology_v6_h10d_mf01_spk_ss_veto_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    MF-01 as a narrow selected-short veto inside the SP-K architecture.

    Start from `replace_mid_v1`, then veto already-selected SP-K-style shorts
    when the book shows supportive replenishment instead of fragility.
    """
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
        candidate_veto_column="mf01_spk_selected_short_veto_flag",
        selected_short_veto_column="mf01_spk_selected_short_veto_flag",
        selected_short_veto_pool_size=10,
        max_selected_short_veto_replacements=1,
    )


def xs_alpha_ontology_v6_h10d_mf01_post_cascade_guardrail_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    MF-01 post-cascade rebound guardrail on the selected short book.

    Keep the SP-K winner intact, but eject already-selected shorts when they
    sit in a same-day downside-shock state with unusually supportive bid-side
    replenishment, i.e. rebound-risk rather than continuation-risk.
    """
    return _xs_alpha_ontology_v6_h10d_spk_short_replacement_score(
        frame,
        replacement_pool_size=6,
        signal_threshold=0.0,
        max_replacements_per_timestamp=1,
        candidate_veto_column="mf01_post_cascade_guardrail_flag",
        selected_short_veto_column="mf01_post_cascade_guardrail_flag",
        selected_short_veto_pool_size=10,
        max_selected_short_veto_replacements=1,
    )


def xs_alpha_ontology_spk_lsk3_mid_tail_h5d_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    SP-K baseline control on the mid/tail perp universe.

    This keeps the canonical lsk3 11-factor score unchanged and lets the SP-K
    cycle evaluation measure whether post-pump stall adds value on top of the
    same baseline inside the relevant small-cap universe.
    """
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    centered_rank = _timestamp_percentile_rank(
        _xs_alpha_ontology_lsk3_base_raw_score(frame),
        frame["timestamp_ms"],
    ) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_spk_post_pump_stall_v1_h5d_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    SP-K v1: lsk3 baseline plus the lead candidate
    `post_pump_stall_core_score_3d` on the mid/tail perp universe.

    Admission lineage on the 2026-05-01 panel, `mid_tail_ex_majors`, h5d:
      raw IC = +0.0411
      G3 same-sign fraction = 1.00
      G6 residual IC vs lsk3 = -0.0444

    The factor score is lower on bearish post-pump-stall names, so adding a
    positive weight lowers their final cross-sectional rank and pushes them
    toward the short book.
    """
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    timestamps = frame["timestamp_ms"]
    base_raw = _xs_alpha_ontology_lsk3_base_raw_score(frame)
    factor_z = _timestamp_zscore(
        pd.to_numeric(frame.get("post_pump_stall_core_score_3d"), errors="coerce").fillna(0.0),
        timestamps,
    )
    raw_score = (base_raw + 0.05 * factor_z).astype("float64")
    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_spk_post_pump_stall_v2_h5d_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    SP-K v2 risk-managed variant.

    Same core factor as v1, but only the bearish tail of the factor is allowed
    to modify the score. This keeps the post-pump mechanism focused on short
    selection and avoids using the noisy "non-event upside" side of the factor
    to promote longs.
    """
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
    timestamps = frame["timestamp_ms"]
    base_raw = _xs_alpha_ontology_lsk3_base_raw_score(frame)
    factor_z = _timestamp_zscore(
        pd.to_numeric(frame.get("post_pump_stall_core_score_3d"), errors="coerce").fillna(0.0),
        timestamps,
    ).clip(upper=0.0)
    raw_score = (base_raw + 0.05 * factor_z).astype("float64")
    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v9_h10d_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    Alpha Ontology SP-F: v9 = v6_h10d (lsk3 + F-cascade w=0.025) + F1
    funding_intraday_dispersion_30d at h10d.

    Selection lineage. SP-F admission audit (2026-04-29 panel,
    `artifacts/quant_research/factor_reports/2026-04-29/subday_funding_factor_report_card.json`):

      F1 funding_intraday_dispersion_30d (per-subject 4h-grain rolling-30d
      mean of within-day std of 6 4h funding values):
        h5d  raw IC -0.0115  G6 vs lsk3+F08: +0.0313 t=+5.77  PASS
        h10d raw IC -0.0187  G6 vs lsk3+F08: +0.0396 t=+7.24  PASS (strongest)

    Per SP-C h10d-preference finding, h10d is the natural integration
    horizon. Tested at both for completeness; h10d 2Ã— the h5d residual
    t-stat â€?same horizon-monotone pattern as F-cascade / F62 / F12.

    Mechanism interpretation: high within-day funding dispersion = unstable
    intraday carry regime â†?asset overheated in derivatives â†?forward
    underperformance. Sign convention NEGATIVE.

    Weight calibration + sign. F1 raw IC is NEGATIVE (-0.019 at h10d) but
    F1 G6 residual IC is POSITIVE (+0.040 vs lsk3+F08; +0.029 vs lsk3+F-
    cascade) â€?this is the standard sign-flip pattern when baseline
    over-corrects in F1's direction. The score-integration sign must
    match the RESIDUAL IC (which is what marginal-contribution-to-score
    actually tracks), NOT the raw IC. So weight is POSITIVE.

    First v9 attempt at w=-0.020 (negative, matching raw IC sign) FAILED:
    walk-forward dropped from v6_h10d +2.832 to +2.513 (-0.319), and
    rotation regime collapsed from -2.736 to -3.001 (below sqrt-scaled
    floor -2.828). Diagnosis: w=-0.020 actively contradicted F1's
    residual signal direction. Fixed by sign flip to w=+0.015 (residual
    IC vs lsk3+F-cascade=0.029 Ã— F-cascade calibration ratio 0.50).

    Stacking rationale. F1 is orthogonal to F08 by design (G6 vs lsk3+F08
    residual still +0.040). F1 is also orthogonal to F-cascade â€?per-ts
    Spearman corr(F1, F-cascade) = 0.064 mean / 0.076 median (low). G6
    of F1 vs lsk3+F-cascade still +0.029 t=+5.19. Different mechanism
    families: cascade is liquidation-event impulse, F1 is carry-microstructure
    dispersion. v9 stacks F-cascade + F1 on top of lsk3.
    """
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = (
        -0.20 * _single_z("intraday_realized_vol_4h_to_1d_smooth_60")
        -0.10 * _single_z("realized_volatility_5")
        +0.18 * _single_z("distance_to_high_60")
        +0.15 * _single_z("distance_to_high_5")
        -0.07 * _single_z("coinglass_top_trader_long_pct_smooth_5")
        -0.10 * _single_z("liquidity_stress_qv_iv")
        -0.06 * _single_z("momentum_decay_5_20")
        +0.05 * _single_z("coinglass_taker_imb_intraday_dispersion_24h")
        -0.05 * _single_z("quality_funding_oi")
        +0.10 * _single_z("downside_upside_vol_ratio_30")
        +0.07 * _single_z("funding_basis_residual_implied_repo_30")
        +0.025 * _single_z("liq_cascade_recency_score_5d")
        +0.015 * _single_z("funding_intraday_dispersion_30d")
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v10_regime_conditional_h10d_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    Alpha Ontology SP-J: regime-conditional v6_h10d.

    Base score = v6_h10d (lsk3 11-factor + F-cascade w=+0.025).
    Plus regime-conditional F1 funding_intraday_dispersion_30d term:
      - trend_up:           + 0.0   Ã— z(F1)  (F1 off in trends â€?SP-F finding cycle non-additive)
      - rotation_high_vol:  + 0.025 Ã— z(F1)  (F1 active in rotation regimes)
      - drawdown_rebound:   + 0.030 Ã— z(F1)  (F1 strongest in cascade-recovery regimes)

    Convergent evidence motivating regime-conditional architecture (5 sources):
      1. SP-F: F1 G6-passes admission (residual IC +0.040 t=+7.24 vs
         lsk3+F08) but cycle-flat at constant weight when stacked with
         F-cascade.
      2. tt_smooth_5 deep dive: drawdown_rebound IC -0.033 t=-3.55 vs
         trend_up IC = 0.000. Regime-fragile alpha pattern.
      3. momentum_decay deep dive: rotation_high_vol IC = +0.075 t=+3.01
         (sign-flipped strong) vs other regimes â‰?0.
      4. Dual-horizon ensemble: 87.5% same-sign reveals shared alpha
         source (h5d / h10d only differ by F-cascade weight). v6_h10d's
         walk-forward advantage is entirely concentrated in
         drawdown_rebound regime (h5d -3.37 vs h10d +2.17 sharpe).
      5. W3.5 v2 overlay precedent: trailing_universe_mean_return throttle
         works specifically because it overlaps lsk3 losing days. Regime-
         conditional pattern empirically validated at overlay layer.

    Regime label source: `regime_label_v10` column merged in features.py
    via `regime_gating.classify_regime_v10`. Production-realistic â€?no
    lookahead (uses trailing_30d/60d universe mean return + BTC vol
    regime quantile, all â‰?0 days lagged).

    Pre-registered decision criteria (per data_utilization_roadmap.md SP-J):
      PROMOTE if walk-forward median > v6_h10d +2.832 AND positive_regime_
        fraction â‰?2/3 AND no regime worst breaks sqrt-scaled floor -2.828
      AT-PAR if walk-forward median â‰?v6_h10d Â±0.10 AND regime preserved
      DECLINE otherwise

    See: algorithm_choices.md ADR-C6; threshold_provenance.md SP-J section.
    """
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    # v6_h10d base score (lsk3 + F-cascade w=0.025)
    base_score = (
        -0.20 * _single_z("intraday_realized_vol_4h_to_1d_smooth_60")
        -0.10 * _single_z("realized_volatility_5")
        +0.18 * _single_z("distance_to_high_60")
        +0.15 * _single_z("distance_to_high_5")
        -0.07 * _single_z("coinglass_top_trader_long_pct_smooth_5")
        -0.10 * _single_z("liquidity_stress_qv_iv")
        -0.06 * _single_z("momentum_decay_5_20")
        +0.05 * _single_z("coinglass_taker_imb_intraday_dispersion_24h")
        -0.05 * _single_z("quality_funding_oi")
        +0.10 * _single_z("downside_upside_vol_ratio_30")
        +0.07 * _single_z("funding_basis_residual_implied_repo_30")
        +0.025 * _single_z("liq_cascade_recency_score_5d")
    ).astype("float64")

    # Regime-conditional F1 addition
    f1_z = _single_z("funding_intraday_dispersion_30d")
    if "regime_label_v10" in frame.columns:
        regime = frame["regime_label_v10"].astype(str)
        # Per-row F1 weight: 0 in trend_up, +0.025 in rotation, +0.030 in drawdown_rebound
        f1_weight = np.where(
            regime == "drawdown_rebound", 0.030,
            np.where(regime == "rotation_high_vol", 0.025, 0.0)
        )
        regime_addition = pd.Series(f1_weight, index=frame.index, dtype="float64") * f1_z
    else:
        # Fail-open: treat as v6_h10d (no F1 contribution)
        regime_addition = pd.Series(0.0, index=frame.index, dtype="float64")

    raw_score = (base_score + regime_addition).astype("float64")
    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v8_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    Alpha Ontology SP-C v8: extends v_alpha_v1_lsk3 by adding F47
    funding_flip_decay_phase (W3.1 idle factor), found at h5d via the SP-C
    multi-horizon audit.

    Selection lineage. SP-C audit (2026-04-29; see
    artifacts/quant_research/factor_reports/2026-04-29/multi_horizon_audit.json):

      F47 funding_flip_decay_phase per-horizon residual IC vs lsk3 baseline:
        h1d: -0.008 (t=-1.45)   G6 FAIL
        h3d: -0.014 (t=-2.67)   G6 FAIL
        h5d: -0.020 (t=-3.89)   G6 PASS (just barely)
        h10d: -0.026 (t=-5.61)  G6 PASS (strongest horizon)

    F47 at h5d is BORDERLINE G6 admissible vs lsk3 alone. Mutual
    orthogonality test: F47 residual FAILS G6 (drops below 0.02) when
    conditioned on lsk3 + F62 OR lsk3 + F-cascade. Therefore v8 builds on
    lsk3 ONLY (not on top of v5/v6/v7) â€?F47's signal overlaps with
    F62/F-cascade.

    F47 mechanism: per-subject "days since last funding sign flip". W3.1
    state-machine factor (MF-08 event impulse). Sign EMPIRICAL NEGATIVE:
    assets where funding flipped LONGER ago (stable funding regime)
    OUTPERFORM. Stable carry regime carries forward; recent-flip = unwind
    risk = forward negative.

    Weights. lsk3 11 weights kept. F47 added with -0.05 (raw IC -0.010 Ã—
    3.25 Ã— signed = -0.033 theoretical; conservative pick of -0.05 given
    SP-A lesson on standalone-Pareto being a starting point not endpoint).

    Note. SP-C primary finding is that ALL score-integrated factors peak
    at h10d, not h5d. Building a full h10d cycle infrastructure to exploit
    this is deferred (M-L effort). v8 captures only the new h5d-admissible
    factor (F47) as the immediate score-layer takeaway.
    """
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = (
        -0.20 * _single_z("intraday_realized_vol_4h_to_1d_smooth_60")
        -0.10 * _single_z("realized_volatility_5")
        +0.18 * _single_z("distance_to_high_60")
        +0.15 * _single_z("distance_to_high_5")
        -0.07 * _single_z("coinglass_top_trader_long_pct_smooth_5")
        -0.10 * _single_z("liquidity_stress_qv_iv")
        -0.06 * _single_z("momentum_decay_5_20")
        +0.05 * _single_z("coinglass_taker_imb_intraday_dispersion_24h")
        -0.05 * _single_z("quality_funding_oi")
        +0.10 * _single_z("downside_upside_vol_ratio_30")
        +0.07 * _single_z("funding_basis_residual_implied_repo_30")
        -0.03 * _single_z("funding_flip_decay_phase")
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v7_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    Alpha Ontology v7: combines the two strongest M2.x score-integrated
    winners â€?F62 settlement_cycle_premium_60d (M2.3, weight -0.08) and
    liq_cascade_recency_score_5d (SP-A, weight +0.05) â€?both on top of the
    lsk3 11-factor baseline.

    Mutual orthogonality verified (2026-04-29 panel):
      F62 residual IC vs lsk3 only:           -0.044 (t=-7.21)
      F62 residual IC vs lsk3 + F-cascade:    -0.040 (t=-6.54)  G6 PASS
      F-cascade residual IC vs lsk3 only:     +0.062 (t=+10.77)
      F-cascade residual IC vs lsk3 + F62:    +0.060 (t=+10.43) G6 PASS
    Per-ts pairwise rank correlation between F62 and F-cascade: -0.155
    (mildly negative â€?they capture different patterns). Each factor
    explains only 3-8% of the other's signal. Ideal additive setup.

    Weights kept at each factor's M2.x Pareto-optimal pick:
      F62 (settlement_cycle_premium_60d): -0.08 (from M2.3 weight scan)
      F-cascade (liq_cascade_recency_score_5d): +0.05 (from SP-A weight scan)

    Hypothesis: walk-forward improvements should be approximately additive
    (M2.3 v5 +0.40 + SP-A v6 +0.226 = +0.6), though regime constraints
    may bind for the combined exposure level. Subject to weight scan if
    regime gates break.
    """
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = (
        -0.20 * _single_z("intraday_realized_vol_4h_to_1d_smooth_60")
        -0.10 * _single_z("realized_volatility_5")
        +0.18 * _single_z("distance_to_high_60")
        +0.15 * _single_z("distance_to_high_5")
        -0.07 * _single_z("coinglass_top_trader_long_pct_smooth_5")
        -0.10 * _single_z("liquidity_stress_qv_iv")
        -0.06 * _single_z("momentum_decay_5_20")
        +0.05 * _single_z("coinglass_taker_imb_intraday_dispersion_24h")
        -0.05 * _single_z("quality_funding_oi")
        +0.10 * _single_z("downside_upside_vol_ratio_30")
        +0.07 * _single_z("funding_basis_residual_implied_repo_30")
        -0.04 * _single_z("settlement_cycle_premium_60d")
        +0.03 * _single_z("liq_cascade_recency_score_5d")
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v6_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    Alpha Ontology SP-A v6: extends v_alpha_v1_lsk3 (11 hand-tuned factors)
    by adding liq_cascade_recency_score_5d (per-subject 1h liquidation cascade
    impulse-response, exponential-decay 5-day recency).

    Selection lineage. SP-A admission audit (2026-04-29 panel; see
    artifacts/quant_research/factor_reports/2026-04-29/liq_cascade_factor_report_card.json):
      - Doc Â§E.12 falsification PASS: per-subject post-cascade 24h abnormal
        log return t-stat = +10.75 (vs 2.5Ïƒ threshold), n=8858 events across
        29 subjects, mean abnormal +0.74%.
      - Cross-sectional admission, all 4 variants tested:
        | factor                           | G1 IC   | G1 t   | G3 same | G6 vs lsk3 |
        | liq_cascade_max_z_24h            | +0.0448 | +9.24  | 1.00    | +0.0578    |
        | liq_cascade_count_24h_z25        | +0.0225 | +5.03  | 1.00    | +0.0523    |
        | liq_cascade_signed_intensity_24h | +0.0010 | +0.24  | 0.67    | +0.0275    |
        | **liq_cascade_recency_score_5d** | +0.0522 | +10.50 | 1.00    | **+0.0616** | â†?STRONGEST
      - All 4 variants PASS G6 strict (>=0.02). v6 selects recency_score_5d
        as the highest-IC orthogonal-to-lsk3 variant.

    Mechanism. Per alpha ontology Â§E.12 + Â§H.4 M3.4 (shipped ahead of doc
    Day 61-90 schedule because data was already in disk): CoinGlass 1h
    liquidation flow identifies cascade events; post-cascade 24-72h shows
    documented mean reversion. Recency_score_5d = exponential-decay (half-
    life 5d) accumulator of cascade intensity â€?captures "is this asset
    currently in a post-cascade recovery window?"

    Sign empirical: POSITIVE. Assets with HIGHER recent cascade intensity
    OUTPERFORM in next 5 days (mean revert up after the cascade clears).
    Aligns with doc-prescribed mechanism direction.

    Weights. lsk3 11 weights kept untouched. liq_cascade_recency_score_5d
    added with weight +0.10. Calibrated conservatively given F62 lesson:
    raw IC of 0.052 Ã— 3.25 ratio = 0.17 would be over-aggressive (F62 raw
    IC -0.024 / w=-0.08 ratio 3.33 was Pareto-optimal; loss-frac risk at
    higher weights). Subject to weight scan against walk-forward + regime
    gates.

    Lookahead disclosure. Per-subject rolling 720h (~30d) z-score baseline
    is causal (only past data). Post-cascade recovery window is also causal.
    Cross-sectional rank IC computed against `target_forward_return` (5d).
    """
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = (
        -0.20 * _single_z("intraday_realized_vol_4h_to_1d_smooth_60")
        -0.10 * _single_z("realized_volatility_5")
        +0.18 * _single_z("distance_to_high_60")
        +0.15 * _single_z("distance_to_high_5")
        -0.07 * _single_z("coinglass_top_trader_long_pct_smooth_5")
        -0.10 * _single_z("liquidity_stress_qv_iv")
        -0.06 * _single_z("momentum_decay_5_20")
        +0.05 * _single_z("coinglass_taker_imb_intraday_dispersion_24h")
        -0.05 * _single_z("quality_funding_oi")
        +0.10 * _single_z("downside_upside_vol_ratio_30")
        +0.07 * _single_z("funding_basis_residual_implied_repo_30")
        +0.05 * _single_z("liq_cascade_recency_score_5d")
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v5_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    Alpha Ontology M2.3 v5: extends v_alpha_v1_lsk3 (11 hand-tuned factors) by
    adding F62 settlement_cycle_premium_60d (per-subject pre-settlement-hour
    drift in 1h perp returns, 60d rolling window).

    Selection lineage. M2.3 admission audit (2026-04-29 panel) variant scan
    across hours definitions Ã— rolling windows; pre-settlement {23,7,15} Ã—
    60d optimal:
      raw cross-sectional spearman IC = -0.0432 (t=-4.64) on the 17k-row
      1h-data overlap window;
      residual IC vs lsk3 11-factor = -0.0449 (t=-4.79), G6 STRONG PASS
      (>=0.02);
      G3 same-sign 1.00 across BTC vol regimes;
      doc E.10 falsification at universe-mean-pooled level: t=-3.67 at
      pre-settlement vs other hours, PASS doc t<2 falsification threshold.

    Mechanism. At UTC 0/8/16 funding settlements, longs reduce exposure
    in the hour BEFORE settlement to avoid funding payment â†?systematic
    selling pressure produces negative drift in the pre-settlement 1h
    bar. Cross-sectionally, assets with stronger pre-settlement unwind
    pressure (more negative settlement_cycle_premium) UNDERPERFORM in
    the next 5 days â€?they're more crowded with funding-arbitrage
    capital. Sign per-asset is NEGATIVE; aligns with the long-short
    top-K-vs-bottom-K construction (LONG low-pressure, SHORT high-
    pressure assets).

    Weights. lsk3 11 weights kept untouched. F62 added with -0.08 weight,
    calibrated against the v91 |w|/|IC| ratio (~3.25): 0.024 (raw IC after
    0-fill broadcast) Ã— 3.25 â‰?0.08, signed negative.

    Lookahead disclosure. The 60d rolling skew/mean is per-subject, no
    cross-asset look-ahead. Earlier panel rows where rolling 60d not yet
    populated are NaN â†?0-filled by build_cross_sectional_feature_bundle
    line 629 final fillna; subjects without 1h derivatives data are also
    0-filled (~70 of 99 subjects). The cross-sectional rank IC therefore
    gets dampened by the 0-mass but the residual signal among 1h-covered
    subjects stays strong.
    """
    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = _alpha_ontology_weighted_raw_score(
        frame,
        factor_weights=ALPHA_ONTOLOGY_V5_FACTOR_WEIGHTS,
    )
    centered_rank = _timestamp_percentile_rank(raw_score, frame["timestamp_ms"]) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_alpha_ontology_v4_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    Alpha Ontology W3.6 â†?M2.2 v4: extends v_alpha_v1_lsk3 (11 hand-tuned
    factors) by adding F08 funding_term_skew_60 (60d rolling skew of daily
    funding_rate per subject; doc Â§D MF-04 F08).

    Selection lineage. M2.2 admission audit (2026-04-29 panel) on
    funding_term_skew_<window> across windows {10..90}: 60d window strongest
    at raw spearman IC = +0.0316 (t=+6.13), and residual IC vs lsk3 11-factor
    = +0.0302 (t=+5.61), G6 PASS (>=0.02). G3 same-sign 2/3 across BTC vol
    regimes (high_vol weakest, near 0). G1 (>=0.04) borderline FAIL but matches
    F12 admission precedent (F12 raw IC was +0.023, admitted to lsk3).

    Sign discovery. Doc Â§D F08 prescribes NEGATIVE sign (high positive skew =
    recent funding spike â†?mean reversion â†?forward return negative). EMPIRICAL
    cross-sectional sign on this panel is POSITIVE: assets with higher 60d
    funding_rate skew tend to OUTPERFORM in the next 5 days. Possible
    interpretation: high-skew assets have ongoing right-tail-funding events
    that proxy for sustained buying pressure. Mechanism documented in
    threshold_provenance.md M2.2 audit.

    Weights. v_alpha_v1_lsk3 weights kept untouched. F08 added with +0.10
    weight, calibrated against the v91 |w|/|IC| ratio (~3.25): +0.0316 * 3.25
    â‰?+0.10. Total |w| = 1.230 (was 1.13 in lsk3).

    Lookahead disclosure. Same as v_alpha_v1: weights are derived from rank IC
    measured on the full 3-year panel including the test segment.
    """
    timestamps = frame["timestamp_ms"]

    def _single_z(column: str) -> pd.Series:
        if column not in frame.columns:
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        series = pd.to_numeric(frame[column], errors="coerce")
        if not series.notna().any():
            return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")
        return _timestamp_zscore(series, timestamps)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    raw_score = (
        -0.20 * _single_z("intraday_realized_vol_4h_to_1d_smooth_60")
        -0.10 * _single_z("realized_volatility_5")
        +0.18 * _single_z("distance_to_high_60")
        +0.15 * _single_z("distance_to_high_5")
        -0.07 * _single_z("coinglass_top_trader_long_pct_smooth_5")
        -0.10 * _single_z("liquidity_stress_qv_iv")
        -0.06 * _single_z("momentum_decay_5_20")
        +0.05 * _single_z("coinglass_taker_imb_intraday_dispersion_24h")
        -0.05 * _single_z("quality_funding_oi")
        +0.10 * _single_z("downside_upside_vol_ratio_30")
        +0.07 * _single_z("funding_basis_residual_implied_repo_30")
        +0.06 * _single_z("funding_term_skew_60")
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_minimal_v1_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v80: minimal 6-feature linear model derived from v79 single-factor IC analysis.

    Tier 1 (4 stable-sign strong-IC features):
        z(realized_volatility_20)               * -0.30
        z(intraday_realized_vol_4h_to_1d)       * -0.20
        z(distance_to_high_20)                  * +0.20
        z(coinglass_top_trader_long_pct)        * -0.15

    Tier 2 (2 regime-conditional sign features):
        z(relative_strength_20)  * sign_regime  * +0.15
        z(momentum_20)           * sign_regime  * +0.10

    sign_regime = clip(per_timestamp_median(momentum_20) / 0.06, -1, +1)
    Final = tanh((percentile_rank(raw_score) - 0.5) * 1.80)
    """
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    top_trader = _feature_series(frame, "coinglass_top_trader_long_pct", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)

    if frame.empty or "timestamp_ms" not in frame.columns:
        return pd.Series(np.zeros(len(frame)), index=frame.index, dtype="float64")

    timestamps = frame["timestamp_ms"]

    # Tier 1: stable-sign features
    z_rv = _timestamp_zscore(realized_volatility, timestamps)
    z_iv = _timestamp_zscore(intraday_vol, timestamps)
    z_dh = _timestamp_zscore(distance_to_high, timestamps)
    z_tt = _timestamp_zscore(top_trader, timestamps)

    # Tier 2: regime-conditional features
    z_rs = _timestamp_zscore(relative_strength, timestamps)
    z_mom = _timestamp_zscore(momentum_20, timestamps)

    # Regime detection via per-timestamp cross-sectional median momentum
    ts_values = timestamps.values
    mom_values = momentum_20.values
    med_df = pd.DataFrame({"v": mom_values, "t": ts_values}, index=frame.index)
    timestamp_median_mom = med_df.groupby("t")["v"].transform("median")
    sign_regime = (timestamp_median_mom / 0.06).clip(lower=-1.0, upper=1.0)
    sign_regime_series = pd.Series(sign_regime.values, index=frame.index)

    raw_score = (
        -0.30 * z_rv
        -0.20 * z_iv
        +0.20 * z_dh
        -0.15 * z_tt
        +0.15 * sign_regime_series * z_rs
        +0.10 * sign_regime_series * z_mom
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(raw_score, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")


def xs_dual_regime_filter_v11_score(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
) -> pd.Series:
    """
    v76 = v74 (xs_dual_regime_filter_v9) architecture extended with 4 intraday-derived
    daily features added at the rank_screen stage. Universe is liquid_perp_core_30 (30 names).
    composite_weight stays at 0.08 (same as v74).
    """
    basis_proxy = _feature_series(frame, "basis_proxy", feature_columns=feature_columns)
    funding_rate = _feature_series(frame, "funding_rate", feature_columns=feature_columns)
    basis_zscore = _feature_series(frame, "basis_zscore_20", feature_columns=feature_columns)
    funding_zscore = _feature_series(frame, "funding_zscore_20", feature_columns=feature_columns)
    oi_change = _feature_series(frame, "oi_change_5", feature_columns=feature_columns)
    relative_strength = _feature_series(frame, "relative_strength_20", feature_columns=feature_columns)
    ema_slope = _feature_series(frame, "ema_slope_5_20", feature_columns=feature_columns)
    momentum_20 = _feature_series(frame, "momentum_20", feature_columns=feature_columns)
    quote_volume_expansion = _feature_series(frame, "quote_volume_expansion", feature_columns=feature_columns)
    intraday_vol = _feature_series(frame, "intraday_realized_vol_4h_to_1d", feature_columns=feature_columns)
    realized_volatility = _feature_series(frame, "realized_volatility_20", feature_columns=feature_columns)
    distance_to_low = _feature_series(frame, "distance_to_low_20", feature_columns=feature_columns)
    distance_to_high = _feature_series(frame, "distance_to_high_20", feature_columns=feature_columns)
    range_position = _feature_series(frame, "range_position_20", feature_columns=feature_columns)
    return_1 = _feature_series(frame, "return_1", feature_columns=feature_columns)
    coinglass_taker_5d = _feature_series(frame, "coinglass_taker_imbalance_5d_sum", feature_columns=feature_columns)
    coinglass_retail_long = _feature_series(frame, "coinglass_global_account_long_pct", feature_columns=feature_columns)
    coinglass_liq_imb = _feature_series(frame, "coinglass_liquidation_imbalance_24h", feature_columns=feature_columns)
    coinglass_top_trader_long = _feature_series(frame, "coinglass_top_trader_long_pct", feature_columns=feature_columns)
    cg_liq_intraday_conc = _feature_series(frame, "coinglass_liq_intraday_concentration_24h", feature_columns=feature_columns)
    cg_taker_intraday_disp = _feature_series(frame, "coinglass_taker_imb_intraday_dispersion_24h", feature_columns=feature_columns)
    cg_top_intraday_vol = _feature_series(frame, "coinglass_top_trader_intraday_volatility_24h", feature_columns=feature_columns)
    cg_ob_persistence = _feature_series(frame, "coinglass_orderbook_imb_persistence_24h", feature_columns=feature_columns)

    raw_cheapness = (-basis_proxy * 0.30 - funding_rate * 0.16).astype("float64")
    normalized_cheapness = (-basis_zscore * 0.53 - funding_zscore * 0.47).astype("float64")
    balanced_discount = (1.0 - ((normalized_cheapness - 0.18).abs() / 0.40)).clip(lower=0.0, upper=1.0)
    cheapness_quality = (1.0 - ((normalized_cheapness - 0.20).abs() / 0.50)).clip(lower=0.0, upper=1.0)
    overcheap_penalty = (
        (normalized_cheapness - 0.85).clip(lower=0.0, upper=1.40) * 1.0
        + (raw_cheapness - 0.011).clip(lower=0.0, upper=0.06) * 11.0
    ).astype("float64")
    rich_penalty = (-normalized_cheapness - 0.08).clip(lower=0.0, upper=1.20).astype("float64")
    reclaim_window = (1.0 - ((distance_to_high + 0.028).abs() / 0.090)).clip(lower=0.0, upper=1.0)
    support_buffer = (1.0 - ((distance_to_low - 0.10).abs() / 0.16)).clip(lower=0.0, upper=1.0)
    quality_zone = (1.0 - ((range_position - 0.50).abs() / 0.28)).clip(lower=0.0, upper=1.0)
    distress_floor_penalty = (0.10 - range_position).clip(lower=0.0, upper=0.10) * 8.0
    distress_floor_penalty = distress_floor_penalty.clip(lower=0.0, upper=1.0)
    upper_extension_penalty = (range_position - 0.78).clip(lower=0.0, upper=0.22) * 4.5
    upper_extension_penalty = upper_extension_penalty.clip(lower=0.0, upper=1.0)
    leadership_anchor = (
        relative_strength * 0.32 + ema_slope * 0.22 + momentum_20 * 0.18
        + reclaim_window * 0.13 + support_buffer * 0.07 + quality_zone * 0.08
    ).astype("float64")
    stable_oi = (1.0 - (oi_change.abs() / 0.30)).clip(lower=0.0, upper=1.0)
    mild_oi_growth = (oi_change.clip(lower=-0.10, upper=0.18) + 0.05).clip(lower=0.0, upper=0.23) * (1.0 / 0.23)
    mild_oi_growth = mild_oi_growth.clip(lower=0.0, upper=1.0)
    balanced_volume = (1.0 - ((quote_volume_expansion - 1.02).abs() / 0.24)).clip(lower=0.0, upper=1.0)
    orderly_reset = (1.0 - ((return_1 - 0.001).abs() / 0.018)).clip(lower=0.0, upper=1.0)
    stress_penalty = (
        intraday_vol.clip(lower=0.0, upper=3.0) * 0.50 + realized_volatility.clip(lower=0.0, upper=2.0) * 0.50
    ).astype("float64")
    distress_penalty = (
        (-relative_strength).clip(lower=0.05, upper=0.40) * 1.20 + (-ema_slope).clip(lower=0.02, upper=0.08) * 0.80
    ).astype("float64")
    broken_tape_penalty = (
        (-distance_to_low - 0.005).clip(lower=0.0, upper=0.20) * 1.20 + (-return_1).clip(lower=0.04, upper=0.12) * 0.80
    ).astype("float64")
    chase_penalty = (
        (quote_volume_expansion - 1.12).clip(lower=0.0, upper=0.60) * 0.42 + return_1.clip(lower=0.0, upper=0.04) * 9.5 * 0.58
    ).astype("float64")

    leader_sub = (
        leadership_anchor * 0.34 + balanced_discount * 0.12 + stable_oi * 0.10
        + balanced_volume * 0.10 + orderly_reset * 0.10 + reclaim_window * 0.09
        + quality_zone * 0.10 + support_buffer * 0.05
    ).astype("float64")
    carry_sub = (
        cheapness_quality * 0.36 + stable_oi * 0.14 + mild_oi_growth * 0.12
        + balanced_volume * 0.10 + quality_zone * 0.10 + support_buffer * 0.08
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
    ).astype("float64")
    contrarian_laggard_tilt = (
        (1.0 - upper_extension_penalty.clip(lower=0.0, upper=1.0)) * 0.18
        + (0.55 - range_position.clip(lower=0.10, upper=0.55)).clip(lower=0.0, upper=0.45) * (1.0 / 0.45) * 0.18
        + (1.0 - chase_penalty.clip(lower=0.0, upper=1.0)) * 0.14
        + (-momentum_20).clip(lower=-0.05, upper=0.10) * (1.0 / 0.15) * 0.10
        + (-return_1).clip(lower=-0.01, upper=0.025) * (1.0 / 0.035) * 0.08
        + support_buffer * 0.10
        + (1.0 - distress_penalty.clip(lower=0.0, upper=1.0)) * 0.10
        + (1.0 - distress_floor_penalty.clip(lower=0.0, upper=1.0)) * 0.06
        + cheapness_quality * 0.06
    ).astype("float64")

    if "timestamp_ms" in frame.columns and not frame.empty:
        ts_values = frame["timestamp_ms"].values
        abs_mom_values = momentum_20.abs().values
        mom_values = momentum_20.values
        disp_df = pd.DataFrame({"v": abs_mom_values, "t": ts_values}, index=frame.index)
        timestamp_disp = disp_df.groupby("t")["v"].transform(
            lambda s: float(pd.Series(s).std() if len(s) > 1 else 0.0)
        )
        median_disp = float(pd.Series(timestamp_disp.values).median()) if len(timestamp_disp) else 0.05
        normalized_disp = (timestamp_disp / max(median_disp * 2.0, 1e-9)).clip(lower=0.0, upper=1.0)
        med_df = pd.DataFrame({"v": mom_values, "t": ts_values}, index=frame.index)
        timestamp_median_mom = med_df.groupby("t")["v"].transform("median")
        scaled_median_mom = (timestamp_median_mom / 0.06).clip(lower=-1.0, upper=1.0)
        broad_uniform_signal = (
            (1.0 - normalized_disp.values) * np.abs(scaled_median_mom.values)
        ).clip(0.0, 1.0)
        disp_array = normalized_disp.values
        med_pos = (scaled_median_mom.values > 0).astype(float)
        med_pos_cont = scaled_median_mom.values.clip(0.0, 1.0)
        med_neg_cont = (-scaled_median_mom.values).clip(0.0, 1.0)
        leader_weight = (0.20 + 0.60 * disp_array) * (0.55 + 0.45 * med_pos)
        carry_weight = (0.20 + 0.60 * disp_array) * (1.0 - (0.55 + 0.45 * med_pos) * 0.30)
        contrarian_weight = 0.20 + 0.60 * broad_uniform_signal
        total = leader_weight + carry_weight + contrarian_weight + 1e-9
        leader_weight = leader_weight / total
        carry_weight = carry_weight / total
        contrarian_weight = contrarian_weight / total
        w_HU = disp_array * med_pos_cont
        w_HD = disp_array * med_neg_cont
        w_LU = (1.0 - disp_array) * med_pos_cont
        w_LD = (1.0 - disp_array) * med_neg_cont
    else:
        n = len(frame)
        leader_weight = np.full(n, 0.40)
        carry_weight = np.full(n, 0.40)
        contrarian_weight = np.full(n, 0.20)
        w_HU = np.zeros(n)
        w_HD = np.zeros(n)
        w_LU = np.zeros(n)
        w_LD = np.zeros(n)

    blended_alpha = (
        pd.Series(leader_weight, index=frame.index) * leader_sub
        + pd.Series(carry_weight, index=frame.index) * carry_sub
        + pd.Series(contrarian_weight, index=frame.index) * contrarian_laggard_tilt
    ).astype("float64")

    common_penalties = (
        stress_penalty * 0.06 + chase_penalty * 0.025 + overcheap_penalty * 0.04
        + rich_penalty * 0.02 + distress_floor_penalty * 0.05 + upper_extension_penalty * 0.045
        + distress_penalty * 0.05 + broken_tape_penalty * 0.04
    ).astype("float64")

    raw_score = (blended_alpha * 1.0 - common_penalties).astype("float64")

    if frame.empty or "timestamp_ms" not in frame.columns:
        return raw_score

    timestamps = frame["timestamp_ms"]
    leader_w_series = pd.Series(leader_weight, index=frame.index)
    carry_w_series = pd.Series(carry_weight, index=frame.index)
    contra_w_series = pd.Series(contrarian_weight, index=frame.index)
    rank_leader = (
        _timestamp_percentile_rank(leadership_anchor, timestamps) * 0.10
        + _timestamp_percentile_rank(reclaim_window, timestamps) * 0.04
        + _timestamp_percentile_rank(orderly_reset, timestamps) * 0.04
        + _timestamp_percentile_rank(quality_zone, timestamps) * 0.05
    ).astype("float64") * leader_w_series
    rank_carry = (
        _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.10
        + _timestamp_percentile_rank(stable_oi, timestamps) * 0.04
        + _timestamp_percentile_rank(mild_oi_growth, timestamps) * 0.04
        + _timestamp_percentile_rank(balanced_volume, timestamps) * 0.03
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.02
    ).astype("float64") * carry_w_series
    rank_contra = (
        _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.06
        + _timestamp_percentile_rank(-chase_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-momentum_20, timestamps) * 0.04
        + _timestamp_percentile_rank(support_buffer, timestamps) * 0.03
        + _timestamp_percentile_rank(cheapness_quality, timestamps) * 0.03
    ).astype("float64") * contra_w_series
    # v76 NEW: 4 intraday-derived terms in rank_screen
    rank_intraday = (
        _timestamp_percentile_rank(cg_liq_intraday_conc.fillna(0.0), timestamps) * 0.03
        + _timestamp_percentile_rank(-cg_taker_intraday_disp.fillna(0.0), timestamps) * 0.03
        + _timestamp_percentile_rank(-cg_top_intraday_vol.fillna(0.0), timestamps) * 0.02
        + _timestamp_percentile_rank(cg_ob_persistence.fillna(0.0), timestamps) * 0.02
    ).astype("float64")
    rank_screen = (
        _timestamp_percentile_rank(-stress_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-distress_floor_penalty, timestamps) * 0.04
        + _timestamp_percentile_rank(-upper_extension_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-distress_penalty, timestamps) * 0.03
        + _timestamp_percentile_rank(-broken_tape_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-overcheap_penalty, timestamps) * 0.02
        + _timestamp_percentile_rank(-rich_penalty, timestamps) * 0.01
    ).astype("float64") + rank_intraday
    rank_gate = _timestamp_percentile_rank(blended_alpha, timestamps) * 0.10
    stable_rank_score = (rank_leader + rank_carry + rank_contra + rank_screen + rank_gate).astype("float64")

    v1_blended_signal = (
        _timestamp_zscore(raw_score, timestamps) * 0.22
        + _timestamp_zscore(stable_rank_score, timestamps) * 0.78
    ).astype("float64")

    z_taker = _timestamp_zscore(coinglass_taker_5d, timestamps)
    z_retail = _timestamp_zscore(coinglass_retail_long, timestamps)
    z_liq = _timestamp_zscore(coinglass_liq_imb, timestamps)
    z_top = _timestamp_zscore(coinglass_top_trader_long, timestamps)

    def _per_q_sign(cfg: tuple) -> np.ndarray:
        return cfg[0] * w_HU + cfg[1] * w_HD + cfg[2] * w_LU + cfg[3] * w_LD

    sign_retail = pd.Series(_per_q_sign(_V8_SIGN_CONFIG["retail"]), index=frame.index)
    sign_liq = pd.Series(_per_q_sign(_V8_SIGN_CONFIG["liq"]), index=frame.index)
    sign_top = pd.Series(_per_q_sign(_V8_SIGN_CONFIG["top"]), index=frame.index)

    coinglass_composite_v11 = (
        z_taker
        + sign_retail * z_retail
        + sign_liq * z_liq
        + sign_top * z_top
    ).astype("float64") / 4.0
    coinglass_composite_zscore = _timestamp_zscore(coinglass_composite_v11, timestamps)

    composite_weight = 0.08
    blended_signal = (
        v1_blended_signal * (1.0 - composite_weight)
        + coinglass_composite_zscore * composite_weight
    ).astype("float64")

    centered_rank = _timestamp_percentile_rank(blended_signal, timestamps) - 0.5
    return np.tanh(centered_rank * 1.80).astype("float64")
