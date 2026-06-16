from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.onchain_stablecoin import (  # noqa: E402
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_MAX_PAGES_PER_WINDOW,
    DEFAULT_PAGE_SIZE,
    DEFAULT_REFRESH_OVERLAP_DAYS,
    DEFAULT_TRANSFER_PROVIDER,
    DEFAULT_SYNC_MODE,
    DEFAULT_MIN_SPLIT_BLOCK_SPAN,
    DEFAULT_WHALE_THRESHOLD,
    run_m3_2_stablecoin_sync,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync Ethereum stablecoin plumbing aggregates for M3.2."
    )
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--mode", default=DEFAULT_SYNC_MODE, choices=("auto", "bootstrap", "refresh"))
    parser.add_argument("--refresh-overlap-days", type=int, default=DEFAULT_REFRESH_OVERLAP_DAYS)
    parser.add_argument("--symbols", default="USDT,USDC,DAI")
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--whale-threshold", type=float, default=DEFAULT_WHALE_THRESHOLD)
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument(
        "--transfer-provider",
        choices=("alchemy_transfers", "eth_rpc_logs"),
        default=DEFAULT_TRANSFER_PROVIDER,
    )
    parser.add_argument(
        "--max-pages-per-window",
        "--max-pages-per-token",
        dest="max_pages_per_window",
        type=int,
        default=DEFAULT_MAX_PAGES_PER_WINDOW,
    )
    parser.add_argument("--min-split-block-span", type=int, default=DEFAULT_MIN_SPLIT_BLOCK_SPAN)
    parser.add_argument("--start-date", type=date.fromisoformat, default=None)
    parser.add_argument("--end-date", type=date.fromisoformat, default=None)
    parser.add_argument("--address-label-root", type=Path, default=None)
    parser.add_argument("--address-label-snapshot-path", type=Path, default=None)
    parser.add_argument("--address-label-as-of-date", type=date.fromisoformat, default=None)
    parser.add_argument("--report-path", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    symbols = [item.strip().upper() for item in str(args.symbols).split(",") if item.strip()]
    try:
        summary = run_m3_2_stablecoin_sync(
            lookback_days=args.lookback_days,
            mode=args.mode,
            refresh_overlap_days=args.refresh_overlap_days,
            transfer_provider=args.transfer_provider,
            external_root=args.external_root,
            token_symbols=symbols,
            whale_threshold=args.whale_threshold,
            page_size=args.page_size,
            max_pages_per_window=args.max_pages_per_window,
            min_split_block_span=args.min_split_block_span,
            start_date_override=args.start_date,
            end_date_override=args.end_date,
            address_label_root=args.address_label_root,
            address_label_snapshot_path=args.address_label_snapshot_path,
            address_label_as_of_date=args.address_label_as_of_date,
            report_path=args.report_path,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
