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

from enhengclaw.quant_research.coinglass_spot_ohlcv import sync_coinglass_spot_ohlcv
from enhengclaw.quant_research.runtime_support import QUANT_INPUT_ROOT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync CoinGlass spot OHLCV for the Quant Research strategy scope.")
    parser.add_argument("--as-of", required=True, help="Quant as-of date in YYYY-MM-DD format.")
    parser.add_argument("--intervals", default="1h", help="Comma-separated intervals. Defaults to 1h.")
    parser.add_argument("--mode", choices=("bootstrap", "refresh"), default="bootstrap")
    parser.add_argument("--quant-input-root", type=Path, default=QUANT_INPUT_ROOT)
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--lookback-days", type=int, default=None)
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--symbols", nargs="*", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = sync_coinglass_spot_ohlcv(
            as_of=args.as_of,
            intervals=tuple(item.strip() for item in args.intervals.split(",") if item.strip()),
            mode=args.mode,
            quant_input_root=args.quant_input_root,
            external_root=args.external_root,
            lookback_days=args.lookback_days,
            max_symbols=args.max_symbols,
            symbols=args.symbols,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
