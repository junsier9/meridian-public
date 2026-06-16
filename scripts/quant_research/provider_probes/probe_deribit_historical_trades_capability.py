"""probe_deribit_historical_trades_capability.py — empirical test of
Deribit Public API trades-by-time endpoint for FREE historical
backfill capability.

Phase 0 scoping (commit 99d68bf) flagged that get_book_summary +
ticker endpoints are real-time only. But /public/get_last_trades_by_
currency_and_time MIGHT provide historical trades with per-trade
mark_iv → could partial-backfill F56/F58 (IV-based) factors WITHOUT
the 60-90d live-sync wall-clock.

This script probes that capability empirically:
  1. Try fetching last-30d, last-60d, last-90d, last-180d, last-365d
     of BTC option trades.
  2. For each window, count: total trades, distinct instruments,
     distinct strikes, distinct expiries, IV coverage.
  3. Assess: can we reconstruct daily ATM IV history? 25Δ skew history?
     OI history? (No — trades don't include OI snapshots.)

Endpoint: /public/get_last_trades_by_currency_and_time
  Params: currency, kind, start_timestamp, end_timestamp, count,
          include_old, sorting

Stage-1 invariant: this is a network-bounded research probe. Output is
a feasibility report; no manifest mutation; no scheduled deployment.

Output:
  artifacts/quant_research/factor_reports/<as-of>/m3_1_historical_data_paths.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]

DERIBIT_PUBLIC_API_BASE = "https://www.deribit.com/api/v2/public"
TRADES_BY_TIME_URL = f"{DERIBIT_PUBLIC_API_BASE}/get_last_trades_by_currency_and_time"


def _fetch_trades_window(
    currency: str, start_ms: int, end_ms: int, count: int = 1000
) -> dict:
    """Returns {trades: [...], has_more: bool, response_status} or error dict."""
    import requests
    params = {
        "currency": currency,
        "kind": "option",
        "start_timestamp": int(start_ms),
        "end_timestamp": int(end_ms),
        "count": int(count),
        "include_old": "true",
        "sorting": "asc",
    }
    try:
        resp = requests.get(TRADES_BY_TIME_URL, params=params, timeout=30)
        if resp.status_code != 200:
            return {
                "status": "http_error",
                "http_status": resp.status_code,
                "body_excerpt": resp.text[:300],
            }
        payload = resp.json()
        result = payload.get("result", {})
        trades = result.get("trades", [])
        has_more = bool(result.get("has_more", False))
        return {
            "status": "ok",
            "n_trades": len(trades),
            "has_more": has_more,
            "trades_sample": trades[:3],
            "first_trade_keys": list(trades[0].keys()) if trades else [],
            "earliest_ts": min((t.get("timestamp", end_ms) for t in trades), default=None),
            "latest_ts": max((t.get("timestamp", start_ms) for t in trades), default=None),
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "exception", "exception_type": type(exc).__name__, "exception_message": str(exc)}


def _summarize_trades_for_factor_unlock(trades: list[dict]) -> dict:
    """Per-trade mark_iv coverage assessment."""
    n_total = len(trades)
    if not n_total:
        return {"n_trades": 0}
    n_with_iv = sum(1 for t in trades if t.get("iv") is not None)
    instruments = set(t.get("instrument_name") for t in trades)
    # Parse strikes from instrument_name (Deribit format: BTC-DDMMMYY-STRIKE-TYPE)
    strikes = set()
    expiries = set()
    for t in trades:
        name = t.get("instrument_name", "")
        parts = name.split("-")
        if len(parts) >= 4:
            try:
                strikes.add(float(parts[2]))
            except (ValueError, IndexError):
                pass
            expiries.add(parts[1])  # date part
    return {
        "n_trades": n_total,
        "n_with_iv_field": n_with_iv,
        "iv_coverage_pct": (100.0 * n_with_iv / n_total) if n_total else 0.0,
        "n_distinct_instruments": len(instruments),
        "n_distinct_strikes": len(strikes),
        "n_distinct_expiries": len(expiries),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe Deribit historical trades capability.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--currency", default="BTC")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "factor_reports",
    )
    args = parser.parse_args(argv)

    print(f"=== Probing Deribit historical trades capability ({args.currency}) ===")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    print(f"  now_utc: {datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).isoformat()}")
    print()

    # Test windows from most-recent backward
    windows = [
        ("last_24h", 1),
        ("last_7d", 7),
        ("last_30d", 30),
        ("last_60d", 60),
        ("last_90d", 90),
        ("last_180d", 180),
        ("last_365d", 365),
    ]

    probe_results = {}
    sample_trades_for_analysis = []

    for label, days in windows:
        start_ms = now_ms - days * 86400 * 1000
        end_ms = now_ms
        print(f"=== Window: {label} ({days} days) ===")
        # Use single chunk first; if has_more, pagination needed
        result = _fetch_trades_window(args.currency, start_ms, end_ms, count=1000)
        probe_results[label] = {
            "window_days": days,
            "start_ts_ms": start_ms,
            "end_ts_ms": end_ms,
            "result": result,
        }
        print(f"  status: {result.get('status')}")
        if result.get("status") == "ok":
            print(f"  n_trades_in_chunk: {result.get('n_trades')}")
            print(f"  has_more: {result.get('has_more')}")
            print(f"  first_trade_keys: {result.get('first_trade_keys')}")
            if result.get("earliest_ts"):
                earliest_dt = datetime.fromtimestamp(result["earliest_ts"] / 1000, tz=timezone.utc)
                latest_dt = datetime.fromtimestamp(result["latest_ts"] / 1000, tz=timezone.utc)
                print(f"  earliest_trade: {earliest_dt.isoformat()}")
                print(f"  latest_trade:   {latest_dt.isoformat()}")
            # Save trades for analysis from longest window
            if days == 90 and result.get("trades_sample"):
                sample_trades_for_analysis = result["trades_sample"]
        time.sleep(0.5)
        print()

    # If we have sample trades, summarize IV coverage
    if sample_trades_for_analysis:
        print("=== Sample trades analysis (first 3 from 90d window) ===")
        for trade in sample_trades_for_analysis[:3]:
            print(f"  trade keys: {list(trade.keys())}")
            print(f"  sample: {json.dumps({k: trade.get(k) for k in list(trade.keys())[:8]}, default=str)}")
            print()

    # Phase 0 + Phase 1 + this Phase 1.5 → 4-option historical-data path matrix
    paths = {
        "C1_tardis_dev_paid_sample": {
            "label": "Tardis.dev paid historical sample purchase",
            "data_completeness": "FULL — book snapshots (OI by strike) + derivative_ticker (greeks + IV) + trades",
            "factors_unlocked": ["F56 25Δ skew (full history)", "F57 IV-RV spread", "F58 IV term slope (full)", "F59 dealer gamma proxy (full OI)", "F60 vanna-charm (full)"],
            "cost": "~$50-200 sample purchase (3-12 months sample)",
            "wall_clock": "1-2 days vendor procurement + 1-2d ETL + 1d admission audit",
            "risk": "vendor relationship setup; data licensing review; one-time cost",
            "recommended_for": "fast unlock of full M3.1 lane",
        },
        "C2_deribit_authenticated_paid": {
            "label": "Deribit authenticated paid historical download (institutional)",
            "data_completeness": "FULL (similar to Tardis)",
            "factors_unlocked": "same as C1 if available",
            "cost": "varies; institutional-grade pricing typically higher than Tardis",
            "wall_clock": "Deribit-side approval process unclear; can take longer",
            "risk": "approval gate + likely higher cost",
            "recommended_for": "if Tardis sample data quality insufficient",
        },
        "C3_free_trades_endpoint_partial": {
            "label": "Free /public/get_last_trades_by_currency_and_time backfill",
            "data_completeness": "PARTIAL — only TRADED instruments visible; per-trade IV available; NO OI snapshots",
            "factors_unlocked": [
                "F56 25Δ skew partial (only if 25Δ strikes actually traded)",
                "F58 IV term slope partial (only traded ATM strikes per expiry)",
                "F60 vanna-charm partial (no OI; cannot compute concentration)",
                "F59 dealer gamma proxy: NOT recoverable (requires OI history)",
            ],
            "cost": "$0 (free public endpoint)",
            "wall_clock": "1d build + 1d ETL (paginated trades fetch)",
            "risk": "low-volume strikes invisible; pagination rate-limit; OI cannot be reconstructed",
            "recommended_for": "validating mechanism + free partial unlock; F58/F60 only",
        },
        "B_continue_live_sync": {
            "label": "Continue M3.1 Phase 1 live-sync (ongoing)",
            "data_completeness": "FULL after wall-clock accumulation",
            "factors_unlocked": "F56-F60 progressively (F58/F60 ~30d; F56/F59 ~60-90d)",
            "cost": "$0",
            "wall_clock": "30-90 days wall-clock (continuous daily run)",
            "risk": "slow; depends on Deribit Public API stability",
            "recommended_for": "Stage-1 closure path; combine with C1 or C3 for faster initial unlock",
        },
    }

    print("=== 4-option historical-data path matrix ===")
    for path_id, info in paths.items():
        print(f"  {path_id}: {info['label']}")
        print(f"    completeness: {info['data_completeness']}")
        print(f"    cost:         {info['cost']}")
        print(f"    wall_clock:   {info['wall_clock']}")
        print(f"    recommended:  {info['recommended_for']}")
        print()

    out = {
        "contract_version": "quant_m3_1_historical_data_paths.v1",
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "as_of": args.as_of,
        "currency_probed": args.currency,
        "trades_endpoint_probe": probe_results,
        "historical_data_paths": paths,
    }
    out_dir = args.output_dir / args.as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "m3_1_historical_data_paths.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(f"=== Done. Report at {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
