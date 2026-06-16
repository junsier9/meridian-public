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

from scripts.market_data.coinapi_ohlcv import (
    DEFAULT_EXCHANGE_ID,
    DEFAULT_EXTERNAL_ROOT_NAME,
    DEFAULT_INTERVALS,
    DEFAULT_QUOTE_ASSET,
    sync_coinapi_ohlcv,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync CoinAPI historical OHLCV into the normalized quant-research store contract."
    )
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=None,
        help="Optional canonical spot symbols to sync, e.g. ETHUSDT BTCUSDT. If omitted, discover from the latest quant input.",
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
        help="Sync mode. bootstrap backfills the requested window or default lookback; refresh only resumes from the latest stored bar.",
    )
    parser.add_argument(
        "--external-root",
        type=Path,
        default=None,
        help=(
            "External CoinAPI OHLCV store root. Defaults to "
            f"%%LOCALAPPDATA%%\\EnhengClaw\\{DEFAULT_EXTERNAL_ROOT_NAME}."
        ),
    )
    parser.add_argument(
        "--exchange-id",
        default=DEFAULT_EXCHANGE_ID,
        help="CoinAPI exchange_id used for spot symbol discovery and OHLCV requests. Defaults to BINANCE for workflow compatibility.",
    )
    parser.add_argument(
        "--quote-asset",
        default=DEFAULT_QUOTE_ASSET,
        help="Quote asset filter used for symbol catalog construction. Defaults to USDT.",
    )
    parser.add_argument(
        "--quant-input-root",
        type=Path,
        default=ROOT / "artifacts" / "quant_research" / "_quant_inputs",
        help="Quant input root used for symbol auto-discovery when --symbols is omitted.",
    )
    parser.add_argument(
        "--time-start",
        default=None,
        help="Optional ISO-8601 start time/date used for bootstrap or bounded refresh runs.",
    )
    parser.add_argument(
        "--time-end",
        default=None,
        help="Optional ISO-8601 end time/date used for bounded refresh or smoke runs.",
    )
    parser.add_argument(
        "--refresh-catalog",
        action="store_true",
        help="Force-refresh the local CoinAPI symbol catalog and exchange mapping before syncing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = sync_coinapi_ohlcv(
            external_root=args.external_root,
            symbols=args.symbols,
            intervals=_split_csv(args.intervals, DEFAULT_INTERVALS),
            mode=args.mode,
            exchange_id=args.exchange_id,
            quote_asset=args.quote_asset,
            quant_input_root=args.quant_input_root,
            time_start=args.time_start,
            time_end=args.time_end,
            refresh_catalog=args.refresh_catalog,
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
