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

from enhengclaw.quant_research.lab import QUANT_ARTIFACTS_ROOT, QUANT_INPUT_ROOT, WORKBENCH_ROOT
from enhengclaw.quant_research.legacy_surface import (
    LEGACY_QUANT_SURFACE_EXIT_CODE,
    LegacyQuantSurfaceFrozenError,
    legacy_surface_summary,
)
from enhengclaw.quant_research.proposals import run_quant_strategy_proposal_cycle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one daily full Quant Research discovery cycle.")
    parser.add_argument("--as-of", help="Discovery date in YYYY-MM-DD format.")
    parser.add_argument("--week-of", help="Legacy alias for --as-of.")
    parser.add_argument(
        "--compiler-backend",
        choices=("deterministic", "live"),
        default="live",
        help="Recorded backend label for the discovery cycle.",
    )
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--quant-input-root", type=Path, default=QUANT_INPUT_ROOT)
    parser.add_argument("--workbench-root", type=Path, default=WORKBENCH_ROOT)
    parser.add_argument("--ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--spot-ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--derivatives-external-root", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    as_of = args.as_of or args.week_of
    if not as_of:
        print("either --as-of or --week-of is required", file=sys.stderr)
        return 2
    try:
        summary = run_quant_strategy_proposal_cycle(
            as_of=as_of,
            week_of=args.week_of,
            compiler_backend=args.compiler_backend,
            artifacts_root=args.artifacts_root,
            quant_input_root=args.quant_input_root,
            workbench_root=args.workbench_root,
            ohlcv_external_root=args.ohlcv_external_root,
            spot_ohlcv_external_root=args.spot_ohlcv_external_root,
            derivatives_external_root=args.derivatives_external_root,
        )
    except LegacyQuantSurfaceFrozenError:
        summary = legacy_surface_summary(
            operation="strategy_proposal_cycle",
            as_of=as_of,
            artifacts_root=args.artifacts_root,
            workbench_root=args.workbench_root,
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return LEGACY_QUANT_SURFACE_EXIT_CODE
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
