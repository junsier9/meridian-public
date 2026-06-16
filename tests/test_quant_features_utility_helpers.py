from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from enhengclaw.quant_research.features import (
    _safe_rolling_skew,
    _timestamp_percentile_rank,
    _timestamp_zscore,
)


def test_safe_rolling_skew_preserves_index_and_min_period_shape() -> None:
    series = pd.Series([1.0, 2.0, 3.0, 4.0], index=list("abcd"))

    result = _safe_rolling_skew(series, 3, min_periods=3)

    assert list(result.index) == list(series.index)
    assert np.isnan(result.loc["a"])
    assert np.isnan(result.loc["b"])
    assert result.loc["c"] == pytest.approx(0.0)
    assert result.loc["d"] == pytest.approx(0.0)


def test_timestamp_percentile_rank_is_grouped_by_timestamp_only() -> None:
    values = pd.Series([10.0, 20.0, 30.0, 5.0, 5.0], index=list("abcde"))
    timestamps = pd.Series([1, 1, 1, 2, 2], index=values.index)

    result = _timestamp_percentile_rank(values, timestamps)

    assert list(result.index) == list(values.index)
    assert result.tolist() == pytest.approx([1 / 3, 2 / 3, 1.0, 0.75, 0.75])


def test_timestamp_zscore_is_grouped_and_zeroes_constant_groups() -> None:
    values = pd.Series([1.0, 2.0, 3.0, 5.0, 5.0], index=list("abcde"))
    timestamps = pd.Series([1, 1, 1, 2, 2], index=values.index)

    result = _timestamp_zscore(values, timestamps)

    assert list(result.index) == list(values.index)
    assert str(result.dtype) == "float64"
    assert result.tolist() == pytest.approx([-1.0, 0.0, 1.0, 0.0, 0.0])
