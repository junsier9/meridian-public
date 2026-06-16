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

from enhengclaw.quant_research.lab import QUANT_ARTIFACTS_ROOT, WORKBENCH_ROOT
from enhengclaw.quant_research.legacy_surface import (
    LEGACY_QUANT_SURFACE_EXIT_CODE,
    LegacyQuantSurfaceFrozenError,
    legacy_surface_summary,
)
from enhengclaw.quant_research.bridge import export_passed_alphas_to_workbench


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage passed quant alphas into a research workbench intake queue.")
    parser.add_argument("--as-of", required=True, help="Research as-of date in YYYY-MM-DD format.")
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--workbench-root", type=Path, default=WORKBENCH_ROOT)
    parser.add_argument("--ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--spot-ohlcv-external-root", type=Path, default=None)
    parser.add_argument("--queue", choices=("quant", "legacy"), default="quant")
    parser.add_argument("--daily-export-cap", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = export_passed_alphas_to_workbench(
            as_of=args.as_of,
            artifacts_root=args.artifacts_root,
            workbench_root=args.workbench_root,
            ohlcv_external_root=args.ohlcv_external_root,
            spot_ohlcv_external_root=args.spot_ohlcv_external_root,
            queue=args.queue,
            daily_export_cap=args.daily_export_cap,
        )
    except LegacyQuantSurfaceFrozenError:
        summary = legacy_surface_summary(
            operation="bridge_export",
            as_of=args.as_of,
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
