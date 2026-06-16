from __future__ import annotations

import argparse
import gzip
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
HOUR_MS = 60 * 60 * 1000
CONTRACT_VERSION = "parallel_1h_venue_volume_native_concordance.v1"
RESEARCH_ID = "venue_volume_native_concordance_1h"
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")
VENUES = ("binance", "okex", "bybitspot", "coinbase")

PRICE_REL_P95_MAX = 1e-4
BASE_VOLUME_REL_P95_MAX = 1e-3
ESTIMATED_QUOTE_REL_P95_MAX = 1e-3
ACTUAL_QUOTE_REL_P95_MAX = 1e-2
ACTUAL_QUOTE_REL_MAX_MAX = 5e-2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare local CoinAPI per-venue 1h spot volume bars against native exchange public APIs. "
            "Research/data QA only; does not admit alpha."
        )
    )
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-05-07")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--sample-hours", type=int, default=24)
    parser.add_argument(
        "--exclude-last-hours",
        type=int,
        default=0,
        help="Move the sample window this many hours behind the strict common local/native closed-bar end.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=0.10)
    return parser


def _resolve_external_root(value: Path | None) -> Path:
    if value is not None:
        return value
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        return Path(localappdata) / "EnhengClaw"
    return Path.home() / ".local" / "share" / "EnhengClaw"


def _venue_root(external_root: Path, venue: str) -> Path:
    if venue == "binance":
        return external_root / "market_history" / "coinapi_ohlcv"
    if venue == "coinbase":
        return external_root / "coinapi_ohlcv_COINBASE"
    if venue == "okex":
        return external_root / "coinapi_ohlcv_OKEX"
    if venue == "bybitspot":
        return external_root / "coinapi_ohlcv_BYBITSPOT"
    raise ValueError(f"unknown venue {venue!r}")


def _parse_symbols(value: str) -> list[str]:
    out = [item.strip().upper() for item in str(value or "").split(",") if item.strip()]
    return out or list(DEFAULT_SYMBOLS)


def _dt_iso_ms(value_ms: int) -> str:
    return datetime.fromtimestamp(int(value_ms) / 1000, tz=timezone.utc).isoformat()


def _http_json(url: str, *, timeout: float = 30.0) -> Any:
    req = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "EnhengClaw/0.1 venue-volume-concordance",
        },
        method="GET",
    )
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _local_rows(
    *,
    external_root: Path,
    venue: str,
    symbol: str,
    sample_hours: int,
    max_open_time_ms: int | None = None,
) -> pd.DataFrame:
    folder = _venue_root(external_root, venue) / "spot" / symbol / "1h"
    if not folder.exists():
        return pd.DataFrame()
    paths = sorted(folder.glob("*.csv.gz"))
    if not paths:
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    wanted = [
        "exchange",
        "symbol",
        "open_time_ms",
        "close_time_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "source",
    ]
    for path in paths:
        try:
            frame = pd.read_csv(path, usecols=wanted)
        except Exception:
            continue
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    frame = pd.concat(frames, ignore_index=True)
    for col in ("open_time_ms", "close_time_ms", "open", "high", "low", "close", "volume", "quote_volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["open_time_ms"]).copy()
    frame["open_time_ms"] = frame["open_time_ms"].astype("int64")
    frame = frame.drop_duplicates("open_time_ms", keep="last")
    if max_open_time_ms is not None:
        frame = frame.loc[frame["open_time_ms"].le(int(max_open_time_ms))].copy()
    frame = frame.sort_values("open_time_ms").tail(int(sample_hours)).reset_index(drop=True)
    frame["venue"] = venue
    frame["local_estimated_quote_volume"] = frame["quote_volume"]
    return frame


def _common_end_open_time_ms(external_root: Path, symbols: list[str]) -> int:
    max_values: list[int] = []
    for venue in VENUES:
        for symbol in symbols:
            local = _local_rows(
                external_root=external_root,
                venue=venue,
                symbol=symbol,
                sample_hours=1,
            )
            if not local.empty:
                max_values.append(int(local["open_time_ms"].max()))
    if not max_values:
        raise RuntimeError("no local 1h rows found for requested venue/symbol sample")
    now_closed_floor = ((int(time.time() * 1000) - HOUR_MS) // HOUR_MS) * HOUR_MS
    return int(min(min(max_values), now_closed_floor))


def _typical_quote(open_: float, high: float, low: float, close: float, volume: float) -> float:
    return float(volume) * max((float(open_) + float(high) + float(low) + float(close)) / 4.0, 0.0)


def _native_binance(symbol: str, start_ms: int, end_ms: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    url = "https://api.binance.com/api/v3/klines?" + urlencode(
        {
            "symbol": symbol,
            "interval": "1h",
            "startTime": int(start_ms),
            "endTime": int(end_ms + HOUR_MS - 1),
            "limit": 1000,
        }
    )
    payload = _http_json(url)
    rows = []
    for item in payload:
        rows.append(
            {
                "open_time_ms": int(item[0]),
                "native_open": float(item[1]),
                "native_high": float(item[2]),
                "native_low": float(item[3]),
                "native_close": float(item[4]),
                "native_base_volume": float(item[5]),
                "native_close_time_ms": int(item[6]),
                "native_actual_quote_volume": float(item[7]),
                "native_quote_volume_mode": "actual_quote_asset_volume",
            }
        )
    return pd.DataFrame(rows), {"url": url, "status": "ok"}


def _okx_inst_id(symbol: str) -> str:
    return f"{symbol[:-4]}-USDT"


def _native_okx(symbol: str, start_ms: int, end_ms: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    # Recent-window audit: no pagination is needed for the default 24h sample.
    url = "https://www.okx.com/api/v5/market/history-candles?" + urlencode(
        {"instId": _okx_inst_id(symbol), "bar": "1H", "limit": 100}
    )
    payload = _http_json(url)
    if str(payload.get("code")) != "0":
        raise RuntimeError(f"OKX API error: {payload}")
    rows = []
    for item in payload.get("data", []):
        open_ms = int(item[0])
        if open_ms < start_ms or open_ms > end_ms:
            continue
        confirm = str(item[8]) if len(item) > 8 else ""
        if confirm != "1":
            continue
        rows.append(
            {
                "open_time_ms": open_ms,
                "native_open": float(item[1]),
                "native_high": float(item[2]),
                "native_low": float(item[3]),
                "native_close": float(item[4]),
                "native_base_volume": float(item[5]),
                "native_close_time_ms": open_ms + HOUR_MS - 1,
                "native_actual_quote_volume": float(item[7]),
                "native_quote_volume_mode": "actual_quote_currency_volume",
            }
        )
    return pd.DataFrame(rows), {"url": url, "status": "ok"}


def _native_bybitspot(symbol: str, start_ms: int, end_ms: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    url = "https://api.bybit.com/v5/market/kline?" + urlencode(
        {
            "category": "spot",
            "symbol": symbol,
            "interval": "60",
            "start": int(start_ms),
            "end": int(end_ms + HOUR_MS - 1),
            "limit": 1000,
        }
    )
    payload = _http_json(url)
    if int(payload.get("retCode", -1)) != 0:
        raise RuntimeError(f"Bybit API error: {payload}")
    rows = []
    for item in payload.get("result", {}).get("list", []):
        rows.append(
            {
                "open_time_ms": int(item[0]),
                "native_open": float(item[1]),
                "native_high": float(item[2]),
                "native_low": float(item[3]),
                "native_close": float(item[4]),
                "native_base_volume": float(item[5]),
                "native_close_time_ms": int(item[0]) + HOUR_MS - 1,
                "native_actual_quote_volume": float(item[6]),
                "native_quote_volume_mode": "actual_turnover",
            }
        )
    return pd.DataFrame(rows), {"url": url, "status": "ok"}


def _native_coinbase(symbol: str, start_ms: int, end_ms: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    product = f"{symbol[:-4]}-USDT"
    start = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    # Coinbase end is exclusive enough for our purposes; add one hour to include the final open.
    end = datetime.fromtimestamp((end_ms + HOUR_MS) / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    url = f"https://api.exchange.coinbase.com/products/{product}/candles?" + urlencode(
        {"granularity": 3600, "start": start, "end": end}
    )
    payload = _http_json(url)
    rows = []
    for item in payload:
        open_ms = int(item[0]) * 1000
        open_, high, low, close, volume = float(item[3]), float(item[2]), float(item[1]), float(item[4]), float(item[5])
        rows.append(
            {
                "open_time_ms": open_ms,
                "native_open": open_,
                "native_high": high,
                "native_low": low,
                "native_close": close,
                "native_base_volume": volume,
                "native_close_time_ms": open_ms + HOUR_MS - 1,
                "native_actual_quote_volume": np.nan,
                "native_quote_volume_mode": "estimated_from_base_volume_public_api_no_quote_turnover",
            }
        )
    return pd.DataFrame(rows), {"url": url, "status": "ok"}


NATIVE_FETCHERS = {
    "binance": _native_binance,
    "okex": _native_okx,
    "bybitspot": _native_bybitspot,
    "coinbase": _native_coinbase,
}


def _rel_error(local: pd.Series, native: pd.Series) -> pd.Series:
    denom = native.abs().replace(0.0, np.nan)
    return (local - native).abs() / denom


def _compare_rows(local: pd.DataFrame, native: pd.DataFrame) -> pd.DataFrame:
    if local.empty:
        return pd.DataFrame()
    if native.empty:
        out = local.copy()
        out["native_missing"] = True
        return out
    merged = local.merge(native, on="open_time_ms", how="left")
    merged["native_missing"] = merged["native_close"].isna()
    for prefix in ("local", "native"):
        pass
    merged["native_estimated_quote_volume"] = merged.apply(
        lambda row: _typical_quote(
            row["native_open"],
            row["native_high"],
            row["native_low"],
            row["native_close"],
            row["native_base_volume"],
        )
        if not pd.isna(row.get("native_base_volume"))
        else np.nan,
        axis=1,
    )
    merged["local_base_volume"] = merged["volume"]
    merged["local_close"] = merged["close"]
    merged["close_rel_error"] = _rel_error(merged["local_close"], merged["native_close"])
    merged["base_volume_rel_error"] = _rel_error(merged["local_base_volume"], merged["native_base_volume"])
    merged["estimated_quote_rel_error"] = _rel_error(
        merged["local_estimated_quote_volume"],
        merged["native_estimated_quote_volume"],
    )
    merged["actual_quote_rel_error"] = _rel_error(
        merged["local_estimated_quote_volume"],
        merged["native_actual_quote_volume"],
    )
    return merged


def _metric_summary(values: pd.Series) -> dict[str, Any]:
    clean = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return {"count": 0, "median": None, "p95": None, "max": None}
    return {
        "count": int(len(clean)),
        "median": float(clean.median()),
        "p95": float(clean.quantile(0.95)),
        "max": float(clean.max()),
    }


def _venue_symbol_summary(compared: pd.DataFrame, *, venue: str, symbol: str, api_meta: dict[str, Any]) -> dict[str, Any]:
    if compared.empty:
        return {
            "venue": venue,
            "symbol": symbol,
            "requested_rows": 0,
            "matched_rows": 0,
            "api_status": api_meta.get("status"),
            "status": "no_local_rows",
            "passed": False,
        }
    missing = int(compared["native_missing"].sum())
    matched = compared.loc[~compared["native_missing"]].copy()
    close_summary = _metric_summary(matched.get("close_rel_error", pd.Series(dtype=float)))
    base_summary = _metric_summary(matched.get("base_volume_rel_error", pd.Series(dtype=float)))
    est_quote_summary = _metric_summary(matched.get("estimated_quote_rel_error", pd.Series(dtype=float)))
    actual_quote_summary = _metric_summary(matched.get("actual_quote_rel_error", pd.Series(dtype=float)))
    actual_quote_supported = int(actual_quote_summary["count"]) > 0
    passed = bool(
        api_meta.get("status") == "ok"
        and missing == 0
        and int(len(matched)) > 0
        and (close_summary.get("p95") is not None and close_summary["p95"] <= PRICE_REL_P95_MAX)
        and (base_summary.get("p95") is not None and base_summary["p95"] <= BASE_VOLUME_REL_P95_MAX)
        and (
            est_quote_summary.get("p95") is not None
            and est_quote_summary["p95"] <= ESTIMATED_QUOTE_REL_P95_MAX
        )
        and (
            not actual_quote_supported
            or (
                actual_quote_summary.get("p95") is not None
                and actual_quote_summary["p95"] <= ACTUAL_QUOTE_REL_P95_MAX
                and actual_quote_summary.get("max") is not None
                and actual_quote_summary["max"] <= ACTUAL_QUOTE_REL_MAX_MAX
            )
        )
    )
    return {
        "venue": venue,
        "symbol": symbol,
        "api_status": api_meta.get("status"),
        "native_url": api_meta.get("url"),
        "requested_rows": int(len(compared)),
        "matched_rows": int(len(matched)),
        "native_missing_rows": missing,
        "native_quote_volume_mode": str(matched["native_quote_volume_mode"].dropna().iloc[0])
        if not matched.empty and "native_quote_volume_mode" in matched
        else None,
        "actual_quote_supported": actual_quote_supported,
        "close_rel_error": close_summary,
        "base_volume_rel_error": base_summary,
        "estimated_quote_rel_error": est_quote_summary,
        "actual_quote_rel_error": actual_quote_summary,
        "passed": passed,
        "sample_rows": [
            {
                "open_time_utc": _dt_iso_ms(int(row.open_time_ms)),
                "local_close": float(row.local_close) if not pd.isna(row.local_close) else None,
                "native_close": float(row.native_close) if not pd.isna(row.native_close) else None,
                "local_base_volume": float(row.local_base_volume) if not pd.isna(row.local_base_volume) else None,
                "native_base_volume": float(row.native_base_volume) if not pd.isna(row.native_base_volume) else None,
                "local_estimated_quote_volume": float(row.local_estimated_quote_volume)
                if not pd.isna(row.local_estimated_quote_volume)
                else None,
                "native_actual_quote_volume": float(row.native_actual_quote_volume)
                if not pd.isna(row.native_actual_quote_volume)
                else None,
                "native_estimated_quote_volume": float(row.native_estimated_quote_volume)
                if not pd.isna(row.native_estimated_quote_volume)
                else None,
            }
            for row in matched.tail(3).itertuples(index=False)
        ],
    }


def _pass_fail_decision(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "label": "blocked",
            "reason": "no comparison rows were produced",
            "fake_liquidity_retry_allowed": False,
            "alpha_rerun_allowed": False,
        }
    failed = [row for row in rows if not row.get("passed")]
    api_blocked = [row for row in rows if row.get("api_status") != "ok"]
    coinbase_estimated_only = [
        row
        for row in rows
        if row.get("venue") == "coinbase" and not row.get("actual_quote_supported")
    ]
    if api_blocked:
        label = "blocked"
        reason = "one or more native exchange APIs were unavailable"
    elif failed:
        label = "fail"
        reason = "one or more venue/symbol comparisons failed strict native concordance thresholds"
    elif coinbase_estimated_only:
        label = "pass_limited_pre_alpha"
        reason = (
            "native price/base-volume concordance passed, and actual quote-volume concordance passed "
            "where the native API exposes quote turnover; Coinbase public API exposes base volume only, "
            "so Coinbase quote volume remains estimated."
        )
    else:
        label = "pass"
        reason = "native quote-volume concordance passed for the sampled venue/symbol/hour set"
    return {
        "label": label,
        "reason": reason,
        "compared_pair_count": int(len(rows)),
        "failed_pair_count": int(len(failed)),
        "api_blocked_pair_count": int(len(api_blocked)),
        "coinbase_estimated_only_pair_count": int(len(coinbase_estimated_only)),
        "thresholds": {
            "price_rel_p95_max": PRICE_REL_P95_MAX,
            "base_volume_rel_p95_max": BASE_VOLUME_REL_P95_MAX,
            "estimated_quote_rel_p95_max": ESTIMATED_QUOTE_REL_P95_MAX,
            "actual_quote_rel_p95_max": ACTUAL_QUOTE_REL_P95_MAX,
            "actual_quote_rel_max_max": ACTUAL_QUOTE_REL_MAX_MAX,
        },
        "provider_concordance_status": label,
        "fake_liquidity_retry_allowed": False,
        "alpha_rerun_allowed": False,
        "h10d_promotion_state_mutation": False,
        "next_landing_shape": (
            "If pass_limited_pre_alpha or pass, run a wider native concordance sample and then "
            "pre-register a venue-concentration capacity-haircut simulator. Do not mutate h10d."
        ),
    }


def _write_markdown(report: dict[str, Any]) -> str:
    decision = report["pass_fail_decision"]
    lines = [
        "# Venue Volume Native Concordance 1h",
        "",
        f"- research_id: `{report['research_id']}`",
        f"- decision: `{decision['label']}`",
        f"- sample window: `{report['sample_window']['start_utc']}` -> `{report['sample_window']['end_utc']}`",
        f"- sample hours per pair: `{report['sample_hours']}`",
        "",
        "| venue | symbol | matched | actual quote? | close p95 | base p95 | est quote p95 | actual quote p95 | pass |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report["by_venue_symbol"]:
        def fmt(metric: str) -> str:
            value = (row.get(metric) or {}).get("p95")
            return "NA" if value is None else f"{value:.6g}"

        lines.append(
            "| {venue} | {symbol} | {matched} | {actual} | {close} | {base} | {est} | {act} | {passed} |".format(
                venue=row["venue"],
                symbol=row["symbol"],
                matched=row.get("matched_rows", 0),
                actual=str(row.get("actual_quote_supported")).lower(),
                close=fmt("close_rel_error"),
                base=fmt("base_volume_rel_error"),
                est=fmt("estimated_quote_rel_error"),
                act=fmt("actual_quote_rel_error"),
                passed=str(row.get("passed")).lower(),
            )
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"`{decision['label']}`: {decision['reason']}",
            "",
            "The sidecar remains research/data QA only. Alpha rerun and fake-liquidity retry remain disabled.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    external_root = _resolve_external_root(args.external_root)
    symbols = _parse_symbols(args.symbols)
    end_open_ms = _common_end_open_time_ms(external_root, symbols) - int(args.exclude_last_hours) * HOUR_MS
    start_open_ms = end_open_ms - (int(args.sample_hours) - 1) * HOUR_MS
    rows: list[dict[str, Any]] = []
    raw_rows: list[pd.DataFrame] = []
    for venue in VENUES:
        fetcher = NATIVE_FETCHERS[venue]
        for symbol in symbols:
            local = _local_rows(
                external_root=external_root,
                venue=venue,
                symbol=symbol,
                sample_hours=int(args.sample_hours),
                max_open_time_ms=end_open_ms,
            )
            local = local.loc[local["open_time_ms"].between(start_open_ms, end_open_ms)].copy()
            api_meta: dict[str, Any]
            try:
                native, api_meta = fetcher(symbol, start_open_ms, end_open_ms)
            except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
                native = pd.DataFrame()
                api_meta = {"status": "error", "error": repr(exc)}
            compared = _compare_rows(local, native)
            compared["venue"] = venue
            compared["symbol"] = symbol
            if not compared.empty:
                raw_rows.append(compared)
            rows.append(_venue_symbol_summary(compared, venue=venue, symbol=symbol, api_meta=api_meta))
            if float(args.sleep_seconds) > 0:
                time.sleep(float(args.sleep_seconds))

    decision = _pass_fail_decision(rows)
    output_dir = args.output_dir or (
        ROOT
        / "artifacts"
        / "quant_research"
        / "factor_reports"
        / f"{args.as_of}-parallel-1h-alpha-stage0"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    detail_path = output_dir / "venue_volume_native_concordance_1h_details.csv.gz"
    if raw_rows:
        detail = pd.concat(raw_rows, ignore_index=True)
        with gzip.open(detail_path, "wt", encoding="utf-8", newline="") as handle:
            detail.to_csv(handle, index=False)
    else:
        detail_path = None
    report: dict[str, Any] = {
        "artifact_family": "parallel_1h_alpha_mining_data_concordance",
        "contract_version": CONTRACT_VERSION,
        "research_id": RESEARCH_ID,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": str(args.as_of),
        "external_root": str(external_root),
        "symbols": symbols,
        "venues": list(VENUES),
        "sample_hours": int(args.sample_hours),
        "exclude_last_hours": int(args.exclude_last_hours),
        "sample_window": {
            "start_open_time_ms": int(start_open_ms),
            "end_open_time_ms": int(end_open_ms),
            "start_utc": _dt_iso_ms(start_open_ms),
            "end_utc": _dt_iso_ms(end_open_ms),
        },
        "schema_note": {
            "local_coinapi_quote_volume": "estimated_from_typical_price_in_repo_sync",
            "coinbase_public_api_quote_volume": "not_available; estimated from base volume and OHLC for this audit",
        },
        "canonical_h10d_boundary": {
            "h10d_parent": "v5_rw_bridge_no_overlay_h10d",
            "status": "not_modified",
            "use": "comparison_and_mechanism_inspiration_only",
        },
        "by_venue_symbol": rows,
        "detail_rows_path": None if detail_path is None else str(detail_path),
        "pass_fail_decision": decision,
    }
    json_path = output_dir / "venue_volume_native_concordance_1h.json"
    md_path = output_dir / "venue_volume_native_concordance_1h.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_write_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "json_path": str(json_path),
                "md_path": str(md_path),
                "detail_rows_path": report["detail_rows_path"],
                "pass_fail_decision": decision,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
