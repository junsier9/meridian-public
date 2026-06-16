from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.lab import QUANT_ARTIFACTS_ROOT, WORKBENCH_ROOT
from enhengclaw.quant_research.overlap_rerun import remediate_historical_overlap_reruns


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mark historical quant experiments with broken overlap interval evidence as needing rerun."
    )
    parser.add_argument("--as-of", help="Optional YYYY-MM-DD date to remediate instead of scanning all manifests.")
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--workbench-root", type=Path, default=WORKBENCH_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = remediate_historical_overlap_reruns(
            artifacts_root=args.artifacts_root,
            workbench_root=args.workbench_root,
            as_of=args.as_of,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
