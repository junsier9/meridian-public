"""Sync OKX 8h funding-rate history per USDT-SWAP symbol to local CSV cache.

Persists OKX's per-symbol funding-rate-history (free public endpoint, no auth
required — `OKX_API` env var is optional and only used by OKX private endpoints
which this script does NOT call). Output matches the layout consumed by
`scripts/quant_research/compute_cross_venue_funding_factor_report.py` (M2.2 F14
audit) so re-running this sync extends the rolling window the audit operates on.

Default coverage: top-30 universe USDT-SWAP symbols. OKX's public endpoint caps
~3 months of rolling history per symbol; some recently-listed symbols return
~6 months.

Usage:
    python scripts/quant_research/sync_okx_funding_history.py
    python scripts/quant_research/sync_okx_funding_history.py --symbols BTC,ETH,SOL
    python scripts/quant_research/sync_okx_funding_history.py --mode bootstrap
    python scripts/quant_research/sync_okx_funding_history.py --mode refresh
    python scripts/quant_research/sync_okx_funding_history.py --output-dir <custom>

Output:
    %LOCALAPPDATA%\\EnhengClaw\\okx_funding\\<BASE>_funding_8h.csv
        columns: fundingTime, fundingRate, realizedRate, instId

Modes:
    bootstrap (default): full re-fetch of available history; overwrites cache.
    refresh: paginate only until reaching the last cached fundingTime; appends
             new rows on top of existing cache. Idempotent.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]

OKX_FUNDING_HISTORY_URL = "https://www.okx.com/api/v5/public/funding-rate-history"
OKX_FUNDING_LIMIT_PER_PAGE = 100
OKX_INTER_PAGE_SLEEP_SEC = 0.25  # ~4 req/s, well under OKX's 10 req/2s public rate limit
OKX_MAX_PAGES_PER_SYMBOL = 20  # ~2000 rows = ~7 months at 8h grain (safety upper bound)

# Top-30 universe matching M2.1 / M2.2 / M2.3 audit panels. Subjects without OKX
# USDT-SWAP listings will be skipped silently per the OKX API response.
DEFAULT_TOP30_BASES: tuple[str, ...] = (
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ZEC", "BNB", "TAO", "TRX", "ADA",
    "PEPE", "PAXG", "SUI", "LINK", "AVAX", "LTC", "FET", "NEAR", "ENA", "AAVE",
    "WLD", "TON", "PENGU", "TRUMP", "KITE", "UNI", "DASH", "XPL", "BCH", "ASTER",
)

# Known unavailable on OKX USDT-SWAP at sync date 2026-04-30:
#   PAXG (no swap pair on OKX)
#   FET   (no swap pair on OKX)
KNOWN_OKX_MISSING: frozenset[str] = frozenset({"PAXG", "FET"})


def _resolve_default_output_dir() -> Path:
    """Resolve LOCALAPPDATA/EnhengClaw/okx_funding (Windows) or
    ~/.local/share/EnhengClaw/okx_funding (POSIX)."""
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        return Path(localappdata) / "EnhengClaw" / "okx_funding"
    return Path.home() / ".local" / "share" / "EnhengClaw" / "okx_funding"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync OKX 8h funding-rate history (free public endpoint)."
    )
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_TOP30_BASES),
        help="Comma-separated base-asset list (e.g. 'BTC,ETH,SOL'). Defaults to "
        "the top-30 universe.",
    )
    parser.add_argument(
        "--mode",
        choices=("bootstrap", "refresh"),
        default="bootstrap",
        help="bootstrap = full re-fetch (default); refresh = only append rows newer "
        "than last cached fundingTime.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=f"Output directory (default: {_resolve_default_output_dir()}).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=OKX_MAX_PAGES_PER_SYMBOL,
        help=f"Safety upper bound on pages per symbol (default: {OKX_MAX_PAGES_PER_SYMBOL}; "
        f"~{OKX_MAX_PAGES_PER_SYMBOL * OKX_FUNDING_LIMIT_PER_PAGE / 3 / 30:.1f} months).",
    )
    parser.add_argument(
        "--inter-page-sleep",
        type=float,
        default=OKX_INTER_PAGE_SLEEP_SEC,
        help=f"Seconds to sleep between paginated requests (default: {OKX_INTER_PAGE_SLEEP_SEC}).",
    )
    return parser.parse_args(argv)


def _http_get_json(url: str, *, timeout: float = 15.0, max_retries: int = 3) -> dict:
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            with urlopen(Request(url, headers={"User-Agent": "EnhengClaw/0.1"}), timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, OSError) as exc:
            last_err = exc
            backoff = 2 ** attempt
            print(
                f"      HTTP attempt {attempt + 1}/{max_retries} failed: {exc}; sleeping {backoff}s",
                file=sys.stderr,
            )
            time.sleep(backoff)
    raise RuntimeError(f"OKX request failed after {max_retries} retries: {last_err}")


def _fetch_funding_pages(
    base: str,
    *,
    stop_at_funding_time_ms: int | None,
    max_pages: int,
    inter_page_sleep: float,
) -> list[dict]:
    """Paginate OKX funding-rate-history backward in time until either:
      - response empty / shorter than page limit
      - reached `stop_at_funding_time_ms` (refresh mode)
      - hit `max_pages` safety bound
    Returns rows newest-first (OKX-native order).
    """
    inst = f"{base}-USDT-SWAP"
    rows: list[dict] = []
    after_cursor = ""  # OKX 'after' = older than this fundingTime
    for page_idx in range(max_pages):
        url = (
            f"{OKX_FUNDING_HISTORY_URL}?instId={inst}&limit={OKX_FUNDING_LIMIT_PER_PAGE}"
            + (f"&after={after_cursor}" if after_cursor else "")
        )
        payload = _http_get_json(url)
        code = payload.get("code", "?")
        msg = payload.get("msg", "")
        if str(code) != "0":
            print(f"      OKX API non-zero code for {inst}: code={code} msg={msg!r}", file=sys.stderr)
            break
        data = payload.get("data") or []
        if not data:
            break
        # Optional refresh-mode early stop: drop rows older than already-cached
        if stop_at_funding_time_ms is not None:
            kept = [r for r in data if int(r["fundingTime"]) > stop_at_funding_time_ms]
            rows.extend(kept)
            if len(kept) < len(data):
                break  # crossed the existing-coverage boundary
        else:
            rows.extend(data)
        oldest_time = int(data[-1]["fundingTime"])
        if len(data) < OKX_FUNDING_LIMIT_PER_PAGE:
            break  # last page
        after_cursor = str(oldest_time)
        time.sleep(inter_page_sleep)
    return rows


def _read_existing_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def _write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["fundingTime", "fundingRate", "realizedRate", "instId"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _merge_rows(existing: list[dict], new: list[dict]) -> list[dict]:
    """Deduplicate by fundingTime, sort newest-first (OKX convention)."""
    seen: dict[int, dict] = {}
    for r in existing + new:
        try:
            ts = int(r["fundingTime"])
        except (KeyError, ValueError, TypeError):
            continue
        seen[ts] = r
    merged = sorted(seen.values(), key=lambda r: int(r["fundingTime"]), reverse=True)
    return merged


def sync_one_symbol(
    base: str,
    *,
    output_dir: Path,
    mode: str,
    max_pages: int,
    inter_page_sleep: float,
) -> dict:
    out_path = output_dir / f"{base}_funding_8h.csv"
    if base in KNOWN_OKX_MISSING:
        return {"base": base, "status": "known_missing_skipped", "n_rows": 0, "path": str(out_path)}

    existing = _read_existing_csv(out_path) if mode == "refresh" else []
    last_cached_ts = (
        max(int(r["fundingTime"]) for r in existing) if existing else None
    )
    if mode == "refresh" and last_cached_ts is None:
        # No existing cache → behave like bootstrap for this symbol
        mode = "bootstrap"

    print(
        f"  {base}: mode={mode}, "
        f"existing_rows={len(existing)}, "
        f"last_cached_ts="
        + (str(last_cached_ts) if last_cached_ts else "(none)")
    )
    new_rows = _fetch_funding_pages(
        base,
        stop_at_funding_time_ms=last_cached_ts if mode == "refresh" else None,
        max_pages=max_pages,
        inter_page_sleep=inter_page_sleep,
    )
    if not new_rows and not existing:
        return {"base": base, "status": "no_data", "n_rows": 0, "path": str(out_path)}
    merged = _merge_rows(existing, new_rows)
    _write_csv(merged, out_path)
    if not merged:
        return {"base": base, "status": "empty_after_merge", "n_rows": 0, "path": str(out_path)}
    first_ts = int(merged[-1]["fundingTime"])
    last_ts = int(merged[0]["fundingTime"])
    first_d = datetime.fromtimestamp(first_ts / 1000, tz=timezone.utc).date()
    last_d = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc).date()
    return {
        "base": base,
        "status": "ok",
        "n_rows": len(merged),
        "n_new": len(new_rows),
        "first_date_utc": first_d.isoformat(),
        "last_date_utc": last_d.isoformat(),
        "path": str(out_path),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = (args.output_dir or _resolve_default_output_dir()).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    bases = [b.strip().upper() for b in args.symbols.split(",") if b.strip()]
    print(f"=== Syncing OKX 8h funding for {len(bases)} bases (mode={args.mode})")
    print(f"=== Output: {output_dir}")
    print()

    summaries: list[dict] = []
    for base in bases:
        try:
            summary = sync_one_symbol(
                base,
                output_dir=output_dir,
                mode=args.mode,
                max_pages=args.max_pages,
                inter_page_sleep=args.inter_page_sleep,
            )
            summaries.append(summary)
            if summary.get("status") == "ok":
                print(
                    f"    {base}: {summary['n_rows']} rows "
                    f"({summary.get('n_new', 0)} new), "
                    f"{summary['first_date_utc']} -> {summary['last_date_utc']}"
                )
            else:
                print(f"    {base}: {summary['status']}")
        except Exception as exc:  # noqa: BLE001 — single-symbol failure shouldn't kill the run
            summaries.append({"base": base, "status": "error", "error": str(exc)})
            print(f"    {base}: ERROR {exc}", file=sys.stderr)

    n_ok = sum(1 for s in summaries if s.get("status") == "ok")
    n_skip = sum(1 for s in summaries if s.get("status") in ("known_missing_skipped", "no_data"))
    n_err = sum(1 for s in summaries if s.get("status") == "error")
    print()
    print(f"=== Done. ok={n_ok}, skipped={n_skip}, errors={n_err}, total={len(summaries)}")
    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
