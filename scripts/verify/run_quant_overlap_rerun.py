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
from enhengclaw.quant_research.overlap_rerun import (
    mark_experiments_needing_overlap_rerun,
    write_overlap_rerun_comparison,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare or compare quant overlap reruns.")
    parser.add_argument("--as-of", action="append", required=True, help="One or more as-of dates in YYYY-MM-DD format.")
    parser.add_argument("--mode", choices=("prepare", "compare"), required=True)
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--workbench-root", type=Path, default=WORKBENCH_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = []
    for as_of in args.as_of:
        if args.mode == "prepare":
            results.append(
                mark_experiments_needing_overlap_rerun(
                    artifacts_root=args.artifacts_root,
                    workbench_root=args.workbench_root,
                    as_of=as_of,
                )
            )
        else:
            results.append(
                write_overlap_rerun_comparison(
                    artifacts_root=args.artifacts_root,
                    as_of=as_of,
                )
            )
    print(json.dumps({"mode": args.mode, "results": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
