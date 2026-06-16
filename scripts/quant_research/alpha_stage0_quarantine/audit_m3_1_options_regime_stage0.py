from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.quant_research import evaluate_v5_h10d_post_pump_short_replacement as v5_eval  # noqa: E402
from enhengclaw.quant_research.coinglass_capability_matrix import (  # noqa: E402
    BASE_URL,
    _http_get_json,
)
from enhengclaw.quant_research.features import xs_alpha_ontology_v5_score  # noqa: E402


CONTRACT_VERSION = "m3_1_options_regime_stage0.v1"
DEFAULT_AS_OF = "2026-05-03"
DEFAULT_REPORT_DIR = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-05-07-m3-1-options-regime-stage0"
)
DEFAULT_PANEL_PATH = ROOT / "artifacts" / "quant_research" / "coinglass" / "options_regime_panel_1d.csv.gz"
OPTION_SYMBOLS = ("BTC", "ETH")
EXCHANGES = ("Binance", "Bybit", "CME", "Deribit", "OKX")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "R-8 M3.1 CoinGlass aggregate-options regime Stage0/data gate. "
            "This builds a market-level panel and tests only parent exposure-conditioning diagnostics."
        )
    )
    parser.add_argument("--as-of", default=DEFAULT_AS_OF)
    parser.add_argument("--target-horizon-bars", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--panel-output-path", type=Path, default=DEFAULT_PANEL_PATH)
    parser.add_argument("--volume-z-threshold", type=float, default=1.5)
    parser.add_argument("--ratio-z-threshold", type=float, default=1.0)
    parser.add_argument("--min-feature-coverage", type=float, default=0.90)
    parser.add_argument("--min-oi-coverage", type=float, default=0.80)
    parser.add_argument("--min-active-date-fraction", type=float, default=0.05)
    parser.add_argument("--max-active-date-fraction", type=float, default=0.40)
    parser.add_argument("--min-conditional-edge", type=float, default=0.005)
    return parser


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _url(path: str, params: dict[str, Any]) -> str:
    return f"{BASE_URL}{path}?{urlencode(params)}"


def _fetch_options_payloads(
    *,
    http_get_json_fn: Callable[[str], Any] = _http_get_json,
) -> dict[str, Any]:
    payloads: dict[str, Any] = {"fetched_at_utc": _now_utc()}
    for symbol in OPTION_SYMBOLS:
        lower = symbol.lower()
        payloads[f"{lower}_option_oi_history"] = http_get_json_fn(
            _url("/option/exchange-oi-history", {"symbol": symbol, "unit": "USD", "range": "1h"})
        )
        payloads[f"{lower}_option_volume_history"] = http_get_json_fn(
            _url("/option/exchange-vol-history", {"symbol": symbol, "unit": "USD", "range": "1d"})
        )
        payloads[f"{lower}_option_max_pain_deribit"] = http_get_json_fn(
            _url("/option/max-pain", {"symbol": symbol, "exchange": "Deribit"})
        )
    payloads["option_vs_futures_oi_ratio"] = http_get_json_fn(
        _url("/index/option-vs-futures-oi-ratio", {"symbol": "BTC"})
    )
    return payloads


def _payload_data(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return None
    if str(payload.get("code")) not in {"0", "None"} and payload.get("code") is not None:
        return None
    return payload.get("data")


def _normalize_exchange(exchange: str) -> str:
    return (
        str(exchange)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "_")
    )


def _date_timestamp_ms(dates: pd.Series) -> pd.Series:
    return pd.to_datetime(dates, utc=True).astype("int64") // 1_000_000


def _exchange_history_payload_to_daily_frame(
    payload: Any,
    *,
    symbol: str,
    metric: str,
) -> pd.DataFrame:
    data = _payload_data(payload)
    if not isinstance(data, dict):
        return pd.DataFrame()

    times = list(data.get("time_list") or [])
    if not times:
        return pd.DataFrame()

    symbol_key = symbol.lower()
    rows = pd.DataFrame({"timestamp_ms": pd.to_numeric(pd.Series(times), errors="coerce")})
    rows = rows.dropna(subset=["timestamp_ms"]).copy()
    rows["timestamp_ms"] = rows["timestamp_ms"].astype("int64")
    rows["date_utc"] = pd.to_datetime(rows["timestamp_ms"], unit="ms", utc=True).dt.normalize()

    price_list = list(data.get("price_list") or [])
    if len(price_list) >= len(rows):
        rows[f"{symbol_key}_option_{metric}_underlying_price"] = pd.to_numeric(
            pd.Series(price_list[: len(rows)]),
            errors="coerce",
        )

    data_map = data.get("data_map") or {}
    exchange_columns: list[str] = []
    if isinstance(data_map, dict):
        for exchange, values in data_map.items():
            if not isinstance(values, list):
                continue
            column = f"{symbol_key}_option_{metric}_usd_{_normalize_exchange(exchange)}"
            rows[column] = pd.to_numeric(pd.Series(values[: len(rows)]), errors="coerce")
            exchange_columns.append(column)

    if exchange_columns:
        rows[f"{symbol_key}_option_{metric}_usd_total"] = rows[exchange_columns].sum(axis=1, min_count=1)

    if rows.empty:
        return rows

    agg: dict[str, str] = {"timestamp_ms": "last"}
    for column in rows.columns:
        if column in {"date_utc", "timestamp_ms"}:
            continue
        if metric == "volume" and column.startswith(f"{symbol_key}_option_{metric}_usd_"):
            agg[column] = "sum"
        else:
            agg[column] = "last"
    daily = rows.groupby("date_utc", as_index=False).agg(agg)
    daily["timestamp_ms"] = _date_timestamp_ms(daily["date_utc"]).astype("int64")
    return daily.sort_values("date_utc").reset_index(drop=True)


def _ratio_payload_to_daily_frame(payload: Any) -> pd.DataFrame:
    data = _payload_data(payload)
    if not isinstance(data, list) or not data:
        return pd.DataFrame()
    frame = pd.DataFrame(data)
    if "timestamp" not in frame.columns:
        return pd.DataFrame()
    frame["timestamp_ms"] = pd.to_numeric(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp_ms"]).copy()
    frame["timestamp_ms"] = frame["timestamp_ms"].astype("int64")
    frame["date_utc"] = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True).dt.normalize()
    rename = {
        "btc_option_vs_futures_radio": "btc_option_vs_futures_oi_ratio",
        "eth_option_vs_futures_radio": "eth_option_vs_futures_oi_ratio",
    }
    frame = frame.rename(columns=rename)
    keep = ["date_utc", "timestamp_ms", *[column for column in rename.values() if column in frame.columns]]
    out = frame[keep].drop_duplicates("date_utc", keep="last").sort_values("date_utc").reset_index(drop=True)
    out["timestamp_ms"] = _date_timestamp_ms(out["date_utc"]).astype("int64")
    for column in rename.values():
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    return out


def _max_pain_summary(payload: Any, *, symbol: str) -> dict[str, Any]:
    data = _payload_data(payload)
    if not isinstance(data, list):
        return {"symbol": symbol, "status": "missing_or_error", "expiry_count": 0}
    prices = [
        pd.to_numeric(item.get("max_pain_price"), errors="coerce")
        for item in data
        if isinstance(item, dict)
    ]
    prices = [float(value) for value in prices if pd.notna(value)]
    expiries = [str(item.get("date")) for item in data if isinstance(item, dict) and item.get("date") is not None]
    return {
        "symbol": symbol,
        "status": "current_snapshot_only",
        "expiry_count": int(len(data)),
        "first_expiry": expiries[0] if expiries else None,
        "last_expiry": expiries[-1] if expiries else None,
        "min_max_pain_price": min(prices) if prices else None,
        "max_max_pain_price": max(prices) if prices else None,
    }


def _merge_daily_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [frame for frame in frames if not frame.empty]
    if not non_empty:
        return pd.DataFrame()
    out = non_empty[0]
    for frame in non_empty[1:]:
        out = out.merge(frame, on=["date_utc", "timestamp_ms"], how="outer")
    return out.sort_values("date_utc").reset_index(drop=True)


def _rolling_z(series: pd.Series, *, window: int = 90, min_periods: int = 30) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    mean = values.rolling(window=window, min_periods=min_periods).mean()
    std = values.rolling(window=window, min_periods=min_periods).std().replace(0.0, np.nan)
    return ((values - mean) / std).replace([np.inf, -np.inf], np.nan)


def _add_regime_features(
    panel: pd.DataFrame,
    *,
    volume_z_threshold: float,
    ratio_z_threshold: float,
) -> pd.DataFrame:
    out = panel.copy()
    for symbol in OPTION_SYMBOLS:
        key = symbol.lower()
        for base in (
            f"{key}_option_volume_usd_total",
            f"{key}_option_oi_usd_total",
            f"{key}_option_vs_futures_oi_ratio",
        ):
            if base in out.columns:
                out[f"{base}_z90"] = _rolling_z(out[base])

    volume_cols = [f"{symbol.lower()}_option_volume_usd_total_z90" for symbol in OPTION_SYMBOLS]
    ratio_cols = [f"{symbol.lower()}_option_vs_futures_oi_ratio_z90" for symbol in OPTION_SYMBOLS]
    volume_cols = [column for column in volume_cols if column in out.columns]
    ratio_cols = [column for column in ratio_cols if column in out.columns]
    out["r8_max_option_volume_z90"] = out[volume_cols].max(axis=1) if volume_cols else np.nan
    out["r8_max_option_vs_futures_ratio_z90"] = out[ratio_cols].max(axis=1) if ratio_cols else np.nan
    out["r8_high_option_volume_shock_flag"] = out["r8_max_option_volume_z90"].ge(float(volume_z_threshold)).fillna(False)
    out["r8_high_option_vs_futures_ratio_flag"] = (
        out["r8_max_option_vs_futures_ratio_z90"].ge(float(ratio_z_threshold)).fillna(False)
    )
    out["r8_any_options_stress_flag"] = (
        out["r8_high_option_volume_shock_flag"] | out["r8_high_option_vs_futures_ratio_flag"]
    )
    return out


def _build_options_panel(
    payloads: dict[str, Any],
    *,
    volume_z_threshold: float,
    ratio_z_threshold: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    frames: list[pd.DataFrame] = []
    max_pain: dict[str, Any] = {}
    endpoint_status: dict[str, Any] = {}
    for symbol in OPTION_SYMBOLS:
        key = symbol.lower()
        for metric, payload_key in (
            ("oi", f"{key}_option_oi_history"),
            ("volume", f"{key}_option_volume_history"),
        ):
            payload = payloads.get(payload_key)
            frame = _exchange_history_payload_to_daily_frame(payload, symbol=symbol, metric=metric)
            frames.append(frame)
            endpoint_status[payload_key] = {
                "panel_rows": int(len(frame)),
                "first_date": str(frame["date_utc"].min().date()) if not frame.empty else None,
                "last_date": str(frame["date_utc"].max().date()) if not frame.empty else None,
            }
        max_payload_key = f"{key}_option_max_pain_deribit"
        max_pain[key] = _max_pain_summary(payloads.get(max_payload_key), symbol=symbol)
        endpoint_status[max_payload_key] = max_pain[key]

    ratio = _ratio_payload_to_daily_frame(payloads.get("option_vs_futures_oi_ratio"))
    frames.append(ratio)
    endpoint_status["option_vs_futures_oi_ratio"] = {
        "panel_rows": int(len(ratio)),
        "first_date": str(ratio["date_utc"].min().date()) if not ratio.empty else None,
        "last_date": str(ratio["date_utc"].max().date()) if not ratio.empty else None,
    }

    panel = _merge_daily_frames(frames)
    if not panel.empty:
        panel = _add_regime_features(
            panel,
            volume_z_threshold=volume_z_threshold,
            ratio_z_threshold=ratio_z_threshold,
        )
    meta = {
        "endpoint_status": endpoint_status,
        "max_pain": max_pain,
    }
    return panel, meta


def _safe_mean(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return None
    return float(values.mean())


def _coverage(series: pd.Series) -> float:
    return float(series.notna().mean()) if len(series) else 0.0


def _load_parent_short_rows(*, as_of: str, target_horizon_bars: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    features_artifact = v5_eval.base_eval._features_artifact_path(as_of)
    frame = v5_eval.base_eval._build_risk_frame(
        features_artifact,
        target_horizon_bars=target_horizon_bars,
    )
    frame = frame.copy()
    frame["parent_score"] = xs_alpha_ontology_v5_score(frame)
    rows: list[dict[str, Any]] = []
    keep = [
        "timestamp_ms",
        "date_utc",
        "subject",
        "liquidity_bucket",
        "parent_score",
        "forward_1d_log_return",
        f"forward_{target_horizon_bars}d_log_return",
    ]
    keep = [column for column in keep if column in frame.columns]
    for _timestamp, group in frame.groupby("timestamp_ms", sort=False):
        shorts = group.sort_values("parent_score", ascending=True).head(min(3, len(group)))
        rows.extend(shorts[keep].to_dict("records"))
    out = pd.DataFrame(rows)
    if not out.empty:
        out["date_utc"] = pd.to_datetime(out["date_utc"], utc=True).dt.normalize()
    meta = {
        "features_artifact": str(features_artifact),
        "risk_frame_rows": int(len(frame)),
        "risk_frame_subjects": int(frame["subject"].astype(str).nunique()) if "subject" in frame.columns else None,
        "parent_short_rows": int(len(out)),
        "parent_short_dates": int(out["date_utc"].nunique()) if not out.empty else 0,
    }
    return out, meta


def _split_edge(date_level: pd.DataFrame, flag_column: str, horizon_col: str) -> dict[str, Any]:
    if date_level.empty:
        return {"status": "empty"}
    dates = sorted(date_level["date_utc"].unique())
    split = int(len(dates) * 0.70)
    split = min(max(split, 1), max(len(dates) - 1, 1))
    train_dates = set(dates[:split])
    test_dates = set(dates[split:])

    def _edge(local: pd.DataFrame) -> dict[str, Any]:
        active = local[local[flag_column]]
        inactive = local[~local[flag_column]]
        if active.empty or inactive.empty:
            return {
                "active_date_count": int(len(active)),
                "inactive_date_count": int(len(inactive)),
                "veto_short_edge": None,
            }
        active_mean = _safe_mean(active, horizon_col)
        inactive_mean = _safe_mean(inactive, horizon_col)
        edge = None if active_mean is None or inactive_mean is None else active_mean - inactive_mean
        return {
            "active_date_count": int(len(active)),
            "inactive_date_count": int(len(inactive)),
            "active_next_h_mean": active_mean,
            "inactive_next_h_mean": inactive_mean,
            "veto_short_edge": edge,
        }

    return {
        "train": _edge(date_level[date_level["date_utc"].isin(train_dates)]),
        "test": _edge(date_level[date_level["date_utc"].isin(test_dates)]),
    }


def _diagnose_parent_conditionals(
    *,
    parent_short_rows: pd.DataFrame,
    panel: pd.DataFrame,
    target_horizon_bars: int,
    min_active_date_fraction: float,
    max_active_date_fraction: float,
    min_conditional_edge: float,
) -> dict[str, Any]:
    if parent_short_rows.empty or panel.empty:
        return {"status": "empty_inputs", "variants": []}
    horizon_col = f"forward_{target_horizon_bars}d_log_return"
    merge_cols = [
        "date_utc",
        "r8_high_option_volume_shock_flag",
        "r8_high_option_vs_futures_ratio_flag",
        "r8_any_options_stress_flag",
        "btc_option_volume_usd_total",
        "eth_option_volume_usd_total",
        "btc_option_vs_futures_oi_ratio",
        "eth_option_vs_futures_oi_ratio",
        "btc_option_oi_usd_total",
        "eth_option_oi_usd_total",
    ]
    merge_cols = [column for column in merge_cols if column in panel.columns]
    aligned = parent_short_rows.merge(panel[merge_cols], on="date_utc", how="left")
    flag_columns = [
        "r8_high_option_volume_shock_flag",
        "r8_high_option_vs_futures_ratio_flag",
        "r8_any_options_stress_flag",
    ]
    variants: list[dict[str, Any]] = []
    for flag in flag_columns:
        if flag not in aligned.columns:
            continue
        local = aligned.dropna(subset=[horizon_col]).copy()
        local[flag] = local[flag].fillna(False).astype(bool)
        date_level = (
            local.groupby("date_utc", as_index=False)
            .agg({horizon_col: "mean", "forward_1d_log_return": "mean", flag: "max"})
            .sort_values("date_utc")
        )
        active = date_level[date_level[flag]]
        inactive = date_level[~date_level[flag]]
        active_mean = _safe_mean(active, horizon_col)
        inactive_mean = _safe_mean(inactive, horizon_col)
        edge = None if active_mean is None or inactive_mean is None else active_mean - inactive_mean
        activation = float(date_level[flag].mean()) if len(date_level) else 0.0
        split = _split_edge(date_level, flag, horizon_col)
        train_edge = split.get("train", {}).get("veto_short_edge")
        test_edge = split.get("test", {}).get("veto_short_edge")
        pass_orientation = None
        if (
            edge is not None
            and train_edge is not None
            and test_edge is not None
            and min_active_date_fraction <= activation <= max_active_date_fraction
        ):
            if (
                edge >= min_conditional_edge
                and train_edge >= min_conditional_edge
                and test_edge >= min_conditional_edge
            ):
                pass_orientation = "veto_short_when_active"
            elif (
                edge <= -min_conditional_edge
                and train_edge <= -min_conditional_edge
                and test_edge <= -min_conditional_edge
            ):
                pass_orientation = "confirm_short_when_active"
        variants.append(
            {
                "label": flag,
                "date_count": int(len(date_level)),
                "active_date_count": int(len(active)),
                "inactive_date_count": int(len(inactive)),
                "active_date_fraction": activation,
                "active_next_h_mean": active_mean,
                "inactive_next_h_mean": inactive_mean,
                "veto_short_edge_active_minus_inactive": edge,
                "split_edges": split,
                "stage0_pass": pass_orientation is not None,
                "pass_orientation": pass_orientation,
            }
        )
    return {
        "status": "ok",
        "aligned_parent_short_rows": int(len(aligned)),
        "aligned_parent_short_dates": int(aligned["date_utc"].nunique()),
        "variants": variants,
    }


def _panel_summary(panel: pd.DataFrame, *, parent_dates: pd.Series | None = None) -> dict[str, Any]:
    if panel.empty:
        return {"row_count": 0}
    out: dict[str, Any] = {
        "row_count": int(len(panel)),
        "first_date": str(panel["date_utc"].min().date()),
        "last_date": str(panel["date_utc"].max().date()),
    }
    for column in (
        "btc_option_volume_usd_total",
        "eth_option_volume_usd_total",
        "btc_option_vs_futures_oi_ratio",
        "eth_option_vs_futures_oi_ratio",
        "btc_option_oi_usd_total",
        "eth_option_oi_usd_total",
    ):
        if column in panel.columns:
            out[f"{column}_coverage"] = _coverage(panel[column])
    if parent_dates is not None and len(parent_dates):
        parent_date_frame = pd.DataFrame({"date_utc": pd.to_datetime(parent_dates, utc=True).dt.normalize().unique()})
        aligned = parent_date_frame.merge(panel, on="date_utc", how="left")
        out["parent_date_count"] = int(len(aligned))
        for column in (
            "btc_option_volume_usd_total",
            "eth_option_volume_usd_total",
            "btc_option_vs_futures_oi_ratio",
            "eth_option_vs_futures_oi_ratio",
            "btc_option_oi_usd_total",
            "eth_option_oi_usd_total",
        ):
            if column in aligned.columns:
                out[f"parent_{column}_coverage"] = _coverage(aligned[column])
    for flag in (
        "r8_high_option_volume_shock_flag",
        "r8_high_option_vs_futures_ratio_flag",
        "r8_any_options_stress_flag",
    ):
        if flag in panel.columns:
            out[f"{flag}_fraction"] = float(panel[flag].fillna(False).astype(bool).mean())
    return out


def _decision(
    *,
    panel_summary: dict[str, Any],
    conditionals: dict[str, Any],
    min_feature_coverage: float,
    min_oi_coverage: float,
) -> dict[str, Any]:
    blockers: list[str] = []
    for column in (
        "btc_option_volume_usd_total",
        "eth_option_volume_usd_total",
        "btc_option_vs_futures_oi_ratio",
        "eth_option_vs_futures_oi_ratio",
    ):
        coverage = float(panel_summary.get(f"parent_{column}_coverage") or 0.0)
        if coverage < min_feature_coverage:
            blockers.append(f"{column}_parent_coverage_below_threshold")
    for column in ("btc_option_oi_usd_total", "eth_option_oi_usd_total"):
        coverage = float(panel_summary.get(f"parent_{column}_coverage") or 0.0)
        if coverage < min_oi_coverage:
            blockers.append(f"{column}_history_not_backfilled")

    variants = list(conditionals.get("variants") or [])
    kept = [variant for variant in variants if variant.get("stage0_pass")]
    if not kept:
        blockers.append("no_stable_parent_conditioning_edge")

    # R-8 aggregate options are market-level states. They can only become an exposure
    # gate after separate falsification; they cannot directly promote as a rank factor.
    blockers.append("market_level_only_not_cross_sectional_rank_factor")
    blockers.append("max_pain_current_snapshot_not_pit_history")

    return {
        "stage0_status": (
            "stage0_quarantined_market_gate_candidate_no_manifest" if kept else "stage0_no_kept_variants"
        ),
        "alpha_rerun_allowed": False,
        "manifest_ab_allowed": False,
        "kept_variant_count": int(len(kept)),
        "kept_variants": [str(variant.get("label")) for variant in kept],
        "blocker_codes": blockers,
        "next_action": (
            "Keep the CoinGlass options panel as a data sidecar. Do not open h10d manifest A/B until "
            "option OI/max-pain have PIT history and a pre-registered exposure gate survives train/test falsification."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    panel_path = args.panel_output_path.resolve()
    panel_path.parent.mkdir(parents=True, exist_ok=True)

    payloads = _fetch_options_payloads()
    panel, options_meta = _build_options_panel(
        payloads,
        volume_z_threshold=args.volume_z_threshold,
        ratio_z_threshold=args.ratio_z_threshold,
    )
    if not panel.empty:
        panel_to_write = panel.copy()
        panel_to_write["date_utc"] = pd.to_datetime(panel_to_write["date_utc"], utc=True).dt.strftime("%Y-%m-%d")
        panel_to_write.to_csv(panel_path, index=False, compression="gzip")

    parent_short_rows, parent_meta = _load_parent_short_rows(
        as_of=args.as_of,
        target_horizon_bars=args.target_horizon_bars,
    )
    summary = _panel_summary(panel, parent_dates=parent_short_rows.get("date_utc"))
    conditionals = _diagnose_parent_conditionals(
        parent_short_rows=parent_short_rows,
        panel=panel,
        target_horizon_bars=args.target_horizon_bars,
        min_active_date_fraction=args.min_active_date_fraction,
        max_active_date_fraction=args.max_active_date_fraction,
        min_conditional_edge=args.min_conditional_edge,
    )
    decision = _decision(
        panel_summary=summary,
        conditionals=conditionals,
        min_feature_coverage=args.min_feature_coverage,
        min_oi_coverage=args.min_oi_coverage,
    )

    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": _now_utc(),
        "as_of": args.as_of,
        "canonical_parent": "v5_rw_bridge_no_overlay_h10d",
        "question": "Can CoinGlass aggregate options data support an immediate M3.1 options-regime alpha gate?",
        "panel_output_path": str(panel_path),
        "options_meta": options_meta,
        "panel_summary": summary,
        "parent_meta": parent_meta,
        "conditional_parent_short_diagnostics": conditionals,
        "decision": decision,
        "thresholds": {
            "volume_z_threshold": float(args.volume_z_threshold),
            "ratio_z_threshold": float(args.ratio_z_threshold),
            "min_feature_coverage": float(args.min_feature_coverage),
            "min_oi_coverage": float(args.min_oi_coverage),
            "min_active_date_fraction": float(args.min_active_date_fraction),
            "max_active_date_fraction": float(args.max_active_date_fraction),
            "min_conditional_edge": float(args.min_conditional_edge),
        },
        "source_boundary": (
            "CoinGlass aggregate option OI/volume/ratio/max-pain endpoints are provider sidecars. "
            "This report does not treat provider-computed market-level aggregates as a cross-sectional alpha."
        ),
    }
    report_path = output_dir / "m3_1_options_regime_stage0.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")

    print(json.dumps({"report_path": str(report_path), "decision": decision}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
