"""triangle_residual — M2.4 Funding-OI-Basis triangle constraint residual.

Per alpha ontology doc §H.3 M2.4 + §E.11: in the no-arbitrage limit
`funding ≈ basis × (1/horizon) - convenience_yield`. The triangle of
funding / basis / OI is closed-form; the residual after fitting
funding to basis AND OI-change jointly captures positioning pressure
that single-variable z-scores miss.

Doc E.11 falsification: constraint residual IR must exceed 70% of the
sum of (single funding_z IR + single basis_z IR), otherwise the joint
fit adds no incremental information beyond the separate z-scores.

Mechanism distinction vs F09.
  F09 (existing) = funding - α * basis (1-variable rolling OLS residual).
  M2.4 F-triangle = funding - α - β1 * basis - β2 * oi_change_5
    (2-regressor rolling OLS residual). The `oi_change_5` regressor adds
    the "OI growth conditional on basis" leg of the doc's 3-equation
    system. The intercept α absorbs the time-varying convenience_yield.

Sign hypothesis (doc-aligned):
  Positive triangle_residual = funding higher than basis-implied
  conditional on OI growth = longs are paying premium beyond no-arb
  → over-crowded long → forward NEGATIVE (mean revert).

Implementation.
  Rolling-60d per-subject 3-variable OLS:
    y = funding_rate
    X = [intercept, basis_proxy, oi_change_5]
  At each row t in subject's series, fit OLS on rows [t-59, t] (60-bar
  trailing window), compute predicted y_hat[t], output residual y[t] - y_hat[t].

  Implementation choice: closed-form rolling OLS via batched matrix ops.
  Avoids Python-loop overhead by computing rolling sums of cross-products
  and inverting 3x3 normal equations.

Output.
  Function: compute_triangle_residual_panel(panel, *, window=60) -> long
  format DataFrame with columns: subject, timestamp_ms, date_utc,
  triangle_residual_60d, triangle_r2_60d.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

TRIANGLE_RESIDUAL_CONTRACT_VERSION = "quant_triangle_residual.v1"
DEFAULT_WINDOW = 60
MIN_OBS_FOR_FIT = 30


def _rolling_ols_residual_3var(
    y: pd.Series,
    x1: pd.Series,
    x2: pd.Series,
    *,
    window: int = DEFAULT_WINDOW,
    min_periods: int = MIN_OBS_FOR_FIT,
) -> tuple[pd.Series, pd.Series]:
    """Rolling-window 2-regressor OLS residual (intercept + 2 slopes).

    For each row t, fit y = α + β1*x1 + β2*x2 on rows [t-window+1, t].
    Returns (residual_series, r2_series). Both Series share y's index.
    """
    df = pd.concat([y.rename("y"), x1.rename("x1"), x2.rename("x2")], axis=1)
    df = df.replace([np.inf, -np.inf], np.nan)

    valid = df.notna().all(axis=1)
    df["valid"] = valid.astype(float)
    df_filled = df[["y", "x1", "x2"]].where(valid, 0.0)

    # Rolling sums of all needed cross-products (only over valid rows)
    n_valid = valid.astype(int).rolling(window, min_periods=min_periods).sum()
    s_y = df_filled["y"].rolling(window, min_periods=min_periods).sum()
    s_x1 = df_filled["x1"].rolling(window, min_periods=min_periods).sum()
    s_x2 = df_filled["x2"].rolling(window, min_periods=min_periods).sum()
    s_yy = (df_filled["y"] ** 2).rolling(window, min_periods=min_periods).sum()
    s_x1x1 = (df_filled["x1"] ** 2).rolling(window, min_periods=min_periods).sum()
    s_x2x2 = (df_filled["x2"] ** 2).rolling(window, min_periods=min_periods).sum()
    s_x1x2 = (df_filled["x1"] * df_filled["x2"]).rolling(window, min_periods=min_periods).sum()
    s_yx1 = (df_filled["y"] * df_filled["x1"]).rolling(window, min_periods=min_periods).sum()
    s_yx2 = (df_filled["y"] * df_filled["x2"]).rolling(window, min_periods=min_periods).sum()

    # Closed-form 3x3 normal equation solve per row.
    n = n_valid.astype(float)
    n_safe = n.where(n >= min_periods, np.nan)

    # Mean-center via pooled centered moments
    mean_y = s_y / n_safe
    mean_x1 = s_x1 / n_safe
    mean_x2 = s_x2 / n_safe

    cov_x1x1 = s_x1x1 / n_safe - mean_x1 ** 2
    cov_x2x2 = s_x2x2 / n_safe - mean_x2 ** 2
    cov_x1x2 = s_x1x2 / n_safe - mean_x1 * mean_x2
    cov_yx1 = s_yx1 / n_safe - mean_y * mean_x1
    cov_yx2 = s_yx2 / n_safe - mean_y * mean_x2
    var_y = s_yy / n_safe - mean_y ** 2

    # Solve [[a c],[c b]] [β1, β2]^T = [d, e]^T  via Cramer
    a = cov_x1x1
    b = cov_x2x2
    c = cov_x1x2
    d = cov_yx1
    e = cov_yx2
    det = a * b - c * c
    det_safe = det.where(det.abs() > 1e-18, np.nan)
    beta1 = (d * b - e * c) / det_safe
    beta2 = (a * e - c * d) / det_safe
    alpha = mean_y - beta1 * mean_x1 - beta2 * mean_x2

    # Residual at row t (using trailing-window-fit coefficients)
    y_pred = alpha + beta1 * df["x1"] + beta2 * df["x2"]
    residual = df["y"] - y_pred

    # R^2 from explained-variance ratio
    var_explained = (beta1 ** 2 * cov_x1x1 + beta2 ** 2 * cov_x2x2 + 2 * beta1 * beta2 * cov_x1x2)
    r2 = (var_explained / var_y.replace(0.0, np.nan)).clip(lower=-1.0, upper=1.0)

    return residual, r2


def compute_triangle_residual_per_subject(
    frame: pd.DataFrame,
    *,
    y_column: str = "funding_rate",
    x1_column: str = "basis_proxy",
    x2_column: str = "oi_change_5",
    window: int = DEFAULT_WINDOW,
) -> pd.DataFrame:
    """For one subject's per-day frame (sorted by timestamp_ms), compute
    triangle_residual_<window>d via rolling 2-regressor OLS.

    Returns the input frame with two new columns:
      triangle_residual_<window>d
      triangle_r2_<window>d
    """
    out = frame.copy()
    if y_column not in out.columns or x1_column not in out.columns or x2_column not in out.columns:
        out[f"triangle_residual_{window}d"] = 0.0
        out[f"triangle_r2_{window}d"] = 0.0
        return out
    y = pd.to_numeric(out[y_column], errors="coerce")
    x1 = pd.to_numeric(out[x1_column], errors="coerce")
    x2 = pd.to_numeric(out[x2_column], errors="coerce")
    residual, r2 = _rolling_ols_residual_3var(y, x1, x2, window=window)
    out[f"triangle_residual_{window}d"] = residual
    out[f"triangle_r2_{window}d"] = r2
    return out


def add_triangle_residual_to_panel(
    features: pd.DataFrame,
    *,
    window: int = DEFAULT_WINDOW,
    subject_column: str = "subject",
    timestamp_column: str = "timestamp_ms",
) -> pd.DataFrame:
    """Add triangle_residual_<window>d + triangle_r2_<window>d columns to a
    cross-sectional panel, computed per-subject in time order.

    Mutates a copy; returns the new frame.
    """
    if subject_column not in features.columns or timestamp_column not in features.columns:
        return features
    out = features.copy()
    res_col = f"triangle_residual_{window}d"
    r2_col = f"triangle_r2_{window}d"
    out[res_col] = np.nan
    out[r2_col] = np.nan
    for sub, group in out.groupby(subject_column, sort=False):
        ordered = group.sort_values(timestamp_column)
        idx = ordered.index
        y = pd.to_numeric(ordered.get("funding_rate"), errors="coerce")
        x1 = pd.to_numeric(ordered.get("basis_proxy"), errors="coerce")
        x2 = pd.to_numeric(ordered.get("oi_change_5"), errors="coerce")
        if y is None or x1 is None or x2 is None:
            continue
        residual, r2 = _rolling_ols_residual_3var(y, x1, x2, window=window)
        out.loc[idx, res_col] = residual.values
        out.loc[idx, r2_col] = r2.values
    return out


__all__ = [
    "TRIANGLE_RESIDUAL_CONTRACT_VERSION",
    "compute_triangle_residual_per_subject",
    "add_triangle_residual_to_panel",
]
