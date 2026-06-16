"""Sync Deribit BTC+ETH DVOL daily history to local CSV.

Persists Deribit's DVOL (30d implied volatility index, free public endpoint,
no auth) as a flat daily CSV per currency. Upstream source for the v93 features
pipeline (`btc_dvol`, `eth_dvol`, derived `btc_dvol_z90`, `eth_dvol_z90`,
`max_iv_z90`).

Default coverage: from Deribit DVOL launch (2023-07-27) to today. Uses
1-year chunked pagination since the Deribit endpoint caps ~1000 rows per call.

Usage:
    python scripts/quant_research/sync_deribit_dvol_history.py
    python scripts/quant_research/sync_deribit_dvol_history.py --currencies BTC,ETH
    python scripts/quant_research/sync_deribit_dvol_history.py --start 2023-07-27 --end 2026-04-29

Output:
    artifacts/external_market_data/deribit_dvol/<currency>_dvol_daily.csv
        columns: timestamp_ms, date_utc, dvol_open, dvol_high, dvol_low, dvol_close
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
from pathlib import Path
import sys
import time

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]

DERIBIT_DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "external_market_data" / "deribit_dvol"
DERIBIT_LAUNCH_DATE = "2023-07-27"
CHUNK_DAYS = 365  # Deribit caps ~1000 rows per call; chunk yearly for safety
INTER_CHUNK_SLEEP_SEC = 0.3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Deribit DVOL daily history (free public endpoint).")
    parser.add_argument(
        "--currencies", default="BTC,ETH",
        help="Comma-separated currency list (default: BTC,ETH).",
    )
    parser.add_argument(
        "--start", default=None,
        help=f"Start date YYYY-MM-DD (default: {DERIBIT_LAUNCH_DATE}, the DVOL launch date).",
    )
    parser.add_argument(
        "--end", default=None,
        help="End date YYYY-MM-DD (default: today UTC).",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR.relative_to(ROOT)}).",
    )
    return parser.parse_args()


def _fetch_chunk(currency: str, start_ts_ms: int, end_ts_ms: int, max_retries: int = 3) -> list:
    params = {
        "currency": currency,
        "start_timestamp": int(start_ts_ms),
        "end_timestamp": int(end_ts_ms),
        "resolution": 86400,
    }
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = requests.get(DERIBIT_DVOL_URL, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()
            if "result" not in payload or "data" not in payload["result"]:
                raise RuntimeError(f"unexpected response shape: {payload!r}")
            return payload["result"]["data"]
        except (requests.RequestException, RuntimeError) as exc:
            last_err = exc
            backoff = 2 ** attempt
            print(f"    chunk fetch attempt {attempt + 1}/{max_retries} failed: {exc}; sleeping {backoff}s",
                  file=sys.stderr)
            time.sleep(backoff)
    raise RuntimeError(f"_fetch_chunk failed after {max_retries} retries: {last_err}")


def fetch_dvol_history(currency: str, start_ts_ms: int, end_ts_ms: int) -> list:
    """Fetch DVOL across the full range using yearly chunks, dedup by timestamp."""
    chunk_ms = CHUNK_DAYS * 86_400_000
    cursor = start_ts_ms
    seen_ts: set[int] = set()
    all_rows: list = []
    while cursor <= end_ts_ms:
        chunk_end = min(cursor + chunk_ms, end_ts_ms)
        chunk_start_d = datetime.fromtimestamp(cursor / 1000, tz=timezone.utc).date()
        chunk_end_d = datetime.fromtimestamp(chunk_end / 1000, tz=timezone.utc).date()
        print(f"    chunk {chunk_start_d} -> {chunk_end_d}", end="", flush=True)
        rows = _fetch_chunk(currency, cursor, chunk_end)
        new_rows = 0
        for row in rows:
            ts = int(row[0])
            if ts not in seen_ts:
                seen_ts.add(ts)
                all_rows.append(row)
                new_rows += 1
        print(f"  ({new_rows} new rows)")
        cursor = chunk_end + 86_400_000  # advance one day past chunk_end
        if cursor <= end_ts_ms:
            time.sleep(INTER_CHUNK_SLEEP_SEC)
    all_rows.sort(key=lambda r: int(r[0]))
    return all_rows


def write_csv(rows: list, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_ms", "date_utc", "dvol_open", "dvol_high", "dvol_low", "dvol_close"])
        for row in rows:
            ts_ms = int(row[0])
            d = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date().isoformat()
            writer.writerow([ts_ms, d, row[1], row[2], row[3], row[4]])


def main(argv: list[str] | None = None) -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()

    start_str = args.start or DERIBIT_LAUNCH_DATE
    end_str = args.end or date.today().isoformat()
    start_ts_ms = int(datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ts_ms = int(datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)

    currencies = [c.strip().upper() for c in args.currencies.split(",") if c.strip()]
    print(f"=== Syncing Deribit DVOL: {currencies} from {start_str} to {end_str}")
    print(f"=== Output dir: {output_dir}")

    summary: dict[str, int] = {}
    for currency in currencies:
        print(f"\n=== Fetching {currency} DVOL...")
        try:
            rows = fetch_dvol_history(currency, start_ts_ms, end_ts_ms)
        except Exception as exc:
            print(f"ERROR: {currency} fetch failed: {exc}", file=sys.stderr)
            return 1
        if not rows:
            print(f"WARNING: {currency} returned 0 rows", file=sys.stderr)
            summary[currency] = 0
            continue
        output_path = output_dir / f"{currency.lower()}_dvol_daily.csv"
        write_csv(rows, output_path)
        first_d = datetime.fromtimestamp(int(rows[0][0]) / 1000, tz=timezone.utc).date()
        last_d = datetime.fromtimestamp(int(rows[-1][0]) / 1000, tz=timezone.utc).date()
        size_kb = output_path.stat().st_size / 1024
        print(f"=== {currency}: {len(rows)} rows, {first_d} -> {last_d}, "
              f"written to {output_path.name} ({size_kb:.1f} KB)")
        summary[currency] = len(rows)

    print(f"\n=== Done. Summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
