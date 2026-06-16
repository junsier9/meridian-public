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
from enhengclaw.quant_research.repo_health import run_quant_repo_health_guard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect, repair, and summarize quant repo health issues.")
    parser.add_argument("--as-of", required=True, help="Quant as-of date in YYYY-MM-DD format.")
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    parser.add_argument("--workbench-root", type=Path, default=WORKBENCH_ROOT)
    parser.add_argument("--now-utc", help="Optional ISO-8601 UTC timestamp for deterministic checks.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    exit_code, summary = run_quant_repo_health_guard(
        as_of=args.as_of,
        repo_root=ROOT,
        artifacts_root=args.artifacts_root,
        workbench_root=args.workbench_root,
        now_utc=args.now_utc,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
