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

from enhengclaw.quant_research.deterministic_survival import (
    SURVIVAL_WINDOW_DAYS_DEFAULT,
    run_baseline_alpha_survival,
)
from enhengclaw.quant_research.lab import QUANT_ARTIFACTS_ROOT


def _json_default(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate rolling deterministic baseline survival across multiple as_of dates.")
    parser.add_argument("--date-from", required=True, help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--date-to", required=True, help="End date in YYYY-MM-DD format.")
    parser.add_argument("--survival-window-days", type=int, default=SURVIVAL_WINDOW_DAYS_DEFAULT)
    parser.add_argument("--artifacts-root", type=Path, default=QUANT_ARTIFACTS_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_baseline_alpha_survival(
            date_from=args.date_from,
            date_to=args.date_to,
            survival_window_days=args.survival_window_days,
            artifacts_root=args.artifacts_root,
        )
    except Exception:
        print(traceback.format_exc(), file=sys.stderr, end="")
        return 1
    print(json.dumps(report, indent=2, sort_keys=True, default=_json_default))
    return 0 if bool(report.get("started_looking_like_alpha")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
