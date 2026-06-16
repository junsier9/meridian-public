from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import traceback


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.deterministic_survival import run_quant_deterministic_daily_sample
from enhengclaw.quant_research.lab import QUANT_ARTIFACTS_ROOT, QUANT_INPUT_ROOT, WORKBENCH_ROOT


def _json_default(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one deterministic daily sample for longitudinal survival tracking.")
    parser.add_argument("--as-of", required=True, help="Sample date in YYYY-MM-DD format.")
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--quant-input-root", type=Path, default=QUANT_INPUT_ROOT)
    parser.add_argument("--workbench-root", type=Path, default=WORKBENCH_ROOT)
    parser.add_argument("--spot-ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--perp-ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--derivatives-external-root", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        sample = run_quant_deterministic_daily_sample(
            as_of=args.as_of,
            artifacts_root=args.artifacts_root,
            quant_input_root=args.quant_input_root,
            workbench_root=args.workbench_root,
            spot_ohlcv_external_root=args.spot_ohlcv_external_root,
            perp_ohlcv_external_root=args.perp_ohlcv_external_root,
            derivatives_external_root=args.derivatives_external_root,
        )
    except Exception:
        print(traceback.format_exc(), file=sys.stderr, end="")
        return 1
    print(json.dumps(sample, indent=2, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
