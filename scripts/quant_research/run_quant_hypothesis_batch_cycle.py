from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import traceback


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research import run_quant_hypothesis_batch_cycle
from enhengclaw.quant_research.lab import QUANT_ARTIFACTS_ROOT, QUANT_INPUT_ROOT, WORKBENCH_ROOT


def _json_default(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the cross-sectional hypothesis batch fast-reject and strict-validation cycle."
    )
    parser.add_argument("--as-of", required=True, help="Sample date in YYYY-MM-DD format.")
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--quant-input-root", type=Path, default=QUANT_INPUT_ROOT)
    parser.add_argument("--workbench-root", type=Path, default=WORKBENCH_ROOT)
    parser.add_argument("--ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--spot-ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--derivatives-external-root", type=Path, default=None)
    parser.add_argument(
        "--compiler-backend",
        default="deterministic",
        help="Compiler backend to use for strict validation candidates.",
    )
    parser.add_argument(
        "--no-auto-api-gap-backfill",
        action="store_true",
        help="Disable suite-specific CoinAPI spot gap backfill during batch preparation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_quant_hypothesis_batch_cycle(
            as_of=args.as_of,
            compiler_backend=args.compiler_backend,
            artifacts_root=args.artifacts_root,
            quant_input_root=args.quant_input_root,
            workbench_root=args.workbench_root,
            ohlcv_external_root=args.ohlcv_external_root,
            spot_ohlcv_external_root=args.spot_ohlcv_external_root,
            derivatives_external_root=args.derivatives_external_root,
            auto_api_gap_backfill=not args.no_auto_api_gap_backfill,
        )
    except Exception:
        print(traceback.format_exc(), file=sys.stderr, end="")
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True, default=_json_default))
    if int(summary.get("strict_survivor_count") or 0) > 0:
        return 0
    return 2 if bool(summary.get("success", True)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
