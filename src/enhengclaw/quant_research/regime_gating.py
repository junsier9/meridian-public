"""regime_gating — universe-wide regime-aware position multiplier builders.

Per `alpha_ontology_and_factor_library.md` §G.3 and §H.2 W3.5: the
universe-wide regime gauges (F49 shock_co_occurrence_index, F26
co_jump_count_3d, F44 dispersion_of_returns, optionally F55
btc_vol_regime_quantile) belong in the position-sizing layer rather than
in the score. This module builds a deterministic
date_utc -> multiplier table from those gauges and registers it as a
position_multiplier_overlay (consumed by execution_backtest._cross_sectional_period
when a manifest's profile_constraints declares a matching overlay id).

Design.
- The overlay is built once at registration time (cached in
  multiplier_overlay._LOOKUP_CACHE) by re-building the cross-sectional
  feature bundle from the latest committed panel artifact and extracting
  the universe-wide gauges per timestamp.
- The multiplier is a smooth function of the gauges, clamped to
  [floor, 1.0] (default floor 0.3 — strategy never trades less than 30%
  of full size) so the overlay never inverts position direction, only
  scales magnitude. Stress signals reduce; calm signals leave at 1.0.
- The overlay does NOT modify v_alpha_v1_lsk3's score function or
  required_feature_columns: it sits at the portfolio sizing layer,
  multiplied into the raw target weights inside _cross_sectional_period
  (existing position_multiplier_overlay_id mechanism).

Hyperparameters (v1):
- F49 shock fraction multiplier: M_F49 = clip(1 - 4 * F49, floor, 1.0)
  Hits floor at F49 = 0.175 (17.5% of universe shocking simultaneously).
- F26 cluster count multiplier: M_F26 = clip(1 - F26 / (N * 0.30), floor, 1.0)
  Where N = universe size at timestamp (typically ~99). Hits floor when
  F26 / N >= 0.30, i.e. when 30% of universe shock-days over the past 3
  days. F26 already has 3-day rolling structure, so cluster intensity.
- F44 dispersion floor: M_F44 = clip(F44 / F44_median_60d, 0.5, 1.0)
  When dispersion is below the rolling-60d median (less idiosyncratic
  alpha to extract), scale exposure DOWN to 0.5. When at or above
  median, leave at 1.0. This is a low-dispersion-to-cash bias, not a
  high-dispersion-to-leverage signal — the cap at 1.0 prevents the
  overlay from inflating positions in dispersion-rich windows.
- Combined: M = max(floor, M_F49 * M_F26 * M_F44).

Selection evidence: this overlay is empirically untested as of
registration. The expected effect is to reduce worst-regime drawdown
magnitude on lsk3 by throttling exposure during shock-cluster windows.
A v_alpha_v1_lsk3_gated manifest is shipped alongside to test whether
the overlay improves cycle-layer regime_holdout / walk_forward metrics
relative to the un-gated lsk3 baseline.

Source data: cross-sectional daily features artifact, latest committed
location is `artifacts/quant_research/features/<date>-cross-sectional-
daily-1d-features-v1/features.csv.gz`. The default builder uses the
2026-04-29 artifact. If the artifact is missing, the builder raises
FileNotFoundError; the overlay is then unavailable and any manifest
referencing it should fall back to multiplier=1.0.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FEATURES_ARTIFACT = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "features"
    / "2026-04-29-cross-sectional-daily-1d-features-v1"
    / "features.csv.gz"
)

REGIME_GATING_CONTRACT_VERSION = "quant_regime_gating_overlay.v1"

_PANEL_INPUT_COLUMNS = (
    "subject", "timestamp_ms", "liquidity_bucket", "usdm_symbol",
    "spot_open", "spot_high", "spot_low", "spot_close",
    "spot_volume", "spot_quote_volume", "rolling_median_quote_volume_usd_30d",
    "funding_rate", "basis_proxy", "open_interest", "open_interest_value",
    "intraday_realized_vol_4h_to_1d",
    "coinglass_top_trader_long_pct",
    "coinglass_taker_imbalance_5d_sum",
    "coinglass_taker_imb_intraday_dispersion_24h",
    "coinglass_top_trader_intraday_volatility_24h",
    "coinglass_orderbook_imb_persistence_24h",
    "coinglass_liquidation_imbalance_24h",
    "coinglass_liq_intraday_concentration_24h",
    "coinglass_global_account_long_pct",
)

# Hyperparameters (v1).
_F49_SLOPE = 4.0
_F49_FLOOR_AT = 0.175
_F26_RELATIVE_FULL_THROTTLE = 0.30
_F44_DISPERSION_FLOOR = 0.5
_F44_ROLLING_MEDIAN_WINDOW = 60
_MULTIPLIER_FLOOR = 0.3


def _load_panel(features_artifact: Path) -> pd.DataFrame:
    if not features_artifact.exists():
        raise FileNotFoundError(
            f"features artifact not found: {features_artifact}. "
            "Re-run the cross_sectional_daily_1d cycle to materialise it, "
            "or point the regime_gating builder at a different artifact."
        )
    df = pd.read_csv(features_artifact, compression="gzip")
    keep = [c for c in _PANEL_INPUT_COLUMNS if c in df.columns]
    return df[keep].copy()


def _rebuild_features_with_w3_columns(panel: pd.DataFrame) -> pd.DataFrame:
    """Rebuild the cross-sectional feature bundle so that F49/F26/F44 columns
    exist on the output (they may not be on the on-disk panel if the panel was
    written before W3.1/W3.2/W3.3 landed).
    """
    from .features import build_cross_sectional_feature_bundle

    bundle = build_cross_sectional_feature_bundle(panel, target_shift_bars=5)
    return bundle["dataframe"]


def _per_timestamp_universe_signal(
    features: pd.DataFrame, column: str
) -> pd.Series:
    """For a column that is constant within a timestamp (universe-wide), pull
    one value per timestamp_ms (sorted)."""
    if column not in features.columns:
        return pd.Series(dtype="float64")
    series = (
        pd.to_numeric(features[column], errors="coerce")
        .groupby(features["timestamp_ms"]).first()
        .sort_index()
    )
    return series


def _compute_alpha_ontology_regime_gating_v1(
    features_artifact: Path | None = None,
) -> dict[str, float]:
    """Compute the v1 regime gating overlay multiplier table.

    Returns a dict[date_str_utc -> multiplier]. The multiplier is in
    [_MULTIPLIER_FLOOR, 1.0]; lookups for dates absent from the table fall
    back to multiplier=1.0 (no throttle) by the consumer convention.
    """
    artifact = features_artifact or DEFAULT_FEATURES_ARTIFACT
    panel = _load_panel(artifact)
    features = _rebuild_features_with_w3_columns(panel)

    f49 = _per_timestamp_universe_signal(features, "shock_co_occurrence_index")
    f26 = _per_timestamp_universe_signal(features, "co_jump_count_3d")
    f44 = _per_timestamp_universe_signal(features, "dispersion_of_returns")
    if f49.empty or f26.empty or f44.empty:
        raise RuntimeError(
            "regime_gating builder requires features to contain "
            "shock_co_occurrence_index, co_jump_count_3d, and "
            "dispersion_of_returns columns (W3.1 / W3.2 / W3.3 features.py)."
        )

    n_subjects = features.groupby("timestamp_ms")["subject"].nunique().sort_index().reindex(f49.index).ffill()

    # Component multipliers
    m_f49 = (1.0 - _F49_SLOPE * f49).clip(lower=_MULTIPLIER_FLOOR, upper=1.0)
    f26_relative = (f26 / (n_subjects * _F26_RELATIVE_FULL_THROTTLE)).fillna(0.0)
    m_f26 = (1.0 - f26_relative).clip(lower=_MULTIPLIER_FLOOR, upper=1.0)

    f44_median = f44.rolling(_F44_ROLLING_MEDIAN_WINDOW, min_periods=10).median()
    # Avoid divide-by-zero: use a minimum positive median.
    f44_ratio = (f44 / f44_median.replace(0.0, np.nan)).clip(lower=_F44_DISPERSION_FLOOR, upper=1.0)
    m_f44 = f44_ratio.fillna(1.0)

    multiplier = (m_f49 * m_f26 * m_f44).clip(lower=_MULTIPLIER_FLOOR, upper=1.0)

    out: dict[str, float] = {}
    for ts_ms, value in multiplier.items():
        if pd.isna(value):
            continue
        date_str = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).date().isoformat()
        out[date_str] = float(value)
    return out


def regime_gating_overlay_summary(
    features_artifact: Path | None = None,
    *,
    builder: str = "v1",
) -> dict[str, Any]:
    """Diagnostic snapshot of an overlay multiplier distribution. `builder` in
    {"v1", "v2"}.
    """
    builder_fn = {
        "v1": _compute_alpha_ontology_regime_gating_v1,
        "v2": _compute_alpha_ontology_regime_gating_v2,
    }.get(builder)
    if builder_fn is None:
        raise ValueError(f"unknown builder {builder!r}; expected 'v1' or 'v2'")
    table = builder_fn(features_artifact)
    if not table:
        return {"available": False, "reason": "empty multiplier table"}
    values = pd.Series(list(table.values()))
    return {
        "available": True,
        "builder": builder,
        "contract_version": REGIME_GATING_CONTRACT_VERSION,
        "feature_artifact": str((features_artifact or DEFAULT_FEATURES_ARTIFACT)),
        "n_dates": int(values.shape[0]),
        "multiplier_min": float(values.min()),
        "multiplier_max": float(values.max()),
        "multiplier_mean": float(values.mean()),
        "multiplier_median": float(values.median()),
        "fraction_at_full": float((values >= 0.99).mean()),
        "fraction_at_floor": float((values <= _MULTIPLIER_FLOOR + 1e-6).mean()),
        "fraction_below_0_75": float((values < 0.75).mean()),
    }


# === v2 builder: adds F55 (BTC vol regime quantile) and trailing universe
# mean return as components, on top of v1's F49/F26/F44. v2 targets the
# slow-grind regimes (rotation_high_vol_2025q4, drawdown_rebound_2026ytd)
# that v1 missed because shock-based gauges don't fire on sustained
# low-return periods. See threshold_provenance.md "W3.5 v1" entry for the
# diagnosis of v1's worst-regime regression. ===

# v2 hyperparameters (calibrated so v2 ~ v1 on calm days but adds throttle
# on sustained-vol / slow-grind regimes that v1's shock-based gauges miss).
# Initial unsoftened picks (F55 thresh 0.5, full 1.0, K=8, no component
# floor) gave a degenerate distribution: 50.5% of days at overall floor
# 0.30, median at 0.30. Softened to keep median in calm range while still
# firing on top-quantile vol regimes.
_F55_BTC_VOL_LOOKBACK = 60          # BTC realized_volatility_20 percentile lookback bars
_F55_THROTTLE_QUANTILE = 0.7        # below this: no throttle (top 30% only)
_F55_FULL_THROTTLE_QUANTILE = 1.5   # span 0.8 -> partial throttle even at q=1
_TRAILING_RETURN_WINDOW = 30        # bars
_TRAILING_RETURN_THROTTLE_K = 3.0   # multiplier slope vs trailing return
_V2_EXTRAS_COMPONENT_FLOOR = 0.5    # per-component floor for m_f55 / m_trailing
                                     # (so the two v2 extras alone cannot drive
                                     # the product below 0.5*0.5=0.25, which
                                     # would clip to overall floor 0.3)


def _rolling_current_rank_pct(series: pd.Series, *, lookback: int, min_periods: int) -> pd.Series:
    def _rank_latest(values: np.ndarray) -> float:
        current = float(values[-1]) if len(values) else np.nan
        if np.isnan(current):
            return np.nan
        clean = values[~np.isnan(values)]
        if len(clean) < min_periods:
            return np.nan
        less_count = int(np.sum(clean < current))
        equal_count = int(np.sum(clean == current))
        average_rank = less_count + ((equal_count + 1) / 2.0)
        return float(average_rank / len(clean))

    return series.rolling(lookback, min_periods=min_periods).apply(_rank_latest, raw=True)


def _compute_btc_vol_regime_quantile(
    features: pd.DataFrame, *, anchor_subject: str = "BTC", lookback: int = _F55_BTC_VOL_LOOKBACK
) -> pd.Series:
    """F55 BTC vol regime quantile: rank BTC's realized_volatility_20 within a
    trailing window. Returns Series indexed by timestamp_ms with values in [0, 1].
    """
    btc = features[features["subject"] == anchor_subject]
    if btc.empty or "realized_volatility_20" not in btc.columns:
        return pd.Series(dtype="float64")
    rv = (
        pd.to_numeric(btc.set_index("timestamp_ms")["realized_volatility_20"], errors="coerce")
        .replace(0.0, np.nan)
        .sort_index()
    )
    return _rolling_current_rank_pct(rv, lookback=lookback, min_periods=20)


def _compute_trailing_universe_mean_return(
    features: pd.DataFrame, *, window: int = _TRAILING_RETURN_WINDOW
) -> pd.Series:
    """Per-timestamp mean of return_1 across universe, smoothed over `window`
    bars. Captures slow-grind bear regimes (sustained negative cross-asset mean).
    """
    ret = pd.to_numeric(features["return_1"], errors="coerce")
    universe_mean_per_ts = ret.groupby(features["timestamp_ms"]).mean().sort_index()
    return universe_mean_per_ts.rolling(window, min_periods=10).mean()


def _compute_alpha_ontology_regime_gating_v2(
    features_artifact: Path | None = None,
) -> dict[str, float]:
    """v2 regime gating: v1 components (F49 + F26 + F44) plus F55 (BTC vol
    regime quantile) and trailing-30-bar universe mean return. Targets
    slow-grind worst-regime drawdowns that v1 missed.
    """
    artifact = features_artifact or DEFAULT_FEATURES_ARTIFACT
    panel = _load_panel(artifact)
    features = _rebuild_features_with_w3_columns(panel)

    # v1 components
    f49 = _per_timestamp_universe_signal(features, "shock_co_occurrence_index")
    f26 = _per_timestamp_universe_signal(features, "co_jump_count_3d")
    f44 = _per_timestamp_universe_signal(features, "dispersion_of_returns")
    if f49.empty or f26.empty or f44.empty:
        raise RuntimeError(
            "regime_gating v2 requires F49 + F26 + F44 columns from W3.x features.py"
        )
    n_subjects = (
        features.groupby("timestamp_ms")["subject"].nunique().sort_index().reindex(f49.index).ffill()
    )
    m_f49 = (1.0 - _F49_SLOPE * f49).clip(lower=_MULTIPLIER_FLOOR, upper=1.0)
    f26_relative = (f26 / (n_subjects * _F26_RELATIVE_FULL_THROTTLE)).fillna(0.0)
    m_f26 = (1.0 - f26_relative).clip(lower=_MULTIPLIER_FLOOR, upper=1.0)
    f44_median = f44.rolling(_F44_ROLLING_MEDIAN_WINDOW, min_periods=10).median()
    m_f44 = (f44 / f44_median.replace(0.0, np.nan)).clip(
        lower=_F44_DISPERSION_FLOOR, upper=1.0
    ).fillna(1.0)

    # v2 additions — both clipped to a higher per-component floor so the
    # product of the two extras alone can't drive M_v2 to overall floor on
    # calm-by-v1 days. Composes multiplicatively with v1.
    f55 = _compute_btc_vol_regime_quantile(features).reindex(f49.index)
    excess_q = (f55 - _F55_THROTTLE_QUANTILE).clip(lower=0.0)
    span_q = max(_F55_FULL_THROTTLE_QUANTILE - _F55_THROTTLE_QUANTILE, 1e-6)
    m_f55 = (1.0 - excess_q / span_q).clip(
        lower=_V2_EXTRAS_COMPONENT_FLOOR, upper=1.0
    ).fillna(1.0)

    trailing_ret = _compute_trailing_universe_mean_return(features).reindex(f49.index)
    cum_signal = trailing_ret * _TRAILING_RETURN_WINDOW
    m_trailing = (1.0 + _TRAILING_RETURN_THROTTLE_K * cum_signal).clip(
        lower=_V2_EXTRAS_COMPONENT_FLOOR, upper=1.0
    ).fillna(1.0)

    multiplier = (m_f49 * m_f26 * m_f44 * m_f55 * m_trailing).clip(
        lower=_MULTIPLIER_FLOOR, upper=1.0
    )

    out: dict[str, float] = {}
    for ts_ms, value in multiplier.items():
        if pd.isna(value):
            continue
        date_str = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).date().isoformat()
        out[date_str] = float(value)
    return out


# === v3 builder: SP-G DVOL extensions on top of v2.
# Adds vol-of-vol throttling using Deribit DVOL daily OHLC (BTC + ETH).
# When the intraday DVOL range (high-low)/close is in its top quantile
# (rolling 90d), throttle harder. SP-E (BTC-ETH realized correlation
# regime gate) was DROPPED — empirically falsified per
# threshold_provenance.md SP-E section: tertile-stratified IC ratio
# REVERSED vs doc §E.17 prediction (high-corr regime has HIGHER IC, not
# lower). SP-G is the only surviving v3 enrichment. ===

# DVOL CSV paths (deribit_dvol sync, gitignored data).
_BTC_DVOL_PATH = (
    ROOT / "artifacts" / "external_market_data" / "deribit_dvol" / "btc_dvol_daily.csv"
)
_ETH_DVOL_PATH = (
    ROOT / "artifacts" / "external_market_data" / "deribit_dvol" / "eth_dvol_daily.csv"
)

# v3 hyperparameters (calibrated so v3 ~ v2 on calm DVOL days but
# adds throttle on top-decile vol-of-vol days that v2 doesn't see).
_V3_DVOL_RANGE_Z_WINDOW = 90       # rolling-90d window for DVOL range z-score
_V3_DVOL_RANGE_Z_THRESHOLD = 1.5   # below this: no DVOL throttle
_V3_DVOL_RANGE_Z_FULL = 2.5        # at/above this: full DVOL throttle (component floor)
_V3_DVOL_COMPONENT_FLOOR = 0.7     # per-component floor for m_btc_dvol / m_eth_dvol


def _load_dvol_with_range_z(path: Path) -> pd.DataFrame | None:
    """Load Deribit DVOL daily CSV and compute rolling-90d z-score of
    intraday range (high-low)/close. Returns DataFrame indexed by date_utc
    with columns [dvol_close, dvol_intraday_range, dvol_range_z90].
    Returns None if file missing.
    """
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if not {"date_utc", "dvol_close", "dvol_high", "dvol_low"}.issubset(df.columns):
        return None
    df = df.sort_values("date_utc").reset_index(drop=True)
    df["dvol_intraday_range"] = (df["dvol_high"] - df["dvol_low"]) / df["dvol_close"].replace(0.0, np.nan)
    rolling_mean = df["dvol_intraday_range"].rolling(_V3_DVOL_RANGE_Z_WINDOW, min_periods=20).mean()
    rolling_std = df["dvol_intraday_range"].rolling(_V3_DVOL_RANGE_Z_WINDOW, min_periods=20).std()
    df["dvol_range_z90"] = (df["dvol_intraday_range"] - rolling_mean) / rolling_std.replace(0.0, np.nan)
    return df.set_index("date_utc")[["dvol_close", "dvol_intraday_range", "dvol_range_z90"]]


def _dvol_range_throttle_multiplier(z90: pd.Series) -> pd.Series:
    """For a date-indexed Series of DVOL range z90, compute the throttle
    multiplier in [_V3_DVOL_COMPONENT_FLOOR, 1.0]:
      z <= threshold       -> 1.0  (no throttle)
      threshold < z < full -> linear ramp to floor
      z >= full            -> floor (full throttle)
    NaN inputs -> 1.0 (no throttle, fail-open).
    """
    excess = (z90 - _V3_DVOL_RANGE_Z_THRESHOLD).clip(lower=0.0)
    span = max(_V3_DVOL_RANGE_Z_FULL - _V3_DVOL_RANGE_Z_THRESHOLD, 1e-6)
    multiplier = (1.0 - excess / span).clip(lower=_V3_DVOL_COMPONENT_FLOOR, upper=1.0)
    return multiplier.fillna(1.0)


def _compute_alpha_ontology_regime_gating_v3(
    features_artifact: Path | None = None,
) -> dict[str, float]:
    """v3 regime gating: v2 components × DVOL-range-z-90 throttle (BTC + ETH).

    SP-G G2 component: when btc_dvol_range_z90 or eth_dvol_range_z90 enters
    the vol-of-vol regime (z > 1.5), throttle harder. The two DVOL
    components compose multiplicatively with v2's existing 5 components.

    SP-E (correlation regime gate per doc §E.17) was DROPPED from v3 after
    tertile-stratified IC analysis showed the regime relationship is the
    OPPOSITE of doc prediction. See threshold_provenance.md SP-E section.
    """
    artifact = features_artifact or DEFAULT_FEATURES_ARTIFACT
    panel = _load_panel(artifact)
    features = _rebuild_features_with_w3_columns(panel)

    # === v1 components ===
    f49 = _per_timestamp_universe_signal(features, "shock_co_occurrence_index")
    f26 = _per_timestamp_universe_signal(features, "co_jump_count_3d")
    f44 = _per_timestamp_universe_signal(features, "dispersion_of_returns")
    if f49.empty or f26.empty or f44.empty:
        raise RuntimeError(
            "regime_gating v3 requires F49 + F26 + F44 columns from W3.x features.py"
        )
    n_subjects = (
        features.groupby("timestamp_ms")["subject"].nunique().sort_index().reindex(f49.index).ffill()
    )
    m_f49 = (1.0 - _F49_SLOPE * f49).clip(lower=_MULTIPLIER_FLOOR, upper=1.0)
    f26_relative = (f26 / (n_subjects * _F26_RELATIVE_FULL_THROTTLE)).fillna(0.0)
    m_f26 = (1.0 - f26_relative).clip(lower=_MULTIPLIER_FLOOR, upper=1.0)
    f44_median = f44.rolling(_F44_ROLLING_MEDIAN_WINDOW, min_periods=10).median()
    m_f44 = (f44 / f44_median.replace(0.0, np.nan)).clip(
        lower=_F44_DISPERSION_FLOOR, upper=1.0
    ).fillna(1.0)

    # === v2 additions ===
    f55 = _compute_btc_vol_regime_quantile(features).reindex(f49.index)
    excess_q = (f55 - _F55_THROTTLE_QUANTILE).clip(lower=0.0)
    span_q = max(_F55_FULL_THROTTLE_QUANTILE - _F55_THROTTLE_QUANTILE, 1e-6)
    m_f55 = (1.0 - excess_q / span_q).clip(
        lower=_V2_EXTRAS_COMPONENT_FLOOR, upper=1.0
    ).fillna(1.0)

    trailing_ret = _compute_trailing_universe_mean_return(features).reindex(f49.index)
    cum_signal = trailing_ret * _TRAILING_RETURN_WINDOW
    m_trailing = (1.0 + _TRAILING_RETURN_THROTTLE_K * cum_signal).clip(
        lower=_V2_EXTRAS_COMPONENT_FLOOR, upper=1.0
    ).fillna(1.0)

    # === v3 SP-G additions: DVOL range z90 throttle (BTC + ETH) ===
    btc_dvol = _load_dvol_with_range_z(_BTC_DVOL_PATH)
    eth_dvol = _load_dvol_with_range_z(_ETH_DVOL_PATH)

    # Build a date_utc-indexed throttle multiplier for both currencies.
    # If a DVOL CSV is missing on disk, fail-open (multiplier=1.0).
    if btc_dvol is not None:
        m_btc_dvol_by_date = _dvol_range_throttle_multiplier(btc_dvol["dvol_range_z90"])
    else:
        m_btc_dvol_by_date = pd.Series(dtype="float64")
    if eth_dvol is not None:
        m_eth_dvol_by_date = _dvol_range_throttle_multiplier(eth_dvol["dvol_range_z90"])
    else:
        m_eth_dvol_by_date = pd.Series(dtype="float64")

    # Map per-timestamp_ms -> date_utc, then look up DVOL throttle.
    ts_to_date = pd.Series(f49.index, index=f49.index).map(
        lambda ms: datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    )
    if not m_btc_dvol_by_date.empty:
        m_btc_dvol = ts_to_date.map(m_btc_dvol_by_date.to_dict()).fillna(1.0)
    else:
        m_btc_dvol = pd.Series(1.0, index=f49.index)
    if not m_eth_dvol_by_date.empty:
        m_eth_dvol = ts_to_date.map(m_eth_dvol_by_date.to_dict()).fillna(1.0)
    else:
        m_eth_dvol = pd.Series(1.0, index=f49.index)

    multiplier = (
        m_f49 * m_f26 * m_f44 * m_f55 * m_trailing * m_btc_dvol * m_eth_dvol
    ).clip(lower=_MULTIPLIER_FLOOR, upper=1.0)

    out: dict[str, float] = {}
    for ts_ms, value in multiplier.items():
        if pd.isna(value):
            continue
        date_str = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc).date().isoformat()
        out[date_str] = float(value)
    return out


def regime_gating_component_frame(
    features_artifact: Path | None = None,
    *,
    include_v3: bool = True,
) -> pd.DataFrame:
    """Return per-date regime-gating gauges and component multipliers.

    This diagnostics surface uses the same formulas as the registered
    v1/v2/v3 overlay builders, while keeping each component separate.
    """
    artifact = features_artifact or DEFAULT_FEATURES_ARTIFACT
    panel = _load_panel(artifact)
    features = _rebuild_features_with_w3_columns(panel)

    f49 = _per_timestamp_universe_signal(features, "shock_co_occurrence_index")
    f26 = _per_timestamp_universe_signal(features, "co_jump_count_3d")
    f44 = _per_timestamp_universe_signal(features, "dispersion_of_returns")
    if f49.empty or f26.empty or f44.empty:
        raise RuntimeError(
            "regime_gating component diagnostics require F49 + F26 + F44 columns"
        )
    n_subjects = (
        features.groupby("timestamp_ms")["subject"].nunique().sort_index().reindex(f49.index).ffill()
    )

    m_f49 = (1.0 - _F49_SLOPE * f49).clip(lower=_MULTIPLIER_FLOOR, upper=1.0)
    f26_relative = (f26 / (n_subjects * _F26_RELATIVE_FULL_THROTTLE)).fillna(0.0)
    m_f26 = (1.0 - f26_relative).clip(lower=_MULTIPLIER_FLOOR, upper=1.0)
    f44_median = f44.rolling(_F44_ROLLING_MEDIAN_WINDOW, min_periods=10).median()
    m_f44 = (f44 / f44_median.replace(0.0, np.nan)).clip(
        lower=_F44_DISPERSION_FLOOR, upper=1.0
    ).fillna(1.0)

    f55 = _compute_btc_vol_regime_quantile(features).reindex(f49.index)
    excess_q = (f55 - _F55_THROTTLE_QUANTILE).clip(lower=0.0)
    span_q = max(_F55_FULL_THROTTLE_QUANTILE - _F55_THROTTLE_QUANTILE, 1e-6)
    m_f55 = (1.0 - excess_q / span_q).clip(
        lower=_V2_EXTRAS_COMPONENT_FLOOR, upper=1.0
    ).fillna(1.0)

    trailing_ret = _compute_trailing_universe_mean_return(features).reindex(f49.index)
    cum_signal = trailing_ret * _TRAILING_RETURN_WINDOW
    m_trailing = (1.0 + _TRAILING_RETURN_THROTTLE_K * cum_signal).clip(
        lower=_V2_EXTRAS_COMPONENT_FLOOR, upper=1.0
    ).fillna(1.0)

    ts_to_date = pd.Series(f49.index, index=f49.index).map(
        lambda ms: datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()
    )
    m_btc_dvol = pd.Series(1.0, index=f49.index)
    m_eth_dvol = pd.Series(1.0, index=f49.index)
    btc_dvol_z90 = pd.Series(np.nan, index=f49.index)
    eth_dvol_z90 = pd.Series(np.nan, index=f49.index)
    if include_v3:
        btc_dvol = _load_dvol_with_range_z(_BTC_DVOL_PATH)
        eth_dvol = _load_dvol_with_range_z(_ETH_DVOL_PATH)
        if btc_dvol is not None:
            btc_dvol_z90 = ts_to_date.map(btc_dvol["dvol_range_z90"].to_dict())
            m_btc_dvol = ts_to_date.map(
                _dvol_range_throttle_multiplier(btc_dvol["dvol_range_z90"]).to_dict()
            ).fillna(1.0)
        if eth_dvol is not None:
            eth_dvol_z90 = ts_to_date.map(eth_dvol["dvol_range_z90"].to_dict())
            m_eth_dvol = ts_to_date.map(
                _dvol_range_throttle_multiplier(eth_dvol["dvol_range_z90"]).to_dict()
            ).fillna(1.0)

    multiplier_v1 = (m_f49 * m_f26 * m_f44).clip(lower=_MULTIPLIER_FLOOR, upper=1.0)
    multiplier_v2 = (multiplier_v1 * m_f55 * m_trailing).clip(
        lower=_MULTIPLIER_FLOOR, upper=1.0
    )
    multiplier_v3 = (multiplier_v2 * m_btc_dvol * m_eth_dvol).clip(
        lower=_MULTIPLIER_FLOOR, upper=1.0
    )

    out = pd.DataFrame(
        {
            "timestamp_ms": f49.index.astype("int64"),
            "date_utc": ts_to_date.values,
            "n_subjects": n_subjects.values,
            "f49_shock_co_occurrence_index": f49.values,
            "f26_co_jump_count_3d": f26.values,
            "f26_relative_cluster_intensity": f26_relative.values,
            "f44_dispersion_of_returns": f44.values,
            "f44_rolling_median_60d": f44_median.values,
            "f55_btc_vol_regime_quantile": f55.values,
            "trailing_universe_mean_return_30d": trailing_ret.values,
            "btc_dvol_range_z90": btc_dvol_z90.values,
            "eth_dvol_range_z90": eth_dvol_z90.values,
            "m_shock_fraction_f49": m_f49.values,
            "m_shock_cluster_f26": m_f26.values,
            "m_low_dispersion_f44": m_f44.values,
            "m_btc_vol_regime_f55": m_f55.values,
            "m_trailing_universe_return": m_trailing.values,
            "m_btc_dvol_range": m_btc_dvol.values,
            "m_eth_dvol_range": m_eth_dvol.values,
            "multiplier_v1": multiplier_v1.values,
            "multiplier_v2": multiplier_v2.values,
            "multiplier_v3": multiplier_v3.values,
        }
    )
    return out.sort_values("timestamp_ms").reset_index(drop=True)


# === SP-J: Production-realistic 3-state regime classifier (per-timestamp).
# Used by xs_alpha_ontology_v10_regime_conditional_h10d_score to apply
# regime-conditional weights. Computed entirely from trailing data — no
# lookahead. Outputs string label per timestamp_ms.
#
# 3-state taxonomy (matches existing regime_holdout calendar in spirit):
#   trend_up                 — universe in positive trailing return regime
#   rotation_high_vol        — universe negative trailing return AND elevated BTC vol
#   drawdown_rebound         — universe was recently negative (60d) but recovering (30d > 60d)
#
# Sources: leverages W3.5 v2 components (trailing_universe_mean_return +
# btc_vol_regime_quantile) which are already proven production-realistic.
# ===

REGIME_CLASSIFIER_V10_CONTRACT_VERSION = "quant_regime_classifier_v10.v1"

# v10 thresholds (production-realistic; tunable)
_V10_TRAILING_RETURN_NEGATIVE_THRESHOLD = -0.005   # below: candidate rotation/drawdown
_V10_BTC_VOL_QUANTILE_HIGH_THRESHOLD = 0.50         # at/above: high-vol regime
_V10_TRAILING_30D_WINDOW = 30
_V10_TRAILING_60D_WINDOW = 60


def classify_regime_v10(features: pd.DataFrame) -> pd.Series:
    """3-state regime classifier from trailing data only (no lookahead).

    Returns Series indexed by timestamp_ms with values in
    {trend_up, rotation_high_vol, drawdown_rebound}.

    Logic:
      - rotation_high_vol: trailing_30d_universe_return < -0.005 AND
        btc_vol_regime_quantile_60d >= 0.50 (negative + high vol)
      - drawdown_rebound: trailing_30d >= -0.005 AND trailing_60d < 0
        (recently negative cumulative but currently recovering)
      - trend_up: else (default — positive trailing or stable)

    Insufficient-data rows default to "trend_up" (fail-open to baseline behavior).
    """
    if "return_1" not in features.columns or "realized_volatility_20" not in features.columns:
        ts_unique = sorted(features["timestamp_ms"].unique())
        return pd.Series("trend_up", index=ts_unique, dtype="object")

    # Trailing universe mean return
    ret = pd.to_numeric(features["return_1"], errors="coerce")
    universe_mean = ret.groupby(features["timestamp_ms"]).mean().sort_index()
    trailing_30d = universe_mean.rolling(_V10_TRAILING_30D_WINDOW, min_periods=10).mean()
    trailing_60d = universe_mean.rolling(_V10_TRAILING_60D_WINDOW, min_periods=20).mean()

    # BTC vol regime quantile (matches F55)
    btc = features[features["subject"] == "BTC"]
    if btc.empty:
        ts_unique = sorted(features["timestamp_ms"].unique())
        return pd.Series("trend_up", index=ts_unique, dtype="object")
    btc_rv = (
        pd.to_numeric(btc.set_index("timestamp_ms")["realized_volatility_20"], errors="coerce")
        .replace(0.0, np.nan)
        .sort_index()
    )
    btc_vol_q = _rolling_current_rank_pct(
        btc_rv,
        lookback=_F55_BTC_VOL_LOOKBACK,
        min_periods=20,
    )

    # Align all on common index
    common = sorted(
        set(trailing_30d.dropna().index)
        & set(trailing_60d.dropna().index)
        & set(btc_vol_q.dropna().index)
    )
    if not common:
        ts_unique = sorted(features["timestamp_ms"].unique())
        return pd.Series("trend_up", index=ts_unique, dtype="object")

    trailing_30d = trailing_30d.reindex(common)
    trailing_60d = trailing_60d.reindex(common)
    btc_vol_q = btc_vol_q.reindex(common)

    # 3-state labeling
    labels = pd.Series("trend_up", index=common, dtype="object")
    rotation_mask = (
        (trailing_30d < _V10_TRAILING_RETURN_NEGATIVE_THRESHOLD)
        & (btc_vol_q >= _V10_BTC_VOL_QUANTILE_HIGH_THRESHOLD)
    )
    drawdown_mask = (
        (trailing_30d >= _V10_TRAILING_RETURN_NEGATIVE_THRESHOLD)
        & (trailing_60d < 0)
    )
    labels[rotation_mask.fillna(False)] = "rotation_high_vol"
    labels[drawdown_mask.fillna(False)] = "drawdown_rebound"

    # Reindex to ALL unique timestamps (fail-open to "trend_up" for early-panel insufficient-data rows)
    ts_unique = sorted(features["timestamp_ms"].unique())
    full_labels = pd.Series("trend_up", index=ts_unique, dtype="object")
    full_labels.update(labels)
    return full_labels


def regime_classifier_v10_summary(features_artifact: Path | None = None) -> dict:
    """Diagnostic summary of regime distribution under v10 classifier."""
    artifact = features_artifact or DEFAULT_FEATURES_ARTIFACT
    panel = _load_panel(artifact)
    features = _rebuild_features_with_w3_columns(panel)
    labels = classify_regime_v10(features)
    counts = labels.value_counts()
    fractions = labels.value_counts(normalize=True)
    return {
        "contract_version": REGIME_CLASSIFIER_V10_CONTRACT_VERSION,
        "n_total_timestamps": int(len(labels)),
        "regime_counts": {str(k): int(v) for k, v in counts.items()},
        "regime_fractions": {str(k): float(v) for k, v in fractions.items()},
        "thresholds": {
            "trailing_return_negative": _V10_TRAILING_RETURN_NEGATIVE_THRESHOLD,
            "btc_vol_quantile_high": _V10_BTC_VOL_QUANTILE_HIGH_THRESHOLD,
            "trailing_30d_window": _V10_TRAILING_30D_WINDOW,
            "trailing_60d_window": _V10_TRAILING_60D_WINDOW,
        },
    }


__all__ = [
    "REGIME_GATING_CONTRACT_VERSION",
    "REGIME_CLASSIFIER_V10_CONTRACT_VERSION",
    "DEFAULT_FEATURES_ARTIFACT",
    "_compute_alpha_ontology_regime_gating_v1",
    "_compute_alpha_ontology_regime_gating_v2",
    "_compute_alpha_ontology_regime_gating_v3",
    "regime_gating_component_frame",
    "regime_gating_overlay_summary",
    "classify_regime_v10",
    "regime_classifier_v10_summary",
]
