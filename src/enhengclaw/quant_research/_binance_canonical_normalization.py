from __future__ import annotations

import numpy as np
import pandas as pd


def _timestamp_zscore(series: pd.Series, timestamps: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    mean = numeric.groupby(timestamps).transform("mean")
    std = numeric.groupby(timestamps).transform(lambda item: item.std(ddof=0))
    z = (numeric - mean) / std.replace(0.0, np.nan)
    return z.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype("float64")


def _timestamp_percentile_rank(series: pd.Series, timestamps: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return numeric.groupby(timestamps).rank(pct=True, method="average").fillna(0.5).astype("float64")
