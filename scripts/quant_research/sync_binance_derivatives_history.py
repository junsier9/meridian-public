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

from enhengclaw.quant_research.binance_derivatives import DEFAULT_INTERVALS, sync_binance_derivatives_history


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync Binance USD-M perpetual derivatives history for Quant Research Lab.")
    parser.add_argument("--symbols", nargs="+", required=True, help="One or more Binance symbols, e.g. ETHUSDT SUIUSDT.")
    parser.add_argument("--intervals", default="4h,1d", help="Comma-separated interval list. Defaults to 4h,1d.")
    parser.add_argument("--mode", choices=("bootstrap", "refresh"), default="refresh")
    parser.add_argument("--external-root", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = sync_binance_derivatives_history(
            symbols=args.symbols,
            intervals=_split_csv(args.intervals, DEFAULT_INTERVALS),
            mode=args.mode,
            external_root=args.external_root,
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
