from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from scripts.market_data.binance_ohlcv import load_interval_rows, resolve_external_history_root


ROOT = Path(__file__).resolve().parents[3]
OPTIONS_SURFACE_FEATURE_PANEL_CONTRACT_VERSION = (
    "quant_m3_1_tardis_deribit_options_surface_features.v1"
)
DEFAULT_OUT_PATH = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "options_surface"
    / "tardis_deribit_options_surface_features.csv"
)
FACTOR_COLUMNS = [
    "iv_25d_skew_residual",
    "iv_rv_spread",
    "iv_term_slope",
    "dealer_gamma_proxy",
    "vanna_charm_window",
]
READY_COLUMNS = ["f56_ready", "f57_ready", "f58_ready", "f59_ready", "f60_ready"]
DEFAULT_SUBJECT_SYMBOL_MAP = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
}


def build_options_surface_feature_panel(
    rows: Iterable[Mapping[str, object]],
    *,
    required_underlyings: Sequence[str] = ("BTC", "ETH"),
    realized_vol_panel: pd.DataFrame | None = None,
) -> pd.DataFrame:
    base_panel = build_options_surface_base_panel(
        rows,
        required_underlyings=required_underlyings,
    )
    return finalize_options_surface_feature_panel(
        base_panel,
        realized_vol_panel=realized_vol_panel,
    )


def build_options_surface_base_panel(
    rows: Iterable[Mapping[str, object]],
    *,
    required_underlyings: Sequence[str] = ("BTC", "ETH"),
) -> pd.DataFrame:
    frame = _prepare_options_chain_frame(rows)
    if frame.empty:
        raise RuntimeError("Tardis Deribit options_chain sample is empty after parsing")

    required = {value.upper() for value in required_underlyings}
    if required:
        frame = frame[frame["subject"].isin(required)].copy()
    if frame.empty:
        raise RuntimeError("No required BTC/ETH options rows found in parsed options_chain sample")

    panel_rows = []
    for (subject, date_utc), group in frame.groupby(["subject", "date_utc"], sort=True):
        panel_rows.append(_aggregate_subject_day(subject=subject, date_utc=date_utc, group=group))
    panel = pd.DataFrame(panel_rows).sort_values(["date_utc", "subject"]).reset_index(drop=True)
    if panel.empty:
        raise RuntimeError("No options-surface feature rows could be built")
    return panel


def finalize_options_surface_feature_panel(
    panel: pd.DataFrame,
    *,
    realized_vol_panel: pd.DataFrame | None = None,
) -> pd.DataFrame:
    panel = panel.copy().sort_values(["date_utc", "subject"]).reset_index(drop=True)
    _derive_skew_residual(panel)
    _apply_realized_vol_panel(panel, realized_vol_panel=realized_vol_panel)
    panel["m3_1_options_surface_panel_ready"] = panel[READY_COLUMNS].all(axis=1)
    return panel[_ordered_columns(panel)]


def load_ohlcv_realized_vol_panel(
    *,
    external_root: Path | None = None,
    required_underlyings: Sequence[str] = ("BTC", "ETH"),
    subject_symbol_map: Mapping[str, str] | None = None,
    market_type: str = "spot",
    interval: str = "1d",
    rv_window_days: int = 30,
) -> pd.DataFrame:
    if rv_window_days <= 1:
        raise ValueError("rv_window_days must be > 1")
    resolved_root = resolve_external_history_root(external_root=external_root)
    symbol_map = {**DEFAULT_SUBJECT_SYMBOL_MAP, **dict(subject_symbol_map or {})}
    frames: list[pd.DataFrame] = []
    for subject in [str(value).upper() for value in required_underlyings]:
        symbol = symbol_map.get(subject)
        if not symbol:
            continue
        rows = load_interval_rows(
            external_root=resolved_root,
            market_type=market_type,
            symbol=symbol,
            interval=interval,
        )
        if not rows:
            continue
        frame = pd.DataFrame(rows)
        for column in ("open_time_ms", "close"):
            frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
        frame = frame.dropna(subset=["open_time_ms", "close"]).copy()
        frame = frame[np.isfinite(frame["close"].astype(float))].copy()
        frame = frame[frame["close"].gt(0)].copy()
        if frame.empty:
            continue
        frame["open_time_ms"] = frame["open_time_ms"].astype("int64")
        frame = (
            frame.sort_values("open_time_ms")
            .drop_duplicates(subset=["open_time_ms"], keep="last")
            .reset_index(drop=True)
        )
        frame["subject"] = subject
        frame["rv_symbol"] = symbol
        frame["date_utc"] = pd.to_datetime(
            frame["open_time_ms"],
            unit="ms",
            utc=True,
            errors="coerce",
        ).dt.strftime("%Y-%m-%d")
        frame = frame.dropna(subset=["date_utc"]).sort_values("open_time_ms").reset_index(drop=True)
        log_return = np.log(frame["close"].astype(float)).diff()
        frame["realized_vol_30d_ohlcv"] = (
            log_return.rolling(rv_window_days, min_periods=rv_window_days).std()
            * np.sqrt(365.0)
            * 100.0
        )
        frame["realized_vol_ohlcv_observation_count"] = (
            log_return.notna().rolling(rv_window_days, min_periods=1).sum().astype("int64")
        )
        frame["realized_vol_ohlcv_window_days"] = rv_window_days
        frame["realized_vol_ohlcv_market_type"] = market_type
        frame["realized_vol_ohlcv_interval"] = interval
        frame["realized_vol_ohlcv_root"] = str(resolved_root)
        frames.append(
            frame[
                [
                    "subject",
                    "date_utc",
                    "rv_symbol",
                    "realized_vol_30d_ohlcv",
                    "realized_vol_ohlcv_observation_count",
                    "realized_vol_ohlcv_window_days",
                    "realized_vol_ohlcv_market_type",
                    "realized_vol_ohlcv_interval",
                    "realized_vol_ohlcv_root",
                ]
            ]
        )
    if not frames:
        return pd.DataFrame(
            columns=[
                "subject",
                "date_utc",
                "rv_symbol",
                "realized_vol_30d_ohlcv",
                "realized_vol_ohlcv_observation_count",
                "realized_vol_ohlcv_window_days",
                "realized_vol_ohlcv_market_type",
                "realized_vol_ohlcv_interval",
                "realized_vol_ohlcv_root",
            ]
        )
    return pd.concat(frames, ignore_index=True).sort_values(["subject", "date_utc"]).reset_index(drop=True)


def write_options_surface_feature_panel(
    panel: pd.DataFrame,
    *,
    output_path: Path = DEFAULT_OUT_PATH,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output_path, index=False)
    return output_path


def summarize_options_surface_feature_panel(
    panel: pd.DataFrame,
    *,
    required_underlyings: Sequence[str] = ("BTC", "ETH"),
    output_path: Path | None = None,
    input_rows_read: int | None = None,
) -> dict[str, Any]:
    required = {value.upper() for value in required_underlyings}
    subjects_present = sorted(str(value) for value in panel["subject"].dropna().unique())
    required_subjects_present = sorted(required.intersection(subjects_present))
    ready_counts = {
        column: int(panel[column].fillna(False).astype(bool).sum())
        for column in READY_COLUMNS
        if column in panel.columns
    }
    factor_non_null_counts = {
        column: int(panel[column].notna().sum()) for column in FACTOR_COLUMNS if column in panel.columns
    }
    all_required_ready = False
    if required:
        latest_by_subject = panel.sort_values("date_utc").groupby("subject", as_index=False).tail(1)
        ready_subjects = set(
            latest_by_subject.loc[
                latest_by_subject["m3_1_options_surface_panel_ready"].fillna(False).astype(bool),
                "subject",
            ]
        )
        all_required_ready = required.issubset(ready_subjects)

    return {
        "contract_version": OPTIONS_SURFACE_FEATURE_PANEL_CONTRACT_VERSION,
        "row_count": int(panel.shape[0]),
        "column_count": int(panel.shape[1]),
        "input_rows_read": input_rows_read,
        "subjects_present": subjects_present,
        "required_subjects": sorted(required),
        "required_subjects_present": required_subjects_present,
        "start_date_utc": str(panel["date_utc"].min()) if not panel.empty else None,
        "end_date_utc": str(panel["date_utc"].max()) if not panel.empty else None,
        "output_path": str(output_path) if output_path is not None else None,
        "raw_sample_retained": False,
        "feature_readiness": {
            "ready_row_counts": ready_counts,
            "factor_non_null_counts": factor_non_null_counts,
            "all_required_subjects_latest_ready": all_required_ready,
        },
        "method_notes": {
            "iv_unit": "percent",
            "f56": "25-delta put IV minus call IV; residual falls back to raw skew until a rolling 60d baseline is available.",
            "f57": "front ATM IV minus 30d realized volatility joined from canonical spot OHLCV; the decision date is date_utc + 1 day.",
            "f58": "front ATM IV minus mid-expiry ATM IV.",
            "f59": "OI and gamma weighted signed strike-distance proxy; call rows positive, put rows negative.",
            "f60": "near-expiry ATM OI concentration weighted by 1/(days_to_expiry+1).",
        },
        "latest_row_preview": panel.tail(1).to_dict(orient="records")[0] if not panel.empty else None,
    }


def _prepare_options_chain_frame(rows: Iterable[Mapping[str, object]]) -> pd.DataFrame:
    data = pd.DataFrame(list(rows))
    if data.empty:
        return pd.DataFrame()

    required_columns = [
        "symbol",
        "timestamp",
        "type",
        "strike_price",
        "expiration",
        "open_interest",
        "mark_iv",
        "underlying_index",
        "underlying_price",
        "delta",
        "gamma",
    ]
    missing = [column for column in required_columns if column not in data.columns]
    if missing:
        raise RuntimeError(f"Tardis options_chain sample missing required columns: {missing}")

    numeric_columns = [
        "timestamp",
        "expiration",
        "strike_price",
        "open_interest",
        "mark_iv",
        "underlying_price",
        "delta",
        "gamma",
        "vega",
        "theta",
        "rho",
    ]
    for column in numeric_columns:
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")

    data["subject"] = data.apply(_underlying_from_row, axis=1)
    data["option_type"] = data["type"].astype(str).str.strip().str.lower()
    data["timestamp_utc"] = pd.to_datetime(data["timestamp"], unit="us", utc=True, errors="coerce")
    data["expiration_utc"] = pd.to_datetime(data["expiration"], unit="us", utc=True, errors="coerce")
    data["date_utc"] = data["timestamp_utc"].dt.strftime("%Y-%m-%d")
    data["days_to_expiry"] = (
        (data["expiration_utc"] - data["timestamp_utc"]).dt.total_seconds() / 86_400.0
    )
    data["mark_iv_percent"] = _normalize_iv_to_percent(data["mark_iv"])
    data = data[
        data["subject"].isin({"BTC", "ETH"})
        & data["timestamp_utc"].notna()
        & data["expiration_utc"].notna()
        & data["date_utc"].notna()
        & data["days_to_expiry"].gt(0)
    ].copy()
    return data


def _aggregate_subject_day(*, subject: str, date_utc: str, group: pd.DataFrame) -> dict[str, Any]:
    put_25d = _median_near_delta_iv(group, option_type="put", lower=0.15, upper=0.35)
    call_25d = _median_near_delta_iv(group, option_type="call", lower=0.15, upper=0.35)
    skew = _safe_subtract(put_25d, call_25d)

    atm_expiries = _atm_iv_by_expiry(group)
    front = atm_expiries.iloc[0] if not atm_expiries.empty else None
    mid = _select_mid_expiry(atm_expiries)
    front_iv = _value_or_nan(front, "iv_atm")
    mid_iv = _value_or_nan(mid, "iv_atm")
    iv_term_slope = _safe_subtract(front_iv, mid_iv)
    dealer_gamma_proxy, dealer_gamma_exposure = _dealer_gamma_proxy(group)
    vanna_charm_window = _vanna_charm_window(group)

    timestamp_min = group["timestamp_utc"].min()
    timestamp_max = group["timestamp_utc"].max()
    row = {
        "subject": subject,
        "date_utc": date_utc,
        "decision_date_utc": _decision_date(date_utc),
        "source": "tardis_deribit_options_chain",
        "row_count": int(group.shape[0]),
        "timestamp_min_utc": timestamp_min.isoformat() if pd.notna(timestamp_min) else None,
        "timestamp_max_utc": timestamp_max.isoformat() if pd.notna(timestamp_max) else None,
        "expiry_count": int(group["expiration"].nunique(dropna=True)),
        "option_symbol_count": int(group["symbol"].nunique(dropna=True)),
        "iv_25d_put": put_25d,
        "iv_25d_call": call_25d,
        "iv_25d_skew": skew,
        "iv_25d_skew_residual": np.nan,
        "iv_25d_skew_residual_method": "pending",
        "iv_atm_front": front_iv,
        "iv_atm_mid": mid_iv,
        "iv_front_expiry_days": _value_or_nan(front, "days_to_expiry"),
        "iv_mid_expiry_days": _value_or_nan(mid, "days_to_expiry"),
        "iv_term_slope": iv_term_slope,
        "realized_vol_30d_ohlcv": np.nan,
        "realized_vol_ohlcv_observation_count": 0,
        "realized_vol_ohlcv_window_days": 30,
        "realized_vol_ohlcv_market_type": "spot",
        "realized_vol_ohlcv_interval": "1d",
        "realized_vol_ohlcv_root": None,
        "rv_symbol": None,
        "iv_rv_spread": np.nan,
        "dealer_gamma_proxy": dealer_gamma_proxy,
        "dealer_gamma_exposure_proxy": dealer_gamma_exposure,
        "vanna_charm_window": vanna_charm_window,
    }
    row.update(
        {
            "f56_ready": _is_finite(row["iv_25d_put"]) and _is_finite(row["iv_25d_call"]),
            "f57_ready": False,
            "f58_ready": _is_finite(row["iv_atm_front"]) and _is_finite(row["iv_atm_mid"]),
            "f59_ready": _is_finite(row["dealer_gamma_proxy"]),
            "f60_ready": _is_finite(row["vanna_charm_window"]),
        }
    )
    return row


def _derive_skew_residual(panel: pd.DataFrame) -> None:
    panel["iv_25d_skew"] = pd.to_numeric(panel["iv_25d_skew"], errors="coerce")
    panel["iv_25d_skew_residual"] = np.nan
    panel["iv_25d_skew_residual_method"] = "raw_skew_until_60d_baseline"
    for subject, index in panel.groupby("subject").groups.items():
        ordered = panel.loc[index].sort_values("date_utc")
        skew = ordered["iv_25d_skew"]
        rolling_mean = skew.rolling(60, min_periods=20).mean()
        residual = skew - rolling_mean
        panel.loc[ordered.index, "iv_25d_skew_residual"] = residual.fillna(skew)
        ready_baseline = rolling_mean.notna()
        panel.loc[ordered.index[ready_baseline], "iv_25d_skew_residual_method"] = (
            "skew_minus_rolling_60d_mean"
        )
    panel["f56_ready"] = panel["f56_ready"] & panel["iv_25d_skew_residual"].notna()


def _apply_realized_vol_panel(
    panel: pd.DataFrame,
    *,
    realized_vol_panel: pd.DataFrame | None,
) -> None:
    if realized_vol_panel is None or realized_vol_panel.empty:
        panel["realized_vol_30d_ohlcv"] = np.nan
        panel["realized_vol_ohlcv_observation_count"] = 0
        panel["f57_ready"] = False
        panel["iv_rv_spread"] = np.nan
        return

    rv = realized_vol_panel.copy()
    required = {"subject", "date_utc", "realized_vol_30d_ohlcv"}
    missing = sorted(required - set(rv.columns))
    if missing:
        raise RuntimeError(f"realized_vol_panel missing required columns: {missing}")
    rv["subject"] = rv["subject"].astype(str).str.upper()
    rv["date_utc"] = rv["date_utc"].astype(str)
    rv = (
        rv.sort_values(["subject", "date_utc"])
        .drop_duplicates(subset=["subject", "date_utc"], keep="last")
        .reset_index(drop=True)
    )
    rv_columns = [
        column
        for column in [
            "subject",
            "date_utc",
            "rv_symbol",
            "realized_vol_30d_ohlcv",
            "realized_vol_ohlcv_observation_count",
            "realized_vol_ohlcv_window_days",
            "realized_vol_ohlcv_market_type",
            "realized_vol_ohlcv_interval",
            "realized_vol_ohlcv_root",
        ]
        if column in rv.columns
    ]
    merged = panel[["subject", "date_utc"]].merge(
        rv[rv_columns],
        on=["subject", "date_utc"],
        how="left",
        sort=False,
    )
    for column in rv_columns:
        if column in {"subject", "date_utc"}:
            continue
        panel[column] = merged[column].values
    panel["realized_vol_30d_ohlcv"] = pd.to_numeric(
        panel["realized_vol_30d_ohlcv"],
        errors="coerce",
    )
    if "realized_vol_ohlcv_observation_count" in panel.columns:
        panel["realized_vol_ohlcv_observation_count"] = pd.to_numeric(
            panel["realized_vol_ohlcv_observation_count"],
            errors="coerce",
        ).fillna(0).astype("int64")
    panel["iv_rv_spread"] = panel["iv_atm_front"] - panel["realized_vol_30d_ohlcv"]
    panel["f57_ready"] = panel["iv_atm_front"].notna() & panel["realized_vol_30d_ohlcv"].notna()


def _median_near_delta_iv(
    group: pd.DataFrame,
    *,
    option_type: str,
    lower: float,
    upper: float,
) -> float:
    subset = group[
        group["option_type"].eq(option_type)
        & group["delta"].abs().between(lower, upper)
        & group["mark_iv_percent"].notna()
    ]
    if subset.empty:
        return np.nan
    return float(subset["mark_iv_percent"].median())


def _atm_iv_by_expiry(group: pd.DataFrame) -> pd.DataFrame:
    atm = group[
        group["delta"].abs().between(0.40, 0.60)
        & group["mark_iv_percent"].notna()
        & group["days_to_expiry"].gt(0)
    ].copy()
    if atm.empty:
        return pd.DataFrame(columns=["expiration", "days_to_expiry", "iv_atm", "row_count"])
    return (
        atm.groupby("expiration", as_index=False)
        .agg(
            days_to_expiry=("days_to_expiry", "median"),
            iv_atm=("mark_iv_percent", "median"),
            row_count=("mark_iv_percent", "count"),
        )
        .sort_values("days_to_expiry")
        .reset_index(drop=True)
    )


def _select_mid_expiry(expiries: pd.DataFrame) -> pd.Series | None:
    if expiries.shape[0] < 2:
        return None
    front_days = float(expiries.iloc[0]["days_to_expiry"])
    later = expiries[expiries["days_to_expiry"].ge(front_days + 7.0)]
    if not later.empty:
        return later.iloc[0]
    return expiries.iloc[1]


def _dealer_gamma_proxy(group: pd.DataFrame) -> tuple[float, float]:
    data = group[
        group["open_interest"].notna()
        & group["gamma"].notna()
        & group["strike_price"].notna()
        & group["underlying_price"].notna()
        & group["underlying_price"].gt(0)
    ].copy()
    if data.empty:
        return np.nan, np.nan
    sign = np.where(data["option_type"].eq("call"), 1.0, np.where(data["option_type"].eq("put"), -1.0, 0.0))
    distance = ((data["strike_price"] - data["underlying_price"]) / data["underlying_price"]).astype(float)
    gamma_weight = (data["open_interest"].abs() * data["gamma"].abs()).astype(float)
    denominator = float(gamma_weight.sum())
    if denominator <= 0:
        return np.nan, np.nan
    proxy = float((gamma_weight * sign * np.square(distance)).sum() / denominator)
    exposure = float(
        (data["open_interest"].astype(float) * data["gamma"].astype(float) * sign * np.square(data["underlying_price"]))
        .sum()
    )
    return proxy, exposure


def _vanna_charm_window(group: pd.DataFrame) -> float:
    data = group[
        group["open_interest"].notna()
        & group["days_to_expiry"].gt(0)
        & group["delta"].abs().between(0.40, 0.60)
    ].copy()
    total_oi = pd.to_numeric(group["open_interest"], errors="coerce").dropna().clip(lower=0).sum()
    if total_oi <= 0 or data.empty:
        return np.nan
    near = data[data["days_to_expiry"].le(7.0)].copy()
    if near.empty:
        return 0.0
    weighted_atm_oi = (near["open_interest"].clip(lower=0) / (near["days_to_expiry"] + 1.0)).sum()
    return float(weighted_atm_oi / total_oi)


def _normalize_iv_to_percent(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    median = values.dropna().median()
    if pd.notna(median) and median <= 3.0:
        return values * 100.0
    return values


def _underlying_from_row(row: pd.Series) -> str:
    underlying_index = str(row.get("underlying_index", "")).upper()
    if "BTC" in underlying_index:
        return "BTC"
    if "ETH" in underlying_index:
        return "ETH"
    symbol = str(row.get("symbol", "")).upper()
    if symbol.startswith("BTC-"):
        return "BTC"
    if symbol.startswith("ETH-"):
        return "ETH"
    return "UNKNOWN"


def _ordered_columns(panel: pd.DataFrame) -> list[str]:
    preferred = [
        "subject",
        "date_utc",
        "decision_date_utc",
        "source",
        "row_count",
        "timestamp_min_utc",
        "timestamp_max_utc",
        "expiry_count",
        "option_symbol_count",
        "iv_25d_put",
        "iv_25d_call",
        "iv_25d_skew",
        "iv_25d_skew_residual",
        "iv_25d_skew_residual_method",
        "iv_atm_front",
        "iv_atm_mid",
        "iv_front_expiry_days",
        "iv_mid_expiry_days",
        "iv_term_slope",
        "rv_symbol",
        "realized_vol_30d_ohlcv",
        "realized_vol_ohlcv_observation_count",
        "realized_vol_ohlcv_window_days",
        "realized_vol_ohlcv_market_type",
        "realized_vol_ohlcv_interval",
        "realized_vol_ohlcv_root",
        "iv_rv_spread",
        "dealer_gamma_proxy",
        "dealer_gamma_exposure_proxy",
        "vanna_charm_window",
        *READY_COLUMNS,
        "m3_1_options_surface_panel_ready",
    ]
    return [column for column in preferred if column in panel.columns] + [
        column for column in panel.columns if column not in preferred
    ]


def _decision_date(date_utc: str) -> str:
    timestamp = pd.Timestamp(date_utc, tz=UTC)
    return (timestamp + pd.Timedelta(days=1)).strftime("%Y-%m-%d")


def _safe_subtract(left: float, right: float) -> float:
    if not _is_finite(left) or not _is_finite(right):
        return np.nan
    return float(left - right)


def _value_or_nan(row: pd.Series | None, column: str) -> float:
    if row is None:
        return np.nan
    value = row.get(column)
    return float(value) if _is_finite(value) else np.nan


def _is_finite(value: object) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False
