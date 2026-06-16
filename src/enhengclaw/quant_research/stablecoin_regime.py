from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .onchain_stablecoin import DEFAULT_TOKEN_SPECS, resolve_onchain_external_root


ROOT = Path(__file__).resolve().parents[3]
STABLECOIN_REGIME_CONTRACT_VERSION = "quant_stablecoin_regime_overlay.v3"
DEFAULT_STABLECOIN_OVERLAY_ID = "stablecoin_issuance_velocity_overlay_v1"
DEFAULT_STABLECOIN_OVERLAY_V2_ID = "stablecoin_issuance_velocity_overlay_v2"
DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID = "stablecoin_exchange_absorption_overlay_v1"
DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID = "stablecoin_whale_to_exchange_stress_overlay_v1"
_REQUIRED_TOKEN_COUNT = len(DEFAULT_TOKEN_SPECS)
_REQUIRED_FULL_DAYS = 7
_NORMALIZATION_WINDOW = 14
_MIN_NORMALIZATION_PERIODS = 5
_EXPANSION_THRESHOLD = 0.75
_CONTRACTION_THRESHOLD = -0.75
_OVERLAY_EXPANSION = 1.0
_OVERLAY_NEUTRAL = 0.85
_OVERLAY_CONTRACTION = 0.70
_V2_WATCH_THRESHOLD = -0.50
_V2_HARD_CONTRACTION_THRESHOLD = -1.25
_V2_ISSUANCE_CONFIRM_THRESHOLD = -0.25
_V2_ISSUANCE_HARD_THRESHOLD = -1.00
_V2_BREADTH_CONFIRM_THRESHOLD = 0.34
_V2_VELOCITY_CONFIRM_THRESHOLD = 0.95
_V2_VELOCITY_HARD_THRESHOLD = 0.85
_V2_SOFT_FLOOR = 0.88
_V2_HARD_FLOOR = 0.80
_FLOW_MIN_COVERAGE_RATIO = 0.03
_FLOW_EXPANSION_THRESHOLD = 0.60
_FLOW_DRAIN_THRESHOLD = -0.90
_FLOW_HARD_DRAIN_THRESHOLD = -1.40
_FLOW_DRAIN_MULTIPLIER = 0.85
_FLOW_HARD_DRAIN_MULTIPLIER = 0.75
_WHALE_STRESS_THRESHOLD = 0.75
_WHALE_HARD_STRESS_THRESHOLD = 1.15
_WHALE_STRESS_MULTIPLIER = 0.90
_WHALE_HARD_STRESS_MULTIPLIER = 0.80


def load_stablecoin_daily_aggregates(external_root: Path | None = None) -> tuple[pd.DataFrame, Path]:
    root = resolve_onchain_external_root(external_root=external_root)
    path = root / "daily_aggregates.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"stablecoin aggregate CSV not found at {path}. "
            "Run scripts/quant_research/sync_alchemy_stablecoin_ethereum.py first."
        )
    df = pd.read_csv(path)
    if df.empty:
        raise RuntimeError(f"stablecoin aggregate CSV is empty: {path}")
    return df, path


def build_stablecoin_regime_panel(external_root: Path | None = None) -> pd.DataFrame:
    raw, _ = load_stablecoin_daily_aggregates(external_root)
    if "is_full_day" not in raw.columns:
        raw["is_full_day"] = False
    if "fetch_status" not in raw.columns:
        raw["fetch_status"] = "legacy_missing"

    required_columns = {
        "date_utc",
        "token_symbol",
        "transfer_count",
        "transfer_amount",
        "net_issuance_amount",
        "mint_amount",
        "burn_amount",
        "whale_transfer_amount",
        "is_full_day",
        "fetch_status",
    }
    missing = sorted(required_columns - set(raw.columns))
    if missing:
        raise RuntimeError(f"stablecoin aggregate CSV missing required columns: {missing}")

    for optional_column in (
        "exchange_inflow_amount",
        "exchange_outflow_amount",
        "exchange_netflow_amount",
        "whale_to_exchange_amount",
        "exchange_to_whale_amount",
        "issuer_to_exchange_amount",
        "bridge_inflow_amount",
        "bridge_outflow_amount",
        "labeled_transfer_share_amount",
        "unknown_transfer_share_amount",
    ):
        if optional_column not in raw.columns:
            raw[optional_column] = 0.0

    df = raw.copy()
    df["date_utc"] = df["date_utc"].astype(str)
    df["token_symbol"] = df["token_symbol"].astype(str).str.upper()
    df["is_full_day"] = _as_bool_series(df["is_full_day"])
    df["fetch_status"] = df["fetch_status"].astype(str).str.strip().str.lower()
    for column in (
        "transfer_count",
        "transfer_amount",
        "net_issuance_amount",
        "mint_amount",
        "burn_amount",
        "whale_transfer_amount",
        "exchange_inflow_amount",
        "exchange_outflow_amount",
        "exchange_netflow_amount",
        "whale_to_exchange_amount",
        "exchange_to_whale_amount",
        "issuer_to_exchange_amount",
        "bridge_inflow_amount",
        "bridge_outflow_amount",
        "labeled_transfer_share_amount",
        "unknown_transfer_share_amount",
    ):
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)

    eligible = df[(df["is_full_day"]) & (df["fetch_status"] != "partial")].copy()
    if eligible.empty:
        return pd.DataFrame()

    token_counts = eligible.groupby("date_utc")["token_symbol"].nunique()
    good_dates = token_counts[token_counts >= _REQUIRED_TOKEN_COUNT].index
    eligible = eligible[eligible["date_utc"].isin(good_dates)].copy()
    if eligible.empty:
        return pd.DataFrame()

    grouped = (
        eligible.groupby("date_utc", as_index=False)
        .agg(
            tracked_token_count=("token_symbol", "nunique"),
            total_transfer_count=("transfer_count", "sum"),
            total_transfer_amount=("transfer_amount", "sum"),
            total_net_issuance_amount=("net_issuance_amount", "sum"),
            total_mint_amount=("mint_amount", "sum"),
            total_burn_amount=("burn_amount", "sum"),
            total_whale_transfer_amount=("whale_transfer_amount", "sum"),
            total_exchange_inflow_amount=("exchange_inflow_amount", "sum"),
            total_exchange_outflow_amount=("exchange_outflow_amount", "sum"),
            total_exchange_netflow_amount=("exchange_netflow_amount", "sum"),
            total_whale_to_exchange_amount=("whale_to_exchange_amount", "sum"),
            total_exchange_to_whale_amount=("exchange_to_whale_amount", "sum"),
            total_issuer_to_exchange_amount=("issuer_to_exchange_amount", "sum"),
            total_bridge_inflow_amount=("bridge_inflow_amount", "sum"),
            total_bridge_outflow_amount=("bridge_outflow_amount", "sum"),
            total_labeled_transfer_share_amount=("labeled_transfer_share_amount", "sum"),
            total_unknown_transfer_share_amount=("unknown_transfer_share_amount", "sum"),
        )
        .sort_values("date_utc")
        .reset_index(drop=True)
    )
    positive_counts = (
        eligible.assign(net_positive=(eligible["net_issuance_amount"] > 0).astype(int))
        .groupby("date_utc")["net_positive"]
        .sum()
        .reindex(grouped["date_utc"])
        .fillna(0)
        .astype(int)
        .to_numpy()
    )
    grouped["positive_issuance_token_count"] = positive_counts
    grouped["issuance_breadth"] = (
        grouped["positive_issuance_token_count"] / grouped["tracked_token_count"].replace(0, np.nan)
    ).fillna(0.0)
    grouped["issuance_ratio"] = (
        grouped["total_net_issuance_amount"] / grouped["total_transfer_amount"].replace(0.0, np.nan)
    ).replace([np.inf, -np.inf], np.nan)
    grouped["velocity_log"] = np.log1p(grouped["total_transfer_amount"].clip(lower=0.0))
    grouped["labeled_coverage_ratio"] = _safe_ratio(
        grouped["total_labeled_transfer_share_amount"],
        grouped["total_transfer_amount"],
    )
    grouped["exchange_inflow_ratio"] = _safe_ratio(
        grouped["total_exchange_inflow_amount"],
        grouped["total_transfer_amount"],
    )
    grouped["exchange_outflow_ratio"] = _safe_ratio(
        grouped["total_exchange_outflow_amount"],
        grouped["total_transfer_amount"],
    )
    grouped["exchange_netflow_ratio"] = _safe_ratio(
        grouped["total_exchange_netflow_amount"],
        grouped["total_transfer_amount"],
    )
    grouped["whale_to_exchange_ratio"] = _safe_ratio(
        grouped["total_whale_to_exchange_amount"],
        grouped["total_transfer_amount"],
    )
    grouped["exchange_to_whale_ratio"] = _safe_ratio(
        grouped["total_exchange_to_whale_amount"],
        grouped["total_transfer_amount"],
    )
    grouped["issuer_to_exchange_ratio"] = _safe_ratio(
        grouped["total_issuer_to_exchange_amount"],
        grouped["total_transfer_amount"],
    )
    grouped["velocity_ratio_7d"] = grouped["total_transfer_amount"] / (
        grouped["total_transfer_amount"].rolling(7, min_periods=3).median().replace(0.0, np.nan)
    )
    grouped["issuance_ratio_z14"] = _rolling_z(grouped["issuance_ratio"])
    grouped["velocity_log_z14"] = _rolling_z(grouped["velocity_log"])
    grouped["labeled_coverage_ratio_z14"] = _rolling_z(grouped["labeled_coverage_ratio"])
    grouped["exchange_netflow_ratio_z14"] = _rolling_z(grouped["exchange_netflow_ratio"])
    grouped["whale_to_exchange_ratio_z14"] = _rolling_z(grouped["whale_to_exchange_ratio"])
    grouped["issuer_to_exchange_ratio_z14"] = _rolling_z(grouped["issuer_to_exchange_ratio"])
    grouped["score_v1"] = 0.65 * grouped["issuance_ratio_z14"] + 0.35 * grouped["velocity_log_z14"]
    grouped["regime_label_v1"] = grouped["score_v1"].apply(_score_to_regime_label)
    grouped["overlay_multiplier_v1"] = grouped["regime_label_v1"].map(
        {
            "expansion": _OVERLAY_EXPANSION,
            "neutral": _OVERLAY_NEUTRAL,
            "contraction": _OVERLAY_CONTRACTION,
        }
    )
    v2_state_multiplier = grouped.apply(_overlay_state_and_multiplier_v2, axis=1, result_type="expand")
    v2_state_multiplier.columns = ["regime_label_v2", "overlay_multiplier_v2"]
    grouped[["regime_label_v2", "overlay_multiplier_v2"]] = v2_state_multiplier
    grouped["exchange_absorption_score_v1"] = (
        0.50 * grouped["exchange_netflow_ratio_z14"].fillna(0.0)
        + 0.30 * grouped["issuer_to_exchange_ratio_z14"].fillna(0.0)
        + 0.20 * grouped["issuance_ratio_z14"].fillna(0.0)
    )
    exchange_state_multiplier = grouped.apply(
        _overlay_state_and_multiplier_exchange_absorption_v1,
        axis=1,
        result_type="expand",
    )
    exchange_state_multiplier.columns = [
        "regime_label_exchange_absorption_v1",
        "overlay_multiplier_exchange_absorption_v1",
    ]
    grouped[
        ["regime_label_exchange_absorption_v1", "overlay_multiplier_exchange_absorption_v1"]
    ] = exchange_state_multiplier
    grouped["whale_exchange_stress_score_v1"] = (
        0.55 * grouped["whale_to_exchange_ratio_z14"].fillna(0.0)
        - 0.30 * grouped["exchange_netflow_ratio_z14"].fillna(0.0)
        - 0.15 * grouped["issuance_ratio_z14"].fillna(0.0)
    )
    whale_state_multiplier = grouped.apply(
        _overlay_state_and_multiplier_whale_stress_v1,
        axis=1,
        result_type="expand",
    )
    whale_state_multiplier.columns = [
        "regime_label_whale_stress_v1",
        "overlay_multiplier_whale_stress_v1",
    ]
    grouped[["regime_label_whale_stress_v1", "overlay_multiplier_whale_stress_v1"]] = whale_state_multiplier
    grouped["signal_ready"] = grouped[["issuance_ratio_z14", "velocity_log_z14"]].notna().all(axis=1)
    grouped["decision_date_utc"] = (
        pd.to_datetime(grouped["date_utc"], utc=True) + pd.Timedelta(days=1)
    ).dt.strftime("%Y-%m-%d")
    return grouped


def compute_stablecoin_issuance_velocity_overlay_v1(
    external_root: Path | None = None,
) -> dict[str, float]:
    return _compute_overlay_table(external_root=external_root, overlay_id=DEFAULT_STABLECOIN_OVERLAY_ID)


def compute_stablecoin_issuance_velocity_overlay_v2(
    external_root: Path | None = None,
) -> dict[str, float]:
    return _compute_overlay_table(external_root=external_root, overlay_id=DEFAULT_STABLECOIN_OVERLAY_V2_ID)


def compute_stablecoin_exchange_absorption_overlay_v1(
    external_root: Path | None = None,
) -> dict[str, float]:
    return _compute_overlay_table(
        external_root=external_root,
        overlay_id=DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID,
    )


def compute_stablecoin_whale_to_exchange_stress_overlay_v1(
    external_root: Path | None = None,
) -> dict[str, float]:
    return _compute_overlay_table(
        external_root=external_root,
        overlay_id=DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID,
    )


def stablecoin_overlay_summary(
    external_root: Path | None = None,
    overlay_id: str = DEFAULT_STABLECOIN_OVERLAY_ID,
) -> dict[str, Any]:
    raw, path = load_stablecoin_daily_aggregates(external_root)
    panel = build_stablecoin_regime_panel(external_root)
    if panel.empty:
        return {
            "available": False,
            "overlay_id": overlay_id,
            "contract_version": STABLECOIN_REGIME_CONTRACT_VERSION,
            "raw_csv_path": str(path),
            "raw_row_count": int(raw.shape[0]),
            "reason": "no complete multi-token daily slices available yet",
        }

    label_column, multiplier_column, score_column = _overlay_columns_for_id(overlay_id)
    ready = panel[_overlay_ready_mask(panel=panel, overlay_id=overlay_id)].copy()
    latest_full = panel.iloc[-1]
    latest_ready = ready.iloc[-1] if not ready.empty else None
    regime_counts = ready[label_column].value_counts().to_dict() if not ready.empty else {}
    multiplier_counts = ready[multiplier_column].value_counts().to_dict() if not ready.empty else {}
    preview_columns = [
        "date_utc",
        "decision_date_utc",
        "total_transfer_amount",
        "total_net_issuance_amount",
        "issuance_ratio",
        "velocity_ratio_7d",
        "labeled_coverage_ratio",
        "exchange_netflow_ratio",
        "whale_to_exchange_ratio",
        score_column,
        label_column,
        multiplier_column,
        "signal_ready",
    ]
    return {
        "available": True,
        "overlay_id": overlay_id,
        "contract_version": STABLECOIN_REGIME_CONTRACT_VERSION,
        "raw_csv_path": str(path),
        "raw_row_count": int(raw.shape[0]),
        "full_day_count": int(panel.shape[0]),
        "ready_signal_day_count": int(ready.shape[0]),
        "history_ready": bool(panel.shape[0] >= _REQUIRED_FULL_DAYS and not ready.empty),
        "required_full_days": _REQUIRED_FULL_DAYS,
        "normalization_window_days": _NORMALIZATION_WINDOW,
        "flow_min_coverage_ratio": _FLOW_MIN_COVERAGE_RATIO,
        "tracked_token_symbols": [token.symbol for token in DEFAULT_TOKEN_SPECS],
        "latest_full_day": _panel_row_to_summary(
            latest_full,
            label_column=label_column,
            multiplier_column=multiplier_column,
            score_column=score_column,
        ),
        "latest_ready_signal": (
            _panel_row_to_summary(
                latest_ready,
                label_column=label_column,
                multiplier_column=multiplier_column,
                score_column=score_column,
            )
            if latest_ready is not None
            else None
        ),
        "regime_counts": {str(key): int(value) for key, value in regime_counts.items()},
        "overlay_multiplier_counts": {str(key): int(value) for key, value in multiplier_counts.items()},
        "overlay_table_size": int(ready.shape[0]),
        "preview_rows": ready.tail(5)[preview_columns].to_dict(orient="records") if not ready.empty else [],
    }


def stablecoin_issuance_velocity_overlay_summary(
    external_root: Path | None = None,
    overlay_id: str = DEFAULT_STABLECOIN_OVERLAY_ID,
) -> dict[str, Any]:
    return stablecoin_overlay_summary(external_root=external_root, overlay_id=overlay_id)


def _compute_overlay_table(
    *,
    external_root: Path | None,
    overlay_id: str,
) -> dict[str, float]:
    panel = build_stablecoin_regime_panel(external_root)
    if panel.empty:
        return {}
    ready = panel[_overlay_ready_mask(panel=panel, overlay_id=overlay_id)].copy()
    if ready.empty:
        return {}
    _, multiplier_column, _ = _overlay_columns_for_id(overlay_id)
    return {
        str(row["decision_date_utc"]): float(row[multiplier_column])
        for _, row in ready.iterrows()
    }


def _overlay_columns_for_id(overlay_id: str) -> tuple[str, str, str]:
    if overlay_id == DEFAULT_STABLECOIN_OVERLAY_ID:
        return "regime_label_v1", "overlay_multiplier_v1", "score_v1"
    if overlay_id == DEFAULT_STABLECOIN_OVERLAY_V2_ID:
        return "regime_label_v2", "overlay_multiplier_v2", "score_v1"
    if overlay_id == DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID:
        return (
            "regime_label_exchange_absorption_v1",
            "overlay_multiplier_exchange_absorption_v1",
            "exchange_absorption_score_v1",
        )
    if overlay_id == DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID:
        return (
            "regime_label_whale_stress_v1",
            "overlay_multiplier_whale_stress_v1",
            "whale_exchange_stress_score_v1",
        )
    raise ValueError(f"unsupported stablecoin overlay id: {overlay_id!r}")


def _overlay_ready_mask(panel: pd.DataFrame, *, overlay_id: str) -> pd.Series:
    base_ready = panel["signal_ready"].copy()
    if overlay_id in {
        DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID,
        DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID,
    }:
        _, _, score_column = _overlay_columns_for_id(overlay_id)
        return (
            base_ready
            & (panel["labeled_coverage_ratio"] >= _FLOW_MIN_COVERAGE_RATIO)
            & panel[score_column].notna()
        )
    return base_ready


def _rolling_z(series: pd.Series) -> pd.Series:
    rolling_mean = series.rolling(_NORMALIZATION_WINDOW, min_periods=_MIN_NORMALIZATION_PERIODS).mean()
    rolling_std = series.rolling(_NORMALIZATION_WINDOW, min_periods=_MIN_NORMALIZATION_PERIODS).std()
    return (series - rolling_mean) / rolling_std.replace(0.0, np.nan)


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return (numerator / denominator.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _score_to_regime_label(score: float) -> str:
    if pd.isna(score):
        return "neutral"
    if float(score) >= _EXPANSION_THRESHOLD:
        return "expansion"
    if float(score) <= _CONTRACTION_THRESHOLD:
        return "contraction"
    return "neutral"


def _as_bool_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y"})


def _overlay_state_and_multiplier_v2(row: pd.Series) -> tuple[str, float]:
    score = row.get("score_v1")
    issuance_z = row.get("issuance_ratio_z14")
    velocity_ratio = row.get("velocity_ratio_7d")
    issuance_breadth = row.get("issuance_breadth")
    if pd.isna(score) or pd.isna(issuance_z):
        return "open", 1.0
    score_value = float(score)
    issuance_z_value = float(issuance_z)
    velocity_ratio_value = 1.0 if pd.isna(velocity_ratio) else float(velocity_ratio)
    issuance_breadth_value = 1.0 if pd.isna(issuance_breadth) else float(issuance_breadth)

    if score_value >= 0.0:
        return "open", 1.0

    issuance_confirmed = (
        issuance_z_value <= _V2_ISSUANCE_CONFIRM_THRESHOLD
        or issuance_breadth_value <= _V2_BREADTH_CONFIRM_THRESHOLD
    )
    velocity_confirmed = velocity_ratio_value <= _V2_VELOCITY_CONFIRM_THRESHOLD
    if score_value > _V2_WATCH_THRESHOLD or not issuance_confirmed:
        return "watch", 1.0

    contraction_pressure = max(0.0, -score_value - abs(_V2_WATCH_THRESHOLD))
    soft_multiplier = 1.0 - 0.10 * math.tanh(0.90 * contraction_pressure)
    if velocity_confirmed:
        velocity_drag = min(max((_V2_VELOCITY_CONFIRM_THRESHOLD - velocity_ratio_value) / 0.25, 0.0), 1.0)
        soft_multiplier -= 0.05 * velocity_drag
    soft_multiplier = max(_V2_SOFT_FLOOR, min(1.0, soft_multiplier))

    hard_confirmed = (
        score_value <= _V2_HARD_CONTRACTION_THRESHOLD
        and issuance_z_value <= _V2_ISSUANCE_HARD_THRESHOLD
        and velocity_ratio_value <= _V2_VELOCITY_HARD_THRESHOLD
    )
    if hard_confirmed:
        return "hard_contraction", min(soft_multiplier, _V2_HARD_FLOOR)
    return "soft_contraction", soft_multiplier


def _overlay_state_and_multiplier_exchange_absorption_v1(row: pd.Series) -> tuple[str, float]:
    coverage_ratio = row.get("labeled_coverage_ratio")
    score = row.get("exchange_absorption_score_v1")
    exchange_netflow_ratio = row.get("exchange_netflow_ratio")
    issuance_ratio = row.get("issuance_ratio")
    if pd.isna(score) or pd.isna(coverage_ratio) or float(coverage_ratio) < _FLOW_MIN_COVERAGE_RATIO:
        return "coverage_insufficient", 1.0
    score_value = float(score)
    netflow_value = 0.0 if pd.isna(exchange_netflow_ratio) else float(exchange_netflow_ratio)
    issuance_value = 0.0 if pd.isna(issuance_ratio) else float(issuance_ratio)
    if score_value >= _FLOW_EXPANSION_THRESHOLD and netflow_value > 0.0:
        return "absorption", 1.0
    if score_value <= _FLOW_HARD_DRAIN_THRESHOLD and netflow_value < 0.0 and issuance_value < 0.0:
        return "hard_drain", _FLOW_HARD_DRAIN_MULTIPLIER
    if score_value <= _FLOW_DRAIN_THRESHOLD and netflow_value < 0.0:
        return "drain", _FLOW_DRAIN_MULTIPLIER
    return "neutral", 1.0


def _overlay_state_and_multiplier_whale_stress_v1(row: pd.Series) -> tuple[str, float]:
    coverage_ratio = row.get("labeled_coverage_ratio")
    score = row.get("whale_exchange_stress_score_v1")
    exchange_netflow_ratio = row.get("exchange_netflow_ratio")
    issuance_ratio = row.get("issuance_ratio")
    if pd.isna(score) or pd.isna(coverage_ratio) or float(coverage_ratio) < _FLOW_MIN_COVERAGE_RATIO:
        return "coverage_insufficient", 1.0
    score_value = float(score)
    netflow_value = 0.0 if pd.isna(exchange_netflow_ratio) else float(exchange_netflow_ratio)
    issuance_value = 0.0 if pd.isna(issuance_ratio) else float(issuance_ratio)
    if score_value >= _WHALE_HARD_STRESS_THRESHOLD and netflow_value < 0.0 and issuance_value < 0.0:
        return "hard_stress", _WHALE_HARD_STRESS_MULTIPLIER
    if score_value >= _WHALE_STRESS_THRESHOLD and netflow_value < 0.0:
        return "stress", _WHALE_STRESS_MULTIPLIER
    if score_value >= _WHALE_STRESS_THRESHOLD:
        return "watch", 1.0
    return "open", 1.0


def _panel_row_to_summary(
    row: pd.Series,
    *,
    label_column: str,
    multiplier_column: str,
    score_column: str,
) -> dict[str, Any]:
    return {
        "date_utc": str(row["date_utc"]),
        "decision_date_utc": str(row["decision_date_utc"]),
        "tracked_token_count": int(row["tracked_token_count"]),
        "total_transfer_amount": float(row["total_transfer_amount"]),
        "total_net_issuance_amount": float(row["total_net_issuance_amount"]),
        "issuance_ratio": None if pd.isna(row["issuance_ratio"]) else float(row["issuance_ratio"]),
        "velocity_ratio_7d": None if pd.isna(row["velocity_ratio_7d"]) else float(row["velocity_ratio_7d"]),
        "issuance_ratio_z14": None if pd.isna(row["issuance_ratio_z14"]) else float(row["issuance_ratio_z14"]),
        "velocity_log_z14": None if pd.isna(row["velocity_log_z14"]) else float(row["velocity_log_z14"]),
        "labeled_coverage_ratio": None if pd.isna(row["labeled_coverage_ratio"]) else float(row["labeled_coverage_ratio"]),
        "exchange_netflow_ratio": None if pd.isna(row["exchange_netflow_ratio"]) else float(row["exchange_netflow_ratio"]),
        "whale_to_exchange_ratio": None if pd.isna(row["whale_to_exchange_ratio"]) else float(row["whale_to_exchange_ratio"]),
        "candidate_score": None if pd.isna(row[score_column]) else float(row[score_column]),
        "score_v1": None if pd.isna(row["score_v1"]) else float(row["score_v1"]),
        "regime_label": str(row[label_column]),
        "overlay_multiplier": None if pd.isna(row[multiplier_column]) else float(row[multiplier_column]),
        "signal_ready": bool(row["signal_ready"]),
    }


__all__ = [
    "STABLECOIN_REGIME_CONTRACT_VERSION",
    "DEFAULT_STABLECOIN_OVERLAY_ID",
    "DEFAULT_STABLECOIN_OVERLAY_V2_ID",
    "DEFAULT_STABLECOIN_EXCHANGE_ABSORPTION_OVERLAY_ID",
    "DEFAULT_STABLECOIN_WHALE_STRESS_OVERLAY_ID",
    "load_stablecoin_daily_aggregates",
    "build_stablecoin_regime_panel",
    "compute_stablecoin_issuance_velocity_overlay_v1",
    "compute_stablecoin_issuance_velocity_overlay_v2",
    "compute_stablecoin_exchange_absorption_overlay_v1",
    "compute_stablecoin_whale_to_exchange_stress_overlay_v1",
    "stablecoin_overlay_summary",
    "stablecoin_issuance_velocity_overlay_summary",
]
