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

from enhengclaw.quant_research.universe_input_producer import (
    QUANT_ARTIFACTS_ROOT,
    QUANT_INPUT_ROOT,
    run_quant_universe_input_producer,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Produce the PIT liquidity Top 100 quant universe input from local replayable OHLCV history."
    )
    parser.add_argument("--as-of", required=True, help="Producer date in YYYY-MM-DD format.")
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--quant-input-root", type=Path, default=QUANT_INPUT_ROOT)
    parser.add_argument("--spot-ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--perp-ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--ohlcv-external-root", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_quant_universe_input_producer(
            as_of=args.as_of,
            artifacts_root=args.artifacts_root,
            quant_input_root=args.quant_input_root,
            spot_ohlcv_external_root=args.spot_ohlcv_external_root,
            perp_ohlcv_external_root=args.perp_ohlcv_external_root,
            ohlcv_external_root=args.ohlcv_external_root,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
