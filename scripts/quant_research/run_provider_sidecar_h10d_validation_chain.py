from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
BASE_URL = "https://open-api-v4.coinglass.com/api"
DEFAULT_OUT_ROOT = ROOT / "artifacts" / "quant_research" / "provider_sidecar_h10d" / "validation_chain_20260518"
DEFAULT_DOC_PATH = (
    ROOT
    / "docs"
    / "quant_research"
    / "03_alpha_branches"
    / "provider_sidecar_h10d_validation_chain_2026_05_18.md"
)
HV_ROOT = ROOT / "artifacts" / "qr" / "hv_balanced"
COINGLASS_PANEL_ROOT = ROOT / "artifacts" / "quant_research" / "coinglass"
LIVE_CONFIG_PATH = ROOT / "config" / "live_trading" / "hv_balanced_binance_usdm_live_pilot.yaml"

LIVE_ENDPOINTS = (
    {
        "endpoint_id": "futures_open_interest_history_usd",
        "family": "funding_oi",
        "path": "/futures/open-interest/history",
        "params": {"exchange": "Binance", "interval": "1h", "unit": "usd", "limit": 5},
    },
    {
        "endpoint_id": "futures_funding_rate_history",
        "family": "funding_oi",
        "path": "/futures/funding-rate/history",
        "params": {"exchange": "Binance", "interval": "1h", "limit": 5},
    },
    {
        "endpoint_id": "futures_taker_buy_sell_volume",
        "family": "taker_flow",
        "path": "/futures/v2/taker-buy-sell-volume/history",
        "params": {"exchange": "Binance", "interval": "1h", "limit": 5},
    },
    {
        "endpoint_id": "futures_liquidation_history",
        "family": "liquidation",
        "path": "/futures/liquidation/history",
        "params": {"exchange": "Binance", "interval": "1h", "limit": 5},
    },
    {
        "endpoint_id": "futures_orderbook_ask_bids_history",
        "family": "orderbook",
        "path": "/futures/orderbook/ask-bids-history",
        "params": {"exchange": "Binance", "interval": "1h", "limit": 5},
    },
    {
        "endpoint_id": "futures_global_long_short_account_ratio",
        "family": "participant",
        "path": "/futures/global-long-short-account-ratio/history",
        "params": {"exchange": "Binance", "interval": "1h", "limit": 5},
    },
    {
        "endpoint_id": "futures_top_long_short_position_ratio",
        "family": "participant",
        "path": "/futures/top-long-short-position-ratio/history",
        "params": {"exchange": "Binance", "interval": "1h", "limit": 5},
    },
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run provider_sidecar_h10d live shadow and overlap-only validation chain."
    )
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC_PATH)
    parser.add_argument("--skip-live-shadow", action="store_true")
    parser.add_argument("--request-sleep-seconds", type=float, default=0.12)
    parser.add_argument("--request-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--symbol-limit", type=int, default=20)
    parser.add_argument("--overlay-short-multiplier", type=float, default=0.75)
    parser.add_argument("--overlay-veto-score-threshold", type=int, default=3)
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def resolve_coinglass_api_key() -> str:
    for name in ("CoinglassAPI", "COINGLASS_API_KEY", "COINGLASSAPI"):
        value = str(os.environ.get(name) or "").strip()
        if value:
            return value
    if os.name != "nt":
        return ""
    try:
        import winreg
    except ImportError:
        return ""
    for name in ("CoinglassAPI", "COINGLASS_API_KEY", "COINGLASSAPI"):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _ = winreg.QueryValueEx(key, name)
        except OSError:
            continue
        value = str(value or "").strip()
        if value:
            return value
    return ""


def read_live_symbols() -> list[str]:
    text = LIVE_CONFIG_PATH.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip().startswith("symbols:"):
            _, raw = line.split(":", 1)
            return [item.strip().strip("'\"") for item in raw.split(",") if item.strip()]
    raise RuntimeError(f"symbols line not found in {LIVE_CONFIG_PATH}")


def request_url(endpoint: dict[str, Any], symbol: str) -> str:
    params = dict(endpoint["params"])
    params["symbol"] = symbol
    return f"{BASE_URL}{endpoint['path']}?{urlencode(params)}"


def parse_payload_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return [dict(item) for item in data if isinstance(item, dict)]
    return []


def parse_time_ms(value: Any) -> int | None:
    try:
        numeric = int(float(value))
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    if numeric < 10_000_000_000:
        numeric *= 1000
    return numeric


def latest_provider_time_utc(rows: list[dict[str, Any]]) -> str | None:
    times = [parse_time_ms(row.get("time")) for row in rows]
    times = [item for item in times if item is not None]
    if not times:
        return None
    return iso_z(datetime.fromtimestamp(max(times) / 1000, tz=UTC))


def run_live_shadow(
    *,
    symbols: list[str],
    out_root: Path,
    timeout_seconds: float,
    request_sleep_seconds: float,
) -> dict[str, Any]:
    api_key = resolve_coinglass_api_key()
    shadow_path = out_root / "live_shadow_available_at.jsonl"
    rows: list[dict[str, Any]] = []
    if not api_key:
        summary = {
            "status": "blocked",
            "reason": "CoinglassAPI key missing",
            "available_at_recorded": False,
            "shadow_path": str(shadow_path),
        }
        write_json(out_root / "live_shadow_summary.json", summary)
        return summary

    for symbol in symbols:
        for endpoint in LIVE_ENDPOINTS:
            requested_at = utc_now()
            url = request_url(endpoint, symbol)
            record: dict[str, Any] = {
                "schema": "provider_sidecar_h10d_live_shadow_available_at.v1",
                "provider": "coinglass",
                "symbol": symbol,
                "endpoint_id": endpoint["endpoint_id"],
                "family": endpoint["family"],
                "requested_at_utc": iso_z(requested_at),
                "available_at_utc": None,
                "latency_ms": None,
                "status": "error",
                "row_count": 0,
                "latest_provider_time_utc": None,
                "error": None,
            }
            try:
                request = Request(url, headers={"CG-API-KEY": api_key, "Accept": "application/json"})
                with urlopen(request, timeout=timeout_seconds) as response:
                    body = response.read().decode("utf-8")
                received_at = utc_now()
                payload = json.loads(body)
                payload_rows = parse_payload_rows(payload)
                code = str(payload.get("code", "0")) if isinstance(payload, dict) else "invalid"
                ok = code in {"0", "200", "success"} or bool(payload_rows)
                record.update(
                    {
                        "available_at_utc": iso_z(received_at),
                        "latency_ms": round((received_at - requested_at).total_seconds() * 1000.0, 3),
                        "status": "success" if ok else "provider_error",
                        "row_count": len(payload_rows),
                        "latest_provider_time_utc": latest_provider_time_utc(payload_rows),
                        "error": None if ok else f"provider_code={code}",
                    }
                )
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                received_at = utc_now()
                record.update(
                    {
                        "available_at_utc": iso_z(received_at),
                        "latency_ms": round((received_at - requested_at).total_seconds() * 1000.0, 3),
                        "status": "error",
                        "error": str(exc),
                    }
                )
            rows.append(record)
            if request_sleep_seconds > 0:
                time.sleep(request_sleep_seconds)

    append_jsonl(shadow_path, rows)
    latencies = [
        float(row["latency_ms"])
        for row in rows
        if row["status"] == "success" and row.get("latency_ms") is not None
    ]
    errors = [row for row in rows if row["status"] != "success"]
    symbol_success = {
        symbol: all(
            row["status"] == "success"
            for row in rows
            if row["symbol"] == symbol
        )
        for symbol in symbols
    }
    summary = {
        "status": "ok" if not errors else "degraded",
        "schema": "provider_sidecar_h10d_live_shadow_summary.v1",
        "provider": "coinglass",
        "generated_at_utc": iso_z(utc_now()),
        "shadow_path": str(shadow_path),
        "requested_symbol_count": len(symbols),
        "endpoint_count": len(LIVE_ENDPOINTS),
        "request_count": len(rows),
        "success_count": len(rows) - len(errors),
        "error_count": len(errors),
        "available_at_recorded": all(bool(row.get("available_at_utc")) for row in rows),
        "latency_ms_median": median(latencies) if latencies else None,
        "latency_ms_p95": percentile(latencies, 0.95) if latencies else None,
        "latency_ms_max": max(latencies) if latencies else None,
        "all_live_symbols_all_endpoints_success": all(symbol_success.values()) if symbol_success else False,
        "symbol_success": symbol_success,
        "errors": errors[:20],
    }
    write_json(out_root / "live_shadow_summary.json", summary)
    return summary


def percentile(values: list[float], q: float) -> float | None:
    clean = sorted(value for value in values if math.isfinite(value))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * q
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return clean[lower]
    return clean[lower] + (clean[upper] - clean[lower]) * (position - lower)


def ms_to_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, unit="ms", utc=True).dt.strftime("%Y-%m-%d")


def date_plus_one(series: pd.Series) -> pd.Series:
    return (pd.to_datetime(series, utc=True) + pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d")


def normalize_date(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "date_utc" in out.columns:
        out["date_utc"] = pd.to_datetime(out["date_utc"], utc=True).dt.strftime("%Y-%m-%d")
    elif "open_time_ms" in out.columns:
        out["date_utc"] = ms_to_date(out["open_time_ms"])
    else:
        raise RuntimeError("missing date_utc/open_time_ms")
    return out


def local_market_history_root() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "EnhengClaw" / "market_history"
    return Path.home() / ".local" / "share" / "EnhengClaw" / "market_history"


def read_derivatives_1d(symbols: Iterable[str]) -> pd.DataFrame:
    root = local_market_history_root() / "binance_derivatives"
    usecols = ["symbol", "open_time_ms", "funding_rate", "open_interest", "open_interest_value"]
    frames = []
    for symbol in sorted(set(symbols)):
        symbol_root = root / symbol / "1d"
        if not symbol_root.exists():
            continue
        for file_path in sorted(symbol_root.glob("*.csv.gz")):
            with gzip.open(file_path, "rt", encoding="utf-8") as handle:
                frame = pd.read_csv(handle, usecols=lambda col: col in usecols)
            if not frame.empty:
                frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["symbol", "date_utc", *usecols[2:]])
    return normalize_date(pd.concat(frames, ignore_index=True))


def rolling_q80(series: pd.Series) -> pd.Series:
    return series.shift(1).rolling(90, min_periods=30).quantile(0.80)


def build_sidecar_feature_panel(symbols: Iterable[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    micro = normalize_date(pd.read_csv(COINGLASS_PANEL_ROOT / "microstructure_panel_1d.csv.gz"))
    participant = normalize_date(pd.read_csv(COINGLASS_PANEL_ROOT / "participant_panel_1d.csv.gz"))
    derivatives = read_derivatives_1d(symbols)
    keep_micro = [
        "symbol",
        "date_utc",
        "long_liquidation_usd",
        "short_liquidation_usd",
        "orderbook_bids_usd",
        "orderbook_asks_usd",
        "taker_buy_volume_usd",
        "taker_sell_volume_usd",
    ]
    keep_participant = [
        "symbol",
        "date_utc",
        "global_account_long_pct",
        "top_trader_long_pct",
    ]
    keep_derivatives = [
        "symbol",
        "date_utc",
        "funding_rate",
        "open_interest_value",
    ]
    panel = micro[[col for col in keep_micro if col in micro.columns]].merge(
        participant[[col for col in keep_participant if col in participant.columns]],
        on=["symbol", "date_utc"],
        how="outer",
    )
    panel = panel.merge(
        derivatives[[col for col in keep_derivatives if col in derivatives.columns]],
        on=["symbol", "date_utc"],
        how="outer",
    )
    panel = panel[panel["symbol"].isin(set(symbols))].copy()
    numeric_cols = [col for col in panel.columns if col not in {"symbol", "date_utc"}]
    for col in numeric_cols:
        panel[col] = pd.to_numeric(panel[col], errors="coerce")
    eps = 1e-12
    panel["taker_imbalance"] = (
        panel["taker_buy_volume_usd"] - panel["taker_sell_volume_usd"]
    ) / (panel["taker_buy_volume_usd"] + panel["taker_sell_volume_usd"] + eps)
    panel["orderbook_bid_imbalance"] = (
        panel["orderbook_bids_usd"] - panel["orderbook_asks_usd"]
    ) / (panel["orderbook_bids_usd"] + panel["orderbook_asks_usd"] + eps)
    panel["short_liq_pressure"] = panel["short_liquidation_usd"] / (
        panel["long_liquidation_usd"] + panel["short_liquidation_usd"] + eps
    )
    panel = panel.sort_values(["symbol", "date_utc"]).reset_index(drop=True)
    panel["oi_change_5d"] = panel.groupby("symbol")["open_interest_value"].pct_change(5)
    signal_cols = [
        "top_trader_long_pct",
        "global_account_long_pct",
        "taker_imbalance",
        "funding_rate",
        "oi_change_5d",
        "orderbook_bid_imbalance",
        "short_liq_pressure",
    ]
    for col in signal_cols:
        panel[f"{col}_q80_lagged"] = panel.groupby("symbol", group_keys=False)[col].apply(rolling_q80)
    required_signal_cols = signal_cols + [f"{col}_q80_lagged" for col in signal_cols]
    panel["provider_core_available"] = panel[required_signal_cols].notna().all(axis=1)
    panel["flag_top_trader_crowded_long"] = (
        panel["top_trader_long_pct"].gt(panel["top_trader_long_pct_q80_lagged"])
        & panel["top_trader_long_pct"].gt(0.55)
    )
    panel["flag_global_crowded_long"] = (
        panel["global_account_long_pct"].gt(panel["global_account_long_pct_q80_lagged"])
        & panel["global_account_long_pct"].gt(0.55)
    )
    panel["flag_taker_buy_pressure"] = (
        panel["taker_imbalance"].gt(panel["taker_imbalance_q80_lagged"])
        & panel["taker_imbalance"].gt(0.0)
    )
    panel["flag_funding_high"] = (
        panel["funding_rate"].gt(panel["funding_rate_q80_lagged"])
        & panel["funding_rate"].gt(0.0)
    )
    panel["flag_oi_rising"] = (
        panel["oi_change_5d"].gt(panel["oi_change_5d_q80_lagged"])
        & panel["oi_change_5d"].gt(0.0)
    )
    panel["flag_bid_support"] = (
        panel["orderbook_bid_imbalance"].gt(panel["orderbook_bid_imbalance_q80_lagged"])
        & panel["orderbook_bid_imbalance"].gt(0.0)
    )
    panel["flag_short_liq_pressure"] = (
        panel["short_liq_pressure"].gt(panel["short_liq_pressure_q80_lagged"])
        & panel["short_liq_pressure"].gt(0.50)
    )
    flag_cols = [col for col in panel.columns if col.startswith("flag_")]
    panel["provider_veto_score"] = panel[flag_cols].sum(axis=1)
    panel["provider_feature_date_utc"] = panel["date_utc"]
    panel["decision_date_utc"] = date_plus_one(panel["date_utc"])
    meta = {
        "symbols": sorted(set(symbols)),
        "symbol_count": int(panel["symbol"].nunique()),
        "row_count": int(len(panel)),
        "first_feature_date_utc": str(panel["provider_feature_date_utc"].min()) if not panel.empty else None,
        "last_feature_date_utc": str(panel["provider_feature_date_utc"].max()) if not panel.empty else None,
        "lag_policy": "provider daily sidecar date D is available to decision date D+1 only",
        "flag_columns": flag_cols,
    }
    return panel, meta


def max_drawdown(returns: pd.Series) -> float:
    equity = (1.0 + returns.fillna(0.0)).cumprod()
    peak = equity.cummax()
    drawdown = equity / peak - 1.0
    return float(-drawdown.min()) if len(drawdown) else 0.0


def metrics(returns: pd.Series, *, annualization_period_days: float = 10.0) -> dict[str, Any]:
    clean = pd.to_numeric(returns, errors="coerce").fillna(0.0)
    if clean.empty:
        return {
            "period_count": 0,
            "net_return": 0.0,
            "mean_period_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
        }
    std = float(clean.std(ddof=1)) if len(clean) > 1 else 0.0
    annualizer = math.sqrt(365.0 / annualization_period_days)
    return {
        "period_count": int(len(clean)),
        "net_return": float((1.0 + clean).prod() - 1.0),
        "mean_period_return": float(clean.mean()),
        "sharpe": float(clean.mean() / std * annualizer) if std > 0 else 0.0,
        "max_drawdown": max_drawdown(clean),
        "win_rate": float(clean.gt(0.0).mean()),
    }


def run_overlap_backtest(
    *,
    out_root: Path,
    overlay_short_multiplier: float,
    veto_score_threshold: int,
) -> dict[str, Any]:
    periods = pd.read_csv(HV_ROOT / "aligned_period_returns.csv")
    periods["period_date_utc"] = ms_to_date(periods["timestamp_ms"])
    positions = pd.read_csv(HV_ROOT / "position_attribution.csv")
    positions["decision_date_utc"] = ms_to_date(positions["decision_timestamp_ms"])
    positions["period_date_utc"] = ms_to_date(positions["fill_timestamp_ms"])
    symbols = sorted(positions["usdm_symbol"].dropna().astype(str).unique())
    panel, panel_meta = build_sidecar_feature_panel(symbols)
    feature_cols = [
        "symbol",
        "decision_date_utc",
        "provider_feature_date_utc",
        "provider_veto_score",
        "flag_top_trader_crowded_long",
        "flag_global_crowded_long",
        "flag_taker_buy_pressure",
        "flag_funding_high",
        "flag_oi_rising",
        "flag_bid_support",
        "flag_short_liq_pressure",
        "provider_core_available",
    ]
    merged = positions.merge(
        panel[feature_cols].rename(columns={"symbol": "usdm_symbol"}),
        on=["usdm_symbol", "decision_date_utc"],
        how="left",
    )
    merged["provider_veto_score"] = pd.to_numeric(merged["provider_veto_score"], errors="coerce")
    merged["provider_sidecar_available"] = merged["provider_core_available"].apply(
        lambda value: bool(value) if pd.notna(value) else False
    )
    merged["overlay_trigger"] = (
        merged["side"].astype(str).eq("short")
        & merged["provider_sidecar_available"]
        & merged["provider_veto_score"].ge(veto_score_threshold)
    )
    merged["overlay_multiplier"] = 1.0
    merged.loc[merged["overlay_trigger"], "overlay_multiplier"] = float(overlay_short_multiplier)
    merged["base_position_contribution"] = pd.to_numeric(
        merged["net_before_trade_cost_contribution"], errors="coerce"
    ).fillna(0.0)
    merged["overlay_position_contribution"] = (
        merged["base_position_contribution"] * merged["overlay_multiplier"]
    )
    period_delta = (
        merged.groupby("period_date_utc", as_index=False)
        .agg(
            decision_date_utc=("decision_date_utc", "first"),
            base_position_contribution=("base_position_contribution", "sum"),
            overlay_position_contribution=("overlay_position_contribution", "sum"),
            overlay_trigger_count=("overlay_trigger", "sum"),
            short_position_count=("side", lambda s: int((s.astype(str) == "short").sum())),
            provider_available_position_count=("provider_sidecar_available", "sum"),
            position_count=("usdm_symbol", "count"),
        )
    )
    period_delta["overlay_delta_return"] = (
        period_delta["overlay_position_contribution"] - period_delta["base_position_contribution"]
    )
    period_delta["coverage_ratio"] = (
        period_delta["provider_available_position_count"] / period_delta["position_count"].replace(0, pd.NA)
    ).fillna(0.0)
    overlap_periods = period_delta[period_delta["provider_available_position_count"].gt(0)]
    first_period = str(overlap_periods["period_date_utc"].min())
    last_period = str(overlap_periods["period_date_utc"].max())
    paired = periods[
        (periods["period_date_utc"] >= first_period)
        & (periods["period_date_utc"] <= last_period)
    ].copy()
    paired = paired.merge(period_delta, on="period_date_utc", how="left")
    for col in [
        "base_position_contribution",
        "overlay_position_contribution",
        "overlay_delta_return",
        "overlay_trigger_count",
        "short_position_count",
        "provider_available_position_count",
        "position_count",
        "coverage_ratio",
    ]:
        paired[col] = pd.to_numeric(paired[col], errors="coerce").fillna(0.0)
    paired = paired[paired["position_count"].gt(0)].copy()
    paired["base_period_return"] = pd.to_numeric(paired["net_period_return"], errors="coerce").fillna(0.0)
    paired["overlay_period_return"] = paired["base_period_return"] + paired["overlay_delta_return"]
    paired["period_delta_return"] = paired["overlay_period_return"] - paired["base_period_return"]
    paired["base_equity"] = (1.0 + paired["base_period_return"]).cumprod()
    paired["overlay_equity"] = (1.0 + paired["overlay_period_return"]).cumprod()
    delta = paired["period_delta_return"]
    delta_std = float(delta.std(ddof=1)) if len(delta) > 1 else 0.0
    paired_summary = {
        "schema": "provider_sidecar_h10d_overlap_paired_comparison.v1",
        "generated_at_utc": iso_z(utc_now()),
        "overlay_name": "coinglass_short_brake_small",
        "overlay_type": "risk_overlay_only",
        "alpha_score_changed": False,
        "live_config_changed": False,
        "overlay_short_multiplier": float(overlay_short_multiplier),
        "veto_score_threshold": int(veto_score_threshold),
        "pit_lag_policy": panel_meta["lag_policy"],
        "panel_meta": panel_meta,
        "base_metrics": metrics(paired["base_period_return"]),
        "overlay_metrics": metrics(paired["overlay_period_return"]),
        "paired_delta": {
            "period_count": int(len(paired)),
            "mean_delta_return": float(delta.mean()) if len(delta) else 0.0,
            "sum_delta_return": float(delta.sum()) if len(delta) else 0.0,
            "positive_delta_share": float(delta.gt(0).mean()) if len(delta) else 0.0,
            "worst_period_delta": float(delta.min()) if len(delta) else 0.0,
            "t_stat": float(delta.mean() / (delta_std / math.sqrt(len(delta)))) if delta_std > 0 and len(delta) else 0.0,
        },
        "overlay_trigger_count": int(paired["overlay_trigger_count"].sum()),
        "overlay_trigger_period_count": int(paired["overlay_trigger_count"].gt(0).sum()),
        "short_position_count": int(paired["short_position_count"].sum()),
        "provider_available_position_count": int(paired["provider_available_position_count"].sum()),
        "position_count": int(paired["position_count"].sum()),
    }
    base_m = paired_summary["base_metrics"]
    overlay_m = paired_summary["overlay_metrics"]
    paired_summary["diagnostic_gates"] = {
        "coverage_ratio_min_95pct": bool((paired["coverage_ratio"] >= 0.95).mean() >= 0.95),
        "max_drawdown_not_worse": bool(overlay_m["max_drawdown"] <= base_m["max_drawdown"]),
        "net_return_drawdown_tradeoff_not_catastrophic": bool(
            overlay_m["net_return"] >= base_m["net_return"] - 0.05
        ),
        "has_overlay_triggers": bool(paired_summary["overlay_trigger_count"] > 0),
    }
    paired_summary["overlap_diagnostic_passed"] = all(paired_summary["diagnostic_gates"].values())
    paired.to_csv(out_root / "overlap_only_mtm_curve.csv", index=False)
    merged.to_csv(out_root / "overlap_only_overlay_position_decisions.csv", index=False)
    write_json(out_root / "overlap_only_paired_comparison_summary.json", paired_summary)
    return paired_summary


def md_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_empty_"
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join(lines)


def write_report(
    *,
    doc_path: Path,
    out_root: Path,
    phase0_summary: dict[str, Any],
    live_shadow_summary: dict[str, Any],
    paired_summary: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    base = paired_summary["base_metrics"]
    overlay = paired_summary["overlay_metrics"]
    metric_rows = [
        {
            "variant": "hv_balanced_overlap_base",
            "net_return": f"{base['net_return']:.6f}",
            "sharpe": f"{base['sharpe']:.3f}",
            "max_drawdown": f"{base['max_drawdown']:.6f}",
            "period_count": base["period_count"],
        },
        {
            "variant": "coinglass_short_brake_small",
            "net_return": f"{overlay['net_return']:.6f}",
            "sharpe": f"{overlay['sharpe']:.3f}",
            "max_drawdown": f"{overlay['max_drawdown']:.6f}",
            "period_count": overlay["period_count"],
        },
    ]
    blockers = "\n".join(f"- {item}" for item in decision["blockers"]) or "- None."
    report = f"""# provider_sidecar_h10d Validation Chain

Generated local date: 2026-05-18

## Hard Status

- `provider_sidecar_h10d_phase0_ready`: **{str(phase0_summary.get("provider_sidecar_h10d_phase0_ready")).lower()}**
- `live_shadow_available_at_bootstrap`: **{str(decision["live_shadow_available_at_bootstrap"]).lower()}**
- `overlap_only_diagnostic_passed`: **{str(paired_summary.get("overlap_diagnostic_passed")).lower()}**
- `paper_shadow_paired_comparison_completed`: **true**
- `small_risk_overlay_shadow_allowed`: **{str(decision["small_risk_overlay_shadow_allowed"]).lower()}**
- `small_risk_overlay_live_allowed`: **false**
- `alpha_score_changed`: **false**
- `live_config_changed`: **false**

## Decision

The validation chain is complete as a bootstrap package, but the provider sidecar is **not approved for live order impact**. The small CoinGlass short-brake overlay remains a default-off blocked candidate until the overlap coverage gate and a forward no-manual-tuning shadow window both pass.

## Blockers

{blockers}

## Live Shadow

- request count: `{live_shadow_summary.get("request_count")}`
- success count: `{live_shadow_summary.get("success_count")}`
- error count: `{live_shadow_summary.get("error_count")}`
- median latency ms: `{live_shadow_summary.get("latency_ms_median")}`
- p95 latency ms: `{live_shadow_summary.get("latency_ms_p95")}`
- available_at recorded: `{live_shadow_summary.get("available_at_recorded")}`

## Overlap Paired Comparison

{md_table(metric_rows, ["variant", "net_return", "sharpe", "max_drawdown", "period_count"])}

Paired delta:

- mean delta return: `{paired_summary["paired_delta"]["mean_delta_return"]:.8f}`
- sum delta return: `{paired_summary["paired_delta"]["sum_delta_return"]:.8f}`
- positive delta share: `{paired_summary["paired_delta"]["positive_delta_share"]:.4f}`
- overlay triggers: `{paired_summary["overlay_trigger_count"]}`

## Artifacts

- `{out_root / "live_shadow_available_at.jsonl"}`
- `{out_root / "live_shadow_summary.json"}`
- `{out_root / "overlap_only_mtm_curve.csv"}`
- `{out_root / "overlap_only_overlay_position_decisions.csv"}`
- `{out_root / "overlap_only_paired_comparison_summary.json"}`
- `{out_root / "risk_overlay_shadow_candidate.json"}`
- `{out_root / "validation_chain_summary.json"}`
"""
    doc_path.write_text(report, encoding="utf-8")


def main() -> int:
    args = parse_args()
    out_root = args.out_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    phase0_path = (
        ROOT
        / "artifacts"
        / "quant_research"
        / "provider_sidecar_h10d"
        / "phase0_coverage_20260518"
        / "phase0_summary.json"
    )
    phase0_summary = read_json(phase0_path)
    live_symbols = read_live_symbols()[: int(args.symbol_limit)]
    if args.skip_live_shadow:
        live_shadow_summary_path = out_root / "live_shadow_summary.json"
        if live_shadow_summary_path.exists():
            live_shadow_summary = read_json(live_shadow_summary_path)
        else:
            live_shadow_summary = {
                "status": "skipped",
                "request_count": 0,
                "success_count": 0,
                "error_count": 0,
                "available_at_recorded": False,
                "all_live_symbols_all_endpoints_success": False,
            }
            write_json(live_shadow_summary_path, live_shadow_summary)
    else:
        live_shadow_summary = run_live_shadow(
            symbols=live_symbols,
            out_root=out_root,
            timeout_seconds=float(args.request_timeout_seconds),
            request_sleep_seconds=float(args.request_sleep_seconds),
        )

    paired_summary = run_overlap_backtest(
        out_root=out_root,
        overlay_short_multiplier=float(args.overlay_short_multiplier),
        veto_score_threshold=int(args.overlay_veto_score_threshold),
    )

    live_shadow_ok = bool(
        live_shadow_summary.get("available_at_recorded")
        and live_shadow_summary.get("success_count", 0) > 0
        and live_shadow_summary.get("error_count", 0) == 0
    )
    shadow_allowed = bool(live_shadow_ok and paired_summary.get("overlap_diagnostic_passed"))
    blockers = []
    if not live_shadow_ok:
        blockers.append("Live shadow bootstrap did not record clean available_at rows for all requested endpoint calls.")
    if not paired_summary.get("overlap_diagnostic_passed"):
        blockers.append(f"Overlap diagnostic gates failed: {paired_summary.get('diagnostic_gates')}.")
    if not phase0_summary.get("provider_sidecar_h10d_phase0_ready"):
        blockers.append(
            "Phase 0 remains not ready for full-window promotion; keep provider overlay shadow/paper-only."
        )
    blockers.append(
        "Forward paper/shadow evidence has only a bootstrap sample; live order impact requires a no-manual-tuning forward window."
    )
    decision = {
        "schema": "provider_sidecar_h10d_validation_chain_summary.v1",
        "generated_at_utc": iso_z(utc_now()),
        "provider_sidecar_h10d_phase0_ready": bool(phase0_summary.get("provider_sidecar_h10d_phase0_ready")),
        "live_shadow_available_at_bootstrap": live_shadow_ok,
        "overlap_only_diagnostic_passed": bool(paired_summary.get("overlap_diagnostic_passed")),
        "paper_shadow_paired_comparison_completed": True,
        "small_risk_overlay_shadow_allowed": shadow_allowed,
        "small_risk_overlay_live_allowed": False,
        "alpha_score_changed": False,
        "live_config_changed": False,
        "blockers": blockers,
        "artifact_root": str(out_root),
    }
    overlay_candidate = {
        "schema": "provider_sidecar_h10d_risk_overlay_shadow_candidate.v1",
        "name": "coinglass_short_brake_small",
        "status": "shadow_allowed" if shadow_allowed else "blocked",
        "default_enabled": False,
        "live_order_impact_allowed": False,
        "alpha_score_changed": False,
        "applies_to": "short positions only",
        "provider_lag_policy": "daily sidecar date D may affect decision D+1 only",
        "trigger": {
            "provider_veto_score_gte": int(args.overlay_veto_score_threshold),
            "signals": [
                "top_trader_crowded_long",
                "global_crowded_long",
                "taker_buy_pressure",
                "funding_high",
                "oi_rising",
                "bid_support",
                "short_liq_pressure",
            ],
        },
        "action": {
            "short_weight_multiplier": float(args.overlay_short_multiplier),
            "long_weight_multiplier": 1.0,
        },
        "promotion_boundary": "Requires forward no-manual-tuning paper/shadow window before live config can reference it.",
    }
    write_json(out_root / "risk_overlay_shadow_candidate.json", overlay_candidate)
    write_json(out_root / "validation_chain_summary.json", decision)
    write_report(
        doc_path=args.doc_path.resolve(),
        out_root=out_root,
        phase0_summary=phase0_summary,
        live_shadow_summary=live_shadow_summary,
        paired_summary=paired_summary,
        decision=decision,
    )
    print(json.dumps(decision, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
