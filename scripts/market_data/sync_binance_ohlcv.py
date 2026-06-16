from __future__ import annotations

import argparse
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

from scripts.market_data.binance_ohlcv import (
    DEFAULT_INTERVALS,
    DEFAULT_MARKETS,
    sync_binance_ohlcv,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync Binance OHLCV history for research-only workflows.")
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=None,
        help="Optional Binance symbols to sync, e.g. ETHUSDT BTCUSDT. If omitted, discover from the workbench.",
    )
    parser.add_argument(
        "--markets",
        default="spot,usdm_perp",
        help="Comma-separated market list. Defaults to spot,usdm_perp.",
    )
    parser.add_argument(
        "--intervals",
        default="1h,4h,1d",
        help="Comma-separated interval list. Defaults to 1h,4h,1d.",
    )
    parser.add_argument(
        "--mode",
        choices=("bootstrap", "refresh"),
        required=True,
        help="Sync mode. bootstrap pulls archive then refreshes current bars; refresh only updates recent bars.",
    )
    parser.add_argument(
        "--external-root",
        type=Path,
        default=None,
        help="External Binance OHLCV store root. Defaults to %%LOCALAPPDATA%%\\EnhengClaw\\market_history\\binance_ohlcv.",
    )
    parser.add_argument(
        "--workbench-root",
        type=Path,
        default=ROOT / "artifacts" / "research_workbench",
        help="Workbench root used for auto-discovery when --symbols is omitted.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = sync_binance_ohlcv(
            external_root=args.external_root,
            symbols=args.symbols,
            markets=_split_csv(args.markets, DEFAULT_MARKETS),
            intervals=_split_csv(args.intervals, DEFAULT_INTERVALS),
            mode=args.mode,
            workbench_root=args.workbench_root,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _split_csv(raw_value: str, default: tuple[str, ...]) -> tuple[str, ...]:
    values = [item.strip() for item in str(raw_value).split(",") if item.strip()]
    return tuple(values) if values else default


if __name__ == "__main__":
    raise SystemExit(main())
