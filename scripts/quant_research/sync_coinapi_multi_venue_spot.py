"""Sync CoinAPI spot OHLCV per-exchange to per-exchange external_root caches.

Wraps `scripts.market_data.coinapi_ohlcv.sync_coinapi_ohlcv` for the multi-
venue case used by M2.1 (cross-venue spot dispersion). The default Binance
sync writes to `LOCALAPPDATA/EnhengClaw/market_history/coinapi_ohlcv/` (per
the `DEFAULT_EXTERNAL_ROOT_NAME` constant); to avoid clobbering that catalog,
non-Binance venues use a separate per-exchange root layout:

    LOCALAPPDATA/EnhengClaw/coinapi_ohlcv_<EXCHANGE>/spot/<SYM>/<intv>/...

This wrapper drives that layout. The default exchange list is COINBASE +
OKEX + BYBITSPOT (the three additional venues with strong USDT-pair coverage
on the top-30 universe per the M2.1 v1 audit). BINANCE is intentionally
excluded by default — it has its own canonical root managed by
`run_quant_coinapi_spot_sync.py`.

Usage:
    python scripts/quant_research/sync_coinapi_multi_venue_spot.py
    python scripts/quant_research/sync_coinapi_multi_venue_spot.py --exchanges OKEX,BYBITSPOT
    python scripts/quant_research/sync_coinapi_multi_venue_spot.py --symbols BTC,ETH --intervals 1d,4h
    python scripts/quant_research/sync_coinapi_multi_venue_spot.py --mode refresh

Output:
    %LOCALAPPDATA%\\EnhengClaw\\coinapi_ohlcv_COINBASE\\spot\\<SYM>\\<intv>\\<YYYY-MM>.csv.gz
    %LOCALAPPDATA%\\EnhengClaw\\coinapi_ohlcv_OKEX\\spot\\<SYM>\\<intv>\\<YYYY-MM>.csv.gz
    %LOCALAPPDATA%\\EnhengClaw\\coinapi_ohlcv_BYBITSPOT\\spot\\<SYM>\\<intv>\\<YYYY-MM>.csv.gz
        columns: exchange, market_type, symbol, interval, open_time_ms,
                 close_time_ms, open, high, low, close, volume, quote_volume,
                 trade_count, taker_buy_base_volume, taker_buy_quote_volume, source

Modes:
    bootstrap (default): full re-fetch of available history per (exchange, symbol).
    refresh: only fetch new bars since last partition's close_time. Idempotent.

Requires: `CoinAPI` env var (CoinAPI key, free tier sufficient for 1d).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.market_data.coinapi_ohlcv import sync_coinapi_ohlcv  # noqa: E402


# Per the M2.1 v1 admission audit, these three CoinAPI venue ids cover
# 25-29 of the top-30 universe USDT pairs. BINANCE is excluded by default
# (canonical Binance root is managed elsewhere).
DEFAULT_EXCHANGES: tuple[str, ...] = ("COINBASE", "OKEX", "BYBITSPOT")
DEFAULT_INTERVALS: tuple[str, ...] = ("1d",)

# Top-30 universe matching M2.1 / M2.2 / M2.3 panels.
DEFAULT_TOP30_BASES: tuple[str, ...] = (
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ZEC", "BNB", "TAO", "TRX", "ADA",
    "PEPE", "PAXG", "SUI", "LINK", "AVAX", "LTC", "FET", "NEAR", "ENA", "AAVE",
    "WLD", "TON", "PENGU", "TRUMP", "KITE", "UNI", "DASH", "XPL", "BCH", "ASTER",
)

# Known per-venue USDT-pair non-listings (from M2.1 v1 probe).
PER_VENUE_KNOWN_MISSING: dict[str, frozenset[str]] = {
    "COINBASE": frozenset(
        # Coinbase USDT-pair coverage is sparse; only the 10 majors below are
        # USDT-paired. The other 20 are USD-only on Coinbase and we don't
        # collect them here.
        {b for b in DEFAULT_TOP30_BASES if b not in {
            "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "LINK", "AVAX", "FET", "NEAR"
        }}
    ),
    "OKEX": frozenset({"TAO"}),
    "BYBITSPOT": frozenset({"TAO", "ZEC", "PAXG", "KITE", "DASH"}),
}


def _resolve_exchange_root(exchange_id: str) -> Path:
    """Resolve LOCALAPPDATA/EnhengClaw/coinapi_ohlcv_<EXCHANGE>/ (Windows) or
    POSIX equivalent. Mirrors the convention established in M2.1 v1."""
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(localappdata) / "EnhengClaw" if localappdata else Path.home() / ".local" / "share" / "EnhengClaw"
    # Special case: if the caller asks for BINANCE, route to the canonical
    # market_history root (not a per-exchange root). This matches the legacy
    # default-named root managed by `run_quant_coinapi_spot_sync.py`.
    if exchange_id.upper() == "BINANCE":
        return base / "market_history" / "coinapi_ohlcv"
    return base / f"coinapi_ohlcv_{exchange_id.upper()}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync CoinAPI spot OHLCV per-exchange (multi-venue)."
    )
    parser.add_argument(
        "--exchanges",
        default=",".join(DEFAULT_EXCHANGES),
        help="Comma-separated CoinAPI exchange ids (e.g. 'COINBASE,OKEX,BYBITSPOT'). "
        "BINANCE is intentionally excluded by default.",
    )
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_TOP30_BASES),
        help="Comma-separated base-asset list. Will be intersected with each venue's "
        "known-listings (skip-list per-venue).",
    )
    parser.add_argument(
        "--quote-asset",
        default="USDT",
        help="Quote asset (default: USDT). Coinbase has many bases as USD-only — pass "
        "'USD' if you want to fetch the broader Coinbase coverage.",
    )
    parser.add_argument(
        "--intervals",
        default=",".join(DEFAULT_INTERVALS),
        help="Comma-separated interval list (default: '1d'). E.g. '1d,4h,1h'.",
    )
    parser.add_argument(
        "--mode",
        choices=("bootstrap", "refresh"),
        default="bootstrap",
        help="bootstrap = full re-fetch of available history; refresh = extend from "
        "last cached bar.",
    )
    parser.add_argument(
        "--refresh-catalog",
        action="store_true",
        help="Force re-fetch of CoinAPI's per-exchange symbol catalog (slow but ensures "
        "newly-listed symbols on the venue are picked up).",
    )
    return parser.parse_args()


def sync_one_exchange(
    *,
    exchange_id: str,
    bases: list[str],
    quote_asset: str,
    intervals: tuple[str, ...],
    mode: str,
    refresh_catalog: bool,
) -> dict:
    """Sync one venue's USDT pairs into LOCALAPPDATA/EnhengClaw/coinapi_ohlcv_<EXCHANGE>/."""
    root = _resolve_exchange_root(exchange_id)
    root.mkdir(parents=True, exist_ok=True)

    skip_set = PER_VENUE_KNOWN_MISSING.get(exchange_id.upper(), frozenset())
    target_bases = [b for b in bases if b not in skip_set]
    skipped = [b for b in bases if b in skip_set]
    target_symbols = [f"{b}{quote_asset}" for b in target_bases]

    print(f"  {exchange_id}: root={root}")
    print(f"    target {len(target_symbols)} symbols (skipped known-missing: {sorted(skipped)})")
    if not target_symbols:
        return {
            "exchange": exchange_id,
            "status": "no_targets",
            "root": str(root),
            "skipped": sorted(skipped),
        }

    try:
        result = sync_coinapi_ohlcv(
            external_root=root,
            symbols=target_symbols,
            intervals=intervals,
            mode=mode,
            exchange_id=exchange_id,
            quote_asset=quote_asset,
            refresh_catalog=refresh_catalog,
        )
    except Exception as exc:  # noqa: BLE001 — venue-level failure shouldn't kill other venues
        return {
            "exchange": exchange_id,
            "status": "error",
            "error": str(exc),
            "root": str(root),
            "skipped": sorted(skipped),
        }
    missing = result.get("missing_requested_symbols") or []
    return {
        "exchange": exchange_id,
        "status": "ok",
        "intervals": list(intervals),
        "root": str(root),
        "n_target": len(target_symbols),
        "missing_at_sync": sorted(missing),
        "skipped_known_missing": sorted(skipped),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args()

    exchanges = [e.strip().upper() for e in args.exchanges.split(",") if e.strip()]
    bases = [b.strip().upper() for b in args.symbols.split(",") if b.strip()]
    intervals = tuple(i.strip() for i in args.intervals.split(",") if i.strip())

    print(f"=== Syncing CoinAPI spot for venues: {exchanges}")
    print(f"=== Quote asset: {args.quote_asset}, Intervals: {intervals}, Mode: {args.mode}")
    print(f"=== Targets: {len(bases)} base assets")
    print()

    summaries: list[dict] = []
    for venue in exchanges:
        summary = sync_one_exchange(
            exchange_id=venue,
            bases=bases,
            quote_asset=args.quote_asset,
            intervals=intervals,
            mode=args.mode,
            refresh_catalog=args.refresh_catalog,
        )
        summaries.append(summary)
        if summary.get("status") == "ok":
            print(
                f"    {venue}: OK  n_target={summary['n_target']}  "
                f"missing_at_sync={summary['missing_at_sync']}"
            )
        elif summary.get("status") == "no_targets":
            print(f"    {venue}: no_targets (all bases on per-venue skip-list)")
        else:
            print(f"    {venue}: ERROR {summary.get('error')}", file=sys.stderr)
        print()

    n_ok = sum(1 for s in summaries if s.get("status") == "ok")
    n_err = sum(1 for s in summaries if s.get("status") == "error")
    print(f"=== Done. ok={n_ok}, errors={n_err}, total={len(summaries)}")
    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
