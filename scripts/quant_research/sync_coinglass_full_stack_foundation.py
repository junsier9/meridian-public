from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable, Iterable

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.coinglass_capability_matrix import build_coinglass_capability_matrix  # noqa: E402
from enhengclaw.quant_research.coinglass_extended import (  # noqa: E402
    load_extended_rows,
    resolve_extended_external_root,
    sync_coinglass_extended_history,
)
from enhengclaw.quant_research.coinglass_spot_ohlcv import (  # noqa: E402
    resolve_external_history_root as resolve_spot_external_root,
)
from enhengclaw.quant_research.coinglass_spot_ohlcv import sync_coinglass_spot_ohlcv  # noqa: E402
from enhengclaw.quant_research.contracts import utc_now  # noqa: E402
from enhengclaw.quant_research.runtime_support import QUANT_INPUT_ROOT  # noqa: E402
from scripts.quant_research.audit_m3_1_options_regime_stage0 import (  # noqa: E402
    _build_options_panel,
    _fetch_options_payloads,
)
from scripts.quant_research.sync_coinglass_etf_onchain_participant_sidecars import (  # noqa: E402
    sync_sidecars as sync_etf_onchain_sidecars,
)
from scripts.quant_research.sync_coinglass_oi_provenance_sidecar import (  # noqa: E402
    UNIVERSE_PATH,
    resolve_external_root as resolve_oi_external_root,
    sync_sidecar as sync_oi_provenance_sidecar,
)


CONTRACT_VERSION = "coinglass_full_stack_foundation_sync.v1"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "quant_research" / "coinglass"
DEFAULT_JSON_PATH = DEFAULT_OUTPUT_ROOT / "coinglass_full_stack_foundation_sync.json"
DEFAULT_DOC_PATH = (
    ROOT / "docs" / "quant_research" / "01_data_foundation" / "coinglass_full_stack_foundation_sync.md"
)
DEFAULT_PROVIDER_SMOKE_ROOT = ROOT / "artifacts" / "quant_research" / "provider_smoke"
DEFAULT_OPTIONS_REPORT_DIR = (
    ROOT / "artifacts" / "quant_research" / "factor_reports" / "2026-05-07-m3-1-options-regime-stage0"
)
DEFAULT_ETF_ONCHAIN_REPORT_DIR = (
    ROOT
    / "artifacts"
    / "quant_research"
    / "factor_reports"
    / "2026-05-07-coinglass-etf-onchain-participant-sidecars"
)
NUMERIC_EXTENDED_COLUMNS = (
    "long_liquidation_usd",
    "short_liquidation_usd",
    "global_account_long_pct",
    "global_account_short_pct",
    "global_account_long_short_ratio",
    "top_trader_long_pct",
    "top_trader_short_pct",
    "top_trader_long_short_ratio",
    "orderbook_bids_usd",
    "orderbook_asks_usd",
    "orderbook_bids_quantity",
    "orderbook_asks_quantity",
    "taker_buy_volume_usd",
    "taker_sell_volume_usd",
)
PARTICIPANT_COLUMNS = (
    "date_utc",
    "timestamp_ms",
    "subject",
    "symbol",
    "liquidity_bucket",
    "global_account_long_pct",
    "global_account_short_pct",
    "global_account_long_short_ratio",
    "top_trader_long_pct",
    "top_trader_short_pct",
    "top_trader_long_short_ratio",
    "top_global_long_pct_disagreement",
    "top_global_net_long_disagreement",
    "taker_buy_volume_usd",
    "taker_sell_volume_usd",
    "taker_net_volume_usd",
    "taker_buy_sell_imbalance",
    "source",
)


ExtendedRowsLoader = Callable[..., list[dict[str, str]]]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "One-stop CoinGlass foundation sync and catalog builder. The script can "
            "refresh heavy API caches, rebuild normalized microstructure/participant "
            "panels, and write the default research data catalog."
        )
    )
    parser.add_argument("--as-of", default="2026-05-04")
    parser.add_argument("--universe-path", type=Path, default=UNIVERSE_PATH)
    parser.add_argument("--quant-input-root", type=Path, default=QUANT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC_PATH)
    parser.add_argument("--provider-smoke-root", type=Path, default=DEFAULT_PROVIDER_SMOKE_ROOT)
    parser.add_argument("--catalog-only", action="store_true", help="Do not call external API refresh steps.")
    parser.add_argument("--mode", choices=("refresh", "bootstrap"), default="refresh")
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--symbols", default="", help="Optional comma-separated symbol override.")
    parser.add_argument("--spot-intervals", default="1h")
    parser.add_argument("--spot-lookback-days", type=int, default=180)
    parser.add_argument("--oi-interval", default="1h")
    parser.add_argument("--oi-lookback-days", type=int, default=180)
    parser.add_argument("--extended-intervals", default="1h")
    parser.add_argument("--extended-lookback-days", type=int, default=187)
    parser.add_argument("--exchange-symbols", default="USDT,USDC")
    parser.add_argument("--exchange-pages", type=int, default=50)
    parser.add_argument("--exchange-per-page", type=int, default=100)
    parser.add_argument("--exchange-min-usd", type=float, default=1_000_000.0)
    parser.add_argument("--whale-symbols", default="BTC,ETH,USDT")
    parser.add_argument("--whale-lookback-days", type=int, default=180)
    parser.add_argument("--whale-window-days", type=int, default=7)
    parser.add_argument("--skip-capability-refresh", action="store_true")
    parser.add_argument("--skip-spot-refresh", action="store_true")
    parser.add_argument("--skip-oi-refresh", action="store_true")
    parser.add_argument("--skip-extended-refresh", action="store_true")
    parser.add_argument("--skip-options-refresh", action="store_true")
    parser.add_argument("--skip-etf-onchain-refresh", action="store_true")
    return parser


def _csv_items(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _csv_upper_items(value: str) -> list[str]:
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _ms_to_date(timestamp_ms: Any) -> str | None:
    try:
        raw = int(float(str(timestamp_ms)))
    except (TypeError, ValueError):
        return None
    if raw < 10_000_000_000:
        raw *= 1000
    return datetime.fromtimestamp(raw / 1000, tz=UTC).date().isoformat()


def _load_universe_records(
    universe_path: Path,
    *,
    max_symbols: int | None = None,
    explicit_symbols: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    payload = json.loads(universe_path.read_text(encoding="utf-8"))
    explicit = {item.strip().upper() for item in (explicit_symbols or []) if item.strip()}
    records: list[dict[str, Any]] = []
    for candidate in list(payload.get("candidates") or []):
        if candidate.get("is_stablecoin") or candidate.get("is_pegged_asset"):
            continue
        spot_symbol = str(candidate.get("spot_symbol") or "").strip().upper()
        usdm_symbol = str(candidate.get("usdm_symbol") or "").strip().upper()
        symbol = usdm_symbol or spot_symbol
        if not symbol:
            continue
        if explicit and symbol not in explicit and spot_symbol not in explicit:
            continue
        records.append(
            {
                "subject": str(candidate.get("subject") or symbol.removesuffix("USDT")),
                "spot_symbol": spot_symbol or symbol,
                "usdm_symbol": usdm_symbol or symbol,
                "symbol": symbol,
                "liquidity_bucket": str(candidate.get("liquidity_bucket") or "unknown"),
                "selection_rank": candidate.get("selection_rank"),
                "listing_age_days_as_of": candidate.get("listing_age_days_as_of"),
            }
        )
    if max_symbols is not None:
        records = records[: max(int(max_symbols), 0)]
    return records


def _run_step(name: str, func: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    started = time.time()
    try:
        payload = func()
        status = str(payload.get("status") or payload.get("overall_status") or "success")
        if payload.get("success") is False and status == "success":
            status = "partial"
        return {
            "name": name,
            "status": status,
            "duration_seconds": round(time.time() - started, 3),
            "payload": payload,
        }
    except Exception as exc:
        return {
            "name": name,
            "status": "error",
            "duration_seconds": round(time.time() - started, 3),
            "error": str(exc)[:500],
        }


def _skipped_step(name: str, reason: str) -> dict[str, Any]:
    return {"name": name, "status": "skipped", "duration_seconds": 0.0, "reason": reason}


def _coerce_numeric_columns(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = frame.copy()
    for column in columns:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    return out


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([pd.NA] * len(frame), index=frame.index, dtype="Float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _add_extended_derived_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    long_liq = _numeric_series(out, "long_liquidation_usd").fillna(0.0)
    short_liq = _numeric_series(out, "short_liquidation_usd").fillna(0.0)
    liq_total = long_liq + short_liq
    out["liquidation_total_usd"] = liq_total
    out["liquidation_imbalance_usd"] = short_liq - long_liq
    out["liquidation_imbalance_ratio"] = (short_liq - long_liq) / liq_total.mask(liq_total == 0.0)

    bids = _numeric_series(out, "orderbook_bids_usd").fillna(0.0)
    asks = _numeric_series(out, "orderbook_asks_usd").fillna(0.0)
    depth = bids + asks
    out["orderbook_depth_usd"] = depth
    out["orderbook_imbalance"] = (bids - asks) / depth.mask(depth == 0.0)

    taker_buy = _numeric_series(out, "taker_buy_volume_usd").fillna(0.0)
    taker_sell = _numeric_series(out, "taker_sell_volume_usd").fillna(0.0)
    taker_total = taker_buy + taker_sell
    out["taker_net_volume_usd"] = taker_buy - taker_sell
    out["taker_buy_sell_imbalance"] = (taker_buy - taker_sell) / taker_total.mask(taker_total == 0.0)

    global_long = _numeric_series(out, "global_account_long_pct")
    global_short = _numeric_series(out, "global_account_short_pct")
    top_long = _numeric_series(out, "top_trader_long_pct")
    top_short = _numeric_series(out, "top_trader_short_pct")
    out["global_account_net_long_pct"] = global_long - global_short
    out["top_trader_net_long_pct"] = top_long - top_short
    out["top_global_long_pct_disagreement"] = top_long - global_long
    out["top_global_net_long_disagreement"] = out["top_trader_net_long_pct"] - out["global_account_net_long_pct"]
    return out


def build_microstructure_and_participant_panels(
    *,
    symbol_records: list[dict[str, Any]],
    output_root: Path,
    external_root: Path | None = None,
    interval: str = "1h",
    rows_loader: ExtendedRowsLoader = load_extended_rows,
) -> dict[str, Any]:
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    resolved_external_root = resolve_extended_external_root(external_root=external_root)
    frames: list[pd.DataFrame] = []
    missing_symbols: list[str] = []
    for record in symbol_records:
        symbol = str(record["usdm_symbol"]).upper()
        rows = rows_loader(external_root=resolved_external_root, symbol=symbol, interval=interval)
        if not rows:
            missing_symbols.append(symbol)
            continue
        frame = pd.DataFrame(rows)
        frame["subject"] = str(record["subject"])
        frame["liquidity_bucket"] = str(record["liquidity_bucket"])
        frames.append(frame)

    if frames:
        hourly = pd.concat(frames, ignore_index=True)
        hourly["open_time_ms"] = pd.to_numeric(hourly["open_time_ms"], errors="coerce")
        hourly = hourly.dropna(subset=["open_time_ms"]).copy()
        hourly["open_time_ms"] = hourly["open_time_ms"].astype("int64")
        hourly["timestamp_ms"] = hourly["open_time_ms"]
        hourly["date_utc"] = pd.to_datetime(hourly["open_time_ms"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
        hourly = _coerce_numeric_columns(hourly, NUMERIC_EXTENDED_COLUMNS)
        hourly = _add_extended_derived_columns(hourly)
        hourly = hourly.sort_values(["symbol", "open_time_ms"]).reset_index(drop=True)
    else:
        hourly = pd.DataFrame()

    micro_1h_path = output_root / "microstructure_panel_1h.csv.gz"
    participant_1h_path = output_root / "participant_panel_1h.csv.gz"
    micro_1d_path = output_root / "microstructure_panel_1d.csv.gz"
    participant_1d_path = output_root / "participant_panel_1d.csv.gz"

    if not hourly.empty:
        hourly.to_csv(micro_1h_path, index=False, compression="gzip")
        participant_hourly_columns = [column for column in PARTICIPANT_COLUMNS if column in hourly.columns]
        hourly[participant_hourly_columns].to_csv(participant_1h_path, index=False, compression="gzip")
        daily = _aggregate_extended_hourly_to_daily(hourly)
        daily.to_csv(micro_1d_path, index=False, compression="gzip")
        participant_daily_columns = [column for column in PARTICIPANT_COLUMNS if column in daily.columns]
        daily[participant_daily_columns].to_csv(participant_1d_path, index=False, compression="gzip")
    else:
        for path in (micro_1h_path, participant_1h_path, micro_1d_path, participant_1d_path):
            pd.DataFrame().to_csv(path, index=False, compression="gzip")

    return {
        "status": "success" if not hourly.empty else "warning",
        "external_root": str(resolved_external_root),
        "interval": interval,
        "requested_symbol_count": int(len(symbol_records)),
        "missing_symbol_count": int(len(missing_symbols)),
        "missing_symbols": missing_symbols[:50],
        "paths": {
            "microstructure_panel_1h": str(micro_1h_path),
            "microstructure_panel_1d": str(micro_1d_path),
            "participant_panel_1h": str(participant_1h_path),
            "participant_panel_1d": str(participant_1d_path),
        },
        "artifacts": {
            "microstructure_panel_1h": summarize_tabular_artifact(micro_1h_path),
            "microstructure_panel_1d": summarize_tabular_artifact(micro_1d_path),
            "participant_panel_1h": summarize_tabular_artifact(participant_1h_path),
            "participant_panel_1d": summarize_tabular_artifact(participant_1d_path),
        },
        "research_status": "sidecar_context_only",
        "alpha_interpretation_allowed": False,
    }


def _aggregate_extended_hourly_to_daily(hourly: pd.DataFrame) -> pd.DataFrame:
    sum_columns = [
        "long_liquidation_usd",
        "short_liquidation_usd",
        "liquidation_total_usd",
        "liquidation_imbalance_usd",
        "taker_buy_volume_usd",
        "taker_sell_volume_usd",
        "taker_net_volume_usd",
    ]
    last_columns = [
        "timestamp_ms",
        "close_time_ms",
        "global_account_long_pct",
        "global_account_short_pct",
        "global_account_long_short_ratio",
        "top_trader_long_pct",
        "top_trader_short_pct",
        "top_trader_long_short_ratio",
        "orderbook_bids_usd",
        "orderbook_asks_usd",
        "orderbook_bids_quantity",
        "orderbook_asks_quantity",
        "global_account_net_long_pct",
        "top_trader_net_long_pct",
        "top_global_long_pct_disagreement",
        "top_global_net_long_disagreement",
        "orderbook_depth_usd",
        "orderbook_imbalance",
        "taker_buy_sell_imbalance",
        "source",
    ]
    group_columns = ["date_utc", "subject", "symbol", "liquidity_bucket"]
    agg: dict[str, str] = {}
    for column in sum_columns:
        if column in hourly.columns:
            agg[column] = "sum"
    for column in last_columns:
        if column in hourly.columns:
            agg[column] = "last"
    daily = hourly.groupby(group_columns, as_index=False).agg(agg)
    counts = hourly.groupby(group_columns, as_index=False).size().rename(columns={"size": "hourly_row_count"})
    daily = daily.merge(counts, on=group_columns, how="left")
    daily["timestamp_ms"] = pd.to_datetime(daily["date_utc"], utc=True).astype("int64") // 1_000_000
    daily = _add_extended_derived_columns(daily)
    return daily.sort_values(["symbol", "date_utc"]).reset_index(drop=True)


def summarize_tabular_artifact(path: Path) -> dict[str, Any]:
    path = path.resolve()
    summary: dict[str, Any] = {"path": str(path), "exists": bool(path.exists())}
    if not path.exists():
        return summary
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        summary["status"] = "read_error"
        summary["error"] = str(exc)[:300]
        return summary
    summary.update(
        {
            "status": "ok",
            "row_count": int(len(frame)),
            "column_count": int(len(frame.columns)),
            "columns": [str(column) for column in frame.columns[:60]],
            "size_bytes": int(path.stat().st_size),
        }
    )
    if "date_utc" in frame.columns and not frame.empty:
        summary["first_date_utc"] = str(frame["date_utc"].min())
        summary["last_date_utc"] = str(frame["date_utc"].max())
    elif "timestamp_ms" in frame.columns and not frame.empty:
        summary["first_date_utc"] = _ms_to_date(frame["timestamp_ms"].min())
        summary["last_date_utc"] = _ms_to_date(frame["timestamp_ms"].max())
    elif "open_time_ms" in frame.columns and not frame.empty:
        summary["first_date_utc"] = _ms_to_date(frame["open_time_ms"].min())
        summary["last_date_utc"] = _ms_to_date(frame["open_time_ms"].max())
    if "symbol" in frame.columns:
        summary["symbol_count"] = int(frame["symbol"].astype(str).nunique())
    if "subject" in frame.columns:
        summary["subject_count"] = int(frame["subject"].astype(str).nunique())
    return summary


def summarize_json_artifact(path: Path) -> dict[str, Any]:
    path = path.resolve()
    summary: dict[str, Any] = {"path": str(path), "exists": bool(path.exists())}
    if not path.exists():
        return summary
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        summary["status"] = "read_error"
        summary["error"] = str(exc)[:300]
        return summary
    summary["status"] = "ok"
    summary["size_bytes"] = int(path.stat().st_size)
    for key in (
        "status",
        "success",
        "success_count",
        "warning_count",
        "error_count",
        "data_success_count",
        "formula_clean_count",
        "formula_warning_count",
        "symbol_count",
        "requested_symbol_count",
        "min_requested_completeness",
    ):
        if key in payload:
            summary[key] = payload[key]
    return summary


def summarize_partition_root(path: Path) -> dict[str, Any]:
    path = path.resolve()
    summary: dict[str, Any] = {"path": str(path), "exists": bool(path.exists())}
    if not path.exists():
        return summary
    csv_files = list(path.rglob("*.csv.gz"))
    manifest_files = list(path.rglob("manifest.json"))
    summary.update(
        {
            "status": "ok",
            "csv_file_count": int(len(csv_files)),
            "manifest_count": int(len(manifest_files)),
            "top_level_dir_count": int(sum(1 for child in path.iterdir() if child.is_dir())),
        }
    )
    return summary


def _write_options_panel(*, output_root: Path) -> dict[str, Any]:
    panel_path = output_root / "options_regime_panel_1d.csv.gz"
    payloads = _fetch_options_payloads()
    panel, options_meta = _build_options_panel(payloads, volume_z_threshold=1.5, ratio_z_threshold=1.0)
    if not panel.empty:
        panel_to_write = panel.copy()
        panel_to_write["date_utc"] = pd.to_datetime(panel_to_write["date_utc"], utc=True).dt.strftime("%Y-%m-%d")
        panel_to_write.to_csv(panel_path, index=False, compression="gzip")
    return {
        "status": "success" if not panel.empty else "warning",
        "panel_output_path": str(panel_path),
        "options_meta": options_meta,
        "artifact": summarize_tabular_artifact(panel_path),
        "research_status": "sidecar_context_only",
        "alpha_interpretation_allowed": False,
    }


def build_artifact_catalog(*, output_root: Path) -> dict[str, Any]:
    spot_root = resolve_spot_external_root()
    oi_root = resolve_oi_external_root()
    extended_root = resolve_extended_external_root()
    return {
        "capability_matrix": {
            "family": "provider_capability",
            "research_status": "diagnostic_only",
            "summary": summarize_json_artifact(DEFAULT_PROVIDER_SMOKE_ROOT / "coinglass_capability_matrix.json"),
            "notes": "Endpoint capability smoke only; not data readiness.",
        },
        "spot_ohlcv": {
            "family": "spot_ohlcv",
            "research_status": "quarantined_until_provider_concordance_passes",
            "summary": summarize_json_artifact(output_root / "coinglass_spot_backfill_summary.json"),
            "raw_cache": summarize_partition_root(spot_root),
            "notes": "Coverage and strict provider concordance remain separate gates.",
        },
        "futures_oi_provenance": {
            "family": "futures_core",
            "research_status": "sidecar_context_with_native_usd_preferred",
            "summary": summarize_json_artifact(output_root / "coinglass_oi_provenance_sidecar_sync_2026-05-04.json"),
            "raw_cache": summarize_partition_root(oi_root),
            "notes": "Native USD OI is preferred; derived OI requires provenance and formula audit.",
        },
        "microstructure_panel_1h": {
            "family": "microstructure",
            "research_status": "sidecar_context_only",
            "summary": summarize_tabular_artifact(output_root / "microstructure_panel_1h.csv.gz"),
            "raw_cache": summarize_partition_root(extended_root),
            "notes": "Contains liquidation, orderbook, taker flow, top/global participant state.",
        },
        "microstructure_panel_1d": {
            "family": "microstructure",
            "research_status": "sidecar_context_only",
            "summary": summarize_tabular_artifact(output_root / "microstructure_panel_1d.csv.gz"),
            "notes": "1h extended rows aggregated to daily by fixed sum/last rules.",
        },
        "participant_panel_1d": {
            "family": "participant_state",
            "research_status": "sidecar_context_only",
            "summary": summarize_tabular_artifact(output_root / "participant_panel_1d.csv.gz"),
            "notes": "Top/global/taker participant panel; not an alpha by itself.",
        },
        "participant_panel_1h": {
            "family": "participant_state",
            "research_status": "sidecar_context_only",
            "summary": summarize_tabular_artifact(output_root / "participant_panel_1h.csv.gz"),
            "notes": "Hourly top/global/taker participant panel; not an alpha by itself.",
        },
        "etf_daily_state": {
            "family": "etf",
            "research_status": "sidecar_context_only_pit_lagged",
            "summary": summarize_tabular_artifact(output_root / "etf_daily_state_1d.csv.gz"),
            "notes": "Daily source date plus one-day PIT lag unless publication timestamp is proven.",
        },
        "exchange_transfers": {
            "family": "onchain_exchange_transfer",
            "research_status": "quarantined_latest_event_feed",
            "summary": summarize_tabular_artifact(output_root / "exchange_transfers_1d.csv.gz"),
            "notes": "Page-based latest-event feed; raw transfer_type is not semantic inflow/outflow.",
        },
        "whale_transfers": {
            "family": "onchain_whale_transfer",
            "research_status": "sidecar_context_only_pit_lagged",
            "summary": summarize_tabular_artifact(output_root / "whale_transfers_1d.csv.gz"),
            "notes": "Event sidecar with exchange-entity direction heuristic.",
        },
        "participant_context": {
            "family": "combined_context",
            "research_status": "sidecar_context_only",
            "summary": summarize_tabular_artifact(output_root / "participant_context_1d.csv.gz"),
            "notes": "Combined ETF/on-chain daily context for narrow pre-registered transition tests.",
        },
        "options_regime": {
            "family": "options_aggregate",
            "research_status": "quarantined_market_gate_only",
            "summary": summarize_tabular_artifact(output_root / "options_regime_panel_1d.csv.gz"),
            "notes": "Market-level options aggregates; max-pain remains snapshot-only unless PIT history is proven.",
        },
        "vendor_indicators": {
            "family": "vendor_indicator",
            "research_status": "diagnostic_only_not_synced",
            "summary": {"exists": False, "status": "intentionally_not_synced"},
            "notes": "Opaque vendor indicators are not foundation alpha inputs.",
        },
    }


def sync_foundation(args: argparse.Namespace) -> dict[str, Any]:
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    explicit_symbols = _csv_upper_items(args.symbols)
    symbol_records = _load_universe_records(
        args.universe_path.resolve(),
        max_symbols=args.max_symbols,
        explicit_symbols=explicit_symbols,
    )
    spot_symbols = [record["spot_symbol"] for record in symbol_records]
    usdm_symbols = [record["usdm_symbol"] for record in symbol_records]
    steps: list[dict[str, Any]] = []
    skip_reason = "catalog_only=True" if args.catalog_only else "explicit skip flag"

    if args.catalog_only or args.skip_capability_refresh:
        steps.append(_skipped_step("capability_matrix", skip_reason))
    else:
        steps.append(
            _run_step(
                "capability_matrix",
                lambda: build_coinglass_capability_matrix(output_root=args.provider_smoke_root.resolve()),
            )
        )

    if args.catalog_only or args.skip_spot_refresh:
        steps.append(_skipped_step("spot_ohlcv", skip_reason))
    else:
        steps.append(
            _run_step(
                "spot_ohlcv",
                lambda: sync_coinglass_spot_ohlcv(
                    as_of=args.as_of,
                    intervals=_csv_items(args.spot_intervals),
                    mode=args.mode,
                    quant_input_root=args.quant_input_root,
                    lookback_days=args.spot_lookback_days,
                    max_symbols=args.max_symbols,
                    symbols=spot_symbols if explicit_symbols else None,
                ),
            )
        )

    if args.catalog_only or args.skip_oi_refresh:
        steps.append(_skipped_step("oi_provenance", skip_reason))
    else:
        steps.append(
            _run_step(
                "oi_provenance",
                lambda: sync_oi_provenance_sidecar(
                    as_of=args.as_of,
                    universe_path=args.universe_path.resolve(),
                    interval=args.oi_interval,
                    lookback_days=args.oi_lookback_days,
                    max_symbols=args.max_symbols,
                ),
            )
        )

    if args.catalog_only or args.skip_extended_refresh:
        steps.append(_skipped_step("extended_microstructure_refresh", skip_reason))
    else:
        steps.append(
            _run_step(
                "extended_microstructure_refresh",
                lambda: sync_coinglass_extended_history(
                    symbols=usdm_symbols,
                    intervals=_csv_items(args.extended_intervals),
                    mode=args.mode,
                    as_of=args.as_of,
                    lookback_days={"1h": args.extended_lookback_days},
                ),
            )
        )

    steps.append(
        _run_step(
            "microstructure_participant_panel_build",
            lambda: build_microstructure_and_participant_panels(
                symbol_records=symbol_records,
                output_root=output_root,
                interval=_csv_items(args.extended_intervals)[0] if _csv_items(args.extended_intervals) else "1h",
            ),
        )
    )

    if args.catalog_only or args.skip_etf_onchain_refresh:
        steps.append(_skipped_step("etf_onchain_participant_sidecars", skip_reason))
    else:
        steps.append(
            _run_step(
                "etf_onchain_participant_sidecars",
                lambda: sync_etf_onchain_sidecars(
                    pit_lag_days=1,
                    output_root=output_root,
                    report_dir=DEFAULT_ETF_ONCHAIN_REPORT_DIR,
                    exchange_symbols=_csv_upper_items(args.exchange_symbols),
                    exchange_pages=args.exchange_pages,
                    exchange_per_page=args.exchange_per_page,
                    exchange_min_usd=args.exchange_min_usd,
                    whale_symbols=_csv_upper_items(args.whale_symbols),
                    whale_lookback_days=args.whale_lookback_days,
                    whale_window_days=args.whale_window_days,
                    sleep_seconds=0.02,
                ),
            )
        )

    if args.catalog_only or args.skip_options_refresh:
        steps.append(_skipped_step("options_regime_panel", skip_reason))
    else:
        steps.append(_run_step("options_regime_panel", lambda: _write_options_panel(output_root=output_root)))

    catalog = build_artifact_catalog(output_root=output_root)
    decision = _foundation_decision(catalog=catalog, steps=steps)
    report = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": utc_now(),
        "as_of": args.as_of,
        "mode": args.mode,
        "catalog_only": bool(args.catalog_only),
        "universe_path": str(args.universe_path.resolve()),
        "symbol_count": int(len(symbol_records)),
        "symbols": usdm_symbols,
        "output_root": str(output_root),
        "steps": steps,
        "catalog": catalog,
        "decision": decision,
    }
    json_path = args.json_path.resolve()
    doc_path = args.doc_path.resolve()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    doc_path.write_text(render_foundation_doc(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["doc_path"] = str(doc_path)
    return report


def _foundation_decision(*, catalog: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    error_steps = [step["name"] for step in steps if step.get("status") == "error"]
    missing_required = [
        key
        for key in (
            "microstructure_panel_1d",
            "participant_panel_1d",
            "etf_daily_state",
            "whale_transfers",
            "options_regime",
        )
        if not ((catalog.get(key) or {}).get("summary") or {}).get("exists")
    ]
    return {
        "foundation_catalog_ready": not error_steps and not missing_required,
        "alpha_rerun_allowed": False,
        "manifest_ab_allowed": False,
        "error_steps": error_steps,
        "missing_required_catalog_entries": missing_required,
        "default_next_action": (
            "Check this catalog first, then run a narrow pre-registered integration/falsification pass. "
            "Do not treat data availability as alpha evidence."
        ),
    }


def _status_counts(steps: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in steps:
        status = str(step.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def render_foundation_doc(report: dict[str, Any]) -> str:
    decision = dict(report.get("decision") or {})
    steps = list(report.get("steps") or [])
    catalog = dict(report.get("catalog") or {})
    counts = _status_counts(steps)
    lines = [
        "# CoinGlass Full-Stack Foundation Sync",
        "",
        f"`Run date: {str(report.get('generated_at_utc', ''))[:10]}`",
        f"`Contract: {report.get('contract_version')}`",
        "`Status: foundation catalog ready; alpha still fail-closed`"
        if decision.get("foundation_catalog_ready")
        else "`Status: foundation catalog incomplete; inspect blockers`",
        "",
        "---",
        "",
        "## Purpose",
        "",
        "This is the default CoinGlass data catalog to check before opening a new",
        "roadmap lane. It consolidates local raw caches, normalized sidecars,",
        "coverage artifacts, and quarantine status so research does not rediscover",
        "data gaps one lane at a time.",
        "",
        "It is not alpha evidence and it does not modify the canonical parent.",
        "",
        "---",
        "",
        "## Execution Summary",
        "",
        f"- as_of: `{report.get('as_of')}`",
        f"- catalog_only: `{report.get('catalog_only')}`",
        f"- symbol_count: `{report.get('symbol_count')}`",
        f"- step_status_counts: `{counts}`",
        f"- foundation_catalog_ready: `{decision.get('foundation_catalog_ready')}`",
        f"- alpha_rerun_allowed: `{decision.get('alpha_rerun_allowed')}`",
        "",
        "| step | status | seconds | note |",
        "| --- | --- | ---: | --- |",
    ]
    for step in steps:
        note = step.get("reason") or step.get("error") or ""
        lines.append(
            f"| `{step.get('name')}` | `{step.get('status')}` | `{step.get('duration_seconds')}` | {note} |"
        )
    lines.extend(
        [
            "",
            "---",
            "",
            "## Catalog",
            "",
            "| entry | family | research status | rows/files | date range | notes |",
            "| --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for key, entry in catalog.items():
        summary = dict(entry.get("summary") or {})
        rows_or_files = summary.get("row_count")
        if rows_or_files is None:
            rows_or_files = summary.get("csv_file_count")
        if rows_or_files is None:
            rows_or_files = summary.get("requested_symbol_count")
        if rows_or_files is None:
            rows_or_files = summary.get("symbol_count")
        if rows_or_files is None:
            rows_or_files = summary.get("success_count")
        if rows_or_files is None:
            rows_or_files = "n/a"
        date_range = "n/a"
        if summary.get("first_date_utc") or summary.get("last_date_utc"):
            date_range = f"{summary.get('first_date_utc')} to {summary.get('last_date_utc')}"
        lines.append(
            f"| `{key}` | `{entry.get('family')}` | `{entry.get('research_status')}` | "
            f"`{rows_or_files}` | {date_range} | {entry.get('notes')} |"
        )
    lines.extend(
        [
            "",
            "---",
            "",
            "## Non-Negotiable Policy",
            "",
            "- Coverage and concordance remain separate gates.",
            "- Snapshot, latest-event, and opaque vendor-indicator data stay quarantined.",
            "- ETF and on-chain rows require PIT lag before entering a decision frame.",
            "- A sidecar can support Stage 0 design, but cannot open manifest A/B without strict falsification.",
            "",
            "## Default Use",
            "",
            "Before starting a new CoinGlass-backed research lane, inspect this catalog",
            "and use the `research_status` field to decide whether the input is",
            "`sidecar_context_only`, `quarantined`, or `diagnostic_only`. If a required",
            "entry is missing, refresh this foundation script first rather than adding",
            "one-off data pulls inside the research script.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = sync_foundation(args)
    print(
        json.dumps(
            {
                "json_path": report["json_path"],
                "doc_path": report["doc_path"],
                "decision": report["decision"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not report["decision"]["error_steps"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
