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

from enhengclaw.quant_research.coinapi_spot_sync import run_quant_coinapi_spot_sync
from enhengclaw.quant_research.runtime_support import QUANT_INPUT_ROOT
from scripts.market_data.coinapi_ohlcv import DEFAULT_EXCHANGE_ID, DEFAULT_QUOTE_ASSET


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync CoinAPI spot OHLCV for the Quant Top100 workflow."
    )
    parser.add_argument("--as-of", required=True, help="Quant as-of date in YYYY-MM-DD format.")
    parser.add_argument("--mode", choices=("refresh", "bootstrap"), required=True)
    parser.add_argument("--quant-input-root", type=Path, default=QUANT_INPUT_ROOT)
    parser.add_argument("--external-root", type=Path, default=None)
    parser.add_argument("--exchange-id", default=DEFAULT_EXCHANGE_ID)
    parser.add_argument("--quote-asset", default=DEFAULT_QUOTE_ASSET)
    parser.add_argument("--refresh-catalog", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_quant_coinapi_spot_sync(
            as_of=args.as_of,
            mode=args.mode,
            quant_input_root=args.quant_input_root,
            external_root=args.external_root,
            exchange_id=args.exchange_id,
            quote_asset=args.quote_asset,
            refresh_catalog=args.refresh_catalog,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
