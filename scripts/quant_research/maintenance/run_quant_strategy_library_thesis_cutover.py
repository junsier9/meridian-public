from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from datetime import datetime


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from enhengclaw.quant_research.governance import cutover_strategy_library_to_thesis_tasks
from enhengclaw.quant_research.runtime_support import QUANT_ARTIFACTS_ROOT


def _default_as_of() -> str:
    return datetime.now().astimezone().date().isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Archive the legacy quant strategy library and rebuild it as a thesis-driven task queue."
    )
    parser.add_argument(
        "--as-of",
        default=_default_as_of(),
        help="Governance as-of date in YYYY-MM-DD format. Defaults to the local calendar date.",
    )
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = cutover_strategy_library_to_thesis_tasks(
            artifacts_root=args.artifacts_root,
            as_of=args.as_of,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
