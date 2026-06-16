"""sync_deribit_options_chain.py — daily snapshot of Deribit options
chain (OI by strike + IV by strike) for BTC + ETH.

Per M3.1 Phase 1 (Option B in Phase 0 feasibility scoping). Deribit
Public API does NOT provide HISTORICAL OI/IV by strike snapshots —
only real-time. This pipeline runs daily to ACCUMULATE history. After
~60-90 days, sufficient history exists to compute M3.1 candidates:
  F56 25Δ skew residual    — IV by 25-delta strike per expiry
  F57 IV-RV spread          — ATM IV
  F58 IV term slope         — front + mid expiry ATM IV
  F59 dealer gamma proxy    — OI by strike (CRITICAL for §E.1)
  F60 vanna-charm window    — OI concentration at ATM

Endpoints (Deribit Public REST API v2, no auth):
  /public/get_instruments?currency={c}&kind=option&expired=false
    → active option instruments (strike, expiration_timestamp, option_type)
  /public/get_book_summary_by_currency?currency={c}&kind=option
    → bulk per-instrument {mark_iv, mark_price, underlying_price,
       open_interest, volume_24h, bid_iv/ask_iv, bid_price/ask_price}

Output (one CSV per snapshot, gzipped):
  artifacts/external_market_data/deribit_options_chain/<currency>/
    snapshot_<YYYY-MM-DDTHHMMZ>.csv.gz

Schema (per row):
  snapshot_timestamp_ms, snapshot_date_utc, snapshot_utc_iso
  instrument_name, currency, option_type, strike,
    expiration_timestamp_ms, expiration_date_utc, days_to_expiry
  underlying_price, mark_price, mark_iv, bid_iv, ask_iv,
    bid_price, ask_price, open_interest, volume_24h, volume_usd_24h

Usage:
    python scripts/quant_research/sync_deribit_options_chain.py
    python scripts/quant_research/sync_deribit_options_chain.py --currencies BTC,ETH,SOL
    python scripts/quant_research/sync_deribit_options_chain.py --output-dir <path>

Idempotency: each snapshot is timestamp-named, so multiple runs per
day produce multiple snapshots. Recommend single daily run via
scheduled task at consistent UTC time (e.g., 00:30 UTC).

Rate limit: Public API ~10 req/s. This script makes 2 calls per
currency, so 4 calls for BTC+ETH = sub-second total.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]

DERIBIT_PUBLIC_API_BASE = "https://www.deribit.com/api/v2/public"
DEFAULT_CURRENCIES = ("BTC", "ETH")
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "external_market_data" / "deribit_options_chain"
INTER_REQUEST_SLEEP_SEC = 0.2

OUTPUT_COLUMNS = [
    "snapshot_timestamp_ms",
    "snapshot_date_utc",
    "snapshot_utc_iso",
    "instrument_name",
    "currency",
    "option_type",
    "strike",
    "expiration_timestamp_ms",
    "expiration_date_utc",
    "days_to_expiry",
    "underlying_price",
    "mark_price",
    "mark_iv",
    "bid_iv",
    "ask_iv",
    "bid_price",
    "ask_price",
    "open_interest",
    "volume_24h",
    "volume_usd_24h",
]


def _fetch(url: str, params: dict, max_retries: int = 3) -> dict:
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            request_url = f"{url}?{urlencode(params)}"
            request = Request(request_url, headers={"User-Agent": "EnhengClaw/0.1"})
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if "result" not in payload:
                raise RuntimeError(f"unexpected response shape: keys={list(payload.keys())}")
            return payload
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt < max_retries - 1:
                sleep = (2 ** attempt) * 0.5
                print(f"  retry {attempt + 1}/{max_retries} after {sleep:.1f}s: {exc}", file=sys.stderr)
                time.sleep(sleep)
            else:
                raise
    raise RuntimeError(f"unreachable; last_err={last_err}")


def _fetch_instruments(currency: str) -> list[dict]:
    """Returns list of active option instruments for a currency. Each item has
    {instrument_name, strike, expiration_timestamp, option_type, ...}."""
    params = {"currency": currency, "kind": "option", "expired": "false"}
    payload = _fetch(f"{DERIBIT_PUBLIC_API_BASE}/get_instruments", params)
    return list(payload["result"])


def _fetch_book_summary(currency: str) -> list[dict]:
    """Returns list of {instrument_name, mark_iv, mark_price, underlying_price,
    open_interest, volume, bid_iv, ask_iv, bid_price, ask_price, ...}."""
    params = {"currency": currency, "kind": "option"}
    payload = _fetch(f"{DERIBIT_PUBLIC_API_BASE}/get_book_summary_by_currency", params)
    return list(payload["result"])


def _parse_iso_date(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).date().isoformat()


def _parse_iso_dt(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()


def fetch_snapshot(currency: str, snapshot_ts_ms: int) -> list[dict]:
    """Fetch + merge instruments and book_summary into snapshot rows."""
    print(f"  [{currency}] fetching active option instruments...")
    instruments = _fetch_instruments(currency)
    print(f"  [{currency}] {len(instruments)} active option instruments")
    time.sleep(INTER_REQUEST_SLEEP_SEC)

    print(f"  [{currency}] fetching book summary (bulk OI + IV)...")
    book_summary = _fetch_book_summary(currency)
    print(f"  [{currency}] {len(book_summary)} book summary rows")

    # Index by instrument_name
    inst_by_name = {it["instrument_name"]: it for it in instruments}
    snapshot_iso = _parse_iso_dt(snapshot_ts_ms)
    snapshot_date = _parse_iso_date(snapshot_ts_ms)

    rows: list[dict] = []
    for bs in book_summary:
        name = bs.get("instrument_name")
        inst = inst_by_name.get(name)
        if not inst:
            # book_summary instrument not in instruments list — skip (e.g., expired between calls)
            continue
        expiry_ms = inst.get("expiration_timestamp")
        days_to_expiry = (
            (int(expiry_ms) - snapshot_ts_ms) / (1000 * 86400) if expiry_ms is not None else None
        )
        row = {
            "snapshot_timestamp_ms": snapshot_ts_ms,
            "snapshot_date_utc": snapshot_date,
            "snapshot_utc_iso": snapshot_iso,
            "instrument_name": name,
            "currency": currency,
            "option_type": inst.get("option_type"),
            "strike": inst.get("strike"),
            "expiration_timestamp_ms": expiry_ms,
            "expiration_date_utc": _parse_iso_date(expiry_ms),
            "days_to_expiry": round(days_to_expiry, 4) if days_to_expiry is not None else None,
            "underlying_price": bs.get("underlying_price"),
            "mark_price": bs.get("mark_price"),
            "mark_iv": bs.get("mark_iv"),
            "bid_iv": bs.get("bid_iv"),
            "ask_iv": bs.get("ask_iv"),
            "bid_price": bs.get("bid_price"),
            "ask_price": bs.get("ask_price"),
            "open_interest": bs.get("open_interest"),
            "volume_24h": bs.get("volume"),
            "volume_usd_24h": bs.get("volume_usd"),
        }
        rows.append(row)
    return rows


def write_snapshot_csv(rows: list[dict], output_dir: Path, currency: str, snapshot_ts_ms: int) -> Path:
    """Write rows to artifacts/.../<currency>/snapshot_<YYYY-MM-DDTHHMMZ>.csv.gz"""
    snapshot_dt = datetime.fromtimestamp(snapshot_ts_ms / 1000, tz=timezone.utc)
    # Filename: snapshot_<YYYYMMDDTHHMMZ>.csv.gz  (no colons for Windows safety)
    label = snapshot_dt.strftime("%Y%m%dT%H%MZ")
    out_dir = output_dir / currency
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"snapshot_{label}.csv.gz"
    with gzip.open(out_path, "wt", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in OUTPUT_COLUMNS})
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Deribit options chain daily snapshot.")
    parser.add_argument(
        "--currencies", default=",".join(DEFAULT_CURRENCIES),
        help=f"Comma-separated currencies (default: {','.join(DEFAULT_CURRENCIES)}). e.g. BTC,ETH,SOL",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help=f"Output dir (default: {DEFAULT_OUTPUT_DIR.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--write-summary", action="store_true",
        help="Also write per-currency snapshot summary JSON for diagnostics.",
    )
    args = parser.parse_args()

    currencies = [c.strip().upper() for c in args.currencies.split(",") if c.strip()]
    snapshot_ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    snapshot_iso = _parse_iso_dt(snapshot_ts_ms)
    print(f"=== Deribit options chain snapshot ===")
    print(f"  snapshot_utc:   {snapshot_iso}")
    print(f"  currencies:     {currencies}")
    print(f"  output_dir:     {args.output_dir}")
    print()

    summary = {
        "contract_version": "quant_deribit_options_chain_snapshot.v1",
        "snapshot_timestamp_ms": snapshot_ts_ms,
        "snapshot_utc_iso": snapshot_iso,
        "currencies": [],
    }

    for currency in currencies:
        try:
            rows = fetch_snapshot(currency, snapshot_ts_ms)
            if not rows:
                print(f"  [{currency}] WARN: 0 rows")
                summary["currencies"].append({
                    "currency": currency,
                    "n_rows": 0,
                    "status": "empty",
                })
                continue
            out_path = write_snapshot_csv(rows, args.output_dir, currency, snapshot_ts_ms)
            n_strikes = len(set(r["strike"] for r in rows if r["strike"] is not None))
            n_expiries = len(set(r["expiration_date_utc"] for r in rows if r["expiration_date_utc"]))
            sum_oi = sum(r["open_interest"] or 0 for r in rows)
            print(f"  [{currency}] wrote {len(rows)} rows → {out_path.relative_to(ROOT)}")
            print(f"  [{currency}]   distinct strikes: {n_strikes}, distinct expiries: {n_expiries}")
            print(f"  [{currency}]   total open_interest sum: {sum_oi:.2f}")
            summary["currencies"].append({
                "currency": currency,
                "n_rows": len(rows),
                "n_distinct_strikes": n_strikes,
                "n_distinct_expiries": n_expiries,
                "total_open_interest": float(sum_oi),
                "output_path": str(out_path.relative_to(ROOT)),
                "status": "ok",
            })
            time.sleep(INTER_REQUEST_SLEEP_SEC)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{currency}] FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
            summary["currencies"].append({
                "currency": currency,
                "n_rows": 0,
                "status": "failed",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            })

    if args.write_summary:
        summary_path = args.output_dir / "_snapshot_summary_latest.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print()
        print(f"  summary → {summary_path.relative_to(ROOT)}")

    print()
    print("=== Done ===")
    return 0 if all(c["status"] == "ok" for c in summary["currencies"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
