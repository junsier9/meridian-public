from __future__ import annotations

import argparse
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.onchain_cryptoquant import (  # noqa: E402
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_REFRESH_OVERLAP_DAYS,
    DEFAULT_SYNC_MODE,
    run_cryptoquant_stablecoin_sync,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync CryptoQuant stablecoin supply and exchange-flow history for M3.2."
    )
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--mode", default=DEFAULT_SYNC_MODE, choices=("auto", "bootstrap", "refresh"))
    parser.add_argument("--refresh-overlap-days", type=int, default=DEFAULT_REFRESH_OVERLAP_DAYS)
    parser.add_argument("--tokens", default="usdt_eth,usdc,dai,tusd,usdt_trx,usdt_omni")
    parser.add_argument("--exchanges", default="all_exchange,spot_exchange,derivative_exchange")
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--report-path", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    token_ids = [item.strip().lower() for item in str(args.tokens).split(",") if item.strip()]
    exchanges = [item.strip().lower() for item in str(args.exchanges).split(",") if item.strip()]
    summary = run_cryptoquant_stablecoin_sync(
        lookback_days=args.lookback_days,
        mode=args.mode,
        refresh_overlap_days=args.refresh_overlap_days,
        external_root=args.external_root,
        token_ids=token_ids,
        exchanges=exchanges,
        report_path=args.report_path,
    )
    print(summary["latest_summary_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
